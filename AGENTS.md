# plotpress

A figure-centric, SVG-first plotting library with a matplotlib-shaped API. Pure
Python, no compiled extension. Three things define it, and most design questions
resolve by appealing to one of them:

1. **No global state.** No `pyplot`, no current figure/axes, no global
   `rcParams`. Everything hangs off a `Figure`, which owns its own `Style`.
2. **matplotlib-like API.** `plotpress.subplots()` returns `(fig, axes)`;
   method names mirror matplotlib so existing code ports easily.
3. **SVG first, raster only where needed.** Vector output, with embedded PNG
   only for mesh/image layers. Hot paths are vectorized in NumPy; huge lines are
   decimated.

## Render pipeline

    Figure ──owns──> Axes ──holds──> artists (artists.py) ─────────────────┐
                                        │                                    │  data-space fields
                          transform.py  │  data space -> pixel space        │  read directly, own
                                        v                                    │  scale/encoding
                          artist_to_prims (primitives.py)                    v
                                        │  backend-agnostic pixel-space   vega_lite.py
                                        │  prims                         (Vega-Lite v5 spec,
                    ┌───────────────────┼───────────────────┬───────────┐   stricter grammar,
                    v                   v                   v           v   barely touches the
                svg.py              raster.py         _interactive.py  vega.py  prims layer at all)
              (SVG string)       (PNG via Pillow,     (vanilla JS      (Vega v5 JSON
                                  PDF via svglib)       layered onto    spec, not SVG,
                                                         the SVG)       reuses primitives.py)

`Figure.to_svg()` is the core entry point; `Figure.save(path, interactive=...)`
dispatches on the file extension. A new plotting method usually means touching
`axes.py` (the public method), `artists.py` (the scene object),
`primitives.py` (the prim conversion), and then each backend that must draw it
-- except `vega_lite.py`, which builds its marks straight from `artists.py`'s
own data-space fields (see `docs/user_guide/architecture.rst` for why).

## Module map

Line counts included because several of these are large — read the section you
need rather than the whole file.

