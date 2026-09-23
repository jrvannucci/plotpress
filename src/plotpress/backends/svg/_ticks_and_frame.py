"""Grid lines, tick marks/labels (major, minor, and a twin's own),
spines, axis labels, and the handful of geometry queries
(``twiny_headroom``, ``_max_ytick_width``) that layout code elsewhere needs
to reserve space for them before they're actually drawn.
"""

from __future__ import annotations

import dataclasses
import math
import warnings

import numpy as np

from ...core.artists import (
    Annotation, Barbs, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Image, Line2D, LineCollection, Pie, Polygon,
    PolyCollection, QuadMesh, Quiver, ScatterCollection, Span, Stem, Table, Text,
    Violin, _edges_from,
)
from ...colors import apply_colormap, resolve_colorbar_ticks, to_hex
from ...png import png_data_uri
from ...core.primitives import artist_to_prims
from ...core.primitives import pie_center_radius, pie_label_positions, tick_axis_edge
from ...core.primitives import (
    marker_polygon, marker_shape_kind, marker_strokes, normalize_marker_shape,
)
from ...core.primitives import ImagePrim as PImage
from ...core.primitives import Line as PLine
from ...core.primitives import Markers as PMarkers
from ...core.primitives import Path as PPath
from ...core.primitives import PolygonBatch as PPolyBatch
from ...core.primitives import Rect as PRect
from ...core.primitives import Segments as PSegments
from ...ticker import minor_ticks
from ...core.transform import LinearTransform

from ._format import _esc, _fmt

def _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body,
                 alpha=None, axis="both", minor=False):
    """``axis`` restricts lines to ``"x"``/``"y"``/``"both"``; ``minor=True``
    draws them thinner and lighter, the standard subordinate look for a
    minor grid alongside (or instead of) the major one.
    """
    lines = []
    if axis != "y":
        for xt in xticks:
            x = tr.x(xt)
            lines.append(f'<line x1="{_fmt(x)}" y1="{_fmt(px_top)}" x2="{_fmt(x)}" y2="{_fmt(px_top + px_h)}"/>')
    if axis != "x":
        for yt in yticks:
            y = tr.y(yt)
            lines.append(f'<line x1="{_fmt(px_left)}" y1="{_fmt(y)}" x2="{_fmt(px_left + px_w)}" y2="{_fmt(y)}"/>')
    if not lines:
        return
    width = st.grid_width * (0.6 if minor else 1.0)
    base_alpha = st.grid_alpha if alpha is None else alpha
    grid_alpha = base_alpha * (0.6 if minor else 1.0)
    body.append(
        f'<g stroke="{st.grid_color}" stroke-width="{_fmt(width)}" '
        f'stroke-opacity="{_fmt(grid_alpha)}">'
        f'{"".join(lines)}</g>'
    )


