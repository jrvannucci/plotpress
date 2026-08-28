Styling and colors
==================

Per-figure style
----------------

Each figure owns a :class:`~plotpress.style.Style` (there is no global
``rcParams``). Mutating one figure's style never affects another.

.. code-block:: python

   fig, ax = plotpress.subplots()
   fig.style.line_width = 2.5
   fig.style.font_family = "Liberation Sans, Arial, sans-serif"

.. note::

   Font choice has a caveat worth reading before you change it -- see
   :ref:`fonts-and-layout` below.

Create a variant without mutating the original with ``Style.copy(**overrides)``,
and pass it to :func:`~plotpress.subplots`:

.. code-block:: python

   dark = plotpress.Style(facecolor="#111", text_color="#eee",
                           axes_facecolor="#111", spine_color="#888")
   fig, ax = plotpress.subplots(style=dark)

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

A figure is laid out *before* anything draws its glyphs, so plotpress predicts
text width from bundled advance-width tables. It bundles **Helvetica, Times and
Courier** -- each in regular, bold, italic and bold-italic -- plus **DejaVu
Sans**, which covers their metric-compatible clones too: Arial and Liberation
Sans are measured as Helvetica, Liberation Serif as Times, Liberation Mono as
Courier.

Families outside those groups -- Verdana, Tahoma, Arial Black, Arial Narrow --
have proprietary metrics matching nothing bundled, so they are measured as
Helvetica. They still render, but expect to hand-tune ``figsize`` and spacing.

.. _measure-installed-fonts:

Measuring the fonts you actually have
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you need one of those unmeasurable families to lay out correctly, opt into
measuring the real file::

    style = plotpress.Style(font_family="Verdana, sans-serif",
                             measure_installed_fonts=True)

Verdana is about 14% wider than the Helvetica it is otherwise measured as, so
this widens its margins to what it actually needs. It needs no extra install --
Pillow already ships for PNG export and does the measuring.

It is **off by default**, because it trades away the property the bundled
tables exist to provide: with it on, layout depends on which fonts this machine
has, so the same script can produce different margins on a colleague's box or on
CI. Turn it on when fidelity on your own machine is worth more than
reproducibility across machines. If no candidate file resolves, it silently
falls back to the bundled tables rather than failing.

See :ref:`limitation-font-metrics` for the full table and the reasoning, and
:doc:`../auto_examples/limitations/plot_01_font_metrics` for the measurements.

Colormaps and normalization
---------------------------

24 built-in colormaps -- perceptually uniform (``"viridis"``, ``"plasma"``,
...), sequential (``"Blues"``, ``"YlOrRd"``, ...), diverging
(``"coolwarm"``, ``"Spectral"``, ...), cyclic (``"twilight"``), and a few
classics (``"jet"``, ``"turbo"``). See
:doc:`../auto_examples/gridded_data/plot_11_colormap_reference` for every
one of them as a gradient swatch. Append ``"_r"`` to any name to reverse it.

``plotpress.available_colormaps()``
    List the available colormap names.

``plotpress.get_cmap(name)``
    Return a ``256x3`` uint8 lookup table (or pass an array through).

``plotpress.Normalize(vmin=None, vmax=None)``
    Linearly map data to ``[0, 1]`` for colormapping. Unset limits are inferred
    from the data on first use. Pass to ``pcolormesh``/``imshow``/``scatter`` via
    ``norm=`` (or use the ``vmin``/``vmax`` shortcuts).

    .. code-block:: python

       norm = plotpress.Normalize(0, 1)
       ax.pcolormesh(x, y, Z, cmap="plasma", norm=norm)
