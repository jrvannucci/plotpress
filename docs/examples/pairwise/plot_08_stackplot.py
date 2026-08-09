"""
Stack plot
==========
"""
import numpy as np
import plotpress

rng = np.random.default_rng(2)
x = np.arange(10)
a, b, c = (np.abs(rng.normal(2, 0.6, 10)).cumsum() / 3 for _ in range(3))
fig, ax = plotpress.subplots()
ax.stackplot(x, a, b, c, labels=["A", "B", "C"])
ax.set_title("stackplot"); ax.legend()
fig.tight_layout()
