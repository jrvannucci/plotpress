"""
Image (imshow)
==============
"""
import numpy as np
import plotpress

g = np.linspace(-3, 3, 120)
X, Y = np.meshgrid(g, g)
Z = np.sin(X ** 2 + Y ** 2)
fig, ax = plotpress.subplots()
im = ax.imshow(Z, cmap="viridis", extent=(-3, 3, -3, 3))
ax.set_title("imshow"); fig.colorbar(im, ax=ax)
