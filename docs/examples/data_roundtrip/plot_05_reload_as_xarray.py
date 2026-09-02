"""
Reload a mesh grid as one labeled xarray.Dataset
==================================================

``load_data()``'s title-keyed dict of dicts is the wrong tool for a
uniform grid of same-shaped scientific measurements -- the exact case the
other reload examples in this gallery already work with (a 30-panel
``pcolormesh`` grid). Pulling a value out at "row 2, column 3" means
already knowing that panel's title, and stacking every panel into one
array for a bulk NumPy operation means looping over the dict by hand.

``plotpress.load_data_xarray()`` (the ``xarray`` extra: ``pip install
plotpress[xarray]``) reads the same saved file back as a single
``xarray.Dataset`` instead, dimensioned by the figure's own ``row``/``col``
grid -- every panel's ``z`` grid stacked into one ``(row, col, y, x)``
array, with each panel's own title/labels riding along as ``(row, col)``
coordinates. No panel-by-panel loop, and no risk of two panels sharing a
title silently colliding the way a plain dict key could (xarray indexes
by row/column position, never by name).
"""
import os
import tempfile

import numpy as np
import plotpress

fig, axes = plotpress.subplots(5, 6, figsize=(16, 9))
x = np.linspace(0, 10, 21)
y = np.linspace(0, 5, 11)
X, Y = np.meshgrid(x, y)
for i, ax in enumerate(np.asarray(axes).ravel()):
    # A travelling-wave-like field, phase-offset per panel.
    Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
    ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
    ax.set_title(f"panel {i}", fontsize=7)
    ax.tick_params(labelsize=5)
fig.tight_layout()
path = os.path.join(tempfile.gettempdir(), "plotpress_gallery_xarray_reload.html")
fig.save(path, interactive=True)

# ---------------------------------------------------------------------------
# The whole 5x6 grid comes back as one Dataset -- ds["z"] is already a
# (row, col, y, x) array, ready for a bulk xarray/NumPy reduction across
# every panel at once, not a 30-iteration Python loop.
# ---------------------------------------------------------------------------
ds = plotpress.load_data_xarray(path)
print(ds)

# The mean field across every panel, as one (y, x) array computed in a
# single call -- the kind of operation a title-keyed dict of dicts has no
# native way to express at all.
mean_field = ds["z"].mean(dim=("row", "col"))

fig2, ax2 = plotpress.subplots(figsize=(6, 4))
ax2.pcolormesh(ds["x"].values, ds["y"].values, mean_field.values, cmap="viridis")
ax2.set_title("Mean field across all 30 panels")
fig2.tight_layout()
