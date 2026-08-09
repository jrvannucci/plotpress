"""
Quiver
======

A field of arrows.
"""
import numpy as np
import plotpress

g = np.linspace(-2, 2, 16)
X, Y = np.meshgrid(g, g)
U, V = -Y, X
fig, ax = plotpress.subplots()
ax.quiver(X, Y, U, V)
ax.set_aspect("equal"); ax.set_title("quiver")
fig.tight_layout()
