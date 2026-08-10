"""
Point by point, raster order
==============================

The slowest and most literal case: one measurement at a time, stepping ``y``
from bottom to top, then taking a single ``x`` step and repeating -- the
order an actual raster-scanning instrument (a probe stage, a laser scanner)
physically sweeps in. The grid and colour scale are both known and fixed
throughout, exactly like :doc:`plot_01_sparse_fill`, so ``pcolormesh_frames``
covers it directly; only the *order* cells fill in differs between the two.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(5)
NY, NX = 15, 20
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)

cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
field = (np.exp(-((rows - 7) ** 2 + (cols - 10) ** 2) / 35.0) * 10.0
         + 0.15 * rng.standard_normal((NY, NX)))

# Column by column, bottom to top within each column -- a real scan stage's
# order, not a shuffled one.
POINTS_PER_FRAME = 6
order = [(r, c) for c in range(NX) for r in range(NY)]
n_frames = int(np.ceil(len(order) / POINTS_PER_FRAME)) + 3   # hold on the full frame

C = np.empty((n_frames, NY, NX))
grid = np.full((NY, NX), np.nan)
for k in range(n_frames):
    lo = k * POINTS_PER_FRAME
    hi = min(lo + POINTS_PER_FRAME, len(order))
    for r, c in order[lo:hi]:
        grid[r, c] = field[r, c]
    C[k] = grid

fig, ax = plotpress.subplots(figsize=(7, 5.5))
m = ax.pcolormesh_frames(gx, gy, C, cmap="cividis")
fig.colorbar(m, ax=ax)
ax.set_aspect("equal")
ax.set_xlabel("x index"); ax.set_ylabel("y index")
ax.set_title("Point by point, raster order")
fig.tight_layout()
