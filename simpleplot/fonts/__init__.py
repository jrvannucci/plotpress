"""Bundled font metrics.

SVG-first rendering means we never rasterize glyphs -- the viewer's renderer
does that from the ``<text>`` elements we emit. We only need *metrics* (glyph
advance widths) to size the canvas and align tick/axis labels. Bundled width
tables keep layout deterministic across machines without a font-file
dependency.

``text_width`` measures the base-14 metric families -- Helvetica, Times and
Courier, each in regular / bold / italic / bold-italic -- plus DejaVu Sans.
That covers the metric-compatible clones too: Arial and Liberation Sans are
Helvetica, Liberation Serif and Tinos are Times, Liberation Mono and Cousine
are Courier.

Known limitation
----------------
Because layout happens before anything draws the glyphs, simpleplot has to
*predict* how wide text will be, from the bundled tables only:

* **Families outside those groups are measured as Helvetica.** Verdana, Tahoma,
  Arial Black and Arial Narrow have proprietary metrics that match nothing
  bundled here, so they still render but their legend boxes and axis margins are
  sized for Helvetica.
* **Small sizes quantize.** Renderers round glyph advances to whole pixels, so
  even a perfectly matched face drifts a few tenths of a percent at tick-label
  sizes. This is inherent to laying out text you do not rasterize; it shows up
  as a little slack in margins, never as overlap.

Lifting the first limitation for arbitrary families means measuring real font
files, which makes layout depend on which fonts happen to be installed -- the
very thing these tables exist to avoid. It is therefore offered as an opt-in
rather than refused: see :mod:`simpleplot.fonts.installed` and
``Style(measure_installed_fonts=True)``.

Module layout
-------------
``families``
    The single registry of font families: which width table measures a CSS
    stack, and which files should draw it. Declared together so layout and the
    raster backend cannot disagree about what a family is.
``metrics``
    The bundled width tables and :func:`text_width`. Generated -- see
    ``tools/gen_font_metrics.py`` for the sources.
``installed``
    Opt-in measurement of the real font files on this machine.
"""

from .families import font_files, resolve_family
from .metrics import text_width

__all__ = ["font_files", "resolve_family", "text_width"]
