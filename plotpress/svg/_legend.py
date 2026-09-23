"""Per-axes and figure-level legends, and the colorbar renderer (it reuses the
legend box's own layout geometry for its own tick labels).
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

from ._format import _DASH, _esc, _fmt
from ._ticks_and_frame import _render_spines

_LEGEND_ANCHORS = {
    "upper right": (1.0, 0.0), "upper left": (0.0, 0.0),
    "lower left": (0.0, 1.0), "lower right": (1.0, 1.0),
    "upper center": (0.5, 0.0), "lower center": (0.5, 1.0),
    "center left": (0.0, 0.5), "center right": (1.0, 0.5),
    "right": (1.0, 0.5), "center": (0.5, 0.5), "best": (1.0, 0.0),
}


def legend_entries(sources):
    """Labelled artists across one or more axes, keeping the first of each label.

    A figure-level legend usually spans panels that plot the *same* series, so
    without the de-duplication the shared legend would just repeat itself once
    per panel.
    """
    out, seen = [], set()
    for ax in sources:
        for a in ax.artists:
            label = getattr(a, "label", None)
            # Truthiness would silently drop label=0/0.0/False -- a legitimate
            # label matplotlib itself shows as "0", not an opt-out the way
            # None/"" is.
            if label is not None and label != "" and label not in seen:
                seen.add(label)
                out.append(a)
    return out


def _legend_layout(ax, st):
    """Compute legend geometry for an axes' own legend.

    ``ax._legend_handles`` (set by ``legend(handles=...)``) overrides which
    artists appear, in the order given, regardless of their own label --
    otherwise every labelled artist on this axes appears, call order.
    """
    source = (ax._legend_handles if ax._legend_handles is not None
             else ax.artists)
    return legend_box(
        [a for a in source if getattr(a, "label", None) not in (None, "")],
        st, ax._legend_ncol, ax._legend_title, fontsize=ax._legend_fontsize,
        framealpha=ax._legend_framealpha)


def legend_box(entries, st, ncol, title, fontsize=None, framealpha=0.85):
    """Compute legend geometry: entries, columns, cell size, box size."""
    if not entries:
        return None
    fs = fontsize if fontsize is not None else st.tick_label_size
    line_h = fs + 6
    sample_w = 22
    pad = 6
    ncol = min(max(1, int(ncol)), len(entries))
    nrows = (len(entries) + ncol - 1) // ncol
    # label is whatever the caller passed to label= -- often a string, but
    # matplotlib accepts anything and str()s it for display, and a bare
    # loop-variable int/float is a common accident this must not crash on.
    text_w = max(st.text_width(str(a.label), fs) for a in entries)
    col_w = sample_w + text_w + pad * 2
    title_h = line_h if title else 0
    box_w = col_w * ncol + pad
    if title:
        # Drawn bold below, so it must be measured bold: Helvetica-Bold runs
        # 5-9% wider than regular on real label strings, which is enough to
        # push a title out through the side of its own box.
        box_w = max(box_w, st.text_width(title, fs, bold=True) + pad * 2)
    box_h = line_h * nrows + pad + title_h
    return {
        "entries": entries, "fs": fs, "line_h": line_h, "sample_w": sample_w,
        "pad": pad, "ncol": ncol, "col_w": col_w, "title": title,
        "title_h": title_h, "box_w": box_w, "box_h": box_h,
        "framealpha": framealpha,
    }


FIGURE_LEGEND_EDGE = {
    "lower center": "bottom", "upper center": "top",
    "right": "right", "center right": "right", "center left": "left",
}


def figure_legend_layout(fig):
    """Legend geometry for ``fig.legend()``, or ``None`` if nothing is labelled."""
    spec = fig._figure_legend
    if spec is None:
        return None
    if spec.get("handles") is not None:
        entries = [a for a in spec["handles"] if getattr(a, "label", None) not in (None, "")]
    else:
        sources = spec["axes"] or [a for a in fig.axes if not a._is_colorbar]
        entries = legend_entries(sources)
    return legend_box(entries, fig.style,
                      spec["ncol"], spec["title"], fontsize=spec.get("fontsize"),
                      framealpha=spec.get("framealpha", 0.85))


def figure_legend_origin(spec, lay, W, H, pad_px):
    """Top-left corner of the figure legend, in figure pixels."""
    box_w, box_h = lay["box_w"], lay["box_h"]
    fx, fy = _LEGEND_ANCHORS.get(spec["loc"], (1.0, 0.0))
    bbox = spec.get("bbox_to_anchor")
    if bbox is not None:
        # (x, y) in whole-figure fraction coordinates, y-up (matplotlib's own
        # convention) -- flipped to pixel space (y-down) here. The loc corner
        # (fx, fy) is which corner of the box sits at that point, free to
        # land outside the figure canvas -- the common reason to reach for
        # bbox_to_anchor at all, so this never reserves space (see the named
        # edges below for that).
        anchor_x, anchor_y = bbox[0] * W, (1.0 - bbox[1]) * H
        return anchor_x - fx * box_w, anchor_y - fy * box_h
    edge = FIGURE_LEGEND_EDGE.get(spec["loc"])
    if edge == "bottom":
        return (W - box_w) / 2.0, H - pad_px - box_h
    if edge == "top":
        return (W - box_w) / 2.0, pad_px
    if edge == "right":
        return W - pad_px - box_w, (H - box_h) / 2.0
    if edge == "left":
        return pad_px, (H - box_h) / 2.0
    # Overlaid: anchor inside the whole figure the way an axes legend anchors
    # inside its own rect.
    return (pad_px + fx * max(0.0, W - box_w - 2 * pad_px),
            pad_px + fy * max(0.0, H - box_h - 2 * pad_px))


def _render_figure_legend(fig, st, W, H, body):
    lay = figure_legend_layout(fig)
    if lay is None:
        return
    spec = fig._figure_legend
    pad_px = spec["pad"] * min(W, H) + 4
    bx, by = figure_legend_origin(spec, lay, W, H, pad_px)
    draw_legend(lay, st, bx, by, body)


def _legend_origin(ax, lay, px_left, px_top, px_w, px_h):
    fx, fy = _LEGEND_ANCHORS.get(ax._legend_loc, (1.0, 0.0))
    if ax._legend_bbox_to_anchor is not None:
        # (x, y) in this axes' own fraction coordinates -- y-up, matplotlib's
        # own convention for it -- flipped to pixel space (y-down) here. The
        # loc corner (fx, fy) is which corner of the box sits at that point,
        # not an inset-space interpolation the way the plain-loc case below
        # is, so this is free to land outside the axes box entirely -- the
        # common reason to reach for bbox_to_anchor at all.
        ax_x, ax_y = ax._legend_bbox_to_anchor
        anchor_x = px_left + ax_x * px_w
        anchor_y = px_top + (1.0 - ax_y) * px_h
        return anchor_x - fx * lay["box_w"], anchor_y - fy * lay["box_h"]
    bx = px_left + 6 + fx * max(0.0, px_w - lay["box_w"] - 12)
    by = px_top + 6 + fy * max(0.0, px_h - lay["box_h"] - 12)
    return bx, by


def _render_legend(ax, st, px_left, px_top, px_w, px_h, body):
    lay = _legend_layout(ax, st)
    if lay is None:
        return
    bx, by = _legend_origin(ax, lay, px_left, px_top, px_w, px_h)
    draw_legend(lay, st, bx, by, body)


def draw_legend(lay, st, bx, by, body):
    """Emit a legend box with its top-left corner at ``(bx, by)``."""
    fs, line_h, sample_w, pad = lay["fs"], lay["line_h"], lay["sample_w"], lay["pad"]
    ncol, col_w, title_h = lay["ncol"], lay["col_w"], lay["title_h"]
    box_w, box_h = lay["box_w"], lay["box_h"]

    body.append(
        f'<g class="plotpress-legend"><rect x="{_fmt(bx)}" y="{_fmt(by)}" '
        f'width="{_fmt(box_w)}" height="{_fmt(box_h)}" rx="3" fill="#ffffff" '
        f'fill-opacity="{lay["framealpha"]}" stroke="#cccccc" stroke-width="0.8"/>'
    )
    if lay["title"]:
        body.append(
            f'<text x="{_fmt(bx + box_w / 2)}" y="{_fmt(by + pad + fs)}" '
            f'text-anchor="middle" font-size="{fs}" font-weight="bold" '
            f'fill="{st.text_color}">{_esc(lay["title"])}</text>'
        )
    for i, a in enumerate(lay["entries"]):
        r, c = divmod(i, ncol)
        sx = bx + pad + c * col_w
        row_y = by + pad + title_h + line_h * r + line_h / 2.0
        if isinstance(a, Bars):
            color = a.colors[0] if a.colors else "#333333"
        else:
            color = getattr(a, "color", None) or getattr(a, "linecolor", None) or "#333333"
        if isinstance(a, ScatterCollection):
            body.append(f'<circle cx="{_fmt(sx + sample_w / 2)}" cy="{_fmt(row_y)}" r="4" fill="{color}"/>')
        elif isinstance(a, (Bars, FillBetween, Span, Polygon)):
            op = getattr(a, "alpha", 1.0) if isinstance(a, (FillBetween, Span, Polygon)) else 1.0
            body.append(
                f'<rect x="{_fmt(sx)}" y="{_fmt(row_y - 5)}" width="{_fmt(sample_w)}" '
                f'height="10" fill="{color}" fill-opacity="{op}"/>'
            )
        else:
            # Carry the artist's dash pattern into the swatch. Reference lines
            # -- control limits, thresholds, fitted asymptotes -- are dashed or
            # dotted precisely so they read as annotations rather than data, and
            # a legend that draws them all solid throws that distinction away
            # exactly where the reader goes to look it up.
            dash = _DASH.get(getattr(a, "linestyle", "-"))
            extra = f' stroke-dasharray="{dash}"' if dash else ""
            body.append(
                f'<line x1="{_fmt(sx)}" y1="{_fmt(row_y)}" x2="{_fmt(sx + sample_w)}" '
                f'y2="{_fmt(row_y)}" stroke="{color}" stroke-width="2"{extra}/>'
            )
        body.append(
            f'<text x="{_fmt(sx + sample_w + pad)}" y="{_fmt(row_y + fs * 0.35)}" '
            f'font-size="{fs}" fill="{st.text_color}">{_esc(str(a.label))}</text>'
        )
    body.append("</g>")


def _render_colorbar(ax, tr, px_left, px_top, px_w, px_h, clip_id, body, parents=None):
    """Vertical gradient strip + right-side ticks for a colorbar axes.

    A colorbar with parent axes is wrapped in a
    ``g.plotpress-colorbar[data-parents="0,1"]`` (the parents' indices) so the
    interactive Slice companion panel -- which shrinks a parent's heatmap to make
    room for a strip -- can shrink the colorbar to match (see ``alignColorbars``
    in ``_interactive.py``), including one shared by several axes when they all
    shrink alike. Nothing else reads it; the static output is otherwise
    unchanged.
    """
    outer = body
    body = [] if parents else outer
    src = ax._cbar_source
    lut = src.lut
    norm = src.norm
    # 256x1 gradient, top = vmax.
    grad = np.flipud(lut).reshape(-1, 1, 3)
    alpha = np.full((grad.shape[0], 1, 1), 255, np.uint8)
    rgba = np.concatenate([grad, alpha], axis=2)
    uri = png_data_uri(rgba)
    body.append(
        f'<image x="{_fmt(px_left)}" y="{_fmt(px_top)}" width="{_fmt(px_w)}" '
        f'height="{_fmt(px_h)}" preserveAspectRatio="none" href="{uri}"/>'
    )
    _render_spines(ax, px_left, px_top, px_w, px_h, body)

    st = ax.style
    _, fracs, tlabels = resolve_colorbar_ticks(norm, ax._cbar_ticks, ax._cbar_format)
    marks, labels = [], []
    for frac, lab in zip(fracs, tlabels):
        y = px_top + (1 - frac) * px_h
        marks.append(f'<line x1="{_fmt(px_left + px_w)}" y1="{_fmt(y)}" x2="{_fmt(px_left + px_w + st.tick_size)}" y2="{_fmt(y)}"/>')
        labels.append(
            f'<text x="{_fmt(px_left + px_w + st.tick_size + 2)}" y="{_fmt(y + st.tick_label_size * 0.35)}" '
            f'font-size="{st.tick_label_size}" fill="{st.text_color}">{_esc(lab)}</text>'
        )
    body.append(f'<g stroke="{st.spine_color}" stroke-width="{st.tick_width}">{"".join(marks)}</g>')
    body.append("".join(labels))
    if parents:
        ids = ",".join(str(i) for i in parents)
        outer.append(f'<g class="plotpress-colorbar" data-parents="{ids}">{"".join(body)}</g>')
