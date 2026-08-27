"""
Side-by-side groups with left/right titles
=============================================

Two groups need not stack (as the row-based "Temperature sweep"/"Pressure
sweep" example does) -- they can sit side by side instead, each labeled on
the outer edge it actually touches: ``title_position="left"`` for the left
half of the grid, ``"right"`` for the right half. Both reach a true outer
edge of the figure, so ``tight_layout()`` reserves margin for each
independently, on its own side.

The boundary between the two halves (column 1 / column 2) is interior,
though, and neither title faces it -- "Before"'s box still needs room for
its own tick labels beyond its bare axes on that side, and "After"'s box
needs the same on its side, so left at ``tight_layout()``'s default column
spacing the two collided right at that seam. ``subplots_adjust`` widens
every column gap explicitly instead, interior boundary included.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(7)
x = np.linspace(0, 10, 21)
y = np.linspace(0, 6, 13)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(2, 4, figsize=(12, 5.5))
flat = axes.ravel()
for i, ax in enumerate(flat):
    row, col = i // 4, i % 4
    noise = 0.5 if col < 2 else 0.1   # left half noisier ("before"), right cleaner ("after")
    Z = np.sin(X * 0.6 + row) * np.cos(Y * 0.5) + noise * rng.standard_normal(X.shape)
    ax.pcolormesh(x, y, Z, cmap="coolwarm", vmin=-1.5, vmax=1.5)
    ax.set_title(f"Run {i}", fontsize=8)
    ax.tick_params(labelsize=6)

fig.group("Before", list(flat[[0, 1, 4, 5]]), color="#7f7f7f", linestyle="--",
         title_position="left")
fig.group("After", list(flat[[2, 3, 6, 7]]), color="#2ca02c", linestyle="--",
         title_position="right")
fig.subplots_adjust(left=0.10, right=0.90, top=0.90, bottom=0.06,
                    wspace=0.18, hspace=0.35)
