"""
Margins and autoscale
======================

``margins`` sets a *persistent* padding fraction that keeps re-applying as
more data is added; ``autoscale(enable=False)`` freezes the current limits so
later data no longer moves them. ``set_xmargin``/``set_ymargin`` are the
per-axis equivalent of ``margins(x=...)``/``margins(y=...)`` -- handy when
only one axis needs a different padding fraction than the other.
"""
import numpy as np
import plotpress

fig, (ax1, ax2, ax3) = plotpress.subplots(1, 3, figsize=(11, 3.5))

ax1.plot([0, 10], [0, 5])
ax1.margins(0.2)
ax1.plot([0, 100], [1, 6])         # added after margins() -- still padded 20%
ax1.set_title("margins(0.2) persists")

ax2.plot([0, 10], [0, 5])
ax2.autoscale(enable=False, axis="x")
ax2.plot([0, 1000], [1, 6])        # x is frozen; new data no longer widens it
ax2.set_title("autoscale(False) freezes x")

ax3.plot([0, 10], [0, 5])
ax3.set_xmargin(0.05)               # tight on x
ax3.set_ymargin(0.4)                 # loose on y
ax3.set_title("set_xmargin/set_ymargin")
fig.tight_layout()
