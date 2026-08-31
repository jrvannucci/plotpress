"""
The vector/raster trade at real scale: forcing it past the limit
====================================================================

``pcolormesh``'s auto mode (``rasterized=None``) draws a non-uniform grid as
vector ``<rect>`` cells only under about 2000 of them -- past that it falls
back to rasterizing, because an SVG with one ``<rect>`` per cell scales with
cell count the way a scatter plot's one-mark-per-point does (see
``docs/scale/plot_09_output_scaling.py``). This example builds a grid the
threshold actually matters for: 5000 cells, geometrically clustered toward
one edge the way a boundary-layer mesh refines near a wall -- a real shape,
not a contrived one.

Both directions of the trade show up at once here. Left at auto, **4193 of
the 5000 cells -- 84% of the mesh -- are narrower than one output pixel and
silently vanish**, leaving only 807 actually drawn: exactly the failure
:doc:`plot_04_pcolormesh_vs_imshow` shows one cell of, just nearly the whole
grid at once, because geometric clustering packs most of a boundary-layer
mesh's cells into a sliver of the span. Forcing ``rasterized=False``
recovers all 5000, at roughly 100x the file size the bars below make
concrete. Neither choice is free; the two warnings, caught and printed
below, name exactly what each one costs.
"""
import warnings

import numpy as np
import plotpress

N = 5000
EDGES = np.concatenate([[0.0], np.geomspace(1e-4, 10.0, N)])
Y_EDGES = np.array([0.0, 1.0])
FIELD = np.tile(np.sin(np.linspace(0.0, 6.0, N)), (1, 1))


def _measure(rasterized):
    """(KiB, n_cells, cells_lost, [warning messages]) for one rasterized= choice.

    Builds its own throwaway figure rather than reusing one across calls, kept
    local so it never becomes a module global the doc scraper would embed --
    only the bar-chart figure below is meant to appear in the gallery.
    """
    fig, ax = plotpress.subplots()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mesh = ax.pcolormesh(EDGES, Y_EDGES, FIELD, cmap="viridis",
                             rasterized=rasterized)
    kib = len(fig.to_svg().encode("utf-8")) / 1024.0
    # dropped_x reports what a raster resample *would* drop, computed either
    # way (see artists._resolve_mesh_render) -- only meaningful when this
    # mesh actually rasterizes. A vectorized mesh never drops anything.
    lost = 0 if mesh.vectorized else int(mesh.dropped_x.size)
    return kib, mesh.n_cells, lost, [f"{w.category.__name__}: {w.message}" for w in caught]


kib_auto, n_cells, lost_auto, warnings_auto = _measure(rasterized=None)
kib_vector, _, lost_vector, warnings_vector = _measure(rasterized=False)

fig, (ax_size, ax_cells) = plotpress.subplots(1, 2, figsize=(10.2, 4.4))

x = [0, 1]
labels = ["auto\n(raster)", "rasterized=False\n(vector)"]
colors = ["#2ca02c", "#d62728"]

ax_size.bar(x, [kib_auto, kib_vector], color=colors)
for i, kib in zip(x, [kib_auto, kib_vector]):
    ax_size.text(i, kib, f"{kib:.1f} KiB", ha="center", va="bottom", fontsize=9)
ax_size.set_xticks(x, labels)
ax_size.set_ylabel("SVG size (KiB)")
ax_size.set_title("File size")

drawn = [n_cells - lost_auto, n_cells - lost_vector]
ax_cells.bar(x, drawn, color=colors)
for i, n in zip(x, drawn):
    ax_cells.text(i, n, f"{n}/{n_cells}", ha="center", va="bottom", fontsize=9)
ax_cells.set_xticks(x, labels)
ax_cells.set_ylabel("cells actually drawn")
ax_cells.set_ylim(0, n_cells * 1.15)
ax_cells.set_title(f"Fidelity ({lost_auto} of {n_cells} cells lost at auto)")

fig.suptitle(f"{n_cells} wall-clustered cells: small-and-lossy vs. exact-and-large")
fig.tight_layout()

print(f"auto:   size={kib_auto:.1f} KiB  cells_drawn={n_cells - lost_auto}/{n_cells}")
print(f"forced: size={kib_vector:.1f} KiB  cells_drawn={n_cells - lost_vector}/{n_cells}")
for msg in warnings_auto:
    print(f"[auto warning] {msg}")
for msg in warnings_vector:
    print(f"[forced warning] {msg}")
