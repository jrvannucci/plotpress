"""
Histogram
=========
"""
import numpy as np
import plotpress

rng = np.random.default_rng(0)
fig, ax = plotpress.subplots()
ax.hist(rng.normal(size=1000), bins=25)
ax.set_title("Histogram"); ax.set_xlabel("value"); ax.set_ylabel("count")
fig.tight_layout()
