"""
Group title fontsize, alongside a colorbar
=============================================

Every other example in this section leaves ``fontsize`` at its default (the
figure's own title size); the top group here passes an explicit ``fontsize``
instead, twice the default, to show it's independent of both the axes'
titles and the other group. A shared ``colorbar`` for the bottom group's
axes composes with ``group()`` the same way it would with any other
axes -- the grid is squeezed to make room, then the group box is drawn
around what's left, in either order.
"""
import numpy as np
import plotpress

x = np.linspace(0, 6, 25)
y = np.linspace(0, 4, 17)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(2, 3, figsize=(11, 6))

for c in range(3):
    Z = np.sin(X + c) * np.cos(Y)
    axes[0, c].pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
    axes[0, c].set_title(f"trial {c + 1}", fontsize=9)

meshes = []
for c in range(3):
    Z = np.cos(X - c) * np.sin(Y)
    meshes.append(axes[1, c].pcolormesh(x, y, Z, cmap="magma", vmin=-1, vmax=1))
    axes[1, c].set_title(f"trial {c + 1}", fontsize=9)

fig.group("Baseline sweep", list(axes[0, :]), title_position="top", fontsize=20,
         color="#1f77b4")
fig.group("Calibrated sweep", list(axes[1, :]), title_position="top",
         color="#9467bd")
fig.colorbar(meshes[-1], ax=list(axes[1, :]))

# tight_layout() only auto-reserves margin at the figure's own outer edges --
# the row boundary between the two groups is interior to the grid, and
# neither group's "top" title faces it, so nothing widens that gap on its
# own. subplots_adjust sets every margin explicitly instead, hspace included,
# the same fix used for the interior boundaries in plot_05/06/07.
fig.subplots_adjust(left=0.05, right=0.86, top=0.90, bottom=0.06,
                    wspace=0.25, hspace=0.55)
