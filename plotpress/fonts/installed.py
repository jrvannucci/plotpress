"""Opt-in measurement of the fonts actually installed on this machine.

Off by default, and deliberately so. plotpress's bundled width tables exist to
make layout *deterministic*: the same script produces the same margins on every
machine, because it never asks the machine anything. Turning this on trades that
guarantee for fidelity, and it is a real trade -- a figure laid out here may not
match one laid out on a colleague's box, or on CI.

Turn it on when the fidelity is worth more than the reproducibility: you are
setting ``Style.font_family`` to a face plotpress cannot measure (Verdana,
Tahoma, Arial Black, Arial Narrow) and you would rather have correct margins on
your own machine than portable ones.

    fig, ax = plotpress.subplots(
        style=plotpress.Style(font_family="Verdana, sans-serif",
                               measure_installed_fonts=True))

Implementation note: this needs no new dependency. Pillow is already required
for PNG export, it already resolves a bare font file name against the system
font directories, and it already measures glyph advances -- the same machinery
the raster backend draws with. Reusing it is what keeps layout and PNG output
agreeing about what a face is: both go through
:func:`plotpress.fonts.families.font_files`.
"""

from __future__ import annotations

# Measured once at a large em square and scaled down, rather than at each label's
# real size: advances are linear in size, so one probe serves every size, and a
# big probe makes per-glyph integer rounding negligible.
_PROBE_EM = 1000

_ASCII = [chr(c) for c in range(32, 127)]

_table_cache = {}


def installed_table(family, bold=False, italic=False):
    """``{char: advance per 1000 em}`` from a real font file, or ``None``.

    Returns ``None`` -- meaning "fall back to the bundled tables" -- when no
    candidate file resolves, or when Pillow was built without FreeType and so
    cannot open a scalable face at all.

    ``italic`` is accepted for signature parity with the bundled path but does
    not select a different file: the family registry tracks weight, not slant,
    since nothing in the default styling draws italic.
    """
    key = (family, bool(bold))
    if key in _table_cache:
        return _table_cache[key]

    table = _measure(family, bool(bold))
    _table_cache[key] = table
    return table


def _measure(family, bold):
    try:
        from PIL import ImageFont
    except ImportError:                      # pragma: no cover - Pillow is required
        return None

    from .families import font_files

    for name in font_files(family, bold):
        try:
            font = ImageFont.truetype(name, _PROBE_EM)
        except (OSError, ImportError):
            # Not installed here, or this Pillow has no FreeType. Either way the
            # next candidate might still work.
            continue
        try:
            return {ch: font.getlength(ch) for ch in _ASCII}
        except (OSError, ValueError):        # pragma: no cover - malformed face
            continue
    return None


def clear_cache():
    """Forget measured faces. Only useful in tests, or if fonts change on disk."""
    _table_cache.clear()
