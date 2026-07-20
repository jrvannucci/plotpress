Styling and colors
==================

Per-figure style
----------------

Each figure owns a :class:`~simpleplot.style.Style` (there is no global
``rcParams``). Mutating one figure's style never affects another.

.. code-block:: python

   fig, ax = simpleplot.subplots()
   fig.style.line_width = 2.5
   fig.style.font_family = "Liberation Sans, Arial, sans-serif"

.. note::

   Font choice has a caveat worth reading before you change it -- see
   :ref:`fonts-and-layout` below.

Create a variant without mutating the original with ``Style.copy(**overrides)``,
and pass it to :func:`~simpleplot.subplots`:

.. code-block:: python

   dark = simpleplot.Style(facecolor="#111", text_color="#eee",
                           axes_facecolor="#111", spine_color="#888")
   fig, ax = simpleplot.subplots(style=dark)

Style fields
------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Field
     - Meaning
   * - ``facecolor``
     - figure background
   * - ``dpi``
     - pixels per inch (figure px = ``figsize * dpi``)
   * - ``axes_facecolor``
     - axes background
   * - ``spine_color`` / ``spine_width``
     - axes frame
   * - ``font_family``
     - CSS font stack for text (see :ref:`fonts-and-layout`)
   * - ``font_size`` / ``title_size`` / ``label_size``
     - text sizes
   * - ``text_color``
     - all text
   * - ``tick_size`` / ``tick_width`` / ``tick_label_size``
     - ticks
   * - ``grid_color`` / ``grid_width`` / ``grid_alpha``
     - grid lines
   * - ``line_width``
     - default line width
   * - ``marker_size``
     - default scatter diameter (points)
   * - ``color_cycle``
     - list of colors cycled per axes (default tab10)

.. _fonts-and-layout:

Fonts and layout
----------------

A figure is laid out *before* anything draws its glyphs -- SVG emits ``<text>``
and the viewer rasterizes it -- so simpleplot has to **predict** how wide text
will be. It predicts using bundled Helvetica advance widths, which keeps layout
identical on every machine with no font-file dependency.

The cost: **only Helvetica-metric families are measured accurately.**

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
     - legend/label text overruns its box
   * - Arial Black
     - +26%
     - overruns
   * - Courier New and monospace faces
     - +46%
     - badly overruns
   * - Arial Narrow and condensed faces
     - -18%
     - margins too generous

Anything outside the safe band still renders -- but legend boxes and axis
margins were sized for Helvetica, so expect to hand-tune ``figsize`` and
spacing. See :doc:`../auto_examples/plot_33_font_metrics` for the measurements
and a worked illustration.

PNG export picks a metric-compatible face to match the layout, falling back to
Pillow's built-in font on machines that have none installed. PDF references the
base-14 Helvetica directly, so it is exact.

Colormaps and normalization
---------------------------

Built-in colormaps: ``"viridis"``, ``"plasma"``, ``"gray"``.

``simpleplot.available_colormaps()``
    List the available colormap names.

``simpleplot.get_cmap(name)``
    Return a ``256x3`` uint8 lookup table (or pass an array through).

``simpleplot.Normalize(vmin=None, vmax=None)``
    Linearly map data to ``[0, 1]`` for colormapping. Unset limits are inferred
    from the data on first use. Pass to ``pcolormesh``/``imshow``/``scatter`` via
    ``norm=`` (or use the ``vmin``/``vmax`` shortcuts).

    .. code-block:: python

       norm = simpleplot.Normalize(0, 1)
       ax.pcolormesh(x, y, Z, cmap="plasma", norm=norm)
