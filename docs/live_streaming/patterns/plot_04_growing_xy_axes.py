"""
Both axes growing: a search window expanding outward
========================================================

Combine :doc:`plot_03_growing_xaxis` with the same growth in ``y``: a search
that starts small and widens its window in both directions each time the
edge of what's been measured still looks interesting -- outward from a seed
region rather than sweeping the same fixed range. Both axes limits *and* the
mesh shape change every frame, which is the case
``pcolormesh_frames``'s shared grid can least accommodate, and the case
where an independent :class:`~plotpress.Figure` per frame earns its keep the
most.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(23)
VMIN, VMAX = 0.0, 10.0
CX, CY = 20.0, 20.0   # true peak of the field being searched for


def measure(gx, gy):
    xs, ys = np.meshgrid(gx, gy)
    return (np.exp(-((xs - CX) ** 2 + (ys - CY) ** 2) / 60.0) * 10.0
            + 0.15 * rng.standard_normal(xs.shape))


half_steps = list(range(2, 22, 2))   # window half-width grows 2, 4, 6, ... 20

_gallery_gif_frames = []
for half in half_steps:
    lo, hi = CX - half, CX + half
    n = 2 * half + 1
    gx = np.linspace(lo, hi, n)
    gy = np.linspace(CY - half, CY + half, n)
    C = measure(gx, gy)

    fig, ax = plotpress.subplots(figsize=(6, 5.5))
    m = ax.pcolormesh(gx, gy, C, cmap="viridis", vmin=VMIN, vmax=VMAX)
    fig.colorbar(m, ax=ax)
    ax.set_aspect("equal")
    ax.set_xlim(CX - 21, CX + 21); ax.set_ylim(CY - 21, CY + 21)   # fixed frame
    ax.set_xlabel("x"); ax.set_ylabel("y")
    ax.set_title(f"Search window: +-{half}")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax, m
