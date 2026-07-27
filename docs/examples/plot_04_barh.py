"""
Horizontal bar chart
====================
"""
import numpy as np
import plotpress

y = np.arange(6)
fig, ax = plotpress.subplots()
ax.barh(y, [3, 7, 2, 5, 8, 4], color="#2ca02c")
ax.set_yticks(y); ax.set_title("barh"); ax.set_xlabel("value")
fig.tight_layout()