def _render_twin_ticks(ax, st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body):
    """Draw a twin overlay's independent axis on the side opposite the parent."""
    # A twin only ever draws *one* of its two axes independently (the other
    # mirrors the parent's own, already-drawn one), so unlike a regular
    # axes/secondary -- which resolve "x" and "y" overrides separately --
    # only that one axis' own tick_params() override is relevant here.
    # Previously neither was ever consulted, so tick_params() on a twin was
    # silently ignored by its own renderer.
    axis = "y" if ax._twin_shared == "x" else "x"
    ov = ax._tick_overrides[axis]
    st = st.copy(**ov) if ov else st
    ts, tw, fs, rot = st.tick_size, st.tick_width, st.tick_label_size, st.tick_label_rotation
    marks, labels = [], []
    if ax._twin_shared == "x":                      # twinx: y-axis on the RIGHT
        xr = px_left + px_w
        for yt, lab in zip(yticks, ax._resolve_yticklabels(yticks)):
            y = tr.y(yt)
            marks.append(f'<line x1="{_fmt(xr)}" y1="{_fmt(y)}" x2="{_fmt(xr + ts)}" y2="{_fmt(y)}"/>')
            lx, ly = xr + ts + 2, y + fs * 0.35
            anchor = "end" if rot else "start"
            rt = f' transform="rotate({_fmt(-rot)} {_fmt(lx)} {_fmt(ly)})"' if rot else ""
            labels.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(ly)}" '
                f'text-anchor="{anchor}" font-size="{fs}" fill="{st.text_color}"{rt}>{_esc(lab)}</text>'
            )
        if ax._shown_ylabel():
            ylabel_size = ax._ylabel_size or st.label_size
            lx = xr + ts + _max_ytick_width(ax, st) + ylabel_size + 4
            cy = px_top + px_h / 2.0
            body.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(cy)}" text-anchor="middle" '
                f'font-size="{ylabel_size}" fill="{st.text_color}" '
                f'transform="rotate(90 {_fmt(lx)} {_fmt(cy)})">{_esc(ax._ylabel)}</text>'
            )
    else:                                           # twiny: x-axis on the TOP
        for xt, lab in zip(xticks, ax._resolve_xticklabels(xticks)):
            x = tr.x(xt)
            marks.append(f'<line x1="{_fmt(x)}" y1="{_fmt(px_top)}" x2="{_fmt(x)}" y2="{_fmt(px_top - ts)}"/>')
            ly = px_top - ts - 3
            anchor = "end" if rot else "middle"
            rt = f' transform="rotate({_fmt(-rot)} {_fmt(x)} {_fmt(ly)})"' if rot else ""
            labels.append(
                f'<text x="{_fmt(x)}" y="{_fmt(ly)}" text-anchor="{anchor}" '
                f'font-size="{fs}" fill="{st.text_color}"{rt}>{_esc(lab)}</text>'
            )
        if ax._shown_xlabel():
            xlabel_size = ax._xlabel_size or st.label_size
            body.append(
                f'<text x="{_fmt(px_left + px_w / 2)}" y="{_fmt(px_top - ts - fs - xlabel_size)}" '
                f'text-anchor="middle" font-size="{xlabel_size}" '
                f'fill="{st.text_color}">{_esc(ax._xlabel)}</text>'
            )
    body.append(f'<g stroke="{st.spine_color}" stroke-width="{tw}">{"".join(marks)}</g>')
    body.append("".join(labels))


def _render_ticks(xst, yst, tr, xticks, yticks, xlabels, ylabels,
                  px_left, px_top, px_w, px_h, body,
                  xside="bottom", yside="left"):
    xts, xfs = xst.tick_size, xst.tick_label_size
    yts, yfs = yst.tick_size, yst.tick_label_size
    xrot, yrot = xst.tick_label_rotation, yst.tick_label_rotation
    xmarks, ymarks, labels = [], [], []
    x_axis, xsign, y_axis, ysign = tick_axis_edge(px_left, px_w, px_top, px_h, xside, yside)

    for xt, lab in zip(xticks, xlabels):
        x = tr.x(xt)
        xmarks.append(f'<line x1="{_fmt(x)}" y1="{_fmt(x_axis)}" x2="{_fmt(x)}" '
                      f'y2="{_fmt(x_axis + xsign * xts)}"/>')
        ly = x_axis + xsign * xts + (xfs if xside == "bottom" else -3)
        # A rotated label pivots around the same point unrotated text would
        # have started from (text-anchor="middle") -- but "end" (the label's
        # own last character) is the sensible anchor once it's diagonal: that
        # puts the string right up against its own tick, tilting away from
        # it, instead of straddling the tick position edge-on. Matplotlib
        # needs a separate ha="right" for this; a diagonal *tick* label has
        # no other look anyone would want, so it isn't a second knob here.
        anchor = "end" if xrot else "middle"
        rot = f' transform="rotate({_fmt(-xrot)} {_fmt(x)} {_fmt(ly)})"' if xrot else ""
        labels.append(
            f'<text x="{_fmt(x)}" y="{_fmt(ly)}" text-anchor="{anchor}" '
            f'font-size="{xfs}" fill="{xst.text_color}"{rot}>{_esc(lab)}</text>'
        )
    for yt, lab in zip(yticks, ylabels):
        y = tr.y(yt)
        ymarks.append(f'<line x1="{_fmt(y_axis)}" y1="{_fmt(y)}" '
                      f'x2="{_fmt(y_axis + ysign * yts)}" y2="{_fmt(y)}"/>')
        anchor = "end" if yside == "left" else "start"
        lx = y_axis + ysign * yts + (-2 if yside == "left" else 2)
        ly2 = y + yfs * 0.35
        rot = f' transform="rotate({_fmt(-yrot)} {_fmt(lx)} {_fmt(ly2)})"' if yrot else ""
        labels.append(
            f'<text x="{_fmt(lx)}" y="{_fmt(ly2)}" text-anchor="{anchor}" '
            f'font-size="{yfs}" fill="{yst.text_color}"{rot}>{_esc(lab)}</text>'
        )
    body.append(f'<g stroke="{xst.spine_color}" stroke-width="{xst.tick_width}">{"".join(xmarks)}</g>')
    body.append(f'<g stroke="{yst.spine_color}" stroke-width="{yst.tick_width}">{"".join(ymarks)}</g>')
    body.append("".join(labels))


