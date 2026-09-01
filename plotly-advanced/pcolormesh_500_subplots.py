"""500 heatmap subplots with a shared colorbar, in Plotly -- built to mirror
plotpress's own docs/scale/plot_01_many_axes.py as closely as possible (same
20x25 grid, same 40x40-cell fields, same shared vmin/vmax, same per-panel
title, timed the same way), so the two are a fair side-by-side comparison,
not two different tasks.

On top of Plotly's own built-in pan/zoom/hover, this adds custom JS to
prototype the two plotpress interactivity features most likely to reveal
real difficulty if attempted on Plotly: point-pick-with-snap (click a
cell -> pin an annotation reading its exact x/y/z, on whichever one of the
500 subplots it belongs to -- Plotly's click event already resolves the
nearest data point and which subplot's axes it's on, so this needs far
less hand-built hit-testing than plotpress's own SVG-based version did)
and a live Extract panel (the pinned points, as JSON, updated on every
pin/unpin).

Usage:
    python pcolormesh_500_subplots.py
writes pcolormesh_500_subplots.html next to this script and prints the
build time and file size.
"""
import json
import time
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

NROWS, NCOLS = 20, 25          # 500 plots, same grid plotpress's example uses
NY = NX = 40                   # 40x40 mesh per plot

# Same field-generation recipe as plotpress's plot_01_many_axes.py, same seed,
# so the two examples are actually showing the same data, not just the same
# shape of data.
g = np.linspace(-3, 3, NX)
X, Y = np.meshgrid(g, g)
rng = np.random.default_rng(0)

fields, centers = [], []
for _ in range(NROWS * NCOLS):
    cx, cy = rng.uniform(-2.0, 2.0, size=2)
    freq = rng.uniform(0.6, 2.2)
    Z = (np.exp(-((X - cx) ** 2 + (Y - cy) ** 2))
         + 0.6 * np.sin(freq * X) * np.cos(freq * Y))
    fields.append(Z)
    centers.append((cx, cy))
zmin = min(Z.min() for Z in fields)
zmax = max(Z.max() for Z in fields)

t0 = time.perf_counter()

fig = make_subplots(
    rows=NROWS, cols=NCOLS,
    subplot_titles=[f"({cx:.1f}, {cy:.1f})" for cx, cy in centers],
    horizontal_spacing=0.002, vertical_spacing=0.003,
)

for i, (Z, (cx, cy)) in enumerate(zip(fields, centers)):
    r, c = divmod(i, NCOLS)
    fig.add_trace(
        go.Heatmap(
            z=Z, x=g, y=g,
            coloraxis="coloraxis",   # one shared colorbar for all 500 traces
            hovertemplate="x=%{x:.2f}<br>y=%{y:.2f}<br>z=%{z:.3f}<extra></extra>",
        ),
        row=r + 1, col=c + 1,
    )

fig.update_layout(
    coloraxis={"colorscale": "Viridis", "cmin": zmin, "cmax": zmax,
              "colorbar": {"thickness": 14, "len": 0.9}},
    height=NROWS * 90, width=NCOLS * 90 + 120,
    showlegend=False,
    title=None,   # set below, once we know the build time
)
# Every subplot's own tick labels, off by default at this panel count (500
# axis label sets would be unreadable clutter) -- plotpress's example gives
# each of the 500 panels its own labeled x/y ticks, so this is a real,
# visible difference between the two outputs worth being upfront about
# rather than quietly making Plotly's version lighter-weight than the
# comparison it's supposed to be.
fig.update_xaxes(showticklabels=False)
fig.update_yaxes(showticklabels=False)
for ann in fig.layout.annotations:
    ann.font = {"size": 8}

build_s = time.perf_counter() - t0
fig.update_layout(
    title=f"500 heatmap subplots (40x40) + shared colorbar -- "
          f"built in {build_s * 1e3:.0f} ms (Plotly figure construction only, "
          f"not HTML write)")

out_dir = Path(__file__).parent
out_path = out_dir / "pcolormesh_500_subplots.html"

t1 = time.perf_counter()
plot_html = fig.to_html(
    full_html=False, include_plotlyjs=True, div_id="plotgraph",
    config={"displaylogo": False},
)
write_s = time.perf_counter() - t1

