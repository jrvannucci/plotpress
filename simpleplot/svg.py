"""SVG serialization: turn a Figure's scene into an SVG document string.

This is the whole rendering pipeline for Phase 0, in pure Python + NumPy:
transforms are vectorized, each series becomes a single ``<path>`` (not one node
per point), and each ``pcolormesh`` becomes one embedded ``<image>``. The hot
paths here (coordinate formatting, per-axes fragment assembly) are exactly what a
Phase 2 Rust backend would take over.
"""

from __future__ import annotations

import math

import numpy as np

from .artists import (
    Annotation, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, HLine, Image, Line2D, LineCollection, Pie, PolyCollection,
    Polygon, QuadMesh, Quiver, ScatterCollection, Span, Stem, Text, Violin,
    VLine,
)
from .fonts import text_width
from .png import png_data_uri
from .ticker import format_ticks, log_ticks, nice_ticks
from .transform import LinearTransform

_DASH = {"-": None, "--": "6,4", ":": "1,3", "-.": "6,3,1,3"}


def _fmt(v: float) -> str:
    """Compact fixed-precision coordinate (2 dp), trimming trailing zeros."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _esc(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def figure_to_svg(fig, interactive: bool = False) -> str:
    dpi = fig.style.dpi
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi

    defs: list[str] = []
    body: list[str] = []

    for i, ax in enumerate(fig.axes):
        _render_axes(ax, fig, W, H, i, defs, body)

    _render_figtexts(fig, W, H, body)

    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{_fmt(W)}" height="{_fmt(H)}" '
        f'viewBox="0 0 {_fmt(W)} {_fmt(H)}" '
        f'font-family="{fig.style.font_family}">'
    )
    bg = f'<rect x="0" y="0" width="{_fmt(W)}" height="{_fmt(H)}" fill="{fig.style.facecolor}"/>'
    defs_block = f"<defs>{''.join(defs)}</defs>" if defs else ""
    return header + defs_block + bg + "".join(body) + "</svg>"


def _pixel_rect(ax, W, H):
    left, bottom, w, h = ax._rect
    return (left * W, (1.0 - (bottom + h)) * H, w * W, h * H)


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


def axes_metadata(fig):
    """Per-axes pixel rect + data limits, for client-side point picking.

    Keyed by the axes index (matching the ``s<index>_<k>`` ids on rendered
    series). Colorbar axes are excluded -- they are not data plots.
    """
    dpi = fig.style.dpi
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi
    meta = {}
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar:
            continue
        (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
        px_left, px_top, px_w, px_h = _effective_rect(
            ax, *_pixel_rect(ax, W, H), (xmin, xmax), (ymin, ymax))
        meta[i] = {
            "x": round(px_left, 3), "y": round(px_top, 3),
            "w": round(px_w, 3), "h": round(px_h, 3),
            "xmin": round(float(xmin), 6), "xmax": round(float(xmax), 6),
            "ymin": round(float(ymin), 6), "ymax": round(float(ymax), 6),
            "grid": bool(ax._grid), "axis_off": bool(ax._axis_off),
            "xscale": ax._xscale, "yscale": ax._yscale,
            # Whether ticks are user-fixed (don't auto-recompute on zoom).
            "xfixed": ax._xticks is not None, "yfixed": ax._yticks is not None,
        }
    return meta


def style_payload(fig):
    """Style constants the client tick-rebuilder needs during per-axes zoom."""
    st = fig.style
    return {
        "spine": st.spine_color, "spine_width": st.spine_width,
        "grid_color": st.grid_color, "grid_width": st.grid_width,
        "grid_alpha": st.grid_alpha, "tick_size": st.tick_size,
        "tick_width": st.tick_width, "tick_label_size": st.tick_label_size,
        "text": st.text_color,
    }


def _rl(a, nd=6):
    """Flatten to a rounded Python-float list (vectorized: NumPy does the work).

    Much faster than a per-element ``round(float(v), nd)`` comprehension on the
    large arrays embedded for point picking (e.g. mesh z grids).
    """
    return np.round(np.asarray(a, dtype=float).ravel(), nd).tolist()


def _round_list(a):
    return _rl(a, 6)


def pick_data(fig, max_points=20000, max_mesh_cells=60000, precision=6):
    """Per-axes data payload for point picking (values incl. z and beyond).

    For point series (line/scatter) embeds x, y and any extra named dimensions
    (``pick_values`` such as ``c`` or ``z``). For meshes embeds the z grid so a
    clicked cell reports its value. Series/meshes exceeding the size caps are
    omitted (picking falls back to a geometry-based x/y readout for those), so
    the HTML stays lean.

    ``precision`` sets the decimal places the embedded arrays are rounded to.
    Lower values shrink the payload (the mesh z grids dominate it); 6 keeps
    full readout fidelity.
    """
    # Local shadow so every _round_list(...) call below honors `precision`
    # without threading it through ~20 call sites.
    def _round_list(a):
        return _rl(a, precision)

    data = {}
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar:
            continue
        series, meshes, pies = [], [], []
        for art in ax.artists:
            if isinstance(art, (Line2D, ScatterCollection)):
                if art.x.size == 0 or art.x.size > max_points:
                    continue
                vals = {k: _round_list(v) for k, v in art.pick_values.items()
                        if np.asarray(v).size == art.x.size}
                series.append({
                    "kind": "scatter" if isinstance(art, ScatterCollection) else "line",
                    "x": _round_list(art.x), "y": _round_list(art.y),
                    "vals": vals,
                })
            elif isinstance(art, Stem):
                series.append({"kind": "stem", "x": _round_list(art.x),
                               "y": _round_list(art.y), "vals": {}})
            elif isinstance(art, ErrorBar):
                vals = {}
                if art.yerr is not None:
                    vals["yerr"] = _round_list(art.yerr)
                if art.xerr is not None:
                    vals["xerr"] = _round_list(art.xerr)
                series.append({"kind": "errorbar", "x": _round_list(art.x),
                               "y": _round_list(art.y), "vals": vals})
            elif isinstance(art, Bars):
                if art.orientation == "vertical":
                    xs, ys = art.pos, art.base + art.length
                else:
                    xs, ys = art.base + art.length, art.pos
                series.append({"kind": "bar", "x": _round_list(xs),
                               "y": _round_list(ys),
                               "vals": {"value": _round_list(art.length)}})
            elif isinstance(art, Quiver):
                series.append({"kind": "quiver", "x": _round_list(art.X),
                               "y": _round_list(art.Y),
                               "vals": {"u": _round_list(art.U),
                                        "v": _round_list(art.V),
                                        "mag": _round_list(np.hypot(art.U, art.V))}})
            elif isinstance(art, EventPlot):
                xs, ys = [], []
                for row, off in zip(art.rows, art.offsets):
                    xs.extend(row.tolist())
                    ys.extend([float(off)] * row.size)
                if art.orientation != "horizontal":
                    xs, ys = ys, xs
                if 0 < len(xs) <= max_points:
                    series.append({"kind": "event", "x": [round(v, 6) for v in xs],
                                   "y": [round(v, 6) for v in ys], "vals": {}})
            elif isinstance(art, BoxPlot):
                # One pickable point per box at its median, carrying all stats.
                xs, ys = [], []
                q1s, q3s, los, his = [], [], [], []
                for pos, s in zip(art.positions, art.stats):
                    if art.orientation == "vertical":
                        xs.append(float(pos)); ys.append(float(s["med"]))
                    else:
                        xs.append(float(s["med"])); ys.append(float(pos))
                    q1s.append(round(float(s["q1"]), 6)); q3s.append(round(float(s["q3"]), 6))
                    los.append(round(float(s["lo"]), 6)); his.append(round(float(s["hi"]), 6))
                series.append({"kind": "box", "x": [round(v, 6) for v in xs],
                               "y": [round(v, 6) for v in ys],
                               "vals": {"q1": q1s, "q3": q3s,
                                        "whislo": los, "whishi": his}})
            elif isinstance(art, Violin):
                # Centerline points per violin (value + normalized width).
                for pos, grid, hw in zip(art.positions, art.grids, art.halfwidths):
                    if grid.size == 0 or grid.size > max_points:
                        continue
                    if art.orientation == "vertical":
                        vx = [round(float(pos), 6)] * grid.size
                        vy = _round_list(grid)
                    else:
                        vx = _round_list(grid)
                        vy = [round(float(pos), 6)] * grid.size
                    series.append({"kind": "violin", "x": vx, "y": vy,
                                   "vals": {"width": _round_list(hw * 2.0)}})
            elif isinstance(art, Contour):
                # Pick like a pcolormesh: report the field value z at the grid
                # cell under the cursor (arrow keys step cell-by-cell).
                ny, nx = art.Z.shape
                if ny * nx <= max_mesh_cells:
                    meshes.append({
                        "extent": [round(float(art.x.min()), 6),
                                   round(float(art.x.max()), 6),
                                   round(float(art.y.min()), 6),
                                   round(float(art.y.max()), 6)],
                        "shape": [int(ny), int(nx)],
                        "z": _round_list(art.Z),  # row 0 = ymin, like QuadMesh
                        "name": "z",
                    })
            elif isinstance(art, FillBetween):
                if 0 < art.x.size <= max_points:
                    hi = np.maximum(art.y1, art.y2)
                    lo = np.minimum(art.y1, art.y2)
                    series.append({"kind": "fill", "x": _round_list(art.x),
                                   "y": _round_list(hi),           # snap to band top
                                   "vals": {"lower": _round_list(lo)}})
            elif isinstance(art, (QuadMesh, Image)):
                is_img = isinstance(art, Image)
                if is_img and art.A.ndim != 2:
                    continue  # RGB image: no scalar to report
                grid = art.A if is_img else art.C
                ny, nx = grid.shape
                if ny * nx > max_mesh_cells:
                    continue
                xmin, xmax, ymin, ymax = art.extent()
                # Store z row-major with row 0 = ymin so a clicked cell maps back.
                z = np.flipud(grid) if (is_img and art.origin == "upper") else grid
                meshes.append({
                    "extent": [round(xmin, 6), round(xmax, 6),
                               round(ymin, 6), round(ymax, 6)],
                    "shape": [int(ny), int(nx)],
                    "z": _round_list(z),
                    "name": "z",
                })
            elif isinstance(art, Pie):
                pies.append({
                    "startangle": float(art.startangle),
                    "radius": float(art.radius),
                    "fracs": _round_list(art.fracs),
                    "values": _round_list(art.values),
                    "labels": list(art.labels) if art.labels is not None else None,
                })
        if series or meshes or pies:
            data[i] = {"series": series, "meshes": meshes, "pies": pies}
    return data


def _effective_rect(ax, px_left, px_top, px_w, px_h, xlim, ylim):
    """Shrink the drawn box to honor ``set_aspect`` (box-adjust), centered."""
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

    if ax._is_colorbar:
        _render_colorbar(ax, tr, *alloc, clip_id, body)
        return

    is_twin = ax._twin_of is not None
    # Axes background (twins overlay their parent, so they draw none).
    if not is_twin:
        body.append(
            f'<rect x="{_fmt(px_left)}" y="{_fmt(px_top)}" width="{_fmt(px_w)}" '
            f'height="{_fmt(px_h)}" fill="{st.axes_facecolor}"/>'
        )

    xticks = (ax._xticks if ax._xticks is not None else
              (log_ticks(xmin, xmax) if ax._xscale == "log" else nice_ticks(xmin, xmax)))
    yticks = (ax._yticks if ax._yticks is not None else
              (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))

    # Grid + ticks live in one group so client-side per-axes zoom can rebuild
    # them from new limits (see _interactive.py).
    body.append(f'<g id="ticks{index}">')
    if ax._grid and not ax._axis_off and not is_twin:
        _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body)
    if not ax._axis_off:
        if is_twin:
            _render_twin_ticks(ax, st, tr, xticks, yticks,
                               px_left, px_top, px_w, px_h, body)
        else:
            xlabels = _resolve_tick_labels(ax._xticklabels, xticks)
            ylabels = _resolve_tick_labels(ax._yticklabels, yticks)
            _render_ticks(st, tr, xticks, yticks, xlabels, ylabels,
                          px_left, px_top, px_w, px_h, body)
    body.append("</g>")

    # Artists: fixed clip to the axes rect, then a transformable zoom group that
    # per-axes data zoom remaps via one affine (old limits -> new limits).
    body.append(f'<g clip-path="url(#{clip_id})"><g id="zoom{index}" class="simpleplot-zoom">')
    for k, artist in enumerate(ax.artists):
        if isinstance(artist, Line2D):
            _render_line(artist, tr, index, k, body)
        elif isinstance(artist, ScatterCollection):
            _render_scatter(artist, tr, st, fig, index, k, body)
        elif isinstance(artist, (QuadMesh, Image)):
            _render_mesh(artist, tr, body)
        elif isinstance(artist, VLine):
            _render_vline(artist, tr, body)
        elif isinstance(artist, HLine):
            _render_hline(artist, tr, body)
        elif isinstance(artist, Span):
            _render_span(artist, tr, body)
        elif isinstance(artist, FrameLine2D):
            _render_frameline(artist, tr, index, k, body)
        elif isinstance(artist, Bars):
            _render_bars(artist, tr, index, k, body)
        elif isinstance(artist, FillBetween):
            _render_fill(artist, tr, index, k, body)
        elif isinstance(artist, Polygon):
            _render_polygon(artist, tr, index, k, body)
        elif isinstance(artist, PolyCollection):
            _render_polycollection(artist, tr, body)
        elif isinstance(artist, LineCollection):
            _render_linecollection(artist, tr, body)
        elif isinstance(artist, Stem):
            _render_stem(artist, tr, st, fig, body)
        elif isinstance(artist, ErrorBar):
            _render_errorbar(artist, tr, st, fig, body)
        elif isinstance(artist, Pie):
            _render_pie(artist, tr, body)
        elif isinstance(artist, BoxPlot):
            _render_boxplot(artist, tr, st, body)
        elif isinstance(artist, Violin):
            _render_violin(artist, tr, body)
        elif isinstance(artist, EventPlot):
            _render_eventplot(artist, tr, body)
        elif isinstance(artist, Quiver):
            _render_quiver(artist, tr, body)
        elif isinstance(artist, Contour):
            _render_contour(artist, tr, body)
        elif isinstance(artist, Text):
            _render_text(artist, tr, body)
        elif isinstance(artist, Annotation):
            _render_annotation(artist, tr, body)
    body.append("</g></g>")   # close zoom group + clip group

    if not ax._axis_off and not is_twin:
        _render_spines(st, px_left, px_top, px_w, px_h, body)
    if not is_twin:
        _render_labels(ax, st, px_left, px_top, px_w, px_h, body)

    if ax._show_legend:
        _render_legend(ax, st, px_left, px_top, px_w, px_h, body)


# -- artists ---------------------------------------------------------------
def _seg_to_path(seg: np.ndarray) -> str:
    """Serialize one contiguous run of points to ``M x,y L x,y ...``.

    Uses vectorized ``numpy.char`` formatting instead of per-point Python
    f-strings -- this is the hot path for large series (and the boundary a
    Rust backend would take over in Phase 2).
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


