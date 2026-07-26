"""The one place that knows about font families.

Two consumers need to answer questions about a CSS font stack, and they must
not disagree:

* **layout** (``fonts.metrics``) asks *which width table describes this stack*,
  because it sizes margins and legend boxes before anything is drawn;
* **the raster backend** asks *which font file should draw these glyphs*,
  because PNG export rasterizes them itself.

Splitting those tables across two modules is how you get glyphs drawn from a
face that does not match the space reserved for them. So a family is declared
once here, with both answers attached, and the fallback chain is derived from
the declaration rather than written out by hand.

The derivation rule: a stack's candidate files always end with faces belonging
to its own *metric* family. That is what keeps the fallback safe. DejaVu Serif
is 29% wider than Times and DejaVu Sans is 14% wider than Helvetica, so putting
either at the end of a chain whose layout was computed from Times or Helvetica
metrics silently overflows every box on a machine that has no better face
installed.
"""

from __future__ import annotations

from collections import namedtuple

# ``metrics`` is the key into the bundled width tables; ``regular``/``bold`` are
# candidate file names for the raster backend, best first.
_Family = namedtuple("_Family", "metrics regular bold")

# Faces belonging to each metric family, in rough platform order (macOS,
# Windows, Linux). Every one of these agrees with the width table it is filed
# under, which is what makes them safe fallbacks.
HELVETICA_FILES = (
    "Helvetica.ttc", "Helvetica.ttf",
    "arial.ttf", "Arial.ttf",
    "LiberationSans-Regular.ttf",
    "Arimo-Regular.ttf",
)
HELVETICA_FILES_BOLD = (
    "Helvetica-Bold.ttf",
    "arialbd.ttf", "Arial Bold.ttf",
    "LiberationSans-Bold.ttf",
    "Arimo-Bold.ttf",
)
TIMES_FILES = (
    "Times New Roman.ttf", "times.ttf",
    "LiberationSerif-Regular.ttf",
    "Tinos-Regular.ttf",
)
TIMES_FILES_BOLD = (
    "Times New Roman Bold.ttf", "timesbd.ttf",
    "LiberationSerif-Bold.ttf",
    "Tinos-Bold.ttf",
)
# DejaVu Sans Mono earns its place here: it advances 602/1000 em against
# Courier's flat 600, so it is Courier-metric to within a third of a percent.
# Its sans and serif siblings are not, and are deliberately absent elsewhere.
COURIER_FILES = (
    "Courier New.ttf", "cour.ttf",
    "LiberationMono-Regular.ttf",
    "Cousine-Regular.ttf",
    "DejaVuSansMono.ttf",
)
COURIER_FILES_BOLD = (
    "Courier New Bold.ttf", "courbd.ttf",
    "LiberationMono-Bold.ttf",
    "Cousine-Bold.ttf",
    "DejaVuSansMono-Bold.ttf",
)
DEJAVU_FILES = ("DejaVuSans.ttf",)
DEJAVU_FILES_BOLD = ("DejaVuSans-Bold.ttf",)

_METRIC_FILES = {
    "helvetica": (HELVETICA_FILES, HELVETICA_FILES_BOLD),
    "times": (TIMES_FILES, TIMES_FILES_BOLD),
    "courier": (COURIER_FILES, COURIER_FILES_BOLD),
    "dejavu sans": (DEJAVU_FILES, DEJAVU_FILES_BOLD),
}

DEFAULT_METRIC_FAMILY = "helvetica"

