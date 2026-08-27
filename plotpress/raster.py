"""Raster (PNG) backend via Pillow.

A second renderer that draws a Figure's primitives directly onto a Pillow canvas
(supersampled, then downscaled for antialiasing). Pillow ships as a pure wheel
on every platform, so PNG export needs no cairo/native SVG rasterizer. The
geometry mirrors :mod:`plotpress.svg` -- both consume the same transforms.
"""

from __future__ import annotations

import math

import numpy as np

from .artists import (
    Annotation, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Pie, Polygon, Quiver, ScatterCollection, Span,
    Stem, Text, Violin,
)
from .colors import colorbar_ticks, to_hex
# Which files can draw a given font stack is declared once, in fonts/families,
# next to which width table measures it -- see that module for why the two must
# be decided together. Imported under the old private names so anything
# monkeypatching this module keeps working.
from .fonts.families import HELVETICA_FILES as _HELVETICA_METRIC_FILES
from .fonts.families import HELVETICA_FILES_BOLD as _HELVETICA_METRIC_FILES_BOLD
from .fonts.families import font_files as _font_files
from .primitives import artist_to_prims
from .primitives import ImagePrim as PImage
from .primitives import Line as PLine
from .primitives import Markers as PMarkers
from .primitives import Path as PPath
from .primitives import PolygonBatch as PPolyBatch
from .primitives import Rect as PRect
from .primitives import Segments as PSegments
from .svg import (
    _effective_rect, _group_axes_extra, _group_colorbar_extra, _group_colorbars,
    _max_ytick_width, _pixel_rect,
    _resolve_tick_labels,
)
from .ticker import log_ticks, nice_ticks
from .transform import LinearTransform

_DASH = {"-": None, "--": (6, 4), ":": (1, 3), "-.": (6, 3, 1, 3)}
_font_cache = {}
_PIL_H = {"left": "l", "center": "m", "right": "r"}
_PIL_V = {"baseline": "s", "center": "m", "top": "a", "bottom": "d"}


def _rgb(color):
    c = to_hex(color).lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _rgba(color, alpha=1.0):
    return _rgb(color) + (int(round(alpha * 255)),)


def _composite_polygon(canvas, pts, rgba, outline=None):
    """Draw a filled polygon with correct alpha by compositing a bbox layer.

    Drawing directly with an RGBA fill *replaces* pixels (alpha is then dropped
    by the final RGB conversion), so translucent fills would render opaque.
    Compositing a small transparent layer blends properly instead.
    """
    from PIL import Image as PILImage, ImageDraw

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = int(math.floor(min(xs))), int(math.floor(min(ys)))
    x1, y1 = int(math.ceil(max(xs))), int(math.ceil(max(ys)))
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    layer = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    ldraw.polygon([(px - x0, py - y0) for px, py in pts], fill=rgba,
                  outline=outline)
    canvas.alpha_composite(layer, (x0, y0))


def _font(size, family=None, bold=False):
    """A Pillow font for ``size`` px, honoring ``family`` where the system has it.

    Falls back to Pillow's built-in face when nothing else resolves, which keeps
    headless machines rendering rather than failing.
    """
    from PIL import ImageFont

    key = (int(round(size)), family, bool(bold))
    if key in _font_cache:
        return _font_cache[key]

    font = None
    for name in _font_files(family, bold):
        try:
            font = ImageFont.truetype(name, key[0])
            break
        except OSError:
            continue                           # not installed here; try the next
    if font is None:
        try:
            font = ImageFont.load_default(size=key[0])
        except Exception:
            # TypeError on very old Pillow (no size=); OSError/ImportError if the
            # sized default needs FreeType and this build lacks it. The unsized
            # bitmap default is the last resort that always exists.
            font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def figure_to_image(fig, scale=2, frame=0, animate_unit="main"):
    """Render ``fig`` to a Pillow ``Image`` (RGB), supersampled by ``scale``.

    ``frame``/``animate_unit`` select which frame of any ``plot_frames()``
    series registered under ``animate_unit`` to draw (see :func:`save_gif`);
    every other artist, and any ``FrameLine2D`` under a different slider
    unit, is unaffected and renders as it always has.
    """
    from PIL import Image as PILImage, ImageDraw

    fig._settle_layout()
    dpi = fig.style.dpi
    W = int(round(fig.figsize[0] * dpi))
    H = int(round(fig.figsize[1] * dpi))
    S = max(1, int(scale))
    canvas = PILImage.new("RGBA", (W * S, H * S), _rgba(fig.style.facecolor))
    draw = ImageDraw.Draw(canvas)

    for ax in fig.axes:
        _raster_axes(ax, fig, W * S, H * S, S, draw, canvas, frame, animate_unit)
    _raster_figtexts(fig, W * S, H * S, S, draw)
    _raster_figure_legend(fig, fig.style, W * S, H * S, S, draw)
    _raster_groups(fig, W * S, H * S, S, draw)

    if S > 1:
        canvas = canvas.resize((W, H), PILImage.LANCZOS)
    return canvas.convert("RGB")


def save_png(fig, path, scale=2):
    figure_to_image(fig, scale=scale).save(path, format="PNG")
    return path


def save_gif(fig, path, fps=10, scale=2, slider_unit="main", label_frames=True):
    """Animate a ``plot_frames()`` figure to a looping GIF via Pillow.

    Every ``FrameLine2D``/``FrameQuadMesh`` series registered under
    ``slider_unit`` (``"main"``, the figure's shared/global slider, by
    default) is stepped through all of its frames and the results stitched
    into a looping GIF -- the same data an interactive HTML slider scrubs
    through, as a self-contained file. A series under a *different* slider
    unit (an axes-local, non-shared ``plot_frames(..., shared=False)``) stays
    on its own frame 0 throughout, since only one unit can drive the
    animation at a time; pass its ``slider_group``/axes unit name to animate
    that one instead.

    ``label_frames`` stamps each frame with its slider value in the top-right
    corner (``"{slider_label} = {value}"``) -- an interactive HTML shows this
    right next to its slider, and a GIF has no slider to show it on, so
    without a label an exported frame is anonymous about which one it is.
    Pass ``False`` for bare frames.

    Raises ``ValueError`` if the figure has no ``plot_frames()`` series
    registered under ``slider_unit`` -- there is nothing to animate.
    """
    if slider_unit not in fig._sliders:
        available = sorted(fig._sliders) or ["(none)"]
        raise ValueError(
            f"no plot_frames() series registered under slider_unit={slider_unit!r}; "
            f"available slider units: {available}"
        )
    spec = fig._sliders[slider_unit]
    frames = []
    for f in range(spec["n"]):
        im = figure_to_image(fig, scale=scale, frame=f, animate_unit=slider_unit)
        if label_frames:
            _label_frame(im, spec["label"], spec["values"][f])
        frames.append(im)
    duration_ms = max(1, round(1000.0 / fps))
    frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:],
                   duration=duration_ms, loop=0)
    return path


