"""
Filled area
===========

``fill_between`` fills vertically, between a curve and a baseline at each
``x``; ``fill_betweenx`` is its transpose -- filling horizontally, between a
curve and a baseline at each ``y``.
"""
import numpy as np
import plotpress

x = np.linspace(0, 2 * np.pi, 200)
y = np.sin(x)

fig, (ax1, ax2) = plotpress.subplots(1, 2, figsize=(9, 4))

ax1.fill_between(x, y, 0.0, alpha=0.4)
ax1.plot(x, y)
ax1.set_title("fill_between")

ax2.fill_betweenx(x, y, 0.0, alpha=0.4, color="#d62728")
ax2.plot(y, x, color="#d62728")
ax2.set_title("fill_betweenx")
fig.tight_layout()
