"""
Per-axes facecolor
===================

``set_facecolor`` colors one axes' own background, independent of the figure
and of every other axes -- unlike the figure-wide ``Style``, which every axes
shares by default.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, axes = plotpress.subplots(1, 2, figsize=(8, 3.5))
axes[0].plot(x, np.sin(x), color="#1f77b4")
axes[0].set_title("default")

axes[1].plot(x, np.sin(x), color="#1f77b4")
axes[1].set_facecolor("#f0f0f7")
axes[1].set_title("set_facecolor")
fig.tight_layout()
