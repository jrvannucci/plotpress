"""Bundled font metrics.

SVG-first rendering means we never rasterize glyphs -- the viewer's renderer
does that from the ``<text>`` elements we emit. We only need *metrics* (glyph
advance widths) to size the canvas and align tick/axis labels. A compact,
bundled Helvetica-like width table keeps layout deterministic across machines
without a font-file dependency. (For custom-font metrics, ``fontTools`` -- a
pure-Python wheel -- could parse a supplied ``.ttf``.)
"""

from .metrics import text_width

__all__ = ["text_width"]
