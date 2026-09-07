"""
Discrete bins, a centered diverging scale, and custom colormaps
===================================================================

Four color-mapping additions, together: ``BoundaryNorm`` classifies data into
discrete bins instead of a gradient; ``TwoSlopeNorm`` keeps a diverging
colormap's neutral color pinned to a real reference value even when
``vmin``/``vmax`` aren't symmetric around it; ``make_cmap``/``register_cmap``
build a colormap from any list of colors instead of picking a built-in name;
and ``tab10`` -- already plotpress's default line-color cycle -- doubles as a
*qualitative* colormap for data with no natural ordering, such as a cluster
label.
"""
import numpy as np
import plotpress
from plotpress import BoundaryNorm, TwoSlopeNorm

g = np.linspace(-3, 3, 60)
X, Y = np.meshgrid(g, g)

fig, axes = plotpress.subplots(2, 2, figsize=(10, 9))

# -- BoundaryNorm: classify a field into discrete risk tiers -------------
ax = axes[0, 0]
risk = np.hypot(X, Y)
mesh = ax.pcolormesh(g, g, risk, cmap="YlOrRd",
                     norm=BoundaryNorm([0, 1, 2, 3, 5]))
fig.colorbar(mesh, ax, label="risk tier",
            ticks=[0, 1, 2, 3, 5], format=lambda v: f"{v:g}")
ax.set_title("BoundaryNorm: discrete tiers, not a gradient")

# -- TwoSlopeNorm: keep zero centered despite asymmetric bounds ----------
ax = axes[0, 1]
anomaly = np.sin(X) * 3 - 1.0   # skewed: mostly negative, a few large positives
mesh = ax.pcolormesh(g, g, anomaly, cmap="coolwarm",
                     norm=TwoSlopeNorm(vcenter=0.0))
fig.colorbar(mesh, ax, label="anomaly")
ax.set_title("TwoSlopeNorm: 0 stays white, even off-center")

# -- make_cmap / register_cmap: a colormap from any list of colors ------
ax = axes[1, 0]
register_cmap_name = plotpress.register_cmap(
    "brand-scale", ["#0b1f3a", "#3a6ea5", "#f2c14e"])
mesh = ax.pcolormesh(g, g, np.cos(X) * np.sin(Y), cmap="brand-scale")
fig.colorbar(mesh, ax, label="value")
ax.set_title('register_cmap("brand-scale", [...])')

# -- tab10 as a qualitative colormap: color by class, not by magnitude ---
ax = axes[1, 1]
rng = np.random.default_rng(0)
n = 300
cluster = rng.integers(0, 4, size=n)          # 4 discrete classes, no ordering
xs = rng.normal(size=n) + cluster
ys = rng.normal(size=n) + cluster * 0.5
sc = ax.scatter(xs, ys, c=cluster, cmap="tab10", vmin=0, vmax=9)
ax.set_title("tab10 as a categorical colormap (scatter c=cluster)")

fig.suptitle("BoundaryNorm, TwoSlopeNorm, and custom colormaps")
fig.tight_layout()
