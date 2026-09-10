"""
GridSpec row/column spans
==========================

``fig.add_gridspec(nrows, ncols)`` supports slicing for axes that cover more
than one cell -- ``gs[0, :]`` spans the whole top row here, sized against the
two ordinary cells below it once :meth:`~plotpress.figure.Figure.tight_layout`
runs.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig = plotpress.Figure(figsize=(7, 6))
gs = fig.add_gridspec(2, 2)
top = fig.add_subplot(gs[0, :])
bottom_left = fig.add_subplot(gs[1, 0])
bottom_right = fig.add_subplot(gs[1, 1])

top.plot(x, np.sin(x), color="#1f77b4")
top.set_title("gs[0, :] -- spans both columns")
bottom_left.plot(x, np.cos(x), color="#d62728")
bottom_left.set_title("gs[1, 0]")
bottom_right.scatter(x[::4], np.sin(x[::4]) * np.cos(x[::4]), s=8, color="#2ca02c")
bottom_right.set_title("gs[1, 1]")
fig.tight_layout()
