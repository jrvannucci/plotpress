"""
AFM/STM topography raster scan
=================================

A scanning-probe microscope builds its image the way a CRT does: the tip
sweeps the fast axis (x) pixel by pixel, then steps the slow axis (y) and
sweeps back -- the same fixed-grid, fixed-scale, point-by-point order as the
acquisition-pattern gallery's raster example, just with physical units (nm)
and a surface topography stand-in (a grain boundary with a step edge)
instead of an abstract field.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(8)
NY, NX = 20, 28                    # slow axis (y), fast axis (x) pixel counts
FIELD_NM = 200.0                   # scan size, nm

gx = np.linspace(0, FIELD_NM, NX + 1)
gy = np.linspace(0, FIELD_NM, NY + 1)
cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
x_nm = (cols + 0.5) * FIELD_NM / NX
y_nm = (rows + 0.5) * FIELD_NM / NY

# A step edge (grain boundary) plus a rounded hillock -- both common AFM
# topography features -- and a little scan noise.
STEP_HEIGHT_NM = 1.8
step = STEP_HEIGHT_NM / (1.0 + np.exp(-(x_nm + 0.6 * y_nm - 140.0) / 6.0))
hillock = 1.1 * np.exp(-((x_nm - 60.0) ** 2 + (y_nm - 130.0) ** 2) / (2 * 22.0 ** 2))
height_nm = step + hillock + 0.04 * rng.standard_normal((NY, NX))

# Fast axis first (x, one pixel at a time), then step the slow axis (y).
order = [(r, c) for r in range(NY) for c in range(NX)]
PIXELS_PER_FRAME = 12
n_frames = int(np.ceil(len(order) / PIXELS_PER_FRAME)) + 2

C = np.empty((n_frames, NY, NX))
grid = np.full((NY, NX), np.nan)
for k in range(n_frames):
    lo = k * PIXELS_PER_FRAME
    hi = min(lo + PIXELS_PER_FRAME, len(order))
    for r, c in order[lo:hi]:
        grid[r, c] = height_nm[r, c]
    C[k] = grid

fig, ax = plotpress.subplots(figsize=(7, 5.2))
m = ax.pcolormesh_frames(gx, gy, C, cmap="inferno")
fig.colorbar(m, ax=ax)
ax.set_aspect("equal")
ax.set_xlabel("x (nm, fast axis)"); ax.set_ylabel("y (nm, slow axis)")
ax.set_title("AFM topography scan")
fig.tight_layout()
