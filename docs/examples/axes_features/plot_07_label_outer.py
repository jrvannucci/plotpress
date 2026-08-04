"""
label_outer
===========

``label_outer`` hides tick labels except on the bottom row and left column of
a subplot grid -- a quick declutter for a grid of related panels.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, axes = plotpress.subplots(3, 3, figsize=(7, 7))
for i, ax in enumerate(axes.ravel()):
    ax.plot(x, np.sin(x + i))
    ax.label_outer()
fig.suptitle("label_outer on a 3x3 grid")
