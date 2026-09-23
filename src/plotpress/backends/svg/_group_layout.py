"""``Figure.group()``'s labeled boxes around clusters of axes: figure-level text,
the box geometry itself, and the extra clearance a twin/secondary/colorbar
member needs reserved around it.
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
from ...style.colors import apply_colormap, resolve_colorbar_ticks, to_hex
from ..png import png_data_uri
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
from ...style.ticker import minor_ticks
from ...core.transform import LinearTransform

from ._format import _DASH, _esc, _fmt, _pixel_rect
from ._ticks_and_frame import _max_ytick_width, _render_twin_ticks, twiny_headroom
from ._text_and_annotations import _bbox_pad, _bbox_svg, text_box
from ._legend import _render_colorbar
from ._render import _render_axes

def _render_figtexts(fig, W, H, body):
    """Figure-level (global) title and shared x/y labels spanning all subplots."""
    st = fig.style
    if fig._suptitle:
        t = fig._suptitle
        size = t.get("size") or st.title_size * 1.5
        body.append(
            f'<text x="{_fmt(W / 2)}" y="{_fmt(size + 6)}" text-anchor="middle" '
            f'font-size="{size}" font-weight="bold" fill="{st.text_color}">'
            f'{_esc(t["text"])}</text>'
        )
    if fig._supxlabel:
        t = fig._supxlabel
        size = t.get("size") or st.label_size * 1.2
        body.append(
            f'<text x="{_fmt(W / 2)}" y="{_fmt(H - 6)}" text-anchor="middle" '
            f'font-size="{size}" fill="{st.text_color}">{_esc(t["text"])}</text>'
        )
    if fig._supylabel:
        t = fig._supylabel
        size = t.get("size") or st.label_size * 1.2
        x, y = size + 4, H / 2
        body.append(
            f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="middle" '
            f'font-size="{size}" fill="{st.text_color}" '
            f'transform="rotate(-90 {_fmt(x)} {_fmt(y)})">{_esc(t["text"])}</text>'
        )
    for t in fig._fig_texts:
        _render_fig_text(t, st, W, H, body)


_HA_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


_VA_DY = {"top": 0.8, "center": 0.35, "bottom": 0.0, "baseline": 0.0}


def _render_fig_text(t, st, W, H, body):
    """One ``fig.text()`` entry, at figure-fraction coordinates."""
    size = t["size"] or st.font_size
    color = t["color"] or st.text_color
    x, y = t["x"] * W, (1.0 - t["y"]) * H + _VA_DY.get(t["va"], 0.0) * size
    anchor = _HA_ANCHOR.get(t["ha"], "start")
    alpha = t.get("alpha", 1.0)
    bbox = t.get("bbox")
    if bbox is not None:
        box = _bbox_pad(text_box(x, y, t["s"], size, t["ha"], t["va"], st), bbox)
        body.append(_bbox_svg(box, bbox))
    op = f' fill-opacity="{alpha}"' if alpha < 1 else ""
    body.append(
        f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="{anchor}" '
        f'font-size="{size}" fill="{color}"{op}>{_esc(t["s"])}</text>'
    )


def _group_top_clearance(ax, st):
    """Extra space above an axes' own rect that Figure.group()'s box must not
    cut through: a twiny()/secondary_xaxis('top') overlay's ticks, and, above
    that, this axes' own title -- mirroring exactly where _render_axes draws
    each (twiny_headroom, then the ax._title block right after it). Wrapping
    just ax._rect (the plot box itself) would otherwise draw the group's top
    edge straight through the top row's own titles.
    """
    extra = twiny_headroom(ax, st)
    if ax._title:
        size = ax._title_size or st.title_size
        extra += 8 + size * 0.8   # matches the title's own baseline offset/ascent
    return extra


def _group_axes_extra(ax, st):
    """(top, bottom, left, right) clearance beyond an axes' own rect that
    Figure.group()'s box must not cut through -- this axes' own title/twiny
    overlay (see _group_top_clearance) above it, and its tick labels plus
    axis label on whichever side they're actually drawn below/beside it.
    Wrapping just ax._rect (the bare plot box) would otherwise draw the
    group's edge straight through the outermost row's/column's own tick
    numbers and x/y axis labels, not just its title.

    A twin (``twinx()``/``twiny()``) is a special case: unlike a secondary
    axis (``secondary_xaxis()``/``secondary_yaxis()``, which sets its own
    ``_xtick_side``/``_ytick_side`` explicitly, so the generic branch below
    already handles it correctly), a twin never sets either -- svg.py's own
    renderer draws a twinx's y-axis on the right / a twiny's x-axis on top
    unconditionally (see ``_render_twin_ticks``/the ``is_twin`` branch in
    ``_render_axes``), regardless of ``_ytick_side``/``_xtick_side``'s
    inherited (and here irrelevant) default. Mirrors tight_layout()'s own
    identical special-case for the exact same reason.
    """
    top = _group_top_clearance(ax, st)
    bottom = left = right = 0.0
    if ax._axis_off:
        return top, bottom, left, right
    if ax._twin_of is not None:
        if ax._twin_shared == "x":                   # twinx: y-axis on the right
            ydec = st.tick_size + _max_ytick_width(ax, st) + 4
            if ax._shown_ylabel():
                ydec += (ax._ylabel_size or st.label_size) + 6
            return top, bottom, left, ydec
        else:                                          # twiny: x-axis on top
            xdec = st.tick_size + st.tick_label_size + 4
            if ax._shown_xlabel():
                xdec += (ax._xlabel_size or st.label_size) + 6
            return top + xdec, bottom, left, right
    xdec = st.tick_size + st.tick_label_size + 4
    if ax._shown_xlabel():
        xdec += (ax._xlabel_size or st.label_size) + 6
    if ax._xtick_side == "top":
        top += xdec
    else:
        bottom += xdec
    ydec = st.tick_size + _max_ytick_width(ax, st) + 4
    if ax._shown_ylabel():
        ydec += (ax._ylabel_size or st.label_size) + 6
    if ax._ytick_side == "right":
        right += ydec
    else:
        left += ydec
    return top, bottom, left, right


def _group_colorbar_extra(cax, st):
    """(top, bottom, left, right) clearance beyond a colorbar axes' own rect
    that Figure.group()'s box must not cut through: its own title, if any,
    plus its tick numbers -- _render_colorbar always draws those to the
    right, regardless of any tick-side setting a plain axes would have.
    """
    top = _group_top_clearance(cax, st)
    _, _, tlabels = resolve_colorbar_ticks(cax._cbar_source.norm, cax._cbar_ticks,
                                           cax._cbar_format)
    width = max((st.text_width(l, st.tick_label_size) for l in tlabels), default=0.0)
    return top, 0.0, 0.0, st.tick_size + width + 4


def _group_colorbars(g_axes, fig):
    """Colorbar axes belonging entirely to this group's own axes.

    A colorbar attached to a grouped axes (``fig.colorbar(mesh, ax=ax)``, one
    per panel or shared across several) steals its space from right next to
    that axes, not from some independent spot -- the group's box has to wrap
    it too, or it juts out past the edge that's supposed to enclose it. A
    colorbar shared with an axes *outside* the group is left alone: pulling
    the box out to wrap it would misrepresent what the group actually is.
    """
    axset = set(id(a) for a in g_axes)
    return [cax for cax in fig.axes
            if cax._is_colorbar and cax._cbar_parents
            and all(id(p) in axset for p in cax._cbar_parents)]


def _group_twins_and_secondaries(g_axes, fig):
    """Twin (``twinx()``/``twiny()``) and secondary
    (``secondary_xaxis()``/``secondary_yaxis()``) axes belonging to this
    group's own member axes.

    Regression: a caller naturally thinks of a twinned/secondary panel as
    *one* panel with a second axis, not two separate axes to list
    explicitly in ``Figure.group()``'s own ``axes=`` -- the same reason
    ``_group_colorbars`` already auto-includes a member's own colorbar
    rather than requiring it listed too. Left out, the overlay's own
    decoration (drawn on the *opposite* side from its parent, the entire
    reason it exists) was measured nowhere: it isn't ``ax._rect`` (twins/
    secondaries share their parent's exact rect, adding no width of their
    own there) and it wasn't counted as any member's own extra either,
    since ``_group_axes_extra`` is only ever called per*-member*, and the
    parent axes' own call knows nothing about a *different* Axes object
    overlaid on it. The box could then end with a real gap on the side the
    overlay actually draws on -- most visible, and worst, on a group's own
    *outer*-touching edge, where (post the pad fix) that's the only thing
    standing between the overlay's label and the canvas edge.
    """
    axset = set(id(a) for a in g_axes)
    return [ax for ax in fig.axes
            if (ax._twin_of is not None and id(ax._twin_of) in axset)
            or (ax._secondary_of is not None and id(ax._secondary_of) in axset)]


def _group_bbox(fig, g, W, H, scale=1.0):
    """This group's own bounding box in pixels -- ``(x0, y0, x1, y1)`` --
    the tight union of its member axes' own allocated rects (each expanded
    for its title/tick/axis labels, see _group_axes_extra) plus ``pad`` and
    any supxlabel/supylabel inset (see _render_groups' own docstring).
    Shared by the SVG/HTML and PNG backends (``scale`` is raster.py's own
    supersampling factor -- ``W``/``H`` already come in pre-multiplied by it
    there, same as every other raster.py geometry call, but the *extras*
    below -- tick sizes, pad, label sizes -- are raw style-space numbers
    that don't know about supersampling and need it applied explicitly;
    SVG has no such factor, so its own call leaves this at the default 1.0),
    and by :meth:`Axes.remove`, which needs this exact box (computed while
    the axes is still there) to freeze into ``frozen_rect`` before
    detaching it.

    A group whose membership has ever shrunk (see :meth:`Axes.remove`:
    removing one axes drops it from the group rather than the whole group)
    stops tracking its live members at all, even the ones still left --
    ``frozen_rect`` (that same box, captured in figure-fraction units at
    the moment the *first* axes departed) stands in instead from then on,
    keeping the box wrapping the group's original structure rather than
    shrinking removal by removal down to whatever happens to be left, and
    finally to nothing measurable at all once the group empties completely.
    """
    if g["frozen_rect"] is not None:
        ghost = _ghost_group_rects(fig, g, W, H)
        if ghost is not None:
            rects, extras = ghost
            return _combine_group_rects(g, fig.style, rects, extras, W, H, scale)
        fx0, fy0, fx1, fy1 = g["frozen_rect"]
        return fx0 * W, fy0 * H, fx1 * W, fy1 * H
    st = fig.style
    members = _group_members(g, fig)
    rects = [_pixel_rect(ax, W, H) for ax in members]
    extras = [_group_colorbar_extra(ax, st) if ax._is_colorbar
             else _group_axes_extra(ax, st) for ax in members]
    return _combine_group_rects(g, st, rects, extras, W, H, scale)


def _group_members(g, fig):
    """This group's own axes plus any twin/secondary overlay and colorbar
    that :func:`_group_bbox` auto-includes with them (see its own docstring)
    -- shared with :meth:`Axes.remove`, which needs this exact list (while
    the axes about to leave is still on it) to snapshot each member's grid
    position and decoration extent into ``_ghost_specs``/``_ghost_extras``
    before detaching it, the same way :func:`_group_bbox` itself used to
    inline this just for its own one-time pixel freeze.
    """
    overlays = _group_twins_and_secondaries(g["axes"], fig)
    return g["axes"] + overlays + _group_colorbars(g["axes"] + overlays, fig)


def _combine_group_rects(g, st, rects, extras, W, H, scale):
    """The shared tail of :func:`_group_bbox`: turn a group's per-member
    ``(rects, extras)`` -- real, currently-live axes or (see
    :func:`_ghost_group_rects`) reconstructed ghosts standing in for
    departed ones -- into the group's own padded bounding box."""
    pad_l, pad_r, pad_t, pad_b = (v * scale for v in g["pad"])
    sx_size = (g["supxlabel_size"] or st.label_size * 1.2) * scale
    sy_size = (g["supylabel_size"] or st.label_size * 1.2) * scale
    sx_extent = (sx_size * 1.2 + 10 * scale) if g["supxlabel"] else 0.0
    sy_extent = (sy_size + 10 * scale) if g["supylabel"] else 0.0
    x0 = min(r[0] - e[2] * scale for r, e in zip(rects, extras)) - pad_l - sy_extent
    y0 = min(r[1] - e[0] * scale for r, e in zip(rects, extras)) - pad_t
    x1 = max(r[0] + r[2] + e[3] * scale for r, e in zip(rects, extras)) + pad_r
    y1 = max(r[1] + r[3] + e[1] * scale for r, e in zip(rects, extras)) + pad_b + sx_extent
    return x0, y0, x1, y1


def _ghost_group_rect(placement, W, H, row0, row1, col0, col1):
    """The pixel rect (same ``(left, top, w, h)`` shape as :func:`_pixel_rect`)
    a grid cell spanning ``row0..row1``/``col0..col1`` would have under
    ``placement`` -- the same ``nrows``/``ncols``/``left``/``bottom``/``axw``/
    ``axh``/``gap_w``/``gap_h`` inputs :func:`_place_spec_rects` itself takes
    (see :attr:`Figure._grid_placement`) -- whether or not any real axes
    currently occupies it. Mirrors :func:`_place_spec_rects`'s own
    col_left/row_bottom derivation exactly, then applies the same bottom-up
    fraction -> top-down pixel flip :func:`_pixel_rect` applies for a real
    axes' ``_rect``.
    """
    nrows, ncols = placement["nrows"], placement["ncols"]
    left, bottom = placement["left"], placement["bottom"]
    axw, axh = placement["axw"], placement["axh"]
    gap_w, gap_h = placement["gap_w"], placement["gap_h"]
    col_left = []
    x = left
    for c in range(ncols):
        col_left.append(x)
        x += axw + (gap_w[c] if c < ncols - 1 else 0.0)
    row_bottom = [0.0] * nrows
    y = bottom
    for r in range(nrows - 1, -1, -1):
        row_bottom[r] = y
        if r > 0:
            y += axh + gap_h[r - 1]
    x0 = col_left[col0]
    w = col_left[col1] + axw - x0
    y0_bottom_up = row_bottom[row1]
    h = row_bottom[row0] + axh - y0_bottom_up
    return (x0 * W, (1.0 - (y0_bottom_up + h)) * H, w * W, h * H)


def _ghost_group_rects(fig, g, W, H):
    """Reconstruct ``(rects, extras)`` for a fully-or-partially emptied
    group from the grid positions its axes had *before* any of them left
    (see :meth:`Axes.remove`'s ``_ghost_specs``/``_ghost_extras``), placed
    at those same positions' *current* geometry -- so the box a departed
    group's members would still occupy keeps matching its still-populated
    siblings' own width/height as tight_layout() reflows the grid, rather
    than staying pixel-locked to whatever the layout looked like the moment
    the group was first left with a gap. Returns ``None`` (falling back to
    the plain frozen pixel rect) when there's nothing to reconstruct from --
    an irregular/freeform group with no shared grid to begin with, or one
    whose recorded shape no longer matches the figure's current grid (e.g.
    after ``tight_layout(collapse="grid")`` reshaped it).
    """
    specs = g.get("_ghost_specs")
    placement = fig._grid_placement
    if not specs or placement is None:
        return None
    if g.get("_ghost_grid_shape") != (placement["nrows"], placement["ncols"]):
        return None
    rects = [_ghost_group_rect(placement, W, H, *span) for span in specs]
    return rects, g["_ghost_extras"]


def _render_groups(fig, W, H, body):
    """``Figure.group()``'s labeled boxes -- one dashed (by default) rect per
    group, tightly wrapping the union of its axes' own allocated rects (each
    expanded for its own title/tick labels/axis labels -- see
    _group_axes_extra) plus ``pad`` px of clearance per side (already
    normalized to a (left, right, top, bottom) 4-tuple by
    figure._normalize_pad, whether the caller passed one number or four),
    with the title just outside whichever edge ``title_position`` names.
    Any colorbar belonging entirely to the group's own axes (see
    _group_colorbars) is wrapped too.

    A ``supxlabel``/``supylabel`` (see :meth:`Figure.group`) draws *inside*
    the box instead, near its bottom/left edge -- the box's own bottom/left
    coordinate is pushed out first (mirroring how ``pad`` already does the
    same for plain clearance) so the label gets a dedicated inset band of
    its own rather than overlapping the member axes' last row/column of
    tick labels. tight_layout() reserves the matching margin (same
    ``* 1.2 + 10`` / ``+ 10`` extents) so the box growing here doesn't in
    turn collide with whatever is outside it.

    ``visible=False`` (see :meth:`Figure.group`/:meth:`Figure.set_group_visible`)
    skips drawing anything for a group -- box, title, supxlabel/supylabel
    alike -- same convention as :meth:`Axes.set_visible`: tight_layout()'s
    own margin reservation doesn't look at this flag at all, so a hidden
    group still holds its space and toggling it back doesn't reflow
    anything else.
    """
    st = fig.style
    for g in fig._groups:
        if not g["visible"]:
            continue
        x0, y0, x1, y1 = _group_bbox(fig, g, W, H)
        sx_size = g["supxlabel_size"] or st.label_size * 1.2
        sy_size = g["supylabel_size"] or st.label_size * 1.2
        # linestyle="none" means an invisible box (title only, still placed
        # the same) -- like every other line-drawing method, not a solid
        # border because "none" fell through _DASH.get() unmatched.
        if g["linestyle"] == "none":
            stroke_attr = 'stroke="none"'
        else:
            dash = _DASH.get(g["linestyle"])
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            stroke_attr = f'stroke="{g["color"]}" stroke-width="{g["linewidth"]}"{dash_attr}'
        body.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(x1 - x0)}" '
            f'height="{_fmt(y1 - y0)}" fill="none" {stroke_attr}/>'
        )
        size = g["fontsize"] or fig.style.title_size
        pos = g["title_position"]
        if pos == "top":
            tx, ty, anchor = (x0 + x1) / 2, y0 - 6, "middle"
        elif pos == "bottom":
            tx, ty, anchor = (x0 + x1) / 2, y1 + size + 2, "middle"
        elif pos == "left":
            tx, ty, anchor = x0 - 6, (y0 + y1) / 2 + 0.35 * size, "end"
        else:
            tx, ty, anchor = x1 + 6, (y0 + y1) / 2 + 0.35 * size, "start"
        body.append(
            f'<text x="{_fmt(tx)}" y="{_fmt(ty)}" text-anchor="{anchor}" '
            f'font-size="{size}" font-weight="bold" fill="{g["color"]}">'
            f'{_esc(g["title"])}</text>'
        )
        # Inside the box, near its bottom/left edge -- see the docstring
        # above for why these two (unlike title) are never optional-position:
        # they mirror Figure.supxlabel/supylabel's own always-bottom/
        # always-left placement, just localized to this box instead of the
        # whole canvas. Ordinary text_color, not the group's own accent
        # color -- an axis label, not part of the box's own styling.
        if g["supxlabel"]:
            body.append(
                f'<text x="{_fmt((x0 + x1) / 2)}" y="{_fmt(y1 - 6)}" '
                f'text-anchor="middle" font-size="{sx_size}" '
                f'fill="{st.text_color}">{_esc(g["supxlabel"])}</text>'
            )
        if g["supylabel"]:
            lx, ly = x0 + sy_size + 4, (y0 + y1) / 2
            body.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(ly)}" text-anchor="middle" '
                f'font-size="{sy_size}" fill="{st.text_color}" '
                f'transform="rotate(-90 {_fmt(lx)} {_fmt(ly)})">'
                f'{_esc(g["supylabel"])}</text>'
            )


def _colorbar_label(ax, fig):
    """The title of any colorbar attached to ``ax``, or ``""`` if none.

    This library's own convention for labeling what a colorbar's scale means
    is ``fig.colorbar(mesh, ax=ax).set_title("units")`` (there is no separate
    ``set_label``) -- reused here so a mesh/image/scatter pick can report what
    its color-encoded value actually means downstream, not just a bare number.
    A colorbar shared across several axes (``fig.colorbar(mesh, ax=[a, b])``)
    reports the same label for each of its parents.
    """
    for cax in fig.axes:
        if cax._is_colorbar and cax._cbar_parents and ax in cax._cbar_parents:
            return cax._title or ""
    return ""
