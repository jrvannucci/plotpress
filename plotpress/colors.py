"""Colormaps and normalization for ``pcolormesh`` / mapped scatter.

Colormaps are lookup tables (256x3 uint8). ``viridis`` is stored as a small set
of anchor stops and linearly interpolated to 256 entries at import time to keep
the source compact while staying visually faithful.
"""

from __future__ import annotations

import copy
import re

import numpy as np

# Viridis anchor stops at t = 0.0, 0.1, ... 1.0 (RGB 0-255).
_VIRIDIS_ANCHORS = np.array([
    [68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142],
    [38, 130, 142], [31, 158, 137], [53, 183, 121], [110, 206, 88],
    [181, 222, 43], [221, 227, 24], [253, 231, 37],
], dtype=float)

# Plasma anchor stops.
_PLASMA_ANCHORS = np.array([
    [13, 8, 135], [84, 2, 163], [139, 10, 165], [185, 50, 137],
    [219, 92, 104], [244, 136, 73], [254, 188, 43], [240, 249, 33],
], dtype=float)

# Inferno / magma / cividis: the rest of the perceptually-uniform family.
_INFERNO_ANCHORS = np.array([
    [0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99],
    [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164],
], dtype=float)

_MAGMA_ANCHORS = np.array([
    [0, 0, 4], [28, 16, 68], [79, 18, 123], [129, 37, 129],
    [181, 54, 122], [229, 80, 100], [251, 135, 97], [254, 194, 135],
    [252, 253, 191],
], dtype=float)

_CIVIDIS_ANCHORS = np.array([
    [0, 32, 76], [0, 42, 102], [45, 63, 108], [87, 86, 109],
    [124, 109, 107], [165, 133, 93], [210, 160, 68], [255, 234, 70],
], dtype=float)

# Coolwarm: a blue-white-red diverging map (for signed data around a midpoint).
_COOLWARM_ANCHORS = np.array([
    [59, 76, 192], [124, 159, 249], [192, 212, 245], [221, 221, 221],
    [246, 193, 169], [241, 133, 103], [180, 4, 38],
], dtype=float)

# RdBu: red-white-blue diverging (coolwarm's classic ColorBrewer cousin).
_RDBU_ANCHORS = np.array([
    [178, 24, 43], [214, 96, 77], [244, 165, 130], [247, 247, 247],
    [146, 197, 222], [67, 147, 195], [33, 102, 172],
], dtype=float)

# Spectral: red-orange-yellow-green-blue diverging (ColorBrewer).
_SPECTRAL_ANCHORS = np.array([
    [213, 62, 79], [252, 141, 89], [254, 224, 139], [255, 255, 191],
    [230, 245, 152], [153, 213, 148], [50, 136, 189],
], dtype=float)

# PiYG: pink-white-green diverging (ColorBrewer).
_PIYG_ANCHORS = np.array([
    [197, 27, 125], [233, 163, 201], [253, 224, 239], [247, 247, 247],
    [230, 245, 208], [161, 215, 106], [77, 146, 33],
], dtype=float)

# BrBG: brown-white-teal diverging (ColorBrewer).
_BRBG_ANCHORS = np.array([
    [140, 81, 10], [216, 179, 101], [246, 232, 195], [245, 245, 245],
    [199, 234, 229], [90, 180, 172], [1, 102, 94],
], dtype=float)

# seismic: sharp blue-white-red diverging (matplotlib), for data that pivots
# hard at zero rather than shading gradually through it like coolwarm/RdBu.
_SEISMIC_ANCHORS = np.array([
    [0, 0, 127], [0, 0, 255], [255, 255, 255], [255, 0, 0], [127, 0, 0],
], dtype=float)

# Single-hue sequential family (ColorBrewer): light-to-dark, for data with no
# natural midpoint -- a density, a count, a magnitude.
_BLUES_ANCHORS = np.array([
    [247, 251, 255], [222, 235, 247], [198, 219, 239], [158, 202, 225],
    [107, 174, 214], [49, 130, 189], [8, 81, 156],
], dtype=float)