def _render_line(line: Line2D, tr, ai, k, body):
    pts = tr.xy(line.x, line.y)
    d = _line_path_d(pts)
    if not d:
        return
    dash = _DASH.get(line.linestyle)
    attrs = (
        f'fill="none" stroke="{line.color}" stroke-width="{line.linewidth}" '
        f'stroke-linejoin="round" stroke-linecap="round"'
    )
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    if line.alpha < 1:
        attrs += f' stroke-opacity="{line.alpha}"'
    label = _esc(line.label) if line.label else ""
    body.append(
        f'<path class="simpleplot-series" id="s{ai}_{k}" data-label="{label}" '
        f'd="{d}" {attrs}/>'
    )


def _render_frameline(art: FrameLine2D, tr, ai, k, body):
    """Render frame 0 statically; the slider JS rewrites ``d`` for other frames."""
    x0, y0 = art.frame_xy(0)
    d = _line_path_d(tr.xy(x0, y0))
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
        f'<path class="simpleplot-series simpleplot-frameline" id="s{ai}_{k}" '
        f'data-label="{label}" d="{d}" {attrs}/>'
    )


def frame_data(fig):
    """Per-axes slider-frame data: all frames' x/Y for JS to redraw on scrub."""
    frames = {}
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar:
            continue
        entries = []
        for k, art in enumerate(ax.artists):
            if not isinstance(art, FrameLine2D):
                continue
            shared = art.X.ndim == 1
            entry = {"id": f"s{i}_{k}", "unit": art.slider_unit,
                     "shared_x": bool(shared)}
            if shared:
                entry["x"] = _round_list(art.X)
            else:
                entry["x"] = [_round_list(art.X[f]) for f in range(art.n_frames)]
            entry["Y"] = [_round_list(art.Y[f]) for f in range(art.n_frames)]
            entries.append(entry)
        if entries:
            frames[i] = entries
    return frames


