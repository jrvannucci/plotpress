"""
Grouping a large grid of panels
==================================

``fig.group()`` scales to a grid far bigger than the previous example's --
here, two 5x3 column-bands (30 ``pcolormesh`` panels total) standing in for
two banks of a sensor array. A group's bounding box only needs to touch the
grid's own outer edge to get a reserved margin for its title; it does not
need to be a single row or column, or made up entirely of edge-row/edge-column
axes -- a column-band spanning every row still reaches row 0, which is what
actually matters.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(0)
nrows, ncols = 5, 6
x = np.linspace(0, 10, 21)
y = np.linspace(0, 5, 11)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(nrows, ncols, figsize=(16, 9))
for i, ax in enumerate(axes.ravel()):
    Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y) + 0.05 * rng.standard_normal(X.shape)
    ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
    ax.set_title(f"panel {i}", fontsize=7)
    ax.tick_params(labelsize=5)

fig.group("Bank A (cols 0-2)", list(axes[:, 0:3].ravel()),
         color="#d62728", linestyle="--", title_position="top")
fig.group("Bank B (cols 3-5)", list(axes[:, 3:6].ravel()),
         color="#1f77b4", linestyle="--", title_position="top")
fig.tight_layout()
