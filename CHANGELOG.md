# Changelog

All notable changes to plotpress are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions come from git tags: a release *is* a tag (e.g. `0.1.0`), and the
package version is derived from it at build time rather than written down
anywhere in the source.

## [Unreleased]

### Added

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
- Annotate is now two separate tools instead of one: **Annotate Point** locks
  a note to the nearest pickable datum, and **Annotate Free** drops it
  anywhere on the figure in figure-fraction coordinates.
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
