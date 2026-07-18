"""
Horizontal violins
==================

``orientation="horizontal"`` lays the violins along the x axis, which keeps
long category names readable. The inner marks follow the orientation.
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(7)
groups = [
    rng.normal(5.0, 0.35, 300),
    rng.normal(5.9, 0.52, 300),
    rng.normal(6.6, 0.64, 300),
]

fig, ax = simpleplot.subplots()
ax.violinplot(groups, orientation="horizontal", cut=2.0, inner="box")
ax.set_yticks([1, 2, 3])
ax.set_yticklabels(["setosa", "versicolor", "virginica"])
ax.set_xlabel("sepal length (cm)")
ax.set_title('violinplot(orientation="horizontal", inner="box")')
fig.tight_layout()
