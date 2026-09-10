"""
Hidden per-panel labels survive the round trip (and the Extract)
==================================================================

A grid that names every panel's axes for later data extraction, but
draws only one shared :meth:`~plotpress.figure.Figure.supxlabel`/
:meth:`~plotpress.figure.Figure.supylabel` pair, using
``set_xlabel(..., visible=False)`` (see
:doc:`/auto_examples/axes_features/plot_25_hidden_axis_labels`).

The hidden labels aren't just cosmetic-free -- they're *recorded*.
``load_data()``'s ``"layout"`` carries each one (plus a ``visible: false``
flag), :func:`plotpress.subplots_from_layout` rebuilds every panel with
its label still attached and still hidden, and in the interactive HTML a
Point Picking **Extract** pulls each picked value out with its panel's
``xlabel``/``ylabel`` *and* the figure's ``supxlabel``/``supylabel``/
``suptitle`` alongside -- so a value lifted out of a CSV still says what
it means.

This renders the source figure and the one rebuilt from its own saved
HTML -- every panel's label recovered, still hidden, drawn nowhere.
"""
import os
import tempfile

import numpy as np
import plotpress

CHANNELS = ["Fz", "Cz", "Pz", "Oz"]

fig, axes = plotpress.subplots(2, 2, figsize=(9, 6))
rng = np.random.default_rng(5)
t = np.linspace(0, 1, 256)
for ax, name in zip(axes.ravel(), CHANNELS):
    ax.plot(t, np.sin(2 * np.pi * 6 * t) + 0.2 * rng.standard_normal(t.size))
    ax.set_title(name)
    # Named for export, hidden on the canvas.
    ax.set_xlabel("time (s)", visible=False)
    ax.set_ylabel("potential (uV)", visible=False)

fig.supxlabel("time (s)")
fig.supylabel("potential (uV)")
fig.suptitle("EEG montage: shared labels drawn, per-channel labels hidden")
fig.tight_layout()

path = os.path.join(tempfile.gettempdir(), "plotpress_hidden_labels_roundtrip.html")
fig.save(path, interactive=True)

# ---------------------------------------------------------------------------
# Load it back. subplots_from_layout() has already re-attached every hidden
# label by the time this loop starts -- nothing below re-types one.
# ---------------------------------------------------------------------------
entry = plotpress.load_data(path)["Figure 1"]
layout, axes_data = entry["layout"], entry["axes"]

rebuilt_fig, rebuilt_axes = plotpress.subplots_from_layout(layout)
for ax, name in zip(np.asarray(rebuilt_axes).ravel(), CHANNELS):
    s = axes_data[name]["series"][0]
    ax.plot(s["x"], s["y"])
rebuilt_fig.tight_layout()

# Every rebuilt panel carries its hidden label back -- stored, flagged
# hidden, and (as the SVG check confirms) still drawn nowhere.
one = rebuilt_fig.get_ax(row=1, col=0)
print("rebuilt panel label:", repr(one.get_xlabel()),
      "visible:", one.get_xlabel_visible())
print("layout recorded visibility:", layout["axes"][2].get("xlabel_visible"))

for name in CHANNELS:
    ax = rebuilt_fig.get_ax(title=name)
    assert ax.get_xlabel() == "time (s)" and not ax.get_xlabel_visible()
    assert ax.get_ylabel() == "potential (uV)" and not ax.get_ylabel_visible()
svg = rebuilt_fig.to_svg()
assert "potential (uV)" in svg          # once, as the shared supylabel
assert svg.count("time (s)") == 1       # once, as the shared supxlabel