def _label_frame(im, label, value):
    """Stamp ``label = value`` in the top-right corner, in place."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(im)
    text = f"{label} = {_format_slider_value(value)}"
    pad = 10
    _text(draw, im.width - pad, pad, text, (17, 17, 17), _font(13.0, None),
          ha="right", va="top", outline=(255, 255, 255), stroke=2.5)


def _format_slider_value(v):
    """An integral slider value (a day, a month) reads as ``5``, not ``5.0``."""
    return str(int(v)) if float(v).is_integer() else f"{v:.3g}"


def save_pdf(fig, path):
    """Vector PDF via svglib + reportlab (no cairo needed)."""
    import io

    try:
        from reportlab.graphics import renderPDF
        from svglib.svglib import svg2rlg
    except ImportError as e:
        raise RuntimeError(
            "PDF export needs svglib + reportlab (standard dependencies); "
            "reinstall plotpress to restore them"
        ) from e
    drawing = svg2rlg(io.StringIO(fig.to_svg()))
    renderPDF.drawToFile(drawing, path)
    return path


# -- axes -------------------------------------------------------------------
def _raster_spines(ax, L, T, Wp, Hp, S, draw):
    """Per-side box outline -- the raster counterpart of ``svg._render_spines``."""
    st = ax.style
    edges = {
        "top": (L, T, L + Wp, T), "bottom": (L, T + Hp, L + Wp, T + Hp),
        "left": (L, T, L, T + Hp), "right": (L + Wp, T, L + Wp, T + Hp),
    }
    for side, (x0, y0, x1, y1) in edges.items():
        spine = ax.spines[side]
        if not spine.get_visible():
            continue
        color = spine._color if spine._color is not None else st.spine_color
        width = spine._linewidth if spine._linewidth is not None else st.spine_width
        draw.line([x0, y0, x1, y1], fill=_rgb(color),
                  width=max(1, int(round(width * S))))


def _raster_axes(ax, fig, W, H, S, draw, canvas, frame=0, animate_unit="main"):
    st = ax.style
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    L, T, Wp, Hp = _effective_rect(ax, *_pixel_rect(ax, W, H), (xmin, xmax), (ymin, ymax))
    xlim_t = (xmax, xmin) if ax._xinverted else (xmin, xmax)
    ylim_t = (ymax, ymin) if ax._yinverted else (ymin, ymax)
    tr = LinearTransform(xlim_t, ylim_t, (L, T, Wp, Hp),
                         xscale=ax._xscale, yscale=ax._yscale)

    if not ax._visible:
        return

    if ax._is_colorbar:
        _raster_colorbar(ax, tr, L, T, Wp, Hp, S, draw, canvas)
        _raster_labels(ax, st, L, T, Wp, Hp, S, draw)   # title only, mirrors the SVG backend
        return

    is_twin = ax._twin_of is not None
    is_secondary = ax._secondary_of is not None
    overlay = is_twin or is_secondary
    if not overlay:
        draw.rectangle([L, T, L + Wp, T + Hp], fill=_rgb(ax.get_facecolor()))

    xticks = (ax._xticks if ax._xticks is not None else
              (log_ticks(xmin, xmax) if ax._xscale == "log" else nice_ticks(xmin, xmax)))
    yticks = (ax._yticks if ax._yticks is not None else
              (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))

    if ax._grid and not ax._axis_off and not overlay:
        gc = _rgba(st.grid_color, st.grid_alpha)
        gw = max(1, int(round(st.grid_width * S)))
        for xt in xticks:
            x = float(tr.x(xt))
            if L <= x <= L + Wp:
                draw.line([x, T, x, T + Hp], fill=gc, width=gw)
        for yt in yticks:
            y = float(tr.y(yt))
            if T <= y <= T + Hp:
                draw.line([L, y, L + Wp, y], fill=gc, width=gw)

    # Artists go onto a scratch layer, and only the part of that layer inside
    # the axes rect is composited back. This is the raster counterpart of the
    # SVG backend's <clipPath>: without it the two backends disagree the moment
    # any data falls outside the limits, and the PNG paints it across the rest
    # of the figure -- over neighbouring subplots, labels and the legend.
    _clip_artists(ax, tr, st, S, canvas, (L, T, Wp, Hp), frame, animate_unit)

    if not ax._axis_off:
        if is_twin:
            _raster_twin_ticks(ax, st, tr, xticks, yticks, L, T, Wp, Hp, S, draw)
        elif is_secondary:
            xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
            yst = st.copy(**ax._tick_overrides["y"]) if ax._tick_overrides["y"] else st
            is_x = ax._secondary_dim == "x"
            _raster_ticks(ax, xst, yst, tr, xticks if is_x else [], yticks if not is_x else [],
                         L, T, Wp, Hp, S, draw,
                         xside=ax._xtick_side, yside=ax._ytick_side)
        else:
            xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
            yst = st.copy(**ax._tick_overrides["y"]) if ax._tick_overrides["y"] else st
            _raster_ticks(ax, xst, yst, tr, xticks, yticks, L, T, Wp, Hp, S, draw,
                         xside=ax._xtick_side, yside=ax._ytick_side)
            if ax._minor_ticks_on:
                from .ticker import minor_ticks
                mxst = (xst.copy(**ax._minor_tick_overrides["x"])
                       if ax._minor_tick_overrides["x"] else xst)
                myst = (yst.copy(**ax._minor_tick_overrides["y"])
                       if ax._minor_tick_overrides["y"] else yst)
                xminor = minor_ticks(xticks, xmin, xmax, ax._xscale)
                yminor = minor_ticks(yticks, ymin, ymax, ax._yscale)
                _raster_minor_ticks(mxst, myst, tr, xminor, yminor, L, T, Wp, Hp, S, draw,
                                   xside=ax._xtick_side, yside=ax._ytick_side)
            _raster_spines(ax, L, T, Wp, Hp, S, draw)
    if not is_twin:
        _raster_labels(ax, st, L, T, Wp, Hp, S, draw)
    if ax._show_legend:
        _raster_legend(ax, st, L, T, Wp, Hp, S, draw)


def _draw_prim(p, S, draw, canvas):
    """Draw one backend-agnostic primitive onto the raster canvas."""
    if isinstance(p, PImage):
        if p.w <= 0 or p.h <= 0:
            return
        from PIL import Image as PILImage
        im = PILImage.fromarray(p.rgba, "RGBA").resize(
            (max(1, int(round(p.w))), max(1, int(round(p.h)))), PILImage.NEAREST)
        canvas.alpha_composite(im, (int(round(p.x)), int(round(p.y))))
        return
    if isinstance(p, PMarkers):
        finite = np.isfinite(p.points).all(axis=1)
        for (cx, cy), dm, col, ok in zip(p.points, p.diameters, p.colors, finite):
            if ok:
                rad = dm / 2.0
                draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                             fill=_rgba(col, p.alpha))
        return
    if isinstance(p, PLine):
        _polyline(draw, np.array([p.p0, p.p1]), _rgb(p.stroke),
                  max(1, int(round(p.stroke_width * S))), _DASH.get(p.linestyle))
    elif isinstance(p, PRect):
        pts = [(p.x, p.y), (p.x + p.w, p.y), (p.x + p.w, p.y + p.h), (p.x, p.y + p.h)]
        _composite_polygon(canvas, pts, _rgba(p.fill, p.fill_opacity))
    elif isinstance(p, PSegments):
        w = max(1, int(round(p.stroke_width * S)))
        dash = _DASH.get(p.linestyle)
        for a, b, c, d in p.segs:
            _polyline(draw, np.array([[a, b], [c, d]]), _rgb(p.stroke), w, dash)
    elif isinstance(p, PPolyBatch):
        outline = _rgb(p.edge) if p.edge else None
        al = int(round(p.alpha * 255))
        for verts, fc in zip(p.polys, p.fills):
            pts = [tuple(v) for v in verts]
            rgba = (_rgb(fc) if isinstance(fc, str)
                    else (int(fc[0]), int(fc[1]), int(fc[2]))) + (al,)
            _composite_polygon(canvas, pts, rgba, outline=outline)
    elif isinstance(p, PPath):
        if p.fill:
            pts = [tuple(v) for sub in p.subpaths for v in sub if np.isfinite(v).all()]
            if len(pts) >= 3:
                outline = _rgb(p.stroke) if p.stroke else None
                _composite_polygon(canvas, pts, _rgba(p.fill, p.fill_opacity),
                                   outline=outline)
        else:
            w = max(1, int(round(p.stroke_width * S)))
            dash = _DASH.get(p.linestyle)
            for sub in p.subpaths:
                _polyline(draw, sub, _rgb(p.stroke), w, dash)


def _clip_artists(ax, tr, st, S, canvas, rect, frame=0, animate_unit="main"):
    """Draw ``ax``'s artists clipped to ``rect`` = (left, top, w, h) in pixels.

    Pillow has no clip region, so the artists are drawn onto a transparent layer
    the size of the canvas and only the rect is composited back. The layer is
    cached on the canvas and cleared per axes rather than reallocated, because a
    figure can carry hundreds of axes and a full-canvas RGBA allocation each
    time dominates the render.
    """
    from PIL import Image as PILImage, ImageDraw

    L, T, Wp, Hp = rect
    box = (max(0, int(math.floor(L))), max(0, int(math.floor(T))),
           min(canvas.size[0], int(math.ceil(L + Wp))),
           min(canvas.size[1], int(math.ceil(T + Hp))))
    if box[2] <= box[0] or box[3] <= box[1]:
        return

    layer = getattr(canvas, "_plotpress_layer", None)
    if layer is None or layer.size != canvas.size:
        layer = PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))
        canvas._plotpress_layer = layer
    ldraw = ImageDraw.Draw(layer)

    for artist in ax.artists:
        _raster_artist(artist, tr, st, S, ldraw, layer, rect, frame, animate_unit)

    canvas.alpha_composite(layer.crop(box), (box[0], box[1]))
    # Clear only what was used, so the next axes starts from transparent.
    layer.paste((0, 0, 0, 0), box)


def _raster_artist(artist, tr, st, S, draw, canvas, clip, frame=0, animate_unit="main"):
    prims = artist_to_prims(artist, tr, 0, 0, size_scale=st.dpi / 72.0 * S)
    if prims is not None:
        for p in prims:
            _draw_prim(p, S, draw, canvas)
        return
    if isinstance(artist, FrameLine2D):
        # Only the unit being animated steps through its frames; a FrameLine2D
        # under any other slider unit stays on frame 0, same as static output.
        f = frame if artist.slider_unit == animate_unit else 0
        f = min(f, artist.n_frames - 1)
        x0, y0 = artist.frame_xy(f)
        _polyline(draw, tr.xy(x0, y0), _rgb(artist.color),
                  max(1, int(round(artist.linewidth * S))),
                  _DASH.get(artist.linestyle))
    elif isinstance(artist, FrameQuadMesh):
        # Same animate_unit rule as FrameLine2D above -- substitute that
        # frame's own fully-realized QuadMesh so this hits the ordinary
        # QuadMesh path in artist_to_prims, image flip/orientation included.
        f = frame if artist.slider_unit == animate_unit else 0
        f = min(f, artist.n_frames - 1)
        mesh_prims = artist_to_prims(artist.frame_mesh(f), tr, 0, 0,
                                     size_scale=st.dpi / 72.0 * S)
        for p in mesh_prims or []:
            _draw_prim(p, S, draw, canvas)
    elif isinstance(artist, Bars):
        _bars(artist, tr, S, draw)
    elif isinstance(artist, Stem):
        _stem(artist, tr, st, S, draw)
    elif isinstance(artist, ErrorBar):
        _errorbar(artist, tr, st, S, draw)
    elif isinstance(artist, EventPlot):
        _eventplot(artist, tr, S, draw)
    elif isinstance(artist, Quiver):
        _quiver(artist, tr, S, draw)
    elif isinstance(artist, Contour):
        col = None
        for lvl, color, segs in artist.line_segments:
            for a, b, c, e in segs:
                draw.line([float(tr.x(a)), float(tr.y(b)),
                           float(tr.x(c)), float(tr.y(e))],
                          fill=_rgb(color), width=max(1, int(round(1.2 * S))))
    elif isinstance(artist, Pie):
        _pie(artist, tr, st, S, draw)
    elif isinstance(artist, BoxPlot):
        _boxplot(artist, tr, st, S, draw)
    elif isinstance(artist, Violin):
        _violin(artist, tr, draw)
    elif isinstance(artist, Text):
        _text(draw, float(tr.x(artist.x)), float(tr.y(artist.y)), artist.text,
              _rgb(artist.color), _font(artist.size * S, st.font_family), artist.ha, artist.va,
              artist.rotation, _rgb(artist.outline) if artist.outline else None,
              artist.size * 0.15 * S)
    elif isinstance(artist, Annotation):
        from .svg import leader_anchor, text_box

        tx, ty = float(tr.x(artist.xytext[0])), float(tr.y(artist.xytext[1]))
        if artist.arrowprops is not None:
            px, py = float(tr.x(artist.xy[0])), float(tr.y(artist.xy[1]))
            col = (artist.arrowprops.get("color", artist.color)
                   if isinstance(artist.arrowprops, dict) else artist.color)
            # Same attachment rule as the SVG backend -- see svg.leader_anchor.
            # The box is measured in unscaled pixels, so scale it to this canvas.
            box = text_box(tx / S, ty / S, artist.text, artist.size,
                           artist.ha, artist.va, st)
            sx, sy = leader_anchor(box, (px / S, py / S))
            _quiver_arrow(draw, sx * S, sy * S, px, py, _rgb(col), S)
        _text(draw, tx, ty, artist.text, _rgb(artist.color), _font(artist.size * S, st.font_family),
              artist.ha, artist.va, 0.0,
              _rgb(artist.outline) if artist.outline else None,
              artist.size * 0.15 * S)


# -- primitives -------------------------------------------------------------
def _polyline(draw, pts, color, width, dash=None):
    mask = np.isfinite(pts).all(axis=1)
    n = len(pts)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        seg = [tuple(p) for p in pts[i:j]]
        if len(seg) >= 2:
            if dash:
                _dashed(draw, seg, color, width, dash)
            else:
                draw.line(seg, fill=color, width=width, joint="curve")
        i = j


def _dashed(draw, seg, color, width, dash):
    on = True
    di = 0
    remaining = dash[0]
    for (x0, y0), (x1, y1) in zip(seg[:-1], seg[1:]):
        seglen = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while pos < seglen:
            step = min(remaining, seglen - pos)
            t0, t1 = pos / seglen, (pos + step) / seglen
            if on:
                draw.line([x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0,
                           x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1],
                          fill=color, width=width)
            pos += step
            remaining -= step
            if remaining <= 1e-6:
                di = (di + 1) % len(dash)
                remaining = dash[di]
                on = not on


def _bars(bars, tr, S, draw):
    for i in range(len(bars.pos)):
        p, ln, th, ba = bars.pos[i], bars.length[i], bars.thickness[i], bars.base[i]
        if bars.orientation == "vertical":
            x0, x1 = float(tr.x(p - th / 2)), float(tr.x(p + th / 2))
            y0, y1 = float(tr.y_base(ba)), float(tr.y_base(ba + ln))
        else:
            y0, y1 = float(tr.y(p - th / 2)), float(tr.y(p + th / 2))
            x0, x1 = float(tr.x_base(ba)), float(tr.x_base(ba + ln))
        box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        outline = _rgb(bars.edgecolor) if bars.edgecolor else None
        draw.rectangle(box, fill=_rgba(bars.colors[i], bars.alpha), outline=outline,
                       width=max(1, int(round(bars.linewidth * S))) if outline else 1)


def _stem(stem, tr, st, S, draw):
    y0 = float(tr.y_base(stem.baseline))
    xb, yb = tr.x(stem.x), tr.y(stem.y)
    for x, y in zip(xb, yb):
        draw.line([float(x), y0, float(x), float(y)], fill=_rgb(stem.linecolor),
                  width=max(1, int(round(1.2 * S))))
    draw.line([float(tr.x(stem.x.min())), y0, float(tr.x(stem.x.max())), y0],
              fill=_rgb(st.spine_color), width=max(1, int(round(0.8 * S))))
    r = st.marker_size / 2.0 * st.dpi / 72.0 * S
    for x, y in zip(xb, yb):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=_rgb(stem.markercolor))


def _errorbar(eb, tr, st, S, draw):
    xb, yb = tr.x(eb.x), tr.y(eb.y)
    col = _rgb(eb.color)
    if eb.linestyle and eb.linestyle != "none":
        _polyline(draw, np.column_stack([xb, yb]), col,
                  max(1, int(round(eb.linewidth * S))))
    cap = eb.capsize * S
    if eb.yerr is not None:
        ylo, yhi = tr.y_base(eb.y - eb.yerr), tr.y_base(eb.y + eb.yerr)
        for x, a, b in zip(xb, ylo, yhi):
            draw.line([x, a, x, b], fill=col, width=S)
            draw.line([x - cap, a, x + cap, a], fill=col, width=S)
            draw.line([x - cap, b, x + cap, b], fill=col, width=S)
    r = eb.markersize / 2.0 * st.dpi / 72.0 * S
    for x, y in zip(xb, yb):
        if np.isfinite(x) and np.isfinite(y):      # see svg._render_errorbar
            draw.ellipse([x - r, y - r, x + r, y + r], fill=col)


def _eventplot(ev, tr, S, draw):
    half = ev.linelength / 2.0
    col = _rgb(ev.color)
    for row, off in zip(ev.rows, ev.offsets):
        if ev.orientation == "horizontal":
            y0, y1 = float(tr.y(off - half)), float(tr.y(off + half))
            for e in row:
                x = float(tr.x(e))
                draw.line([x, y0, x, y1], fill=col, width=max(1, int(round(1.2 * S))))
        else:
            x0, x1 = float(tr.x(off - half)), float(tr.x(off + half))
            for e in row:
                y = float(tr.y(e))
                draw.line([x0, y, x1, y], fill=col, width=max(1, int(round(1.2 * S))))


def _quiver(q, tr, S, draw):
    tx, ty = q.tips()
    x0, y0, x1, y1 = tr.x(q.X), tr.y(q.Y), tr.x(tx), tr.y(ty)
    col = _rgb(q.color)
    hl = 5.0 * S
    w = max(1, int(round(1.2 * S)))
    for bx, by, ex, ey in zip(x0, y0, x1, y1):
        draw.line([bx, by, ex, ey], fill=col, width=w)
        ang = math.atan2(ey - by, ex - bx)
        for da in (-math.radians(25), math.radians(25)):
            draw.line([ex, ey, ex - hl * math.cos(ang + da), ey - hl * math.sin(ang + da)],
                      fill=col, width=w)


def _pie(pie, tr, st, S, draw):
    cx = tr.px_left + tr.px_w / 2.0
    cy = tr.px_top + tr.px_h / 2.0
    R = 0.42 * min(tr.px_w, tr.px_h) * pie.radius
    box = [cx - R, cy - R, cx + R, cy + R]
    font = _font(10 * S, st.font_family)          # matches svg's fixed 10px
    txt_fill = _rgb(st.text_color)
    ang = math.radians(pie.startangle)
    for i, frac in enumerate(pie.fracs):
        a1 = ang - frac * 2 * math.pi
        draw.pieslice(box, -math.degrees(ang), -math.degrees(a1),
                      fill=_rgb(pie.colors[i]), outline=(255, 255, 255),
                      width=max(1, int(round(1.5 * S))))
        am = (ang + a1) / 2.0
        if pie.labels is not None:
            lx, ly = cx + 1.15 * R * math.cos(am), cy - 1.15 * R * math.sin(am)
            ha = "left" if math.cos(am) >= 0 else "right"
            _text(draw, lx, ly, str(pie.labels[i]), txt_fill, font, ha, "center")
        pct = pie.pct_text(frac)
        if pct is not None:
            px, py = cx + 0.6 * R * math.cos(am), cy - 0.6 * R * math.sin(am)
            _text(draw, px, py, pct, txt_fill, font, "center", "center")
        ang = a1


def _boxplot(bp, tr, st, S, draw):
    col = _rgb(bp.color)
    w = max(1, int(round(1.3 * S)))
    wm = max(1, int(round(1.8 * S)))
    r = st.marker_size / 2.0 * st.dpi / 72.0 * S
    for pos, s in zip(bp.positions, bp.stats):
        c0, c1 = pos - bp.width / 2, pos + bp.width / 2
        if bp.orientation == "vertical":
            x0, x1 = float(tr.x(c0)), float(tr.x(c1))
            xc = float(tr.x(pos))
            yq1, yq3, ym = float(tr.y(s["q1"])), float(tr.y(s["q3"])), float(tr.y(s["med"]))
            ylo, yhi = float(tr.y(s["lo"])), float(tr.y(s["hi"]))
            draw.rectangle([min(x0, x1), min(yq1, yq3), max(x0, x1), max(yq1, yq3)],
                           outline=col, width=w)
            draw.line([x0, ym, x1, ym], fill=col, width=wm)
            draw.line([xc, yq1, xc, ylo], fill=col, width=S)
            draw.line([xc, yq3, xc, yhi], fill=col, width=S)
            draw.line([x0, ylo, x1, ylo], fill=col, width=S)
            draw.line([x0, yhi, x1, yhi], fill=col, width=S)
            for fx in s["fliers"]:
                fy = float(tr.y(fx))
                draw.ellipse([xc - r, fy - r, xc + r, fy + r], outline=col, width=S)
        else:
            y0, y1 = float(tr.y(c0)), float(tr.y(c1))
            yc = float(tr.y(pos))
            xq1, xq3, xm = float(tr.x(s["q1"])), float(tr.x(s["q3"])), float(tr.x(s["med"]))
            xlo, xhi = float(tr.x(s["lo"])), float(tr.x(s["hi"]))
            draw.rectangle([min(xq1, xq3), min(y0, y1), max(xq1, xq3), max(y0, y1)],
                           outline=col, width=w)
            draw.line([xm, y0, xm, y1], fill=col, width=wm)
            draw.line([xq1, yc, xlo, yc], fill=col, width=S)
            draw.line([xq3, yc, xhi, yc], fill=col, width=S)
            draw.line([xlo, y0, xlo, y1], fill=col, width=S)
            draw.line([xhi, y0, xhi, y1], fill=col, width=S)
            for fx in s["fliers"]:
                fxx = float(tr.x(fx))
                draw.ellipse([fxx - r, yc - r, fxx + r, yc + r], outline=col, width=S)


def _violin(v, tr, draw):
    for pos, grid, hw in zip(v.positions, v.grids, v.halfwidths):
        if v.orientation == "vertical":
            left = np.column_stack([tr.x(pos - hw), tr.y(grid)])
            right = np.column_stack([tr.x(pos + hw)[::-1], tr.y(grid)[::-1]])
        else:
            left = np.column_stack([tr.x(grid), tr.y(pos - hw)])
            right = np.column_stack([tr.x(grid)[::-1], tr.y(pos + hw)[::-1]])
        poly = [tuple(p) for p in np.vstack([left, right])]
        draw.polygon(poly, fill=_rgba(v.color, 0.55), outline=_rgb(v.color))


def _text(draw, x, y, s, fill, font, ha="left", va="baseline", rotation=0.0,
          outline=None, stroke=0.0):
    """Draw text, optionally with a contrasting halo (see svg._text_svg).

    Pillow's ``stroke_width`` paints the rim under the glyph exactly as SVG's
    ``paint-order="stroke"`` does, so the two backends agree.
    """
    kw = {}
    if outline and stroke >= 1.0:
        kw = {"stroke_width": int(round(stroke)), "stroke_fill": outline}
    if rotation:
        from PIL import Image as PILImage, ImageDraw

        bbox = draw.textbbox((0, 0), s, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 4 + int(round(stroke))
        tmp = PILImage.new("RGBA", (max(1, w + 2 * pad), max(1, h + 2 * pad)),
                           (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((pad - bbox[0], pad - bbox[1]), s, fill=fill,
                                 font=font, **kw)
        tmp = tmp.rotate(rotation, expand=True)  # PIL & matplotlib: CCW positive
        draw._image.alpha_composite(tmp, (int(x - tmp.width / 2), int(y - tmp.height / 2)))
        return
    anchor = _PIL_H.get(ha, "l") + _PIL_V.get(va, "s")
    draw.text((x, y), s, fill=fill, font=font, anchor=anchor, **kw)


def _quiver_arrow(draw, x0, y0, x1, y1, col, S):
    w = max(1, int(round(1.2 * S)))
    draw.line([x0, y0, x1, y1], fill=col, width=w)
    ang = math.atan2(y1 - y0, x1 - x0)
    hl = 7.0 * S
    for da in (-0.4, 0.4):
        draw.line([x1, y1, x1 - hl * math.cos(ang + da), y1 - hl * math.sin(ang + da)],
                  fill=col, width=w)


# -- furniture --------------------------------------------------------------
def _raster_ticks(ax, xst, yst, tr, xticks, yticks, L, T, Wp, Hp, S, draw,
                  xside="bottom", yside="left"):
    xts = xst.tick_size * S
    xcol = _rgb(xst.spine_color)
    xfs = xst.tick_label_size * S
    xfont = _font(xfs, xst.font_family)
    xtw = max(1, int(round(xst.tick_width * S)))
    yts = yst.tick_size * S
    ycol = _rgb(yst.spine_color)
    yfs = yst.tick_label_size * S
    yfont = _font(yfs, yst.font_family)
    ytw = max(1, int(round(yst.tick_width * S)))
    xlabels = _resolve_tick_labels(ax._xticklabels, xticks)
    ylabels = _resolve_tick_labels(ax._yticklabels, yticks)
    x_top = xside == "top"
    x_axis = T if x_top else T + Hp
    x_sign = -1 if x_top else 1
    y_right = yside == "right"
    y_axis = L + Wp if y_right else L
    y_sign = 1 if y_right else -1
    for xt, lab in zip(xticks, xlabels):
        x = float(tr.x(xt))
        draw.line([x, x_axis, x, x_axis + x_sign * xts], fill=xcol, width=xtw)
        ly = x_axis + x_sign * (xts + 1)
        draw.text((x, ly), lab, fill=_rgb(xst.text_color), font=xfont,
                  anchor=("md" if x_top else "ma"))
    for yt, lab in zip(yticks, ylabels):
        y = float(tr.y(yt))
        draw.line([y_axis, y, y_axis + y_sign * yts, y], fill=ycol, width=ytw)
        lx = y_axis + y_sign * (yts + 2)
        draw.text((lx, y), lab, fill=_rgb(yst.text_color), font=yfont,
                  anchor=("lm" if y_right else "rm"))


def _raster_minor_ticks(xst, yst, tr, xticks, yticks, L, T, Wp, Hp, S, draw,
                        xside="bottom", yside="left"):
    """Unlabeled minor tick marks -- the raster counterpart of the SVG one."""
    xts = xst.tick_size * 0.6 * S
    xcol = _rgb(xst.spine_color)
    xtw = max(1, int(round(xst.tick_width * S)))
    yts = yst.tick_size * 0.6 * S
    ycol = _rgb(yst.spine_color)
    ytw = max(1, int(round(yst.tick_width * S)))
    x_top = xside == "top"
    x_axis = T if x_top else T + Hp
    x_sign = -1 if x_top else 1
    y_right = yside == "right"
    y_axis = L + Wp if y_right else L
    y_sign = 1 if y_right else -1
    for xt in xticks:
        x = float(tr.x(xt))
        draw.line([x, x_axis, x, x_axis + x_sign * xts], fill=xcol, width=xtw)
    for yt in yticks:
        y = float(tr.y(yt))
        draw.line([y_axis, y, y_axis + y_sign * yts, y], fill=ycol, width=ytw)


def _raster_twin_ticks(ax, st, tr, xticks, yticks, L, T, Wp, Hp, S, draw):
    col = _rgb(st.spine_color)
    ts = st.tick_size * S
    fs = st.tick_label_size * S
    font = _font(fs, st.font_family)
    tw = max(1, int(round(st.tick_width * S)))
    if ax._twin_shared == "x":                       # twinx: y-axis on the RIGHT
        xr = L + Wp
        for yt, lab in zip(yticks, _resolve_tick_labels(ax._yticklabels, yticks)):
            y = float(tr.y(yt))
            draw.line([xr, y, xr + ts, y], fill=col, width=tw)
            draw.text((xr + ts + 2, y), lab, fill=_rgb(st.text_color),
                      font=font, anchor="lm")
        if ax._ylabel:
            lx = xr + ts + (_max_ytick_width(ax, st) + st.label_size + 4) * S
            _vtext(draw, ax._ylabel, lx, T + Hp / 2.0,
                   _rgb(st.text_color), _font(st.label_size * S, st.font_family))
    else:                                            # twiny: x-axis on the TOP
        for xt, lab in zip(xticks, _resolve_tick_labels(ax._xticklabels, xticks)):
            x = float(tr.x(xt))
            draw.line([x, T, x, T - ts], fill=col, width=tw)
            draw.text((x, T - ts - 1), lab, fill=_rgb(st.text_color),
                      font=font, anchor="md")
        if ax._xlabel:
            draw.text((L + Wp / 2.0, T - ts - fs - st.label_size * S),
                      ax._xlabel, fill=_rgb(st.text_color),
                      font=_font(st.label_size * S, st.font_family), anchor="md")


def _raster_labels(ax, st, L, T, Wp, Hp, S, draw):
    cx = L + Wp / 2.0
    ts, fs = st.tick_size, st.tick_label_size
    if ax._xlabel and not ax._axis_off:
        # Overrides (align_xlabels) are stamped in 1x figure-pixel space, like
        # the SVG backend's -- scale to this backend's supersampled space.
        if ax._xlabel_y_override is not None:
            y = ax._xlabel_y_override * S
        elif ax._xtick_side == "top":
            y = T - (ts + fs + st.label_size) * S
        else:
            y = T + Hp + (ts + fs + st.label_size + 4) * S
        draw.text((cx, y), ax._xlabel, fill=_rgb(st.text_color),
                  font=_font(st.label_size * S, st.font_family), anchor="mm")
    if ax._ylabel and not ax._axis_off:
        # Mirror svg._render_labels exactly: clear the *measured* tick labels.
        # Substituting the tick font size for their width put this up to ~9px
        # from where the SVG draws it, jammed against the figure edge.
        if ax._ylabel_x_override is not None:
            lx = ax._ylabel_x_override * S
        elif ax._ytick_side == "right":
            lx = L + Wp + (ts + _max_ytick_width(ax, st) + st.label_size + 4) * S
        else:
            lx = L - (ts + _max_ytick_width(ax, st) + st.label_size + 4) * S
        _vtext(draw, ax._ylabel, lx, T + Hp / 2.0,
               _rgb(st.text_color), _font(st.label_size * S, st.font_family))
    if ax._title:
        # Pillow refuses a bottom/baseline anchor on multiline text, and the
        # title is the only label that uses one -- so a "\n" in a title raised
        # ValueError and took the whole PNG export with it, where every other
        # label merely broke the line. Stack the lines by hand instead. A
        # single-line title takes the same path and lands exactly where it did.
        from .svg import twiny_headroom

        size = ax._title_size or st.title_size
        font = _font(size * S, st.font_family)
        line_h = size * 1.2 * S
        top = T - (8 + twiny_headroom(ax, st)) * S
        for i, line in enumerate(reversed(ax._title.split("\n"))):
            draw.text((cx, top - i * line_h), line,
                      fill=_rgb(st.text_color), font=font, anchor="mb")


def _vtext(draw, text, x, y, fill, font):
    """Draw vertical (rotated 90°) text centered at (x, y)."""
    from PIL import Image as PILImage, ImageDraw

    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tmp = PILImage.new("RGBA", (max(1, w + 4), max(1, h + 4)), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((2 - bbox[0], 2 - bbox[1]), text, fill=fill, font=font)
    tmp = tmp.rotate(90, expand=True)
    draw._image.alpha_composite(
        tmp, (int(x - tmp.width / 2), int(y - tmp.height / 2)))


_LEGEND_ANCHORS = {
    "upper right": (1.0, 0.0), "upper left": (0.0, 0.0),
    "lower left": (0.0, 1.0), "lower right": (1.0, 1.0),
    "upper center": (0.5, 0.0), "lower center": (0.5, 1.0),
    "center left": (0.0, 0.5), "center right": (1.0, 0.5),
    "right": (1.0, 0.5), "center": (0.5, 0.5), "best": (1.0, 0.0),
}


def _raster_legend(ax, st, L, T, Wp, Hp, S, draw):
    entries = [a for a in ax.artists if getattr(a, "label", None)]
    if not entries:
        return
    fs = st.tick_label_size * S
    font = _font(fs, st.font_family)
    title_font = _font(fs, st.font_family, bold=True)   # SVG draws the title bold
    line_h = fs + 6 * S
    sample = 22 * S
    pad = 6 * S
    ncol = min(max(1, ax._legend_ncol), len(entries))
    nrows = (len(entries) + ncol - 1) // ncol
    tw = max(draw.textlength(a.label, font=font) for a in entries)
    col_w = sample + tw + pad * 2
    title = ax._legend_title
    title_h = line_h if title else 0
    box_w = col_w * ncol + pad
    if title:
        box_w = max(box_w, draw.textlength(title, font=title_font) + pad * 2)
    box_h = line_h * nrows + pad + title_h

    fx, fy = _LEGEND_ANCHORS.get(ax._legend_loc, (1.0, 0.0))
    bx = L + 6 * S + fx * max(0.0, Wp - box_w - 12 * S)
    by = T + 6 * S + fy * max(0.0, Hp - box_h - 12 * S)
    _raster_draw_legend(entries, st, S, draw, bx, by, box_w, box_h, ncol, col_w,
                        line_h, sample, pad, title, title_h, font, title_font)


def _raster_figure_legend(fig, st, W, H, S, draw):
    """The PNG counterpart of svg._render_figure_legend.

    Geometry comes from the *shared* layout in svg.py rather than from Pillow's
    own measurements, because figure.py already reserved a band of the canvas
    using those numbers -- measuring again here could size the box to something
    the reservation does not match.
    """
    from .svg import figure_legend_layout, figure_legend_origin

    lay = figure_legend_layout(fig)
    if lay is None:
        return
    spec = fig._figure_legend
    pad_px = spec["pad"] * min(W / S, H / S) + 4
    bx, by = figure_legend_origin(spec, lay, W / S, H / S, pad_px)
    fs = lay["fs"] * S
    _raster_draw_legend(
        lay["entries"], st, S, draw, bx * S, by * S,
        lay["box_w"] * S, lay["box_h"] * S, lay["ncol"], lay["col_w"] * S,
        lay["line_h"] * S, lay["sample_w"] * S, lay["pad"] * S,
        lay["title"], lay["title_h"] * S,
        _font(fs, st.font_family), _font(fs, st.font_family, bold=True))


def _raster_draw_legend(entries, st, S, draw, bx, by, box_w, box_h, ncol, col_w,
                        line_h, sample, pad, title, title_h, font, title_font):
    """Paint a legend box whose geometry has already been decided."""
    draw.rectangle([bx, by, bx + box_w, by + box_h], fill=(255, 255, 255),
                   outline=(204, 204, 204))
    if title:
        draw.text((bx + box_w / 2, by + pad), title, fill=_rgb(st.text_color),
                  font=title_font, anchor="ma")
    for i, a in enumerate(entries):
        r, c = divmod(i, ncol)
        sx = bx + pad + c * col_w
        ry = by + pad + title_h + line_h * r + line_h / 2.0
        if isinstance(a, Bars):
            color = _rgb(a.colors[0] if a.colors else "#333333")
        else:
            color = _rgb(getattr(a, "color", None)
                         or getattr(a, "linecolor", None) or "#333333")
        if isinstance(a, ScatterCollection):
            rr = 4 * S
            draw.ellipse([sx + sample / 2 - rr, ry - rr, sx + sample / 2 + rr, ry + rr], fill=color)
        elif isinstance(a, (Bars, FillBetween, Span, Polygon)):
            # SVG gives this swatch the artist's fill-opacity; composite the
            # same alpha over the box's white background so the two backends
            # agree on how a translucent fill reads in the legend.
            alpha = getattr(a, "alpha", 1.0) if isinstance(
                a, (FillBetween, Span, Polygon)) else 1.0
            swatch = tuple(int(round(c * alpha + 255 * (1.0 - alpha)))
                           for c in color[:3])
            draw.rectangle([sx, ry - 5 * S, sx + sample, ry + 5 * S], fill=swatch)
        else:
            # Match svg.draw_legend: the swatch carries the artist's dash
            # pattern, so a dashed reference line is not drawn as a solid one.
            width = max(1, int(round(2 * S)))
            dash = _DASH.get(getattr(a, "linestyle", "-"))
            seg = [(sx, ry), (sx + sample, ry)]
            if dash:
                _dashed(draw, seg, color, width, tuple(d * S for d in dash))
            else:
                draw.line([sx, ry, sx + sample, ry], fill=color, width=width)
        draw.text((sx + sample + pad, ry), a.label, fill=_rgb(st.text_color),
                  font=font, anchor="lm")


def _raster_figtexts(fig, W, H, S, draw):
    st = fig.style
    if fig._suptitle:
        t = fig._suptitle
        size = (t.get("size") or st.title_size * 1.5) * S
        draw.text((W / 2, 6 * S), t["text"], fill=_rgb(st.text_color),
                  font=_font(size, st.font_family, bold=True), anchor="ma")
    if fig._supxlabel:
        t = fig._supxlabel
        size = (t.get("size") or st.label_size * 1.2) * S
        draw.text((W / 2, H - 6 * S), t["text"], fill=_rgb(st.text_color),
                  font=_font(size, st.font_family), anchor="md")
    if fig._supylabel:
        t = fig._supylabel
        size = (t.get("size") or st.label_size * 1.2) * S
        _vtext(draw, t["text"], 6 * S + size / 2, H / 2, _rgb(st.text_color), _font(size, st.font_family))
    for t in fig._fig_texts:
        size = (t["size"] or st.font_size) * S
        x, y = t["x"] * W, (1.0 - t["y"]) * H
        anchor = _PIL_H.get(t["ha"], "l") + _PIL_V.get(t["va"], "s")
        draw.text((x, y), t["s"], fill=_rgb(t["color"] or st.text_color),
                  font=_font(size, st.font_family), anchor=anchor)


def _raster_groups(fig, W, H, S, draw):
    """The PNG counterpart of svg._render_groups."""
    st = fig.style
    for g in fig._groups:
        members = g["axes"] + _group_colorbars(g["axes"], fig)
        rects = [_pixel_rect(ax, W, H) for ax in members]
        extras = [_group_colorbar_extra(ax, st) if ax._is_colorbar
                 else _group_axes_extra(ax, st) for ax in members]
        pad = g["pad"] * S
        x0 = min(r[0] - e[2] * S for r, e in zip(rects, extras)) - pad
        y0 = min(r[1] - e[0] * S for r, e in zip(rects, extras)) - pad
        x1 = max(r[0] + r[2] + e[3] * S for r, e in zip(rects, extras)) + pad
        y1 = max(r[1] + r[3] + e[1] * S for r, e in zip(rects, extras)) + pad
        pts = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
        dash = _DASH.get(g["linestyle"])
        dash_scaled = tuple(d * S for d in dash) if dash else None
        _polyline(draw, pts, _rgb(g["color"]),
                 max(1, int(round(g["linewidth"] * S))), dash_scaled)
        size = (g["fontsize"] or fig.style.title_size) * S
        font = _font(size, fig.style.font_family, bold=True)
        color = _rgb(g["color"])
        pos = g["title_position"]
        if pos == "top":
            draw.text(((x0 + x1) / 2, y0 - 6 * S), g["title"], fill=color,
                      font=font, anchor="md")
        elif pos == "bottom":
            draw.text(((x0 + x1) / 2, y1 + 6 * S), g["title"], fill=color,
                      font=font, anchor="ma")
        elif pos == "left":
            draw.text((x0 - 6 * S, (y0 + y1) / 2), g["title"], fill=color,
                      font=font, anchor="rm")
        else:
            draw.text((x1 + 6 * S, (y0 + y1) / 2), g["title"], fill=color,
                      font=font, anchor="lm")


def _raster_colorbar(ax, tr, L, T, Wp, Hp, S, draw, canvas):
    from PIL import Image as PILImage

    src = ax._cbar_source
    lut = src.lut
    grad = np.flipud(lut).reshape(-1, 1, 3).astype(np.uint8)
    alpha = np.full((grad.shape[0], 1, 1), 255, np.uint8)
    rgba = np.concatenate([grad, alpha], axis=2)
    im = PILImage.fromarray(rgba, "RGBA").resize(
        (max(1, int(Wp)), max(1, int(Hp))), PILImage.BILINEAR)
    canvas.alpha_composite(im, (int(L), int(T)))
    draw.rectangle([L, T, L + Wp, T + Hp], outline=_rgb(ax.style.spine_color),
                   width=max(1, int(round(ax.style.spine_width * S))))
    st = ax.style
    _, fracs, tlabels = colorbar_ticks(src.norm)
    font = _font(st.tick_label_size * S, st.font_family)
    for frac, lab in zip(fracs, tlabels):
        y = T + (1 - frac) * Hp
        draw.line([L + Wp, y, L + Wp + st.tick_size * S, y], fill=_rgb(st.spine_color), width=S)
        draw.text((L + Wp + st.tick_size * S + 2, y), lab, fill=_rgb(st.text_color),
                  font=font, anchor="lm")
