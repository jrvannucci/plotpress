"""
Draw order (zorder)
====================

Every artist takes a ``zorder`` -- higher draws on top, ties keep call
order (the previous, only behavior). Useful for pulling a series above
something added later, or pinning a reference band underneath everything
regardless of when it was drawn.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)
fig, ax = plotpress.subplots()

# The line is plotted first -- without zorder it would sit *under* the two
# bands added after it. Its higher zorder keeps it on top regardless.
ax.plot(x, np.sin(x), color="k", linewidth=2, zorder=2, label="signal")
ax.axhspan(-1, 0, color="#d62728", alpha=0.25, zorder=0, label="below zero")
ax.axhspan(0, 1, color="#2ca02c", alpha=0.25, zorder=0, label="above zero")
ax.set_title("zorder: the line stays on top though the bands are added after it")
ax.legend(loc="lower right")
fig.tight_layout()
