"""
Polar line
==========
"""
import numpy as np
import plotpress

theta = np.linspace(0, 2 * np.pi, 500)
fig, ax = plotpress.subplots(projection="polar")
ax.plot(theta, np.abs(np.cos(3 * theta)), color="C0", linewidth=1.5)
ax.set_title("polar rose: r = |cos 3θ|")
