"""
Point by point, raster order
==============================

The slowest and most literal case: one measurement at a time, stepping ``y``
from bottom to top, then taking a single ``x`` step and repeating -- the
order an actual raster-scanning instrument (a probe stage, a laser scanner)
physically sweeps in. The grid and colour scale are both known and fixed
throughout, exactly like :doc:`plot_01_sparse_fill`; only the *order* cells
fill in differs between the two.

Structured the way a real acquisition script would be: a callback that
receives whatever new points the stage reported since the last tick and
pushes the updated grid to the plot, fed here by a loop simulating a raster
scan stage. Swap ``read_next_points()`` for a real instrument call and
``_GalleryLiveArtist`` for ``plotpress.qt.LiveArtist`` and the rest is
unchanged.
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
    itself.
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
# Live plotting -- this half doesn't change when you swap in a real stage.
# ---------------------------------------------------------------------------
NY, NX = 15, 20
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)
VMIN, VMAX = 0.0, 10.2   # the instrument's own known reading range

fig, ax = plotpress.subplots(figsize=(7, 5.5))
grid = np.full((NY, NX), np.nan)

# One-time setup: draw the still-empty grid so the axes decorations and
# colorbar are in place before any live updates start.
m0 = ax.pcolormesh(gx, gy, grid, cmap="cividis", vmin=VMIN, vmax=VMAX)
ax.set_aspect("equal")
ax.set_xlabel("x index"); ax.set_ylabel("y index")
ax.set_title("Point by point, raster order")
fig.colorbar(m0, ax=ax)
fig.tight_layout()

mesh = _GalleryLiveArtist(ax, cmap="cividis", vmin=VMIN, vmax=VMAX)
_gallery_gif_frames = []


def on_new_points(points):
    """Called once per acquisition tick with whatever ``(row, col, value)``
    points the stage reported since the last one.
    """
    for r, c, v in points:
        grid[r, c] = v
    mesh.update(gx, gy, grid)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlabel("x index"); ax.set_ylabel("y index")
    ax.set_title("Point by point, raster order")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))   # gallery-only


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own raster stage controller.
# Everything above only needs a list of (row, col, value) points handed to
# on_new_points() as they're measured.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(5)
cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
field = np.clip(
    np.exp(-((rows - 7) ** 2 + (cols - 10) ** 2) / 35.0) * 10.0
    + 0.15 * rng.standard_normal((NY, NX)), 0.0, None)

# Column by column, bottom to top within each column -- a real scan stage's
# order, not a shuffled one.
order = [(r, c) for c in range(NX) for r in range(NY)]
POINTS_PER_TICK = 6


def read_next_points(lo, hi):
    """Stand-in for the stage reporting whichever points it measured this
    tick, in raster order.
    """
    return [(r, c, float(field[r, c])) for r, c in order[lo:hi]]


for lo in range(0, len(order), POINTS_PER_TICK):
    hi = min(lo + POINTS_PER_TICK, len(order))
    on_new_points(read_next_points(lo, hi))
for _ in range(3):   # hold on the fully-filled frame for a moment
    _gallery_gif_frames.append(_gallery_gif_frames[-1])

# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