# The custom interactivity layer: point-pick-with-snap (a click on any cell
# pins a Plotly annotation on that exact subplot, reading its x/y/z) and a
# live Extract panel listing every pinned point as JSON. Plotly's own click
# event already resolves the nearest point *and* which subplot's x/y axes
# it belongs to (points[0].xaxis/yaxis, e.g. "x37"/"y37") -- that hit-testing
# is exactly the part plotpress's own SVG-based point-pick had to hand-build
# (see plotpress/_interactive.py's nearestVertex()); here it's free.
CUSTOM_JS = r"""
<div id="pp-toolbar" style="position:fixed;top:8px;right:8px;z-index:1000;
    background:#fff;border:1px solid #b8b8b8;border-radius:6px;padding:8px 12px;
    font:12px system-ui,sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.2)">
  <button id="pp-clear" style="padding:3px 8px;border:1px solid #b8b8b8;
      border-radius:4px;background:#fff;cursor:pointer">Clear pins</button>
  <button id="pp-extract" style="padding:3px 8px;border:1px solid #b8b8b8;
      border-radius:4px;background:#fff;cursor:pointer;margin-left:6px">Extract</button>
  <div id="pp-count" style="margin-top:6px;color:#555">0 points pinned</div>
</div>
<div id="pp-extract-panel" style="display:none;position:fixed;top:56px;right:8px;
    width:340px;max-height:70vh;overflow:auto;background:#fff;border:1px solid #b8b8b8;
    border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);padding:10px;z-index:1001;
    font:11px ui-monospace,monospace;white-space:pre-wrap">
</div>
<script>
(function () {
  var gd = document.getElementById('plotgraph');
  var pins = [];   // {x, y, z, xaxis, yaxis}

  function redraw() {
    var annotations = pins.map(function (p, i) {
      return {
        x: p.x, y: p.y, xref: p.xaxis, yref: p.yaxis,
        text: 'x=' + p.x.toFixed(2) + '<br>y=' + p.y.toFixed(2) +
              '<br>z=' + p.z.toFixed(3),
        showarrow: true, arrowhead: 2, ax: 20, ay: -20,
        bgcolor: '#fff3cd', bordercolor: '#856404', font: {size: 9},
        captureevents: true,   // lets a click on the annotation itself remove it
        // stash the pin index so plotly_clickannotation can find it again
        _pinIndex: i,
      };
    });
    Plotly.relayout(gd, {annotations: annotations});
    document.getElementById('pp-count').textContent = pins.length + ' point' +
      (pins.length === 1 ? '' : 's') + ' pinned';
  }

  gd.on('plotly_click', function (evt) {
    var p = evt.points[0];
    if (!p) return;
    // points[0].xaxis/yaxis are the actual axis *objects* Plotly resolved
    // for this subplot; .._id is the "x37"/"y37"-style ref annotations need.
    pins.push({x: p.x, y: p.y, z: p.z, xaxis: p.xaxis._id, yaxis: p.yaxis._id});
    redraw();
  });

  gd.on('plotly_clickannotation', function (evt) {
    pins.splice(evt.index, 1);
    redraw();
  });

  document.getElementById('pp-clear').addEventListener('click', function () {
    pins = [];
    redraw();
  });

  document.getElementById('pp-extract').addEventListener('click', function () {
    var panel = document.getElementById('pp-extract-panel');
    panel.textContent = JSON.stringify(pins.map(function (p) {
      return {x: p.x, y: p.y, z: p.z};
    }), null, 1);
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  });
})();
</script>
"""

full_html = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<title>500 pcolormesh-equivalent subplots (Plotly)</title></head><body>"
    + plot_html + CUSTOM_JS + "</body></html>"
)
out_path.write_text(full_html, encoding="utf-8")
total_s = time.perf_counter() - t0

size_mb = out_path.stat().st_size / 1e6
print(f"figure build:  {build_s * 1e3:8.0f} ms")
print(f"HTML write:    {write_s * 1e3:8.0f} ms")
print(f"total:         {total_s * 1e3:8.0f} ms")
print(f"output file:   {out_path}")
print(f"file size:     {size_mb:.2f} MB")
