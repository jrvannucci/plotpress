"""Bundled font metrics.

SVG-first rendering means we never rasterize glyphs -- the viewer's renderer
does that from the ``<text>`` elements we emit. We only need *metrics* (glyph
advance widths) to size the canvas and align tick/axis labels. A compact,
bundled Helvetica-like width table keeps layout deterministic across machines
without a font-file dependency.

Known limitation
----------------
Because layout happens before anything draws the glyphs, simpleplot has to
*predict* how wide text will be, and it always predicts with Helvetica widths.
Two consequences:

* **Only Helvetica-metric families are accurate.** Helvetica, Arial and
  Liberation Sans are metric-compatible by design and agree to within 0.1%.
  Setting ``Style.font_family`` to something else still renders, but legend
  boxes and axis margins are sized for Helvetica: Courier New measures ~46%
  wider than reserved, Arial Narrow ~18% narrower.
* **Small sizes quantize.** Renderers round glyph advances to whole pixels, so
  even a perfectly compatible face drifts a few percent at tick-label sizes.
  This is inherent to laying out text you do not rasterize; it shows up as a
  little slack in margins, never as overlap.

Lifting the first limitation means measuring real font files -- ``fontTools``
parses a ``.ttf`` in pure Python -- but that makes layout depend on which fonts
happen to be installed, which is exactly what this table exists to avoid.
"""

from .metrics import text_width

__all__ = ["text_width"]
