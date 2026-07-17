"""Raster (PNG) backend via Pillow.

A second renderer that draws a Figure's primitives directly onto a Pillow canvas
(supersampled, then downscaled for antialiasing). Pillow ships as a pure wheel
on every platform, so PNG export needs no cairo/native SVG rasterizer. The
geometry mirrors :mod:`simpleplot.svg` -- both consume the same transforms.
"""

from __future__ import annotations

import math

import numpy as np

from .artists import (
    Annotation, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, HLine, Image, Line2D, LineCollection, Pie, Polygon, QuadMesh,
    Quiver, ScatterCollection, Span, Stem, Text, Violin, VLine,
)
from .colors import apply_colormap, to_hex
from .svg import _effective_rect, _pixel_rect, _resolve_tick_labels
from .ticker import format_ticks, log_ticks, nice_ticks
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


def _font(size):
    from PIL import ImageFont

    key = int(round(size))
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.load_default(size=key)
        except TypeError:                      # very old Pillow
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def figure_to_image(fig, scale=2):
    """Render ``fig`` to a Pillow ``Image`` (RGB), supersampled by ``scale``."""
    from PIL import Image as PILImage, ImageDraw

    dpi = fig.style.dpi
    W = int(round(fig.figsize[0] * dpi))
    H = int(round(fig.figsize[1] * dpi))
    S = max(1, int(scale))
    canvas = PILImage.new("RGBA", (W * S, H * S), _rgba(fig.style.facecolor))
    draw = ImageDraw.Draw(canvas)

    for ax in fig.axes:
        _raster_axes(ax, fig, W * S, H * S, S, draw, canvas)
    _raster_figtexts(fig, W * S, H * S, S, draw)

    if S > 1:
        canvas = canvas.resize((W, H), PILImage.LANCZOS)
    return canvas.convert("RGB")


def save_png(fig, path, scale=2):
    figure_to_image(fig, scale=scale).save(path, format="PNG")
    return path


def save_pdf(fig, path):
    """Vector PDF via svglib + reportlab (no cairo needed)."""
    import io

    try:
        from reportlab.graphics import renderPDF
        from svglib.svglib import svg2rlg
    except ImportError as e:
        raise RuntimeError(
            "PDF export needs svglib + reportlab (standard dependencies); "
            "reinstall simpleplot to restore them"
        ) from e
    drawing = svg2rlg(io.StringIO(fig.to_svg()))
    renderPDF.drawToFile(drawing, path)
    return path


# -- axes -------------------------------------------------------------------
def _raster_axes(ax, fig, W, H, S, draw, canvas):
    st = ax.style
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    L, T, Wp, Hp = _effective_rect(ax, *_pixel_rect(ax, W, H), (xmin, xmax), (ymin, ymax))
    xlim_t = (xmax, xmin) if ax._xinverted else (xmin, xmax)
    ylim_t = (ymax, ymin) if ax._yinverted else (ymin, ymax)
    tr = LinearTransform(xlim_t, ylim_t, (L, T, Wp, Hp),
                         xscale=ax._xscale, yscale=ax._yscale)

    if ax._is_colorbar:
        _raster_colorbar(ax, tr, L, T, Wp, Hp, S, draw, canvas)
        return

    draw.rectangle([L, T, L + Wp, T + Hp], fill=_rgb(st.axes_facecolor))

    xticks = (ax._xticks if ax._xticks is not None else
              (log_ticks(xmin, xmax) if ax._xscale == "log" else nice_ticks(xmin, xmax)))
    yticks = (ax._yticks if ax._yticks is not None else
              (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))

    if ax._grid and not ax._axis_off:
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

    clip = (L, T, L + Wp, T + Hp)
    for artist in ax.artists:
        _raster_artist(artist, tr, st, S, draw, canvas, clip)

    if not ax._axis_off:
        _raster_ticks(ax, st, tr, xticks, yticks, L, T, Wp, Hp, S, draw)
        draw.rectangle([L, T, L + Wp, T + Hp], outline=_rgb(st.spine_color),
                       width=max(1, int(round(st.spine_width * S))))
    _raster_labels(ax, st, L, T, Wp, Hp, S, draw)
    if ax._show_legend:
        _raster_legend(ax, st, L, T, Wp, Hp, S, draw)


