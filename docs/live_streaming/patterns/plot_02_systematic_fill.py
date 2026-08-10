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
one. ``LiveArtist.last_artist`` is exactly that snapshot -- see
:doc:`/user_guide/viewing`.

The code below is exactly what you'd write against the real
``plotpress.qt.LiveArtist``: a callback that receives one finished column at
a time and pushes it to the plot, fed by a loop simulating a raster scan
controller. Only ``read_next_column()`` is meant to be replaced, with your
own instrument call.
"""
import numpy as np
import plotpress

# sphinx_gallery_start_ignore
# Doc-build-only harness below: there's no Qt binding to drive a real window
# with at doc-build time, so LiveArtist here reproduces plotpress.qt.
# LiveArtist's update() exactly (ax.cla(), replot, the same auto x-limits for
# a line, the same last_artist bookkeeping) and renders a frame instead of
# pushing one to a live window. None of this -- including this whole
# ignored block -- is part of what a real script using the actual
# LiveArtist would need.
from plotpress.raster import figure_to_image


class LiveArtist:
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


_gallery_gif_frames = []
# sphinx_gallery_end_ignore

NY, NX = 18, 18
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)

fig, ax = plotpress.subplots(figsize=(6, 5))
grid = np.full((NY, NX), np.nan)
mesh = LiveArtist(ax, cmap="magma")   # no vmin/vmax -- autoscales every call
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
    # sphinx_gallery_start_ignore
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))
    # sphinx_gallery_end_ignore


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

# sphinx_gallery_start_ignore
# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
# sphinx_gallery_end_ignore
