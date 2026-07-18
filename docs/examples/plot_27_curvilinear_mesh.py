"""
Curvilinear pcolormesh
======================

A warped (2-D ``X``/``Y``) grid, scan-converted to a single image in pure NumPy.
"""
import numpy as np
import simpleplot

n = 50
r = np.linspace(0.3, 1.0, n)
th = np.linspace(0, 1.7 * np.pi, n)
R, TH = np.meshgrid(r, th)
X, Y = R * np.cos(TH), R * np.sin(TH)     # 2-D node coordinates
C = np.sin(4 * TH) * R

fig, ax = simpleplot.subplots(figsize=(6, 6))
m = ax.pcolormesh(X, Y, C, cmap="plasma")
ax.set_aspect("equal")
ax.set_title("curvilinear pcolormesh")
fig.colorbar(m, ax=ax)
