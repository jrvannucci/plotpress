"""
Wireframe
=========
"""
import numpy as np
import simpleplot

g = np.linspace(-3, 3, 24)
X, Y = np.meshgrid(g, g)
Z = np.exp(-(X ** 2 + Y ** 2) / 6)

fig, ax = simpleplot.subplots(projection="3d", figsize=(5.5, 5))
ax.plot_wireframe(X, Y, Z, color="C0")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
ax.set_title("plot_wireframe")
