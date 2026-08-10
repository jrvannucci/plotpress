"""
Systematic acquisition with an autoscaling colour bar
========================================================

A raster scan collects a whole column at a time, stepping across ``x`` --
more orderly than the sparse case, but its colour scale can't be fixed up
front the way :doc:`plot_01_sparse_fill`'s could: with only a handful of
values in, one noisy point can dominate the range. Autoscaling the colour
bar to whatever has been measured *so far* keeps the plot readable at every
stage, at the cost of a scale that shifts as new extremes come in -- and a
cost specific to autoscaling live: the colour bar itself has to be dropped
and redrawn every update, since it renders from a fixed snapshot of
whatever mappable it was handed, not a live reference to the axes' current
one.

Structured the way a real acquisition script would be: a callback that
receives one finished column at a time and pushes it to the plot, fed here
by a loop simulating a raster scan controller. Swap ``read_next_column()``
for a real instrument call and ``_GalleryLiveArtist`` for
``plotpress.qt.LiveArtist`` and the rest is unchanged.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image


class _GalleryLiveArtist:
    """Doc-build-only stand-in for ``plotpress.qt.LiveArtist`` -- there's no
    Qt binding to drive a real window with at doc-build time, so this only
    reproduces ``update()``'s redraw behavior (``ax.cla()``, replot, and for
    a line the same auto x-limits from the data) and nothing else. Swap it
    for ``from plotpress.qt import PlotPressWidget, LiveArtist`` and
    ``LiveArtist(widget, fig, ax, **plot_kwargs)`` -- every
    ``artist.update(...)`` call below needs no other change; just drop each
    callback's trailing ``_gallery_gif_frames.append(...)`` line, since a
    real ``LiveArtist`` already pushes every frame to the live window
    itself. ``last_artist`` (the ``Line2D``/``QuadMesh`` the most recent
    update drew) isn't part of the real API -- it's only here so a script
    that also needs a per-frame colorbar refresh has something to hand
    ``fig.colorbar()``.
    """

    def __init__(self, ax, **plot_kwargs):
        self.ax = ax
        self.plot_kwargs = plot_kwargs
        self.last_artist = None

    def update(self, *data):
        self.ax.cla()
        if len(data) == 2:
            x, y = data
            self.last_artist = self.ax.plot(x, y, **self.plot_kwargs)
            if len(x):
                self.ax.set_xlim(float(min(x)), float(max(x)))
        elif len(data) == 3:
            x, y, c = data
            self.last_artist = self.ax.pcolormesh(x, y, c, **self.plot_kwargs)
        else:
            raise TypeError("update() takes (x, y) or (x, y, C)")


# ---------------------------------------------------------------------------
# Live plotting -- this half doesn't change when you swap in a real scan.
# ---------------------------------------------------------------------------
NY, NX = 18, 18
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)

fig, ax = plotpress.subplots(figsize=(6, 5))
grid = np.full((NY, NX), np.nan)
mesh = _GalleryLiveArtist(ax, cmap="magma")   # no vmin/vmax -- autoscales every call
_gallery_gif_frames = []
_cbar_ax = None


def on_new_column(col_idx, values):
    """Called once per column the scan finishes -- push it into the grid
    and redraw, autoscaling the colour bar to whatever's been measured so
    far.
    """
    global _cbar_ax
    grid[:, col_idx] = values
    mesh.update(gx, gy, grid)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlabel("x index"); ax.set_ylabel("y index")
    ax.set_title(f"Systematic fill, column {col_idx + 1}/{NX} (autoscaled)")
    if _cbar_ax is not None:
        fig.delaxes(_cbar_ax)
    _cbar_ax = fig.colorbar(mesh.last_artist, ax=ax)
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))   # gallery-only


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own raster scan controller.
# Everything above only needs a column index and its values handed to
# on_new_column() as each column finishes.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(3)
rows, cols = np.meshgrid(np.arange(NY), np.arange(NX), indexing="ij")
field = (np.exp(-((rows - 9) ** 2 + (cols - 13) ** 2) / 30.0) * 8.0
         + np.exp(-((rows - 13) ** 2 + (cols - 4) ** 2) / 20.0) * 5.0
         + 0.15 * rng.standard_normal((NY, NX)))


def read_next_column(col_idx):
    """Stand-in for the scan controller reporting a finished column."""
    return field[:, col_idx]


for col in range(NX):
    on_new_column(col, read_next_column(col))

# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