def _raster_artist(artist, tr, st, S, draw, canvas, clip):
    if isinstance(artist, (Line2D, FrameLine2D)):
        if isinstance(artist, FrameLine2D):
            x0, y0 = artist.frame_xy(0)
            pts = tr.xy(x0, y0)
        else:
            pts = tr.xy(artist.x, artist.y)
        _polyline(draw, pts, _rgb(artist.color),
                  max(1, int(round(artist.linewidth * S))),
                  _DASH.get(artist.linestyle))
    elif isinstance(artist, ScatterCollection):
        _scatter(artist, tr, st, S, draw)
    elif isinstance(artist, (QuadMesh, Image)):
        _mesh(artist, tr, canvas)
    elif isinstance(artist, VLine):
        x = float(tr.x(artist.x))
        _polyline(draw, np.array([[x, tr.px_top], [x, tr.px_top + tr.px_h]]),
                  _rgb(artist.color), max(1, int(round(artist.linewidth * S))),
                  _DASH.get(artist.linestyle))
    elif isinstance(artist, HLine):
        y = float(tr.y(artist.y))
        _polyline(draw, np.array([[tr.px_left, y], [tr.px_left + tr.px_w, y]]),
                  _rgb(artist.color), max(1, int(round(artist.linewidth * S))),
                  _DASH.get(artist.linestyle))
    elif isinstance(artist, Span):
        rl, rt = tr.px_left, tr.px_top
        rr, rb = tr.px_left + tr.px_w, tr.px_top + tr.px_h
        if artist.orientation == "vertical":
            a, b = float(tr.x(artist.lo)), float(tr.x(artist.hi))
            box = [max(min(a, b), rl), rt, min(max(a, b), rr), rb]
        else:
            a, b = float(tr.y(artist.lo)), float(tr.y(artist.hi))
            box = [rl, max(min(a, b), rt), rr, min(max(a, b), rb)]
        if box[2] > box[0] and box[3] > box[1]:
            pts = [(box[0], box[1]), (box[2], box[1]),
                   (box[2], box[3]), (box[0], box[3])]
            _composite_polygon(canvas, pts, _rgba(artist.color, artist.alpha))
    elif isinstance(artist, Bars):
        _bars(artist, tr, S, draw)
    elif isinstance(artist, FillBetween):
        top = tr.xy(artist.x, artist.y1)
        bot = tr.xy(artist.x[::-1], artist.y2[::-1])
        poly = [tuple(p) for p in np.vstack([top, bot]) if np.isfinite(p).all()]
        if len(poly) >= 3:
            _composite_polygon(canvas, poly, _rgba(artist.color, artist.alpha))
    elif isinstance(artist, Polygon):
        pts = [tuple(p) for p in tr.xy(artist.x, artist.y) if np.isfinite(p).all()]
        if len(pts) >= 3:
            outline = _rgb(artist.edgecolor) if artist.edgecolor else None
            _composite_polygon(canvas, pts, _rgba(artist.color, artist.alpha),
                               outline=outline)
    elif isinstance(artist, LineCollection):
        w = max(1, int(round(artist.linewidth * S)))
        dash = _DASH.get(artist.linestyle)
        for x0, y0, x1, y1 in artist.segments:
            seg = np.array([[tr.x(x0), tr.y(y0)], [tr.x(x1), tr.y(y1)]])
            _polyline(draw, seg, _rgb(artist.color), w, dash)
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
        _pie(artist, tr, S, draw)
    elif isinstance(artist, BoxPlot):
        _boxplot(artist, tr, st, S, draw)
    elif isinstance(artist, Violin):
        _violin(artist, tr, draw)
    elif isinstance(artist, Text):
        _text(draw, float(tr.x(artist.x)), float(tr.y(artist.y)), artist.text,
              _rgb(artist.color), _font(artist.size * S), artist.ha, artist.va,
              artist.rotation)
    elif isinstance(artist, Annotation):
        tx, ty = float(tr.x(artist.xytext[0])), float(tr.y(artist.xytext[1]))
        if artist.arrowprops is not None:
            px, py = float(tr.x(artist.xy[0])), float(tr.y(artist.xy[1]))
            col = (artist.arrowprops.get("color", artist.color)
                   if isinstance(artist.arrowprops, dict) else artist.color)
            _quiver_arrow(draw, tx, ty, px, py, _rgb(col), S)
        _text(draw, tx, ty, artist.text, _rgb(artist.color), _font(artist.size * S),
              artist.ha, artist.va, 0.0)


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


def _scatter(coll, tr, st, S, draw):
    xp, yp = tr.x(coll.x), tr.y(coll.y)
    r = np.broadcast_to(np.asarray(coll.s, float), xp.shape) / 2.0 * st.dpi / 72.0 * S
    colors = coll.face_colors() or [coll.color] * len(xp)
    for cx, cy, rad, col in zip(xp, yp, r, colors):
        if np.isfinite(cx) and np.isfinite(cy):
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                         fill=_rgba(col, coll.alpha))


