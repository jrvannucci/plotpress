"""Stress demo: a 25x20 grid of 500 axes, each a 35x45 pcolormesh.

That is 500 embedded ``<image>`` layers covering 500 * 35 * 45 = 787,500 mesh
cells. In matplotlib every cell of a QuadMesh is vector geometry, so an SVG of
this figure is enormous and slow; plotpress rasterizes each mesh to a single
``<image>``, so the whole figure stays small and renders fast -- this is the
"many axes on one figure" case plotpress is built for.

Run: python examples/mesh_grid_500.py
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress

NROWS, NCOLS = 25, 20          # 500 axes
NY, NX = 35, 45               # pcolormesh grid per axes (rows x cols = pixels)
CMAPS = ["viridis", "plasma", "gray"]


def build():
    # Shared coordinate grid; each axes gets its own field for visual variety.
    x = np.linspace(0, 3, NX)
    y = np.linspace(0, 3, NY)
    X, Y = np.meshgrid(x, y)   # shape (NY, NX) = (35, 45)

    fig, axes = plotpress.subplots(NROWS, NCOLS, figsize=(28, 34))
    flat = axes.ravel()
    for k, ax in enumerate(flat):
        fx = 1 + (k % 7) * 0.6
        fy = 1 + (k % 5) * 0.5
        phase = k * 0.13
        Z = np.sin(fx * X + phase) * np.cos(fy * Y - phase)
        ax.pcolormesh(Z, cmap=CMAPS[k % len(CMAPS)])
        ax.set_xticks([])       # clean tiled look
        ax.set_yticks([])
    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "mesh_grid_500.svg")

    t0 = time.perf_counter()
    fig = build()
    t_build = time.perf_counter() - t0

    t1 = time.perf_counter()
    svg = fig.to_svg()
    t_svg = time.perf_counter() - t1

    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)

    n_axes = NROWS * NCOLS
    n_cells = n_axes * NY * NX
    print(f"axes:          {n_axes}")
    print(f"mesh cells:    {n_cells:,} ({NY}x{NX} per axes)")
    print(f"build time:    {t_build * 1e3:8.1f} ms")
    print(f"serialize svg: {t_svg * 1e3:8.1f} ms")
    print(f"total:         {(t_build + t_svg) * 1e3:8.1f} ms")
    print(f"svg size:      {os.path.getsize(out) / 1024:8.1f} KiB")
    print(f"<image> nodes: {svg.count('<image')}")
    print(f"wrote {out}")
