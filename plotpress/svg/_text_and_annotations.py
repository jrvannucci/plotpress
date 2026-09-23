"""Plain text, annotations, and the shared text-box/leader-line geometry
(``text_box``, ``leader_anchor``, ``_bbox_svg``) that both of them, plus
legends and colorbars elsewhere in this package, are built from.
"""

from __future__ import annotations

import dataclasses
import math
import warnings

import numpy as np

from ..artists import (
    Annotation, Barbs, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Image, Line2D, LineCollection, Pie, Polygon,
    PolyCollection, QuadMesh, Quiver, ScatterCollection, Span, Stem, Table, Text,
    Violin, _edges_from,
)
from ..colors import apply_colormap, resolve_colorbar_ticks, to_hex
from ..png import png_data_uri
from ..primitives import artist_to_prims
from ..primitives import pie_center_radius, pie_label_positions, tick_axis_edge
from ..primitives import (
    marker_polygon, marker_shape_kind, marker_strokes, normalize_marker_shape,
)
from ..primitives import ImagePrim as PImage
from ..primitives import Line as PLine
from ..primitives import Markers as PMarkers
from ..primitives import Path as PPath
from ..primitives import PolygonBatch as PPolyBatch
from ..primitives import Rect as PRect
from ..primitives import Segments as PSegments
from ..ticker import minor_ticks
from ..transform import LinearTransform

from ._format import _esc, _fmt

_HA = {"left": "start", "center": "middle", "right": "end"}


_VA = {"baseline": "alphabetic", "bottom": "text-after-edge",
       "center": "central", "top": "hanging"}


_HA_FRAC = {"left": 0.0, "center": -0.5, "right": -1.0}


_VA_FRAC = {"baseline": -0.78, "bottom": -1.0, "center": -0.5, "top": 0.0}


_LINE_HEIGHT_FRAC = 1.25


def text_box(x, y, text, size, ha, va, st, bold=False, italic=False):
    """Pixel bounding box ``(x0, y0, x1, y1)`` of a label drawn at ``(x, y)``.

    Measured with the same font metrics layout uses, so the box the leader
    attaches to is the box the glyphs actually occupy.
    """
    lines = text.split("\n")
    w = max((st.text_width(ln, size, bold=bold, italic=italic) for ln in lines),
            default=0.0)
    h = size * _LINE_HEIGHT_FRAC * len(lines)
    x0 = x + _HA_FRAC.get(ha, 0.0) * w
    y0 = y + _VA_FRAC.get(va, -0.78) * h
    return x0, y0, x0 + w, y0 + h


def leader_anchor(box, target, pad=3.0):
    """Where a leader line should meet a label box on its way to ``target``.

    Edge midpoints first, corners only as a fallback: a line that arrives at the
    middle of the top edge reads as belonging to the whole label, while one that
    stops at the text anchor -- which is what happens without this -- is drawn
    straight through the words it is pointing away from.
    """
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    tx, ty = target
    edges = [((cx, y0 - pad), 1.0),          # top centre
             ((cx, y1 + pad), 1.0),          # bottom centre
             ((x0 - pad, cy), 1.0),          # left centre
             ((x1 + pad, cy), 1.0)]          # right centre
    corners = [((x0 - pad, y0 - pad), 1.25), ((x1 + pad, y0 - pad), 1.25),
               ((x0 - pad, y1 + pad), 1.25), ((x1 + pad, y1 + pad), 1.25)]
    # The weight makes a corner win only when it is clearly nearer, so a target
    # roughly above the label still gets the top-centre attachment.
    return min(edges + corners,
               key=lambda c: math.hypot(c[0][0] - tx, c[0][1] - ty) * c[1])[0]


def _multiline_shift(va, n, line_height):
    if va == "bottom":
        return (n - 1) * line_height
    if va == "center":
        return (n - 1) * line_height / 2.0
    return 0.0