def _mesh(mesh, tr, canvas):
    from PIL import Image as PILImage

    rgba = mesh.rgba().astype(np.uint8)
    xmin, xmax, ymin, ymax = mesh.extent()
    ix, iy = float(tr.x(xmin)), float(tr.y(ymax))
    iw = float(tr.x(xmax)) - ix
    ih = float(tr.y(ymin)) - iy
    if iw <= 0 or ih <= 0:
        return
    im = PILImage.fromarray(rgba, "RGBA").resize(
        (max(1, int(round(iw))), max(1, int(round(ih)))), PILImage.NEAREST)
    canvas.alpha_composite(im, (int(round(ix)), int(round(iy))))


def _bars(bars, tr, S, draw):
    for i in range(len(bars.pos)):
        p, ln, th, ba = bars.pos[i], bars.length[i], bars.thickness[i], bars.base[i]
        if bars.orientation == "vertical":
            x0, x1 = float(tr.x(p - th / 2)), float(tr.x(p + th / 2))
            y0, y1 = float(tr.y(ba)), float(tr.y(ba + ln))
        else:
            y0, y1 = float(tr.y(p - th / 2)), float(tr.y(p + th / 2))
            x0, x1 = float(tr.x(ba)), float(tr.x(ba + ln))
        box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        outline = _rgb(bars.edgecolor) if bars.edgecolor else None
        draw.rectangle(box, fill=_rgba(bars.colors[i], bars.alpha), outline=outline,
                       width=max(1, int(round(bars.linewidth * S))) if outline else 1)


def _stem(stem, tr, st, S, draw):
    y0 = float(tr.y(stem.baseline))
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
        ylo, yhi = tr.y(eb.y - eb.yerr), tr.y(eb.y + eb.yerr)
        for x, a, b in zip(xb, ylo, yhi):
            draw.line([x, a, x, b], fill=col, width=S)
            draw.line([x - cap, a, x + cap, a], fill=col, width=S)
            draw.line([x - cap, b, x + cap, b], fill=col, width=S)
    r = eb.markersize / 2.0 * st.dpi / 72.0 * S
    for x, y in zip(xb, yb):
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


def _pie(pie, tr, S, draw):
    cx = tr.px_left + tr.px_w / 2.0
    cy = tr.px_top + tr.px_h / 2.0
    R = 0.42 * min(tr.px_w, tr.px_h) * pie.radius
    box = [cx - R, cy - R, cx + R, cy + R]
    ang = math.radians(pie.startangle)
    for i, frac in enumerate(pie.fracs):
        a1 = ang - frac * 2 * math.pi
        draw.pieslice(box, -math.degrees(ang), -math.degrees(a1),
                      fill=_rgb(pie.colors[i]), outline=(255, 255, 255),
                      width=max(1, int(round(1.5 * S))))
        ang = a1


def _boxplot(bp, tr, st, S, draw):
    col = _rgb(bp.color)
    w = max(1, int(round(1.3 * S)))
    for pos, s in zip(bp.positions, bp.stats):
        c0, c1 = pos - bp.width / 2, pos + bp.width / 2
        if bp.orientation == "vertical":
            x0, x1 = float(tr.x(c0)), float(tr.x(c1))
            xc = float(tr.x(pos))
            yq1, yq3, ym = float(tr.y(s["q1"])), float(tr.y(s["q3"])), float(tr.y(s["med"]))
            ylo, yhi = float(tr.y(s["lo"])), float(tr.y(s["hi"]))
            draw.rectangle([min(x0, x1), min(yq1, yq3), max(x0, x1), max(yq1, yq3)],
                           outline=col, width=w)
            draw.line([x0, ym, x1, ym], fill=col, width=max(1, int(round(1.8 * S))))
            draw.line([xc, yq1, xc, ylo], fill=col, width=S)
            draw.line([xc, yq3, xc, yhi], fill=col, width=S)
            draw.line([x0, ylo, x1, ylo], fill=col, width=S)
            draw.line([x0, yhi, x1, yhi], fill=col, width=S)


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


