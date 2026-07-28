"""
pcolormesh vs imshow: 1-D coordinates are assumed uniform
=========================================================

On a uniform grid these two are not merely similar -- they emit **byte-identical**
rasters at identical placement. Both rasterize the field to one embedded
``<image>``, so ``pcolormesh(x, y, C)`` with evenly spaced ``x``/``y`` and
``imshow(C, extent=...)`` are the same call by another name. Every gridded field
in the gallery relies on that, and it is exact.

The two part company when the coordinates are **not** evenly spaced, and that is
the limitation. Given 1-D ``x``/``y``, plotpress spans ``min`` to ``max`` and
divides it into equal cells -- it never inspects the spacing. matplotlib instead
derives cell edges from the midpoints between centers, so on the grid below its
boundaries fall at 1, 2, 4 and 8 while plotpress puts them at 3.2, 6.4, 9.6 and
12.8.

The middle panel shows the consequence: the field is drawn with the right colors
in the wrong places. It also covers the wrong *extent* -- the mesh spans the
range of the given centers rather than of the cells they stand for, so it stops
short of the data's true bounds in both axes. Nothing warns about any of this,
because a coordinate vector carries no flag saying whether it is uniform.

**The fix is to pass 2-D coordinates.** Those are treated as cell corners and
scan-converted, which honors whatever spacing they describe -- the right panel.
Use it whenever the grid is logarithmic, adaptively refined, or otherwise
irregular. If the grid really is uniform, prefer the 1-D form: it is the fast
path and it is exact.
"""
import numpy as np
import plotpress

# Five cells whose widths double: 1, 1, 2, 4, 8.
edges = np.array([0.0, 1.0, 2.0, 4.0, 8.0, 16.0])
centers = 0.5 * (edges[:-1] + edges[1:])
y_centers = np.array([0.25, 0.75])
y_edges = np.array([0.0, 0.5, 1.0])

# Varies only in x, so the cell boundaries are unmistakable.
field = np.tile(np.arange(5.0), (2, 1))

fig, axes = plotpress.subplots(1, 3, figsize=(12.5, 4.0))

# Left: imshow is explicit about being uniform -- it takes an extent, not
# coordinates, so nothing is lost in translation.
axes[0].imshow(field, cmap="viridis", origin="lower",
               extent=(edges[0], edges[-1], 0.0, 1.0))
axes[0].set_title("imshow(extent=...): uniform by construction")

# Middle: 1-D coordinates. plotpress divides min..max evenly, so the boundaries
# land in the wrong place.
axes[1].pcolormesh(centers, y_centers, field, cmap="viridis")
axes[1].set_title("pcolormesh 1-D: spacing ignored")

# Right: 2-D corner arrays. Spacing honored.
X, Y = np.meshgrid(edges, y_edges)
axes[2].pcolormesh(X, Y, field, cmap="viridis")
axes[2].set_title("pcolormesh 2-D: spacing honored")

# Dashed marks at the true cell edges, so the disagreement is measurable rather
# than a matter of impression.
for ax in axes:
    for e in edges[1:-1]:
        ax.axvline(e, color="#ffffff", linestyle="--", linewidth=1.2)
    ax.set_xlim(edges[0], edges[-1])
    ax.set_ylim(0.0, 1.0)
    ax.set_yticks([])
    ax.set_xticks(list(edges))
    ax.set_xlabel("x")

fig.suptitle("Dashed lines mark the true cell edges")
fig.tight_layout()