def _text_svg(x, y, text, color, size, ha, va, rotation=0.0, outline=None, alpha=1.0,
              bold=False, italic=False):
    anchor = _HA.get(ha, "start")
    baseline = _VA.get(va, "alphabetic")
    rot = (f' transform="rotate({_fmt(-rotation)} {_fmt(x)} {_fmt(y)})"'
           if rotation else "")
    # paint-order puts the halo stroke *under* the fill, so the glyph keeps its
    # shape and only gains a rim. Without it the stroke thickens every letter.
    halo = ("" if not outline else
            f' stroke="{outline}" stroke-width="{_fmt(size * 0.30)}" '
            'stroke-linejoin="round" paint-order="stroke"')
    op = f' fill-opacity="{alpha}"' if alpha < 1 else ""
    weight = ' font-weight="bold"' if bold else ""
    style = ' font-style="italic"' if italic else ""
    lines = text.split("\n")
    if len(lines) == 1:
        return (f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="{anchor}" '
                f'dominant-baseline="{baseline}" font-size="{size}" '
                f'fill="{color}"{halo}{op}{weight}{style}{rot}>{_esc(text)}</text>')
    # Multi-line: dominant-baseline positions line one exactly as it would a
    # single line, then each further line is a sibling tspan stepped down by
    # one line height -- an explicit x= on every tspan starts a fresh "text
    # chunk" so text-anchor re-centers/re-rights each line independently
    # (matplotlib's default multialignment, which follows ha).
    line_height = size * _LINE_HEIGHT_FRAC
    y0 = y - _multiline_shift(va, len(lines), line_height)
    def _tspan(i, ln):
        # A backslash inside an f-string's {} expression needs 3.12+ (PEP
        # 701); this project supports 3.9+, so the nested dy="..." literal
        # is built as a plain variable first rather than escaped inline.
        dy = "" if i == 0 else f' dy="{_fmt(line_height)}"'
        return f'<tspan x="{_fmt(x)}"{dy}>{_esc(ln)}</tspan>'

    tspans = "".join(_tspan(i, ln) for i, ln in enumerate(lines))
    return (f'<text x="{_fmt(x)}" y="{_fmt(y0)}" text-anchor="{anchor}" '
            f'dominant-baseline="{baseline}" font-size="{size}" '
            f'fill="{color}"{halo}{op}{weight}{style}{rot}>{tspans}</text>')


def _bbox_pad(box, bbox):
    """Expand a tight ``text_box()`` rect by ``bbox['pad']``."""
    x0, y0, x1, y1 = box
    pad = bbox["pad"]
    return x0 - pad, y0 - pad, x1 + pad, y1 + pad


def _bbox_svg(padded_box, bbox):
    """The ``<rect>`` a ``bbox=`` dict draws behind a label.

    ``padded_box`` is already expanded by ``pad`` (see :func:`_bbox_pad`) --
    callers that also need a leader-line anchor point (``annotate()``) use the
    same padded rect for both, so the arrow visibly touches the box instead of
    stopping short of it.
    """
    x0, y0, x1, y1 = padded_box
    rx = min(8.0, (x1 - x0) / 2.0, (y1 - y0) / 2.0) if bbox["boxstyle"] == "round" else 0.0
    edge = (f' stroke="{bbox["edgecolor"]}" stroke-width="{bbox["linewidth"]}"'
            if bbox["edgecolor"] not in (None, "none") else "")
    op = f' fill-opacity="{bbox["alpha"]}"' if bbox["alpha"] < 1 else ""
    return (f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(x1 - x0)}" '
            f'height="{_fmt(y1 - y0)}" rx="{_fmt(rx)}" fill="{bbox["facecolor"]}"'
            f'{op}{edge}/>')


def _axes_fraction_xy(tr, fx, fy):
    """``transform=ax.transAxes`` fraction -> pixels, independent of data limits.

    ``(0, 0)`` is the axes' bottom-left, ``(1, 1)`` its top-right -- matplotlib's
    own convention -- mapped straight off the axes' own pixel rect rather than
    through the data-space affine, so it holds regardless of xlim/ylim/scale.
    """
    return tr.px_left + fx * tr.px_w, tr.px_top + (1.0 - fy) * tr.px_h