def _render_scatter(coll: ScatterCollection, tr, st, fig, ai, k, body):
    xp = tr.x(coll.x)
    yp = tr.y(coll.y)
    pt_to_px = st.dpi / 72.0
    diam = np.broadcast_to(np.asarray(coll.s, dtype=float), xp.shape) * pt_to_px
    colors = coll.face_colors()          # per-point when a `c` array is set
    finite = np.isfinite(xp) & np.isfinite(yp)
    op = f' stroke-opacity="{coll.alpha}"' if coll.alpha < 1 else ""
    label = _esc(coll.label) if coll.label else ""

    # Markers are zero-length, round-capped strokes: with non-scaling-stroke
    # (applied inside the zoom group) they stay a constant pixel size -- and
    # circular -- under per-axes zoom, unlike a scaled <circle>.
    def dot(cx, cy):
        return f"M{_fmt(cx)},{_fmt(cy)}L{_fmt(cx)},{_fmt(cy)}"

    parts = []
    same_size = diam.size and float(np.ptp(diam)) < 1e-9
    if colors is None and same_size:
        # One path for every point of the single color / size (fewest nodes).
        d = "".join(dot(cx, cy) for cx, cy, ok in zip(xp, yp, finite) if ok)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{coll.color}" '
            f'stroke-width="{_fmt(float(diam[0]) if diam.size else 0)}" '
            f'stroke-linecap="round"/>'
        )
    else:
        cols = colors if colors is not None else [coll.color] * len(xp)
        for cx, cy, dm, col, ok in zip(xp, yp, diam, cols, finite):
            if ok:
                parts.append(
                    f'<path d="{dot(cx, cy)}" fill="none" stroke="{col}" '
                    f'stroke-width="{_fmt(dm)}" stroke-linecap="round"/>'
                )
    body.append(
        f'<g class="simpleplot-series" id="s{ai}_{k}" data-label="{label}"{op}>'
        f'{"".join(parts)}</g>'
    )


