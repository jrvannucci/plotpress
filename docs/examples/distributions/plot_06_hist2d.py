"""
2-D histogram
=============
"""
import numpy as np
import plotpress

rng = np.random.default_rng(6)
x = rng.normal(size=5000); y = x + rng.normal(size=5000)
fig, ax = plotpress.subplots()
counts, im = ax.hist2d(x, y, bins=40)
ax.set_title("hist2d"); fig.colorbar(im, ax=ax)
