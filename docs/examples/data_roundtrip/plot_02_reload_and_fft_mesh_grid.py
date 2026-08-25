"""
Reload a mesh grid and FFT every panel
=======================================

A second reload scenario, this time transforming rather than slicing:
:doc:`plot_01_reload_mesh_grid_as_lines` pulls one row out of each panel's
mesh, but the full 2-D grid ``load_data()`` hands back supports any NumPy
operation -- here, a 2-D FFT run over every panel at once, replotted as a
new mesh in the same grid layout.

As in that example, the source figure is built and saved here only to have
a self-contained file to load back from -- ``load_data()`` doesn't care
whether the file it's reading was written a moment ago or came from an
entirely separate run.
"""
import os
import tempfile

import numpy as np
import plotpress


def _build_source_html():
    """The same 30-panel pcolormesh grid as plot_01, saved as interactive
    HTML -- standing in for a figure produced by an earlier, separate run."""
    fig, axes = plotpress.subplots(5, 6, figsize=(16, 9))
    x = np.linspace(0, 10, 21)
    y = np.linspace(0, 5, 11)
    X, Y = np.meshgrid(x, y)
    for i, ax in enumerate(np.asarray(axes).ravel()):
        Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
        ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
        ax.set_title(f"panel {i}", fontsize=7)
        ax.tick_params(labelsize=5)
    fig.tight_layout()
    path = os.path.join(tempfile.gettempdir(), "plotpress_gallery_mesh_grid.html")
    fig.save(path, interactive=True)
    return path


source_path = _build_source_html()
figures = plotpress.load_data(source_path)
axes_data = figures[0]["axes"]

# ---------------------------------------------------------------------------
# 2-D FFT every panel's mesh, replotting the (log-scaled, zero-frequency
# centered) magnitude spectrum as a new mesh in the same 5x6 layout.
# ---------------------------------------------------------------------------
fig, axes = plotpress.subplots(5, 6, figsize=(16, 9))
for i, ax in enumerate(np.asarray(axes).ravel()):
    mesh = axes_data[i]["meshes"][0]
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(mesh["z"])))
    ax.pcolormesh(np.log1p(spectrum), cmap="magma")
    ax.set_title(f"panel {i}", fontsize=7)
    ax.tick_params(labelsize=5)
fig.tight_layout()
