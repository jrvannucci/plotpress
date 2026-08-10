"""
Point by point, with axes that grow to fit
=============================================

The most general case, combining :doc:`plot_05_point_by_point`'s true
one-measurement-at-a-time raster order with a window that isn't known up
front: the underlying grid exists, but nothing is drawn beyond the bounding
box of what's actually been measured so far, so the visible axes widen a
step at a time right along with the data. Both the mesh shape and the axes
limits change every frame, so -- as with the other growing-extent examples
-- this needs an independent :class:`~plotpress.Figure` per frame rather
than ``pcolormesh_frames``'s one shared grid.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(5)
NY, NX = 15, 20
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)
VMIN, VMAX = 0.0, 10.0

cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
field = (np.exp(-((rows - 7) ** 2 + (cols - 10) ** 2) / 35.0) * 10.0
         + 0.15 * rng.standard_normal((NY, NX)))

# Same raster order as plot_05_point_by_point: column by column, bottom to
# top within each column.
POINTS_PER_FRAME = 6
order = [(r, c) for c in range(NX) for r in range(NY)]
n_frames = int(np.ceil(len(order) / POINTS_PER_FRAME))

_gallery_gif_frames = []
grid = np.full((NY, NX), np.nan)
r_min = r_max = c_min = c_max = None
for k in range(n_frames):
    lo = k * POINTS_PER_FRAME
    hi = min(lo + POINTS_PER_FRAME, len(order))
    for r, c in order[lo:hi]:
        grid[r, c] = field[r, c]
        r_min = r if r_min is None else min(r_min, r)
        r_max = r if r_max is None else max(r_max, r)
        c_min = c if c_min is None else min(c_min, c)
        c_max = c if c_max is None else max(c_max, c)

    fig, ax = plotpress.subplots(figsize=(7, 5.5))
    m = ax.pcolormesh(gx, gy, grid, cmap="cividis", vmin=VMIN, vmax=VMAX)
    fig.colorbar(m, ax=ax)
    ax.set_xlim(c_min, c_max + 1); ax.set_ylim(r_min, r_max + 1)   # bbox of what's revealed
    ax.set_aspect("equal")
    ax.set_xlabel("x index"); ax.set_ylabel("y index")
    ax.set_title(f"Point by point, growing window: {hi}/{len(order)}")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax, m
