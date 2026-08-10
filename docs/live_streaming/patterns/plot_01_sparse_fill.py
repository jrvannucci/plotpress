"""
Sparse, randomly-ordered acquisition
=====================================

A real 2-D sweep -- a lock-in scan, a resonance map, anything gathered point
by point rather than rendered all at once -- rarely fills its grid in raster
order, and it's mostly ``NaN`` until it's done. ``pcolormesh`` already treats
``NaN`` as "no data" (it just leaves that cell blank), so a mesh with a fixed
grid and a fixed colour scale animates the fill-in with nothing more than
``pcolormesh_frames`` and a cumulative array per frame -- no special handling
for the gaps.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(7)
NY, NX = 18, 18
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)

rows, cols = np.meshgrid(np.arange(NY), np.arange(NX), indexing="ij")
field = (np.exp(-((rows - 9) ** 2 + (cols - 9) ** 2) / 40.0) * 10.0
         + 0.2 * rng.standard_normal((NY, NX)))

order = rng.permutation(NY * NX)
CELLS_PER_FRAME = 8
n_frames = int(np.ceil(len(order) / CELLS_PER_FRAME)) + 2   # +2: hold on the full frame

C = np.empty((n_frames, NY, NX))
grid = np.full((NY, NX), np.nan)
for k in range(n_frames):
    lo = k * CELLS_PER_FRAME
    hi = min(lo + CELLS_PER_FRAME, len(order))
    for flat in order[lo:hi]:
        r, c = divmod(flat, NX)
        grid[r, c] = field[r, c]
    C[k] = grid

fig, ax = plotpress.subplots(figsize=(6, 5))
m = ax.pcolormesh_frames(gx, gy, C, cmap="viridis")
fig.colorbar(m, ax=ax)
ax.set_aspect("equal")
ax.set_xlabel("x index"); ax.set_ylabel("y index")
ax.set_title("Sparse, random-order fill")
fig.tight_layout()
