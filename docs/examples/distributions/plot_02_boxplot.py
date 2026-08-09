"""
Box plot
========
"""
import numpy as np
import plotpress

rng = np.random.default_rng(5)
data = [rng.normal(loc, 1.0, 200) for loc in (0, 1, 2, 1.5)]
fig, ax = plotpress.subplots()
ax.boxplot(data)
ax.set_title("Box plot")
fig.tight_layout()
