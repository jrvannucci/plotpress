"""
axis() convenience
===================

matplotlib's overloaded ``axis()``: ``'equal'`` fixes a 1:1 aspect ratio,
``[xmin, xmax, ymin, ymax]`` sets both limits in one call.
"""
import numpy as np
import plotpress

theta = np.linspace(0, 2 * np.pi, 200)

fig, (ax1, ax2) = plotpress.subplots(1, 2, figsize=(8, 4))
ax1.plot(np.cos(theta), np.sin(theta))
ax1.axis("equal")
ax1.set_title("axis('equal')")

ax2.plot(theta, np.sin(theta))
ax2.axis([0, 3, -0.5, 1.2])
ax2.set_title("axis([xmin, xmax, ymin, ymax])")
fig.tight_layout()