def _render_vline(vl: VLine, tr, body):
    x = float(tr.x(vl.x))
    y1, y2 = tr.px_top, tr.px_top + tr.px_h
    dash = _DASH.get(vl.linestyle)
    attrs = f'stroke="{vl.color}" stroke-width="{vl.linewidth}"'
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    if vl.alpha < 1:
        attrs += f' stroke-opacity="{vl.alpha}"'
    label = _esc(vl.label) if vl.label else ""
    body.append(
        f'<line class="simpleplot-series" data-label="{label}" x1="{_fmt(x)}" '
        f'y1="{_fmt(y1)}" x2="{_fmt(x)}" y2="{_fmt(y2)}" {attrs}/>'
    )


def _render_hline(hl, tr, body):
    y = float(tr.y(hl.y))
    x1, x2 = tr.px_left, tr.px_left + tr.px_w
    dash = _DASH.get(hl.linestyle)
    attrs = f'stroke="{hl.color}" stroke-width="{hl.linewidth}"'
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    if hl.alpha < 1:
        attrs += f' stroke-opacity="{hl.alpha}"'
    label = _esc(hl.label) if hl.label else ""
    body.append(
        f'<line class="simpleplot-series" data-label="{label}" x1="{_fmt(x1)}" '
        f'y1="{_fmt(y)}" x2="{_fmt(x2)}" y2="{_fmt(y)}" {attrs}/>'
    )


def _render_span(sp, tr, body):
    if sp.orientation == "vertical":       # axvspan: x band, full height
        a, b = float(tr.x(sp.lo)), float(tr.x(sp.hi))
        x, w = min(a, b), abs(b - a)
        y, h = tr.px_top, tr.px_h
    else:                                  # axhspan: y band, full width
        a, b = float(tr.y(sp.lo)), float(tr.y(sp.hi))
        y, h = min(a, b), abs(b - a)
        x, w = tr.px_left, tr.px_w
    label = _esc(sp.label) if sp.label else ""
    body.append(
        f'<rect class="simpleplot-series" data-label="{label}" x="{_fmt(x)}" '
        f'y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" fill="{sp.color}" '
        f'fill-opacity="{sp.alpha}"/>'
    )


