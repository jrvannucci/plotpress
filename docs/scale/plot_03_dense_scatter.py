"""
Half a million scatter points
=============================

Scatter is the plot type that scales worst, because unlike a line it cannot be
decimated: every point is an independent mark, and removing one removes
information about density rather than about a silhouette.

plotpress emits the whole collection as **one** ``<path>`` of zero-length
round-capped strokes rather than 500,000 ``<circle>`` elements. That is a factor
of several hundred thousand in node count, and it is also what keeps the markers
a constant size under the interactive zoom: the zoom applies an affine to the
group, and a stroke width can be declared non-scaling where a circle radius
cannot.

The honest counterpoint is on the right. At this density the scatter has stopped
being readable *as a scatter* -- the core saturates and the eye cannot recover
the distribution -- so the same points are binned into a hexbin with a
logarithmic count scale. The left panel is the one that renders quickly; the
right panel is the one that answers the question. Both are worth having, and
this gallery is about the first while being clear that it is rarely the right
choice above about ten thousand points.
"""
import time

import numpy as np
import plotpress

rng = np.random.default_rng(7)

N = 500_000
# Two overlapping populations, so density is the interesting quantity.
x = np.concatenate([rng.normal(-0.6, 0.9, N // 2), rng.normal(1.1, 0.5, N // 2)])
y = np.concatenate([rng.normal(0.4, 0.8, N // 2), rng.normal(-0.5, 1.1, N // 2)])
y += 0.45 * x                                   # correlate them

t0 = time.perf_counter()
fig, axes = plotpress.subplots(1, 2, figsize=(13.0, 5.6), sharex=True, sharey=True)
ax_pts, ax_hex = axes

ax_pts.scatter(x, y, s=1.6, color="#1f77b4", alpha=0.25)
ax_pts.set_xlabel("x")
ax_pts.set_ylabel("y")
ax_pts.set_title(f"{N:,} points as one path")

hb = ax_hex.hexbin(x, y, gridsize=70, cmap="viridis", mincnt=1,
                   norm=plotpress.LogNorm())
fig.colorbar(hb, ax=ax_hex).set_title("points\nper bin")
ax_hex.set_xlabel("x")
ax_hex.set_title("the same points, binned")

ax_pts.set_xlim(-4.5, 3.5)
ax_pts.set_ylim(-4.5, 4.5)
fig.tight_layout()
build_ms = (time.perf_counter() - t0) * 1e3

svg = fig.to_svg()
fig.suptitle(f"Scatter cannot be decimated, only batched or binned -- "
             f"{len(svg) / 1024:.0f} KiB, built in {build_ms:.0f} ms")
