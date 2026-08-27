"""
All four title positions at once
===================================

A 4x4 grid split into four 2x2 quadrants, each its own group -- and each
using the one ``title_position`` that actually faces an outer edge from
where it sits: top-left ("top"), top-right ("right"), bottom-left
("left"), bottom-right ("bottom"). All four reach a true edge of the
figure, so ``tight_layout()`` reserves *outer* margin for every one of
them automatically -- including a left/right title's own rendered
*width*, not just a top/bottom title's height.

That reservation only ever applies to the figure's own outer edges,
though: the boundary between the top two quadrants and the bottom two is
an *interior* row gap, and the one between the left two and right two is
an interior column gap -- neither is faced by any of the four groups'
titles, so nothing widens either one for them automatically. Left at their
defaults, the top pair's box and the bottom pair's box would collide at
the row seam, and likewise left/right at the column seam.
``group_spacing(wspace=..., hspace=...)`` gives every box room on every
side, interior boundaries included, without discarding the outer-edge
margins ``tight_layout()`` already reserved for all four titles above.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(9)
x = np.linspace(0, 6, 13)
y = np.linspace(0, 6, 13)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(4, 4, figsize=(10, 9))
for r in range(4):
    for c in range(4):
        Z = np.sin(X * 0.6 + r) * np.cos(Y * 0.6 + c) + 0.05 * rng.standard_normal(X.shape)
        axes[r, c].pcolormesh(x, y, Z, cmap="cividis", vmin=-1.2, vmax=1.2)
        axes[r, c].tick_params(labelsize=6)

fig.group("Top-left", list(axes[0:2, 0:2].ravel()), title_position="top",
         color="#d62728")
fig.group("Top-right", list(axes[0:2, 2:4].ravel()), title_position="right",
         color="#1f77b4")
fig.group("Bottom-left", list(axes[2:4, 0:2].ravel()), title_position="left",
         color="#2ca02c")
fig.group("Bottom-right", list(axes[2:4, 2:4].ravel()), title_position="bottom",
         color="#9467bd")
fig.group_spacing(wspace=24.0, hspace=24.0)
fig.tight_layout()
