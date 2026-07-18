"""
Gouraud shading
===============

``shading="gouraud"`` interpolates color smoothly between grid nodes instead of
drawing flat cells.
"""
import numpy as np
import simpleplot

g = np.linspace(-3, 3, 24)
X, Y = np.meshgrid(g, g)
C = np.exp(-(X ** 2 + Y ** 2) / 4) + 0.3 * np.sin(2 * X) * np.cos(2 * Y)

fig, axes = simpleplot.subplots(1, 2, figsize=(10, 4))
axes[0].pcolormesh(g, g, C, cmap="viridis")
axes[0].set_title("flat")
axes[1].pcolormesh(X, Y, C, cmap="viridis", shading="gouraud")
axes[1].set_title("gouraud")
fig.suptitle("shading: flat vs gouraud")
fig.tight_layout()
