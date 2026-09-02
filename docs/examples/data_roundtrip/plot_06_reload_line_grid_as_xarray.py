"""
Reload a grid of line traces as one labeled xarray.Dataset, analyze, and replot
====================================================================================

``plotpress.load_data_xarray()`` isn't limited to mesh grids -- a uniform
grid where every panel holds exactly one line series (the other half of
its supported scope; see the mesh version of this example,
:doc:`plot_05_reload_as_xarray`) comes back the same way, dimensioned by
the figure's own ``row``/``col`` grid, with every panel's ``y`` trace
stacked into one ``(row, col, point)`` array instead of a title-keyed dict
one panel at a time.

The source figure below is a 3x4 grid of independent sensor traces, each
its own damped oscillation at a different frequency -- standing in for a
bank of channel recordings saved earlier, with none of the code that built
them still around. This example loads it back, mean-centers every
channel's trace in one broadcast subtraction, and replots the *whole*
grid of centered traces, titled straight from what ``load_data_xarray()``
recovered.
"""
import os
import tempfile

import numpy as np
import plotpress

fig, axes = plotpress.subplots(3, 4, figsize=(14, 7))
t = np.linspace(0, 4, 400)
grid = np.asarray(axes)
for i, ax in enumerate(grid.ravel()):
    freq = 1.0 + 0.4 * i
    # A nonzero baseline (+0.2), so the mean-centering analysis below has
    # something real to remove from each channel.
    y = np.exp(-0.6 * t) * np.sin(2 * np.pi * freq * t) + 0.2
    ax.plot(t, y, color="C0")
    ax.set_title(f"channel {i}", fontsize=9)
    ax.tick_params(labelsize=6)
fig.tight_layout()
path = os.path.join(tempfile.gettempdir(), "plotpress_gallery_line_grid_xarray.html")
fig.save(path, interactive=True)

# ---------------------------------------------------------------------------
# Load: every channel's trace comes back as one (row, col, point) array --
# ds["y"] -- sharing the single "point" coordinate every panel plotted
# against, since they all used the same `t`.
# ---------------------------------------------------------------------------
ds = plotpress.load_data_xarray(path)
print(ds)

# Analyze: mean-center every channel's own trace in one broadcast
# subtraction across the whole grid -- the kind of per-panel operation a
# title-keyed dict of dicts has no native way to express at all.
# `centered` keeps the full (row, col, point) shape, so it can be
# replotted channel-for-channel below.
centered = ds["y"] - ds["y"].mean(dim="point")

# Replot: rebuild the same 3x4 grid and draw each channel's centered trace
# straight from the xarray Dataset -- ds["title"] hands each channel's own
# title back, with nothing re-typed on this side.
nrows, ncols = ds.sizes["row"], ds.sizes["col"]
fig2, axes2 = plotpress.subplots(nrows, ncols, figsize=(14, 7))
for r in range(nrows):
    for c in range(ncols):
        ax = axes2[r, c]
        ax.plot(ds["point"].values, centered.values[r, c], color="C3")
        ax.set_title(str(ds["title"].values[r, c]), fontsize=9)
        ax.tick_params(labelsize=6)
fig2.suptitle("Every channel's trace, mean-centered")
fig2.tight_layout()