_GREENS_ANCHORS = np.array([
    [247, 252, 245], [229, 245, 224], [199, 233, 192], [161, 217, 155],
    [116, 196, 118], [49, 163, 84], [0, 109, 44],
], dtype=float)

_ORANGES_ANCHORS = np.array([
    [255, 245, 235], [254, 230, 206], [253, 208, 162], [253, 174, 107],
    [253, 141, 60], [230, 85, 13], [166, 54, 3],
], dtype=float)

_REDS_ANCHORS = np.array([
    [255, 245, 240], [254, 224, 210], [252, 187, 161], [252, 146, 114],
    [251, 106, 74], [222, 45, 38], [165, 15, 21],
], dtype=float)

_PURPLES_ANCHORS = np.array([
    [252, 251, 253], [239, 237, 245], [218, 218, 235], [188, 189, 220],
    [158, 154, 200], [117, 107, 177], [84, 39, 143],
], dtype=float)

# YlOrRd: yellow-orange-red sequential (ColorBrewer) -- a common heatmap map.
_YLORRD_ANCHORS = np.array([
    [255, 255, 178], [254, 217, 118], [254, 178, 76], [253, 141, 60],
    [252, 78, 42], [227, 26, 28], [177, 0, 38],
], dtype=float)

# twilight: cyclic (matplotlib) -- the first and last anchor match, so it
# wraps cleanly for data with no true minimum/maximum, like a phase or angle.
_TWILIGHT_ANCHORS = np.array([
    [23, 22, 25], [76, 66, 127], [152, 137, 192], [223, 206, 208],
    [219, 159, 150], [164, 88, 79], [97, 46, 48], [23, 22, 25],
], dtype=float)

# jet: the classic MATLAB/matplotlib rainbow map. Not perceptually uniform
# (it implies edges in the data where its own hue turns sharply, brightest at
# cyan/yellow -- see docs/scale/limitations' colormap-uniformity example) but
# kept for the code that still asks for it by name.
_JET_ANCHORS = np.array([
    [0, 0, 128], [0, 0, 255], [0, 255, 255], [0, 255, 0],
    [255, 255, 0], [255, 0, 0], [128, 0, 0],
], dtype=float)

# turbo: Google's perceptually-improved rainbow -- similar use case to jet
# (a wide, intuitively-ordered hue sweep) without jet's flat middle band or
# its hard clipping at black/dark red.
_TURBO_ANCHORS = np.array([
    [48, 18, 59], [63, 71, 204], [40, 142, 222], [26, 187, 156],
    [64, 209, 72], [170, 222, 36], [247, 182, 32], [230, 86, 20],
    [122, 4, 3],
], dtype=float)

# hot: black-red-yellow-white -- a thermal/blackbody-radiation ramp.
_HOT_ANCHORS = np.array([
    [0, 0, 0], [255, 0, 0], [255, 255, 0], [255, 255, 255],
], dtype=float)

# cool: a two-stop cyan-to-magenta linear ramp.
_COOL_ANCHORS = np.array([
    [0, 255, 255], [255, 0, 255],
], dtype=float)


def _build_lut(anchors: np.ndarray, n: int = 256) -> np.ndarray:
    """Linearly interpolate anchor stops into an ``(n, 3)`` uint8 LUT."""
    m = anchors.shape[0]
    src = np.linspace(0.0, 1.0, m)
    dst = np.linspace(0.0, 1.0, n)
    lut = np.empty((n, 3), dtype=np.uint8)
    for c in range(3):
        lut[:, c] = np.round(np.interp(dst, src, anchors[:, c])).astype(np.uint8)
    return lut


_GRAY_LUT = np.repeat(np.linspace(0, 255, 256, dtype=np.uint8)[:, None], 3, axis=1)