| File | Lines | What lives there |
|---|---|---|
| `src/plotpress/axes.py` | 4055 | The `Axes` object: every public plotting method, limits, scales, ticks, legend setup |
| `src/plotpress/figure/` | ~5182 | The root object, split by concern: `_core` (`Figure` itself, plus `Group`/`GroupLayout`/`subplots()`/`subplots_from_groups()` -- genuinely mutually coupled with `Figure`, so they stay one file rather than a forced acyclic split), `_layout` and `_html_options` (the two leaf modules `_core` depends on -- render-time layout/summary helpers, and startup-option validation + HTML-export JSON encoding), `_template` (`figure_from_template`, built from `_core`), `_report` (the `Report` multi-figure aggregator), `_io` (`load_data`/`load_data_xarray`/`load_template`/`select_panel` -- the round-trip's load side, which recovers plain data/dicts rather than a rebuilt `Figure`). `__init__.py` re-exports everything |
| `src/plotpress/svg/` | ~3681 | SVG serialization, split by concern: `_format` (leaf string/geometry helpers), `_ticks_and_frame`, `_text_and_annotations`, `_legend` (+ colorbar), `_render` (one `_render_*` per artist kind — the bulk), `_group_layout` (`Figure.group()`'s boxes), `_core` (`figure_to_svg`, the public entry point), `_metadata` (the interactive-HTML JSON payloads). `__init__.py` re-exports everything, including the private helpers `raster.py` imports (legend/tick/text-box geometry) |
| `src/plotpress/raster.py` | 1586 | PNG backend via Pillow; PDF via svglib/reportlab |
| `src/plotpress/vega.py` | 1445 | `Figure.to_vega()`: a real Vega v5 JSON spec, reusing `primitives.py` |
| `src/plotpress/artists.py` | 1420 | Scene objects (`Line2D`, `Bars`, `Contour`, …) — data, not geometry |
| `src/plotpress/vega_lite.py` | 1320 | `Figure.to_vega_lite()`: a Vega-Lite v5 spec, three fidelity tiers |
| `src/plotpress/colors.py` | 789 | Colormaps and `Normalize` / `LogNorm` / `PowerNorm` / `SymLogNorm` |
| `src/plotpress/fonts/` | ~590 | Bundled advance-width tables, family resolution, opt-in installed-font measurement |
| `src/plotpress/primitives.py` | 530 | Pixel-space prims (`Path`, `Markers`, …) + `artist_to_prims`; line decimation |
| `src/plotpress/_js/` | ~5300 | The vanilla-JS toolbar (pan/zoom, pick, Slice, …), split by tool/feature into one `.js` file per concern — see `src/plotpress/_interactive.py`'s own module docstring for the file list. Not Python; not counted in any total below |
| `src/plotpress/qt.py` | 440 | Embed interactive figures in PyQt/PySide (`qt` extra) |
| `src/plotpress/ticker.py` | 432 | Tick locations and label formatting (1-2-5 "nice numbers"), plus the declarative locator/formatter specs `set_x/ylocator`/`set_x/yformat` accept |
| `src/plotpress/polar.py` | 240 | Polar `(theta, r)` axes on top of the Cartesian core |
| `src/plotpress/_interactive.py` | 239 | Assembles `src/plotpress/_js/`'s fragments into the one script string `figure.py` inlines into every interactive export — the file itself is just that assembly plus the module docstring describing the toolbar's UX; the JS is what actually got big |
| `src/plotpress/dates.py` | 172 | Datetime axis support: date ⟷ float-days-since-epoch conversion, calendar-aware tick locating/formatting |
| `src/plotpress/style.py` | 155 | Per-figure `Style` — the replacement for `rcParams` |
| `src/plotpress/_spectral.py` | 154 | Spectral estimators behind the signal-processing methods |
| `src/plotpress/png.py` | 120 | Minimal stdlib-only PNG encoder (`zlib`) |
| `src/plotpress/transform.py` | 85 | Vectorized data-space → pixel-space transforms |

This table is a size guide, not a promise -- regenerate it (`wc -l src/plotpress/*.py`) whenever
it visibly drifts rather than trusting a stale number.

## Commands

Tests (`testpaths = ["tests"]`, browser tests deselected by default):

```bash
pytest -q
```

What CI runs on the Python matrix (3.9–3.14):

```bash
pytest -m "not perf and not browser" -q
```

Point-picking tests, which drive the interactive HTML's JS in headless Chromium.
Needs `pip install .[browser]` and `playwright install chromium`:

```bash
pytest -m browser -q
```

Build the docs the way CI does — warnings are errors, and the three galleries
execute every script under `docs/examples`, `docs/scale`, `docs/applications`
(needs the `docs` extra: `pip install .[docs]`). `-j` runs the gallery scripts
in parallel (opt-in; omit it for a plain serial build):

```bash
python -m sphinx -b html -W --keep-going -j auto docs docs/_build/html
```

Benchmarks (needs the `bench` extra for matplotlib/seaborn/plotly):

```bash
python -m benchmarks.benchmark
```

Regenerate the bundled font metric tables:

```bash
python tools/gen_font_metrics.py
```

## Conventions

**Comments explain why, not what.** The existing comments carry the reasoning
behind a choice — why the default-tag exists, why browser tests are opt-in, why
the "drew something" check compares against a forced-limits empty axes. Match
that; don't add comments that restate the code.

**Tests assert on parsed output, not strings.** `xml.etree.ElementTree` parses
the SVG (which also asserts well-formedness) and the test counts or inspects
elements. See `tests/test_render_all.py` for the pattern. Cross-library
comparisons `importorskip` matplotlib/seaborn so a plain install still runs.

**No global state is a tested invariant** — `tests/test_no_global_state.py`.
Anything module-level and mutable is a bug.

**The version comes from the git tag.** There is no version literal anywhere;
versioningit derives it, and `src/plotpress/_version.py` is a generated build
artifact (git-ignored). Don't hand-edit it or add a literal to `__init__.py`.

## Repo gotchas

- **`docs/` is ~397 tracked files, 336 of them gallery scripts** under `applications/`
  (165), `examples/` (106), `figure_layout/` (32, incl. its `grouping/` section),
  `live_streaming/` (18), and `scale/` (15). Scope searches to `src/plotpress/` or
  `tests/` unless the gallery is genuinely the subject.
- **`docs/_build/` is ~370 MB** of generated HTML, and `examples/*.svg|html|png|pdf`
  are generated outputs. All git-ignored; never read them to answer a question
  about behavior — read the script that produced them.
- **`docs/auto_examples/`, `auto_figure_layout/`, `auto_scale/`,
  `auto_live_streaming/`, `auto_applications/`** are written by sphinx-gallery at
  build time. Edit the source scripts, not the generated pages.

## Deferred design work

**Overlaid meshes in Slice.** The interactive Slice tool (`_interactive.py`) slices
only the *first* mesh of an axes; a second mesh drawn into the same axes (e.g. a
translucent field over a base map) is ignored, so the strip can disagree with what
the heatmap shows. This is a known limitation, deliberately left for a designed
tool rather than patched: the intended shape is one line per mesh in the strip
(own colour and legend key), a line absent wherever its mesh doesn't cover the
cursor. That needs the cursor to become a *data coordinate* (each mesh snapping to
its own nearest row/column) instead of an index into the first mesh's grid, and
pins/Extract to record which mesh a sample came from. Don't bolt a partial version
onto the index-based slider; design it as a whole when it's picked up. (Inset axes
are a different case: they are left out of Slice on purpose.)

## Releasing

Tagging and publishing are deliberately separate steps, because a PyPI version
can never be reused:

1. `git tag -a 0.1.0 -m "..."` — the tag *is* the version.
2. Publish the GitHub Release (or dispatch `release.yml` by hand). The workflow
   refuses to publish anything carrying a `.postN`, `+dirty`, or `0+unknown`
   suffix, which would mean a missing tag or an unclean tree.

Docs deploy to GitHub Pages automatically on every push to `main`.
