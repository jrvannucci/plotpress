.. _limitations:

Limitations
===========

Every one of these is a consequence of a deliberate design choice -- SVG-first
rendering, no compiled extension, no global state. They are documented here so
you can tell in advance whether a trade-off affects your use, rather than
discovering it in a figure. Worked examples with measurements live in the
:ref:`limitations gallery <limitations_gallery>`, and the ones about *size* --
where scatter stops scaling, where extra mesh cells stop reaching the screen,
what interactivity costs, and why contour output has no ceiling -- are measured
at :ref:`the foot of the large-scale gallery <scale_limits_gallery>`.

.. _limitation-font-metrics:

Only bundled metric families are measured accurately
----------------------------------------------------

A figure is laid out *before* anything draws its glyphs: SVG emits ``<text>``
and the viewer rasterizes it. plotpress therefore has to **predict** how wide
text will be, and it predicts from bundled advance-width tables. That keeps
layout identical on every machine with no font-file dependency -- but it is
only correct for families those tables describe.

Bundled are the base-14 metric families -- Helvetica, Times and Courier, each
in regular / bold / italic / bold-italic -- plus DejaVu Sans. Any family that
resolves to one of them is measured exactly:

.. list-table::
   :header-rows: 1
   :widths: 45 25 30

   * - Family
     - Measured as
     - Result
   * - Helvetica, Arial, Liberation Sans, Arimo
     - Helvetica
     - accurate (the default stack)
   * - Times New Roman, Liberation Serif, Tinos
     - Times
     - accurate
   * - Courier New, Liberation Mono, Cousine
     - Courier
     - accurate
   * - DejaVu Sans
     - DejaVu Sans
     - accurate
   * - Verdana
     - Helvetica (+16% needed)
     - legend and label text overruns its box
   * - Arial Black
     - Helvetica (+26% needed)
     - overruns
   * - Arial Narrow and condensed faces
     - Helvetica (-18% needed)
     - margins come out too generous

The families in the lower group have proprietary metrics that match nothing
bundled, so they fall back to Helvetica. They still render -- but their legend
boxes and axis margins were sized for the wrong font, so expect to hand-tune
``figsize`` and spacing. See
:doc:`../auto_examples/limitations/plot_01_font_metrics`.

Weight is modelled, style is available
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Bold is not a free variation on regular -- Helvetica-Bold runs 5-9% wider on
realistic label strings. The elements plotpress draws bold (the legend title
and ``suptitle``) are measured with the bold tables, in both the SVG and raster
backends. Italic tables are bundled for the same reason, though nothing in the
default styling draws italic yet.

**Why not just measure the real font?** Because layout would then depend on
which fonts happen to be installed, and the same script would produce different
margins on different machines. This is a determinism trade-off, not a technical
barrier -- so it is offered as a choice rather than refused outright. Set
``Style(measure_installed_fonts=True)`` and plotpress measures the file on this
machine instead, which is the right call when you need an unmeasurable family to
fit and can live with layout that varies across machines. See
:ref:`measure-installed-fonts`.

The measuring is done by Pillow, which is already required for PNG export, so
the option costs no extra install. For comparison, matplotlib solves the general
problem by bundling 8.5 MB of fonts and linking FreeType through a C extension.

The tables themselves are generated from authoritative sources rather than
typed by hand -- see ``tools/gen_font_metrics.py`` -- and a test re-derives them
from those sources to catch drift.

Text width is an estimate, not a measurement
--------------------------------------------

Even with a perfectly compatible font, renderers round each glyph's advance to
a whole pixel while the metrics table is continuous. Predicted and drawn widths
therefore differ slightly.

This is inherent to laying out text you do not rasterize, and it is small: at
the default ``fig.save(..., scale=2)`` supersampling it is about 0.1%. It
shows up as a little slack in a margin, never as overlap. Only ``scale=1``
makes it visible at all.

PNG is a second renderer, not a rasterized SVG
-----------------------------------------------

``fig.save("out.png")`` draws the figure again through Pillow rather than
rasterizing the SVG, because every SVG rasterizer available in Python needs
cairo -- a system library, not a pip wheel. Keeping PNG export dependency-free
means maintaining a parallel backend in ``raster.py``.

Both backends consume the same primitives and the same layout, so output
matches closely, but they are not guaranteed pixel-identical. SVG and PDF are
the reference: PDF references the base-14 Helvetica directly and is exact. The
one visible disagreement is a newline in a label -- see
:doc:`../auto_examples/limitations/plot_03_single_line_text`.

Density estimates are approximate for large samples
----------------------------------------------------

``kdeplot`` and ``violinplot`` use the exact kernel sum for small samples. Above
a few thousand observations that sum's ``grid x n`` intermediate dominates
(~0.9 s and 20M floats at 100k), so they switch to **linear binning**: the data
is binned onto the grid once and the result convolved with the kernel, which is
independent of sample size and handles millions of points in milliseconds.

The binned estimate is an approximation -- typically well under 1% from the
exact curve, and always a proper density that integrates to 1. It is least
accurate where a coarse grid cannot resolve the bandwidth, which happens when
heavy-tailed outliers stretch the range; raise ``points=`` there if the peak
looks blocky. The switch-over is by sample size alone, so a given dataset always
renders the same way. See
:doc:`../auto_examples/limitations/plot_02_kde_binning`.

.. _limitation-polar:

Polar is projected onto the 2-D core
-------------------------------------

Polar (``projection="polar"``) axes are real, but built by projecting the data
into the existing 2-D renderer rather than by a dedicated polar pipeline -- so
a few things follow from that choice:

* **Orientation is fixed before plotting.** ``set_theta_direction`` /
  ``set_theta_zero_location`` project the data as it is added, so they raise if
  called after the first plot.
* Polar covers ``plot``/``scatter``/``fill`` only -- other plot types are not
  polar-aware.

There is no 3-D plotting -- pure-Python and no compiled extension rules out a
real depth-buffered/perspective pipeline, and an orthographic-projection
approximation over the 2-D core (as an earlier version of this library had)
was consistently weaker than dedicated 3-D tools without being meaningfully
simpler to build than doing 2-D well; it was removed rather than kept as a
permanently-second-tier feature.

Not implemented
---------------

Deliberate omissions, listed so you do not go looking:

* No geographic / map projections (these need projection-database and datum
  machinery out of proportion to a pure-Python library).
* No ``streamplot`` / ``barbs``, and no triangulation (``tri*``) plot types.
* No animation API. ``plot_frames`` gives a slider over an extra dimension in
  interactive HTML, which covers the common case.
* No text layout beyond single-line strings -- no rich text, no math/LaTeX
  rendering. A ``\n`` in a label is **not** portable: the raster backend breaks
  the line, while SVG collapses it to a space. Use separate ``text()`` calls if
  you need two lines.
* No tidy-dataframe or semantic-mapping API (``hue=``, ``FacetGrid``). The
  seaborn-style methods take plain arrays.
* No global configuration. This one is the point of the library rather than a
  gap -- see :doc:`architecture`.
