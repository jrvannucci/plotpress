"""
An x axis whose extent isn't known up front
==============================================

Sometimes the sweep range itself is the unknown -- a search that keeps
extending until a stopping condition is met, rather than a pre-planned grid.
Here ``x`` grows one column at a time and the axes limits grow with it,
while ``y`` and the colour scale stay fixed throughout. A growing axis
extent means each frame's mesh has a different shape, which
``pcolormesh_frames`` (one fixed grid shared by every frame) can't express --
so again, one independent :class:`~plotpress.Figure` per frame.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(11)
NY = 18
Y = np.arange(NY + 1, dtype=float)
VMIN, VMAX = 0.0, 10.0

rows = np.arange(NY)
n_steps = 26

_gallery_gif_frames = []
xs_collected = []
cols_collected = []
for step in range(1, n_steps + 1):
    x0 = step - 1
    col = (np.exp(-((rows - 9) ** 2) / 22.0) * 8.0 * np.cos(x0 / 4.0) ** 2
           + 0.15 * rng.standard_normal(NY))
    xs_collected.append(x0)
    cols_collected.append(col)

    X = np.arange(step + 1, dtype=float)
    C = np.column_stack(cols_collected)

    fig, ax = plotpress.subplots(figsize=(7, 4.5))
    m = ax.pcolormesh(X, Y, C, cmap="plasma", vmin=VMIN, vmax=VMAX)
    fig.colorbar(m, ax=ax)
    ax.set_xlim(0, n_steps)          # fixed frame -- shows how far there is to go
    ax.set_xlabel("x (sweep step)"); ax.set_ylabel("y index")
    ax.set_title(f"Growing x axis: {step}/{n_steps} columns collected")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax, m
