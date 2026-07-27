"""Colormaps and normalization for ``pcolormesh`` / mapped scatter.

Colormaps are lookup tables (256x3 uint8). ``viridis`` is stored as a small set
of anchor stops and linearly interpolated to 256 entries at import time to keep
the source compact while staying visually faithful.
"""

from __future__ import annotations

import copy

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
    "viridis": _build_lut(_VIRIDIS_ANCHORS),
    "plasma": _build_lut(_PLASMA_ANCHORS),
    "inferno": _build_lut(_INFERNO_ANCHORS),
    "magma": _build_lut(_MAGMA_ANCHORS),
    "cividis": _build_lut(_CIVIDIS_ANCHORS),
    "coolwarm": _build_lut(_COOLWARM_ANCHORS),
    "RdBu": _build_lut(_RDBU_ANCHORS),
    "gray": _GRAY_LUT,
    "grey": _GRAY_LUT,
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


# Common named colors (CSS/X11 subset + matplotlib single-letter aliases), so
# both the SVG and raster/PDF backends accept names like "red" or "k", not just
# hex. SVG understands the long names natively; the raster backend needs this.
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
}


def to_hex(color: str) -> str:
    """Resolve a color name to ``#rrggbb``; pass hex through unchanged."""
    if not isinstance(color, str):
        return color
    if color.startswith("#"):
        return color
    return NAMED_COLORS.get(color.lower(), color)


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
        A = np.asarray(A, dtype=float)
        if self.vmin is None:
            self.vmin = float(np.nanmin(A))
        if self.vmax is None:
            self.vmax = float(np.nanmax(A))

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
