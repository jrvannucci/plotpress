# plotpress

A **lightweight, dependency-light** plotting library that renders **SVG and
self-contained interactive HTML** through a **matplotlib-shaped** API — with
**no global state** and **no compiled extension**, so it installs everywhere
`pip` runs.

```python
import plotpress
import numpy as np

fig, ax = plotpress.subplots()
x = np.linspace(0, 4 * np.pi, 400)
ax.plot(x, np.sin(x), label="sin")
ax.plot(x, np.cos(x), label="cos", linestyle="--")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.legend()

fig.save("out.svg")                       # static vector SVG
fig.save("out.png"); fig.save("out.pdf")  # raster + vector export
fig.save("out.html", interactive=True)    # interactive toolbar: zoom / pick / annotate
fig.show()                                # native pop-up window
```

`out.html` above is a real, self-contained page — no server, no external JS —
with a toolbar over every axes in the figure at once. PyPI/GitHub READMEs
can't run the page's own script, so the three GIFs below stand in for it;
open one yourself (or click through to the
[real-applications gallery](https://jrvannucci.github.io/plotpress/auto_applications/index.html),
embedded exactly this way) and it's fully live.

**Pan / zoom**, working the same over every axes, not just the one under the cursor:

![Wheel-zoom toward the cursor on one panel, then panning across to the next](https://raw.githubusercontent.com/jrvannucci/plotpress/main/assets/readme_zoom_pan.gif)

**Point picking**, reading a value off any axes — a mesh's `z`, not just a
line's `x`/`y` — then extracting every picked point as CSV/JSON:

![Picking a point on a line panel and a mesh panel, then extracting both as CSV](https://raw.githubusercontent.com/jrvannucci/plotpress/main/assets/readme_point_picking.gif)

**Annotation**, a free-form note whose label box drags independently of the
point it's pinned to:

![Dropping an annotation on a bar chart and dragging its label away from the point it's pinned to](https://raw.githubusercontent.com/jrvannucci/plotpress/main/assets/readme_annotation.gif)

## One figure, several outputs

The same `Figure` built once from the matplotlib-shaped API renders to every
format below — no separate figure per output, no plugin to install:

```
                                    one Figure object
                                            │
    ┌───────────────┬───────────────┬───────┴───────┬───────────────┬───────────────┐
    ▼               ▼               ▼               ▼               ▼               ▼
  .svg            .png            .pdf            .html           Vega          Vega-Lite
(vector,        (raster,        (vector,        (SVG + JS       (v5 JSON,      (v5 JSON, a
the core         Pillow)        svglib +       inlined --      real pixel-   stricter, more
 format)                       reportlab)       no server     space marks)     declarative
                                               round trip)                      grammar)
```

`fig.save(path, ...)` dispatches on the file extension for the first four;
`fig.to_vega()` / `fig.to_vega_lite()` return a JSON specification as a plain
`dict` for a separate Vega/Vega-Lite runtime to render, rather than a
rendered artifact — useful for handing a figure to an existing Vega-based
dashboard or notebook instead of embedding plotpress's own SVG/JS. See the
[architecture docs](https://jrvannucci.github.io/plotpress/user_guide/architecture.html)
for exactly how much of the rendering pipeline each of these six actually
shares, and where a format gets its own dedicated path instead.

## Reading a figure back out of HTML

The interactive HTML above isn't a one-way trip: it embeds the plotted data
and the figure's own layout as JSON alongside the SVG, so a later process —
with none of the Python objects that built it still around — can read a
figure back out and rebuild it:

```
a saved .html (Figure.save(path, interactive=True))
      embeds <script id="plotpress-pick"> and
         id="plotpress-layout"> per figure
                         │
                         ▼
             plotpress.load_data(path)
         parses that embedded JSON back out
                          │
           ┌──────────────┴──────────────┐
           ▼                             ▼
       "layout"                       "axes"
   (grid shape, each            (recovered series/
axes' own decorations,        mesh/pie data per axes,
  groups, sup-title)              keyed by title)

           │
           ▼
       plotpress.subplots_from_layout(layout)
       rebuilds the grid and every axes' own
     decorations -- not the plotted data itself
                         │
                         ▼
     a new, already-labeled Figure -- ready for
     the caller to replot the recovered "axes"
                   data back into
```

A freeform `Figure.add_axes()` rect, an inset, or a colorbar axes has no grid
cell to rebuild from — its index is listed in `layout["omitted_axes"]`
instead of silently vanishing. See the
[full API and worked examples](https://jrvannucci.github.io/plotpress/usage.html#reading-html-data)
for the round trip end to end.

For the common case of a *uniform* grid — every axes its own single
`pcolormesh` or line series, all the same shape — `plotpress.load_data_xarray()`
skips the title-keyed dict above entirely and reads the same file straight
into one `xarray.Dataset` indexed by row/column instead, with the recovered
layout still available under `ds.attrs["layout"]` for
`plotpress.subplots_from_layout()`. See the
[data round-trip example](https://jrvannucci.github.io/plotpress/auto_examples/data_roundtrip/index.html)
for both paths worked through end to end.

## What it is for

plotpress is **not a matplotlib replacement**, and it does not try to match
matplotlib's twenty years of breadth (no geographic projections or triangulated
grids, one font-metric family, no 3-D, and its polar axes project onto the 2-D
core rather than a dedicated pipeline — see [Supported plot types](#supported-plot-types)
below). It aims at a narrower, underserved spot: plotting where matplotlib's
install footprint or global state gets in the way.

**Reach for plotpress when you want to:**

- **Ship plots from a constrained runtime** — locked-down servers, minimal
  containers, Pyodide/WASM, or CI — where a pure-Python + NumPy install with no
  build toolchain and no per-platform wheels matters.
- **Embed in web apps or notebooks** as SVG or self-contained interactive HTML
  whose JS makes no external requests (works under strict CSPs like Jupyter).
- **Write library or server code** that should never touch a global "current
  figure" or a process-wide `rcParams`.

**Reach for matplotlib** (or seaborn, Plotly) when you need publication-grade
typography across arbitrary fonts, the full plot-type gallery, 3-D, or the
deep ecosystem that pandas, seaborn and scikit-learn plot into.

Two galleries in the docs, on separate pages: a
[plot-type reference](https://jrvannucci.github.io/plotpress/auto_examples/index.html)
with one figure per method, and
[real applications](https://jrvannucci.github.io/plotpress/auto_applications/index.html)
— a hundred-odd worked figures built from the data real measurements produce,
grouped by field, each explaining the axis, scale and colour choices the data
forces. Every application figure is embedded live, with the interactive toolbar.

## What makes it different

1. **No `pyplot`, no globals.** There is no "current figure/axes" and no global
   `rcParams`. A `Figure` owns its axes and its own `Style`; two figures never
   share mutable state. `plotpress.subplots()` returns `(fig, axes)` just like
   `plt.subplots()` — but touches no global state.
2. **matplotlib-*shaped* API** so moving code either direction is mostly
   mechanical: `Figure`/`Axes`, `plot`, `scatter`, `pcolormesh`,
   `set_xlabel/ylabel/title`, `set_xlim/ylim`, `grid`, `legend`, `colorbar`. It
   is shaped, not drop-in — there's no `pyplot` state machine and not every
   matplotlib keyword is present; treat the gallery as the compatibility surface.
3. **SVG-first + built for speed.** Output is vector SVG; only mesh/image layers
   are rasterized (as a single embedded `<image>`, not thousands of rects). Each
   series is one `<path>`. It's **pure Python + NumPy** — vectorized coordinate
   formatting, min/max-decimated huge lines — with **no compiled extension**, so
   it installs everywhere pip does.

## Install

```bash
pip install plotpress            # SVG + interactive HTML + PNG/PDF export
pip install plotpress[gui]       # + native pop-up window (fig.show(), pywebview)
pip install plotpress[qt]        # + embed in a PyQt/PySide app (fig.show_qt())
pip install plotpress[dev]       # + pytest (contributors)
pip install plotpress[bench]     # + matplotlib (benchmark comparison)
```

The standard install covers **all file output** -- SVG, interactive HTML, PNG and
vector PDF -- with pure-wheel dependencies that install everywhere (servers, CI,
notebooks). Only the native ``fig.show()`` window needs the ``[gui]`` extra,
since it pulls a desktop webview stack; without it, ``fig.show()`` falls back to
the browser.

## Output surfaces (one scene, many targets)

| Call | Result |
|------|--------|
| `fig.save("x.svg")` | static vector SVG |
| `fig.save("x.png")` / `fig.savefig(...)` | raster PNG (supersampled Pillow backend) |
| `fig.save("x.pdf")` | vector PDF (svglib + reportlab) |
| `fig.save("x.html", interactive=True)` | interactive HTML (self-contained JS toolbar) |
| `fig.to_svg()` / `fig.to_html()` | string, for embedding |
| `fig._repr_svg_()` | inline SVG in Jupyter |
| `fig.show()` | native pop-up window (pywebview, `[gui]` extra; falls back to browser) |
| `fig.show_qt()` | embed in a PyQt/PySide app (`plotpress.qt`, `[qt]` extra) |

## Interactive figures

Interactive HTML and pop-up output carry a self-contained vanilla-JS toolbar (no
external requests, so it works under strict CSPs like Jupyter and sandboxed
webviews). Nothing is active until you pick a tool:

Pan/Zoom and Home sit standalone on the toolbar's left; everything else is
grouped into Axes, Point Picking, Annotate, and File menus:

- **Pan/Zoom** — plain-wheel whole-figure zoom/pan, for wherever
  holding Ctrl (Axis Zoom's whole-figure gesture, below) is awkward.
  **Home** restores its magnification back to natural size.
- **Axis Span** — drag to pan a single plot's data window (log-aware).
- **Axis Zoom** — rubber-band box to zoom *one* axes in **data space** (ticks
  recompute, markers keep a constant size); Ctrl+wheel (or a trackpad pinch)
  zooms the *whole figure* instead, centered on the cursor. **Reset All
  Axes** restores every axes' own pan/zoom back to its original view; neither
  Reset button clears pins/annotations — double-click a single plot under
  Axis Span/Zoom to reset just that one.
- **Point Picking** — click to pin the nearest data point's value; arrow keys
  step along the series (nearest-neighbour for scatter, cell-by-cell for
  meshes/contours), reporting extra dims (`z`, `c`, …). Click a pin, or use
  **Clear Points**, to remove it. Its label box (connected to the marker by a
  leader arrow) is draggable while Point Picking is active. **Hide
  Points** toggles every pin's visibility without deleting them, and
  **Extract** copies/downloads them all as CSV/JSON, or hands them back to
  the kernel (`fig.show(wait_for_extract=True)`).
- **Annotation** — drop a user-written note anywhere on the figure, not
  locked to any datum; **Clear Annotations** removes only these, leaving
  Point Picking pins untouched (Escape clears both kinds at once, and
  deselects the active tool). Its box drags the same way, while Annotation
  is active. **Hide Annotations** toggles every note's visibility (plus any
  boxed callout the figure itself drew) without deleting them.
- **Save**/**Save As** — persist pan/zoom, every pin/annotation, and every
  toggle above to a new (or the same) self-contained HTML file.

`fig.to_html()`/`fig.save(..., interactive=True)` accept `pick_precision`
(decimal places embedded per value) and `pick_max_mesh_cells`/
`pick_max_points` (a hard cap on how much of each mesh/series is embedded for
picking, per artist) to bound the interactive payload for mesh- or
point-heavy figures.

Per axes: `ax.set_pickable(False)` excludes that axes from Point Picking
(Axis Span/Zoom/Annotation still work everywhere), and
`ax.set_pick_context(**kwargs)` attaches extra key/value context — e.g. a
panel's spine color — that rides along on every record picked from it. Every
picked record also always carries `axes_title` (falling back to a generated
name when the axes has no title) plus `xlabel`/`ylabel` and `zlabel` (the
title of any colorbar attached to that axes, shared or not), so a value
pulled out of context still says what it means.

3-D data via `ax.plot_frames(...)` adds a **slider** (play/pause/step) over the
extra dimension; multiple sliders can be linked by a shared index.

## Supported plot types

plotpress covers the core of matplotlib's "Plot types" reference grid:

| | | |
|---|---|---|
| `plot` (lines) | `scatter` (+ `c`/`cmap`) | `bar` / `barh` |
| `hist` | `step` | `fill_between` |
| `stem` | `errorbar` (x/y err + caps) | `imshow` |
| `pcolormesh` | `pie` | `plot_frames` (slider) |
| `boxplot` | `violinplot` (KDE) | `eventplot` |
| `quiver` | `contour` (marching squares) | `hist2d` |
| `stackplot` | `contourf` (filled) | `hexbin` |
| `matshow` | `spy` | `broken_barh` |
| `stairs` | `axline` | |

**Signal processing** (pure-NumPy Welch estimators): `psd`, `csd`, `cohere`,
`magnitude_spectrum`, `angle_spectrum`, `phase_spectrum`, `specgram`, `xcorr`,
`acorr`.

**Polar** (`projection="polar"`): `plot`, `scatter`, `fill`, with
`set_rmax`/`set_rlim`/`set_rticks`/`set_thetagrids` and orientation control,
projected onto the 2-D core — see the
[limitations docs](https://jrvannucci.github.io/plotpress/user_guide/limitations.html)
for the caveats. No 3-D (see below).

Plus reference marks & fills — `axhline`/`axvline`, `axhspan`/`axvspan`,
`fill`/`fill_between`/`fill_betweenx`, `hlines`/`vlines` — and axis control:
**log scales** (`set_xscale`/`set_yscale`/`loglog`/`semilogx`),
**`set_aspect("equal")`**, `set_xlim/ylim`, `set_xticks/yticks`,
`set_xticklabels/yticklabels`, `invert_xaxis/yaxis`, `margins`, `grid`,
`set_axis_off`, **`subplots(sharex=…, sharey=…)`** (plus post-hoc
`sharex()`/`sharey()`), and **`twinx`/`twiny`** (overlaid axes with a second
y/x axis), `tick_params` (per-axes, per-x/y-axis tick styling), and
matplotlib `"C0"`..`"CN"` cycle colors. Plus **`fig.tight_layout()`**
(auto-margins so labels never overflow) and **`fig.subplots_adjust(...)`** /
**`GridSpec`** row/column spans for direct margin control, `ax.spines`
(per-side visible/color/linewidth), `secondary_xaxis`/`secondary_yaxis`
(a mirrored, unit-converted second axis) and `inset_axes` (a nested axes),
`align_xlabels`/`align_ylabels`, text (`ax.text`, `ax.annotate` with
arrows), figure-level `suptitle`/`supxlabel`/`supylabel`,
`fig.colorbar(...)` (single **or shared across a list of axes**),
`legend(loc=…, ncol=…, title=…)`, named colors (`"red"`, `"k"`, …), and
colormaps `viridis`, `plasma`, `inferno`, `magma`, `cividis`, `coolwarm`,
`RdBu`, `gray` (+ any `_r` reversed variant) with `Normalize`, `LogNorm`,
`PowerNorm`, or `SymLogNorm` scaling.

```bash
python examples/plot_types.py    # plot / scatter / bar / hist / pie / imshow / ...
python examples/plot_types_2.py  # boxplot / violin / quiver / contour / hist2d / ...
python examples/gallery.py       # line/scatter/pcolormesh/subplots
```

**Not yet implemented** (would need new primitives): `streamplot`/`barbs`,
triangulation (`tri*`), and geographic / map projections. These are the main
remaining plot-type gaps vs matplotlib's full gallery.

## Testing

```bash
pip install plotpress[dev]         # pytest
python -m pytest -m "not perf"  # fast unit + output tests (~2s)
python -m pytest -m perf -s     # timing tests + speedup report (needs matplotlib)
```

The suite covers the no-global-state invariants, plotting/autoscale logic,
transforms/tickers/colors, a lossless PNG round-trip, SVG/HTML well-formedness
and structure, and performance (regression guards + a comparative claim vs
matplotlib).

### Point-picking tests (opt-in)

Point picking runs in JavaScript inside the interactive HTML, so it is tested
end-to-end in a real browser: each case clicks the pixel where the renderer drew
a known datum and asserts the marker reports that datum, across every pickable
plot type (line, scatter, bar, stem, errorbar, quiver, eventplot, boxplot,
violin, fill, pcolormesh, imshow, pie) and awkward axes (log, inverted,
`set_aspect`, multi-subplot).

These need a browser, so they are deselected by default and skip cleanly when it
is missing:

```bash
pip install plotpress[browser] && playwright install chromium
python -m pytest -m browser
```

## Benchmarks

```bash
pip install plotpress[bench]        # matplotlib, for comparison
python benchmarks/benchmark.py  # plotpress vs matplotlib, plot build + SVG output
```

Representative run (best of 3, one machine — build **and** serialize to SVG,
both using the object-oriented API):

| scenario | plotpress | matplotlib | speedup |
|----------|------:|-----------:|--------:|
| pcolormesh 300×300 | ~16 ms | ~6400 ms | **~400×** |
| many axes (8×8 grid) | ~40 ms | ~1600 ms | **~40×** |
| scatter, 5k points | ~15 ms | ~220 ms | **~14×** |
| single line, 100k points | ~9 ms | ~48 ms | **~5.6×** |

**Honest caveat:** plotpress's win comes from avoiding matplotlib's per-`Artist`
Python overhead (many axes) and from rasterizing meshes to one `<image>` instead
of tens of thousands of vector cells (pcolormesh). The *single huge polyline*
case used to be a loss (pure-Python float→string serialization of 100k points);
it's now a win via **min/max path decimation** — a monotonic-x line is reduced
to first/last/min/max per pixel column before serializing, which is visually
lossless (spikes preserved), keeps the output **vector**, and needs no compiled
backend. Coordinate formatting itself is already vectorized with `numpy.char`.

## Roadmap

**Done:** pure-Python core with a self-contained object model; static SVG,
interactive HTML, and native-window output; PNG + vector-PDF export; the full
"Plot types" grid above; log scales and equal aspect; `tight_layout`; text /
annotations and figure-level titles; per-axes **data** zoom / pan / box-zoom with
live ticks, point-picking + extraction, in-browser annotation, and sliders for
3-D data.

**Pure Python, and staying that way.** plotpress is deliberately pure Python +
NumPy with no compiled extension — it installs everywhere pip does, no build
toolchain, no per-platform wheels. Speed comes from NumPy, not native code:
coordinate formatting is vectorized, huge lines are min/max-decimated (the
100k-point line runs ~5.6× vs matplotlib), and curvilinear / Gouraud meshes
scan-convert in NumPy. The "installs everywhere" promise is a first-class
feature, not a trade-off.

**Next:**
- Finish unifying the SVG and raster renderers behind the shared primitive
  layer (pure Python) so features aren't implemented twice.
- More plot types: `streamplot`/`barbs` and triangulation (`tri*`).
- Deeper polar (polar bars, cross-collection depth sorting).
- Hover tooltips; decimation for huge scatter collections.

## Architecture notes

`plotpress/` layout:

| Module | Responsibility |
|--------|----------------|
| `figure.py` | `Figure`, `subplots()`, layout, save/show/`_repr_*` |
| `axes.py` | `Axes`: plotting methods, limits, autoscale |
| `polar.py` | `PolarAxes`: (θ, r) projection + polar frame, built from existing artists |
| `_spectral.py` | pure-NumPy Welch spectral estimators (psd/csd/cohere/specgram/…) |
| `artists.py` | data-only scene primitives (`Line2D`, `ScatterCollection`, `QuadMesh`) |
| `style.py` | per-figure `Style` (replaces global `rcParams`) |
| `transform.py` | vectorized data→pixel transforms (linear + log scales) |
| `colors.py` | `Normalize`, colormap LUTs, colormap application |
| `ticker.py` | "nice number" + log tick locations, label formatting |
| `svg.py` | the renderer: scene → SVG string (+ per-axes metadata) |
| `primitives.py` | backend-agnostic pixel-space primitives + one artist→primitive converter |
| `png.py` | stdlib-only PNG encoder for mesh/image layers |
| `raster.py` | Pillow raster backend for PNG export; svglib/reportlab for PDF |
| `fonts/` | bundled width tables + the family registry (layout only; no glyph rasterization) |
| `_interactive.py` | inlined vanilla JS: toolbar, per-axes zoom, picking, annotate, sliders, export |
| `qt.py` | optional PyQt/PySide WebEngine widget + window (`fig.show_qt()`, `[qt]` extra) |

Artists never render themselves — they just hold arrays. The geometry of each
artist is computed once in `primitives.py`; `svg.py` and `raster.py` are thin
emitters over that shared primitive vocabulary, so an artist is defined in one
place, not per backend.

**Fonts.** A figure is laid out *before* anything draws its glyphs — SVG emits
`<text>` and lets the viewer rasterize — so plotpress has to predict text width
from bundled metric tables. That keeps layout identical on every machine with no
font-file dependency. Bundled are the base-14 metric families — **Helvetica,
Times and Courier**, each in regular / bold / italic / bold-italic — plus
**DejaVu Sans**, which covers the metric-compatible clones too (Arial and
Liberation Sans are Helvetica, Liberation Serif is Times, Liberation Mono is
Courier). Families outside those groups — Verdana, Tahoma, Arial Black, Arial
Narrow — have proprietary metrics, so they render but are measured as Helvetica
and need hand-tuned `figsize`; `Style(measure_installed_fonts=True)` opts into
measuring the real file on this machine instead, trading cross-machine
reproducibility for fidelity. PNG export picks a matching face, falling back to
Pillow's built-in font where the system has none.
