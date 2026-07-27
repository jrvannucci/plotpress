"""
Polar fill
==========
"""
import numpy as np
import plotpress

theta = np.linspace(0, 2 * np.pi, 400)
r = 0.6 + 0.3 * np.sin(4 * theta)
fig, ax = plotpress.subplots(projection="polar")
ax.fill(theta, r, color="C1", alpha=0.5)
ax.plot(theta, r, color="C1")
ax.set_title("polar fill")
