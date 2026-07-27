"""
Surface
=======
"""
import numpy as np
import plotpress

g = np.linspace(-3, 3, 60)
X, Y = np.meshgrid(g, g)
Z = np.sin(np.hypot(X, Y))

fig, ax = plotpress.subplots(projection="3d", figsize=(5.5, 5))
surf = ax.plot_surface(X, Y, Z, cmap="viridis")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
ax.set_title("plot_surface"); fig.colorbar(surf, ax=ax)
