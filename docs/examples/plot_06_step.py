"""
Step plot
=========
"""
import numpy as np
import plotpress

rng = np.random.default_rng(1)
x = np.arange(12)
fig, ax = plotpress.subplots()
ax.step(x, rng.integers(0, 8, 12), where="mid")
ax.set_title("Step plot")
fig.tight_layout()