def _render_minor_ticks(xst, yst, tr, xticks, yticks, px_left, px_top, px_w, px_h, body,
                        xside="bottom", yside="left"):
    """Unlabeled minor tick marks, drawn shorter than the major ones."""
    xts = xst.tick_size * 0.6
    yts = yst.tick_size * 0.6
    xmarks, ymarks = [], []
    x_axis, xsign, y_axis, ysign = tick_axis_edge(px_left, px_w, px_top, px_h, xside, yside)

    for xt in xticks:
        x = tr.x(xt)
        xmarks.append(f'<line x1="{_fmt(x)}" y1="{_fmt(x_axis)}" x2="{_fmt(x)}" '
                      f'y2="{_fmt(x_axis + xsign * xts)}"/>')
    for yt in yticks:
        y = tr.y(yt)
        ymarks.append(f'<line x1="{_fmt(y_axis)}" y1="{_fmt(y)}" '
                      f'x2="{_fmt(y_axis + ysign * yts)}" y2="{_fmt(y)}"/>')
    body.append(f'<g stroke="{xst.spine_color}" stroke-width="{xst.tick_width}">{"".join(xmarks)}</g>')
    body.append(f'<g stroke="{yst.spine_color}" stroke-width="{yst.tick_width}">{"".join(ymarks)}</g>')


def _render_spines(ax, px_left, px_top, px_w, px_h, body):
    """Draw the axes box outline, one ``<line>`` per visible side.

    Each :class:`~plotpress.axes.Spine` resolves its own color/width (falling
    back to the figure style), independent of the other three sides.
    """
    st = ax.style
    x0, y0, x1, y1 = px_left, px_top, px_left + px_w, px_top + px_h
    edges = {
        "top": (x0, y0, x1, y0), "bottom": (x0, y1, x1, y1),
        "left": (x0, y0, x0, y1), "right": (x1, y0, x1, y1),
    }
    for side, (ex0, ey0, ex1, ey1) in edges.items():
        spine = ax.spines[side]
        if not spine.get_visible():
            continue
        color = spine._color if spine._color is not None else st.spine_color
        width = spine._linewidth if spine._linewidth is not None else st.spine_width
        op = f' stroke-opacity="{spine._alpha}"' if spine._alpha is not None else ""
        body.append(
            f'<line x1="{_fmt(ex0)}" y1="{_fmt(ey0)}" x2="{_fmt(ex1)}" y2="{_fmt(ey1)}" '
            f'stroke="{color}" stroke-width="{width}"{op}/>'
        )


def _render_labels(ax, st, px_left, px_top, px_w, px_h, body):
    """Draw this axes' title and x/y axis labels.

    ``st`` is the figure-wide default -- axis-label *text* uses it unless
    this axes' own :meth:`~plotpress.axes.Axes.set_xlabel`/``set_ylabel``
    gave it a ``size`` of its own (``text_color`` still isn't a per-axes
    field), but the *offset* that clears the tick marks/labels first has to
    match ``tick_params()``'s own per-axis override, resolved here exactly
    like :func:`_render_ticks`'s own caller already does. Using the figure
    default there regardless of the override used to put the axis label
    on top of a tick label sized (or rotated) differently from the
    default -- most visibly with a *larger* ``labelsize`` override, whose
    now-bigger tick labels reached past where this assumed they would end.
    """
    xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
    yst = st.copy(**ax._tick_overrides["y"]) if ax._tick_overrides["y"] else st
    cx = px_left + px_w / 2.0
    if ax._shown_xlabel() and not ax._axis_off:
        xlabel_size = ax._xlabel_size or st.label_size
        if ax._xlabel_y_override is not None:
            y = ax._xlabel_y_override
        else:
            xdec = xst.tick_size + _xtick_label_extent(ax, xst) + 4
            y = (px_top - xdec - xlabel_size if ax._xtick_side == "top"
                else px_top + px_h + xdec + xlabel_size)
        body.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'font-size="{xlabel_size}" fill="{st.text_color}">{_esc(ax._xlabel)}</text>'
        )
    if ax._shown_ylabel() and not ax._axis_off:
        ylabel_size = ax._ylabel_size or st.label_size
        cy = px_top + px_h / 2.0
        if ax._ylabel_x_override is not None:
            x, angle = ax._ylabel_x_override, -90
        elif ax._ytick_side == "right":
            x = px_left + px_w + yst.tick_size + _max_ytick_width(ax, yst) + ylabel_size + 4
            angle = 90
        else:
            x = px_left - yst.tick_size - _max_ytick_width(ax, yst) - ylabel_size - 4
            angle = -90
        body.append(
            f'<text x="{_fmt(x)}" y="{_fmt(cy)}" text-anchor="middle" '
            f'font-size="{ylabel_size}" fill="{st.text_color}" '
            f'transform="rotate({angle} {_fmt(x)} {_fmt(cy)})">{_esc(ax._ylabel)}</text>'
        )
    if ax._title:
        size = ax._title_size or st.title_size
        body.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(px_top - 8 - twiny_headroom(ax, st))}" '
            f'text-anchor="middle" font-size="{size}" '
            f'fill="{st.text_color}">{_esc(ax._title)}</text>'
        )


