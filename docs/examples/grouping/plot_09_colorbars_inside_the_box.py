"""
Colorbars stay inside the group box
=======================================

A colorbar steals its space from right next to the axes it's attached to
(``fig.colorbar(mesh, ax=ax)``) -- ``fig.group()``'s box wraps that too, not
just the bare pcolormesh rect, so a colorbar belonging entirely to a group's
own axes never poked out past the box meant to enclose it. Every panel below
has its own, independently labeled colorbar (``fig.colorbar(...).set_title(...)``),
proving this holds panel by panel, not just for one shared bar.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(11)
x = np.linspace(0, 8, 17)
y = np.linspace(0, 5, 11)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(2, 2, figsize=(10, 8.5))
specs = [("dB", -1, 1), ("deg C", 10, 30), ("kPa", 90, 110), ("counts", 0, 200)]
for i, (ax, (label, vmin, vmax)) in enumerate(zip(axes.ravel(), specs)):
    Z = vmin + (vmax - vmin) * (0.5 + 0.5 * np.sin(X * 0.6 + i) * np.cos(Y * 0.5))
    mesh = ax.pcolormesh(x, y, Z, cmap="viridis", vmin=vmin, vmax=vmax)
    ax.set_title(f"sensor {i}", fontsize=9)
    fig.colorbar(mesh, ax=ax).set_title(label)

fig.group("Group A", list(axes[0, :]), title_position="top", color="#1f77b4")
fig.group("Group B", list(axes[1, :]), title_position="bottom", color="#d62728")
# Denser than plot_01's row-pair example, and each panel's own colorbar adds
# more for tight_layout()'s default row gap to clear -- subplots_adjust
# widens it explicitly, same fix as the other tightly packed examples here.
fig.subplots_adjust(left=0.08, right=0.92, top=0.90, bottom=0.09,
                    wspace=0.55, hspace=0.55)
