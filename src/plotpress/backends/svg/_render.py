"""The per-axes render dispatch (``_render_axes``) and one ``_render_*`` function
per artist kind -- the bulk of what used to be ``svg.py``.
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

from ._format import _DASH, _esc, _fmt, _pixel_rect
from ._ticks_and_frame import _render_grid, _render_labels, _render_minor_ticks, _render_spines, _render_ticks, _render_twin_ticks
from ._text_and_annotations import _render_annotation, _render_table, _render_text
from ._legend import _render_colorbar, _render_legend

def _effective_rect(ax, px_left, px_top, px_w, px_h, xlim, ylim):
    """Shrink the drawn box to honor ``set_aspect``/``set_box_aspect``, centered."""
    if ax._box_aspect is not None:
        # A fixed physical height/width ratio, independent of the data range
        # entirely -- unlike set_aspect (which shrinks to keep a *data* unit
        # the same size in x and y), this never looks at xlim/ylim at all.
        a = ax._box_aspect
        s = min(px_w, px_h / a)
        used_w, used_h = s, a * s
        return (px_left + (px_w - used_w) / 2, px_top + (px_h - used_h) / 2,
                used_w, used_h)
    if ax._aspect is None:
        return px_left, px_top, px_w, px_h
    fx = math.log10 if ax._xscale == "log" else (lambda v: v)
    fy = math.log10 if ax._yscale == "log" else (lambda v: v)
    xspan = abs(fx(xlim[1]) - fx(xlim[0])) or 1.0
    yspan = abs(fy(ylim[1]) - fy(ylim[0])) or 1.0
    a = ax._aspect
    s = min(px_w / xspan, px_h / (a * yspan))
    used_w, used_h = s * xspan, a * s * yspan
    return (px_left + (px_w - used_w) / 2, px_top + (px_h - used_h) / 2,
            used_w, used_h)


def _render_axes(ax, fig, W, H, index, defs, body):
    st = ax.style
    alloc = _pixel_rect(ax, W, H)
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    px_left, px_top, px_w, px_h = _effective_rect(ax, *alloc, (xmin, xmax), (ymin, ymax))
    xlim_t = (xmax, xmin) if ax._xinverted else (xmin, xmax)
    ylim_t = (ymax, ymin) if ax._yinverted else (ymin, ymax)
    tr = LinearTransform(xlim_t, ylim_t, (px_left, px_top, px_w, px_h),
                         xscale=ax._xscale, yscale=ax._yscale)

    clip_id = f"clip{index}"
    defs.append(
        f'<clipPath id="{clip_id}"><rect x="{_fmt(px_left)}" y="{_fmt(px_top)}" '
        f'width="{_fmt(px_w)}" height="{_fmt(px_h)}"/></clipPath>'
    )

    if not ax._visible:
        return

    if ax._is_colorbar:
        parents = [i for i, a in enumerate(fig.axes) if a in (ax._cbar_parents or ())]
        _render_colorbar(ax, tr, *alloc, clip_id, body, parents=parents or None)
        _render_labels(ax, st, *alloc, body)   # title only, by convention: set_title() labels a colorbar's scale
        return

    is_twin = ax._twin_of is not None
    is_secondary = ax._secondary_of is not None
    overlay = is_twin or is_secondary
    # Axes background (twins/secondaries overlay their parent, so neither
    # draws one).
    if not overlay:
        body.append(
            f'<rect x="{_fmt(px_left)}" y="{_fmt(px_top)}" width="{_fmt(px_w)}" '
            f'height="{_fmt(px_h)}" fill="{ax.get_facecolor()}"/>'
        )

    xticks = ax._resolve_xticks()
    yticks = ax._resolve_yticks()

    # Grid + ticks live in one group so client-side per-axes zoom can rebuild
    # them from new limits (see _interactive.py).
    body.append(f'<g id="ticks{index}">')
    if ax._grid and not ax._axis_off and not overlay:
        grid_alpha = ax._grid_alpha if ax._grid_alpha is not None else st.grid_alpha
        if ax._grid_which in ("major", "both"):
            _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body,
                        grid_alpha, axis=ax._grid_axis)
        if ax._grid_which in ("minor", "both"):
            xminor_g = (ax._xticks_minor if ax._xticks_minor is not None
                       else minor_ticks(xticks, xmin, xmax, ax._xscale))
            yminor_g = (ax._yticks_minor if ax._yticks_minor is not None
                       else minor_ticks(yticks, ymin, ymax, ax._yscale))
            _render_grid(st, tr, xminor_g, yminor_g, px_left, px_top, px_w, px_h,
                        body, grid_alpha, axis=ax._grid_axis, minor=True)
    if not ax._axis_off:
        if is_twin:
            _render_twin_ticks(ax, st, tr, xticks, yticks,
                               px_left, px_top, px_w, px_h, body)
        elif is_secondary:
            # No data of its own -- draw only the mirrored dimension's ticks,
            # on whichever side tick_top()/tick_right() (reused here) picked.
            xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
            yst = st.copy(**ax._tick_overrides["y"]) if ax._tick_overrides["y"] else st
            is_x = ax._secondary_dim == "x"
            xlabels = ax._resolve_xticklabels(xticks) if is_x else []
            ylabels = ax._resolve_yticklabels(yticks) if not is_x else []
            _render_ticks(xst, yst, tr, xticks if is_x else [], yticks if not is_x else [],
                          xlabels, ylabels, px_left, px_top, px_w, px_h, body,
                          xside=ax._xtick_side, yside=ax._ytick_side)
        else:
            xlabels = ax._resolve_xticklabels(xticks)
            ylabels = ax._resolve_yticklabels(yticks)
            xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
            yst = st.copy(**ax._tick_overrides["y"]) if ax._tick_overrides["y"] else st
            _render_ticks(xst, yst, tr, xticks, yticks, xlabels, ylabels,
                          px_left, px_top, px_w, px_h, body,
                          xside=ax._xtick_side, yside=ax._ytick_side)
            if ax._minor_ticks_on:
                mxst = (xst.copy(**ax._minor_tick_overrides["x"])
                       if ax._minor_tick_overrides["x"] else xst)
                myst = (yst.copy(**ax._minor_tick_overrides["y"])
                       if ax._minor_tick_overrides["y"] else yst)
                xminor = (ax._xticks_minor if ax._xticks_minor is not None
                         else minor_ticks(xticks, xmin, xmax, ax._xscale))
                yminor = (ax._yticks_minor if ax._yticks_minor is not None
                         else minor_ticks(yticks, ymin, ymax, ax._yscale))
                _render_minor_ticks(mxst, myst, tr, xminor, yminor,
                                    px_left, px_top, px_w, px_h, body,
                                    xside=ax._xtick_side, yside=ax._ytick_side)
    body.append("</g>")

    # Artists: fixed clip to the axes rect, then a transformable zoom group that
    # per-axes data zoom remaps via one affine (old limits -> new limits).
    body.append(f'<g clip-path="url(#{clip_id})"><g id="zoom{index}" class="plotpress-zoom">')
    # Draw order follows zorder (ties keep call order), but k stays each
    # artist's own call-order index -- pick/series ids and legend order must
    # stay stable regardless of what zorder does to the visual stacking.
    draw_order = sorted(enumerate(ax.artists), key=lambda ka: (ka[1].zorder, ka[0]))
    axes_fraction_artists = []
    for k, artist in draw_order:
        if isinstance(artist, QuadMesh) and artist.vectorized:
            _render_mesh_vector(artist, tr, index, k, body)
            continue
        prims = artist_to_prims(artist, tr, index, k, size_scale=st.dpi / 72.0)
        if prims is not None:
            body.extend(_emit_prim(p) for p in prims)
            continue
        if isinstance(artist, FrameLine2D):
            _render_frameline(artist, tr, index, k, body)
        elif isinstance(artist, FrameQuadMesh):
            _render_framequadmesh(artist, tr, index, k, body)
        elif isinstance(artist, Bars):
            _render_bars(artist, tr, index, k, body, defs)
        elif isinstance(artist, Stem):
            _render_stem(artist, tr, st, fig, body)
        elif isinstance(artist, ErrorBar):
            _render_errorbar(artist, tr, st, fig, body)
        elif isinstance(artist, Pie):
            # Drawn in axes-*pixel* space (see _render_pie) so it stays
            # circular regardless of xlim/ylim -- it has no data-space
            # geometry to begin with, so it belongs outside the zoom group
            # entirely, the same as table()/transform=ax.transAxes text.
            # Left inside it, a per-axes data zoom's matrix(sx,sy,...)
            # stretched the whole pie into a rectangle instead of leaving it
            # alone, since non-uniform sx/sy has nothing to do with a pie's
            # own (data-independent) circular shape.
            axes_fraction_artists.append(artist)
        elif isinstance(artist, BoxPlot):
            _render_boxplot(artist, tr, st, body)
        elif isinstance(artist, Violin):
            _render_violin(artist, tr, body)
        elif isinstance(artist, EventPlot):
            _render_eventplot(artist, tr, body)
        elif isinstance(artist, Quiver):
            _render_quiver(artist, tr, body)
        elif isinstance(artist, Barbs):
            _render_barbs(artist, tr, st, body)
        elif isinstance(artist, Contour):
            _render_contour(artist, tr, body)
        elif isinstance(artist, Text):
            if artist.axes_fraction:
                axes_fraction_artists.append(artist)
            else:
                _render_text(artist, tr, st, body, index=index)
        elif isinstance(artist, Annotation):
            if artist.axes_fraction:
                axes_fraction_artists.append(artist)
            else:
                _render_annotation(artist, tr, st, body, index=index)
        elif isinstance(artist, Table):
            axes_fraction_artists.append(artist)   # always axes-fraction, like a table() bbox
    body.append("</g>")   # close the zoom group only -- axes-fraction text is next
    # transform=ax.transAxes text/annotate (and table(), always axes-fraction)
    # sit at a fixed spot on the axes *frame*, not the data -- rendered
    # outside the zoom group so a per-axes data zoom/pan leaves them alone,
    # still inside the clip group so they can't spill past the axes rect the
    # way a data-anchored label already can't.
    for artist in axes_fraction_artists:
        if isinstance(artist, Text):
            _render_text(artist, tr, st, body)
        elif isinstance(artist, Annotation):
            _render_annotation(artist, tr, st, body)
        elif isinstance(artist, Pie):
            _render_pie(artist, tr, body)
        else:
            _render_table(artist, tr, st, body)
    body.append("</g>")   # close the clip group

    if not ax._axis_off and not overlay:
        _render_spines(ax, px_left, px_top, px_w, px_h, body)
    # A twin's axis label is drawn inline by _render_twin_ticks; a secondary
    # axis has no such bespoke renderer, so it goes through the generic (now
    # tick-side-aware) label placement below, same as an ordinary axes.
    if not is_twin:
        _render_labels(ax, st, px_left, px_top, px_w, px_h, body)

    if ax._show_legend:
        _render_legend(ax, st, px_left, px_top, px_w, px_h, body)


def _seg_to_path(seg: np.ndarray) -> str:
    """Serialize one contiguous run of points to ``M x,y L x,y ...``.

    Uses vectorized ``numpy.char`` formatting instead of per-point Python
    f-strings. Combined with min/max decimation of huge lines (see
    :func:`_decimate_minmax`), this keeps large-series serialization fast in
    pure NumPy.
    """
    xs = np.char.mod("%.2f", seg[:, 0])
    ys = np.char.mod("%.2f", seg[:, 1])
    coords = np.char.add(np.char.add(xs, ","), ys)
    return "M" + "L".join(coords.tolist())


def _line_path_d(pts: np.ndarray) -> str:
    """Build an SVG path ``d`` string, splitting on non-finite points."""
    mask = np.isfinite(pts).all(axis=1)
    if mask.all():
        return _seg_to_path(pts) if len(pts) else ""
    n = len(pts)
    out = []
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        out.append(_seg_to_path(pts[i:j]))
        i = j
    return "".join(out)


def _path_d(subpaths, closed):
    d = "".join(_seg_to_path(s) for s in subpaths if len(s))
    return (d + "Z") if (closed and d) else d


def _prim_color(c):
    return c if isinstance(c, str) else "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))


def _emit_markers(p) -> str:
    shape = getattr(p, "shape", "o") or "o"
    if shape in ("o", "."):
        return _emit_round_markers(p)
    return _emit_shaped_markers(p, shape)


def _emit_round_markers(p) -> str:
    """Round markers as zero-length round-capped strokes -> circular dots.

    Tagged ``plotpress-marker`` so the interactive CSS (see _interactive.py)
    can single them out of the zoom group's usual non-scaling-stroke rule --
    a marker represents a footprint on the *data*, so it should grow or
    shrink with a per-axes zoom the same way the axis itself does, unlike a
    line's stroke width (still constant screen size, deliberately, so a thin
    line doesn't vanish when zoomed out) or a point-pick pin (its own
    separate constant-size mechanism -- see layoutPin).
    """
    pts, diam = p.points, p.diameters
    finite = np.isfinite(pts).all(axis=1)
    op = f' stroke-opacity="{p.alpha}"' if p.alpha < 1 else ""
    idattr = f' id="{p.series_id}"' if p.series_id else ""

    def dot(cx, cy):
        return f"M{_fmt(cx)},{_fmt(cy)}L{_fmt(cx)},{_fmt(cy)}"

    parts = []
    same_size = diam.size and float(np.ptp(diam)) < 1e-9
    edged = getattr(p, "edgecolor", None) and getattr(p, "edgewidth", 0) > 0
    if edged:
        # An outline drawn as *wider* dots underneath the face dots, not an
        # actual stroke -- the face/edge dots are each their own zero-length
        # round-capped stroke (see the docstring above), so stacking a wider
        # one in the edge color behind each keeps both a constant pixel size
        # under zoom, the same property a real <circle stroke> would lose.
        if same_size:
            edge_d = "".join(dot(cx, cy) for (cx, cy), ok in zip(pts, finite) if ok)
            parts.append(
                f'<path d="{edge_d}" fill="none" stroke="{p.edgecolor}" '
                f'stroke-width="{_fmt(float(diam[0]) + 2 * p.edgewidth if diam.size else 0)}" '
                f'stroke-linecap="round"/>')
        else:
            for (cx, cy), dm, ok in zip(pts, diam, finite):
                if ok:
                    parts.append(
                        f'<path d="{dot(cx, cy)}" fill="none" stroke="{p.edgecolor}" '
                        f'stroke-width="{_fmt(dm + 2 * p.edgewidth)}" stroke-linecap="round"/>')
    if p.single_color and same_size:
        d = "".join(dot(cx, cy) for (cx, cy), ok in zip(pts, finite) if ok)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{p.colors[0]}" '
            f'stroke-width="{_fmt(float(diam[0]) if diam.size else 0)}" '
            f'stroke-linecap="round"/>')
    else:
        for (cx, cy), dm, col, ok in zip(pts, diam, p.colors, finite):
            if ok:
                parts.append(
                    f'<path d="{dot(cx, cy)}" fill="none" stroke="{col}" '
                    f'stroke-width="{_fmt(dm)}" stroke-linecap="round"/>')
    return (f'<g class="plotpress-series plotpress-marker"{idattr} '
            f'data-label="{_esc(p.label)}"{op}>{"".join(parts)}</g>')


def _emit_shaped_markers(p, shape: str) -> str:
    """Non-round marker shapes -- square/triangle(x4)/diamond as filled
    polygons, plus/x as open strokes -- batched into one ``<path>`` per
    (shape, color) group in the common case (one color, one size), the same
    discipline :func:`_emit_round_markers` uses for the round case.

    Each polygon/stroke is built from :func:`~plotpress.primitives.
    marker_polygon`/``marker_strokes``, offset from the marker's own pixel
    center -- unlike the round case's zero-length-stroke trick, this needs a
    real per-point coordinate list, but it's the same vertex count either
    way (a handful of points per marker, nothing close to mesh-cell scale).
    """
    pts, diam = p.points, p.diameters
    finite = np.isfinite(pts).all(axis=1)
    idattr = f' id="{p.series_id}"' if p.series_id else ""
    is_stroke = marker_shape_kind(shape) == "stroke"
    same_size = diam.size and float(np.ptp(diam)) < 1e-9

    def path_d(cx, cy, r):
        if is_stroke:
            return "".join(
                f"M{_fmt(cx + ax)},{_fmt(cy + ay)}L{_fmt(cx + bx)},{_fmt(cy + by)}"
                for (ax, ay), (bx, by) in marker_strokes(shape, r))
        verts = marker_polygon(shape, r)
        head = f"M{_fmt(cx + verts[0][0])},{_fmt(cy + verts[0][1])}"
        tail = "".join(f"L{_fmt(cx + dx)},{_fmt(cy + dy)}" for dx, dy in verts[1:])
        return head + tail + "Z"

    parts = []
    if is_stroke:
        # An open shape (plus/x) has no interior to fill and no separate
        # edge to outline -- its "color" is the stroke itself, matching
        # matplotlib's own plus/x markers.
        op = f' stroke-opacity="{p.alpha}"' if p.alpha < 1 else ""
        if p.single_color and same_size:
            d = "".join(path_d(cx, cy, dm / 2.0)
                       for (cx, cy), dm, ok in zip(pts, diam, finite) if ok)
            w = float(diam[0]) * 0.28 if diam.size else 1.0
            parts.append(f'<path d="{d}" fill="none" stroke="{p.colors[0]}" '
                        f'stroke-width="{_fmt(w)}" stroke-linecap="round"{op}/>')
        else:
            for (cx, cy), dm, col, ok in zip(pts, diam, p.colors, finite):
                if ok:
                    parts.append(f'<path d="{path_d(cx, cy, dm / 2.0)}" fill="none" '
                                f'stroke="{col}" stroke-width="{_fmt(dm * 0.28)}" '
                                f'stroke-linecap="round"{op}/>')
    else:
        op = f' fill-opacity="{p.alpha}"' if p.alpha < 1 else ""
        edged = getattr(p, "edgecolor", None) and getattr(p, "edgewidth", 0) > 0
        edge_attr = (f' stroke="{p.edgecolor}" stroke-width="{_fmt(p.edgewidth)}"'
                    if edged else ' stroke="none"')
        if p.single_color and same_size:
            d = "".join(path_d(cx, cy, dm / 2.0)
                       for (cx, cy), dm, ok in zip(pts, diam, finite) if ok)
            parts.append(f'<path d="{d}" fill="{p.colors[0]}"{edge_attr}{op}/>')
        else:
            for (cx, cy), dm, col, ok in zip(pts, diam, p.colors, finite):
                if ok:
                    parts.append(f'<path d="{path_d(cx, cy, dm / 2.0)}" '
                                f'fill="{col}"{edge_attr}{op}/>')
    return (f'<g class="plotpress-series plotpress-marker"{idattr} '
            f'data-label="{_esc(p.label)}">{"".join(parts)}</g>')


def _emit_prim(p) -> str:
    """Serialize one backend-agnostic primitive to an SVG element."""
    if isinstance(p, PImage):
        uri = png_data_uri(p.rgba)
        style = "" if p.smooth else ' style="image-rendering:pixelated"'
        # class/data-label match every other series (see _emit_prim's PLine/PRect
        # branches below) so the legend's click-to-hide toggle -- which matches
        # on .plotpress-series + data-label -- can find a raster mesh/image the
        # same way it already finds a vectorized one. plotpress-mesh (shared
        # with _render_mesh_vector's own <g>, the other of the two ways a
        # QuadMesh/Image artist can reach the page -- see
        # artists._resolve_mesh_render) is the interactive Slice tool's own
        # hook for "hide whichever of the two this axes actually used" when
        # switching to its 1-D slice view (renderMeshOrSlice); .plotpress-series
        # alone can't do that since plain lines/bars/fills share it too.
        return (f'<image class="plotpress-series plotpress-mesh" '
                f'data-label="{_esc(p.label)}" '
                f'x="{_fmt(p.x)}" y="{_fmt(p.y)}" width="{_fmt(p.w)}" '
                f'height="{_fmt(p.h)}" preserveAspectRatio="none"'
                f'{style} href="{uri}"/>')
    if isinstance(p, PMarkers):
        return _emit_markers(p)
    lbl = _esc(p.label) if p.label else ""
    if isinstance(p, PLine):
        attrs = f'stroke="{p.stroke}" stroke-width="{p.stroke_width}"'
        dash = _DASH.get(p.linestyle)
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        if p.stroke_opacity < 1:
            attrs += f' stroke-opacity="{p.stroke_opacity}"'
        return (f'<line class="plotpress-series" data-label="{lbl}" '
                f'x1="{_fmt(p.p0[0])}" y1="{_fmt(p.p0[1])}" x2="{_fmt(p.p1[0])}" '
                f'y2="{_fmt(p.p1[1])}" {attrs}/>')
    if isinstance(p, PRect):
        return (f'<rect class="plotpress-series" data-label="{lbl}" '
                f'x="{_fmt(p.x)}" y="{_fmt(p.y)}" width="{_fmt(p.w)}" '
                f'height="{_fmt(p.h)}" fill="{p.fill}" fill-opacity="{p.fill_opacity}"/>')
    if isinstance(p, PSegments):
        dash = _DASH.get(p.linestyle)
        lines = "".join(
            f'<line x1="{_fmt(a)}" y1="{_fmt(b)}" x2="{_fmt(c)}" y2="{_fmt(d)}"/>'
            for a, b, c, d in p.segs)
        attrs = f'stroke="{p.stroke}" stroke-width="{p.stroke_width}"'
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        if p.stroke_opacity < 1:
            attrs += f' stroke-opacity="{p.stroke_opacity}"'
        return f'<g class="plotpress-series" data-label="{lbl}" {attrs}>{lines}</g>'
    if isinstance(p, PPolyBatch):
        edge = f'stroke="{p.edge}"' if p.edge else 'stroke="none"'
        op = f' fill-opacity="{p.alpha}"' if p.alpha < 1 else ""
        out = [f'<g class="plotpress-series" {edge} stroke-width="{p.edge_width}">']
        for verts, fc in zip(p.polys, p.fills):
            coords = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in verts)
            out.append(f'<polygon points="{coords}" fill="{_prim_color(fc)}"{op}/>')
        out.append("</g>")
        return "".join(out)
    if isinstance(p, PPath):
        idattr = f' id="{p.series_id}"' if p.series_id else ""
        # A <title> child is a real, no-JS browser tooltip on hover -- the
        # one bit of the interactive toolbar's "what series is this" that a
        # static SVG (a README, a Sphinx gallery page, a PDF/print viewer
        # that renders SVG) can still offer without the JS payload at all.
        title = f"<title>{lbl}</title>" if p.label else ""
        if p.element == "polygon":
            pts = p.subpaths[0]
            coords = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts
                              if np.isfinite([x, y]).all())
            stroke = (f'stroke="{p.stroke}" stroke-width="{p.stroke_width}"'
                      if p.stroke else 'stroke="none"')
            return (f'<polygon class="plotpress-series"{idattr} data-label="{lbl}" '
                    f'points="{coords}" fill="{p.fill}" '
                    f'fill-opacity="{p.fill_opacity}" {stroke}>{title}</polygon>')
        d = _path_d(p.subpaths, p.closed)
        fill = (f'fill="{p.fill}" fill-opacity="{p.fill_opacity}"'
                if p.fill else 'fill="none"')
        stroke = (f'stroke="{p.stroke}" stroke-width="{p.stroke_width}" '
                  f'stroke-linejoin="round" stroke-linecap="round"'
                  if p.stroke else 'stroke="none"')
        attrs = f'{fill} {stroke}'
        dash = _DASH.get(p.linestyle)
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        if p.stroke_opacity < 1:
            attrs += f' stroke-opacity="{p.stroke_opacity}"'
        return (f'<path class="plotpress-series"{idattr} data-label="{lbl}" '
                f'd="{d}" {attrs}>{title}</path>')
    raise TypeError(f"unknown primitive {type(p).__name__}")


def _render_frameline(art: FrameLine2D, tr, ai, k, body):
    """Render frame 0 statically; the slider JS rewrites ``d`` for other frames."""
    x0, y0 = art.frame_xy(0)
    d = _line_path_d(tr.xy(x0, y0))
    # linestyle="none" means invisible, not "no <path> at all" -- unlike
    # plain plot(), plot_frames() has no marker to fall back to, and the
    # slider JS needs this element's id to keep existing across every frame
    # it scrubs to (it rewrites `d` in place, it doesn't recreate the node).
    if art.linestyle == "none":
        attrs = 'fill="none" stroke="none"'
    else:
        dash = _DASH.get(art.linestyle)
        attrs = (
            f'fill="none" stroke="{art.color}" stroke-width="{art.linewidth}" '
            f'stroke-linejoin="round" stroke-linecap="round"'
        )
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        if art.alpha < 1:
            attrs += f' stroke-opacity="{art.alpha}"'
    label = _esc(art.label) if art.label else ""
    body.append(
        f'<path class="plotpress-series plotpress-frameline" id="s{ai}_{k}" '
        f'data-label="{label}" d="{d}" {attrs}/>'
    )


def _render_framequadmesh(art: FrameQuadMesh, tr, ai, k, body):
    """Render frame 0 statically; the slider JS swaps ``href`` for other frames.

    Unlike a frame line's ``d``, the image's ``x``/``y``/``width``/``height``
    never need to be recomputed on scrub: every frame shares one X/Y grid, so
    only the pixel content -- which frame's colours -- changes.
    """
    prims = artist_to_prims(art.frame_mesh(0), tr, ai, k)
    if not prims:
        return
    p = prims[0]
    uri = png_data_uri(p.rgba)
    label = _esc(art.label) if art.label else ""
    # plotpress-mesh (shared with a plain QuadMesh/Image's own raster/
    # vectorized rendering -- see _emit_prim's PImage branch) is the
    # interactive Slice tool's hook for hiding this mesh when switching to
    # its 1-D slice view; plotpress-framemesh is a separate, pre-existing
    # marker with its own callers and stays untouched.
    body.append(
        f'<image class="plotpress-series plotpress-framemesh plotpress-mesh" '
        f'id="s{ai}_{k}" data-label="{label}" x="{_fmt(p.x)}" y="{_fmt(p.y)}" '
        f'width="{_fmt(p.w)}" height="{_fmt(p.h)}" preserveAspectRatio="none" '
        f'style="image-rendering:pixelated" href="{uri}"/>'
    )


def _render_mesh_vector(art: QuadMesh, tr, ai, k, body):
    """One ``<rect>`` per cell, in exact data-edge positions -- no resampling.

    Reached only when ``art.vectorized`` (see ``artists._resolve_mesh_render``),
    i.e. a non-uniform, non-curvilinear grid small enough that per-cell rects
    stay cheap. Unlike the raster path, there is no pixel grid here for a thin
    cell to fall between: every cell gets its own rect, at its own true edges,
    however narrow. A NaN cell (alpha 0) is simply skipped rather than drawn
    transparent -- an absent rect and a fully transparent one look identical
    but the absent one costs nothing.

    Coordinates and colors are batch-formatted with vectorized ``numpy.char``
    calls (the same approach ``_seg_to_path`` uses for a huge line's path
    string) rather than one Python format call per cell -- up to
    ``_VECTOR_CELL_LIMIT`` of them.
    """
    xe, ye = art.cell_edges()
    xpix = tr.x(xe)
    ypix = tr.y(ye)
    rgba = apply_colormap(art.C, art.lut, art.norm)
    ny, nx = art.C.shape
    label = _esc(art.label) if art.label else ""
    op = f' fill-opacity="{art.alpha}"' if art.alpha < 1 else ""

    x0 = np.minimum(xpix[:-1], xpix[1:])
    w = np.abs(np.diff(xpix))
    y0 = np.minimum(ypix[:-1], ypix[1:])
    h = np.abs(np.diff(ypix))
    # Broadcast each axis's per-cell geometry across the other axis, then
    # flatten row-major (y, x) to match rgba's own (ny, nx, 4) layout.
    X0 = np.broadcast_to(x0, (ny, nx)).ravel()
    W = np.broadcast_to(w, (ny, nx)).ravel()
    Y0 = np.broadcast_to(y0[:, None], (ny, nx)).ravel()
    H = np.broadcast_to(h[:, None], (ny, nx)).ravel()

    visible = (rgba[..., 3] != 0).ravel()
    if not visible.any():
        return
    X0, Y0, W, H = X0[visible], Y0[visible], W[visible], H[visible]
    rgb = rgba[..., :3].reshape(-1, 3)[visible]

    fmt = lambda v: np.char.mod("%.2f", v)  # noqa: E731 -- local, used 4x below
    hexcolor = np.char.add(np.char.add(np.char.add(
        "#", np.char.mod("%02x", rgb[:, 0].astype(int))),
        np.char.mod("%02x", rgb[:, 1].astype(int))),
        np.char.mod("%02x", rgb[:, 2].astype(int)))

    rects = '<rect x="'
    for piece in (fmt(X0), '" y="', fmt(Y0), '" width="', fmt(W),
                 '" height="', fmt(H), '" fill="', hexcolor, '"/>'):
        rects = np.char.add(rects, piece)

    # plotpress-mesh (shared with _emit_prim's PImage branch, the raster
    # path a large/uniform mesh takes instead) is the interactive Slice
    # tool's own hook for finding this mesh's on-screen element regardless
    # of which of the two rendering paths it actually took -- see that
    # branch's own comment.
    body.append(
        f'<g class="plotpress-series plotpress-mesh" id="s{ai}_{k}" '
        f'data-label="{label}"{op}>{"".join(rects.tolist())}</g>'
    )


_HATCH_ANGLES = {"|": 0, "-": 90, "/": 45, "\\": -45}


_HATCH_NAMES = {"|": "v", "-": "h", "/": "fs", "\\": "bs", "+": "plus", "x": "x"}


_HATCH_SIZE = 6.0


def _hatch_pattern_id(hatch: str, fill: str) -> str:
    return f"hatch_{_HATCH_NAMES.get(hatch, 'u')}_{fill.lstrip('#')}"


def _defs_has_id(defs: list, pid: str) -> bool:
    marker = f'id="{pid}"'
    return any(marker in d for d in defs)


def _hatch_pattern_def(hatch: str, fill: str) -> str | None:
    """An SVG ``<pattern>`` tiling ``hatch`` lines (always black, matplotlib's
    own default) over a ``fill``-colored background, or ``None`` if ``hatch``
    isn't one this library draws.
    """
    size = _HATCH_SIZE
    pid = _hatch_pattern_id(hatch, fill)
    bg = f'<rect width="{size}" height="{size}" fill="{fill}"/>'
    if hatch in _HATCH_ANGLES:
        transform = f' patternTransform="rotate({_HATCH_ANGLES[hatch]})"'
        lines = f'<line x1="0" y1="0" x2="0" y2="{size}" stroke="#000000" stroke-width="1"/>'
    elif hatch == "+":
        transform = ""
        lines = (f'<line x1="0" y1="0" x2="0" y2="{size}" stroke="#000000" stroke-width="1"/>'
                f'<line x1="0" y1="0" x2="{size}" y2="0" stroke="#000000" stroke-width="1"/>')
    elif hatch == "x":
        transform = ""
        lines = (f'<line x1="0" y1="0" x2="{size}" y2="{size}" stroke="#000000" stroke-width="1"/>'
                f'<line x1="{size}" y1="0" x2="0" y2="{size}" stroke="#000000" stroke-width="1"/>')
    else:
        return None
    return (f'<pattern id="{pid}" width="{size}" height="{size}" '
            f'patternUnits="userSpaceOnUse"{transform}>{bg}{lines}</pattern>')


def _render_bars(bars: Bars, tr, ai, k, body, defs):
    label = _esc(bars.label) if bars.label else ""
    op = f' fill-opacity="{bars.alpha}"' if bars.alpha < 1 else ""
    edge = (f' stroke="{bars.edgecolor}" stroke-width="{bars.linewidth}"'
            if bars.edgecolor else "")
    hatch = getattr(bars, "hatch", None)
    fill_urls = {}
    if hatch:
        # dict.fromkeys, not set(): a plain set's iteration order depends on
        # Python's per-process randomized string hashing, so the <defs>
        # block (and the exact SVG bytes) would otherwise vary run to run
        # for any hatched series with more than one color -- breaking
        # byte-identical regeneration (golden-file tests, doc diffs).
        for fill in dict.fromkeys(bars.colors):
            pdef = _hatch_pattern_def(hatch, fill)
            if pdef is None:
                break   # not a hatch this library draws -- fall back to plain fill
            pid = _hatch_pattern_id(hatch, fill)
            if not _defs_has_id(defs, pid):
                defs.append(pdef)
            fill_urls[fill] = f"url(#{pid})"
    rects = []
    for i in range(len(bars.pos)):
        p, ln, th, ba = bars.pos[i], bars.length[i], bars.thickness[i], bars.base[i]
        if bars.orientation == "vertical":
            x0, x1 = tr.x(p - th / 2), tr.x(p + th / 2)
            y0, y1 = tr.y_base(ba), tr.y_base(ba + ln)
        else:
            y0, y1 = tr.y(p - th / 2), tr.y(p + th / 2)
            x0, x1 = tr.x_base(ba), tr.x_base(ba + ln)
        rx, ry = min(x0, x1), min(y0, y1)
        fill = fill_urls.get(bars.colors[i], bars.colors[i])
        rects.append(
            f'<rect x="{_fmt(rx)}" y="{_fmt(ry)}" width="{_fmt(abs(x1 - x0))}" '
            f'height="{_fmt(abs(y1 - y0))}" fill="{fill}"{edge}/>'
        )
    body.append(
        f'<g class="plotpress-series" id="s{ai}_{k}" data-label="{label}"{op}>'
        f'{"".join(rects)}</g>'
    )


def _render_stem(stem: Stem, tr, st, fig, body):
    if stem.x.size == 0:
        return
    xb = tr.x(stem.x)
    yb = tr.y(stem.y)
    y0 = tr.y_base(stem.baseline)
    lines = [f'<line x1="{_fmt(x)}" y1="{_fmt(y0)}" x2="{_fmt(x)}" y2="{_fmt(y)}"/>'
             for x, y in zip(xb, yb)]
    body.append(
        f'<g stroke="{stem.linecolor}" stroke-width="1.2">{"".join(lines)}</g>'
    )
    x0, x1 = tr.x(stem.x.min()), tr.x(stem.x.max())
    body.append(
        f'<line x1="{_fmt(x0)}" y1="{_fmt(y0)}" x2="{_fmt(x1)}" y2="{_fmt(y0)}" '
        f'stroke="{st.spine_color}" stroke-width="0.8"/>'
    )
    r = st.marker_size / 2.0 * st.dpi / 72.0
    dots = [f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{_fmt(r)}" fill="{stem.markercolor}"/>'
            for x, y in zip(xb, yb)]
    body.append("".join(dots))


def _render_errorbar(eb: ErrorBar, tr, st, fig, body):
    xb = tr.x(eb.x)
    yb = tr.y(eb.y)
    if eb.linestyle and eb.linestyle != "none":
        d = _line_path_d(np.column_stack([xb, yb]))
        if d:
            body.append(
                f'<path fill="none" stroke="{eb.color}" '
                f'stroke-width="{eb.linewidth}" d="{d}"/>'
            )
    whiskers, caps, cap = [], [], eb.capsize
    every = eb.errorevery
    if eb.yerr is not None:
        # An error bar reaching below zero on a log axis has no pixel to land
        # on; clamp the whisker to the frame rather than emitting NaN, which
        # drops the whole bar and quietly understates the uncertainty.
        ylo, yhi = tr.y_base(eb.y - eb.yerr), tr.y_base(eb.y + eb.yerr)
        for i, (x, a, b) in enumerate(zip(xb, ylo, yhi)):
            if i % every:
                continue
            whiskers.append(f'<line x1="{_fmt(x)}" y1="{_fmt(a)}" x2="{_fmt(x)}" y2="{_fmt(b)}"/>')
            caps.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(a)}" x2="{_fmt(x + cap)}" y2="{_fmt(a)}"/>')
            caps.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(b)}" x2="{_fmt(x + cap)}" y2="{_fmt(b)}"/>')
    if eb.xerr is not None:
        xlo, xhi = tr.x_base(eb.x - eb.xerr), tr.x_base(eb.x + eb.xerr)
        for i, (y, a, b) in enumerate(zip(yb, xlo, xhi)):
            if i % every:
                continue
            whiskers.append(f'<line x1="{_fmt(a)}" y1="{_fmt(y)}" x2="{_fmt(b)}" y2="{_fmt(y)}"/>')
            caps.append(f'<line x1="{_fmt(a)}" y1="{_fmt(y - cap)}" x2="{_fmt(a)}" y2="{_fmt(y + cap)}"/>')
            caps.append(f'<line x1="{_fmt(b)}" y1="{_fmt(y - cap)}" x2="{_fmt(b)}" y2="{_fmt(y + cap)}"/>')
    if whiskers:
        body.append(f'<g stroke="{eb.ecolor}" stroke-width="{_fmt(eb.elinewidth)}">{"".join(whiskers)}</g>')
    if caps:
        body.append(f'<g stroke="{eb.ecolor}" stroke-width="{_fmt(eb.capthick)}">{"".join(caps)}</g>')
    r = eb.markersize / 2.0 * st.dpi / 72.0
    # Skip points that do not map to a pixel -- a value at or below zero on a
    # log axis, most often. Emitting cx/cy="nan" produces invalid SVG that some
    # renderers reject outright rather than merely skipping the one marker.
    shape = normalize_marker_shape(eb.marker) or "o"
    finite_xy = [(x, y) for x, y in zip(xb, yb) if np.isfinite(x) and np.isfinite(y)]
    if shape in ("o", "."):
        dots = [f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{_fmt(r)}" fill="{eb.color}"/>'
                for x, y in finite_xy]
        body.append("".join(dots))
    elif marker_shape_kind(shape) == "stroke":
        w = r * 0.56
        segs = "".join(
            f"M{_fmt(x + ax)},{_fmt(y + ay)}L{_fmt(x + bx)},{_fmt(y + by)}"
            for x, y in finite_xy for (ax, ay), (bx, by) in marker_strokes(shape, r)
        )
        if segs:
            body.append(
                f'<path d="{segs}" fill="none" stroke="{eb.color}" '
                f'stroke-width="{_fmt(w)}" stroke-linecap="round"/>')
    else:
        polys = []
        for x, y in finite_xy:
            verts = marker_polygon(shape, r)
            head = f"M{_fmt(x + verts[0][0])},{_fmt(y + verts[0][1])}"
            tail = "".join(f"L{_fmt(x + dx)},{_fmt(y + dy)}" for dx, dy in verts[1:])
            polys.append(head + tail + "Z")
        if polys:
            body.append(f'<path d="{"".join(polys)}" fill="{eb.color}"/>')


def _render_pie(pie: Pie, tr, body):
    """Draw wedges in axes-pixel space so the pie stays circular."""
    cx, cy, R = pie_center_radius(tr.px_w, tr.px_h, pie.radius, tr.px_left, tr.px_top)
    label_rows = pie_label_positions(pie.fracs, pie.startangle, cx, cy, R)
    ang = math.radians(pie.startangle)
    op = f' fill-opacity="{pie.alpha}"' if pie.alpha < 1 else ""
    parts = []
    labels = []
    for i, frac in enumerate(pie.fracs):
        sweep = frac * 2 * math.pi
        a0, a1 = ang, ang - sweep  # clockwise, matplotlib default
        x0, y0 = cx + R * math.cos(a0), cy - R * math.sin(a0)
        x1, y1 = cx + R * math.cos(a1), cy - R * math.sin(a1)
        large = 1 if sweep > math.pi else 0
        parts.append(
            f'<path d="M{_fmt(cx)},{_fmt(cy)} L{_fmt(x0)},{_fmt(y0)} '
            f'A{_fmt(R)},{_fmt(R)} 0 {large} 1 {_fmt(x1)},{_fmt(y1)} Z" '
            f'fill="{pie.colors[i]}" stroke="#ffffff" stroke-width="1.5"{op}/>'
        )
        row = label_rows[i]
        if pie.labels is not None:
            anchor = "start" if row["right_side"] else "end"
            labels.append(
                f'<text x="{_fmt(row["label_x"])}" y="{_fmt(row["label_y"])}" text-anchor="{anchor}" '
                f'font-size="10" dominant-baseline="middle">{_esc(pie.labels[i])}</text>'
            )
        pct = pie.pct_text(frac)
        if pct is not None:
            labels.append(
                f'<text x="{_fmt(row["pct_x"])}" y="{_fmt(row["pct_y"])}" text-anchor="middle" '
                f'font-size="10" dominant-baseline="middle">{_esc(pct)}</text>'
            )
        ang = a1
    body.append("".join(parts) + "".join(labels))


def _render_boxplot(bp: BoxPlot, tr, st, body):
    vert = bp.orientation == "vertical"
    parts = []
    r = st.marker_size / 2.0 * st.dpi / 72.0
    for pos, s in zip(bp.positions, bp.stats):
        c0, c1 = pos - bp.width / 2, pos + bp.width / 2
        if vert:
            x0, x1 = tr.x(c0), tr.x(c1)
            yq1, yq3, ym = tr.y(s["q1"]), tr.y(s["q3"]), tr.y(s["med"])
            ylo, yhi = tr.y(s["lo"]), tr.y(s["hi"])
            xc = tr.x(pos)
            parts.append(f'<rect x="{_fmt(min(x0, x1))}" y="{_fmt(min(yq1, yq3))}" '
                         f'width="{_fmt(abs(x1 - x0))}" height="{_fmt(abs(yq3 - yq1))}" '
                         f'fill="none" stroke="{bp.color}" stroke-width="1.3"/>')
            parts.append(f'<line x1="{_fmt(x0)}" y1="{_fmt(ym)}" x2="{_fmt(x1)}" y2="{_fmt(ym)}" stroke="{bp.color}" stroke-width="1.8"/>')
            parts.append(f'<line x1="{_fmt(xc)}" y1="{_fmt(yq1)}" x2="{_fmt(xc)}" y2="{_fmt(ylo)}" stroke="{bp.color}" stroke-width="1"/>')
            parts.append(f'<line x1="{_fmt(xc)}" y1="{_fmt(yq3)}" x2="{_fmt(xc)}" y2="{_fmt(yhi)}" stroke="{bp.color}" stroke-width="1"/>')
            parts.append(f'<line x1="{_fmt(x0)}" y1="{_fmt(ylo)}" x2="{_fmt(x1)}" y2="{_fmt(ylo)}" stroke="{bp.color}" stroke-width="1"/>')
            parts.append(f'<line x1="{_fmt(x0)}" y1="{_fmt(yhi)}" x2="{_fmt(x1)}" y2="{_fmt(yhi)}" stroke="{bp.color}" stroke-width="1"/>')
            for fx in s["fliers"]:
                parts.append(f'<circle cx="{_fmt(xc)}" cy="{_fmt(tr.y(fx))}" r="{_fmt(r)}" fill="none" stroke="{bp.color}"/>')
        else:
            y0, y1 = tr.y(c0), tr.y(c1)
            xq1, xq3, xm = tr.x(s["q1"]), tr.x(s["q3"]), tr.x(s["med"])
            xlo, xhi = tr.x(s["lo"]), tr.x(s["hi"])
            yc = tr.y(pos)
            parts.append(f'<rect x="{_fmt(min(xq1, xq3))}" y="{_fmt(min(y0, y1))}" '
                         f'width="{_fmt(abs(xq3 - xq1))}" height="{_fmt(abs(y1 - y0))}" '
                         f'fill="none" stroke="{bp.color}" stroke-width="1.3"/>')
            parts.append(f'<line x1="{_fmt(xm)}" y1="{_fmt(y0)}" x2="{_fmt(xm)}" y2="{_fmt(y1)}" stroke="{bp.color}" stroke-width="1.8"/>')
            parts.append(f'<line x1="{_fmt(xq1)}" y1="{_fmt(yc)}" x2="{_fmt(xlo)}" y2="{_fmt(yc)}" stroke="{bp.color}" stroke-width="1"/>')
            parts.append(f'<line x1="{_fmt(xq3)}" y1="{_fmt(yc)}" x2="{_fmt(xhi)}" y2="{_fmt(yc)}" stroke="{bp.color}" stroke-width="1"/>')
            parts.append(f'<line x1="{_fmt(xlo)}" y1="{_fmt(y0)}" x2="{_fmt(xlo)}" y2="{_fmt(y1)}" stroke="{bp.color}" stroke-width="1"/>')
            parts.append(f'<line x1="{_fmt(xhi)}" y1="{_fmt(y0)}" x2="{_fmt(xhi)}" y2="{_fmt(y1)}" stroke="{bp.color}" stroke-width="1"/>')
            for fx in s["fliers"]:
                parts.append(f'<circle cx="{_fmt(tr.x(fx))}" cy="{_fmt(yc)}" r="{_fmt(r)}" fill="none" stroke="{bp.color}"/>')
    # Every element here is stroke-only, so one wrapping group's stroke-opacity
    # covers the whole box-and-whiskers at once rather than repeating it per line.
    if bp.alpha < 1:
        body.append(f'<g stroke-opacity="{bp.alpha}">{"".join(parts)}</g>')
    else:
        body.append("".join(parts))


def _render_violin(v: Violin, tr, body):
    vert = v.orientation == "vertical"
    parts = []
    for pos, grid, hw in zip(v.positions, v.grids, v.halfwidths):
        if vert:
            left = np.column_stack([tr.x(pos - hw), tr.y(grid)])
            right = np.column_stack([tr.x(pos + hw)[::-1], tr.y(grid)[::-1]])
        else:
            left = np.column_stack([tr.x(grid), tr.y(pos - hw)])
            right = np.column_stack([tr.x(grid)[::-1], tr.y(pos + hw)[::-1]])
        pts = np.vstack([left, right])
        coords = [f"{_fmt(px)},{_fmt(py)}" for px, py in pts]
        d = "M" + coords[0] + "".join("L" + c for c in coords[1:]) + "Z"
        parts.append(f'<path d="{d}" fill="{v.color}" fill-opacity="{v.alpha}" '
                     f'stroke="{v.color}" stroke-width="1"/>')
    body.append("".join(parts))


def _render_eventplot(ev: EventPlot, tr, body):
    horiz = ev.orientation == "horizontal"
    half = ev.linelength / 2.0
    lines = []
    for row, off in zip(ev.rows, ev.offsets):
        if horiz:
            y0, y1 = tr.y(off - half), tr.y(off + half)
            for e in row:
                x = tr.x(e)
                lines.append(f'<line x1="{_fmt(x)}" y1="{_fmt(y0)}" x2="{_fmt(x)}" y2="{_fmt(y1)}"/>')
        else:
            x0, x1 = tr.x(off - half), tr.x(off + half)
            for e in row:
                y = tr.y(e)
                lines.append(f'<line x1="{_fmt(x0)}" y1="{_fmt(y)}" x2="{_fmt(x1)}" y2="{_fmt(y)}"/>')
    op = f' stroke-opacity="{ev.alpha}"' if ev.alpha < 1 else ""
    body.append(f'<g stroke="{ev.color}" stroke-width="1.2"{op}>{"".join(lines)}</g>')


def _render_quiver(q: Quiver, tr, body):
    tx, ty = q.tips()
    x0, y0 = tr.x(q.X), tr.y(q.Y)
    x1, y1 = tr.x(tx), tr.y(ty)
    hl = 5.0  # arrowhead length in px
    parts = []
    for bx, by, ex, ey in zip(x0, y0, x1, y1):
        ang = math.atan2(ey - by, ex - bx)
        h1 = (ex - hl * math.cos(ang - math.radians(25)),
              ey - hl * math.sin(ang - math.radians(25)))
        h2 = (ex - hl * math.cos(ang + math.radians(25)),
              ey - hl * math.sin(ang + math.radians(25)))
        parts.append(f'<path d="M{_fmt(bx)},{_fmt(by)} L{_fmt(ex)},{_fmt(ey)} '
                     f'M{_fmt(ex)},{_fmt(ey)} L{_fmt(h1[0])},{_fmt(h1[1])} '
                     f'M{_fmt(ex)},{_fmt(ey)} L{_fmt(h2[0])},{_fmt(h2[1])}"/>')
    op = f' stroke-opacity="{q.alpha}"' if q.alpha < 1 else ""
    body.append(f'<g fill="none" stroke="{q.color}" stroke-width="1.2" '
                f'stroke-linecap="round"{op}>{"".join(parts)}</g>')


def _barb_geometry(cx, cy, angle, speed, L):
    """One wind barb's pixel-space geometry: ``(lines, polygons, calm)``.

    ``lines`` is ``[(x0, y0, x1, y1), ...]`` -- the shaft plus its full/half
    ticks; ``polygons`` is ``[[(x, y), ...], ...]`` -- its 50-unit pennant
    triangles. ``speed`` rounds to the nearest 5 first, then decomposes into
    a pennant per 50, a full tick per 10, and a half tick for a remaining 5
    -- the usual meteorological convention. ``calm`` is true when that rounds
    to 0 (matplotlib draws a bare circle there instead of an empty shaft).
    ``angle`` is the shaft direction in screen-space radians (``atan2``
    convention); the barb is built shaft-along-+x in a local frame, ticks on
    the local +y side, then rotated by ``angle`` and placed at ``(cx, cy)``.
    """
    speed5 = round(speed / 5.0) * 5.0
    if speed5 <= 0:
        return [], [], True
    n_pennant = int(speed5 // 50)
    rem = speed5 - n_pennant * 50
    n_full = int(rem // 10)
    half = (rem - n_full * 10) >= 5

    spacing = 0.16 * L
    tick_len = 0.38 * L
    ca, sa = math.cos(math.radians(60)), math.sin(math.radians(60))

    local_lines = [(0.0, 0.0, L, 0.0)]   # the shaft itself
    local_polys = []
    pos = L
    for _ in range(n_pennant):
        local_polys.append([(pos, 0.0), (pos - spacing, 0.0),
                            (pos - spacing / 2.0, tick_len)])
        pos -= spacing
    for _ in range(n_full):
        local_lines.append((pos, 0.0, pos - tick_len * ca, tick_len * sa))
        pos -= spacing
    if half:
        local_lines.append((pos, 0.0, pos - (tick_len / 2) * ca, (tick_len / 2) * sa))

    def rot(x, y):
        return (cx + x * math.cos(angle) - y * math.sin(angle),
                cy + x * math.sin(angle) + y * math.cos(angle))

    lines = [(*rot(x0, y0), *rot(x1, y1)) for x0, y0, x1, y1 in local_lines]
    polygons = [[rot(px, py) for px, py in poly] for poly in local_polys]
    return lines, polygons, False


def _barb_angles(b, tr):
    """Screen-space direction (radians, ``atan2`` convention) for every barb
    in ``b`` -- transforms a unit step in ``(U, V)``'s own data-space
    direction through ``tr``, the same way :func:`_render_quiver` derives its
    arrow angle, so an unequal x/y data scale (or a non-1:1 ``set_aspect``)
    still points each barb where it visually should, not where a raw
    ``atan2(V, U)`` on the untransformed data would."""
    mag = np.hypot(b.U, b.V)
    mag_safe = np.where(mag == 0, 1.0, mag)
    ux, uy = b.U / mag_safe, b.V / mag_safe
    x0, y0 = tr.x(b.X), tr.y(b.Y)
    x1, y1 = tr.x(b.X + ux), tr.y(b.Y + uy)
    return mag, np.arctan2(y1 - y0, x1 - x0)


def _render_barbs(b: Barbs, tr, st, body):
    L = b.length * st.dpi / 72.0   # points -> px, same conversion markers use
    cx, cy = tr.x(b.X), tr.y(b.Y)
    mag, ang = _barb_angles(b, tr)
    op = f' stroke-opacity="{b.alpha}"' if b.alpha < 1 else ""
    fop = f' fill-opacity="{b.alpha}"' if b.alpha < 1 else ""
    lines, polys = [], []
    calm_pts = []
    r = 0.12 * L
    for x, y, spd, a in zip(cx, cy, mag, ang):
        ls, ps, calm = _barb_geometry(float(x), float(y), float(a), float(spd), L)
        if calm:
            calm_pts.append((x, y))
        else:
            lines.extend(ls)
            polys.extend(ps)
    parts = []
    if lines:
        d = "".join(f"M{_fmt(x0)},{_fmt(y0)}L{_fmt(x1)},{_fmt(y1)}" for x0, y0, x1, y1 in lines)
        parts.append(f'<path d="{d}" fill="none" stroke="{b.color}" '
                     f'stroke-width="1.2" stroke-linecap="round"{op}/>')
    for poly in polys:
        coords = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in poly)
        parts.append(f'<polygon points="{coords}" fill="{b.color}"{fop}/>')
    for x, y in calm_pts:
        parts.append(f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{_fmt(r)}" '
                     f'fill="none" stroke="{b.color}" stroke-width="1.2"{op}/>')
    body.append("".join(parts))


def _render_contour(ct: Contour, tr, body):
    op = f' stroke-opacity="{ct.alpha}"' if ct.alpha < 1 else ""
    for lvl, color, lw, ls, segs in ct.line_segments:
        if not segs:
            continue
        d = "".join(
            f"M{_fmt(tr.x(a))},{_fmt(tr.y(b))}L{_fmt(tr.x(c))},{_fmt(tr.y(e))}"
            for a, b, c, e in segs
        )
        dash = _DASH.get(ls)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        body.append(
            f'<path d="{d}" fill="none" stroke="{color}" '
            f'stroke-width="{_fmt(lw)}"{dash_attr}{op}/>'
        )