def _xtick_label_extent(ax, xst):
    """Pixels an x tick label reaches away from the axis line -- one flat
    text row when horizontal, or the label's real (measured) rotated
    footprint when :meth:`~plotpress.axes.Axes.tick_params`'s
    ``labelrotation`` is set. Mirrors :meth:`Figure.tight_layout`'s own
    identical trig exactly (see its own comment on why this small
    computation is duplicated rather than shared): this is what the axis
    label's own offset has to clear, the same way tight_layout's margin
    does.
    """
    if not xst.tick_label_rotation:
        return xst.tick_label_size
    ticks = ax._resolve_xticks()
    labels = ax._resolve_xticklabels(ticks)
    xtw = max((xst.text_width(l, xst.tick_label_size) for l in labels), default=0.0)
    theta = math.radians(xst.tick_label_rotation)
    return xtw * abs(math.sin(theta)) + xst.tick_label_size * abs(math.cos(theta))
    if ax._title:
        size = ax._title_size or st.title_size
        body.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(px_top - 8 - twiny_headroom(ax, st))}" '
            f'text-anchor="middle" font-size="{size}" '
            f'fill="{st.text_color}">{_esc(ax._title)}</text>'
        )


def twiny_headroom(ax, st):
    """Pixels of tick decoration above the axes box that the title must clear.

    Three sources draw there: a ``twiny`` overlay's ticks/label, a
    ``secondary_xaxis('top')``'s ticks/label, and this axes' own ticks after
    ``tick_top()`` -- all drawn on top, in the same band the title occupies.
    Without this the title lands on top of them, and any of the three is
    usually the *reason* the title is worth reading, so overlapping them is
    doubly unhelpful. ``tight_layout`` reserves the same band.
    """
    h = 0.0
    if ax._xtick_side == "top" and not ax._axis_off:
        h = st.tick_size + st.tick_label_size + 4
        if ax._shown_xlabel():
            h += (ax._xlabel_size or st.label_size) + 6
    for other in ax.figure.axes:
        is_twiny = other._twin_of is ax and other._twin_shared == "y"
        is_secondary_top = (other._secondary_of is ax
                            and other._secondary_dim == "x"
                            and other._xtick_side == "top")
        if is_twiny or is_secondary_top:
            th = st.tick_size + st.tick_label_size + 4
            if other._shown_xlabel():
                th += (other._xlabel_size or st.label_size) + 6
            h = max(h, th)
    return h


def _max_ytick_width(ax, st):
    """Horizontal footprint of the widest y tick label, as drawn.

    Must mirror the tick selection the renderer uses -- explicit ``set_yticks``
    and ``set_yticklabels`` included -- or the y label gets placed on top of
    labels this never measured. When ``tick_params(axis='y',
    labelrotation=...)`` is set, that footprint is the *rotated* label's
    horizontal reach, not its unrotated string width -- a tilted label is
    narrower (or wider) than the plain text, and every caller of this
    function positions the y-axis label just past whatever this returns.
    """
    ticks = ax._resolve_yticks()
    labels = ax._resolve_yticklabels(ticks)
    w = max((st.text_width(l, st.tick_label_size) for l in labels), default=0.0)
    if st.tick_label_rotation:
        theta = math.radians(st.tick_label_rotation)
        w = w * abs(math.cos(theta)) + st.tick_label_size * abs(math.sin(theta))
    return w
