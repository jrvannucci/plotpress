"""
Systematic acquisition with an autoscaling colour bar
========================================================

A raster scan collects a whole column at a time, stepping across ``x`` --
more orderly than the sparse case, but its colour scale can't be fixed up
front the way :doc:`plot_01_sparse_fill`'s could: with only a handful of
values in, one noisy point can dominate the range. Autoscaling the colour
bar to whatever has been measured *so far* keeps the plot readable at every
stage, at the cost of a scale that shifts as new extremes come in --
``pcolormesh_frames`` shares one fixed ``Normalize`` across every frame by
design, so this needs an independent :class:`~plotpress.Figure` per frame
instead, each with its own colour scale, stitched into a GIF afterward.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(3)
NY, NX = 18, 18
gx = np.arange(NX + 1, dtype=float)
gy = np.arange(NY + 1, dtype=float)

rows, cols = np.meshgrid(np.arange(NY), np.arange(NX), indexing="ij")
field = (np.exp(-((rows - 9) ** 2 + (cols - 13) ** 2) / 30.0) * 8.0
         + np.exp(-((rows - 13) ** 2 + (cols - 4) ** 2) / 20.0) * 5.0
         + 0.15 * rng.standard_normal((NY, NX)))

grid = np.full((NY, NX), np.nan)
_gallery_gif_frames = []
for col in range(NX):
    grid[:, col] = field[:, col]

    fig, ax = plotpress.subplots(figsize=(6, 5))
    m = ax.pcolormesh(gx, gy, grid, cmap="magma")   # autoscales to grid's finite values
    fig.colorbar(m, ax=ax)
    ax.set_aspect("equal")
    ax.set_xlabel("x index"); ax.set_ylabel("y index")
    ax.set_title(f"Systematic fill, column {col + 1}/{NX} (autoscaled)")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

# Each frame is its own plotpress.Figure, rasterized and discarded above --
# none should linger as a bare global, or the gallery scraper would also
# capture the last one as a redundant static PNG alongside the GIF.
del fig, ax, m