_COLORMAPS = {
    # Perceptually uniform sequential
    "viridis": _build_lut(_VIRIDIS_ANCHORS),
    "plasma": _build_lut(_PLASMA_ANCHORS),
    "inferno": _build_lut(_INFERNO_ANCHORS),
    "magma": _build_lut(_MAGMA_ANCHORS),
    "cividis": _build_lut(_CIVIDIS_ANCHORS),
    # Single-hue / heat sequential
    "gray": _GRAY_LUT,
    "grey": _GRAY_LUT,
    "Blues": _build_lut(_BLUES_ANCHORS),
    "Greens": _build_lut(_GREENS_ANCHORS),
    "Oranges": _build_lut(_ORANGES_ANCHORS),
    "Reds": _build_lut(_REDS_ANCHORS),
    "Purples": _build_lut(_PURPLES_ANCHORS),
    "YlOrRd": _build_lut(_YLORRD_ANCHORS),
    "hot": _build_lut(_HOT_ANCHORS),
    # Diverging
    "coolwarm": _build_lut(_COOLWARM_ANCHORS),
    "RdBu": _build_lut(_RDBU_ANCHORS),
    "Spectral": _build_lut(_SPECTRAL_ANCHORS),
    "PiYG": _build_lut(_PIYG_ANCHORS),
    "BrBG": _build_lut(_BRBG_ANCHORS),
    "seismic": _build_lut(_SEISMIC_ANCHORS),
    # Cyclic
    "twilight": _build_lut(_TWILIGHT_ANCHORS),
    # Miscellaneous / rainbow
    "jet": _build_lut(_JET_ANCHORS),
    "turbo": _build_lut(_TURBO_ANCHORS),
    "cool": _build_lut(_COOL_ANCHORS),
}


def get_cmap(name) -> np.ndarray:
    """Return a 256x3 uint8 LUT for ``name`` (or pass an LUT through).

    A trailing ``_r`` reverses any known map, e.g. ``"viridis_r"`` -- matching
    matplotlib's reversed-colormap convention.
    """
    if isinstance(name, np.ndarray):
        return name
    key, reverse = name, False
    if isinstance(name, str) and name.endswith("_r"):
        key, reverse = name[:-2], True
    try:
        lut = _COLORMAPS[key]
    except KeyError:
        raise ValueError(
            f"Unknown colormap {name!r}. Available: {available_colormaps()}"
        )
    return lut[::-1].copy() if reverse else lut


def available_colormaps():
    """Named colormaps, including the ``_r`` reversed variants."""
    base = sorted(_COLORMAPS)
    return base + [n + "_r" for n in base]


