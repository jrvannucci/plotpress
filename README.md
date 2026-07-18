# simpleplot

A fast, **figure-centric**, **SVG-first** plotting library with a matplotlib-like
API and **no global state**.

```python
import simpleplot
import numpy as np

fig, ax = simpleplot.subplots()
x = np.linspace(0, 4 * np.pi, 400)
ax.plot(x, np.sin(x), label="sin")
ax.plot(x, np.cos(x), label="cos", linestyle="--")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.legend()

fig.save("out.svg")                       # static vector SVG
fig.save("out.png"); fig.save("out.pdf")  # raster + vector export
fig.save("out.html", interactive=True)    # interactive toolbar: zoom / pick / annotate
fig.show()                                # native pop-up window
```

## Why simpleplot is different from matplotlib

1. **No `pyplot`, no globals.** There is no "current figure/axes" and no global
   `rcParams`. A `Figure` owns its axes and its own `Style`; two figures never
   share mutable state. `simpleplot.subplots()` returns `(fig, axes)` just like
   `plt.subplots()` — but touches no global state.
2. **matplotlib-like API** so porting is easy: `Figure`/`Axes`, `plot`,
   `scatter`, `pcolormesh`, `set_xlabel/ylabel/title`, `set_xlim/ylim`, `grid`,
   `legend`, `colorbar`.
3. **SVG-first + built for speed.** Output is vector SVG; only mesh/image layers
   are rasterized (as a single embedded `<image>`, not thousands of rects). Each
   series is one `<path>`. The hot paths (coordinate formatting, per-axes
   fragment assembly) are isolated so they can move to a **Rust backend** later.

## Install

```bash
pip install simpleplot            # SVG + interactive HTML + PNG/PDF export
pip install simpleplot[gui]       # + native pop-up window (fig.show(), pywebview)
pip install simpleplot[dev]       # + pytest (contributors)
pip install simpleplot[bench]     # + matplotlib (benchmark comparison)
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

## Interactive figures

Interactive HTML and pop-up output carry a self-contained vanilla-JS toolbar (no
external requests, so it works under strict CSPs like Jupyter and sandboxed
webviews). Nothing is active until you pick a tool:

- **Span** — drag to pan a single plot's data window (log-aware).
- **Zoom** — wheel or rubber-band box to zoom *one* axes in **data space**; its
  ticks recompute and markers keep a constant size.
- **Point Pick** — click to pin the nearest data point's value; arrow keys step
  along the series (nearest-neighbour for scatter, cell-by-cell for
  meshes/contours), reporting extra dims (`z`, `c`, …). Right-click deletes.
- **Annotate** — click to drop a text note anchored to the data.
- **Reset** restores the view (double-click resets just the plot under the
  cursor). **Extract** copies/downloads all markers + annotations as CSV/JSON,
  or hands them back to the kernel (`fig.show(wait_for_extract=True)`).

3-D data via `ax.plot_frames(...)` adds a **slider** (play/pause/step) over the
extra dimension; multiple sliders can be linked by a shared index.

## Supported plot types

simpleplot covers the core of matplotlib's "Plot types" reference grid:

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

Plus reference marks & fills — `axhline`/`axvline`, `axhspan`/`axvspan`,
`fill`/`fill_between`/`fill_betweenx`, `hlines`/`vlines` — and axis control:
**log scales** (`set_xscale`/`set_yscale`/`loglog`/`semilogx`),
**`set_aspect("equal")`**, `set_xlim/ylim`, `set_xticks/yticks`,
`set_xticklabels/yticklabels`, `invert_xaxis/yaxis`, `margins`, `grid`,
`set_axis_off`, **`subplots(sharex=…, sharey=…)`**, and **`twinx`/`twiny`**
(overlaid axes with a second y/x axis), `tick_params` (per-axes tick styling),
and matplotlib `"C0"`..`"CN"` cycle colors. Plus **`fig.tight_layout()`**
(auto-margins so labels never overflow), text (`ax.text`, `ax.annotate` with
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
triangulation (`tri*`), polar, and 3-D axes. These are the main remaining
plot-type gaps vs matplotlib's full gallery.

## Testing

```bash
pip install simpleplot[dev]         # pytest
python -m pytest -m "not perf"  # fast unit + output tests (~2s)
python -m pytest -m perf -s     # timing tests + speedup report (needs matplotlib)
```

The suite covers the no-global-state invariants, plotting/autoscale logic,
transforms/tickers/colors, a lossless PNG round-trip, SVG/HTML well-formedness
and structure, and performance (regression guards + a comparative claim vs
matplotlib).

## Benchmarks

```bash
pip install simpleplot[bench]        # matplotlib, for comparison
python benchmarks/benchmark.py  # simpleplot vs matplotlib, plot build + SVG output
```

Representative run (best of 3, one machine — build **and** serialize to SVG,
both using the object-oriented API):

| scenario | simpleplot | matplotlib | speedup |
|----------|------:|-----------:|--------:|
| pcolormesh 300×300 | ~16 ms | ~6400 ms | **~400×** |
| many axes (8×8 grid) | ~40 ms | ~1600 ms | **~40×** |
| scatter, 5k points | ~15 ms | ~220 ms | **~14×** |
| single line, 100k points | ~9 ms | ~48 ms | **~5.6×** |

**Honest caveat:** simpleplot's win comes from avoiding matplotlib's per-`Artist`
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

**Next:**
- **Rust backend** (PyO3/maturin) — vectorized transforms, fast float→string
  serialization, and **parallel per-axes fragment rendering (`rayon`)** for the
  many-axes case; would also unify the SVG and PNG renderers.
- More plot types: `streamplot`/`barbs`, triangulation (`tri*`), polar, and
  3-D axes.
- Hover tooltips; Gouraud (smooth-shaded) pcolormesh.

## Architecture notes

`simpleplot/` layout:

| Module | Responsibility |
|--------|----------------|
| `figure.py` | `Figure`, `subplots()`, layout, save/show/`_repr_*` |
| `axes.py` | `Axes`: plotting methods, limits, autoscale |
| `artists.py` | data-only scene primitives (`Line2D`, `ScatterCollection`, `QuadMesh`) |
| `style.py` | per-figure `Style` (replaces global `rcParams`) |
| `transform.py` | vectorized data→pixel transforms (linear + log scales) |
| `colors.py` | `Normalize`, colormap LUTs, colormap application |
| `ticker.py` | "nice number" + log tick locations, label formatting |
| `svg.py` | the renderer: scene → SVG string (+ per-axes metadata) |
| `png.py` | stdlib-only PNG encoder for mesh/image layers |
| `raster.py` | Pillow raster backend for PNG export; svglib/reportlab for PDF |
| `fonts/` | bundled Helvetica metrics (layout only; no glyph rasterization) |
| `_interactive.py` | inlined vanilla JS: toolbar, per-axes zoom, picking, annotate, sliders, export |

Artists never render themselves — they just hold arrays. Rendering is a single
pass in `svg.py`, which is exactly the boundary a Rust backend would slot into.