def _render_mesh(mesh: QuadMesh, tr, body):
    uri = png_data_uri(mesh.rgba())
    xmin, xmax, ymin, ymax = mesh.extent()
    ix = tr.x(xmin)
    iy = tr.y(ymax)
    iw = tr.x(xmax) - ix
    ih = tr.y(ymin) - iy
    body.append(
        f'<image x="{_fmt(ix)}" y="{_fmt(iy)}" width="{_fmt(iw)}" '
        f'height="{_fmt(ih)}" preserveAspectRatio="none" '
        f'style="image-rendering:pixelated" href="{uri}"/>'
    )


def _render_bars(bars: Bars, tr, ai, k, body):
    label = _esc(bars.label) if bars.label else ""
    op = f' fill-opacity="{bars.alpha}"' if bars.alpha < 1 else ""
    edge = (f' stroke="{bars.edgecolor}" stroke-width="{bars.linewidth}"'
            if bars.edgecolor else "")
    rects = []
    for i in range(len(bars.pos)):
        p, ln, th, ba = bars.pos[i], bars.length[i], bars.thickness[i], bars.base[i]
        if bars.orientation == "vertical":
            x0, x1 = tr.x(p - th / 2), tr.x(p + th / 2)
            y0, y1 = tr.y(ba), tr.y(ba + ln)
        else:
            y0, y1 = tr.y(p - th / 2), tr.y(p + th / 2)
            x0, x1 = tr.x(ba), tr.x(ba + ln)
        rx, ry = min(x0, x1), min(y0, y1)
        rects.append(
            f'<rect x="{_fmt(rx)}" y="{_fmt(ry)}" width="{_fmt(abs(x1 - x0))}" '
            f'height="{_fmt(abs(y1 - y0))}" fill="{bars.colors[i]}"{edge}/>'
        )
    body.append(
        f'<g class="simpleplot-series" id="s{ai}_{k}" data-label="{label}"{op}>'
        f'{"".join(rects)}</g>'
    )


def _render_fill(fb: FillBetween, tr, ai, k, body):
    top = tr.xy(fb.x, fb.y1)
    bot = tr.xy(fb.x[::-1], fb.y2[::-1])
    pts = np.vstack([top, bot])
    coords = [f"{_fmt(x)},{_fmt(y)}" for x, y in pts]
    d = "M" + coords[0] + "".join("L" + c for c in coords[1:]) + "Z"
    label = _esc(fb.label) if fb.label else ""
    body.append(
        f'<path class="simpleplot-series" id="s{ai}_{k}" data-label="{label}" '
        f'd="{d}" fill="{fb.color}" fill-opacity="{fb.alpha}" stroke="none"/>'
    )


def _render_polygon(poly: Polygon, tr, ai, k, body):
    pts = tr.xy(poly.x, poly.y)
    coords = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts if np.isfinite([x, y]).all())
    label = _esc(poly.label) if poly.label else ""
    stroke = (f'stroke="{poly.edgecolor}" stroke-width="{poly.linewidth}"'
              if poly.edgecolor else 'stroke="none"')
    body.append(
        f'<polygon class="simpleplot-series" id="s{ai}_{k}" data-label="{label}" '
        f'points="{coords}" fill="{poly.color}" fill-opacity="{poly.alpha}" {stroke}/>'
    )


def _to_hex_color(c):
    if isinstance(c, str):
        return c
    return "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))


def _render_polycollection(pc: PolyCollection, tr, body):
    edge = f'stroke="{pc.edgecolor}"' if pc.edgecolor else 'stroke="none"'
    op = f' fill-opacity="{pc.alpha}"' if pc.alpha < 1 else ""
    parts = [f'<g class="simpleplot-series" {edge} stroke-width="0.4">']
    for verts, fc in zip(pc.verts, pc.facecolors):
        pts = tr.xy(verts[:, 0], verts[:, 1])
        coords = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts)
        parts.append(f'<polygon points="{coords}" fill="{_to_hex_color(fc)}"{op}/>')
    parts.append("</g>")
    body.append("".join(parts))


def _render_linecollection(lc: LineCollection, tr, body):
    dash = _DASH.get(lc.linestyle)
    lines = []
    for x0, y0, x1, y1 in lc.segments:
        lines.append(
            f'<line x1="{_fmt(tr.x(x0))}" y1="{_fmt(tr.y(y0))}" '
            f'x2="{_fmt(tr.x(x1))}" y2="{_fmt(tr.y(y1))}"/>'
        )
    attrs = f'stroke="{lc.color}" stroke-width="{lc.linewidth}"'
    if dash:
        attrs += f' stroke-dasharray="{dash}"'
    if lc.alpha < 1:
        attrs += f' stroke-opacity="{lc.alpha}"'
    label = _esc(lc.label) if lc.label else ""
    body.append(
        f'<g class="simpleplot-series" data-label="{label}" {attrs}>'
        f'{"".join(lines)}</g>'
    )


