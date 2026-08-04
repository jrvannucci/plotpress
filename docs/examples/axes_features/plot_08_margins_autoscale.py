"""
Margins and autoscale
======================

``margins`` sets a *persistent* padding fraction that keeps re-applying as
more data is added; ``autoscale(enable=False)`` freezes the current limits so
later data no longer moves them.
"""
import numpy as np
import plotpress

fig, (ax1, ax2) = plotpress.subplots(1, 2, figsize=(8, 3.5))

ax1.plot([0, 10], [0, 5])
ax1.margins(0.2)
ax1.plot([0, 100], [1, 6])         # added after margins() -- still padded 20%
ax1.set_title("margins(0.2) persists")

ax2.plot([0, 10], [0, 5])
ax2.autoscale(enable=False, axis="x")
ax2.plot([0, 1000], [1, 6])        # x is frozen; new data no longer widens it
ax2.set_title("autoscale(False) freezes x")
fig.tight_layout()
