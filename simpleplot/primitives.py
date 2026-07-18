"""Backend-agnostic drawing primitives in **pixel space**.

The geometry of an artist (applying the transform, splitting on NaN, decimating
huge lines, computing quad corners) is computed *once* here, producing a small
fixed vocabulary of primitives. Each backend (:mod:`simpleplot.svg`,
:mod:`simpleplot.raster`) then only needs to know how to draw those few
primitive types -- so a new artist that emits, say, a filled polygon needs no
new code in either backend.

``artist_to_prims(artist, tr, ai, k)`` returns the primitives for a migrated
artist, or ``None`` if the artist still uses its legacy per-backend renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from .artists import (
    AxLine, FillBetween, HLine, Image, Line2D, LineCollection, Polygon,
    PolyCollection, QuadMesh, Rug, ScatterCollection, Span, VLine,
)

# Lines longer than this are min/max-decimated per pixel column before drawing
# (monotonic x only), the pure-Python analogue of matplotlib's path
# simplification: huge time-series lines draw ~7x faster and ~40x smaller with
# no visible change, keeping the output vector.
_DECIMATE_MIN_POINTS = 5000


def _is_monotonic(x: np.ndarray) -> bool:
    d = np.diff(x)
    return bool(np.all(d >= 0) or np.all(d <= 0))


def _decimate_minmax(x, y, ncols):
    """Keep first/last/min-y/max-y per pixel column (monotonic x only)."""
    n = x.size
    if n <= 4 * ncols or ncols < 1:
        return x, y
    x0, x1 = float(x[0]), float(x[-1])
    span = (x1 - x0) or 1.0
    col = np.clip(((x - x0) / span * ncols).astype(np.intp), 0, ncols - 1)
    keep = np.zeros(n, bool)
    runstart = np.empty(n, bool); runstart[0] = True; runstart[1:] = col[1:] != col[:-1]
    runend = np.empty(n, bool); runend[-1] = True; runend[:-1] = col[1:] != col[:-1]
    keep |= runstart | runend
    order = np.lexsort((y, col))
    sc = col[order]
    lo = np.empty(n, bool); lo[0] = True; lo[1:] = sc[1:] != sc[:-1]
    hi = np.empty(n, bool); hi[-1] = True; hi[:-1] = sc[1:] != sc[:-1]
    keep[order[lo]] = True
    keep[order[hi]] = True
    idx = np.flatnonzero(keep)
    return x[idx], y[idx]


def _finite_subpaths(pts):
    """Split an (N,2) pixel array into contiguous finite runs."""
    mask = np.isfinite(pts).all(axis=1)
    if mask.all():
        return [pts] if len(pts) else []
    out = []
    n = len(pts)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        out.append(pts[i:j])
        i = j
    return out


# -- primitive vocabulary ---------------------------------------------------
@dataclass
class Path:
    """A stroked and/or filled path of one or more subpaths (pixel coords)."""
    subpaths: List[np.ndarray]
    closed: bool = False
    element: str = "path"          # "path" or "polygon" (single closed subpath)
    stroke: Optional[str] = None
    stroke_width: float = 1.0
    linestyle: str = "-"
    stroke_opacity: float = 1.0
    stroke_round: bool = False
    fill: Optional[str] = None
    fill_opacity: float = 1.0
    series_id: Optional[str] = None
    label: str = ""


@dataclass
class Line:
    """A single straight segment (axvline / axhline / axline)."""
    p0: tuple
    p1: tuple
    stroke: str
    stroke_width: float
    linestyle: str = "-"
    stroke_opacity: float = 1.0
    label: str = ""


@dataclass
class Rect:
    """An axis-aligned filled rectangle (axhspan / axvspan)."""
    x: float
    y: float
    w: float
    h: float
    fill: str
    fill_opacity: float = 1.0
    label: str = ""


@dataclass
class Segments:
    """A batch of independent line segments (hlines / vlines)."""
    segs: np.ndarray               # (N, 4): x0, y0, x1, y1
    stroke: str
    stroke_width: float
    linestyle: str = "-"
    stroke_opacity: float = 1.0
    label: str = ""


@dataclass
class PolygonBatch:
    """Many filled polygons with per-polygon colors (hexbin)."""
    polys: List[np.ndarray]        # list of (k, 2)
    fills: list                    # per-poly color (str or rgb triple)
    edge: Optional[str] = None
    edge_width: float = 0.4
    alpha: float = 1.0
    label: str = ""


@dataclass
class ImagePrim:
    """An RGBA raster placed at a pixel rect (pcolormesh / imshow / contourf)."""
    rgba: np.ndarray               # (H, W, 4) uint8
    x: float
    y: float
    w: float
    h: float


@dataclass
class Markers:
    """A batch of round point markers (scatter), constant-size in pixels."""
    points: np.ndarray             # (N, 2) pixel centers (may contain NaN)
    diameters: np.ndarray          # (N,) pixel diameters
    colors: list                   # per-point color strings (len N)
    single_color: bool = True      # all points share one color (fewer nodes)
    alpha: float = 1.0
    series_id: Optional[str] = None
    label: str = ""


# -- artist -> primitives ---------------------------------------------------
def artist_to_prims(artist, tr, ai, k, size_scale=1.0):
    """Primitives for a migrated artist, or None to use its legacy renderer.

    ``size_scale`` converts marker sizes from points to this backend's pixels
    (``dpi/72`` for SVG, ``dpi/72 * S`` for the supersampled raster).
    """
    a = artist
    lbl = a.label or "" if getattr(a, "label", None) else ""

    if isinstance(a, ScatterCollection):
        pts = tr.xy(a.x, a.y)
        diam = np.broadcast_to(np.asarray(a.s, float), a.x.shape).astype(float) * size_scale
        fc = a.face_colors()
        colors = fc if fc is not None else [a.color] * a.x.size
        return [Markers(pts, diam, list(colors), single_color=(fc is None),
                        alpha=a.alpha, series_id=f"s{ai}_{k}", label=lbl)]

    if isinstance(a, Line2D):
        x, y = a.x, a.y
        if x.size > _DECIMATE_MIN_POINTS and _is_monotonic(x):
            x, y = _decimate_minmax(x, y, int(round(tr.px_w)))
        subs = _finite_subpaths(tr.xy(x, y))
        if not subs:
            return []
        return [Path(subpaths=subs, stroke=a.color, stroke_width=a.linewidth,
                     linestyle=a.linestyle, stroke_opacity=a.alpha,
                     stroke_round=True, series_id=f"s{ai}_{k}", label=lbl)]

    if isinstance(a, VLine):
        x = float(tr.x(a.x))
        return [Line((x, tr.px_top), (x, tr.px_top + tr.px_h), a.color,
                     a.linewidth, a.linestyle, a.alpha, lbl)]

    if isinstance(a, HLine):
        y = float(tr.y(a.y))
        return [Line((tr.px_left, y), (tr.px_left + tr.px_w, y), a.color,
                     a.linewidth, a.linestyle, a.alpha, lbl)]

    if isinstance(a, AxLine):
        if not np.isfinite(a.slope):
            x = float(tr.x(a.x1))
            p0, p1 = (x, tr.px_top), (x, tr.px_top + tr.px_h)
        else:
            xmin, xmax = tr.xmin, tr.xmax
            y0 = a.y1 + a.slope * (xmin - a.x1)
            y1 = a.y1 + a.slope * (xmax - a.x1)
            p0 = (float(tr.x(xmin)), float(tr.y(y0)))
            p1 = (float(tr.x(xmax)), float(tr.y(y1)))
        return [Line(p0, p1, a.color, a.linewidth, a.linestyle, a.alpha, lbl)]

    if isinstance(a, Span):
        if a.orientation == "vertical":
            p, q = float(tr.x(a.lo)), float(tr.x(a.hi))
            x, w, yy, h = min(p, q), abs(q - p), tr.px_top, tr.px_h
        else:
            p, q = float(tr.y(a.lo)), float(tr.y(a.hi))
            yy, h, x, w = min(p, q), abs(q - p), tr.px_left, tr.px_w
        return [Rect(x, yy, w, h, a.color, a.alpha, lbl)]

    if isinstance(a, FillBetween):
        top = tr.xy(a.x, a.y1)
        bot = tr.xy(a.x[::-1], a.y2[::-1])
        pts = np.vstack([top, bot])
        return [Path(subpaths=[pts], closed=True, fill=a.color,
                     fill_opacity=a.alpha, series_id=f"s{ai}_{k}", label=lbl)]

    if isinstance(a, Polygon):
        pts = tr.xy(a.x, a.y)
        return [Path(subpaths=[pts], closed=True, element="polygon",
                     fill=a.color, fill_opacity=a.alpha,
                     stroke=a.edgecolor, stroke_width=a.linewidth,
                     series_id=f"s{ai}_{k}", label=lbl)]

    if isinstance(a, LineCollection):
        segs = np.column_stack([
            tr.x(a.segments[:, 0]), tr.y(a.segments[:, 1]),
            tr.x(a.segments[:, 2]), tr.y(a.segments[:, 3]),
        ])
        return [Segments(segs, a.color, a.linewidth, a.linestyle, a.alpha, lbl)]

    if isinstance(a, Rug):
        n = a.x.size
        if n == 0:
            return []
        # Anchored in pixel space, so the tick length is a fraction of the axes
        # rather than of the data range.
        if a.side == "left":
            y = tr.y(a.x)
            x0 = np.full(n, tr.px_left)
            segs = np.column_stack([x0, y, x0 + a.height * tr.px_w, y])
        else:
            x = tr.x(a.x)
            y0 = np.full(n, tr.px_top + tr.px_h)
            segs = np.column_stack([x, y0, x, y0 - a.height * tr.px_h])
        return [Segments(segs, a.color, a.linewidth, "-", a.alpha, lbl)]

    if isinstance(a, PolyCollection):
        polys = [tr.xy(v[:, 0], v[:, 1]) for v in a.verts]
        return [PolygonBatch(polys, list(a.facecolors), a.edgecolor,
                             0.4, a.alpha, lbl)]

    if isinstance(a, (QuadMesh, Image)):
        xmin, xmax, ymin, ymax = a.extent()
        ix, iy = float(tr.x(xmin)), float(tr.y(ymax))
        iw, ih = float(tr.x(xmax)) - ix, float(tr.y(ymin)) - iy
        return [ImagePrim(a.rgba().astype(np.uint8), ix, iy, iw, ih)]

    return None
