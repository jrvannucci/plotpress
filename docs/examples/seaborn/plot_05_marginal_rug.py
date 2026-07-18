"""
Marginal rugs on a scatter
==========================

``side="left"`` rugs the y axis, so a scatter can carry both marginal
distributions without the extra axes a jointplot would need.
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(11)
n = 250
x = rng.normal(5.9, 0.7, n)
y = 0.55 * x + rng.normal(0.0, 0.35, n)

fig, ax = simpleplot.subplots()
ax.scatter(x, y, s=14, color="#1f77b4", alpha=0.55)
ax.rugplot(x, color="#1f77b4", alpha=0.6)
ax.rugplot(y, side="left", color="#1f77b4", alpha=0.6)
ax.set_xlabel("sepal length (cm)")
ax.set_ylabel("petal length (cm)")
ax.set_title("scatter with marginal rugs")
fig.tight_layout()
