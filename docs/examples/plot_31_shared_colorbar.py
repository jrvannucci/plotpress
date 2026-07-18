"""
Shared colorbar over a grid
===========================

One colorbar describing a whole grid of axes -- pass the list of axes and
simpleplot squeezes the grid to make room. All panels share ``vmin``/``vmax``.
"""
import numpy as np
import simpleplot

g = np.linspace(-3, 3, 60)
X, Y = np.meshgrid(g, g)

fig, axes = simpleplot.subplots(2, 3, figsize=(11, 6))
m = None
for k, ax in enumerate(axes.ravel()):
    Z = np.exp(-((X - (k - 2)) ** 2 + Y ** 2) / 2.0)
    m = ax.pcolormesh(g, g, Z, cmap="magma", vmin=0, vmax=1)
    ax.set_xticks([])
    ax.set_yticks([])
fig.colorbar(m, ax=axes)
fig.suptitle("one shared colorbar")
