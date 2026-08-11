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

    Figure ──owns──> Axes ──holds──> artists (artists.py)
                                        │
                          transform.py  │  data space -> pixel space
                                        v
                          artist_to_prims (primitives.py)
                                        │  backend-agnostic pixel-space prims
                        ┌───────────────┼───────────────┐
                        v               v               v
                    svg.py          raster.py     _interactive.py
                  (SVG string)   (PNG via Pillow,   (vanilla JS layered
                                  PDF via svglib)    onto the SVG)

`Figure.to_svg()` is the core entry point; `Figure.save(path, interactive=...)`
dispatches on the file extension. A new plotting method usually means touching
`axes.py` (the public method), `artists.py` (the scene object),
`primitives.py` (the prim conversion), and then each backend that must draw it.

## Module map

Line counts included because several of these are large — read the section you
need rather than the whole file.

| File | Lines | What lives there |
|---|---|---|
| `plotpress/axes.py` | 1430 | The `Axes` object: every public plotting method, limits, scales, ticks, legend setup |
| `plotpress/svg.py` | 1291 | SVG serialization — one `_render_*` per artist kind, plus axis decoration |
| `plotpress/_interactive.py` | 1181 | The vanilla-JS payload injected into interactive HTML (pan/zoom, pick, toolbar) |
| `plotpress/artists.py` | 927 | Scene objects (`Line2D`, `Bars`, `Contour`, …) — data, not geometry |
| `plotpress/raster.py` | 820 | PNG backend via Pillow; PDF via svglib/reportlab |
| `plotpress/figure.py` | 729 | The root object: layout, `to_svg`, `save`, `show`, figure-level text and legend |
| `plotpress/axes3d.py` | 310 | 3-D `(x, y, z)` axes on top of the 2-D core |
| `plotpress/colors.py` | 290 | Colormaps and `Normalize` / `LogNorm` / `PowerNorm` / `SymLogNorm` |
| `plotpress/primitives.py` | 286 | Pixel-space prims (`Path`, `Markers`, …) + `artist_to_prims`; line decimation |
| `plotpress/qt.py` | 230 | Embed interactive figures in PyQt/PySide (`qt` extra) |
| `plotpress/polar.py` | 213 | Polar `(theta, r)` axes on top of the Cartesian core |
| `plotpress/ticker.py` | 166 | Tick locations and label formatting (1-2-5 "nice numbers") |
| `plotpress/_spectral.py` | 142 | Spectral estimators behind the signal-processing methods |
| `plotpress/png.py` | 93 | Minimal stdlib-only PNG encoder (`zlib`) |
| `plotpress/style.py` | 91 | Per-figure `Style` — the replacement for `rcParams` |
| `plotpress/transform.py` | 85 | Vectorized data-space → pixel-space transforms |
| `plotpress/fonts/` | ~590 | Bundled advance-width tables, family resolution, opt-in installed-font measurement |

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
execute every script under `docs/examples`, `docs/scale`, `docs/applications`:

```bash
python -m sphinx -b html -W --keep-going docs docs/_build/html
```

Benchmarks (needs the `bench` extra for matplotlib/seaborn):

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
versioningit derives it, and `plotpress/_version.py` is a generated build
artifact (git-ignored). Don't hand-edit it or add a literal to `__init__.py`.

## Repo gotchas

- **`docs/` is 226 files, 183 of them gallery scripts** under `applications/`
  (122), `examples/` (69), and `scale/` (15). Scope searches to `plotpress/` or
  `tests/` unless the gallery is genuinely the subject.
- **`docs/_build/` is ~94 MB** of generated HTML, and `examples/*.svg|html|png|pdf`
  are generated outputs. All git-ignored; never read them to answer a question
  about behavior — read the script that produced them.
- **`docs/auto_examples/`, `auto_scale/`, `auto_applications/`** are written by
  sphinx-gallery at build time. Edit the source scripts, not the generated pages.

## Releasing

Tagging and publishing are deliberately separate steps, because a PyPI version
can never be reused:

1. `git tag -a 0.1.0 -m "..."` — the tag *is* the version.
2. Publish the GitHub Release (or dispatch `release.yml` by hand). The workflow
   refuses to publish anything carrying a `.postN`, `+dirty`, or `0+unknown`
   suffix, which would mean a missing tag or an unclean tree.

Docs deploy to GitHub Pages automatically on every push to `main`.
