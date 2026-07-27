"""
Filled area
===========
"""
import numpy as np
import plotpress

x = np.linspace(0, 2 * np.pi, 200)
y = np.sin(x)
fig, ax = plotpress.subplots()
ax.fill_between(x, y, 0.0, alpha=0.4)
ax.plot(x, y)
ax.set_title("fill_between")
fig.tight_layout()
