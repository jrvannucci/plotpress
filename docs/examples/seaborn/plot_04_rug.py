"""
Rug of raw observations
=======================

``rugplot`` marks each observation on the axis edge, showing where the sample
actually is -- here, that the left mode is densely sampled and the right one is
not. Tick length is a fraction of the axes, so repeated rugs share a baseline
and none of them disturb the autoscale.
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(7)
setosa = rng.normal(5.0, 0.35, 70)
virginica = rng.normal(6.6, 0.64, 70)

fig, ax = simpleplot.subplots()
ax.kdeplot(np.concatenate([setosa, virginica]), color="#b8c4d9", fill=True,
           alpha=0.45, label="kde")
ax.rugplot(setosa, color="#1f77b4", label="setosa")
ax.rugplot(virginica, color="#d1495b", label="virginica")
ax.set_xlabel("sepal length (cm)")
ax.set_ylabel("density")
ax.set_title("rugplot")
ax.legend()
fig.tight_layout()
