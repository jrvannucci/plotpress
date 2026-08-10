"""
Sparse, randomly-ordered acquisition
=====================================

A real 2-D sweep -- a lock-in scan, a resonance map, anything gathered point
by point rather than rendered all at once -- rarely fills its grid in raster
order, and it's mostly ``NaN`` until it's done. ``pcolormesh`` already treats
``NaN`` as "no data" (it just leaves that cell blank), so a mesh with a fixed
grid and a fixed colour scale animates the fill-in with nothing more than
plain ``pcolormesh`` calls and a running array -- no special handling for
the gaps.

The code below is exactly what you'd write against the real
``plotpress.qt.LiveArtist``: a callback that receives whatever new cells the
instrument reported since the last tick and pushes the updated grid to the
plot, fed by a loop simulating a sweep controller. Only ``read_next_cells()``
is meant to be replaced, with your own instrument call.
"""
import numpy as np
import plotpress

# sphinx_gallery_start_ignore
# Doc-build-only harness below: there's no Qt binding to drive a real window
# with at doc-build time, so LiveArtist here reproduces plotpress.qt.
# LiveArtist's update() exactly (ax.cla(), replot, the same auto x-limits for
# a line) and renders a frame instead of pushing one to a live window. None
# of this -- including this whole ignored block -- is part of what a real
# script using the actual LiveArtist would need.
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
VMIN, VMAX = 0.0, 10.5   # the instrument's own known reading range

fig, ax = plotpress.subplots(figsize=(6, 5))
grid = np.full((NY, NX), np.nan)

# One-time setup: draw the still-empty grid so the axes decorations and
# colorbar are in place before any live updates start.
m0 = ax.pcolormesh(gx, gy, grid, cmap="viridis", vmin=VMIN, vmax=VMAX)
ax.set_aspect("equal")
ax.set_xlabel("x index"); ax.set_ylabel("y index")
ax.set_title("Sparse, random-order fill")
fig.colorbar(m0, ax=ax)
fig.tight_layout()

mesh = LiveArtist(ax, cmap="viridis", vmin=VMIN, vmax=VMAX)


def on_new_cells(cells):
    """Called once per acquisition tick with whatever ``(row, col, value)``
    cells the sweep reported since the last one, in whatever order they
    came back.
    """
    for r, c, v in cells:
        grid[r, c] = v
    mesh.update(gx, gy, grid)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlabel("x index"); ax.set_ylabel("y index")
    ax.set_title("Sparse, random-order fill")
    fig.tight_layout()
    # sphinx_gallery_start_ignore
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))
    # sphinx_gallery_end_ignore


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own sweep controller. Every-
# thing above only needs a list of (row, col, value) cells handed to
# on_new_cells() as they're measured.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(7)
rows, cols = np.meshgrid(np.arange(NY), np.arange(NX), indexing="ij")
field = np.clip(
    np.exp(-((rows - 9) ** 2 + (cols - 9) ** 2) / 40.0) * 10.0
    + 0.2 * rng.standard_normal((NY, NX)), 0.0, None)
order = rng.permutation(NY * NX)
CELLS_PER_TICK = 8


def read_next_cells(lo, hi):
    """Stand-in for the instrument reporting whichever cells it measured
    this tick -- sparse and randomly ordered, not a raster scan.
    """
    flats = order[lo:hi]
    rr, cc = np.unravel_index(flats, (NY, NX))
    return list(zip(rr.tolist(), cc.tolist(), field[rr, cc].tolist()))


for lo in range(0, len(order), CELLS_PER_TICK):
    hi = min(lo + CELLS_PER_TICK, len(order))
    on_new_cells(read_next_cells(lo, hi))

# sphinx_gallery_start_ignore
for _ in range(2):   # hold on the fully-filled frame for a moment
    _gallery_gif_frames.append(_gallery_gif_frames[-1])
# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
# sphinx_gallery_end_ignore