def _render_stem(stem: Stem, tr, st, fig, body):
    xb = tr.x(stem.x)
    yb = tr.y(stem.y)
    y0 = tr.y(stem.baseline)
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
    bars, cap = [], eb.capsize
    if eb.yerr is not None:
        ylo, yhi = tr.y(eb.y - eb.yerr), tr.y(eb.y + eb.yerr)
        for x, a, b in zip(xb, ylo, yhi):
            bars.append(f'<line x1="{_fmt(x)}" y1="{_fmt(a)}" x2="{_fmt(x)}" y2="{_fmt(b)}"/>')
            bars.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(a)}" x2="{_fmt(x + cap)}" y2="{_fmt(a)}"/>')
            bars.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(b)}" x2="{_fmt(x + cap)}" y2="{_fmt(b)}"/>')
    if eb.xerr is not None:
        xlo, xhi = tr.x(eb.x - eb.xerr), tr.x(eb.x + eb.xerr)
        for y, a, b in zip(yb, xlo, xhi):
            bars.append(f'<line x1="{_fmt(a)}" y1="{_fmt(y)}" x2="{_fmt(b)}" y2="{_fmt(y)}"/>')
            bars.append(f'<line x1="{_fmt(a)}" y1="{_fmt(y - cap)}" x2="{_fmt(a)}" y2="{_fmt(y + cap)}"/>')
            bars.append(f'<line x1="{_fmt(b)}" y1="{_fmt(y - cap)}" x2="{_fmt(b)}" y2="{_fmt(y + cap)}"/>')
    if bars:
        body.append(f'<g stroke="{eb.color}" stroke-width="1">{"".join(bars)}</g>')
    r = eb.markersize / 2.0 * st.dpi / 72.0
    dots = [f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{_fmt(r)}" fill="{eb.color}"/>'
            for x, y in zip(xb, yb)]
    body.append("".join(dots))


def _render_pie(pie: Pie, tr, body):
    """Draw wedges in axes-pixel space so the pie stays circular."""
    cx = tr.px_left + tr.px_w / 2.0
    cy = tr.px_top + tr.px_h / 2.0
    R = 0.42 * min(tr.px_w, tr.px_h) * pie.radius
    ang = math.radians(pie.startangle)
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
            f'fill="{pie.colors[i]}" stroke="#ffffff" stroke-width="1.5"/>'
        )
        if pie.labels is not None:
            am = (a0 + a1) / 2.0
            lx, ly = cx + 1.15 * R * math.cos(am), cy - 1.15 * R * math.sin(am)
            anchor = "start" if math.cos(am) >= 0 else "end"
            labels.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(ly)}" text-anchor="{anchor}" '
                f'font-size="10" dominant-baseline="middle">{_esc(pie.labels[i])}</text>'
            )
        ang = a1
    body.append("".join(parts) + "".join(labels))


_HA = {"left": "start", "center": "middle", "right": "end"}
_VA = {"baseline": "alphabetic", "bottom": "text-after-edge",
       "center": "central", "top": "hanging"}


def _text_svg(x, y, text, color, size, ha, va, rotation=0.0):
    anchor = _HA.get(ha, "start")
    baseline = _VA.get(va, "alphabetic")
    rot = (f' transform="rotate({_fmt(-rotation)} {_fmt(x)} {_fmt(y)})"'
           if rotation else "")
    return (f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="{anchor}" '
            f'dominant-baseline="{baseline}" font-size="{size}" '
            f'fill="{color}"{rot}>{_esc(text)}</text>')


def _render_text(t: Text, tr, body):
    body.append(_text_svg(float(tr.x(t.x)), float(tr.y(t.y)), t.text, t.color,
                          t.size, t.ha, t.va, t.rotation))


def _render_annotation(an: Annotation, tr, body):
    tx, ty = float(tr.x(an.xytext[0])), float(tr.y(an.xytext[1]))
    if an.arrowprops is not None:
        px, py = float(tr.x(an.xy[0])), float(tr.y(an.xy[1]))
        color = (an.arrowprops.get("color", an.color)
                 if isinstance(an.arrowprops, dict) else an.color)
        ang = math.atan2(py - ty, px - tx)
        hl = 7.0
        h1 = (px - hl * math.cos(ang - 0.4), py - hl * math.sin(ang - 0.4))
        h2 = (px - hl * math.cos(ang + 0.4), py - hl * math.sin(ang + 0.4))
        body.append(
            f'<path d="M{_fmt(tx)},{_fmt(ty)} L{_fmt(px)},{_fmt(py)} '
            f'M{_fmt(px)},{_fmt(py)} L{_fmt(h1[0])},{_fmt(h1[1])} '
            f'M{_fmt(px)},{_fmt(py)} L{_fmt(h2[0])},{_fmt(h2[1])}" '
            f'fill="none" stroke="{color}" stroke-width="1.2"/>'
        )
    body.append(_text_svg(tx, ty, an.text, an.color, an.size, an.ha, an.va))


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
        parts.append(f'<path d="{d}" fill="{v.color}" fill-opacity="0.55" '
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
    body.append(f'<g stroke="{ev.color}" stroke-width="1.2">{"".join(lines)}</g>')


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
    body.append(f'<g fill="none" stroke="{q.color}" stroke-width="1.2" '
                f'stroke-linecap="round">{"".join(parts)}</g>')


def _render_contour(ct: Contour, tr, body):
    for lvl, color, segs in ct.line_segments:
        if not segs:
            continue
        d = "".join(
            f"M{_fmt(tr.x(a))},{_fmt(tr.y(b))}L{_fmt(tr.x(c))},{_fmt(tr.y(e))}"
            for a, b, c, e in segs
        )
        body.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.2"/>')


# -- axes furniture --------------------------------------------------------
def _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body):
    lines = []
    for xt in xticks:
        x = tr.x(xt)
        lines.append(f'<line x1="{_fmt(x)}" y1="{_fmt(px_top)}" x2="{_fmt(x)}" y2="{_fmt(px_top + px_h)}"/>')
    for yt in yticks:
        y = tr.y(yt)
        lines.append(f'<line x1="{_fmt(px_left)}" y1="{_fmt(y)}" x2="{_fmt(px_left + px_w)}" y2="{_fmt(y)}"/>')
    body.append(
        f'<g stroke="{st.grid_color}" stroke-width="{st.grid_width}" '
        f'stroke-opacity="{st.grid_alpha}">{"".join(lines)}</g>'
    )


