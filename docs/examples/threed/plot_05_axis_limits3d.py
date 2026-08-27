"""
3-D axis limits
===============

``set_xlim3d``/``set_ylim3d``/``set_zlim3d`` fix each axis' data range
explicitly, instead of leaving it to autoscale from the plotted data --
useful for cropping in on part of a series, or for lining up limits across
several 3-D panels.
"""
import numpy as np
import plotpress

t = np.linspace(0, 6 * np.pi, 400)
x, y, z = np.cos(t), np.sin(t), t / (6 * np.pi)

fig, (ax1, ax2) = plotpress.subplots(1, 2, projection="3d", figsize=(10, 5))

ax1.plot(x, y, z, color="C0", linewidth=1.5)
ax1.view_init(elev=25, azim=-50)
ax1.set_title("full range (autoscaled)")

ax2.plot(x, y, z, color="C0", linewidth=1.5)
ax2.set_xlim3d(-1, 1)
ax2.set_ylim3d(-1, 1)
ax2.set_zlim3d(0.0, 0.5)   # crop to the helix's first half-turn upward
ax2.view_init(elev=25, azim=-50)
ax2.set_title("set_*lim3d cropped to z <= 0.5")
