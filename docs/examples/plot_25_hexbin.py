"""
Hexbin density
==============

Hexagonal 2-D binning of a point cloud, colored by count.
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(0)
x = rng.normal(size=8000)
y = x * 0.6 + rng.normal(size=8000)

fig, ax = simpleplot.subplots()
hb = ax.hexbin(x, y, gridsize=30, cmap="viridis")
ax.set_title("hexbin")
ax.set_xlabel("x")
ax.set_ylabel("y")
fig.colorbar(hb, ax=ax)
