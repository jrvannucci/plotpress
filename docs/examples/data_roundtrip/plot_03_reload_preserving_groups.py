"""
Reload a grouped dashboard, preserving its group boxes
========================================================

A figure's :meth:`plotpress.Figure.group` boxes are layout, not data --
``load_data()`` alone never returns them, since its per-axes dicts only
carry what got plotted, not how the grid around it was organized. That
information lives in the ``"layout"`` entry :func:`plotpress.load_data`
also returns, next to ``"axes"``: :func:`plotpress.subplots_from_layout`
reads it back and re-creates the exact same grid *and* the same
:meth:`~plotpress.Figure.group` boxes, so a rebuilt dashboard groups its
panels the same way the source did without a single ``fig.group()`` call
written by hand on the reload side -- each panel's own title comes back
the same way, with no ``set_title()`` needed either.
"""
import os
import tempfile

import numpy as np
import plotpress


def _build_source_html():
    """A 2x4 sensor dashboard -- the left two columns are one alert
    cluster, the right two are a second -- saved as interactive HTML,
    standing in for a dashboard produced by an earlier, separate run."""
    fig, axes = plotpress.subplots(2, 4, figsize=(14, 6))
    t = np.linspace(0, 4 * np.pi, 200)
    for i, ax in enumerate(np.asarray(axes).ravel()):
        ax.plot(t, np.sin(t + i) * (1 + 0.1 * i), color="C0")
        ax.set_title(f"sensor {i}", fontsize=9)
    fig.group("Bay A", [axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]],
             color="#b8003a", pad=(6, 10, 14, 6))
    fig.group("Bay B", [axes[0, 2], axes[0, 3], axes[1, 2], axes[1, 3]],
             color="#1f6fa8", pad=(10, 6, 14, 6))
    fig.tight_layout()
    path = os.path.join(tempfile.gettempdir(), "plotpress_gallery_grouped_dashboard.html")
    fig.save(path, interactive=True)
    return path


source_path = _build_source_html()
data = plotpress.load_data(source_path)
# A bare (non-Report) figure has no report-level title of its own, so it
# falls back to the same "Figure N" label a Report page would show it under.
fig_entry = data["Figure 1"]
axes_data = fig_entry["axes"]    # keyed by each panel's own title

# ---------------------------------------------------------------------------
# Rebuild the same 2x4 grid AND both group boxes from the source figure's
# recorded layout, then replot each sensor's recovered trace, offset and
# recolored -- the grouping itself needs no re-declaring.
# ---------------------------------------------------------------------------
fig, axes = plotpress.subplots_from_layout(fig_entry["layout"])
for i, ax in enumerate(np.asarray(axes).ravel()):
    s = axes_data[f"sensor {i}"]["series"][0]
    ax.plot(s["x"], s["y"] + 2.0, color="C3")
fig.tight_layout()
