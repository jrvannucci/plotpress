"""
Image (imshow)
==============

``alpha`` blends the image into whatever is drawn underneath it -- here, a
scatter of sample points laid down first stays visible through the field.
"""
import numpy as np
import plotpress

rng = np.random.RandomState(0)
g = np.linspace(-3, 3, 120)
X, Y = np.meshgrid(g, g)
Z = np.sin(X ** 2 + Y ** 2)
fig, ax = plotpress.subplots()
ax.scatter(rng.uniform(-3, 3, 40), rng.uniform(-3, 3, 40), color="k", s=12)
im = ax.imshow(Z, cmap="viridis", extent=(-3, 3, -3, 3), alpha=0.6)
ax.set_title("imshow"); fig.colorbar(im, ax=ax)
