"""
A different spine color per axes
===================================

Setting all four sides of ``ax.spines`` to the same color gives an axes a
single-color box outline -- looping that over a grid gives every panel its
own, which is a handy way to color-code panels that belong to different
groups or datasets.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)
colors = ["red", "green", "blue", "orange"]

fig, axes = plotpress.subplots(2, 2, figsize=(7, 6))
for ax, color, phase in zip(axes.ravel(), colors, range(4)):
    ax.plot(x, np.sin(x + phase))
    for spine in ax.spines.values():
        spine.set_color(color)
        spine.set_linewidth(2.0)
    ax.set_title(color)
fig.suptitle("one spine color per axes")
fig.tight_layout()
