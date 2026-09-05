"""
500 panels, 250 groups, each with its own colorbar
======================================================

The flagship case for everything the grouping gallery covers at once: a
20x25 grid (500 ``pcolormesh`` panels), paired top-to-bottom into 250
groups -- each pair its own group, each panel its own colorbar, and each
group's box cycling through four accent colors so a reader can tell
neighboring groups apart at a glance without reading every title.

This is also what motivated :func:`~plotpress.figure.Figure.group`'s
``max()``-not-``+=`` outer-margin fix: 25 of these 250 groups (one per
column) share the grid's own top edge, all title-facing. They still need
only *one* correctly-sized top margin between them -- not one that grows
with how many columns happen to reach that edge.

Every panel keeps its own tick numbers rather than hiding the inner ones
the way a ``sharex``/``sharey`` grid would -- a figure-level
:meth:`~plotpress.figure.Figure.supxlabel`/
:meth:`~plotpress.figure.Figure.supylabel` still names the shared axis
once, but each panel's own 0/0.5/1 stays readable at a glance rather than
only appearing at the true grid edges. Building all 500 panels, their
colorbars, and every group box still takes well under a second -- see the
:ref:`scale gallery <scale_gallery>` for what happens well past this size.
"""
import numpy as np
import plotpress

GROUP_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]  # blue/red/green/purple

NROWS, NCOLS = 20, 25   # 500 panels, 250 top/bottom groups
MESH_N = 20              # 20x20 mesh per panel

fig, axes = plotpress.subplots(NROWS, NCOLS, figsize=(NCOLS * 1.1, NROWS * 1.1))

x_edges = np.linspace(0, 1, MESH_N + 1)
# A smooth Gaussian-plus-ripple field per panel (the same shape as the
# gridded_data gallery's own gouraud-shading example), each with a shifted
# center and frequency so every panel looks distinct without being pure
# noise -- real structure to read a colorbar value off of.
g = np.linspace(-3, 3, MESH_N)
Xc, Yc = np.meshgrid(g, g)

group_idx = 0
for col in range(NCOLS):
    for row_pair in range(NROWS // 2):
        top_row, bot_row = row_pair * 2, row_pair * 2 + 1
        color = GROUP_COLORS[group_idx % len(GROUP_COLORS)]
        pair_axes = []
        for r in (top_row, bot_row):
            ax = axes[r][col]
            cx = 1.6 * np.sin(0.6 * col + 0.3 * r)
            cy = 1.6 * np.cos(0.5 * row_pair - 0.4 * col)
            freq = 1.3 + 0.15 * (r % 3)
            z = (np.exp(-((Xc - cx) ** 2 + (Yc - cy) ** 2) / 4)
                 + 0.3 * np.sin(freq * Xc) * np.cos(freq * Yc))
            mesh = ax.pcolormesh(x_edges, x_edges, z, cmap="viridis")
            ax.set_title(f"panel {r}–{col}", fontsize=5)
            ax.tick_params(labelsize=4)
            fig.colorbar(mesh, ax=ax, fraction=0.08)
            pair_axes.append(ax)
        fig.group(f"Group {group_idx}", pair_axes, color=color, linewidth=1.0,
                 fontsize=5)
        group_idx += 1

fig.group_spacing(wspace=10, hspace=28)
fig.suptitle("500 grouped pcolormesh panels")
fig.supxlabel("global x")
fig.supylabel("global y")
fig.tight_layout()
