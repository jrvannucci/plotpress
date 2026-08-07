# Changelog

All notable changes to plotpress are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions come from git tags: a release *is* a `v*` tag, and the package version
is derived from it at build time rather than written down anywhere in the source.

## [Unreleased]

### Fixed

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

[Unreleased]: https://github.com/jrvannucci/plotpress/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jrvannucci/plotpress/releases/tag/v0.1.0