def _render_table(t: Table, tr, st, body):
    """``ax.table()`` -- a grid of cells at an axes-fraction ``bbox``, in the
    same pixel space :func:`_axes_fraction_xy` maps text/annotate labels
    through (only the corners are needed here, not a single point)."""
    x0, y0, w, h = t.bbox
    left, bottom = _axes_fraction_xy(tr, x0, y0)
    right, top = _axes_fraction_xy(tr, x0 + w, y0 + h)
    rect_w, rect_h = right - left, bottom - top

    has_col_header = t.col_labels is not None
    has_row_header = t.row_labels is not None
    body_rows = t.cell_text
    n_data_rows = len(body_rows)
    n_data_cols = len(body_rows[0]) if body_rows else (len(t.col_labels) if has_col_header else 0)
    n_rows = n_data_rows + (1 if has_col_header else 0)
    n_cols = n_data_cols + (1 if has_row_header else 0)
    if n_rows == 0 or n_cols == 0:
        return
    cell_w, cell_h = rect_w / n_cols, rect_h / n_rows
    fs = t.fontsize if t.fontsize is not None else st.tick_label_size
    op = f' fill-opacity="{t.alpha}"' if t.alpha < 1 else ""
    row0 = 1 if has_col_header else 0
    col0 = 1 if has_row_header else 0

    def cell_fill(r, c):
        if has_col_header and r == 0 and c >= col0 and t.col_colors:
            i = c - col0
            if i < len(t.col_colors):
                return t.col_colors[i]
        if has_row_header and c == 0 and r >= row0 and t.row_colors:
            i = r - row0
            if i < len(t.row_colors):
                return t.row_colors[i]
        if r >= row0 and c >= col0 and t.cell_colors:
            ri, ci = r - row0, c - col0
            if ri < len(t.cell_colors) and ci < len(t.cell_colors[ri]):
                return t.cell_colors[ri][ci]
        return "#ffffff"

    def cell_text(r, c):
        if has_col_header and r == 0:
            return "" if (c == 0 and has_row_header) else t.col_labels[c - col0]
        if has_row_header and c == 0:
            return t.row_labels[r - row0]
        return body_rows[r - row0][c - col0]

    for r in range(n_rows):
        for c in range(n_cols):
            cx0, cy0 = left + c * cell_w, top + r * cell_h
            body.append(
                f'<rect x="{_fmt(cx0)}" y="{_fmt(cy0)}" width="{_fmt(cell_w)}" '
                f'height="{_fmt(cell_h)}" fill="{cell_fill(r, c)}"{op} '
                f'stroke="#888888" stroke-width="0.75"/>')
            text = cell_text(r, c)
            if text:
                tx, ty = cx0 + cell_w / 2.0, cy0 + cell_h / 2.0
                weight = ' font-weight="bold"' if (r < row0 or c < col0) else ""
                body.append(
                    f'<text x="{_fmt(tx)}" y="{_fmt(ty)}" text-anchor="middle" '
                    f'dominant-baseline="central" font-size="{fs}" '
                    f'fill="{st.text_color}"{weight}>{_esc(text)}</text>')


def _cscale_open(index, x, y):
    """Open a counter-scale group: a data-anchored label's glyphs/box must
    stay a constant screen size under a per-axes interactive zoom (see
    _interactive.py's relayoutTextCounterScale) the same way a title, tick
    label, or point-pick pin already does -- unlike a marker (whose size
    represents a footprint *on the data*, deliberately scaling with the
    axis -- see the marker-scaling fix), a text label exists to be read, so
    its legibility shouldn't depend on how far zoomed in the reader is.

    A bare CSS transform on the label alone can't do this: only *client-side
    JS*, recomputing the counter-scale on every zoom from the live
    zoomAffine(), can -- the group starts with no transform (identity) since
    nothing has zoomed yet at render time. ``(x, y)`` is the anchor JS holds
    fixed while everything else around it counter-scales; passing the
    label's own text/box anchor keeps that point pinned exactly where plain
    ancestor scaling would already put it, so only the *size* around it
    changes, not its tracked position. Only for a *data*-anchored label
    (never call this for axes_fraction text -- already immune, being
    outside the zoom group's scaling entirely).
    """
    return (f'<g class="plotpress-cscale" data-axes="{index}" '
            f'data-x0="{_fmt(x)}" data-y0="{_fmt(y)}">')


