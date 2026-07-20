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

A figure is laid out *before* anything draws its glyphs, so simpleplot predicts
text width from bundled Helvetica advance widths. **Only Helvetica-metric
families are measured accurately** -- Helvetica, Arial and Liberation Sans agree
to within 0.1%, while Courier New needs ~46% more room than gets reserved for
it and overruns its legend box.

Prefer a family in that safe band. Anything else still renders, but expect to
hand-tune ``figsize`` and spacing.

See :ref:`limitation-font-metrics` for the full table and the reasoning, and
:doc:`../auto_examples/limitations/plot_01_font_metrics` for the measurements.

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
