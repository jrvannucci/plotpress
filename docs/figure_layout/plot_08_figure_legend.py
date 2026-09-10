"""
Figure-level legend
=====================

``fig.legend()`` draws one legend for the whole grid instead of repeating the
same entries in every panel -- labels are de-duplicated across axes. The
``"lower center"`` placement (default) reserves a band at that edge and
shrinks the grid to fit, so it never lands on a plot.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, axes = plotpress.subplots(1, 2, figsize=(7, 3.2))
for ax in axes:
    ax.plot(x, np.sin(x), color="#1f77b4", label="sin")
    ax.plot(x, np.cos(x), color="#d62728", linestyle="--", label="cos")
fig.legend(loc="lower center", ncol=2)
fig.tight_layout()
