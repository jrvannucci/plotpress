"""
Bar chart
=========

``yerr`` draws error bars (whiskers + caps) centered at each bar's own top.
"""
import numpy as np
import plotpress

cats = np.arange(6)
fig, ax = plotpress.subplots()
ax.bar(cats, [3, 7, 2, 5, 8, 4], yerr=[0.4, 0.9, 0.3, 0.6, 1.1, 0.5], capsize=4)
ax.set_xticks(cats); ax.set_title("Bar chart"); ax.set_ylabel("value")
fig.tight_layout()
