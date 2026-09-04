# Changelog

All notable changes to plotpress are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions come from git tags: a release *is* a tag (e.g. `0.1.0`), and the
package version is derived from it at build time rather than written down
anywhere in the source.

## [Unreleased]

### Added

- **The home page's "one figure, several outputs" diagram now uses real
  box-drawing lines** (matching `CLAUDE.md`'s own render-pipeline diagram)
  instead of plain `+`/`-`/`v` ASCII.
- **A new "Reading a figure back out of HTML" diagram** on the home page,
  covering the reverse direction the first diagram didn't: a saved
  ``interactive=True`` HTML file's embedded JSON, through
  `plotpress.load_data()` and `plotpress.subplots_from_layout()`, to a
  rebuilt `Figure` ready for the caller to replot recovered data into.
  Links to the full API docs and the `data_roundtrip` example gallery.

### Fixed

- **A third break-it audit** (new territory: real `load_data()`/
  `subplots_from_layout()` round trips, `Report`, polar axes, `Figure.
  group()`, `plot_frames()`, style independence, `adopt_axes()`) found and
  fixed three more real bugs, two of them affecting completely ordinary
  matplotlib usage, not edge cases:

  - **A plain RGB(A) tuple color** (`color=(1.0, 0.0, 0.0)`) reached the
    SVG backend as a literal, invalid `stroke="(1.0, 0.0, 0.0)"` (silently
    invisible -- a browser treats an unrecognized value as unset) and
    crashed PNG export outright with `'tuple' object has no attribute
    'lstrip'`. `to_hex()` now recognizes a flat, purely-numeric 3/4-element
    sequence as an RGB(A) color and converts it, matching matplotlib's own
    convention (floats in `[0, 1]` or already `0-255`).
  - **`bar()`'s one-color-per-bar array** (`color=[[r, g, b, a], ...]`)
    reached every renderer's own `fill=`/`stroke=` as a raw, unresolved
    Python list per bar -- `fill="[1.0, 0, 0, 1]"` in SVG, the same class
    of bug as the tuple one above, just one level of nesting deeper.
    `artists._as_colors()` now resolves each bar's own color through
    `to_hex()` once, the same "resolve here, once" fix already applied to
    `Axes._resolve_color()` earlier in this audit.
  - **`plot_frames()` with zero frames** (`Y` shaped `(0, n_points)`)
    crashed at *render* time with a bare `IndexError` -- rendering always
    draws "frame 0" unconditionally, which doesn't exist when there are no
    frames at all. Now validated eagerly.

  Verified via a third adversarial battery (~30 new cases: real HTML round
  trips including `Report`/polar/`twinx`/`sharex`/groups, not just
  isolated method calls), the full non-browser + browser suite (1026 + 105
  passed), and a from-clean full docs rebuild -- zero regressions.
  `tests/test_input_validation.py` gained 11 more tests (62 total).

- **A second, more aggressive break-it audit** (new territory: legends,
  annotations, gridded-data methods, `table()`/`bar_label()`, `quiver()`/
  `barbs()`, colorbar geometry, text sizing) found and fixed seven more
  cases of the same pattern -- plausible input crashing with a confusing
  internal traceback, or degrading silently with no warning:

  - **`bar_label(labels=...)` with the wrong count** crashed with a bare
    `IndexError` three frames into text placement. Now raises immediately,
    naming the actual mismatch.
  - **`table()` with mismatched `rowLabels`/`colLabels`/ragged rows**
    crashed with a bare `IndexError` at *render* time, not at the `table()`
    call that caused it. Now validated eagerly.
  - **`quiver()`/`barbs()` with `U`/`V` shaped differently from `X`/`Y`**
    reached a bare NumPy broadcast error inside `Quiver.tips()` at render
    time. Now validated eagerly, same as the paired-array fix from the
    first audit.
  - **A non-string legend label** (`label=42` -- a common loop-variable
    accident) crashed with `TypeError: 'int' object is not iterable` deep
    in the font-metrics text-width walk, in both the SVG *and* PNG legend
    (two separate, independently-broken code paths). Both now stringify
    the label, matching matplotlib. Along the way: `label=0`/`0.0`/`False`
    was being silently excluded from the legend entirely (a truthiness
    check, not a `None`/`""` check) even though it's a legitimate label
    matplotlib shows as `"0"` -- fixed in both backends.
  - **A negative `fontsize`** on `text()`/`annotate()` reached the SVG
    backend as a literal, invalid `font-size="-12"` attribute -- not a
    crash, just silently unrenderable text. Now raises.
  - **`colorbar(fraction<=0)`** produced a colorbar axes with a *negative*
    pixel width -- an invalid layout, not a crash, so nothing caught it.
    Now validated eagerly.
  - **`imshow(extent=...)` with a non-finite bound** (e.g. a `NaN` from an
    upstream calculation) was silently dropped by autoscale's finite-only
    filter, falling back to a default range that quietly didn't match the
    `extent=` actually given -- no error, no warning anywhere. Now raises.

  Verified via a second adversarial battery (~45 new cases across legends,
  annotations, gridded-data methods, spectral methods, `subplots_from_
  layout()` round trips, sharing, and unverified survivors from the first
  audit), the full non-browser + browser suite (1015 + 105 passed), and a
  from-clean full docs rebuild -- zero regressions. `tests/test_input_
  validation.py` gained 17 more tests (51 total) pinning these plus the
  first audit's seven.

- **CI's `Tests (py3.9)`/`(py3.10)`/`(py3.11)` jobs were failing on every
  push** -- `plotpress/svg.py`'s multiline-text renderer had a nested
  f-string with a backslash inside another f-string's `{...}` expression
  part, which PEP 701 only legalized in Python 3.12. Every 3.9-3.11 job
  raised `SyntaxError: f-string expression part cannot include a
  backslash` on import and failed outright, while 3.12-3.14 (this
  project's own dev environment) never saw it. Rewritten to build the
  nested `dy="..."` fragment as a plain variable first, with identical
  output. `tests/test_python_compat.py` (new) pins the source pattern
  that caused this so it can't silently regress again, and confirms the
  fixed renderer's output is unchanged.

- **A break-it audit across the whole library** found and fixed seven cases
  where an input a real user would plausibly pass either crashed with a
  confusing internal traceback, rendered silently wrong with no warning at
  all, or produced literally invalid SVG/PNG output:

  - **Unrecognized color names.** `to_hex()` only knew ~24 basic named
    colors; anything else -- including completely ordinary CSS/matplotlib
    names like `"cornflowerblue"` that were never in that small table --
    passed straight through unresolved. The SVG backend often got lucky
    (a browser natively understands CSS names), but the raster backend's
    hex parser crashed with a bare `int(..., 16)` error mentioning nothing
    about color, and a genuine typo (`"crimon"`) reached the SVG backend
    as an invalid `stroke=`/`fill=` attribute -- silently invisible, no
    error anywhere. `NAMED_COLORS` now carries the full CSS4 named-color
    set (matching `matplotlib.colors.CSS4_COLORS`), and `to_hex()` raises
    a clear `ValueError` for anything still unresolvable (a misspelling or
    malformed hex) instead of passing it through. `"none"`/`"transparent"`
    still pass through unresolved -- real SVG/CSS paint keywords already
    used elsewhere in this codebase, not colors to validate.
  - **Mismatched-length paired arrays** (`plot`, `scatter`, `bar`, `barh`,
    `fill_between`, `fill_betweenx`, `hlines`, `vlines`, `errorbar`) used
    to reach a bare NumPy broadcast/concatenate error deep inside
    `transform.py`/`artists.py` with no mention of which plotting call
    produced it. `stem()` was worse: it silently `zip()`-truncated to the
    shorter array with no error or warning at all. All now validate
    eagerly and name the method and the actual shapes.
  - **`Figure.colorbar(mappable, ...)` with an invalid `mappable`** (e.g.
    `None`) crashed with `AttributeError: 'NoneType' object has no
    attribute 'norm'` three calls deep. Now raises a clear `TypeError` up
    front.
  - **`print_layout_summary()`/`print_summary()` mis-reported axis
    direction** for an axis inverted via `set_xlim(hi, lo)` (a completely
    ordinary way to invert an axis, and matplotlib's own idiom) rather
    than `invert_xaxis()` -- the figure genuinely rendered inverted (see
    `transform.py`'s pixel math), but the summary checked only the
    `invert_xaxis()` flag and said nothing, misdescribing the exact kind
    of figure this feature exists to describe accurately. Now computes
    the actually-rendered direction the same way `svg.py`'s own renderer
    does.
  - **A log-scaled axis with no positive data rendered a completely empty
    panel with zero warning** -- `_pad()` has no sane range to return for
    an axis whose real data is entirely non-positive, so it silently
    clamped to an arbitrary small positive window containing none of the
    actual data. Now warns, matching matplotlib's own message.
  - **`Figure(figsize=...)` accepted a non-positive width/height**,
    producing a literally invalid SVG (`width="0"` or a negative width
    attribute) with no validation anywhere. Now raises immediately.
  - **`pie()` accepted a negative wedge value**, producing a genuinely
    negative wedge fraction (a wedge sweeping the wrong way) instead of
    the `ValueError` matplotlib itself raises for the same input.

  Verified via a dedicated adversarial test battery across ~70 edge cases
  (empty/single-point/all-NaN data, degenerate limits, zero/negative
  figsize, mismatched shapes, unknown colors/colormaps, twin/inset/
  colorbar edge cases), a full non-browser + browser test suite pass, and
  a from-clean `python -m sphinx -b html -W --keep-going` rebuild
  re-executing all 420 files across every gallery -- zero regressions,
  zero new warnings. `tests/test_input_validation.py` (new, 34 tests)
  pins all seven fixes as regressions.

### Added

- **`Figure.print_layout_summary()` / `Axes.print_summary()`** print a
  plain-English orientation to a figure/axes -- how many axes there are,
  how each is arranged (a grid cell, a multi-cell span, a `twinx()`/
  `twiny()` overlay, a secondary axis, an inset, a colorbar, or a
  free-form `add_axes()` rect), what's plotted on it, its scales/limits/
  labels, and whether it would export cleanly to `to_vega()`/
  `to_vega_lite()` -- naming exactly which artist or structural gap would
  warn, not just "yes/no". Meant for the fastest way to understand a
  figure you didn't build yourself (a saved layout, an imported HTML
  file) -- both print to stdout and return nothing, not for programmatic
  use.

  The export-compatibility lines are never a separately-maintained "what's
  supported" list that could drift from the real exporters: both methods
  actually call `fig.to_vega()`/`fig.to_vega_lite()` (capturing their real
  warnings/caveats) and report exactly what came back, attributed back to
  the axes each one named. `Figure.print_layout_summary()` and
  `Axes.print_summary()` share the same per-axes description code, so the
  two can never describe the same axes differently.

  Named `print_*`, not e.g. `layout_summary()`/`summary()`, so they
  tab-complete together -- and alongside whatever summary methods this
  library adds next.

- **`Figure.to_vega(mesh_data=True)` / `Figure.to_vega_lite(mesh_data=True)`**
  opt a `pcolormesh`/mesh-backed `imshow` into real per-cell `rect` marks
  with a genuine `field`+`scale` color encoding, instead of the default
  rasterized `image` mark -- reactive to a downstream color-scale change,
  and queryable by anything reading the spec, not just a picture of the
  result. The default stays `False` (the rasterized path) -- this is a
  scoped, opt-in feature, not a change to either export's own default
  behavior.

  Only offered for meshes small/simple enough to stay cheap and
  unambiguous: a rectilinear (non-curvilinear) grid, a plain linear color
  `Normalize` (not `LogNorm`/`PowerNorm`/`SymLogNorm`), a colormap with an
  exact-name match in Vega's own built-in scheme catalog (`viridis`,
  `plasma`, `inferno`, `magma`, `cividis`, `turbo`, and the single-hue
  `Blues`/`Greens`/`Oranges`/`Reds`/`Purples`/`gray` families -- silently
  guessing a "close enough" scheme for anything else risked a
  wrong-colored mesh, worse than not offering the path at all), and at
  most `_VECTOR_CELL_LIMIT` (~2000) cells -- the exact same threshold
  `pcolormesh(rasterized=None)`'s own auto-mode already uses for "how
  many discrete cells is reasonable to draw individually," reused rather
  than a new number invented for this. A mesh that doesn't qualify still
  gets the image mark, with a `UserWarning` naming exactly why
  (`"...falling back to a rasterized image mark for it instead"`).

  A new `docs/examples/gridded_data/plot_12_small_mesh_reactive_data.py`
  (a small 10x8 grid, comfortably under the cell limit) demonstrates it;
  the docs gallery scraper now passes `mesh_data=True` for every
  example's Vega/Vega-Lite export page, so any *other* small-enough mesh
  already in the gallery shows the real per-cell path too, for free.

  A dedicated audit (a real-engine PNG-vs-raw-data comparison across every
  eligible mesh in the gallery, plus targeted edge-case testing) found and
  fixed four real bugs before this shipped:
  - **`cmap="gray"`/`"gray_r"` rendered color-inverted.** Vega's built-in
    `"greys"` scheme follows ColorBrewer's light=low/dark=high convention
    -- the same direction `viridis`/`plasma`/`Blues`/`Greens`/etc. already
    use, which is why the generic `_r`-suffix handling is correct for all
    of them. plotpress's own `"gray"` colormap follows matplotlib's
    literal-luminance convention instead (black=low, white=high) -- the
    *opposite* direction -- so it needs `reverse=True` (and `"gray_r"`
    needs `reverse=False`), backwards from every other entry. Found by
    sampling actual rendered pixel colors against plotpress's own LUT.
  - **A numpy `vmin`/`vmax` broke JSON serialization** (`vmin=data.min()`
    is an entirely ordinary pattern) -- the one place on this path that
    skipped the `float()` cast every other value already gets.
  - **An all-NaN mesh silently disappeared** -- eligible per the
    capability check (which never looked at whether there was any finite
    data), then produced zero rows and zero marks with no fallback and no
    warning, contradicting this feature's own "never silently wrong,
    always fall back with a warning" contract. Now excluded explicitly,
    falling back to the rasterized path like every other disqualified case.
  - **A log-scaled axis could produce `NaN` pixel coordinates.** Unlike
    every other mark, a raw per-cell `rect`'s x/y defers to the same
    shared scale every other mark on the axes uses, computed by the
    Vega/Vega-Lite runtime itself at render time -- not pre-clamped in
    pixel space via `transform.py` the way the rasterized path (and every
    other backend) already is. A cell edge at exactly 0 (an ordinary
    edge-based grid starting at the origin) fed into a log-typed scale
    evaluates to `NaN` there, confirmed against the real `vega` runtime.
    Now excluded explicitly rather than silently producing broken cells.

- **`Figure.to_vega_lite()`** returns a Vega-Lite v5 specification -- a
  stricter, more declarative sibling to `Figure.to_vega()` (Vega-Lite
  compiles down to Vega itself, with a closed mark vocabulary and no raw
  path-per-datum mark, and a grid-like `hconcat`/`vconcat` composition
  model instead of Vega's arbitrary-pixel-positioned `group` marks).
  Unlike every other export method, it returns `(result, caveats)`, not a
  bare value -- a deliberate, documented departure, not an oversight (see
  `Figure.to_vega_lite()`'s own docstring for why).

  Fidelity is a three-tier hybrid, spelled out in `plotpress.vega_lite`'s
  module docstring: `Line2D`, `ScatterCollection`, `Bars`, `ErrorBar`
  (Vega-Lite's own `errorbar` mark, with precomputed `yError`/`xError`
  fields -- genuinely *simpler* than `to_vega()`'s hand-built whisker/cap
  geometry), `Pie` (Vega-Lite's `arc` mark auto-stacks `theta`, no manual
  per-wedge trig), a monotonic-x `FillBetween` (a real `area` mark), and
  `QuadMesh`/`Image` (a real `image` mark, reusing the same rasterized
  RGBA + data extent every other backend already computes) map onto
  Vega-Lite's native vocabulary directly. Reference lines/spans, `Stem`,
  dashed lines, plain text, and custom tick labels (via `axis.labelExpr`,
  capped at ~12 ticks) work through a layered workaround within that same
  vocabulary. Everything already unsupported in `to_vega()` (`BoxPlot`,
  `Violin`, `Quiver`, `Contour`, `EventPlot`, `Barbs`, `Table`, legends)
  has no mapping here either, plus `PolyCollection` (no closed-vocabulary
  polygon-batch mark), a non-monotonic `FillBetween`, and annotation
  *arrows* specifically (the label stays, Vega-Lite has no arrow-drawing
  mark) -- each warns by name rather than silently dropping content.

  The harder problem Vega itself never forced: plotpress allows arbitrary
  grid spans, `add_axes()` free rects, `inset_axes()`, `twinx()`/`twiny()`,
  secondary axes, and colorbar axes, none of which `hconcat`/`vconcat` can
  position as freely as a Vega `group` mark's own explicit pixel position
  can. `to_vega_lite()` partitions a figure's axes into what composes
  cleanly into one nested `hconcat`/`vconcat` grid (`result["grid"]`), a
  twin merged into its parent's own view via Vega-Lite's
  `resolve.scale.<axis>: "independent"` (whichever axis it doesn't share
  -- `y` for `twinx()`, `x` for `twiny()`), and everything else exported as
  an independent standalone spec (`result["standalone"]`) rather than
  forced into a layout Vega-Lite was never asked to represent. Every
  structural compromise is collected into `caveats` (a dropped colorbar, a
  grid-shape mismatch, a spanning axes placed once instead of duplicated)
  -- data for a caller, not just console noise -- and re-emitted as one
  aggregate `UserWarning` too, so a caller who ignores the tuple still
  sees it.

  Three audit passes (semantic fidelity vs. `svg.py` field by field,
  empirical crash/edge-case testing against real figures, and a
  systematic comparison against `to_vega()`'s own output across the
  gallery) found and fixed real bugs before this shipped, several only
  visible by actually rendering through `vega-lite`/`vega`/`vega-cli`,
  not from the JSON alone:
  - **A multi-cell grid span was inserted as the *same* dict object into
    every cell it covered**, rendering duplicated side by side instead of
    spanning -- now placed once, at its own top-left cell, sized with an
    explicit pixel width/height.
  - **A colorbar axes was silently dropped with zero caveat**, despite
    every other excluded-axes kind warning by name -- it has no artists of
    its own to export (`fig.colorbar()` draws it through a separate path,
    not `ax.artists`) and Vega-Lite has no standalone gradient-legend
    mark to stand in for it, so it now warns explicitly instead of just
    vanishing.
  - **`twiny()`'s independent-scale merge was backwards** -- every twin
    got `resolve.scale.y: "independent"` regardless of which axis it
    actually shared with its parent, correct for the common `twinx()`
    case but exactly wrong for `twiny()` (shares `y`, wants `x`
    independent).
  - **A `pcolormesh`/`imshow` on an inverted axis rendered upside-down.**
    Reversing Vega-Lite's scale repositions an `image` mark's bounding
    box but does not re-flip the raster *inside* it the way a
    point/line/bar mark's geometry, computed from the data at render
    time, naturally would -- confirmed by rendering an inverted-axis mesh
    and comparing pixel-for-pixel against plotpress's own output. Now
    manually flipped to match, the same way `artist_to_prims`'s own
    `(QuadMesh, Image)` branch already does for the other backends.
  - `_bars_layer` crashed (`unhashable type: numpy.ndarray`) on a
    per-bar RGBA color array; `_errorbar_layers` forced Vega-Lite's caps
    on unconditionally, ignoring `capsize=0`; a `fill_between()` with
    all-`NaN` data was mislabeled as "non-monotonic" (a `NaN` comparison
    is always `False`, tripping the same check a real non-monotonic
    series does) instead of "nothing to draw"; `Text`/`Annotation`
    dropped vertical alignment and rotation entirely.
  - **A `pcolormesh`/`imshow` image rendered as a small square with blank
    space around it**, whenever the mesh's own row/col resolution wasn't
    already square -- Vega-Lite's `image` mark defaults to *preserving*
    the raster's own native pixel aspect ratio inside its box instead of
    stretching to fill it, unlike every other backend. Now `aspect: false`
    explicitly. Found by comparing this export's rendering directly
    against plotpress's own output for the same figure.
  - **Pie wedges rendered in the wrong angular order** (sorted by color,
    not data order) whenever the slice colors weren't already
    ascending-hex -- Vega-Lite's default stack order for a nominal color
    field sorts by that field rather than keeping row/input order. Wedge
    *sizes* were correct; which wedge sat where wasn't. Fixed with an
    explicit `order` channel pinning it back to data order.
  - **`linestyle="none"` with a marker still drew a solid connecting
    line** -- the mark stayed a `line` type with `point: true` regardless
    of the dash setting, since `linestyle="none"` has nothing for
    `strokeDash` to suppress. Now switches to a `point`-only mark, no
    line at all, matching plotpress's own "markers only" rendering.

  A fourth pass -- a systematic comparison against `to_vega()`'s own
  output across the gallery -- found two more:
  - **A non-monotonic-x line rendered as a zigzag**, connecting points in
    x-sorted order instead of data order (e.g. a parametric line like
    `ax.plot(sin(t), t)`) -- the same missing-`order` bug class as the pie
    fix above, applied to `line` marks too.
  - **`set_aspect("equal")`/`set_box_aspect()` figures rendered squashed
    or stretched** -- every view was sized from the raw, unadjusted axes
    cell, never the aspect-locked box `plotpress.vega`'s own
    `_axes_to_group` already shrinks to (centered within the cell). Found
    via a curvilinear, `aspect="equal"` mesh that should render as a
    circle and instead came out an ellipse -- affects *every*
    aspect-locked figure exported through `to_vega_lite()`, not just
    meshes.

  That same pass also found real coverage gaps and closed them, rather
  than just documenting them: `LineCollection` (`hlines()`/`vlines()`,
  violin inner quartile/whisker lines, `acorr()`/`xcorr()`) and `Rug`
  (seaborn-style rug plots) now export as real `rule` marks; `Polygon`
  (`fill()`, and critically `fill_betweenx()` -- the direct sibling of the
  already-supported `fill_between()`) now exports as a real `area` mark
  whenever it has the two-boundary-strip shape both calls actually build,
  falling back to a named warning only for a genuinely arbitrary closed
  shape (a filled circle, a hexbin cell) that has no Vega-Lite
  closed-vocabulary equivalent. All three previously fell through the
  generic "no Vega-Lite mapping yet" branch with a *fixed* warning message
  that named neither of them -- indistinguishable from a truly silent
  drop. Pie wedge **labels and `autopct` percentages**, documented as
  supported since this module's first version but never actually built,
  now render too -- as real per-wedge text layers positioned against an
  explicit arc center/radius (rather than trusting Vega-Lite's own
  undocumented auto-sizing, which the label math has to already know), and
  fixed a second bug surfaced while building them: a Vega-Lite layer with
  only literal `{"value": ...}` encodings and no `data` of its own has
  zero rows to instantiate its mark from and draws nothing, silently.

  Verified against every script in `docs/examples` **and**
  `docs/applications`: 298 figures export with zero failures and zero
  malformed/blank output, 221 scripts with one or more caveats or
  per-artist warnings (a colorbar, a legend, an arbitrary polygon, or one
  of the named unsupported artist types) cleanly named rather than
  silently dropped.

  `docs/conf.py`'s gallery scraper links every example/application figure
  with exportable content to a standalone page rendering its own
  `to_vega_lite()` output live (via `vega-lite` + `vega-embed`), the raw
  JSON, and any caveats -- mirroring the existing `to_vega()` page, with
  one difference: since a figure can produce several specs (a combined
  grid plus independent standalone ones), the page renders each in its
  own labeled panel instead of assuming exactly one.

- **`Figure.to_vega()`** returns a real Vega (not Vega-Lite) v5 JSON
  specification as a plain `dict` -- a third export surface alongside
  `to_svg()`/`to_html()`, for handing a figure to a Vega runtime instead of
  embedding plotpress's own rendering. Each axes becomes its own Vega
  `group` mark with local scales/axes, so plotpress's arbitrary subplot
  grids map onto Vega's own grouping rather than one flattened scene.

  Fidelity is a deliberate hybrid, spelled out in both the method's and
  `plotpress.vega`'s own docstrings rather than left implicit: `Line2D`
  (unmarked), `ScatterCollection`, `Bars`, `ErrorBar`, and `Stem` get real
  `field`+`scale`-encoded marks (reactive to a downstream change to the Vega
  scale domain). `Pie` and `Text`/`Annotation` get their own dedicated mark
  builders too, but stay frozen-pixel like everything below -- a pie draws
  in fixed axes-pixel space regardless of the data scale by design (it has
  none to be reactive to), and text is positioned at its resolved pixel
  location, matching what `to_svg()` itself does for both. Everything else
  reachable through the shared `artist_to_prims()` pixel-space layer (fills,
  spans, collections, rugs, quadmesh/image, ...) is likewise frozen
  pixel-space marks -- visually faithful to what plotpress itself computed,
  but not reactive. `BoxPlot`, `Violin`, `Quiver`, `Contour`, `EventPlot`,
  `Table`, `Barbs`, and animated `Frame*` artists have no Vega mapping yet;
  an axes using one warns once, naming the artist type, and skips just that
  artist rather than failing the whole export.

  Several real bugs only showed up by actually rendering a spec through a
  real Vega engine (`vega-cli`'s `vg2png`, and separately a browser via
  `vega-embed`) -- most are not visible from inspecting the JSON structure
  alone, since Vega silently drops or ignores what it can't place rather
  than erroring:
  - The y-axis scale is built with an ascending `domain` and an explicit,
    possibly-reversed `range` array (never a manually-descending domain) --
    Vega linear scales don't reliably honor a hand-reversed domain, which
    silently re-inverted the axis during development.
  - Each axes' outer Vega group is left unclipped; only a nested inner
    group holding the data marks is clipped. Clipping the outer group (the
    first version) cut away axis ticks/labels/titles and this axes' own
    title -- all Vega child marks drawn outside the plot rectangle by
    design, the same way `svg.py`'s tick/label `<g>` sits outside its
    separate clip-pathed zoom `<g>`. A plain single-axes figure with a
    title and axis labels rendered as a bare, unlabeled line before this
    fix -- about as central a case as this feature has.
  - **Pie charts rendered as nothing at all.** Vega's `pie` transform
    belongs on a *data* entry, not on the mark itself (marks have no
    `transform` property and silently ignore one there); the original
    version also left `startAngle` hardcoded to `0`, never set `endAngle`,
    and never gave the arc a radius or a real center. Every wedge was a
    zero-angle, zero-radius arc sitting at the group's local `(0, 0)`
    corner. Now built as a proper data transform, with center/radius
    computed the same way `svg.py`'s own `_render_pie` does.
  - **Marker and error-bar point sizes were missing the same points-to-pixels
    `dpi/72` conversion every other backend applies** (`svg.py`/`raster.py`
    always pass `size_scale=dpi/72.0` into `artist_to_prims()`) -- at the
    library's default `dpi=100`, markers exported roughly 28% smaller than
    the same figure's own SVG/PNG output. Compounding that, Vega's `symbol`
    `size` channel is pixel *area* (`radius = sqrt(size/pi)`), not diameter
    squared -- every circular marker was independently ~13% oversized in
    diameter (~27% in area) on top of the missing dpi scaling.
  - **A figure's exported Vega JSON was embedded straight into an inline
    `<script>` block via plain `json.dumps`**, skipping the
    `</script>`-escaping `Figure.to_html()`'s own payload already goes
    through (`_json_payload()`, in `plotpress/figure.py`) -- a title, axis
    label, or annotation containing the literal text `</script` would have
    truncated the generated Vega page's script block early.
  - **Bar and scatter marker edges (`edgecolor`/`linewidths`) were silently
    dropped** -- `svg.py` and `primitives.py`'s own `ScatterCollection`
    conversion both draw an outline when one is set; the dedicated
    `_bars_marks`/`_scatter_marks` encoders didn't.
  - A `fontsize=0` on a `Text`/`Annotation` (e.g. a deliberately hidden
    label) was silently promoted to `11` by an `or 11` fallback that
    couldn't tell "explicitly zero" from "not set".

  A further pass, checking every mark builder against `svg.py`'s renderer
  for the same artist field by field rather than only rendering and eyeballing
  the result, found and fixed several more real fidelity gaps -- again mostly
  invisible from the JSON alone, since Vega omits what it can't place rather
  than complaining:
  - **Draw order ignored `zorder`.** Artists were emitted in list order, not
    `svg.py`'s own `sorted(enumerate(ax.artists), key=lambda ka: (ka[1].zorder, ka[0]))`
    -- `ax.fill_between(..., zorder=1)` called after a `zorder=3` line
    painted over it instead of sitting behind it.
  - **Dashed lines (`linestyle="--"`/`":"`/`"-."`) always rendered solid.**
    None of `_line_marks` or the prim-reuse path's `Line`/`Segments`/`Path`
    marks read `linestyle` at all -- including `axhline`/`axvline`, whose
    default linestyle is dashed.
  - **A line with `NaN` values bridged the gap with a straight line instead
    of breaking there** (`ax.plot(x, y)` after `y[50:60] = np.nan`, the
    standard "missing data" idiom) -- `_line_marks` dropped every non-finite
    point outright rather than using Vega's own `defined` mark channel to
    split the line the way `svg.py`'s `_line_path_d` already does.
  - **`errorbar()`'s connecting line and its caps were both missing** --
    only the bare whiskers exported; `capsize`/`capthick` had no visible
    effect, and the line joining the points (drawn whenever
    `linestyle` isn't `"none"`) was absent entirely.
  - **`stem()`'s baseline -- the horizontal reference line the stems sit
    on -- was never drawn**, so `ax.stem(x, y, baseline=2)`'s whole point
    (what the stems are measured *from*) didn't show. The tip marker also
    used Vega's default size instead of the figure style's own marker size.
  - **Pie wedge labels and `autopct` percentages were dropped entirely** --
    `ax.pie(values, labels=[...], autopct="%.1f%%")` exported as an
    unlabeled disc.
  - **`ax.axis("off")` (and `ax.pie()`, which calls it internally) still
    got a full tick/grid frame** with auto-generated 0.0-1.0 labels no
    `to_svg()` output ever shows -- the "axes" array was built
    unconditionally, ignoring `_axis_off`. Custom tick positions/labels
    (`set_xticks`/`set_xticklabels`) and a non-default axes facecolor
    (`set_facecolor`) were similarly ignored in favor of Vega's own
    auto-generated ticks and a transparent background.
  - **`Text`/`Annotation` dropped vertical alignment, rotation, bold/italic,
    partial alpha, the `bbox=` background box, and -- for `annotate()` --
    the arrow entirely.** A label was always drawn horizontal, middle-
    baseline, fully opaque, with no box and no leader line to whatever it
    was meant to point at, regardless of what was actually passed.
  - **A figure's `suptitle()`/`supxlabel()`/`supylabel()`/`text()` and any
    legend (axes or figure-level) were silently absent, with no warning** --
    unlike every unsupported *axes-level* artist, which does warn. Now
    `suptitle`/`supxlabel`/`supylabel`/`text()` export as real marks (the
    same top-level, figure-pixel-space treatment as `Figure.group()`'s own
    boxes); a legend still isn't exported -- it needs real layout
    (`svg.py`'s `figure_legend_layout()`/`draw_legend()`) this module
    doesn't have yet -- but now warns, naming which axes (or the figure)
    has one, instead of vanishing quietly.
  - **A figure's primary content vanished entirely behind a `twinx()`/
    `twiny()`/secondary-axis overlay.** Every axes group painted its own
    opaque background fill unconditionally, but a twin/secondary axes
    occupies the *exact same* pixel rect as its parent (`twinx()`/`twiny()`/
    `secondary_xaxis()`/`secondary_yaxis()` all copy it verbatim) and is
    drawn *after* the parent in `fig.axes` order -- so its own blank
    background painted directly over the parent's already-drawn curve/bars.
    `svg.py` already skips this rect for exactly that reason ("twins/
    secondaries overlay their parent, so neither draws one"); this group
    now does too. Found by comparing this exporter's own output against
    `to_vega_lite()`'s (which merges a twin into its parent's view as an
    extra layer instead, and so never had this problem) on the same figure.

  Verified against every script in the `docs/examples` **and**
  `docs/applications` galleries this way: 298 figures across 286 scripts
  export and render correctly (axis chrome, pie wedges and labels, marker/bar
  edges, dashes, error-bar caps, annotation arrows, and every twin/secondary
  axes's own content all included), zero producing a blank or malformed
  render. 123 scripts warn about something -- a legend `to_vega()` doesn't
  export yet (the single most common gap, now that everything else in this
  list is fixed) or one of the named unsupported artist types -- the rest
  of each such figure still exports and renders correctly regardless.

  `Figure.group()`'s own labeled boxes are exported too, as a `rect`+`text`
  mark pair per group spanning the pixel rect of its member axes (plus any
  colorbar that belongs entirely to them) -- the same geometry `svg.py`'s
  `_render_groups` computes, reused directly rather than re-derived.

  Every plot-type reference example and real-application figure with
  supported content now links to a standalone page rendering its own
  `to_vega()` export live, via a real Vega engine in the browser, alongside
  the raw JSON spec -- `docs/conf.py`'s gallery scraper writes one self-
  contained HTML page per figure and links it from the generated example
  page, skipping figures with nothing a Vega export can show (an
  unsupported-artist-only figure, e.g. a lone `boxplot()`). `scale`/
  `live_streaming` are left out -- their point is file size/build time and
  the live-acquisition pattern, not plot-type coverage.

  The interactive toolbar (pan/zoom/pick) doesn't carry over -- a Vega
  runtime has its own interaction model, not plotpress's `_interactive.py`
  payload.

### Removed

- **3-D plotting is gone.** `plotpress/axes3d.py`/`Axes3D`, `projection="3d"`,
  `scatter3D`/`plot3D`/`plot_surface`/`plot_wireframe`/`view_init`/
  `set_zlabel`/`set_xlim3d`/`set_ylim3d`/`set_zlim3d`, the `examples/threed`
  gallery section, and every doc mention of 3-D are all removed. **Breaking
  change** for any code that plots on a `projection="3d"` axes.
  `add_axes`/`add_subplot(projection="3d")` now raises a clear
  `ValueError` naming the unsupported projection, matching every other
  out-of-scope case this library already rejects explicitly rather than
  silently degrading.

  This was never going to be competitive: plotpress is pure Python with no
  compiled extension, so its 3-D was always an orthographic-projection,
  painter's-algorithm approximation bolted onto the 2-D core -- no real
  depth buffer, no perspective, separate collections that could occlude
  wrongly where they interpenetrated -- a permanently weaker corner next to
  dedicated 3-D tools (Plotly's WebGL-backed 3-D, or even matplotlib's own
  `mplot3d` despite its similar, longstanding limitations), and a poor fit
  for what actually differentiates this library (SVG-first 2-D rendering,
  the interactive toolbar, broad matplotlib-shaped 2-D coverage).

  `plotpress.load_data()`'s `"layout"` can still report the literal `"3d"`
  string when reading back a file saved before this removal (it just reads
  back whatever was stored, unvalidated) -- `subplots_from_layout()` raises
  the same clear `ValueError` for that case, since it genuinely cannot
  rebuild an axes kind that no longer exists. Existing static output
  (`.svg`/`.png`/`.pdf`) already saved from a 3-D axes is unaffected --
  this only touches the ability to *create* new 3-D plots or *rebuild* one
  from a saved layout going forward.

### Changed

- **`pick_max_mesh_cells`'s default is raised from 60,000 to 250,000**
  (`Figure.to_html`/`save`/`show_in_jupyter`, `Report.save`) -- 60,000 was
  low enough that an entirely ordinary mesh (a few hundred by a few hundred
  cells -- 114,000 for one real example that prompted this) got silently
  block-averaged down for picking well before its file size became a real
  concern. 250,000 covers meshes like that at full resolution by default
  (~700 KiB embedded, in that example) while still bounding a genuinely
  huge one (a multi-million-cell mesh uncapped can reach double-digit MiB
  of embedded pick JSON alone -- the exact "no browser will open this"
  problem the raster mesh path exists to avoid, just for pick data instead
  of SVG geometry).

- **A mesh/contour over `pick_max_mesh_cells` now warns, once per figure
  with every affected axes named, instead of silently degrading.** A
  downsampled cell's z reads as the *mean* of the original cells folded
  into it, not the exact value at the point clicked, and that cell's own
  x/y coarsens the same way -- real, silent precision loss, not just a
  coarser click radius, and with no visual hint of it since the rendered
  image itself is never downsampled (only the pick payload is). The
  `UserWarning` names each affected axes' index/title and its shape before
  and after (`axes 0 ('deficit'): 300x380 (114,000 cells) -> 150x190
  (28,500 cells)`), and says how to raise the cap. An animated
  (`plot_frames`/`pcolormesh_frames`) mesh warns once per mesh, not once
  per frame, even though every frame's own z needs downsampling
  separately.

### Added

- **`plotpress.select_panel(ds, title=...)`** (or `row=`/`col=`) pulls one
  panel out of a `load_data_xarray()` grid, dropping `row`/`col` entirely --
  a mesh panel's `z` comes back `(y, x)` instead of `(row, col, y, x)`, a
  line panel's `y` comes back `(point,)`, and `title`/`xlabel`/`ylabel`/
  `has_data` become plain scalar attributes of that one panel. Previously
  this needed knowing the `ds.where(ds["title"] == ..., drop=True)
  .squeeze(("row", "col"))` idiom by hand, with no built-in check for a
  title that matches zero or more than one panel. `multiple=True` returns
  every panel sharing a duplicated `title` as a `list` instead of raising
  -- and always a `list`, even for a unique `title` or an explicit
  `row=`/`col=`, so a caller that loops over the result never has to
  branch on how many panels actually matched.

- **`load_data_xarray()` now handles a grid with missing panels**, instead
  of refusing the whole figure the moment one grid cell had no axes, or an
  axes with nothing plotted on it. A missing panel comes back NaN (its own
  `x`/`y` too, in the per-panel-coordinate case) with the new `has_data`
  `(row, col)` coordinate `False` for it -- distinguishing "this panel is
  genuinely empty" from "this panel's real data legitimately happened to be
  all-NaN", which just checking for NaN can't tell apart.

- **`load_data_xarray()`'s returned `Dataset` now also carries the full
  layout dict** (the same one `load_data()` returns under `"layout"`) as
  `ds.attrs["layout"]`, ready to hand straight to `subplots_from_layout()`.
  Previously, getting both the `Dataset` *and* the layout needed a second,
  separate `load_data()` call -- a second parse of the same file just to
  get a dict `load_data_xarray()` had already read internally and thrown
  away.

- **The interactive toolbar is now a single full-width menu bar**, replacing
  the old floating two-row button cluster. **Pan/Zoom** and **Home** (the
  renamed Figure Navigator/Reset Figure) sit standalone at the far left
  (reached for often enough to skip a menu's extra click); everything else
  groups into four menus by scope -- **Axes** (Axis Span, Axis Zoom, Reset
  All Axes), **Point Picking** (the tool, Hide Points, Clear Points,
  Extract), **Annotate** (the tool, Hide Annotations, Clear Annotations),
  and **File** (Save, Save As) -- plus a persistent indicator naming the
  current tool, pinned to the bar's far right. The old single "Hide All"
  toggle is now two independent ones, Hide Points and Hide Annotations, each
  scoped to its own menu. A menu item that selects a tool is checkable: a
  single click selects it and leaves the menu open (so switching tools
  doesn't need reopening it), double-click deselects -- so does Escape, from
  anywhere, which also still clears every pin/annotation the way it always
  has (a keyboard-only user has no double-click to deselect a tool with
  otherwise). A caller's own `plotpressAddTool()` tools now land in a fifth
  **Custom** menu instead of their own extra row. The collapse toggle
  (`▸`/`◂`) is gone -- there's no longer a second row to hide. Still
  `position:fixed`, pinned to the top of the window regardless of
  scrolling, panning, or Pan/Zoom's own whole-figure zoom -- an in-flow and
  a `position:sticky` variant were both tried during development and
  dropped, the former because it scrolled away with an oversized figure,
  the latter because it didn't reliably track a dynamically-resized
  ancestor's bounds across browsers. `docs/user_guide/interactivity.rst`
  and every screenshot/example are updated for the new layout.

- **`Extract` now returns Point Picking pins only, not Annotation notes.**
  Extract lives solely under the Point Picking menu now (see above), and an
  Annotation note has nothing to "extract" in the same sense a picked data
  value does -- so its CSV/JSON output, the native-window (`pywebview`)
  handoff, and `Figure.show(wait_for_extract=True)`'s return value are all
  narrower than before for a figure that has both kinds of marker.
  `window.plotpressGetMarkers()` is unaffected -- it stays the general
  "every pin and annotation" query that `plotpress.qt`'s live embedding and
  a custom tool's own logging already relied on.

- **A batch of previously-missing matplotlib kwargs**, found by the same
  API audit as the Fixed entry below: `boxplot(vert=, labels=,
  tick_labels=, showmeans=)`, `violinplot(vert=, showmeans=,
  showmedians=)`, `bar`/`barh(align="edge")`, `hist(orientation=
  "horizontal")` (both `histtype="bar"` and `"step"`/`"stepfilled"`),
  `fill_between`/`fill_betweenx(where=)` (splits into one artist per
  contiguous `True` run -- returns a list instead of a single artist when
  given), `imshow(aspect=)`, and `legend(bbox_to_anchor=)` (places the
  `loc` corner of the legend box at an exact axes-fraction point instead
  of inset within the axes -- the usual way to put a legend outside the
  plot entirely; implemented in both the SVG and raster backends).

- **`Figure.show_in_jupyter()`**, a new optional (`pip install
  plotpress[jupyter]`) way to display the full interactive toolbar inline in
  a notebook cell -- `fig` alone only ever renders static SVG (there's
  deliberately no `_repr_html_`: Jupyter prefers `text/html` over
  `image/svg+xml`, and a full interactive HTML document dropped into an
  output cell that way renders messily and its `<script>` doesn't run
  regardless). `show_in_jupyter()` instead wraps `to_html()`'s
  self-contained output in an `IPython.display.HTML` iframe, which does
  isolate and run the inlined JS, so pan/zoom, point-picking, and the rest
  of the toolbar all work exactly as they do in a saved `.html` file.
  `width`/`height` default to the figure's own pixel size and can be
  overridden. Documented with a worked example on the interactive-figures
  page (`docs/user_guide/interactivity.rst`).

- **`plotpress.load_data_xarray()`**, a new optional (`pip install
  plotpress[xarray]`) way to read a saved figure's data back as a single
  labeled `xarray.Dataset`, dimensioned by the figure's own `row`/`col`
  axes grid, instead of `load_data()`'s title-keyed dict of dicts -- the
  natural fit for the uniform-grid-of-same-shaped-measurements case this
  gallery already showcases (every panel its own `pcolormesh`, or its own
  single line series): the whole grid comes back as one `z`/`y` array
  ready for a bulk reduction across every panel at once, each panel's own
  title/labels riding along as `(row, col)` coordinates, with no
  panel-by-panel loop and no title to collide on (xarray indexes by
  row/column position, never by name). Raises a clear `ValueError` naming
  exactly what didn't fit for anything outside that scope -- a row/column
  span, a mix of mesh and line panels, multiple series on one axes,
  mismatched shapes -- pointing at `load_data()` as the fallback. New
  examples covering both supported panel kinds, each loading the saved
  grid back, running a bulk xarray analysis across every panel at once
  (a per-panel deviation-from-grid-mean / mean-centering), picturing that
  same transformation on one panel as an explicit before/after pair joined
  by an arrow, and replotting the whole analyzed grid straight from the
  `Dataset`:
  `docs/examples/data_roundtrip/plot_05_reload_as_xarray.py` (mesh grid)
  and `plot_06_reload_line_grid_as_xarray.py` (line-series grid).

- **Text selection is now disabled while any toolbar mode is active**, not
  just Pan/Zoom -- every mode's own drag (Axis Span/Zoom across
  tick labels and titles, Point Picking/Annotation dragging a pin's own
  label box across other pins' text) could highlight text underneath it
  the same way Pan/Zoom's whole-figure pan always could.
- **A Point Picking pin's (and an Annotation note's) label box is now
  draggable**, independent of the dot/anchor it belongs to: grab the box
  itself (not the dot) while the mode that created that kind of pin is
  active, and a thin leader arrow (pointing at the dot's own edge) keeps
  the two connected wherever the box ends up. A dragged position survives
  every later pan/zoom/arrow-key step and a Save/Save As round trip, the
  same as everything else about a pin. A plain Point Picking pin drags
  under Point Picking mode; an Annotation note (including a legacy
  "Annotate Point" pin restored from an older saved file) drags under
  Annotation mode -- the same split `Clear Points`/`Clear Annotations`
  already use.

- **Figure layout export/import**, so recovered data can be replotted into
  a figure structurally identical to the one it came from: every interactive
  HTML now also embeds a `plotpress-layout` payload (grid shape/position of
  each subplot-grid axes, plus any `Figure.group()` boxes), surfaced through
  `load_data()`'s new `"layout"` return key. `plotpress.subplots_from_layout()`
  reads that back into a fresh `(fig, axes)` -- squeezed the same way
  `plotpress.subplots()` itself would (bare `Axes`, 1-D, or 2-D array) for a
  plain uniform grid, falling back to a flat list for row/column spans --
  and re-applies every recorded group. New example:
  `docs/examples/data_roundtrip/plot_03_reload_preserving_groups.py`;
  `plot_01_reload_mesh_grid_as_lines.py`/`plot_02_reload_and_fft_mesh_grid.py`
  no longer hand-hardcode the destination grid shape, now reading it back
  via `subplots_from_layout()` instead.

- **The exported layout now carries every axes' own decorations, not just
  its grid position** -- title (and its own fontsize), x/y labels,
  explicit limits, scale, grid, aspect/box aspect, an inverted axis, a
  per-axes facecolor, and legend settings, plus the figure's own
  `suptitle()`/`supxlabel()`/`supylabel()` and background color.
  `subplots_from_layout()` re-applies all of it automatically (everything
  except the legend, which needs already-plotted, labeled artists to draw
  from -- call `ax.legend(**layout["axes"][i]["legend"])` yourself once
  you've replotted into it), so a caller never has to already know what
  titles or labels to re-add. A figure rebuilt this way and replotted with
  its recovered data now renders **byte-identical SVG** to the source
  figure -- enforced by
  `test_reconstructed_figure_renders_byte_identical_svg_to_the_original`.
  Colorbars, `tick_params()`/explicit tick overrides, twin/secondary/inset
  axes, and a custom `Style` are documented, deliberate gaps, not
  oversights -- see `subplots_from_layout()`'s own docstring. New example:
  `docs/examples/data_roundtrip/plot_04_full_decoration_round_trip.py`;
  the three existing reload examples no longer hand-call `set_title()` on
  the reload side either, now that it comes back on its own.

- **A matplotlib `Axes` API audit, closing every gap found except three
  that are genuinely multi-day subsystems on their own** (datetime axis
  support, `streamplot`, and the `tricontour`/`tricontourf`/`tripcolor`/
  `triplot` triangulation family -- left as deliberate follow-ups, not
  oversights):
  - Getters with no previous read-back: `get_aspect`, `get_xbound`/
    `get_ybound` (always sorted low-high, unlike `get_xlim`/`get_ylim`,
    which preserve direction), `get_xticklabels`/`get_yticklabels`,
    `xaxis_inverted`/`yaxis_inverted`, `get_autoscalex_on`/
    `get_autoscaley_on`.
  - `ax.set(**kwargs)` -- matplotlib's bulk setter, dispatching each
    keyword to this axes' own `set_<name>()`; raises naming every
    unrecognized keyword at once, not just the first.
  - `set_box_aspect()`/`get_box_aspect()` -- a fixed physical height/width
    ratio for the drawn box, independent of the data range entirely
    (unlike `set_aspect`, which shrinks to keep one data unit equal in x
    and y).
  - `set_xticks(ticks, minor=True)`/`set_yticks(..., minor=True)` --
    explicit minor-tick positions, previously only reachable via the
    all-or-nothing `minorticks_on()`. Reaches the per-axes interactive
    metadata too, so it survives a client-side zoom rebuild instead of
    reverting to the auto minor-tick algorithm (the same regression class
    already fixed once for `tick_params()` and once for `grid(alpha=)`).
  - `get_legend()`/`get_legend_handles_labels()`, and `legend()` now
    returns a `Legend` handle (`set_visible`/`get_visible`/`remove`/
    `set_title`/`get_title`/`get_texts`) for repositioning or hiding a
    legend after the fact without a full `legend(...)` call.
  - `pcolor()` -- a true alias of `pcolormesh` (matplotlib itself now
    recommends `pcolormesh`; kept only so matplotlib-written code still
    runs unchanged).
  - `arrow(x, y, dx, dy)` -- a single arrow in data coordinates throughout
    (a thin wrapper over `quiver` with one vector and no auto-scaling).
  - `quiverkey(Q, X, Y, U, label)` -- a reference-length arrow + label for
    a `quiver()` field, `coordinates="axes"` by default.
  - `indicate_inset(bounds)`/`indicate_inset_zoom(inset_ax)` -- a marker
    rectangle for the region an `inset_axes()` zooms into (matplotlib's
    own connector lines from the rectangle to the inset's corners aren't
    drawn -- those cross from one axes' clipped drawing area into
    another's, a figure-level connection this library has no artist for
    yet).
  - `bar_label(bars)` -- auto-labels each bar in a `bar()`/`barh()` result
    with its own height/width, just outside the tip.
  - `clabel(CS)` -- labels a `contour()` result's lines with each level's
    value (one label per level, at the middle of its longest run of
    segments, not one per disconnected island the way matplotlib does).
  - `table(cellText, ...)` -- a grid of text cells, positioned in
    axes-fraction space the same way `text()`'s `transform=ax.transAxes`
    is (stays put under a later pan/zoom; `loc=` only reaches positions
    *inside* the axes box, unlike matplotlib's own outside-the-axes
    placements like the default `loc="bottom"`).
  - `barbs(X, Y, U, V)` -- wind barbs: a fixed-length shaft per point,
    with flags/full/half ticks near the tip encoding `hypot(U, V)` by the
    usual meteorological convention.
- **`ax.text()`/`ax.annotate()`: multi-line text, `fontweight=`/`fontstyle=`,
  and `transform=ax.transAxes`.** Fixed a real bug found along the way: a
  `\n` embedded in a label's string was never actually rendered as a line
  break -- SVG treats a raw newline inside `<text>` content as ordinary
  whitespace, so a multi-line label silently ran together onto one line, even
  though the existing `bbox=`/leader-anchor math already measured it as if it
  were multiple lines. Each line is now its own `<tspan>` (raster's
  `ImageDraw.text` already handled `\n` correctly on its own), independently
  aligned per `ha`, with the block as a whole placed per `va`.
  `fontweight="bold"`/`fontstyle="italic"` (or any matplotlib weight name/
  number -- `>= 600` counts as bold) select the glyph face on both backends;
  raster has no italic font file in its bundled/installed registry, so it
  fakes the slant with a shear instead. `transform=ax.transAxes` places
  `(x, y)` (or `annotate()`'s `xytext`, via `textcoords=ax.transAxes`) as an
  axes-fraction position -- `(0, 0)` bottom-left, `(1, 1)` top-right --
  instead of data coordinates, rendered outside the per-axes interactive zoom
  group so a label like `ax.text(0.95, 0.95, ..., transform=ax.transAxes)`
  stays pinned to a corner under autoscaling, panning, or a data zoom rather
  than needing recomputing whenever the axis limits change.
- **The interactive toolbar's Hide Annotations toggle now also hides every
  boxed `ax.text()`/`ax.annotate(bbox=...)` callout**, not just interactive
  Point Pick/Annotate pins -- a figure-drawn callout reads as the same kind
  of annotation on screen. A plain, unboxed label is not a callout and stays
  visible either way. New gallery example
  `plot_19_grid_of_meshes_with_corner_labels.py`: a 4x4 `pcolormesh` grid
  where each panel is self-labeled in its own top-right corner via
  `transform=ax.transAxes`, all sixteen toggled by one click of Hide
  Annotations.
- **`alpha=` on every method matplotlib supports it for.** A full sweep
  found 17 gaps: `pie`, `boxplot`, `violinplot`, `eventplot`, `quiver`,
  `contour` (its own sibling `contourf` already had it), `hexbin`,
  `matshow`/`spy`/`hist2d` (all imshow-based, imshow already had it),
  `ecdfplot` and the whole `psd`/`csd`/`cohere`/`magnitude_spectrum`/
  `angle_spectrum`/`phase_spectrum`/`specgram`/`xcorr`/`acorr` family (all
  built on `plot`/`vlines`/`imshow`, which already had it), plus `text()`/
  `annotate()` (fading the glyphs, independent of the existing `outline`
  halo) and `annotate(arrowprops={"alpha": ...})` (the arrow, independent of
  the text). `violinplot`'s default is `0.55`, the fill both backends
  already drew before it was configurable; every other new default is
  `1.0`, so nothing already drawn changes appearance.
- **`Spine.set_alpha()`**/**`get_alpha()`**, and **`ax.grid(alpha=)`** --
  a per-axes override of the figure `Style`'s `grid_alpha` default, using
  the same "`None` inherits" convention as `Spine`'s own color/linewidth.
  The override reaches the embedded per-axes interactive metadata too, so
  it survives a client-side pan/zoom rebuild rather than reverting to the
  figure default the way the `tick_params()` regression this same pattern
  already fixed once did.
- **`framealpha=` on `Axes.legend()`/`Figure.legend()`** (default `0.85`,
  matching what the box already drew). Fixed a real backend-parity bug in
  the process: the raster (PNG/PDF) legend box was always fully opaque
  regardless of the SVG box's own `fill-opacity="0.85"` -- the two backends
  drew a visibly different legend for the same figure.
- **`bbox=` on `text()`/`annotate()`/`Figure.text()`.** A filled/bordered
  box behind the label -- matplotlib's own `bbox=` dict, a subset of its
  keys (`facecolor`/`fc`, `edgecolor`/`ec`, `alpha`, `pad`, `boxstyle` of
  `"square"`/`"round"`, `linewidth`). Different from the existing `outline`
  halo: `outline` keeps a label legible over whatever it lands on, `bbox`
  reads as a callout chip. With `annotate()`, the arrow leader now attaches
  to the box's own padded edge rather than the bare text's tighter bounds,
  so it visibly touches the box instead of stopping short of it.
- Three new gallery examples: `docs/examples/axes_features/plot_16_alpha_
  everywhere.py` (quiver over contourf, two boxplots at one position,
  hexbin over a scatter sample), `plot_17_text_bbox.py`, and
  `plot_18_text_features.py` (multi-line, bold/italic, `transform=
  ax.transAxes`).

### Fixed

- **Point Picking no longer lets a line/scatter point "steal" a click plainly
  aimed at a mesh cell behind it.** A short line drawn over or near a
  `pcolormesh` (a threshold marker, a turbine rotor disc, a boundary trace)
  used to win any click within the generous 28px snap-to-point radius of one
  of its own vertices, even when the click landed squarely inside a mesh
  cell well away from the line itself -- the resolver had no notion that a
  mesh cell under the cursor was also a candidate, let alone a stronger
  positional signal than a loose point-distance threshold. A click inside a
  mesh cell now only loses to a line/scatter point on a genuinely precise
  click (within 10px); a precise click still always wins, so nothing that
  depended on that continues to work exactly as before. That 10px radius
  (and the original 28px one) is now also converted to a real, constant
  screen-pixel distance rather than compared directly in root SVG
  user-space units -- those units stop meaning a fixed number of screen
  pixels the moment Pan/Zoom magnifies the whole figure (its viewBox stays
  fixed while the rendered SVG grows), so at any real magnification the old
  raw-unit comparison silently let both radii balloon to many dozens of
  actual screen pixels, reproducing the same steal-the-click bug at a
  farther and farther visual distance the more a reader zoomed in to
  target a specific cell precisely.

- **A found-while-auditing-the-new-toolbar bug: the menu bar's mode
  indicator could sit flush against, or partly behind, the window's right
  edge.** `.plotpress-menubar` is `position:fixed; width:100%; padding:5px
  8px` without `box-sizing:border-box`, so the 16px of horizontal padding
  was added on top of the 100% width instead of being absorbed by it,
  pushing the bar's own right edge (and the indicator pinned to it) 16px
  past the scrollbar-safe viewport width.

- **Another found-while-auditing bug: a Point Picking pin could drift off
  its true constant on-screen size across a Pan/Zoom.** The baseline
  `naturalW`/`naturalH` a pin's zoom compensation scales from were measured
  before the toolbar's own docked-menu-bar DOM restructuring ran later in
  the same script, capturing the SVG's stale pre-reflow size instead of its
  real final one.

- **An API audit ("try to break every matplotlib-shaped plot type") found
  and fixed two silent-corruption bugs, six empty-input crashes, an
  SVG-only color-resolution gap, and added a batch of previously-missing
  matplotlib kwargs.** Full detail:

  - **`plot(x, y, fmt)` silently dropped matplotlib's format-string
    shorthand.** `ax.plot(x, y, 'ro-')` rendered with the default color, no
    marker, and no error -- the third positional argument was never read
    at all. `plot()` now parses it (`_parse_fmt`): any combination of one
    color, one linestyle, and one marker, in any order, matching
    matplotlib's own mini-language for the common cases. An explicit
    `color=`/`linestyle=`/`marker=` keyword still overrides whatever `fmt`
    says for that piece; an unparseable `fmt` raises `ValueError` naming
    the leftover characters rather than guessing.
  - **`errorbar()`'s 5th positional argument silently corrupted `color`.**
    matplotlib's own signature is `errorbar(x, y, yerr, xerr, fmt, ...)`;
    plotpress's was `errorbar(x, y, yerr, xerr, color, ...)` -- the exact
    same slot, different meaning. `ax.errorbar(x, y, yerr, xerr, 'o')`, an
    entirely idiomatic matplotlib call, silently set `color='o'` and
    rendered `stroke="o"` into the SVG -- an invalid value no browser
    recognizes -- with no error anywhere in the pipeline. `errorbar()` now
    takes `fmt` in that same 5th slot and parses it the same way `plot()`
    does; `color`/`marker`/`linestyle` moved later in the signature (still
    fully keyword-compatible) and each still overrides `fmt` if given
    explicitly.
  - **matplotlib's single-letter color shortcuts (`'r'`, `'k'`, `'b'`, ...)
    silently didn't render in SVG output**, plotpress's default and
    SVG-first format -- unlike a full name (`"red"`), a bare letter isn't a
    valid CSS/SVG color keyword on its own, so passed straight through to
    `stroke=`/`fill=` it rendered as nothing a browser recognizes. The
    raster backend already resolved every color through
    `colors.to_hex()`; SVG never did. `Axes._resolve_color()` -- already
    the chokepoint nearly every plotting method's own `color=` routes
    through -- now resolves through `to_hex()` too, closing this for every
    such method at once; `edgecolor=`/`ecolor=`-style secondary colors
    (`bar`/`barh`/`hist`/`fill`/`fill_between`/`fill_betweenx`),
    `pie(colors=)`, `contour(colors=)`, `axvspan`/`axhspan`,
    `text`/`annotate` (including `annotate(arrowprops={"color": ...})`),
    and `Spine.set_color()`/`Axes.set_facecolor()` were fixed at their own
    call sites the same way.
  - **`bar`/`barh`/`fill_between`/`fill_betweenx`/`stackplot`/`errorbar`/
    `stem`/`eventplot`/`quiver` crashed on empty input** (`ax.bar([],
    [])`, etc.) with a raw, unhelpful numpy `ValueError`/`IndexError`
    deferred all the way to `fig.to_svg()`/`.save()` -- far from the
    actual call that caused it -- instead of drawing nothing, the way
    `plot([], [])`/`scatter([], [])`/`hist([])` already did. The fix
    pattern already existed in the codebase and just hadn't been
    propagated: `Polygon.data_bounds()` already guarded the empty case;
    the other artists' `data_bounds()` (plus `Stem`'s own SVG/raster
    renderer and `eventplot()`/`quiver()`'s own call-time auto-scaling,
    which had the same gap one level up) now do too.

- **`load_data()` silently lost data when two axes (or two `Report`
  entries) shared the same title.** The title-keyed dict this defaults to
  had no collision handling at all -- a later axes/figure with an
  identical title simply overwrote (and lost) an earlier one, so
  `load_data()`'s return dict could come back with fewer entries than the
  figure actually had, with nothing to signal it happened. A collision is
  now disambiguated with a `" (2)"`, `" (3)"`, ... suffix instead, with a
  `UserWarning` naming every one resolved -- every axes/figure stays
  recoverable, and `by_index=True` remains the fully collision-proof
  escape hatch it already was.

- **A multi-agent audit of the toolbar reorganization and the new layout
  export/import feature (see Added above) turned up and fixed six real
  bugs**, plus two documented-but-untested behavior boundaries and a set of
  stale doc/comment references now covered by new tests and examples:
  - `linestyle="none"` (matplotlib's "markers only" idiom) silently drew a
    solid connecting line in `plot()`/`axvline()`/`axhline()`/`axline()`/
    `hlines()`/`vlines()` -- only `errorbar()`'s own renderer skipped the
    line for `"none"`. Fixed once, centrally, in `primitives.py`'s
    `artist_to_prims()` (and mirrored for `plot_frames()`'s separate legacy
    renderer in both backends) rather than patched per call site.
  - `Figure.group(pad=<numpy scalar>)` (e.g. `np.int64`, `np.float32`) raised
    `TypeError: '...' object is not iterable` -- a regression from the
    plain `float(pad)` coercion `pad`'s single-number case used before this
    release's `(left, right, top, bottom)` tuple support. `_normalize_pad()`
    now duck-types on `float(pad)` succeeding instead of an `isinstance`
    check only genuine Python `int`/`float` passed.
  - `Figure.group(linestyle=<invalid>)`'s "not a recognized style" warning
    pointed at a useless location (not the caller's own `group()` line) --
    `normalize_linestyle()`'s `stacklevel` is now a parameter, since
    `group()` calls it two frames from user code, not three like every
    `Axes` plotting method.
  - `plotpress.subplots_from_layout()` silently dropped any axes placed with
    a freeform `Figure.add_axes()` rect (no subplot grid cell to recover) --
    it now warns, naming which axes indices won't come back.
  - The Annotation tool's `window.prompt()` call, uncaught, could surface as
    a JS error on every click in an embedding that blocks it (a `Report`
    entry's `<iframe srcdoc=...>` has an opaque origin, which browsers
    silently block `alert`/`confirm`/`prompt` from) -- now caught, so it
    degrades to the same no-op a cancelled prompt already was.
  - `layout_metadata()` rebuilt the same `id(axes) -> index` map
    `axes_metadata()` already builds, once per interactive save -- both now
    accept a shared one instead of independently recomputing it.
  - New tests cover all of the above, plus the previously-untested
    boundaries that Home and Reset All Axes leave every pin/annotation
    untouched (only Clear Points/Clear Annotations/Escape do) and that a
    pre-removal "Annotate Point" pin restores correctly from an older saved
    file; stale "Point Pick"/"Annotate Point"/"Annotate Free" references
    left over from this release's renames were swept from `README.md`,
    `plotpress/qt.py`, `plotpress/figure.py`, and the `examples/` scripts.
    New example: `docs/examples/pairwise/plot_15_linestyles.py` now also
    demonstrates `linestyle="none"`.
- **A follow-up re-audit of the fixes directly above caught four more real
  issues** (three left by the fixes themselves, one a genuine regression in
  one of them), all now covered by new tests:
  - `Figure.group(linestyle="none")` still drew a solid box border -- the
    exact bug class just fixed everywhere else, left open on the one artist
    (`Figure.group`'s own box) whose `normalize_linestyle()` call site the
    prior fix pass happened to edit for its `stacklevel` without touching
    its rendering.
  - `_normalize_pad("5")` (a numeric-looking *string*) silently succeeded
    as `(5.0, 5.0, 5.0, 5.0)` instead of raising -- a real regression from
    duck-typing on `float(pad)` succeeding, since `float()` accepts strings
    too; strings are now rejected explicitly before the duck-typing check.
  - `subplots_from_layout()`'s `omitted_axes` warning said *an* axes was
    dropped but never named which `Figure.group()` box that broke -- a
    group spanning a freeform `add_axes()` axes and a grid-placed one lost
    the freeform member with no group-specific signal. A new warning names
    the group and how many of its original members came back.
  - The Annotation tool's blocked-`window.prompt()` catch (above) degraded
    to a totally silent no-op, indistinguishable from a user cancelling --
    it now also `console.warn`s once, so a developer debugging "Annotation
    does nothing here" has a lead.
- **`pie()` distorted into a rectangle under a per-axes interactive data
  zoom**, found while auditing the text counter-scale fix below for the
  same class of bug: a pie has no data-space geometry at all -- it draws
  in axes-*pixel* space specifically so it stays circular regardless of
  xlim/ylim -- but rendered inside the zoom group anyway, so a data zoom's
  `matrix(sx,sy,...)` transform (a non-square zoom box especially, giving
  unequal `sx`/`sy`) stretched the whole pie, wedges and labels together,
  instead of leaving it alone. Moved outside the zoom group entirely, the
  same as `table()`/`transform=ax.transAxes` text (its own rendering logic
  needed no change at all, since it already only ever read the axes' fixed
  pixel rect, never anything data-dependent).
- **A data-anchored `ax.text()`/`ax.annotate()` label's glyphs (and its
  `bbox=`, if any) stretched under a per-axes interactive data zoom**,
  found auditing the marker-scaling fix above for the same regression
  class: the label sat directly inside the zoom group a data zoom's
  `matrix(sx,sy,...)` transform scales, so a normal-size label at rest
  could render many times its own font size after zooming into a small
  region, or shrink to unreadable after zooming out -- the same bug as the
  marker one, but the opposite fix. A marker's size represents a footprint
  *on* the data, so it should scale with the axis; a label exists to be
  read, so it needs to stay a constant screen size, the way a title, tick
  label, or point-pick pin already does. Fixed by wrapping the label (and
  its `bbox=`) in a `plotpress-cscale` group the client JS counter-scales
  on every zoom -- the same live-recomputation approach pins already use,
  since a bare CSS trick can't cancel a transform that has not happened
  yet at render time. `annotate()`'s arrow is deliberately left outside
  that group (its own geometry should keep tracking the data point it
  points at), so after a large zoom its leader can end up not quite
  touching the now constant-size label -- a minor, accepted cosmetic gap
  next to the alternative of an illegible or gigantic label.
- **Every stroke-only line in the raster (PNG/PDF) backend ignored
  `alpha` entirely**, discovered while testing the sweep above: `plot()`,
  `step()` (and so `ecdfplot()`), `hlines`/`vlines`/`axhline`/`axvline`/
  `axline` (and so `xcorr()`) all carried their alpha into the shared
  `Path`/`Line`/`Segments` primitives (SVG already read it), but
  `raster.py`'s drawing code for each read only the plain color, silently
  dropping the opacity. `plot(alpha=0.3)` and the like have never actually
  been translucent in a PNG or PDF export before this fix, only in SVG/HTML.
- **A large marker (`scatter(s=...)`, `plot(markersize=...)`) stayed a
  constant screen-pixel size across a per-axes rubber-band zoom**, the same
  `vector-effect:non-scaling-stroke` rule that correctly keeps *line* stroke
  width constant under that zoom. A marker's size represents a footprint on
  the data, not a decorative stroke width, so it should scale with the axis
  the way the data itself does -- left as-is, a marker sized for the full
  view stayed exactly that many pixels after zooming into a small region and
  could swallow the entire (now much smaller) visible axis. Marker dots are
  now tagged `plotpress-marker` and excluded from that rule, so they grow or
  shrink with a per-axes zoom; line strokes and point-pick pins are
  unaffected (pins already had their own separate constant-size mechanism).
  Note this means a non-square zoom box (different x/y zoom factors) now
  stretches a marker into an ellipse along with the data, the same way a
  data-space shape would.

### Fixed

- **`pcolormesh(rasterized=)` follow-up fixes**, found by an audit of 0.11.0:
  - `rasterized=False` on a *curvilinear* grid silently rasterized anyway
    with no warning -- it now warns that vector cells aren't available for a
    curvilinear grid (there's no axis-aligned rect for a warped cell), rather
    than quietly ignoring the request the same way losing a cell to the
    raster path does.
  - The dropped-cell warning's suggested fix always called `rasterized=False`
    "cheap" -- true only when the mesh triggered the warning via an explicit
    `rasterized=True` override on a small grid, not when auto mode rasterized
    because the mesh was already past the vector cell-count threshold (the
    more common way to see this warning). The message now says which case
    applies instead of giving advice that immediately trips the *other* new
    warning.
  - A `pcolormesh(label=...)` legend entry's click-to-hide toggle worked only
    when the mesh happened to render as vector -- a raster mesh's `<image>`
    carried no `class`/`data-label` for the toggle to match on at all (this
    predates `rasterized=`; vectorizing a mesh was the first time any mesh
    got that wrapper). Both `imshow()` and `pcolormesh()` now emit it either
    way.
  - `_dropped_indices`' docstring claimed it "reuses the exact... lookup"
    `QuadMesh._rgba_rectilinear` performs; it was actually an independent
    reimplementation of the same formula that could silently drift out of
    sync. Both now call one shared `_resample_axis_index` helper, so they
    provably can't disagree.
  - The vector-mesh size warning's "will emit N `<rect>` elements" could
    overstate a NaN-heavy mesh's real output, since NaN cells are skipped;
    now says "up to N".
  - `FrameQuadMesh` was missing the `.n_cells`/`.uniform_grid` attributes
    `QuadMesh` carries, a latent `AttributeError` waiting for any code that
    reads them generically across both mesh types.
  - The returned mesh's `.rasterized`/`.vectorized`/`.n_cells`/`.dropped_x`/
    `.dropped_y` attributes, and the PNG-export caveat, are now documented
    in `pcolormesh()`'s own docstring instead of being discoverable only by
    reading source.
  - `_render_mesh_vector` now batch-formats coordinates and colors with
    vectorized `numpy.char` calls (the same approach `_seg_to_path` uses for
    a large line's path string) instead of one Python format call per cell.

### Added

- **`pcolormesh(..., rasterized=None)`.** A non-uniform rectilinear grid used
  to always resample into the SVG's one embedded raster image, which can
  drop a cell entirely once it's narrower than one output pixel (see
  `docs/examples/limitations/plot_04_pcolormesh_vs_imshow.py`). Auto mode
  (`None`, the default) now draws a non-uniform grid under ~2000 cells as
  exact vector `<rect>` elements instead -- no resampling, so no cell can
  ever be too thin to draw -- and falls back to the raster path above that,
  the same tradeoff `docs/scale/plot_09_output_scaling.py` already documents
  for keeping mesh file size independent of cell count. `True`/`False`
  override the automatic choice outright. Either way, if the raster path
  ends up dropping a cell, a warning now names it (`cell N (x=a..b) ...`)
  instead of it vanishing silently; forcing vector past the cell-count
  threshold warns about the SVG size instead. A uniform grid is unaffected
  either way -- its raster path was already a lossless, byte-identical copy.
  `pcolormesh_frames()` gets the dropped-cell warning too, but not the
  `rasterized` kwarg itself: its interactive slider swaps one embedded image
  per frame, and animating per-cell vector geometry would need far heavier
  client-side JS for the same reason a mesh frame already costs more than a
  line frame (see `docs/scale/limitations/plot_05_slider_frame_cost.py`).

### Added

- `hist()` gains `histtype="bar"|"step"|"stepfilled"`, `cumulative`,
  `weights`, `stacked` -- `data` may now be a single array or a sequence of
  arrays, sharing one set of bins, overlaid by default or `stacked=True`
  bottom-to-top.
- `boxplot()` gains `whis` (whisker reach in IQRs past q1/q3, matplotlib's
  own default `1.5`) and `showfliers` (drop the outlier circles instead of
  drawing them).
- `errorbar()` gains `ecolor`/`elinewidth`/`capthick` -- the whiskers/caps
  can now be styled independently of the connecting line and marker (each
  falls back to `color`/`linewidth` if not given; `capthick` falls back to
  `elinewidth` in turn). The whisker/cap width was previously hardcoded to
  1px regardless of `linewidth` in both backends.
- `imshow()` gains `interpolation="nearest"|...` -- `"nearest"` (default)
  keeps the existing crisp-pixel SVG rendering at any scale; anything else
  lets the browser smooth it. SVG-only: raster output already samples at
  its own fixed resolution.
- `pcolormesh()` gains `alpha`/`label`, matching `imshow()` -- its own
  animated sibling `pcolormesh_frames()` already had both; this one hadn't
  caught up.
- `scatter()` gains `edgecolors`/`linewidths` -- outlines every marker in
  the call (one color/width for the whole collection), keeping overlapping
  same-color points distinguishable. Giving `edgecolors` alone still draws
  a visible outline, at a default width.
- `legend()` (both `Axes.legend()` and `Figure.legend()`) gains `fontsize`;
  `Axes.legend()` also gains `handles`/`labels` for manual/proxy entries --
  any plotpress artist, in the order given, from this axes, another, or
  never added to one at all, with `labels` overriding the text shown,
  positionally.

### Fixed

- `raster._raster_legend()` (the axes-level legend's PNG/PDF renderer)
  recomputed its own entries and font size independently of svg.py's
  layout instead of reusing it, so `legend(handles=, fontsize=)` rendered
  correctly in SVG but was silently ignored in raster output -- the same
  class of backend-parity bug as the marker color list, `errorbar(xerr=)`,
  and polygon outline width fixes before it, found the same way: by
  actually rendering to PNG rather than trusting a clean SVG.

### Added

- Every plotting method gains `zorder=0` -- draw order within an axes,
  independent of call order (ties keep call order, matching the only
  behavior before this existed). Previously there was no way to reorder
  the visual stack at all short of reordering the calls themselves.

### Fixed

- `imshow(alpha=...)` was accepted, stored, and documented, but never
  actually applied -- `apply_colormap()` always emitted a full-255 alpha
  channel, and no opacity ever reached the embedded `<image>`, so
  `alpha=0.2` rendered identically to `alpha=1.0` in both backends. Now
  scales the existing alpha channel rather than overwriting it, so a NaN
  cell's own transparency and an RGBA input's own alpha channel both stay
  correct alongside the new uniform `alpha`.

### Added

- `plot(..., marker=None, markersize=None, markerfacecolor=None)` -- a dot
  at each vertex alongside the line, the same constant-pixel-size marker
  `scatter()` already draws (only round shapes are drawn; any other
  `marker` warns, same limitation `scatter()`/`errorbar()` already have).
- `bar()`/`barh()` gain `yerr`/`xerr`/`capsize`/`ecolor` -- error bars
  (whiskers + caps, no connecting line or marker) centered at each bar's
  own top (`barh`: right edge), composed from the same primitives
  `errorbar()` already draws. `ecolor` defaults to black, independent of
  the bars' own `color`.
- `fill_between()`/`fill_betweenx()` gain `edgecolor`/`linewidth` --
  `fill()` already had both (same closed-path primitive), so there was no
  reason the outline was `fill()`-only.

### Fixed

- `contour()`'s per-level colors came from each level's *rank* in the
  `levels` array, not its value -- correct only when levels happened to
  be evenly spaced with no explicit `vmin`/`vmax` (there wasn't one to
  give). Now colors come from each level's value normalized by
  `vmin`/`vmax` (new, default `Z`'s own min/max), the same normalization
  `contourf()`/`pcolormesh()` already use -- non-uniform `levels` (e.g.
  `[0, 1, 10]`) now get each one's true position on the scale, and an
  explicit `vmin`/`vmax` colors contour lines consistently with a filled
  version of the same field.
- A `Line2D`'s own marker primitive (see `marker=` above) passed a
  single-element color list where the raster backend expects one entry
  per point -- `zip()` silently truncated to the shortest list, so only
  the *first* vertex's marker ever rendered in PNG/PDF output, with
  nothing to reveal the rest were dropped.
- `errorbar(xerr=...)` -- and, composed on top of it, `bar()`/`barh()`'s
  own new `yerr`/`xerr` -- rendered correctly in SVG but drew no whiskers
  or caps at all in PNG/PDF output: the raster backend's error-bar
  renderer had a branch for `yerr` but none at all for `xerr`. Found via
  `barh()`'s own `xerr=` composing on top of `errorbar()`, the first real
  path to exercise `xerr` with no `yerr` alongside it.
- A filled shape's outline width had no effect in PNG/PDF output --
  `raster.py`'s polygon compositor passed PIL an outline *color* but
  never a *width*, so `fill_between()`/`fill()`'s `linewidth=` (and
  `hexbin()`'s own fixed hexagon edge width) always drew PIL's own
  default 1px outline regardless of what was requested, while SVG
  correctly scaled the stroke. Found the same way as the `xerr` bug
  above: rendering the same fill at `linewidth=1.0` vs `linewidth=12.0`
  produced pixel-for-pixel identical outlines in PNG until fixed.

### Fixed

- A point-pick marker's dot/label grew right along with the whole figure
  under Magnify/Zoom's whole-figure wheel zoom, since its position and size
  were baked as absolute coordinates straight into its SVG children with no
  compensation for the SVG's own growing rendered CSS size. Fine at rest,
  but a marker that read as a small dot became a blob tens of pixels across
  a few zoom ticks later -- covering the very cell it was meant to point
  at, worst on a large many-panel grid where each panel (and so each mesh
  cell) starts out small to begin with. A marker's on-screen size now stays
  constant at any Magnify/Zoom level.

### Added

- `fig.to_html()`/`fig.save()` gained `extra_js` and `include_default_js` --
  a caller-supplied JS string inlined into the page, after plotpress's own
  (`window.plotpressAddTool`/`plotpressGetMarkers`/`plotpressToData`
  already exist by the time it runs). With `include_default_js=True` (the
  default), `window.plotpressAddTool({label, onClick})`/`{label, mode,
  onClick, onEnter, onExit, cursor}` registers a real button in its own
  row, stacked below plotpress's own (not appended into the built-in row
  itself, which would otherwise run longer with every tool added and
  blur which buttons are plotpress's own vs the page's; the collapse
  toggle hides both rows together) -- an always-on action, or one
  joining the same single-selection group as Span/Zoom/Point Pick,
  called back with `(event, userSpacePoint)`; `window.plotpressToData(point)`
  reuses Point Pick's own per-axes pixel-to-data conversion for it. With
  `include_default_js=False`, plotpress's own toolbar/pan/zoom/pick JS is
  dropped entirely -- `extra_js` becomes the only interactivity the page
  gets, built from the raw `#plotpress-meta`/`#plotpress-pick`/
  `#plotpress-style` JSON payloads and `#plotpress-svg` directly (pair
  with `binary_pick_data=False`, since the default binary encoding needs
  plotpress's own decoder). Nothing about either fetches anything
  external on its own -- both are inlined the same as plotpress's own JS,
  keeping the "no external requests" guarantee intact regardless of what
  they contain. See `docs/examples/custom_interactivity/` for both
  worked examples.
- `fig.adopt_axes(ax)` -- merges an axes built standalone (most often a
  copy that just crossed a process boundary: a `joblib`/`multiprocessing`
  worker's return value) into this figure, in place of whichever of its
  own axes shares that grid position. A `Figure` isn't something a worker
  process can share with the one that owns it -- pickling an axes to hand
  it to a worker always produces a copy, never a live reference, however
  identical it looks, so mutating that copy inside the worker never
  touched the original before now. Lets a worker function plot directly
  onto the axes it's given (fit + plot in one call, no separate
  return-arrays-then-replot step) whether it's running in this process or
  a subprocess -- the function itself never needs to know which. A
  colorbar axes is appended instead of replacing a slot, since
  `fig.colorbar()` always creates one that never existed in the parent to
  begin with. See `docs/examples/parallel_building/plot_01_joblib_lazy_parquet_fit.py`
  for a full worked example (a lazy parquet scan per panel, fit inside a
  joblib worker, merged back with `adopt_axes()`; the same worker function
  also plots directly when called outside joblib, for live debugging).
- Extracted/picked points now carry a `group` field -- the title of any
  `fig.group()` box the source axes belongs to (empty if none, `", "`-joined
  if more than one), the same way they already carry `axes_title`. Reaches
  the CSV/JSON Extract panel and `window.plotpressGetMarkers()` alike, since
  both build off the same per-axes metadata payload.
- `docs/examples/grouping/plot_10_nested_groups.py` -- a worked example of
  `fig.group()` boxes that visually nest (an outer group's box containing
  two narrower ones, titles included). `fig.group()` itself has no notion
  of hierarchy; the example spells out the two choices (distinct title
  edges, and margins wide enough for the outer box's `pad` to clear the
  inner titles) that make the containment read cleanly rather than as
  overlapping dashes or clipped text.
- 15 more built-in colormaps, rounding the library out to matplotlib's usual
  categories: single-hue/heat sequential (`Blues`, `Greens`, `Oranges`,
  `Reds`, `Purples`, `YlOrRd`, `hot`), diverging (`Spectral`, `PiYG`, `BrBG`,
  `seismic`), cyclic (`twilight`), and classic rainbows (`jet`, `turbo`,
  `cool`) -- alongside the existing perceptually uniform (`viridis`,
  `plasma`, `inferno`, `magma`, `cividis`) and `coolwarm`/`RdBu`/`gray`
  ones, all reversible with `_r` like before. New gallery page
  `auto_examples/gridded_data/plot_11_colormap_reference` shows every one
  of them as a gradient swatch, grouped by category like matplotlib's own
  colormap reference.

### Changed

- The interactive toolbar's buttons are now grouped by what they do instead
  of the order features were added in: navigate the view (Span/Zoom/Magnify,
  then Reset), mark data (Point Pick/Annotate Point/Annotate Free), control
  what's visible (Hide Annotations), then get something out of the figure
  (Extract, then Save/Save As). Purely a display-order change -- every
  button is still selected by its own label, nothing about what any of them
  do changed.
- That grouping is now two physical rows, not one long one: navigate the
  view and persist it (Span/Zoom/Magnify/Reset, then Save/Save As) on top;
  mark data and get it out (Point Pick/Annotate Point/Annotate Free/Hide
  Annotations, then Extract) below. A caller's own `extra_js=` tools
  (`window.plotpressAddTool`) get a third row of their own, stacked below
  both -- see `fig.to_html(extra_js=...)` below. The collapse toggle
  (**▸**/**◂**) hides every row together.
- Whole-figure zoom (Zoom's Ctrl+wheel, and Magnify) now grows the SVG's
  own rendered size on the page instead of cropping its viewBox. Cropping
  never changed the SVG's on-page footprint, so once zoomed in there was
  nothing for the browser's own scrollbars to reach -- a custom drag was
  the only way to see the rest of a zoomed-in figure. Growing the element
  makes the overflow real, native-scrollable page content: the browser's
  own scrollbars, trackpad, and keyboard all work now, on top of drag-to-pan
  still working exactly as before. Reset and double-click (Magnify) both
  shrink back to the figure's natural size with nothing left to scroll.

### Added

- **Magnify** now double-click-resets the whole-figure view (there is no
  per-axes zoom here for Span/Zoom's own double-click reset to act on) and
  disables text selection on the figure while active, so a pan drag no
  longer highlights the tick labels/titles it sweeps across.
- A point-pick marker's own dot now scales with the pixel size of the axes
  it lands on (clamped to a comfortably clickable minimum and the same
  maximum a normal-sized single axes already used), instead of a flat
  3.5px radius everywhere -- on a large grid of small panels (100 axes on
  one figure, say) that fixed size dwarfed the panel it sat on.
- `fig.group_spacing(wspace=None, hspace=None)` -- extra pixels reserved
  between subplots for `fig.group()` boxes at *interior* grid boundaries
  (two groups facing each other where neither title touches that boundary,
  so `tight_layout()` reserves nothing there automatically), without
  discarding any of `tight_layout()`'s own automatic margins the way
  reaching for `subplots_adjust()` previously required. Applies only to the
  row/col boundaries that actually border a group's own bounding box --
  two rows paired inside the *same* group stay exactly as tight as
  `tight_layout()` would put them; only the seam facing a neighboring
  group grows. `tight_layout()` also grows the figure to hold that room
  rather than shrinking every axes to fit it, so a plot's own size is
  unaffected by how much room its groups need between them. All six
  grouping examples that previously fought this with hand-tuned
  `subplots_adjust()` margins (`plot_02`, `plot_04` through `plot_08`) now
  use it instead, restoring `tight_layout()`'s automatic
  title/tick-label/colorbar sizing that `subplots_adjust()` had been
  overriding wholesale just to fix one gap.

### Fixed

- `fig.group_spacing()` widened *every* interior row/column gap in the
  grid uniformly, not just the boundaries that actually sit between two
  different groups -- rows paired inside the same group (see
  `plot_05_many_small_row_pairs`) got pushed apart by the same amount as a
  genuine group-to-group seam, even though nothing needed the room there.
  It also shrank every axes to make space for the reservation, since the
  figure's own size never grew to hold it. Both fixed: the extra room now
  lands only at boundaries a group's box actually touches, and
  `tight_layout()` grows `figsize` by exactly what's reserved instead of
  shrinking the plot area.
- `tight_layout()` sized every axes' tick-label margin from the
  figure-wide default (`Style.tick_label_size`/`tick_size`) even when that
  axes had its own smaller `tick_params(labelsize=..., length=...)`
  override -- a grid that shrinks its tick labels to fit small panels
  (`plot_05_many_small_row_pairs`, `plot_06_many_small_column_pairs`,
  `plot_08_fontsize_and_colorbar`, all of which do this) still reserved
  margin sized for the bigger, unused default, over-widening every gap
  next to it. Margin sizing now resolves the same per-axis tick style
  `svg.py` already draws with.
- A **Magnify** toolbar mode -- the same whole-figure wheel zoom as
  Ctrl+wheel under **Zoom**, but on a *plain* wheel, no Ctrl needed. Its own
  mode rather than folded into Zoom, so selecting it is an explicit choice
  to have this figure capture the page's scroll -- for wherever holding
  Ctrl is awkward, or a browser/OS extension already claims it. Drag pans
  the same whole-figure view in any direction, so a zoomed-in figure stays
  fully reachable without switching tools -- always the figure's own view,
  never an axes' data range, isolating it completely from per-axes zoom/pan.
- `benchmarks/`'s cross-library comparison now includes plotly, on
  interactive HTML output specifically (`fig.to_html()` vs
  `fig.to_html(interactive=True)`) rather than static SVG -- plotly has no
  native static-image path of its own; `fig.to_image()` always shells out to
  a real headless browser via `kaleido`, which would measure a browser's
  cold-start cost far more than rendering. Every timing comparison
  (`benchmarks/benchmark.py`, `benchmarks/example_timings.py`) now also
  reports each library's output **size**, alongside time -- a free
  byproduct of a call already being made (every builder returns what it
  just serialized), not an extra render.
- `docs/conf.py`: sphinx-gallery's example scripts now execute in parallel
  under `sphinx-build -j <N>` (opt-in via `-j`; a plain `sphinx-build` with
  no `-j` still runs serially) -- plotpress's own "no global state" design
  means no example script has anything to leak into another's worker
  process, which is usually what keeps projects from turning this on. A
  full clean build of all ~230 examples: 13m43s serial vs 8m52s at `-j 6`
  (this machine), output verified byte-identical aside from each page's own
  self-reported execution-time line.

### Fixed

- `suptitle()`/`supxlabel()`/`supylabel()` added straight into the same
  accumulators `tight_layout()` also uses to size the *interior* row/col
  gap between subplots -- a figure-level label, drawn once outside the
  whole grid, ended up widening every gap between every row or column too,
  not just the true outer margin it actually needs. Each now reserves only
  its own outer-margin band, the same fix already applied to `fig.group()`.
- Two `docs/examples/data_roundtrip/` scripts wrote their standalone HTML
  fixture to the exact same temp filename -- harmless run serially (each
  writes-then-reads-back before the other runs) but a real race once
  example scripts can execute in parallel (see above), where one could load
  the other's file. Each now uses its own name.

### Changed

- `docs/requirements.txt` is gone -- its packages (`sphinx`, `sphinx-gallery`,
  `sphinx-rtd-theme`, `matplotlib`, `polars`, `adaptive`) plus a new `joblib`
  (parallel gallery execution, see above) now live in `pyproject.toml`'s
  `docs` extra: `pip install .[docs]`. `bench` also gained `plotly`.

### Added

- **Save**/**Save As** toolbar buttons -- download the current interactive
  session (pan/zoom, every pin/annotation, hidden-legend-series toggles,
  Hide Annotations) as a new, equally self-contained HTML file; reopening
  it resumes exactly where this session left off, not just what was
  originally plotted. Save additionally tries to overwrite the file this
  page was opened from in place, via the File System Access API where a
  browser supports it (Chromium, a secure context), falling back to the
  same download Save As does everywhere else -- a page can never be handed
  a writable handle to the exact file it was itself opened from, so this
  is really "pick a destination, defaulting to this file's own name," not a
  silent, prompt-free overwrite. Works the same inside a `Report`'s
  embedded figure: each panel is its own independent document, so saving
  from one saves only that panel.
- `fig.group(title, axes, ...)` -- draws a labeled box around a set of
  axes (e.g. a cluster of related panels in a larger grid): the tight
  bounding rectangle of their own positions -- expanded to also clear each
  axes' own tick labels, axis labels, and title, not just its bare plot
  rect -- plus a little padding, with the title just outside whichever edge
  `title_position` (`"top"` (default), `"bottom"`, `"left"`, `"right"`)
  names. Several groups may be added to one figure. `tight_layout()`
  reserves margin for a group whose title faces the grid's own outer
  edge, the same way it already does for a `suptitle`/colorbar/figure
  legend -- sized to the title's own rendered height for a top/bottom
  title, or its rendered *width* for a left/right one, since that one
  runs alongside the box rather than centered over it; an interior group
  (not touching that edge) is left to the existing row/col gap instead.
  Has its own gallery section (`docs/examples/grouping`, `.. _grouping_gallery:`),
  seven examples: row-based and column-based groups (both a `"top"`-titled
  small-grid version and a many-small-groups version at 15 and 12 groups
  respectively), a 30-panel `pcolormesh` grid split into two column-bands,
  a single-axes interior group with no reserved margin, side-by-side
  groups with left/right titles, and a four-quadrant grid using all four
  `title_position` values in one figure. An eighth example now also passes
  an explicit `fontsize` and combines a group with a `colorbar()` on the
  same figure.
- Closed the remaining gaps between the docs example gallery and the
  public API: new examples for `Report` (`docs/examples/figure_layout`),
  `Axes.fill_betweenx`, `Axes.hlines`/`vlines`, `Axes.semilogx`/`semilogy`,
  `Axes.tick_bottom`/`tick_left`, `Axes.minorticks_off`, `Axes.sharex`,
  `Axes.twiny`, `Axes.set_xmargin`/`set_ymargin`, `Axes.get_pick_context`,
  `Axes3D.set_xlim3d`/`set_ylim3d`/`set_zlim3d`, and a new
  `docs/examples/polar/plot_04_polar_customization.py` covering
  `set_rlim`/`set_rticks`/`set_thetagrids`/`set_theta_direction`/
  `set_theta_zero_location`/`set_theta_offset` -- none of which had any
  prior example.

### Added

- `docs/scale/plot_10_many_groups_with_colorbars.py` -- times `fig.to_svg()`
  on the same 100-axes grid with no groups, 50 groups, and 50 groups where
  every axes also carries its own colorbar, to put a number on whether
  `fig.group()` costs anything at scale (answer: no, for normal use; a
  measurable but still small amount only at this kind of extreme density).
- The interactive toolbar's button row can now be collapsed (a **▸**/**◂**
  handle, always at the same corner) to declutter the view -- a screenshot,
  say -- without losing the only way to bring it back. Not remembered
  across a reload/Save; it always starts expanded.

### Fixed

- `fig.group()`'s box now wraps a colorbar attached to one of its own axes
  (`fig.colorbar(mesh, ax=ax)`) instead of only the bare pcolormesh rect --
  a colorbar steals its space from right next to its axes, and the box used
  to stop short of it, leaving the colorbar poking out past the line meant
  to enclose it. A colorbar shared with an axes *outside* the group is left
  alone, since pulling the box out to wrap it would misrepresent the group.
  New example: `docs/examples/grouping/plot_09_colorbars_inside_the_box.py`,
  four panels each with its own independently labeled colorbar.
- A colorbar's `.set_title("units")` -- this library's own convention for
  labeling what its scale means -- never actually rendered in either
  backend; both returned out of axes rendering before reaching the
  title-drawing code. Now renders in SVG and PNG alike.
- **Save As** now shows the same File System Access API file picker **Save**
  already did, instead of always silently downloading to the browser's
  default location under an auto-generated name -- the whole point of "Save
  As" is choosing a destination and name, and it previously never let you.
  Falls back to the same plain download anywhere the picker API is
  unavailable (Firefox, Safari, a non-secure origin), same as **Save**.
- Arrow-key stepping between mesh cells (`pcolormesh`/`pcolormesh_frames`
  point-pick) now honors `invert_xaxis()`/`invert_yaxis()` -- Up/Down and
  Left/Right used to always mean "increase/decrease the underlying row or
  column index," so on an axis drawn flipped (e.g. a depth plot with the
  y-axis inverted, where larger values are drawn toward the bottom) Up
  moved the pin down the screen instead of up.

### Changed

- The interactive toolbar's whole-figure wheel zoom now requires Ctrl
  (matching the standard browser/OS convention -- a trackpad pinch is
  already reported as a wheel event with `ctrlKey` set, so that gesture
  works unchanged). A plain wheel, even with Zoom selected, now scrolls the
  page instead of always hijacking it to zoom the figure -- the figure
  could previously make the enclosing page unscrollable wherever it
  appeared, which is a worse default than requiring one held key.
- Docs build: a gallery figure with more than 6 axes (currently only
  `docs/examples/data_roundtrip`'s 30-panel grids) now links to its full
  standalone interactive HTML in a new page instead of embedding it in a
  fixed-size `<iframe>` -- most of a many-panel grid's panels would be too
  small to usefully pick or zoom into at iframe size. Also disables
  sphinx-gallery's default last-expression capture (`capture_repr`), which
  printed a stray `<plotpress.figure.Figure object at 0x...>` line on
  nearly every gallery page, since most examples end with a bare
  `fig.tight_layout()` (returns `self`) as their last statement.

### Fixed

- `Report` embedded each figure at its own fixed pixel size, centered by
  `Figure.to_html()`'s standalone body style inside a same-size `<iframe>` --
  narrower than most browser windows, and, whenever the iframe's fixed
  height (a flat +96px "room for the toolbar" guess, regardless of whether
  the figure actually had one docked) didn't match the centered figure's
  own height, split the difference into empty grey bands above and below
  it. `Figure.to_html()` gains a `standalone` parameter (`Report` now passes
  `False`): the SVG scales to fill whatever width its container gives it
  instead of sitting at a fixed size, and the page no longer forces itself
  to a full viewport tall. Each `Report` iframe now stretches to the full
  width of the page and a small resize script settles its height to the
  real rendered content -- exactly the figure, plus real reserved space per
  docked slider strip, nothing left over.

  A `plot_frames()`/`pcolormesh_frames()` figure needed a second, deeper
  fix: the div it wraps the SVG in (to position docked sliders over it) was
  hardcoded `display:inline-block`, which shrink-wraps to the SVG's own
  fixed width/height attributes regardless of any CSS on the SVG -- a
  circular size dependency that silently undid the scaling above for any
  figure with a slider. That wrapper's sizing now comes from the same
  standalone-aware stylesheet as everything else, not a hardcoded inline style.

  Toolbar/slider clearance is now real body padding inside the embedded
  document itself (a new `_toolbar_clearance()` helper), not a guessed
  iframe height: dropping the old flat +96px guess had also silently
  removed the only thing keeping the toolbar (`position:fixed`, so it
  otherwise takes no layout space of its own) from drawing over a legend or
  colorbar in a figure's top-right corner once nothing else reserved room
  for it. The docs build's own gallery and `usage.rst` demo embeds
  (`docs/conf.py`) shared the exact same bug -- `standalone=True` plus a
  flat height guess -- and now use this same fix. The report resize script
  also no longer risks collapsing a `loading="lazy"` entry that hasn't
  loaded yet to near-zero height if a resize fires before the reader
  scrolls to it, and skips re-measuring an iframe whose width hasn't
  changed since its last fit.
- `pcolormesh_frames()` (a `pcolormesh` with a slider over an extra
  dimension) had no pick data at all, at any frame -- `frame_data()` only
  ever embedded each frame's rendered PNG for the slider to swap in, never
  its raw z grid, and `pick_data()` only ever handles a plain (non-frame)
  `QuadMesh`. Point Pick and Annotate Point silently produced no marker on
  one, however precisely a click landed on a cell. Frame meshes now embed a
  z grid per frame (rectilinear and curvilinear both); a picked cell keeps
  its position across a slider scrub (the grid is shared across frames --
  only the color data animates) while its reported value updates to the
  new frame's, and it steps to neighboring cells by arrow key exactly like
  a plain mesh pick does. `plot_frames()` (a line with a slider) already
  picked correctly and is unaffected.
- `plotpress.qt.view()`/`fig.show_qt()` constructed `QApplication([])` --
  an argv with no program name, which leaves QtWebEngine's internal
  `base::CommandLine` uninitialized. Depending on platform and Qt/WebEngine
  version this broke every `QWebEngineView` the app ever created, anywhere
  from a clean "the program name is not passed to QCoreApplication" error
  to a hard native crash on the first one -- for any caller who didn't
  already own a `QApplication` (i.e. `plotpress.qt` used standalone, not
  inside an existing Qt app). `sys.argv` always carries a program name;
  `[]` doesn't.
- A `NaN`/`Infinity` anywhere in a figure's data (a masked heatmap region, a
  dropped-out channel, a divide-by-zero) silently disabled the *entire*
  interactive toolbar, not just picking on the affected series. `json.dumps`'s
  default `allow_nan=True` emitted those as bare, unquoted tokens -- valid
  Python, not valid JSON -- so the browser's strict `JSON.parse` threw on the
  very first one and none of the embedded payload (meta, pick data, style,
  sliders) loaded. Non-finite floats are now sanitized to `null` before
  embedding. This affected several of the real-application gallery examples,
  whose data has genuine masked regions (e.g. `chemistry/plot_01_excitation_
  emission`'s excised Rayleigh/second-order bands).
- A per-axis `tick_params()` style override (`color`, `width`, `labelsize`,
  `labelcolor`) rendered correctly in the initial static SVG but silently
  reverted to the figure's default style the moment that axes was panned or
  zoomed in interactive HTML -- the client's tick-rebuild read only the
  figure-wide style payload, never the per-axes override. It now carries the
  override through the embedded metadata and reproduces it on every rebuild.
- **Extract panel/`window.plotpressGetMarkers()` bugs**, all in the
  interactive HTML's JS toolbar:
  - CSV export had no RFC 4180 field quoting -- a comma, quote, or newline in
    any string value (annotation text, `axes_title`, a pie label, a
    `set_pick_context()` value) shifted every column after it out of
    alignment. Fields are now quoted per spec.
  - A series' `values={...}` dict was merged onto its picked record with no
    collision guard, so a key sharing a name with a structured field
    (`kind`, `x`, `y`, `index`, `axes`) silently overwrote it -- the same
    hazard `set_pick_context` was already protected against, in the other
    direction. The structured field now always wins, for both mechanisms.
  - Point Pick's fallback for a series too large to embed for picking (over
    `to_html()`'s default `pick_max_points=20000`) compared the click
    against that series' raw, pre-pan/zoom SVG geometry -- after the axes
    was panned or zoomed, a click resolved to whatever vertex happened to
    sit at that pixel position in the *stale* coordinate space, not the
    datum actually under the cursor. It now maps the click through the same
    affine the pan/zoom view transform uses before comparing.
  - `plot_frames`' slider scrub silently reverted an "Annotate Point" note's
    custom text back to the auto-generated `"x=.., y=.."` readout, because
    the frame-update path was the one place that re-laid out a pin without
    going through the helper that preserves a user-typed label -- pan/zoom
    and arrow-key stepping already did this correctly.

### Added

- **`plotpress.qt.LiveArtist` -- streamed data in a Qt widget without a full
  page reload.** `PlotPressWidget.set_figure()` is a full `QWebEngineView`
  navigation, and that navigation's own cost (teardown, re-parse, toolbar JS
  re-running from scratch) dominates over rendering: it tops out around 4-5 Hz
  regardless of how much data is on the figure, from 200 points to 50,000.
  `LiveArtist` loads the figure once (a normal `set_figure()`, needed to get
  the toolbar/JS/pick-data in place) and patches the already-loaded page on
  every call after that -- swapping the visible `<svg>`'s children for a fresh
  render and refreshing that axes' point-pick payload via
  `page().runJavaScript()`, in one round trip. Measured at roughly 55 Hz
  sustained for a 50,000-point line and 140 Hz for a 100x100 mesh, against
  the 4-5 Hz full-reload ceiling above. Works for both `ax.plot()`-style lines
  (`artist.update(x, y)`) and `ax.pcolormesh()`-style meshes
  (`artist.update(x, y, C)`) -- including a mesh that's mostly `NaN` and fills
  in over time, the common shape for a real 2-D instrument sweep or scope
  trace, which needs no special handling since `NaN` already renders and
  picks as "no data" the same as a static figure's masked region -- the
  live-refreshed pick payload is sanitized the same way the initial static
  one already is, so a `NaN` doesn't break the point-pick JSON the way an
  unsanitized one would. A live update also leaves the current pan/zoom
  view alone (it patches around the toolbar's view state instead of
  overwriting it) and preserves any pins or annotations already on the
  figure, rather than silently discarding both on every call.
  `LiveArtist.last_artist` exposes whatever `update()` most recently drew
  (a `Line2D`/`QuadMesh`), for the one thing `update()` itself can't do --
  refresh a colorbar for an autoscaled mesh, whose old mappable goes stale
  the moment `update()` clears the axes out from under it.

  Gets its own top-level gallery section (18 examples) rather than a
  subsection of the plot-type reference, since a Qt binding isn't available
  at doc-build time to drive a real live window: six examples animate the
  acquisition shapes in the abstract (sparse vs. dense, growing vs. fixed
  extent), and twelve put those shapes into specific instruments -- an
  oscilloscope's rolling buffer, a spectrum analyzer's sweep-and-max-hold, a
  titration's live equivalence-point detection, simultaneous qPCR wells, a
  chromatogram's live peak-calling, an AFM raster scan, a particle
  detector's accumulating (not merely revealed) hit map, cyclic voltammetry
  drawn cycle over cycle, a four-channel bioreactor dashboard (multiple
  `LiveArtist`s on one figure), a radio telescope's serpentine sky survey,
  and two searches driven by the `adaptive` package's own `Learner2D` --
  concentrating samples on a ring's steep edges and, separately, across
  four unrelated structures at once, rather than sampling uniformly. Every
  example's *rendered* code is copy-paste turnkey against the real
  `LiveArtist` -- only a `read_next_*()`-style stand-in is meant to be
  replaced with a real instrument call -- rather than merely structured to
  resemble it: the doc-build-only harness a Qt-less build needs to render
  each example as a GIF (a `LiveArtist`-alike that renders a frame instead
  of pushing one live, the frame capture itself) is real code that
  actually runs, just marked for sphinx-gallery to execute without
  displaying, so nothing on the page needs mentally subtracting out before
  it's usable.

- **`fig.to_html(binary_pick_data=True)` / `fig.save(...html, binary_pick_data=True)`.**
  Long embedded point-pick arrays (mesh `z` grids, animated line frames) now
  encode as base64 float32 bytes instead of JSON number text, on by default.
  Benchmarked against gzip-compressing the JSON instead (also smaller, but
  5-7x slower to decode client-side -- `DecompressionStream`'s per-call
  overhead dominates at these payload sizes) and against the plain-JSON
  payload it replaces across every example in the plot-type and large-scale
  galleries (see `docs/performance.rst`'s "Binary vs. JSON pick data"
  section): roughly half the size on mesh- or line-heavy figures, at
  JS-decode speed close to `JSON.parse`, and *faster* to build server-side
  too (`base64.b64encode(arr.tobytes())` beats formatting tens of thousands
  of floats as JSON text). Float32 also represents `NaN`/`Infinity`
  natively, so a masked mesh cell survives the round trip without
  `_sanitize_nan`'s `None` substitution. Short arrays (below a length where
  the base64 wrapper would cost more than it saves) are left as plain JSON,
  unaffected either way. Set `binary_pick_data=False` for the exact old
  payload -- e.g. to hand-inspect it or diff against an older plotpress
  version.

  An array also drops to float16 (half the float32 size again) wherever a
  round trip through it loses nothing beyond what `pick_precision` already
  rounded away, checked per array rather than inferred from the precision
  number alone -- a value past float16's +-65504 range or finer than its
  ~3 significant digits falls back to float32 automatically, so lowering
  `pick_precision` on out-of-range data can't silently corrupt it into
  `Infinity`. At the library's default `pick_precision=6` this essentially
  never qualifies (float16 can't hold 6 decimal digits of fidelity), so
  `pick_precision` now does what it always documented -- lower it, get a
  smaller file -- instead of being inert once an array was already large
  enough to binary-encode.

  `binary_pick_data=True` also restructures the embedded per-axes metadata
  column-wise (one array per field instead of one object per axes). That
  payload has no long arrays of its own -- every field is a single scalar
  per axes -- so on a many-axes figure its cost was ~25 JSON key names
  (`"tick_style"`, `"secondary_dim"`, ...) repeated in full for every axes
  rather than a big number array the encoding above could shrink. Stating
  each key once cuts it roughly in half on its own (measured 0.43-0.48x
  across a 500- and a 900-axes figure); the numeric columns that leaves
  (`x`/`y`/`w`/`h`/`xmin`/`xmax`/`ymin`/`ymax`) then qualify for the same
  binary encoding, compounding it further. The axes index itself (not
  necessarily contiguous -- a colorbar, 3-D, or hidden axes is excluded
  from this payload wherever it sits) rides along as its own plain-JSON
  array rather than through the encoder, since a short run of small
  sequential integers is cheaper as JSON text than base64.
- **`Axes.pcolormesh_frames(X, Y, C, ...)`.** The mesh counterpart of
  `plot_frames()`: `C` carries a leading frame axis, `X`/`Y` stay shared
  across every frame, and a `FrameQuadMesh` artist animates it through the
  same slider machinery -- shared or per-axes docked scope, GIF export,
  interactive HTML scrubbing all included. Each frame is built as its own
  fully-validated `QuadMesh` (curvilinear/gouraud/descending-axis handling
  included rather than reimplemented) sharing one `Normalize` autoscaled to
  every frame's data at once, so the colour scale stays fixed instead of
  jumping frame to frame. In interactive HTML a mesh frame swaps its
  `<image>` `href` on scrub rather than recomputing geometry, since every
  frame shares one grid and only the pixel content changes -- cheaper than
  the line case, not more expensive. Five new worked examples: a room's
  modal pressure actually standing still at its nodal lines while
  oscillating everywhere else, a full 2-D sea-surface-temperature field
  through the seasonal cycle, the exact closed-form decaying Taylor-Green
  vortex (a CFD validation case, not merely a demonstration flow), a
  four-panel reference example exercising both shared and linked-docked
  slider scopes for meshes, and a size/save-time benchmark against
  `plot_frames()` showing why: a mesh frame is an independent embedded PNG
  where a line frame is a raw array, and the growth curves diverge
  accordingly (megabyte range by 80 frames at a modest resolution, where the
  equivalent line animation stays in the low hundreds of KiB).
- **`fig.save(path.gif, label_frames=True)` stamps each frame with its
  slider value.** A GIF has no slider to read the current value off of, so by
  default the exported frame now carries a small top-right label (`t = 1.57`,
  `month = 8`) reusing the slider's own value formatting and `slider_label`.
  Set `label_frames=False` to opt back out to a bare render. Works the same
  for both `plot_frames()` line series and `pcolormesh_frames()` meshes,
  since it's stamped onto the already-rendered raster frame rather than
  threaded through either artist.
- **`fig.save(path.gif, fps=10, slider_unit="main")`.** Any
  `Axes.plot_frames()` series now exports to a self-contained looping GIF via
  Pillow, animating through the same frames an interactive HTML slider
  scrubs -- for anywhere that slider does not fit (a README, a slide, a chat
  message). `slider_unit` picks which slider drives the animation on a
  figure with more than one (a mix of shared and per-axes `plot_frames()`
  panels); every other series holds its frame 0 for that render. Raises
  `ValueError` on a figure with no `plot_frames()` series -- there is
  nothing to animate.
- **Sixteen GIF-export worked examples**, one in the plot-type reference
  gallery and one in each of the fifteen real-application fields, each
  building a genuinely time- or parameter-varying quantity and exporting it
  with `fig.save(path.gif, ...)`: a duct pulse reflecting off rigid walls
  (finite-difference wave equation), a morphogen gradient forming by
  diffusion and degradation, a reaction's UV-vis spectrum crossing its own
  isosbestic point, a training run's validation loss overfitting live, a
  hemisphere's seasonal temperature cycle, a week of daily grid load curves,
  a yield curve un-inverting month by month, a boundary layer diffusing from
  an impulsively started plate (Stokes' first problem), a control chart and
  a tensile test and an ECG strip each revealed the way their instruments
  actually produce them, a Rabi chevron taken apart into its line cuts, a
  MOSFET's output family swept continuously in gate voltage, a pulsar
  profile emerging from noise as more pulses are folded, and an airfoil's
  stall angle creeping outward with Reynolds number. The docs build's own
  image scraper (`docs/conf.py`) now captures any figure with a
  `plot_frames()` series as that same animated GIF rather than a frame-0
  PNG snapshot -- sphinx-gallery copies a `.gif` byte for byte for its
  thumbnail rather than re-encoding it, so both the gallery page and its
  thumbnail grid play the animation, not just the sixteen examples' own
  `fig.save()` calls.
- **Per-axes point-picking control.** `Axes.set_pickable(False)` excludes an
  axes from Point Pick/Annotate Point (Span, Zoom and Annotate Free are
  unaffected), so a figure can restrict picking to a single panel.
  `Axes.set_pick_context(**kwargs)` attaches arbitrary key/value context that
  rides along on every record picked from that axes -- e.g. surfacing a
  per-panel spine color -- without clobbering the picked data's own fields.
  Every picked/extracted record now always carries `axes_title`, falling back
  to a generated `"axes N"` when the axes has no title of its own instead of
  omitting the field. Every record also now carries `xlabel`/`ylabel` and
  `zlabel` (from any colorbar attached to that axes -- shared across several
  axes via `fig.colorbar(mesh, ax=[...])` reports the same label for each of
  them), so a value pulled out of context still says what it means.
- **Real applications gallery** — a second, separate gallery of 100+ worked
  figures built from the data real measurements produce, grouped into fifteen
  fields (earth science, astronomy, medical imaging, biology, chemistry,
  materials, quantum devices, semiconductors, fluids, acoustics, energy,
  transport, manufacturing, computing and finance). Each starts from the
  measurement and explains the axis, scale and colour choices it forces. Every
  figure is also embedded live, with the interactive toolbar. The plot-type
  reference gallery is unchanged and now lives on its own page.
- Ten more superconducting-qubit examples in the quantum devices gallery, all
  `pcolormesh` parameter sweeps: TLS defects wandering through a T1-vs-
  frequency-vs-time map, a Ramsey chevron and a separate Ramsey-vs-flux
  dephasing map, flux-swept 0-1/two-photon 0-2 spectroscopy for anharmonicity,
  photon-number splitting, multi-photon ladder spectroscopy, a signed
  cross-resonance ZX-rate map, SQUID switching probability, single-shot
  readout fidelity's two-dimensional (frequency, integration-time) optimum,
  and error-amplification gate calibration.
- Ten gate-calibration/tune-up examples in the quantum devices gallery: DRAG
  coefficient calibration from amplified leakage, an AllXY amplitude-scaling
  sweep, a CZ gate's `|1,1>`-`|0,2>` avoided-crossing chevron and its
  conditional-phase calibration, static `ZZ` crosstalk nulling via a tunable
  coupler, flux-line crosstalk from a tilted spectroscopy arch, active-reset
  residual population falling exponentially with rounds, a single-qubit
  gate's amplitude/duration speed limit against leakage, a single-shot
  readout IQ blob histogram, and CPMG dynamical-decoupling coherence
  extension.
- Five more tune-up examples (IQ mixer LO-leakage and image-sideband
  nulling, measurement-induced state transitions, photon-shot-noise Hahn
  echo dephasing, flux-pulse rise-time/leakage trade-off) and five
  randomized-benchmarking examples (RB fidelity across the flux range,
  simultaneous RB crosstalk, purity RB, cross-entropy benchmarking vs depth
  and qubit count, leakage RB) in the quantum devices gallery.
- Ten more quantum devices examples pushing past device calibration into
  device *theory*: Floquet sideband spectroscopy of a flux-modulated qubit
  (Bessel-weighted photon replicas, computed from a self-contained
  trapezoidal-quadrature Bessel function rather than a SciPy dependency),
  fluxonium's multi-level spectrum from an exact finite-difference
  diagonalization of its Hamiltonian rather than a closed-form fit,
  Landau-Zener-Stuckelberg interference diamonds, Autler-Townes dressed-state
  splitting, a Josephson parametric amplifier's gain-bandwidth trade-off,
  GHZ-state parity oscillation and its visibility decay with qubit count,
  a noisy gate's Pauli transfer matrix from process tomography, a simulated
  repetition-code space-time syndrome plot, a Bell/CHSH correlation map
  reaching the Tsirelson bound, and a Kerr-cat qubit's exponential-vs-linear
  bit-flip/phase-flip noise-bias trade-off.
- Every real-application gallery script (all fifteen fields, ~140 examples)
  now builds a `polars` `DataFrame` from the underlying theory or simulation
  and extracts the `numpy` arrays it plots from that table, rather than
  plotting arrays computed inline. This isolates data generation from
  rendering, matching how data is actually collected and tabulated in a lab
  or on a shop floor before anyone touches a plotting call. `polars` is a
  docs-only dependency (`docs/requirements.txt`), not a package dependency.
- `hexbin` and `hist2d` accept `norm` / `vmin` / `vmax`, matching `pcolormesh`
  and `imshow`. Bin counts routinely span decades, and a linear ramp paints
  everything but the densest bin the same colour.
- **Large-scale gallery** on its own page, grown from one example to eleven: a
  million-point line, half a million scatter points, a 2.25-million-cell mesh, a
  thousand series on one axes, nine hundred axes on one canvas, two shared-
  colorbar grids, the interactive payload against `pick_precision`, vector
  overlays on a rasterized field, how output size scales with the data, and a
  head-to-head against matplotlib measured on the machine that builds the docs.
  Examples now come before applications in the sidebar. A **Where it runs out**
  section at the foot of that page measures the costs of the same design
  decisions: scatter output that grows with the data and never flattens, mesh
  cells that stop reaching the screen past one per output pixel, the size of a
  self-contained interactive file, and contour output, which has no ceiling at
  all -- a noisy 800-square field produces 76 MiB of SVG where the identical
  call on a smooth one produces 328 KiB.
- `set_title` takes `size` (and `fontsize`, as matplotlib spells it). A
  small-multiples grid of several hundred panels needs a title a few points
  high, and the alternative was a whole `Style` copy that changes every other
  title too.
- `text` and `annotate` draw a contrasting halo behind the glyphs by default --
  white behind dark ink, black behind light -- so a label stays readable over
  whatever it lands on. A label in the data area is placed before anyone knows
  what will end up underneath it, and over a plain background the halo is
  invisible. Pass `outline=False` to switch it off, or a colour to choose one.
  Titles, axis labels and tick labels are unaffected.
- An annotation's leader now starts at the edge of its text box nearest the
  target, preferring the middle of an edge over a corner, rather than at the
  text anchor. From the anchor the line set off straight across its own label
  whenever the target lay back over the words.
- **Matplotlib-parity axes/figure manipulation**: `ax.spines` (per-side
  `visible`/`color`/`linewidth`), `set_facecolor`/`get_facecolor`,
  `set_visible`/`get_visible`, `remove()`, `cla()`/`clear()`, matplotlib-
  mirroring getters (`get_xlabel`, `get_title`, `get_xticks`, ...),
  `minorticks_on`/`off`, `tick_top`/`bottom`/`left`/`right`, post-hoc
  `sharex()`/`sharey()`, `label_outer()`, persistent `margins()`/
  `set_xmargin`/`autoscale()`, `axis()`, and `set_prop_cycle()`. On the figure
  side: `set_size_inches`/`set_dpi`, `subplots_adjust`, `GridSpec` row/column
  spans (`fig.add_subplot(gs[0, :2])`), `align_xlabels`/`align_ylabels`/
  `align_labels`, `delaxes()`, `clf()`/`clear()`, `fig.text()`, and
  `secondary_xaxis`/`secondary_yaxis`/`inset_axes`.
- `pick_max_mesh_cells`/`pick_max_points` on `to_html()`/`save()`, bounding
  the interactive payload for figures with many mesh-bearing axes instead of
  only trading off per-number precision.
- Point picking now covers every remaining artist kind that had none:
  `fill()`'s polygon, `hlines()`/`vlines()`'s segments, and `broken_barh()`/
  `hexbin()`'s bounding boxes -- `hexbin` also now surfaces its raw bin count
  on pick instead of only the colormapped RGB.
- `import plotpress` resolves `Figure`/`subplots`/`Style`/colormap helpers
  lazily on first access instead of eagerly, keeping a bare `import plotpress`
  cheap for callers who only need `__version__`.
- **Interactive toolbar: "Hide Annotations".** A standalone toggle (not a
  mode -- available regardless of which tool is active) that hides every pin
  and annotation, Point Pick markers and Annotate notes alike, without
  deleting any of them. It only ever flips a CSS `display` rule on
  `.plotpress-pin`, so toggling back to "Show Annotations" restores them
  exactly as they were, including selection state and user-written text.
  See `docs/usage.rst`'s interactivity section for a live demo.
- **`plotpress.Report` -- combine several figures into one self-contained
  HTML file.** Each figure keeps its own independent interactivity (its own
  toolbar, pan/zoom, point-picking, annotations) because it is embedded in
  its own `<iframe>` via `srcdoc` rather than spliced into the page directly
  -- an interactive figure's JS (fixed element ids, a document-level
  toolbar) assumes it owns the page, so several sharing one page would
  otherwise collide, the same reason the docs gallery already embeds every
  live figure this way. `Report.add(figure, title=..., details=...)` appends
  a figure with an optional heading and longer description, in the order it
  should appear -- there is no separate ordering mechanism to keep in sync,
  the call order *is* the display order. `Report.save(path, ...)` forwards
  `interactive`/`pick_precision`/`pick_max_mesh_cells`/`pick_max_points`/
  `binary_pick_data` to every figure's own `to_html()`. See `docs/usage.rst`
  for a live demo combining four figures, each a 5x10 grid of independent
  `pcolormesh` panels with their own title/axes/ticks/labels/colorbar.
- **`plotpress.load_data(path)` -- read the plotted data straight back out
  of a saved interactive HTML file.** Every `interactive=True` file already
  embeds each axes' full plotted data (as JSON, or as base64 float32/float16
  under `binary_pick_data=True`) for point-picking; `load_data()` decodes
  that same payload into plain NumPy arrays instead of re-deriving anything
  from the drawn SVG. Returns a dict keyed by each figure's own title (one
  entry for a bare `Figure`'s HTML, one per embedded figure for a
  `Report`'s, via its `Report.add(title=, details=)` annotations -- a
  generated `"Figure N"` for one with no title), each mapping its own axes'
  titles (generated `"axes N"` for an untitled one, matching a picked
  record's own `axes_title` fallback) to that panel's series/mesh/pie data
  plus its labels/limits/scale. A mesh comes back as a 2-D `z` array with
  its own 1-D `x`/`y` cell-center coordinates, ready for
  `ax.plot(x, z[row, :])` or `np.fft.fft2(z)` without hand-deriving a grid
  from edges or extent. Title keys aren't guaranteed unique -- pass
  `by_index=True` for a plain list of per-figure dicts instead, each keyed
  by integer axes index rather than title, when that matters. Raises
  `ValueError` on a static SVG or `interactive=False` HTML, which embeds
  only drawn shapes, nothing to read back. See `docs/examples/data_roundtrip`
  for two worked examples: reloading a 30-panel `pcolormesh` grid and
  replotting one x-slice per panel as a line, and reloading the same grid
  to run a 2-D FFT over every panel.

### Fixed

- `log_ticks` no longer emits decades outside the axis limits. Autoscale margins
  alone were enough to pull in an out-of-range tick, which -- since tick labels
  are not clipped -- was drawn into whatever sat beside the axes, typically the
  neighbouring subplot. Ranges narrower than three decades now subdivide (1-2-5,
  then linear) instead of labelling a wide axis with two round numbers, and a
  range of many decades thins the decades out rather than interpolating between
  them into ticks like `4.3e-17`.
- `sharex`/`sharey` now share explicit limits and axis inversion, not just the
  autoscale. `set_xlim` or `invert_xaxis` on one panel of a shared grid moved
  that panel alone, silently pulling the grid out of alignment along the very
  axis it was built to share.
- `tight_layout` measures a twin axes' decorations on the side they are drawn
  on. A `twinx`'s right-hand tick labels and axis label were sized into the
  *left* margin, so they overflowed the canvas, or the next subplot. Interior
  column gaps now reserve both neighbours' decorations, and an axes title clears
  a `twiny`'s top labels instead of landing on them.
- `fill_between` broadcasts both bounds against `x`. Only the upper one was, so
  `fill_between(x, floor, series)` raised a shape error from inside the
  transform while the same call with the arguments reversed worked.
- Legend swatches carry the artist's line style, so a dashed threshold and a
  solid data series are distinguishable in the legend as well as on the plot.
- Bars, stems and error bars survive a log axis. Their baseline is zero, which a
  log axis cannot map, so the geometry came out `NaN` and the series vanished --
  a log-scaled histogram drew an empty panel, and an error bar reaching below
  zero disappeared entirely rather than clamping to the frame. Anchors are now
  clipped into the visible domain, and points that genuinely cannot be mapped
  are skipped rather than emitted as `NaN` coordinates in the SVG.
- Titles and axis labels set *after* `tight_layout` now get space reserved for
  them. The fit was sized from the decorations that existed when it ran, so a
  later `suptitle` was drawn straight over the top row of a grid -- and a figure
  whose title reports its own build time has no other option, since the number
  does not exist until the figure is built. Colorbars and figure legends already
  re-applied their reservations; text now does too, deferred to render so a
  several-hundred-panel grid does not re-lay out once per `set_title`.
- A grid too dense for its decorations shrinks instead of overflowing the
  canvas. `tight_layout` clamped the cell size to a floor while leaving the
  inter-axes gap at full width, so the rows ran off the top edge: the first nine
  rows of a 30x30 grid were placed outside the figure and simply never appeared.
  The gap now gives way first.
- An artist whose data is entirely `nan` no longer prints a RuntimeWarning. A
  fully masked frame is a real case -- an exposure that failed quality control, a
  channel that dropped out for the whole record -- and `errstate` did not
  suppress NumPy's all-NaN warning because it is a warning rather than a
  floating-point condition.
- The PNG backend clips artists to the axes, as the SVG backend's `clipPath`
  already did. It accepted a clip rectangle and ignored it, so any data outside
  the limits was painted across the rest of the figure -- over neighbouring
  subplots, the axis labels and the legend -- in exactly the format the docs and
  most saved figures use.
- `hexbin` derives its row count from `gridsize` alone, as matplotlib does, so
  the lattice no longer depends on the choice of units. Deriving it from the
  ratio of the data ranges meant plotting kilowatts against metres per second
  asked for three thousand rows and drew every bin as a sub-pixel dash.
- A ~1000x `pcolormesh` slowdown: 2-D `X`/`Y` that are secretly rectilinear
  (e.g. `np.meshgrid` output, every row of `X` and column of `Y` constant) now
  route through the vectorized rectilinear path instead of curvilinear
  scan-conversion's per-cell Python loop (6.16s -> 0.009s on a 200x200 grid).
- Point picking on non-uniform or curvilinear `pcolormesh`/`contour` meshes
  matched the wrong cell -- the client bucketed a click by dividing the mesh's
  extent evenly, which only agreed with the real cell boundaries on a uniform
  grid. The payload now carries the actual edges (or per-cell centers for a
  curvilinear mesh).
- An inset axes was permanently unreachable by click/wheel/drag: the hit test
  always resolved to whichever axes was added first (its parent), so the
  inset itself never received the click.
- Twin and secondary axes desynced from their parent on interactive pan/zoom/
  reset -- only the actually-clicked axes' view updated, leaving the other
  frozen, since the two occupy the same pixel rect.
- `cla()`/`clear()` now detaches from a `sharex`/`sharey` group before
  resetting, instead of leaving stale membership that could still receive a
  sibling's `set_xlim`/`set_ylim`.
- Minor ticks now reposition during interactive pan/zoom/reset; they
  previously stayed frozen at their initial positions.
- Polar axes now attach the original `(theta, r)` as pick values on the
  projected line/scatter artist, so picking reports what was actually
  plotted instead of the projected Cartesian `(x, y)`.
- `Axes.tick_params(axis=...)` now actually filters which axis it restyles --
  `axis='x'`/`'y'` previously restyled both axes' ticks regardless.
- `set_xscale`/`set_yscale` now raise a clear error on `PolarAxes`/`Axes3D`
  instead of silently accepting an unhandled `'log'` scale and drawing the
  same figure as if it had never been called.
- `GridSpec(left=, right=, top=, bottom=, wspace=, hspace=)` are now honored
  (applied as the figure's own margins) instead of being silently ignored.

### Changed

- `scatter(marker=...)` and `errorbar(marker=...)` warn when given a shape other
  than a round marker. Only round markers are drawn; accepting the argument and
  silently substituting a dot loses distinctions the shape was carrying, such as
  censored versus observed, with nothing on the figure to reveal it.
- Annotate was briefly two separate tools instead of one -- **Annotate
  Point** locking a note to the nearest pickable datum, **Annotate Free**
  dropping it anywhere on the figure -- before landing on the single
  **Annotation** tool further down in this file; noted here rather than
  left standing, since this section never shipped as its own dated
  release and a reader following it top-to-bottom would otherwise hit a
  tool description that contradicts what the toolbar actually ships with.
- **Both plot-type reference sections split by subject rather than left as one
  long flat list.** The quantum devices field's 52 examples are now five
  fields -- spectroscopy, readout and device maps, coherence and noise, gate
  calibration, and benchmarking -- since sphinx-gallery only nests one level
  of subsection per gallery root, so they sit as siblings of the other
  application fields rather than nested under a single "quantum" page. The
  plot-type reference gallery's 37 flat examples are now five subsections
  (pairwise data, statistical distributions, gridded data, multi-axes layout
  and annotation, animation), alongside the feature-demonstration subsections
  that already existed (axes & figure manipulation, secondary/inset axes,
  polar, 3-D, signal processing, seaborn, limitations). `benchmarks/
  example_timings.py` and `docs/performance.rst` were updated for the new
  subsection paths.
- **The interactive toolbar's Zoom tool now does two distinct things.** A
  rubber-band box drag still zooms one axes in data space, unchanged. The
  wheel now zooms the *whole figure* instead of that same one axes -- it
  rescales the SVG's own viewBox, centered on the cursor, regardless of
  which axes (if any) is under it, and never touches any axes' data range,
  ticks, or pick data. A per-axes wheel zoom only ever affected whichever
  tiny panel the cursor happened to be over, which wasn't a useful "zoom
  out to see the grid" gesture on a figure with many small axes -- the
  whole-figure image zoom is. See `docs/usage.rst`'s Zoom bullet for two
  demo GIFs: one zooming into a cluster of a 30-panel `pcolormesh` grid,
  one on a plain single-axes line plot.
- **The interactive toolbar's built-in tools were renamed, and Reset/Clear
  each split into two more precisely scoped actions.** Renamed for clarity:
  Magnify -> **Pan/Zoom**, Span -> **Axis Span**, Zoom -> **Axis
  Zoom**, Point Pick -> **Point Picking**, Annotate Free -> **Annotation**
  (Annotate Point removed -- Point Picking already covers snapping to a
  datum, and Annotation covers everything else). Split: the single
  **Reset** button is now **Reset All Axes** (per-axes pan/zoom only) and
  **Home** (whole-figure magnification only) -- a single **Clear Points**
  button that used to remove every pin *and* annotation is now **Clear
  Points** (Point Picking pins only) and **Clear Annotations** (Annotation
  notes only), each scoped by the `.plotpress-note` class Annotation notes
  carry -- and the original **Hide Annotations** toggle (which despite the
  name already hid both marker kinds and every boxed callout) is now the
  same **Hide Points**/**Hide Annotations** split, each properly scoped this
  time. Escape clears everything at once and deselects the active tool.
  See `docs/user_guide/interactivity.rst` for the toolbar's current layout
  and the full tool reference -- superseded since this entry by a menu-bar
  redesign, see above.
- `Figure.group()`'s `pad` now also accepts a `(left, right, top, bottom)`
  sequence, not just a single number, for unequal clearance on each side of
  the box -- e.g. tight on the side facing a neighboring group, generous on
  the side carrying the title. See the new
  `docs/examples/grouping/plot_11_unequal_padding.py`.

### Fixed

- **`linestyle=` silently drew a solid line for matplotlib's long-form
  style names.** `plot()`/`hlines()`/`vlines()`/`errorbar()`/`axhline()`/
  `axvline()`/`axline()`/`Figure.group()` all accept `linestyle="--"` short
  form, but matplotlib's equally valid `"dashed"`/`"dotted"`/`"dashdot"`/
  `"solid"` aliases missed both backends' own dash-pattern lookup table
  (keyed by short form only) and silently fell back to a plain solid
  line -- no error, no warning, nothing on the figure to reveal the
  requested style was ignored. Now resolved to the identical dash pattern
  the short form draws. An unrecognized value beyond these (a typo, say)
  now warns instead of silently drawing solid, the same "accept it, don't
  crash, but don't stay silent" choice already made for an unsupported
  marker shape. matplotlib's several spellings for "no connecting line at
  all" (`"none"`/`"None"`/`""`/`" "`, used with `marker=` to show only the
  markers) are unaffected -- still resolve the same way they already did.
  New example: `docs/examples/pairwise/plot_15_linestyles.py`.

## [0.1.0] - 2026-07-26

First public release.

plotpress renders SVG and self-contained interactive HTML through a
matplotlib-shaped API, with no global state and no compiled extension.

### Added

- **Figure/Axes core** with no `pyplot` and no global `rcParams`. A `Figure`
  owns its axes and its own `Style`; two figures never share mutable state.
  `plotpress.subplots()` mirrors `plt.subplots()` without touching globals.
- **Output surfaces**: static vector SVG, raster PNG (Pillow), vector PDF
  (svglib + reportlab), self-contained interactive HTML, inline SVG for
  Jupyter, a native pop-up window (`[gui]` extra), and a PyQt/PySide widget
  (`[qt]` extra).
- **Plot types** covering the core of matplotlib's reference grid: `plot`,
  `scatter`, `bar`/`barh`, `hist`, `step`, `fill_between`, `stem`, `errorbar`,
  `imshow`, `pcolormesh`, `pie`, `boxplot`, `violinplot`, `eventplot`,
  `quiver`, `contour`/`contourf`, `hist2d`, `stackplot`, `hexbin`, `matshow`,
  `spy`, `broken_barh`, `stairs`, `axline`, and `plot_frames`.
- **Signal processing** in pure NumPy: `psd`, `csd`, `cohere`,
  `magnitude_spectrum`, `angle_spectrum`, `phase_spectrum`, `specgram`,
  `xcorr`, `acorr`.
- **Polar and 3-D projections**, projected onto the 2-D core.
- **Axis control**: log scales, equal aspect, shared axes, `twinx`/`twiny`,
  `tight_layout`, colorbars (single or shared across axes), legends, text and
  annotations, and figure-level titles.
- **Colormaps** — viridis, plasma, inferno, magma, cividis, coolwarm, RdBu,
  gray and `_r` variants — with `Normalize`, `LogNorm`, `PowerNorm` and
  `SymLogNorm`.
- **Interactive toolbar** in HTML and pop-up output: per-axes data-space zoom
  and pan with live ticks, point picking with keyboard traversal, in-browser
  annotation, sliders over extra dimensions, and CSV/JSON extraction. The
  JavaScript is inlined and makes no external requests, so it works under
  strict CSPs.
- **Font metrics** for the base-14 metric families — Helvetica, Times and
  Courier, each in regular, bold, italic and bold-italic — plus DejaVu Sans,
  covering their metric-compatible clones (Arial, Liberation Sans/Serif/Mono,
  Arimo, Tinos, Cousine). Families outside those groups are measured as
  Helvetica; `Style(measure_installed_fonts=True)` opts into measuring the font
  files actually installed, trading cross-machine reproducibility for fidelity.
- **Performance** from NumPy rather than native code: vectorized coordinate
  formatting and min/max decimation of huge lines. Against matplotlib on one
  machine, roughly 700x on a 300x300 `pcolormesh`, 40x on an 8x8 axes grid, 8x
  on a 5k-point scatter and 5.5x on a 100k-point line, measured over build plus
  SVG serialization.

### Known limitations

Documented in full at
<https://jrvannucci.github.io/plotpress/user_guide/limitations.html>: font
families outside the bundled metric groups, PNG as a second renderer rather
than a rasterized SVG, approximate density estimates for large samples, 3-D and
polar as projections onto the 2-D core, and no `streamplot`/`barbs`,
triangulation, geographic projections, animation API, rich text or math
rendering.

[Unreleased]: https://github.com/jrvannucci/plotpress/compare/0.1.0...HEAD
[0.1.0]: https://github.com/jrvannucci/plotpress/releases/tag/0.1.0
