"""
Log-scaled colors (LogNorm)
===========================

``LogNorm`` maps color on a log scale, revealing structure across several orders
of magnitude that a linear norm flattens.
"""
import numpy as np
import simpleplot

g = np.linspace(-3, 3, 200)
X, Y = np.meshgrid(g, g)
Z = np.exp(-(X ** 2 + Y ** 2)) * 1000 + 1     # spans ~1 .. 1000

fig, axes = simpleplot.subplots(1, 2, figsize=(10, 4))
m0 = axes[0].pcolormesh(g, g, Z, cmap="inferno")
axes[0].set_title("linear norm")
fig.colorbar(m0, ax=axes[0])
m1 = axes[1].pcolormesh(g, g, Z, cmap="inferno", norm=simpleplot.LogNorm())
axes[1].set_title("LogNorm")
fig.colorbar(m1, ax=axes[1])          # decade ticks, positioned logarithmically
fig.tight_layout()
