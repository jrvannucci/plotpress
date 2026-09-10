"""
Many groups sharing one outer edge share one margin
=======================================================

Every column here is its own two-panel group, and every one of them has a
``title_position="top"`` title touching the grid's own top edge -- eight
groups sharing that single edge, not eight interior ones the way the
earlier "many small groups" example mostly used. ``tight_layout()`` still
reserves just *one* band across the top, sized for the single largest
title reaching it, exactly as if there were only one group there: the
eight groups sit side by side along that shared edge, so the band never
needs to be taller than whichever one of them needs the most room, no
matter how many columns share it.

Interior row-pair boundaries are a different story -- as the earlier
examples show, those need their own explicit ``group_spacing(hspace=...)``
room, since no title faces them at all.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(11)
nrows, ncols = 2, 8
x = np.linspace(0, 6, 13)
y = np.linspace(0, 6, 13)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(nrows, ncols, figsize=(16, 4.5))

for col in range(ncols):
    top_ax, bot_ax = axes[0, col], axes[1, col]
    Z = np.sin(X + 0.4 * col) * np.cos(Y - 0.3 * col)
    top_ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
    bot_ax.pcolormesh(x, y, -Z, cmap="viridis", vmin=-1, vmax=1)
    top_ax.set_title("+", fontsize=8)
    bot_ax.set_title("−", fontsize=8)
    top_ax.tick_params(labelsize=5)
    bot_ax.tick_params(labelsize=5)
    fig.group(f"Col {col}", [top_ax, bot_ax], title_position="top",
             pad=4.0, linewidth=1.0)

fig.group_spacing(wspace=10.0)
fig.tight_layout()
