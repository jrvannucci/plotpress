"""
Contour lines
=============

Marching-squares contours of a 2-D field.
"""
import numpy as np
import plotpress

g = np.linspace(-3, 3, 120)
X, Y = np.meshgrid(g, g)
Z = np.sin(X) * np.cos(Y)
fig, ax = plotpress.subplots()
ax.contour(g, g, Z, levels=10)
ax.set_title("contour")
fig.tight_layout()
