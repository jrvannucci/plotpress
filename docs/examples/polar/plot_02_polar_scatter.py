"""
Polar scatter
=============
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(0)
theta = rng.uniform(0, 2 * np.pi, 200)
r = rng.uniform(0.2, 1.0, 200)
fig, ax = simpleplot.subplots(projection="polar")
ax.scatter(theta, r, c=r, cmap="viridis", s=14)
ax.set_title("polar scatter")
