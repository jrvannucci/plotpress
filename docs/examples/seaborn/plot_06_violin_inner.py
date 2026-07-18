"""
Violin inner annotations
========================

``inner`` overlays a summary of the raw data inside each violin: ``"box"`` for
an IQR bar with 1.5-IQR whiskers and a median dot, ``"quartile"`` for lines
across the density at Q1/median/Q3, or ``"stick"`` for one line per
observation.
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(7)
groups = [
    rng.normal(5.0, 0.35, 300),
    rng.normal(5.9, 0.52, 300),
    rng.normal(6.6, 0.64, 300),
]
names = ["setosa", "versicolor", "virginica"]

fig, axes = simpleplot.subplots(1, 3, figsize=(12.0, 4.0), sharey=True)
for ax, inner in zip(axes, ["box", "quartile", "stick"]):
    ax.violinplot(groups, cut=2.0, inner=inner)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(names)
    ax.set_title(f'inner="{inner}"')
axes[0].set_ylabel("sepal length (cm)")
fig.tight_layout()
