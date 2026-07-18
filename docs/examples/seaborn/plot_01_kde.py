"""
Overlapping densities
=====================

``kdeplot`` draws a Gaussian kernel-density estimate. Each curve integrates to
one, so shapes stay comparable across groups of different sizes.
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(7)
groups = {
    "setosa": rng.normal(5.0, 0.35, 300),
    "versicolor": rng.normal(5.9, 0.52, 450),
    "virginica": rng.normal(6.6, 0.64, 380),
}

fig, ax = simpleplot.subplots()
for name, values in groups.items():
    ax.kdeplot(values, fill=True, label=name)
ax.set_xlabel("sepal length (cm)")
ax.set_ylabel("density")
ax.set_title("kdeplot")
ax.legend()
fig.tight_layout()