def _resolve_tick_labels(custom, ticks):
    """Explicit tick-label strings if set, else formatted tick values."""
    if custom is None:
        return format_ticks(ticks)
    labs = list(custom)[:len(ticks)]
    return labs + [""] * (len(ticks) - len(labs))


def _render_twin_ticks(ax, st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body):
    """Draw a twin overlay's independent axis on the side opposite the parent."""
    ts, tw, fs = st.tick_size, st.tick_width, st.tick_label_size
    marks, labels = [], []
    if ax._twin_shared == "x":                      # twinx: y-axis on the RIGHT
        xr = px_left + px_w
        for yt, lab in zip(yticks, _resolve_tick_labels(ax._yticklabels, yticks)):
            y = tr.y(yt)
            marks.append(f'<line x1="{_fmt(xr)}" y1="{_fmt(y)}" x2="{_fmt(xr + ts)}" y2="{_fmt(y)}"/>')
            labels.append(
                f'<text x="{_fmt(xr + ts + 2)}" y="{_fmt(y + fs * 0.35)}" '
                f'text-anchor="start" font-size="{fs}" fill="{st.text_color}">{_esc(lab)}</text>'
            )
        if ax._ylabel:
            lx = xr + ts + _max_ytick_width(ax, st) + st.label_size + 4
            cy = px_top + px_h / 2.0
            body.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(cy)}" text-anchor="middle" '
                f'font-size="{st.label_size}" fill="{st.text_color}" '
                f'transform="rotate(90 {_fmt(lx)} {_fmt(cy)})">{_esc(ax._ylabel)}</text>'
            )
    else:                                           # twiny: x-axis on the TOP
        for xt, lab in zip(xticks, _resolve_tick_labels(ax._xticklabels, xticks)):
            x = tr.x(xt)
            marks.append(f'<line x1="{_fmt(x)}" y1="{_fmt(px_top)}" x2="{_fmt(x)}" y2="{_fmt(px_top - ts)}"/>')
            labels.append(
                f'<text x="{_fmt(x)}" y="{_fmt(px_top - ts - 3)}" text-anchor="middle" '
                f'font-size="{fs}" fill="{st.text_color}">{_esc(lab)}</text>'
            )
        if ax._xlabel:
            body.append(
                f'<text x="{_fmt(px_left + px_w / 2)}" y="{_fmt(px_top - ts - fs - st.label_size)}" '
                f'text-anchor="middle" font-size="{st.label_size}" '
                f'fill="{st.text_color}">{_esc(ax._xlabel)}</text>'
            )
    body.append(f'<g stroke="{st.spine_color}" stroke-width="{tw}">{"".join(marks)}</g>')
    body.append("".join(labels))


def _render_ticks(st, tr, xticks, yticks, xlabels, ylabels,
                  px_left, px_top, px_w, px_h, body):
    ts, tw = st.tick_size, st.tick_width
    fs = st.tick_label_size
    marks, labels = [], []
    y_axis = px_top + px_h

    for xt, lab in zip(xticks, xlabels):
        x = tr.x(xt)
        marks.append(f'<line x1="{_fmt(x)}" y1="{_fmt(y_axis)}" x2="{_fmt(x)}" y2="{_fmt(y_axis + ts)}"/>')
        labels.append(
            f'<text x="{_fmt(x)}" y="{_fmt(y_axis + ts + fs)}" text-anchor="middle" '
            f'font-size="{fs}" fill="{st.text_color}">{_esc(lab)}</text>'
        )
    for yt, lab in zip(yticks, ylabels):
        y = tr.y(yt)
        marks.append(f'<line x1="{_fmt(px_left - ts)}" y1="{_fmt(y)}" x2="{_fmt(px_left)}" y2="{_fmt(y)}"/>')
        labels.append(
            f'<text x="{_fmt(px_left - ts - 2)}" y="{_fmt(y + fs * 0.35)}" text-anchor="end" '
            f'font-size="{fs}" fill="{st.text_color}">{_esc(lab)}</text>'
        )
    body.append(f'<g stroke="{st.spine_color}" stroke-width="{tw}">{"".join(marks)}</g>')
    body.append("".join(labels))


def _render_spines(st, px_left, px_top, px_w, px_h, body):
    body.append(
        f'<rect x="{_fmt(px_left)}" y="{_fmt(px_top)}" width="{_fmt(px_w)}" '
        f'height="{_fmt(px_h)}" fill="none" stroke="{st.spine_color}" '
        f'stroke-width="{st.spine_width}"/>'
    )


def _render_labels(ax, st, px_left, px_top, px_w, px_h, body):
    cx = px_left + px_w / 2.0
    if ax._xlabel and not ax._axis_off:
        y = px_top + px_h + st.tick_size + st.tick_label_size + st.label_size + 4
        body.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'font-size="{st.label_size}" fill="{st.text_color}">{_esc(ax._xlabel)}</text>'
        )
    if ax._ylabel and not ax._axis_off:
        # Push the rotated label left of the widest y tick label.
        x = px_left - st.tick_size - _max_ytick_width(ax, st) - st.label_size - 4
        cy = px_top + px_h / 2.0
        body.append(
            f'<text x="{_fmt(x)}" y="{_fmt(cy)}" text-anchor="middle" '
            f'font-size="{st.label_size}" fill="{st.text_color}" '
            f'transform="rotate(-90 {_fmt(x)} {_fmt(cy)})">{_esc(ax._ylabel)}</text>'
        )
    if ax._title:
        body.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(px_top - 8)}" text-anchor="middle" '
            f'font-size="{st.title_size}" fill="{st.text_color}">{_esc(ax._title)}</text>'
        )


