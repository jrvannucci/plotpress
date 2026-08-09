"""
Stairs
======
"""
import numpy as np
import plotpress

rng = np.random.default_rng(2)
values = rng.integers(1, 8, size=12)
edges = np.arange(values.size + 1)          # len(values) + 1 bin edges

fig, ax = plotpress.subplots()
ax.stairs(values, edges, color="C0")
ax.set_title("stairs"); ax.set_xlabel("bin edge")