def _render_text(t: Text, tr, st, body, index=None):
    if t.axes_fraction:
        x, y = _axes_fraction_xy(tr, t.x, t.y)
    else:
        x, y = float(tr.x(t.x)), float(tr.y(t.y))
    cscale = index is not None and not t.axes_fraction
    if cscale:
        body.append(_cscale_open(index, x, y))
    # A boxed label is a "text box" the toolbar's Hide Annotations toggle
    # (see _interactive.py's .plotpress-textbox rule) can hide alongside
    # every Annotation note -- a plain unboxed label has no comparable "hide
    # the callout" reading, so it stays outside the group and always shows.
    if t.bbox is not None:
        body.append('<g class="plotpress-textbox">')
        box = _bbox_pad(text_box(x, y, t.text, t.size, t.ha, t.va, st,
                                  bold=t.bold, italic=t.italic), t.bbox)
        body.append(_bbox_svg(box, t.bbox))
    body.append(_text_svg(x, y, t.text, t.color, t.size, t.ha, t.va, t.rotation,
                          t.outline, t.alpha, bold=t.bold, italic=t.italic))
    if t.bbox is not None:
        body.append("</g>")
    if cscale:
        body.append("</g>")


def _render_annotation(an: Annotation, tr, st, body, index=None):
    if an.axes_fraction:
        tx, ty = _axes_fraction_xy(tr, an.xytext[0], an.xytext[1])
    else:
        tx, ty = float(tr.x(an.xytext[0])), float(tr.y(an.xytext[1]))
    box = text_box(tx, ty, an.text, an.size, an.ha, an.va, st,
                    bold=an.bold, italic=an.italic)
    if an.bbox is not None:
        box = _bbox_pad(box, an.bbox)   # the leader below anchors to this, padded, edge
    if an.arrowprops is not None:
        px, py = float(tr.x(an.xy[0])), float(tr.y(an.xy[1]))
        arrow_color = to_hex(an.arrowprops.get("color", an.color)
                             if isinstance(an.arrowprops, dict) else an.color)
        arrow_alpha = (an.arrowprops.get("alpha", 1.0)
                       if isinstance(an.arrowprops, dict) else 1.0)
        # Start the leader at the edge of the text (or bbox) nearest the
        # target, not at the text anchor -- from the anchor the line sets off
        # across its own label whenever the target is up and to the left of it.
        # Left outside the counter-scale group below on purpose: the leader
        # tracks the *data* point `xy` at one end, which should scale with a
        # zoom same as any other data-anchored geometry, and matching the box
        # exactly at the other end after a large zoom is a minor, accepted
        # cosmetic gap next to the alternative (a giant or unreadable label).
        sx, sy = leader_anchor(box, (px, py))
        ang = math.atan2(py - sy, px - sx)
        hl = 7.0
        h1 = (px - hl * math.cos(ang - 0.4), py - hl * math.sin(ang - 0.4))
        h2 = (px - hl * math.cos(ang + 0.4), py - hl * math.sin(ang + 0.4))
        op = f' stroke-opacity="{arrow_alpha}"' if arrow_alpha < 1 else ""
        body.append(
            f'<path d="M{_fmt(sx)},{_fmt(sy)} L{_fmt(px)},{_fmt(py)} '
            f'M{_fmt(px)},{_fmt(py)} L{_fmt(h1[0])},{_fmt(h1[1])} '
            f'M{_fmt(px)},{_fmt(py)} L{_fmt(h2[0])},{_fmt(h2[1])}" '
            f'fill="none" stroke="{arrow_color}" stroke-width="1.2"{op}/>'
        )
    cscale = index is not None and not an.axes_fraction
    if cscale:
        body.append(_cscale_open(index, tx, ty))
    # See _render_text: a boxed callout -- box and text together -- is what
    # Hide Annotations can toggle off.
    if an.bbox is not None:
        body.append('<g class="plotpress-textbox">')
        body.append(_bbox_svg(box, an.bbox))
    body.append(_text_svg(tx, ty, an.text, an.color, an.size, an.ha, an.va,
                          0.0, an.outline, an.alpha, bold=an.bold, italic=an.italic))
    if an.bbox is not None:
        body.append("</g>")
    if cscale:
        body.append("</g>")