_FAMILIES = {
    # -- Helvetica and its metric-compatible clones -----------------------
    "helvetica": _Family("helvetica", HELVETICA_FILES, HELVETICA_FILES_BOLD),
    "helvetica neue": _Family("helvetica", ("HelveticaNeue.ttc",),
                              ("HelveticaNeue-Bold.ttf",)),
    "arial": _Family("helvetica", ("arial.ttf", "Arial.ttf"),
                     ("arialbd.ttf", "Arial Bold.ttf")),
    "liberation sans": _Family("helvetica", ("LiberationSans-Regular.ttf",),
                               ("LiberationSans-Bold.ttf",)),
    "arimo": _Family("helvetica", ("Arimo-Regular.ttf",), ("Arimo-Bold.ttf",)),
    "nimbus sans": _Family("helvetica", ("NimbusSans-Regular.otf",),
                           ("NimbusSans-Bold.otf",)),
    "sans-serif": _Family("helvetica", HELVETICA_FILES, HELVETICA_FILES_BOLD),

    # -- Times and its metric-compatible clones ---------------------------
    "times": _Family("times", TIMES_FILES, TIMES_FILES_BOLD),
    "times new roman": _Family("times", ("Times New Roman.ttf", "times.ttf"),
                               ("Times New Roman Bold.ttf", "timesbd.ttf")),
    "liberation serif": _Family("times", ("LiberationSerif-Regular.ttf",),
                                ("LiberationSerif-Bold.ttf",)),
    "tinos": _Family("times", ("Tinos-Regular.ttf",), ("Tinos-Bold.ttf",)),
    "nimbus roman": _Family("times", ("NimbusRoman-Regular.otf",),
                            ("NimbusRoman-Bold.otf",)),
    "serif": _Family("times", TIMES_FILES, TIMES_FILES_BOLD),

    # -- Courier and its metric-compatible clones -------------------------
    "courier": _Family("courier", COURIER_FILES, COURIER_FILES_BOLD),
    "courier new": _Family("courier", ("Courier New.ttf", "cour.ttf"),
                           ("Courier New Bold.ttf", "courbd.ttf")),
    "liberation mono": _Family("courier", ("LiberationMono-Regular.ttf",),
                               ("LiberationMono-Bold.ttf",)),
    "cousine": _Family("courier", ("Cousine-Regular.ttf",), ("Cousine-Bold.ttf",)),
    "nimbus mono": _Family("courier", ("NimbusMonoPS-Regular.otf",),
                           ("NimbusMonoPS-Bold.otf",)),
    "monospace": _Family("courier", COURIER_FILES, COURIER_FILES_BOLD),

    # -- DejaVu -----------------------------------------------------------
    "dejavu sans": _Family("dejavu sans", DEJAVU_FILES, DEJAVU_FILES_BOLD),

    # -- Declared, but not measurable -------------------------------------
    # Proprietary metrics that match no bundled table, so layout measures them
    # as Helvetica -- see the limitations docs. They are listed anyway so PNG
    # export can still draw their real glyphs where the system has them; the
    # derivation rule then tails the chain with Helvetica-metric faces rather
    # than with whatever happens to look similar.
    "verdana": _Family("helvetica", ("verdana.ttf", "Verdana.ttf"),
                       ("verdanab.ttf", "Verdana Bold.ttf")),
    "tahoma": _Family("helvetica", ("tahoma.ttf", "Tahoma.ttf"),
                      ("tahomabd.ttf", "Tahoma Bold.ttf")),
    "arial narrow": _Family("helvetica", ("ARIALN.TTF", "Arial Narrow.ttf"),
                            ("ARIALNB.TTF", "Arial Narrow Bold.ttf")),
    "arial black": _Family("helvetica", ("ariblk.ttf", "Arial Black.ttf"), ()),
}


def _names(family):
    """The stack, lowercased and unquoted, in order."""
    return [n.strip().strip("'\"").lower()
            for n in (family or "").split(",") if n.strip()]


def resolve_family(family):
    """The metric family describing the first recognized name in a CSS stack.

    Unknown names are skipped, so a stack naming an unmeasurable face first
    still finds a measurable fallback behind it. A stack with no recognized
    name at all resolves to Helvetica, which is what layout has always assumed.
    """
    for name in _names(family):
        entry = _FAMILIES.get(name)
        if entry is not None:
            return entry.metrics
    return DEFAULT_METRIC_FAMILY


def font_files(family, bold=False):
    """Candidate font files for a CSS stack, best first.

    The chain is: the faces each named family actually is, then the faces of
    the metric family layout measured it with, then -- for a bold request --
    the same chain at regular weight, since the right glyphs at the wrong
    weight beat the wrong glyphs entirely.

    It ends with the Helvetica faces as a last resort. For a non-Helvetica
    metric family that is a compromise rather than a match: it keeps a machine
    with no serif or mono face installed rendering, but Helvetica glyphs are
    wider than the Times metrics the layout used, so text can overflow. It
    still beats Pillow's built-in bitmap default, which is both wider and
    unscalable.
    """
    out = []

    def add(names):
        for f in names:
            if f not in out:
                out.append(f)

    for name in _names(family):
        entry = _FAMILIES.get(name)
        if entry is not None:
            add(entry.bold if bold else entry.regular)

    regular_files, bold_files = _METRIC_FILES[resolve_family(family)]
    add(bold_files if bold else regular_files)
    if bold:
        add(font_files(family, bold=False))
    add(HELVETICA_FILES_BOLD if bold else ())
    add(HELVETICA_FILES)
    return out
