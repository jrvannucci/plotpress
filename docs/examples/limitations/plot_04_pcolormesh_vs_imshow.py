"""
Non-uniform meshes resample, and the raster has a floor
=======================================================

``pcolormesh`` and ``imshow`` are the same call on a uniform grid: both
rasterize the field to one embedded ``<image>``, and given evenly spaced
coordinates they emit **byte-identical** rasters at identical placement. The
difference is what they accept. ``imshow`` takes an ``extent`` and is uniform by
construction; ``pcolormesh`` takes coordinates and honors whatever spacing they
describe.

Honoring it costs something. The mesh is one image stretched linearly across the
extent, so equal-width pixels cannot represent unequal cells -- plotpress
resamples, assigning each output pixel the cell its center falls inside. The
output is sized to resolve the *narrowest* cell, capped at 1024 pixels per axis.

**Past that cap a cell thinner than one pixel cannot be drawn.** The left panel
below has a width ratio of 40:1 and every cell survives. The right panel pushes
one cell to 1/4000 of the span; it is narrower than a pixel of the raster and
disappears, while its neighbours stay in the right places. Nothing warns about
it, because at that ratio no single raster of any fixed size could show the cell
and its neighbours at once.

If you need a decade-spanning axis drawn faithfully, use a log scale so the
cells are uniform in the coordinate actually being rasterized, rather than a
linear axis with geometrically spaced edges.
"""
import numpy as np
import plotpress

# Left: a 40:1 ratio, comfortably resolvable. Right: 4000:1, past the cap.
MODERATE = np.array([0.0, 1.0, 2.0, 6.0, 16.0, 40.0])
EXTREME = np.array([0.0, 0.01, 2.0, 6.0, 16.0, 40.0])

field = np.tile(np.arange(5.0), (2, 1))
y_edges = np.array([0.0, 0.5, 1.0])

fig, axes = plotpress.subplots(1, 2, figsize=(12.0, 3.8))
for ax, edges, label in ((axes[0], MODERATE, "40:1 -- all five cells drawn"),
                         (axes[1], EXTREME, "4000:1 -- the thin cell is lost")):
    ax.pcolormesh(edges, y_edges, field, cmap="viridis", vmin=0.0, vmax=4.0)
    for e in edges[1:-1]:
        ax.axvline(e, color="#ffffff", linestyle="--", linewidth=1.2)
    ratio = np.diff(edges).max() / np.diff(edges).min()
    ax.set_title(f"{label}  (ratio {ratio:.0f}:1)")
    ax.set_xlim(edges[0], edges[-1])
    ax.set_ylim(0.0, 1.0)
    ax.set_yticks([])
    ax.set_xlabel("x")

fig.suptitle("Dashed lines mark the true cell edges")
fig.tight_layout()
