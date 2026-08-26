"""
Reload a mesh grid and replot one slice per panel as a line
============================================================

``plotpress.load_data()`` reads the plotted data straight back out of a
saved interactive HTML file -- the original Python objects that built it
don't need to still be around. That matters whenever the figure and the
code behind it have drifted apart: a report generated earlier, handed off
by someone else, or produced by a pipeline that never kept the arrays
after writing the file.

The source figure below -- a 30-panel grid of independent sensor sweeps,
each its own ``pcolormesh`` -- is built and saved here only to have a
self-contained interactive file to load back from; in practice this file
could equally well already exist from an earlier run, with none of this
module in scope. ``load_data()`` keys each panel by its own title by
default -- so ``"panel 5"`` reads back as ``"panel 5"``, not a bare index
that has to line up with however the grid was built -- and returns each
panel's mesh as a 2-D ``z`` array plus its own 1-D ``x``/``y`` cell-center
coordinates, so slicing a fixed row out of ``z`` and pairing it with ``x``
is exactly the ``(x, y)`` pair ``ax.plot()`` expects -- no re-deriving the
grid from the mesh's edges or extent by hand.
"""
import os
import tempfile

import numpy as np
import plotpress


def _build_source_html():
    """A 30-panel pcolormesh grid, saved as interactive HTML -- standing in
    for a figure produced (and saved) by an earlier, separate run."""
    fig, axes = plotpress.subplots(5, 6, figsize=(16, 9))
    x = np.linspace(0, 10, 21)
    y = np.linspace(0, 5, 11)
    X, Y = np.meshgrid(x, y)
    for i, ax in enumerate(np.asarray(axes).ravel()):
        # A travelling-wave-like field, phase-offset per panel so each
        # panel's x-slice below comes out meaningfully different.
        Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
        ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
        ax.set_title(f"panel {i}", fontsize=7)
        ax.tick_params(labelsize=5)
    fig.tight_layout()
    path = os.path.join(tempfile.gettempdir(), "plotpress_gallery_mesh_grid.html")
    fig.save(path, interactive=True)
    return path


source_path = _build_source_html()
data = plotpress.load_data(source_path)
# A bare (non-Report) figure has no report-level title of its own, so it
# falls back to the same "Figure N" label a Report page would show it under.
axes_data = data["Figure 1"]["axes"]    # keyed by each panel's own title

# ---------------------------------------------------------------------------
# Slice every panel's mesh along x at the same fixed row -- one 1-D line per
# panel, in the same 5x6 layout the source figure used.
# ---------------------------------------------------------------------------
ROW = 5   # a fixed y index, the same across every panel

fig, axes = plotpress.subplots(5, 6, figsize=(16, 9))
for i, ax in enumerate(np.asarray(axes).ravel()):
    mesh = axes_data[f"panel {i}"]["meshes"][0]
    ax.plot(mesh["x"], mesh["z"][ROW, :], color="C0")
    ax.set_title(f"panel {i}", fontsize=7)
    ax.tick_params(labelsize=5)
fig.tight_layout()
