"""Regenerate ``plotpress/fonts/metrics.py`` from authoritative metric sources.

Run this only when adding a family; the generated table is committed, so a
normal install and test run needs none of the sources below.

    python tools/gen_font_metrics.py > plotpress/fonts/metrics.py

Sources (both come from matplotlib, which is already the ``[bench]`` extra):

* **base-14 AFMs** -- ``mpl-data/fonts/afm``. These are the URW clones
  (Nimbus Sans / Nimbus Roman / Nimbus Mono), which exist precisely to be
  metric-compatible with Adobe's Helvetica / Times / Courier, so their advance
  widths are the base-14 widths.
* **DejaVu Sans** -- ``mpl-data/fonts/ttf``, read through fontTools.

Widths are extracted **by glyph name**, not by the AFM's ``C`` column: that
column is Adobe StandardEncoding, where 39 is ``quoteright`` and 96 is
``quoteleft``. ASCII 39 and 96 are ``quotesingle`` and ``grave``, which have
different widths (191 and 333 vs 222 in Helvetica). Reading by code would
silently mismeasure any string containing an apostrophe or a backtick.
"""

from __future__ import annotations

import os
import re
import sys

# ASCII -> PostScript glyph name. Diverges from StandardEncoding at 39 and 96.
_GLYPH_NAMES = {
    32: "space", 33: "exclam", 34: "quotedbl", 35: "numbersign", 36: "dollar",
    37: "percent", 38: "ampersand", 39: "quotesingle", 40: "parenleft",
    41: "parenright", 42: "asterisk", 43: "plus", 44: "comma", 45: "hyphen",
    46: "period", 47: "slash", 58: "colon", 59: "semicolon", 60: "less",
    61: "equal", 62: "greater", 63: "question", 64: "at", 91: "bracketleft",
    92: "backslash", 93: "bracketright", 94: "asciicircum", 95: "underscore",
    96: "grave", 123: "braceleft", 124: "bar", 125: "braceright",
    126: "asciitilde",
}
for _i, _n in enumerate("zero one two three four five six seven eight nine".split()):
    _GLYPH_NAMES[48 + _i] = _n
for _c in range(65, 91):
    _GLYPH_NAMES[_c] = chr(_c)
for _c in range(97, 123):
    _GLYPH_NAMES[_c] = chr(_c)

# (metric family, bold, italic) -> AFM file in mpl-data/fonts/afm.
_AFM_SOURCES = {
    ("helvetica", False, False): "phvr8a.afm",
    ("helvetica", True, False): "phvb8a.afm",
    ("helvetica", False, True): "phvro8a.afm",
    ("helvetica", True, True): "phvbo8a.afm",
    ("times", False, False): "ptmr8a.afm",
    ("times", True, False): "ptmb8a.afm",
    ("times", False, True): "ptmri8a.afm",
    ("times", True, True): "ptmbi8a.afm",
    ("courier", False, False): "pcrr8a.afm",
    ("courier", True, False): "pcrb8a.afm",
    ("courier", False, True): "pcrro8a.afm",
    ("courier", True, True): "pcrbo8a.afm",
}

_TTF_SOURCES = {
    ("dejavu sans", False, False): "DejaVuSans.ttf",
    ("dejavu sans", True, False): "DejaVuSans-Bold.ttf",
    ("dejavu sans", False, True): "DejaVuSans-Oblique.ttf",
    ("dejavu sans", True, True): "DejaVuSans-BoldOblique.ttf",
}


def _mpl_dir(kind):
    import matplotlib

    return os.path.join(os.path.dirname(matplotlib.__file__),
                        "mpl-data", "fonts", kind)


def _afm_widths(path):
    """ASCII char -> advance width in 1/1000 em, read by glyph name."""
    by_name = {}
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.decode("latin-1")
            if not line.startswith("C "):
                continue
            m = re.match(r"C\s+(-?\d+)\s*;\s*WX\s+(-?\d+)\s*;\s*N\s+(\S+)", line)
            if m:
                by_name[m.group(3)] = int(m.group(2))
    out = {}
    for code, name in _GLYPH_NAMES.items():
        if name not in by_name:
            raise SystemExit(f"{path}: no glyph named {name!r}")
        out[chr(code)] = by_name[name]
    return out


def _ttf_widths(path):
    """Same, scaled from the font's own em square to 1/1000 em."""
    from fontTools.ttLib import TTFont

    font = TTFont(path, lazy=True)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    out = {}
    for code in _GLYPH_NAMES:
        glyph = cmap.get(code)
        if glyph is None:
            raise SystemExit(f"{path}: no glyph for U+{code:04X}")
        out[chr(code)] = round(hmtx[glyph][0] * 1000.0 / upem)
    font.close()
    return out


def _fmt_table(widths):
    """Emit a table as a dict literal, run-compressing the common runs."""
    items = sorted(widths.items(), key=lambda kv: ord(kv[0]))
    lines, row = [], []
    for ch, w in items:
        row.append(f"{ch!r}: {w},")
        if len(row) == 8:
            lines.append("    " + " ".join(row))
            row = []
    if row:
        lines.append("    " + " ".join(row))
    return "\n".join(lines)


