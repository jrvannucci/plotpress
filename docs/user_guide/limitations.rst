.. _limitations:

Limitations
===========

Every one of these is a consequence of a deliberate design choice -- SVG-first
rendering, no compiled extension, no global state. They are documented here so
you can tell in advance whether a trade-off affects your use, rather than
discovering it in a figure. Worked examples with measurements live in the
:ref:`limitations gallery <limitations_gallery>`.

.. _limitation-font-metrics:

Only Helvetica-metric fonts are measured accurately
---------------------------------------------------

A figure is laid out *before* anything draws its glyphs: SVG emits ``<text>``
and the viewer rasterizes it. simpleplot therefore has to **predict** how wide
text will be, and it predicts using a bundled table of Helvetica advance
widths. That keeps layout identical on every machine with no font-file
dependency -- but it is only correct for fonts whose widths match Helvetica's.

.. list-table::
   :header-rows: 1
   :widths: 45 20 35

   * - Family
     - Width vs Helvetica
     - Result
   * - Helvetica, Arial, Liberation Sans
     - within 0.1%
     - accurate (the default stack)
   * - Verdana
     - +16%
     - legend and label text overruns its box
   * - Arial Black
     - +26%
     - overruns
   * - Courier New and monospace faces
     - +46%
     - badly overruns
   * - Arial Narrow and condensed faces
     - -18%
     - margins come out too generous

Anything outside the safe band still renders -- but legend boxes and axis
margins were sized for Helvetica, so expect to hand-tune ``figsize`` and
spacing. See :doc:`../auto_examples/limitations/plot_01_font_metrics`.

**Why not just measure the real font?** Because layout would then depend on
which fonts happen to be installed, and the same script would produce different
margins on different machines. Reading real metrics is possible in pure Python
(``fontTools`` parses a ``.ttf``), so this is a determinism trade-off rather
than a technical barrier. For comparison, matplotlib solves the general problem
by bundling 8.5 MB of fonts and linking FreeType through a C extension.

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
the reference: PDF references the base-14 Helvetica directly and is exact.

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
renders the same way.

Not implemented
---------------

Deliberate omissions, listed so you do not go looking:

* No 3-D axes, no polar or geographic projections.
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
