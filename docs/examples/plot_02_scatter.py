"""
Scatter plot
============

Points colored by a third variable (``c`` + ``cmap``).
"""
import numpy as np
import plotpress

rng = np.random.default_rng(3)
x = rng.normal(size=300); y = x * 0.5 + rng.normal(size=300)
fig, ax = plotpress.subplots()
ax.scatter(x, y, c=x * x + y * y, cmap="plasma", s=14, alpha=0.85)
ax.set_title("Scatter"); ax.set_xlabel("x"); ax.set_ylabel("y")
fig.tight_layout()