# Common named colors (the full CSS4/matplotlib named-color set, plus
# matplotlib's single-letter aliases), so both the SVG and raster/PDF
# backends accept any name a matplotlib user would reach for -- "crimson",
# "cornflowerblue" -- not just the handful of X11 basics. SVG understands
# CSS names natively, which used to mask this: a name outside a small table
# still rendered fine in the SVG backend (the browser resolved it), while
# the raster backend's own hex parser crashed on the exact same name with a
# confusing ``int(..., 16)`` error pointing nowhere near the real cause.
NAMED_COLORS = {
    "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "black": "#000000", "white": "#ffffff", "gray": "#808080",
    "grey": "#808080", "orange": "#ffa500", "purple": "#800080",
    "brown": "#a52a2a", "pink": "#ffc0cb", "cyan": "#00ffff",
    "magenta": "#ff00ff", "yellow": "#ffff00", "lime": "#00ff00",
    "navy": "#000080", "teal": "#008080", "olive": "#808000",
    "maroon": "#800000", "silver": "#c0c0c0", "gold": "#ffd700",
    # matplotlib single-letter base colors
    "b": "#0000ff", "g": "#008000", "r": "#ff0000", "c": "#00bfbf",
    "m": "#bf00bf", "y": "#bfbf00", "k": "#000000", "w": "#ffffff",
    # The rest of the CSS4 named-color set (matplotlib.colors.CSS4_COLORS).
    "aliceblue": "#F0F8FF", "antiquewhite": "#FAEBD7", "aqua": "#00FFFF",
    "aquamarine": "#7FFFD4", "azure": "#F0FFFF", "beige": "#F5F5DC", "bisque": "#FFE4C4",
    "blanchedalmond": "#FFEBCD", "blueviolet": "#8A2BE2", "burlywood": "#DEB887",
    "cadetblue": "#5F9EA0", "chartreuse": "#7FFF00", "chocolate": "#D2691E",
    "coral": "#FF7F50", "cornflowerblue": "#6495ED", "cornsilk": "#FFF8DC",
    "crimson": "#DC143C", "darkblue": "#00008B", "darkcyan": "#008B8B",
    "darkgoldenrod": "#B8860B", "darkgray": "#A9A9A9", "darkgreen": "#006400",
    "darkgrey": "#A9A9A9", "darkkhaki": "#BDB76B", "darkmagenta": "#8B008B",
    "darkolivegreen": "#556B2F", "darkorange": "#FF8C00", "darkorchid": "#9932CC",
    "darkred": "#8B0000", "darksalmon": "#E9967A", "darkseagreen": "#8FBC8F",
    "darkslateblue": "#483D8B", "darkslategray": "#2F4F4F", "darkslategrey": "#2F4F4F",
    "darkturquoise": "#00CED1", "darkviolet": "#9400D3", "deeppink": "#FF1493",
    "deepskyblue": "#00BFFF", "dimgray": "#696969", "dimgrey": "#696969",
    "dodgerblue": "#1E90FF", "firebrick": "#B22222", "floralwhite": "#FFFAF0",
    "forestgreen": "#228B22", "fuchsia": "#FF00FF", "gainsboro": "#DCDCDC",
    "ghostwhite": "#F8F8FF", "goldenrod": "#DAA520", "greenyellow": "#ADFF2F",
    "honeydew": "#F0FFF0", "hotpink": "#FF69B4", "indianred": "#CD5C5C", "indigo": "#4B0082",
    "ivory": "#FFFFF0", "khaki": "#F0E68C", "lavender": "#E6E6FA",
    "lavenderblush": "#FFF0F5", "lawngreen": "#7CFC00", "lemonchiffon": "#FFFACD",
    "lightblue": "#ADD8E6", "lightcoral": "#F08080", "lightcyan": "#E0FFFF",
    "lightgoldenrodyellow": "#FAFAD2", "lightgray": "#D3D3D3", "lightgreen": "#90EE90",
    "lightgrey": "#D3D3D3", "lightpink": "#FFB6C1", "lightsalmon": "#FFA07A",
    "lightseagreen": "#20B2AA", "lightskyblue": "#87CEFA", "lightslategray": "#778899",
    "lightslategrey": "#778899", "lightsteelblue": "#B0C4DE", "lightyellow": "#FFFFE0",
    "limegreen": "#32CD32", "linen": "#FAF0E6", "mediumaquamarine": "#66CDAA",
    "mediumblue": "#0000CD", "mediumorchid": "#BA55D3", "mediumpurple": "#9370DB",
    "mediumseagreen": "#3CB371", "mediumslateblue": "#7B68EE",
    "mediumspringgreen": "#00FA9A", "mediumturquoise": "#48D1CC",
    "mediumvioletred": "#C71585", "midnightblue": "#191970", "mintcream": "#F5FFFA",
    "mistyrose": "#FFE4E1", "moccasin": "#FFE4B5", "navajowhite": "#FFDEAD",
    "oldlace": "#FDF5E6", "olivedrab": "#6B8E23", "orangered": "#FF4500",
    "orchid": "#DA70D6", "palegoldenrod": "#EEE8AA", "palegreen": "#98FB98",
    "paleturquoise": "#AFEEEE", "palevioletred": "#DB7093", "papayawhip": "#FFEFD5",
    "peachpuff": "#FFDAB9", "peru": "#CD853F", "plum": "#DDA0DD", "powderblue": "#B0E0E6",
    "rebeccapurple": "#663399", "rosybrown": "#BC8F8F", "royalblue": "#4169E1",
    "saddlebrown": "#8B4513", "salmon": "#FA8072", "sandybrown": "#F4A460",
    "seagreen": "#2E8B57", "seashell": "#FFF5EE", "sienna": "#A0522D", "skyblue": "#87CEEB",
    "slateblue": "#6A5ACD", "slategray": "#708090", "slategrey": "#708090",
    "snow": "#FFFAFA", "springgreen": "#00FF7F", "steelblue": "#4682B4", "tan": "#D2B48C",
    "thistle": "#D8BFD8", "tomato": "#FF6347", "turquoise": "#40E0D0", "violet": "#EE82EE",
    "wheat": "#F5DEB3", "whitesmoke": "#F5F5F5", "yellowgreen": "#9ACD32",
}

