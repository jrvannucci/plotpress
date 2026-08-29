"""
Horizontal bar chart
====================

``xerr`` draws error bars on the value axis, centered at each bar's own
right edge -- the horizontal-bar counterpart of ``bar``'s own ``yerr``.
"""
import numpy as np
import plotpress

y = np.arange(6)
fig, ax = plotpress.subplots()
ax.barh(y, [3, 7, 2, 5, 8, 4], xerr=[0.4, 0.9, 0.3, 0.6, 1.1, 0.5],
       color="#2ca02c", capsize=4)
ax.set_yticks(y); ax.set_title("barh"); ax.set_xlabel("value")
fig.tight_layout()