def main():
    afm_dir, ttf_dir = _mpl_dir("afm"), _mpl_dir("ttf")
    tables = {}
    for key, fn in _AFM_SOURCES.items():
        tables[key] = _afm_widths(os.path.join(afm_dir, fn))
    for key, fn in _TTF_SOURCES.items():
        tables[key] = _ttf_widths(os.path.join(ttf_dir, fn))

    # Courier is monospaced; assert it rather than emitting 95 copies of 600.
    for bold in (False, True):
        for italic in (False, True):
            w = set(tables[("courier", bold, italic)].values())
            if w != {600}:
                raise SystemExit(f"courier {bold=} {italic=} is not monospaced: {w}")

    out = sys.stdout
    out.write(HEADER)
    for key in sorted(tables):
        if key[0] == "courier":
            continue
        family, bold, italic = key
        name = _const_name(family, bold, italic)
        out.write(f"\n{name} = {{\n{_fmt_table(tables[key])}\n}}\n")
    out.write(FOOTER)


def _const_name(family, bold, italic):
    base = "_" + family.upper().replace(" ", "_").replace("-", "_")
    return base + ("_BOLD" if bold else "") + ("_ITALIC" if italic else "")


HEADER = '''"""Advance-width tables for the fonts plotpress can measure.

GENERATED by ``tools/gen_font_metrics.py`` -- do not edit by hand.

Only the metric matters for layout: we place ``<text>`` and let the renderer
draw glyphs. ``text_width`` estimates a string's rendered width so labels can be
centered / right-aligned and margins sized.

Widths are in 1/1000 em. Sources are the URW base-14 clones (metric-compatible
with Adobe Helvetica / Times / Courier) and the DejaVu Sans TTFs; see the
generator for why they are read by glyph name rather than by character code.

Which table describes a given CSS font stack is decided in ``families.py``,
alongside which files should draw it -- one declaration, so layout and the
raster backend cannot disagree.
"""

from __future__ import annotations

from .families import DEFAULT_METRIC_FAMILY, resolve_family
'''

FOOTER = '''
# Courier and its variants are monospaced: every ASCII glyph is 600/1000 em.
_COURIER_ADVANCE = 600

# Fallback for characters outside the tables -- anything non-ASCII, so degree
# signs, Greek and micro. Each family uses its own digit advance: digits are a
# single uniform width per family and sit mid-range, which makes them a better
# stand-in than a constant borrowed from Helvetica.
_DEFAULTS = {
    "helvetica": 556,
    "times": 500,
    "dejavu sans": 636,
}

# (metric family, bold, italic) -> width table. Oblique/italic keys are present
# for every family, so a lookup never has to fall back across a style boundary.
_TABLES = {
    ("helvetica", False, False): _HELVETICA,
    ("helvetica", True, False): _HELVETICA_BOLD,
    ("helvetica", False, True): _HELVETICA_ITALIC,
    ("helvetica", True, True): _HELVETICA_BOLD_ITALIC,
    ("times", False, False): _TIMES,
    ("times", True, False): _TIMES_BOLD,
    ("times", False, True): _TIMES_ITALIC,
    ("times", True, True): _TIMES_BOLD_ITALIC,
    ("dejavu sans", False, False): _DEJAVU_SANS,
    ("dejavu sans", True, False): _DEJAVU_SANS_BOLD,
    ("dejavu sans", False, True): _DEJAVU_SANS_ITALIC,
    ("dejavu sans", True, True): _DEJAVU_SANS_BOLD_ITALIC,
}

def text_width(text, font_size, family=None, bold=False, italic=False,
               measure_installed=False):
    """Estimated rendered width of ``text`` in pixels at ``font_size`` px.

    ``family`` is a CSS font stack; it is resolved to the nearest bundled
    metric family. ``bold`` / ``italic`` select the matching face, which matters
    because bold Helvetica runs several percent wider than regular.

    ``measure_installed`` opts out of the bundled tables and measures the font
    file actually present on this machine, which is more faithful for families
    plotpress cannot otherwise measure but makes layout depend on what is
    installed. It silently falls back to the bundled tables when no face
    resolves. See :mod:`plotpress.fonts.installed`.
    """
    if measure_installed:
        from .installed import installed_table

        table = installed_table(family, bold, italic)
        if table is not None:
            default = table.get("0", _DEFAULTS[DEFAULT_METRIC_FAMILY])
            units = 0
            for ch in text:
                units += table.get(ch, default)
            return units / 1000.0 * font_size

    resolved = resolve_family(family)
    if resolved == "courier":
        return len(text) * _COURIER_ADVANCE / 1000.0 * font_size
    table = _TABLES[(resolved, bool(bold), bool(italic))]
    default = _DEFAULTS[resolved]
    units = 0
    for ch in text:
        units += table.get(ch, default)
    return units / 1000.0 * font_size
'''


if __name__ == "__main__":
    main()