#: SVG/CSS paint keywords that are deliberately *not* colors -- passed
#: through as-is rather than resolved. ``_BBOX_DEFAULTS["edgecolor"]`` and
#: several call sites use ``"none"`` as "draw nothing"; ``"transparent"`` is
#: the equivalent CSS keyword a caller might reach for instead.
_PAINT_KEYWORDS = frozenset(("none", "transparent"))

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def to_hex(color: str) -> str:
    """Resolve a color name to ``#rrggbb``; pass hex (and the ``"none"``/
    ``"transparent"`` paint keywords) through unchanged.

    Raises ``ValueError`` for anything else unrecognized -- a misspelled
    name (``"crimon"``) or malformed hex (``"#zzzzzz"``). Letting either
    through unresolved, as this used to, meant it reached the SVG backend as
    a bare, invalid ``stroke``/``fill`` value (a browser silently treats
    that as unset, so the artist just doesn't render -- no error anywhere)
    or the raster backend's hex parser, which fails with a bare
    ``int(..., 16)`` error that never mentions the color was the problem.
    """
    if not isinstance(color, str):
        return color
    if color.lower() in _PAINT_KEYWORDS:
        return color
    if color.startswith("#"):
        if not _HEX_RE.match(color):
            raise ValueError(
                f"Invalid hex color {color!r} -- expected '#rgb' or '#rrggbb'."
            )
        return color
    resolved = NAMED_COLORS.get(color.lower())
    if resolved is None:
        raise ValueError(
            f"Unknown color {color!r}. Use a '#rrggbb'/'#rgb' hex code, an "
            "RGB(A) tuple, or a named CSS color (e.g. 'crimson', 'steelblue')."
        )
    return resolved


class Normalize:
    """Linearly map data to [0, 1] using ``vmin``/``vmax``.

    Unset limits are inferred from the data on first use. That inference writes
    back to the instance, so artists take a private copy (see
    :func:`resolve_norm`) rather than scaling the norm you handed them -- one
    norm passed to two figures would otherwise pin the second to the first's
    data range.
    """

    def __init__(self, vmin=None, vmax=None):
        self.vmin = vmin
        self.vmax = vmax

    def autoscale_none(self, A):
        """Fill unset limits from the data, tolerating a fully masked field.

        A frame where every cell is ``nan`` is a real case, not a mistake -- a
        detector exposure that failed quality control, a tile with no coverage,
        one panel of a stack that a shared norm still has to accept. NumPy's
        ``nanmin`` warns on an all-NaN slice and returns NaN, which then
        propagated into the transform; fall back to a unit range instead, since
        there is nothing to scale and every cell will be drawn transparent.
        """
        A = np.asarray(A, dtype=float)
        finite = A[np.isfinite(A)] if A.size else A
        if self.vmin is None:
            self.vmin = float(finite.min()) if finite.size else 0.0
        if self.vmax is None:
            self.vmax = float(finite.max()) if finite.size else 1.0

    def __call__(self, A):
        A = np.asarray(A, dtype=float)
        self.autoscale_none(A)
        span = self.vmax - self.vmin
        if span == 0:
            span = 1.0
        return (A - self.vmin) / span


class LogNorm(Normalize):
    """Map data to [0, 1] on a **log10** scale between ``vmin`` and ``vmax``.

    Non-positive values map to NaN (rendered transparent, like matplotlib's
    masked handling). Unset limits are inferred from the positive data.
    """

    def autoscale_none(self, A):
        A = np.asarray(A, dtype=float)
        if self.vmin is None or self.vmax is None:
            pos = A[np.isfinite(A) & (A > 0)]
            if self.vmin is None:
                self.vmin = float(pos.min()) if pos.size else 1e-10
            if self.vmax is None:
                self.vmax = float(pos.max()) if pos.size else 1.0

    def __call__(self, A):
        A = np.asarray(A, dtype=float)
        self.autoscale_none(A)
        vmin = max(self.vmin, 1e-300)
        lmin, lmax = np.log10(vmin), np.log10(max(self.vmax, vmin * 10))
        span = (lmax - lmin) or 1.0
        with np.errstate(divide="ignore", invalid="ignore"):
            logA = np.log10(np.where(A > 0, A, np.nan))
        return (logA - lmin) / span


