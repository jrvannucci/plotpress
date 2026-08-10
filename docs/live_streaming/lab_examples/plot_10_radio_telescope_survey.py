"""
Radio telescope beam map, serpentine scan
=============================================

An on-the-fly sky survey doesn't raster back to the start of each row --
that would waste half the observing time slewing the dish. It scans one row
left to right, steps down, then scans right to left, alternating direction
every row (a "boustrophedon" or serpentine pattern) so the telescope is
always integrating, never just repositioning. The grid and colour scale are
both fixed by the survey plan, exactly like the acquisition-pattern
gallery's raster example -- only the *order* pixels arrive in differs.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(19)
NY, NX = 22, 34                  # declination steps, right-ascension steps
gx = np.linspace(-1.5, 1.5, NX + 1)   # degrees, RA offset
gy = np.linspace(-1.0, 1.0, NY + 1)   # degrees, Dec offset

cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
ra = (cols + 0.5) * 3.0 / NX - 1.5
dec = (rows + 0.5) * 2.0 / NY - 1.0

# Background sky temperature plus two point sources of different brightness.
SOURCES = [(-0.5, 0.3, 8.0, 0.06), (0.6, -0.2, 4.5, 0.05)]
temp_k = 2.7 + 0.05 * rng.standard_normal((NY, NX))
for src_ra, src_dec, peak, width in SOURCES:
    temp_k += peak * np.exp(-((ra - src_ra) ** 2 + (dec - src_dec) ** 2) / (2 * width ** 2))

# Serpentine order: row 0 left to right, row 1 right to left, and so on.
order = []
for r in range(NY):
    cols_this_row = range(NX) if r % 2 == 0 else range(NX - 1, -1, -1)
    order.extend((r, c) for c in cols_this_row)

PIXELS_PER_FRAME = 10
n_frames = int(np.ceil(len(order) / PIXELS_PER_FRAME)) + 2

C = np.empty((n_frames, NY, NX))
grid = np.full((NY, NX), np.nan)
for k in range(n_frames):
    lo = k * PIXELS_PER_FRAME
    hi = min(lo + PIXELS_PER_FRAME, len(order))
    for r, c in order[lo:hi]:
        grid[r, c] = temp_k[r, c]
    C[k] = grid

fig, ax = plotpress.subplots(figsize=(8, 5.2))
m = ax.pcolormesh_frames(gx, gy, C, cmap="magma")
fig.colorbar(m, ax=ax)
ax.set_aspect("equal")
ax.set_xlabel("RA offset (deg)"); ax.set_ylabel("Dec offset (deg)")
ax.set_title("On-the-fly sky survey, serpentine scan")
fig.tight_layout()