def _max_ytick_width(ax, st):
    (_, _), (ymin, ymax) = ax._resolved_limits()
    labels = format_ticks(nice_ticks(ymin, ymax))
    return max((text_width(l, st.tick_label_size) for l in labels), default=0.0)


# loc name -> (fx, fy) fractions of the free space inside the axes: 0 = left/top.
_LEGEND_ANCHORS = {
    "upper right": (1.0, 0.0), "upper left": (0.0, 0.0),
    "lower left": (0.0, 1.0), "lower right": (1.0, 1.0),
    "upper center": (0.5, 0.0), "lower center": (0.5, 1.0),
    "center left": (0.0, 0.5), "center right": (1.0, 0.5),
    "right": (1.0, 0.5), "center": (0.5, 0.5), "best": (1.0, 0.0),
}


def _legend_layout(ax, st):
    """Compute legend geometry: entries, columns, cell size, box size."""
    entries = [a for a in ax.artists if getattr(a, "label", None)]
    if not entries:
        return None
    fs = st.tick_label_size
    line_h = fs + 6
    sample_w = 22
    pad = 6
    ncol = min(max(1, ax._legend_ncol), len(entries))
    nrows = (len(entries) + ncol - 1) // ncol
    text_w = max(text_width(a.label, fs) for a in entries)
    col_w = sample_w + text_w + pad * 2
    title = ax._legend_title
    title_h = line_h if title else 0
    box_w = col_w * ncol + pad
    if title:
        box_w = max(box_w, text_width(title, fs) + pad * 2)
    box_h = line_h * nrows + pad + title_h
    return {
        "entries": entries, "fs": fs, "line_h": line_h, "sample_w": sample_w,
        "pad": pad, "ncol": ncol, "col_w": col_w, "title": title,
        "title_h": title_h, "box_w": box_w, "box_h": box_h,
    }


def _legend_origin(ax, lay, px_left, px_top, px_w, px_h):
    fx, fy = _LEGEND_ANCHORS.get(ax._legend_loc, (1.0, 0.0))
    bx = px_left + 6 + fx * max(0.0, px_w - lay["box_w"] - 12)
    by = px_top + 6 + fy * max(0.0, px_h - lay["box_h"] - 12)
    return bx, by


def _render_legend(ax, st, px_left, px_top, px_w, px_h, body):
    lay = _legend_layout(ax, st)
    if lay is None:
        return
    fs, line_h, sample_w, pad = lay["fs"], lay["line_h"], lay["sample_w"], lay["pad"]
    ncol, col_w, title_h = lay["ncol"], lay["col_w"], lay["title_h"]
    box_w, box_h = lay["box_w"], lay["box_h"]
    bx, by = _legend_origin(ax, lay, px_left, px_top, px_w, px_h)

    body.append(
        f'<g class="simpleplot-legend"><rect x="{_fmt(bx)}" y="{_fmt(by)}" '
        f'width="{_fmt(box_w)}" height="{_fmt(box_h)}" rx="3" fill="#ffffff" '
        f'fill-opacity="0.85" stroke="#cccccc" stroke-width="0.8"/>'
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
            body.append(
                f'<line x1="{_fmt(sx)}" y1="{_fmt(row_y)}" x2="{_fmt(sx + sample_w)}" '
                f'y2="{_fmt(row_y)}" stroke="{color}" stroke-width="2"/>'
            )
        body.append(
            f'<text x="{_fmt(sx + sample_w + pad)}" y="{_fmt(row_y + fs * 0.35)}" '
            f'font-size="{fs}" fill="{st.text_color}">{_esc(a.label)}</text>'
        )
    body.append("</g>")


def _render_colorbar(ax, tr, px_left, px_top, px_w, px_h, clip_id, body):
    """Vertical gradient strip + right-side ticks for a colorbar axes."""
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
    _render_spines(ax.style, px_left, px_top, px_w, px_h, body)

    st = ax.style
    vmin, vmax = norm.vmin, norm.vmax
    ticks = nice_ticks(vmin, vmax)
    span = (vmax - vmin) or 1.0
    marks, labels = [], []
    for t, lab in zip(ticks, format_ticks(ticks)):
        frac = (t - vmin) / span
        y = px_top + (1 - frac) * px_h
        marks.append(f'<line x1="{_fmt(px_left + px_w)}" y1="{_fmt(y)}" x2="{_fmt(px_left + px_w + st.tick_size)}" y2="{_fmt(y)}"/>')
        labels.append(
            f'<text x="{_fmt(px_left + px_w + st.tick_size + 2)}" y="{_fmt(y + st.tick_label_size * 0.35)}" '
            f'font-size="{st.tick_label_size}" fill="{st.text_color}">{_esc(lab)}</text>'
        )
    body.append(f'<g stroke="{st.spine_color}" stroke-width="{st.tick_width}">{"".join(marks)}</g>')
    body.append("".join(labels))
