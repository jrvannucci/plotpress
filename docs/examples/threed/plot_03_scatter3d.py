"""
3-D scatter
===========
"""
import numpy as np
import plotpress

rng = np.random.default_rng(0)
xs, ys, zs = rng.standard_normal((3, 300))
c = xs + ys + zs

fig, ax = plotpress.subplots(projection="3d", figsize=(5.5, 5))
ax.scatter(xs, ys, zs, c=c, cmap="plasma", s=12)
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
ax.set_title("3-D scatter")
