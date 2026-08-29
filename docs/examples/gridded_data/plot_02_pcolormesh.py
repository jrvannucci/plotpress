"""
Pcolormesh
==========

``alpha`` blends the mesh into whatever is drawn underneath it -- here, a
contour of the same field laid down first stays visible through it.
"""
import numpy as np
import plotpress

g = np.linspace(-3, 3, 200)
X, Y = np.meshgrid(g, g)
Z = np.exp(-(X ** 2 + Y ** 2))
fig, ax = plotpress.subplots()
ax.contour(g, g, Z, levels=6, colors=["#333333"])
m = ax.pcolormesh(g, g, Z, cmap="viridis", alpha=0.7, label="density")
ax.set_title("pcolormesh"); fig.colorbar(m, ax=ax)
