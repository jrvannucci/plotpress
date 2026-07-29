# Changelog

All notable changes to plotpress are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions come from git tags: a release *is* a `v*` tag, and the package version
is derived from it at build time rather than written down anywhere in the source.

## [Unreleased]

### Added

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
  Examples now come before applications in the sidebar.
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

### Changed

- `scatter(marker=...)` and `errorbar(marker=...)` warn when given a shape other
  than a round marker. Only round markers are drawn; accepting the argument and
  silently substituting a dot loses distinctions the shape was carrying, such as
  censored versus observed, with nothing on the figure to reveal it.

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
