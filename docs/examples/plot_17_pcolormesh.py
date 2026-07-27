"""
Pcolormesh
==========
"""
import numpy as np
import plotpress

g = np.linspace(-3, 3, 200)
X, Y = np.meshgrid(g, g)
Z = np.exp(-(X ** 2 + Y ** 2))
fig, ax = plotpress.subplots()
m = ax.pcolormesh(g, g, Z, cmap="viridis")
ax.set_title("pcolormesh"); fig.colorbar(m, ax=ax)
