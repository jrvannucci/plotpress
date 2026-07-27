"""
3-D line (parametric)
=====================
"""
import numpy as np
import plotpress

t = np.linspace(0, 6 * np.pi, 400)
fig, ax = plotpress.subplots(projection="3d", figsize=(5.5, 5))
ax.plot(np.cos(t), np.sin(t), t / (6 * np.pi), color="C0", linewidth=1.5)
ax.view_init(elev=25, azim=-50)
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
ax.set_title("3-D helix")
