# Plotly interactivity prototype: point-pick, vs. plotpress

A feasibility test, not a package: can Plotly's own click/annotation API be
used to build the interactive features plotpress hand-rolled in
`plotpress/_interactive.py` (point-pick-with-snap, a pinned value readout, a
live extract panel), and how does Plotly hold up at the specific scale
plotpress's own `docs/scale/plot_01_many_axes.py` example targets -- 500
independent small heatmaps on one figure, sharing one colorbar?

`pcolormesh_500_subplots.py` builds the *same* dataset (same seed, same
20x25 grid of 40x40 fields, same shared color range) via
`plotly.subplots.make_subplots` + `go.Heatmap`, and writes a fully offline,
self-contained HTML file (`include_plotlyjs=True` -- no CDN, no external
requests) with custom JS added on top for point-pick.

## Results (this machine, one run each -- not a benchmark suite)

| | plotpress | Plotly |
|---|---|---|
| Figure build | 175 ms | 4,110 ms |
| HTML write | 884 ms | 1,299 ms |
| **Total** | **1,059 ms** | **5,477 ms** |
| Output file size | 7.66 MB | 15.91 MB |

Plotly's version has **all 500 subplots' own tick labels turned off**
(`update_xaxes(showticklabels=False)`) because at this panel count they were
illegible clutter and slowed rendering further -- plotpress's comparison
figure keeps full per-panel x/y tick labels. The gap above understates
Plotly's real cost for an apples-to-apples "every panel fully labeled" figure.

**Why the gap:** plotpress rasterizes each 40x40 mesh to one small embedded
PNG (a lossless copy of a uniform grid — see `plotpress/artists.py`'s
`_VECTOR_CELL_LIMIT` machinery). Plotly's `Heatmap` embeds the raw
800,000-cell `z` array as JSON text in the page and re-renders it via SVG at
load time — that scales with cell count in a way plotpress's raster path
doesn't.

## Point-pick: works, and is genuinely easier than plotpress's own version

Clicking any cell across all 500 subplots correctly pins an annotation
reading the exact value, on the *correct* subplot's own axes
(`points[0].xaxis`/`yaxis` resolve to e.g. `"x29"`/`"y29"` automatically).
Verified live: click at an arbitrary point → pinned annotation read back as
`x=-0.85, y=-2.23, z=0.443`, matching the clicked cell.

This is the one place Plotly is a clear *win* over plotpress's approach:
plotpress's point-pick had to hand-build nearest-vertex hit-testing
(`plotpress/_interactive.py`'s `nearestVertex()`); Plotly's `plotly_click`
event resolves the nearest point *and* which subplot it belongs to for free.

The **Extract** panel (reads the pinned points back out as JSON) worked
correctly on the first attempt, built on the same pin-tracking array.

## Point-pick: what did *not* just work

Removing a single pin by clicking its own annotation
(`plotly_clickannotation`, with `captureevents: true` set on the
annotation) **never fired**, even clicking the annotation's own verified
on-screen bounding box directly. Root cause not chased down further within
this prototype's scope. A bulk **Clear pins** button (calling
`Plotly.relayout` with an empty `annotations` array) works reliably and was
used as the fallback.

Read as: not everything maps onto Plotly's API as cleanly as the plain
click-to-pin case did. A production version of this would need to actually
resolve that (or design around it — e.g. a small "x" button rendered next to
each pin instead of relying on `plotly_clickannotation`).

## Bottom line

For the *specific* "many small subplots" shape plotpress optimizes for,
Plotly is markedly heavier and slower at this run's scale (500 panels) —
worth checking whether that matters at whatever scale you actually need
before treating it as disqualifying; it may not matter at all for a
handful of panels or a single big one. For the *interactivity* question
that motivated this prototype, the picture is mixed in a genuinely useful
way: point-pick-with-snap needed dramatically less custom code than
plotpress's own version and worked immediately; the "manage individual
pins" half needs more investment than expected. Neither library gets you a
finished, tested feature for free — but Plotly's starting point for this
specific feature was measurably further along.
