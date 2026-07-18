"""
Filled contours (contourf)
==========================

Filled contour bands via a banded colormap; the result backs a colorbar.
"""
import numpy as np
import simpleplot

g = np.linspace(-3, 3, 120)
X, Y = np.meshgrid(g, g)
Z = np.sin(X) * np.cos(Y) + 0.3 * (X + Y)

fig, ax = simpleplot.subplots()
cf = ax.contourf(g, g, Z, levels=12, cmap="plasma")
ax.set_title("contourf")
fig.colorbar(cf, ax=ax)