def _text(draw, x, y, s, fill, font, ha="left", va="baseline", rotation=0.0):
    if rotation:
        from PIL import Image as PILImage, ImageDraw

        bbox = draw.textbbox((0, 0), s, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tmp = PILImage.new("RGBA", (max(1, w + 4), max(1, h + 4)), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((2 - bbox[0], 2 - bbox[1]), s, fill=fill, font=font)
        tmp = tmp.rotate(rotation, expand=True)  # PIL & matplotlib: CCW positive
        draw._image.alpha_composite(tmp, (int(x - tmp.width / 2), int(y - tmp.height / 2)))
        return
    anchor = _PIL_H.get(ha, "l") + _PIL_V.get(va, "s")
    draw.text((x, y), s, fill=fill, font=font, anchor=anchor)


def _quiver_arrow(draw, x0, y0, x1, y1, col, S):
    w = max(1, int(round(1.2 * S)))
    draw.line([x0, y0, x1, y1], fill=col, width=w)
    ang = math.atan2(y1 - y0, x1 - x0)
    hl = 7.0 * S
    for da in (-0.4, 0.4):
        draw.line([x1, y1, x1 - hl * math.cos(ang + da), y1 - hl * math.sin(ang + da)],
                  fill=col, width=w)


# -- furniture --------------------------------------------------------------
def _raster_ticks(ax, st, tr, xticks, yticks, L, T, Wp, Hp, S, draw):
    ts = st.tick_size * S
    col = _rgb(st.spine_color)
    fs = st.tick_label_size * S
    font = _font(fs)
    yb = T + Hp
    xlabels = _resolve_tick_labels(ax._xticklabels, xticks)
    ylabels = _resolve_tick_labels(ax._yticklabels, yticks)
    for xt, lab in zip(xticks, xlabels):
        x = float(tr.x(xt))
        draw.line([x, yb, x, yb + ts], fill=col, width=max(1, int(round(st.tick_width * S))))
        draw.text((x, yb + ts + 1), lab, fill=_rgb(st.text_color), font=font, anchor="ma")
    for yt, lab in zip(yticks, ylabels):
        y = float(tr.y(yt))
        draw.line([L - ts, y, L, y], fill=col, width=max(1, int(round(st.tick_width * S))))
        draw.text((L - ts - 2, y), lab, fill=_rgb(st.text_color), font=font, anchor="rm")


def _raster_labels(ax, st, L, T, Wp, Hp, S, draw):
    cx = L + Wp / 2.0
    if ax._xlabel and not ax._axis_off:
        y = T + Hp + (st.tick_size + st.tick_label_size + st.label_size + 4) * S
        draw.text((cx, y), ax._xlabel, fill=_rgb(st.text_color),
                  font=_font(st.label_size * S), anchor="mm")
    if ax._ylabel and not ax._axis_off:
        _vtext(draw, ax._ylabel, L - (st.tick_label_size + st.label_size + 20) * S,
               T + Hp / 2.0, _rgb(st.text_color), _font(st.label_size * S))
    if ax._title:
        draw.text((cx, T - 8 * S), ax._title, fill=_rgb(st.text_color),
                  font=_font(st.title_size * S), anchor="mb")


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
    font = _font(fs)
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
        box_w = max(box_w, draw.textlength(title, font=font) + pad * 2)
    box_h = line_h * nrows + pad + title_h

    fx, fy = _LEGEND_ANCHORS.get(ax._legend_loc, (1.0, 0.0))
    bx = L + 6 * S + fx * max(0.0, Wp - box_w - 12 * S)
    by = T + 6 * S + fy * max(0.0, Hp - box_h - 12 * S)
    draw.rectangle([bx, by, bx + box_w, by + box_h], fill=(255, 255, 255),
                   outline=(204, 204, 204))
    if title:
        draw.text((bx + box_w / 2, by + pad), title, fill=_rgb(st.text_color),
                  font=font, anchor="ma")
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
            draw.rectangle([sx, ry - 5 * S, sx + sample, ry + 5 * S], fill=color)
        else:
            draw.line([sx, ry, sx + sample, ry], fill=color, width=max(1, int(round(2 * S))))
        draw.text((sx + sample + pad, ry), a.label, fill=_rgb(st.text_color),
                  font=font, anchor="lm")


def _raster_figtexts(fig, W, H, S, draw):
    st = fig.style
    if fig._suptitle:
        t = fig._suptitle
        size = (t.get("size") or st.title_size * 1.5) * S
        draw.text((W / 2, 6 * S), t["text"], fill=_rgb(st.text_color),
                  font=_font(size), anchor="ma")
    if fig._supxlabel:
        t = fig._supxlabel
        size = (t.get("size") or st.label_size * 1.2) * S
        draw.text((W / 2, H - 6 * S), t["text"], fill=_rgb(st.text_color),
                  font=_font(size), anchor="md")
    if fig._supylabel:
        t = fig._supylabel
        size = (t.get("size") or st.label_size * 1.2) * S
        _vtext(draw, t["text"], 6 * S + size / 2, H / 2, _rgb(st.text_color), _font(size))


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
    vmin, vmax = src.norm.vmin, src.norm.vmax
    ticks = nice_ticks(vmin, vmax)
    span = (vmax - vmin) or 1.0
    font = _font(st.tick_label_size * S)
    for t, lab in zip(ticks, format_ticks(ticks)):
        frac = (t - vmin) / span
        y = T + (1 - frac) * Hp
        draw.line([L + Wp, y, L + Wp + st.tick_size * S, y], fill=_rgb(st.spine_color), width=S)
        draw.text((L + Wp + st.tick_size * S + 2, y), lab, fill=_rgb(st.text_color),
                  font=font, anchor="lm")