class PowerNorm(Normalize):
    """Map data to [0, 1] then raise to ``gamma`` (matplotlib's PowerNorm).

    ``gamma < 1`` emphasizes low values, ``gamma > 1`` the high end.
    """

    def __init__(self, gamma=1.0, vmin=None, vmax=None):
        super().__init__(vmin, vmax)
        self.gamma = float(gamma)

    def __call__(self, A):
        A = np.asarray(A, dtype=float)
        self.autoscale_none(A)
        span = (self.vmax - self.vmin) or 1.0
        t = np.clip((A - self.vmin) / span, 0.0, 1.0)
        return np.power(t, self.gamma)


class SymLogNorm(Normalize):
    """Symmetric-log mapping: linear within ``+/-linthresh``, log beyond.

    Handles data spanning zero and both signs (matplotlib's SymLogNorm).
    """

    def __init__(self, linthresh, vmin=None, vmax=None):
        super().__init__(vmin, vmax)
        self.linthresh = float(linthresh)

    def _symlog(self, x):
        lt = self.linthresh
        x = np.asarray(x, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            far = np.sign(x) * (1.0 + np.log10(np.abs(x) / lt))
        return np.where(np.abs(x) <= lt, x / lt, far)

    def __call__(self, A):
        A = np.asarray(A, dtype=float)
        self.autoscale_none(A)
        lo, hi = self._symlog(self.vmin), self._symlog(self.vmax)
        span = (hi - lo) or 1.0
        return (self._symlog(A) - lo) / span


def resolve_norm(norm, vmin=None, vmax=None) -> Normalize:
    """Return the norm instance an artist should own.

    A caller-supplied norm is *copied*. Autoscaling mutates ``vmin``/``vmax`` in
    place, so without this the first artist to use a norm would pin it for every
    later one -- including artists on a different figure, which is exactly the
    shared mutable state this library sets out not to have. Copying keeps the
    caller's object pristine and makes each artist's scaling depend only on its
    own data.

    Limits set explicitly on the norm survive the copy, so passing one
    ``Normalize(0, 100)`` to several artists still puts them on a common scale.
    """
    if norm is None:
        return Normalize(vmin, vmax)
    return copy.copy(norm)


def colorbar_ticks(norm):
    """Tick ``(values, fractions, labels)`` for a colorbar honoring ``norm``.

    The gradient strip is an even colormap ramp; ticks are positioned at
    ``norm(value)`` (their fractional height), so a ``LogNorm``/``PowerNorm``/
    ``SymLogNorm`` colorbar places its labels correctly instead of linearly.
    """
    from .ticker import format_ticks, log_ticks, nice_ticks

    vmin, vmax = norm.vmin, norm.vmax
    vals = log_ticks(vmin, vmax) if isinstance(norm, LogNorm) else nice_ticks(vmin, vmax)
    vals = np.asarray(vals, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        fracs = np.asarray(norm(vals), dtype=float)
    keep = np.isfinite(fracs) & (fracs >= -1e-9) & (fracs <= 1 + 1e-9)
    vals, fracs = vals[keep], np.clip(fracs[keep], 0.0, 1.0)
    return vals, fracs, format_ticks(vals)


def apply_colormap(A, lut, norm: Normalize) -> np.ndarray:
    """Map data array ``A`` to an RGBA uint8 array. NaNs become transparent."""
    normed = norm(A)
    finite = np.isfinite(normed)
    idx = np.clip(np.nan_to_num(normed) * (lut.shape[0] - 1), 0, lut.shape[0] - 1)
    idx = idx.astype(np.intp)
    rgb = lut[idx]
    alpha = np.where(finite, 255, 0).astype(np.uint8)
    return np.concatenate([rgb, alpha[..., None]], axis=-1)
