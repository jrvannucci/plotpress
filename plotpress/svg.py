"""SVG serialization: turn a Figure's scene into an SVG document string.

This is the whole rendering pipeline, in pure Python + NumPy: transforms are
vectorized, each series becomes a single ``<path>`` (not one node per point),
huge lines are min/max-decimated before serialization, and each ``pcolormesh``
becomes one embedded ``<image>``. Coordinate formatting is vectorized with
``numpy.char``. Pure Python and NumPy are the whole story -- no compiled
extension; the library installs everywhere pip does.
"""

from __future__ import annotations

import math
import warnings

import numpy as np

from .artists import (
    Annotation, Barbs, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Image, Line2D, LineCollection, Pie, Polygon,
    PolyCollection, QuadMesh, Quiver, ScatterCollection, Span, Stem, Table, Text,
    Violin, _edges_from,
)
from .colors import apply_colormap, colorbar_ticks
from .png import png_data_uri
from .primitives import artist_to_prims
from .primitives import ImagePrim as PImage
from .primitives import Line as PLine
from .primitives import Markers as PMarkers
from .primitives import Path as PPath
from .primitives import PolygonBatch as PPolyBatch
from .primitives import Rect as PRect
from .primitives import Segments as PSegments
from .ticker import format_ticks, log_ticks, minor_ticks, nice_ticks
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
    fig._settle_layout()
    dpi = fig.style.dpi
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi

    defs: list[str] = []
    body: list[str] = []

    for i, ax in enumerate(fig.axes):
        _render_axes(ax, fig, W, H, i, defs, body)

    _render_figtexts(fig, W, H, body)
    _render_figure_legend(fig, fig.style, W, H, body)
    _render_groups(fig, W, H, body)

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
    for t in fig._fig_texts:
        _render_fig_text(t, st, W, H, body)


_HA_ANCHOR = {"left": "start", "center": "middle", "right": "end"}
# Baseline offsets approximating each va, matching the vertical-centering trick
# already used for tick labels (y + fs*0.35) rather than true font metrics.
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
    """
    top = _group_top_clearance(ax, st)
    bottom = left = right = 0.0
    if not ax._axis_off:
        xdec = st.tick_size + st.tick_label_size + 4
        if ax._xlabel:
            xdec += st.label_size + 6
        if ax._xtick_side == "top":
            top += xdec
        else:
            bottom += xdec
        ydec = st.tick_size + _max_ytick_width(ax, st) + 4
        if ax._ylabel:
            ydec += st.label_size + 6
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
    _, _, tlabels = colorbar_ticks(cax._cbar_source.norm)
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
    """
    st = fig.style
    for g in fig._groups:
        members = g["axes"] + _group_colorbars(g["axes"], fig)
        rects = [_pixel_rect(ax, W, H) for ax in members]
        extras = [_group_colorbar_extra(ax, st) if ax._is_colorbar
                 else _group_axes_extra(ax, st) for ax in members]
        pad_l, pad_r, pad_t, pad_b = g["pad"]
        x0 = min(r[0] - e[2] for r, e in zip(rects, extras)) - pad_l
        y0 = min(r[1] - e[0] for r, e in zip(rects, extras)) - pad_t
        x1 = max(r[0] + r[2] + e[3] for r, e in zip(rects, extras)) + pad_r
        y1 = max(r[1] + r[3] + e[1] for r, e in zip(rects, extras)) + pad_b
        dash = _DASH.get(g["linestyle"])
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        body.append(
            f'<rect x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(x1 - x0)}" '
            f'height="{_fmt(y1 - y0)}" fill="none" stroke="{g["color"]}" '
            f'stroke-width="{g["linewidth"]}"{dash_attr}/>'
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


def axes_metadata(fig, idx_of=None):
    """Per-axes pixel rect + data limits, for client-side point picking.

    Keyed by the axes index (matching the ``s<index>_<k>`` ids on rendered
    series). Colorbar axes are excluded -- they are not data plots. So is a
    3-D axes: pan/zoom/point-pick all reason about one affine map between a
    *fixed* data range and pixels, but a 3-D axes' "data" is already a
    camera-projected snapshot at a specific elev/azim -- zooming it stretches
    the projection into a shape no real camera angle produces, and a picked
    point reports meaningless projected coordinates instead of the original
    (x, y, z). Leaving it out of this payload is what makes ``axesAt()`` (the
    JS hit-test) treat the whole 3-D panel as outside any interactive axes,
    so the toolbar simply does nothing there instead of producing a wrong
    answer. The panel itself still renders fully -- this only affects
    interactivity in the HTML export.

    ``idx_of`` (an ``id(axes) -> index`` map) is accepted rather than always
    rebuilt -- see :func:`layout_metadata`, which needs the identical map and
    would otherwise redo this same O(axes) dict build a second time in the
    same ``to_html()`` call.
    """
    dpi = fig.style.dpi
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi
    if idx_of is None:
        idx_of = {id(a): i for i, a in enumerate(fig.axes)}
    meta = {}
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar or not ax._visible or ax._is_3d:
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
            # None (omitted from the client's perspective via the JS ?? below)
            # unless grid(alpha=...) actually overrode the figure-wide
            # default, mirroring tick_style's "only present when overridden"
            # convention -- see the tick_params() regression this pattern
            # already fixed: a per-axes style that only applied to the
            # initial render, then silently reverted on the client's own
            # pan/zoom rebuild, which reads only the figure-wide style.
            "grid_alpha": ax._grid_alpha,
            "xscale": ax._xscale, "yscale": ax._yscale,
            # Axis direction, so the client maps data<->pixels the same way
            # _render_axes does (it swaps the limits it feeds the transform).
            "xinv": bool(ax._xinverted), "yinv": bool(ax._yinverted),
            # Whether ticks are user-fixed (don't auto-recompute on zoom) --
            # explicit *minor* ticks count too: without this, an explicit
            # set_xticks(vals, minor=True) would render correctly here but
            # silently revert to the auto minor-tick algorithm the moment a
            # reader zoomed, the same regression class already fixed once for
            # tick_params() and once for grid(alpha=) (see grid_alpha above).
            "xfixed": ax._xticks is not None or ax._xticks_minor is not None,
            "yfixed": ax._yticks is not None or ax._yticks_minor is not None,
            "xside": ax._xtick_side, "yside": ax._ytick_side,
            "minor": bool(ax._minor_ticks_on),
            # Raw tick_params() overrides (Style field -> value), so the
            # client's pan/zoom tick-rebuild can reproduce a per-axis style
            # instead of always falling back to the figure-wide default --
            # only present when this axes actually has an override, to keep
            # the common (unstyled) case's payload as small as before.
            "tick_style": {
                "x": ax._tick_overrides["x"] or None,
                "y": ax._tick_overrides["y"] or None,
                "xminor": ax._minor_tick_overrides["x"] or None,
                "yminor": ax._minor_tick_overrides["y"] or None,
            },
            # Surfaced on extracted points as axes_title (falling back to a
            # generated "axes N" when untitled), so a multi-panel export
            # always identifies which panel a marker came from by name
            # instead of just a bare index.
            "title": ax._title,
            # Also surfaced on every extracted record, so a value pulled out
            # of context (a CSV row, a JSON dict) still carries what its x/y
            # and any color-encoded value actually mean, not just bare numbers.
            "xlabel": ax._xlabel, "ylabel": ax._ylabel,
            "zlabel": _colorbar_label(ax, fig),
            # Which fig.group() box(es) this axes belongs to, if any -- joined
            # with ", " on the rare figure where an axes was added to more
            # than one group, empty when it belongs to none. Lets a picked
            # record from a clustered panel say which cluster it came from,
            # the same way axes_title says which panel.
            "group": ", ".join(g["title"] for g in fig._groups if ax in g["axes"]),
            # False excludes this axes from Point Picking --
            # see Axes.set_pickable.
            "pickable": bool(ax._pickable),
            # Arbitrary user-supplied key/value pairs merged onto every pick
            # record from this axes -- see Axes.set_pick_context.
            "context": dict(ax._pick_context),
            # A twin/secondary axes fully overlaps its parent's pixel rect, so
            # they can never both be reached by a click -- the client instead
            # resolves one and propagates the limit change to the other(s)
            # here, keeping their views in sync. `None` when there is no link,
            # or when the linked axes isn't itself in this payload (e.g. it
            # was hidden) -- see `_interactive.py`'s `syncLinked`.
            "twin_of": idx_of.get(id(ax._twin_of)) if ax._twin_of is not None else None,
            "twin_shared": ax._twin_shared,
            "secondary_of": (idx_of.get(id(ax._secondary_of))
                             if ax._secondary_of is not None else None),
            "secondary_dim": ax._secondary_dim,
        }
    return meta


def layout_metadata(fig, idx_of=None):
    """Grid shape/position of every subplot-grid axes, plus ``fig.group()``
    boxes -- everything ``load_data()``'s ``"layout"`` needs to rebuild an
    equivalent figure structure with :func:`plotpress.subplots_from_layout`,
    independent of ``axes_metadata()``'s per-axes pixel/style payload above.

    ``idx_of`` (an ``id(axes) -> index`` map) is accepted rather than always
    rebuilt, so a caller that already has one -- ``to_html()`` builds one for
    :func:`axes_metadata` moments before calling this -- doesn't pay for the
    same O(axes) dict twice in the same save.

    Only axes placed via :meth:`Figure.add_subplot`/:meth:`Figure.subplots`
    (``ax._subplotspec is not None``) end up in ``"axes"`` -- a freeform
    :meth:`Figure.add_axes` rect has no grid cell to recover, so it is
    simply absent from the payload rather than guessed at; its index is
    still recorded in ``"omitted_axes"`` (colorbars excluded -- they were
    never expected to round-trip) so :func:`plotpress.subplots_from_layout`
    can warn that a real, once-visible axes won't come back, instead of the
    drop passing without any signal beyond the payload simply being smaller.
    """
    if idx_of is None:
        idx_of = {id(a): i for i, a in enumerate(fig.axes)}
    axes = {}
    omitted = []
    for i, ax in enumerate(fig.axes):
        spec = ax._subplotspec
        if spec is None:
            if not ax._is_colorbar:
                omitted.append(i)
            continue
        axes[i] = {
            "nrows": spec.nrows, "ncols": spec.ncols,
            "row0": spec.row0, "row1": spec.row1,
            "col0": spec.col0, "col1": spec.col1,
            # None for a plain Cartesian axes, so a round trip through
            # add_subplot(..., projection=...) reproduces it exactly.
            "projection": ("polar" if getattr(ax, "_is_polar", False)
                          else "3d" if ax._is_3d else None),
        }
    groups = [
        {
            "title": g["title"],
            "axes": [idx_of[id(a)] for a in g["axes"] if id(a) in idx_of],
            "linestyle": g["linestyle"], "color": g["color"],
            "linewidth": g["linewidth"], "title_position": g["title_position"],
            "pad": list(g["pad"]), "fontsize": g["fontsize"],
        }
        for g in fig._groups
    ]
    return {"figsize": list(fig.figsize), "axes": axes, "groups": groups,
           "omitted_axes": omitted}


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


def _downsample_grid(z, max_cells):
    """Block-average ``z`` down to at most ``max_cells`` cells.

    A mesh/contour too large to embed at full resolution used to be dropped
    from the pick payload entirely, so a click reported bare x/y with no data
    value -- exactly the case a "third dimension" plot type exists for.
    Block-averaging keeps every pick answerable (a real, spatially
    representative value) while still bounding the embedded HTML size,
    mirroring how huge line series are min/max-decimated before embedding
    rather than dropped (see primitives._decimate_minmax).
    """
    ny, nx = z.shape
    if ny * nx <= max_cells:
        return z
    factor = math.ceil(math.sqrt((ny * nx) / max_cells))
    new_ny = max(1, math.ceil(ny / factor))
    new_nx = max(1, math.ceil(nx / factor))
    pad_ny, pad_nx = new_ny * factor - ny, new_nx * factor - nx
    zp = np.pad(z, ((0, pad_ny), (0, pad_nx)), mode="edge")
    blocked = zp.reshape(new_ny, factor, new_nx, factor)
    # A block that's entirely NaN (masked/missing data, e.g. land in an ocean
    # field) is a real, expected input -- nanmean's "Mean of empty slice"
    # warning about it is noise, not a bug to surface on every such figure.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmean(blocked, axis=(1, 3))


def _curvilinear_centers(X, Y, ny, nx):
    """Each cell's center: the average of its 4 corner nodes.

    ``X``/``Y`` are the ``(ny+1, nx+1)``-ish node grid a curvilinear mesh
    scan-converts from (see ``QuadMesh._rgba_curvilinear``); a warped mesh has
    no separable 1-D edge vectors the way a rectilinear one does, so picking
    it needs an explicit per-cell coordinate instead.
    """
    cx = (X[:ny, :nx] + X[:ny, 1:nx + 1] + X[1:ny + 1, :nx] + X[1:ny + 1, 1:nx + 1]) / 4.0
    cy = (Y[:ny, :nx] + Y[:ny, 1:nx + 1] + Y[1:ny + 1, :nx] + Y[1:ny + 1, 1:nx + 1]) / 4.0
    return cx, cy


def _quadmesh_pick_entry(art, max_mesh_cells, precision):
    """The geometry + z data pick_data() embeds for one plain QuadMesh.

    Factored out so a FrameQuadMesh can reuse it once per frame (see
    frame_data()) instead of duplicating this branch -- every frame shares
    one X/Y grid, so only C differs, but each frame still needs its own
    downsampled z at whatever cell the click lands in.
    """
    def _round_list(a):
        return _rl(a, precision)

    grid = art.C
    curvilinear = art.curvilinear
    if curvilinear:
        ny0 = min(grid.shape[0], art.X.shape[0] - 1)
        nx0 = min(grid.shape[1], art.X.shape[1] - 1)
        grid = grid[:ny0, :nx0]
    else:
        ny0, nx0 = grid.shape
    xmin, xmax, ymin, ymax = art.extent()
    z = _downsample_grid(grid, max_mesh_cells)
    ny, nx = z.shape
    entry = {
        "extent": [round(xmin, 6), round(xmax, 6), round(ymin, 6), round(ymax, 6)],
        "shape": [int(ny), int(nx)],
        "z": _round_list(z),
        "name": "z",
        "curvilinear": bool(curvilinear),
    }
    if curvilinear:
        cx, cy = _curvilinear_centers(art.X, art.Y, ny0, nx0)
        if (ny, nx) != (ny0, nx0):
            cx, cy = _downsample_grid(cx, max_mesh_cells), _downsample_grid(cy, max_mesh_cells)
        entry["xc"], entry["yc"] = _round_list(cx), _round_list(cy)
    else:
        if (ny, nx) == (ny0, nx0):
            xe, ye = art.cell_edges()
        else:
            xe = np.linspace(xmin, xmax, nx + 1)
            ye = np.linspace(ymin, ymax, ny + 1)
        entry["xedges"], entry["yedges"] = _round_list(xe), _round_list(ye)
    return entry


def pick_data(fig, max_points=20000, max_mesh_cells=60000, precision=6):
    """Per-axes data payload for point picking (values incl. z and beyond).

    For point series (line/scatter) embeds x, y and any extra named dimensions
    (``pick_values`` such as ``c`` or ``z``). For meshes/contours embeds the z
    grid so a clicked cell reports its value -- block-averaged down to
    ``max_mesh_cells`` for a grid over the cap, so even a huge mesh always
    answers a pick with a real value instead of falling back to a bare x/y
    readout. Point series over ``max_points`` are still omitted outright (that
    fallback -- nearest-vertex geometry -- has no missing-value problem to
    solve), so the HTML stays lean.

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
        if ax._is_colorbar or not ax._visible or ax._is_3d:
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
                # cell under the cursor (arrow keys step cell-by-cell). A grid
                # over the cap is downsampled, not dropped -- see
                # _downsample_grid. `art.x`/`art.y` are sample coordinates
                # (matplotlib contour explicitly allows non-uniform spacing),
                # not necessarily evenly spaced, so the client needs the real
                # cell boundaries -- not "shape cells spanning the extent
                # evenly", which was silently wrong for any non-uniform grid
                # (and subtly off even for a uniform one, by treating point
                # samples as if they were cells).
                ny0, nx0 = art.Z.shape
                z = _downsample_grid(art.Z, max_mesh_cells)
                ny, nx = z.shape
                xmin, xmax = float(art.x.min()), float(art.x.max())
                ymin, ymax = float(art.y.min()), float(art.y.max())
                entry = {
                    "extent": [round(xmin, 6), round(xmax, 6),
                               round(ymin, 6), round(ymax, 6)],
                    "shape": [int(ny), int(nx)],
                    "z": _round_list(z),  # row 0 = ymin, like QuadMesh
                    "name": "z",
                }
                if (ny, nx) == (ny0, nx0):
                    # Edges (for bucketing a click into the right sample's
                    # Voronoi-like span) and the exact sample coordinates
                    # (for display) are different things here: unlike a true
                    # mesh cell, a contour sample's own coordinate generally
                    # isn't the midpoint between its implied edges once the
                    # spacing is non-uniform, so reporting the edge midpoint
                    # would label the point with a value that isn't in the
                    # data.
                    entry["xedges"] = _round_list(_edges_from(art.x, nx))
                    entry["yedges"] = _round_list(_edges_from(art.y, ny))
                    entry["xcoord"] = _round_list(art.x)
                    entry["ycoord"] = _round_list(art.y)
                else:
                    entry["xedges"] = _round_list(np.linspace(xmin, xmax, nx + 1))
                    entry["yedges"] = _round_list(np.linspace(ymin, ymax, ny + 1))
                meshes.append(entry)
            elif isinstance(art, FillBetween):
                if 0 < art.x.size <= max_points:
                    hi = np.maximum(art.y1, art.y2)
                    lo = np.minimum(art.y1, art.y2)
                    series.append({"kind": "fill", "x": _round_list(art.x),
                                   "y": _round_list(hi),           # snap to band top
                                   "vals": {"lower": _round_list(lo)}})
            elif isinstance(art, Polygon):
                if 0 < art.x.size <= max_points:
                    series.append({"kind": "polygon", "x": _round_list(art.x),
                                   "y": _round_list(art.y), "vals": {}})
            elif isinstance(art, LineCollection):
                segs = art.segments
                if 0 < len(segs) <= max_points:
                    # One pickable point per segment, at its midpoint -- vals
                    # carry the full span so hlines/vlines report where the
                    # line actually starts and ends, not just where it was
                    # clicked along its length.
                    x0, y0, x1, y1 = segs[:, 0], segs[:, 1], segs[:, 2], segs[:, 3]
                    series.append({"kind": "lines",
                                   "x": _round_list((x0 + x1) / 2.0),
                                   "y": _round_list((y0 + y1) / 2.0),
                                   "vals": {"x0": _round_list(x0), "x1": _round_list(x1),
                                            "y0": _round_list(y0), "y1": _round_list(y1)}})
            elif isinstance(art, PolyCollection):
                n = len(art.verts)
                if 0 < n <= max_points:
                    # One pickable point per polygon, at its centroid -- vals
                    # carry its bounding box (broken_barh's rectangles) and,
                    # when present, the raw per-polygon value a colormap was
                    # built from (hexbin's counts -- the facecolors array
                    # alone has already thrown that number away).
                    cx = np.array([v[:, 0].mean() for v in art.verts])
                    cy = np.array([v[:, 1].mean() for v in art.verts])
                    vals = {
                        "xmin": _round_list([v[:, 0].min() for v in art.verts]),
                        "xmax": _round_list([v[:, 0].max() for v in art.verts]),
                        "ymin": _round_list([v[:, 1].min() for v in art.verts]),
                        "ymax": _round_list([v[:, 1].max() for v in art.verts]),
                    }
                    counts = getattr(art, "counts", None)
                    if counts is not None and len(counts) == n:
                        vals["count"] = _round_list(counts)
                    series.append({"kind": "poly", "x": _round_list(cx),
                                   "y": _round_list(cy), "vals": vals})
            elif isinstance(art, (QuadMesh, Image)):
                is_img = isinstance(art, Image)
                if is_img and art.A.ndim != 2:
                    continue  # RGB image: no scalar to report
                grid = art.A if is_img else art.C
                curvilinear = isinstance(art, QuadMesh) and art.curvilinear
                if curvilinear:
                    # A curvilinear mesh's node arrays have no fixed size
                    # contract with C beyond "at least as large" -- X/Y the
                    # same shape as C (centers, not corners) is common and
                    # valid. _rgba_curvilinear clamps to however many whole
                    # cells the two actually provide together; picking has to
                    # match that exactly, or _curvilinear_centers indexes
                    # X/Y past their real width and numpy's elementwise add
                    # raises a shape-mismatch error building the centers.
                    ny0 = min(grid.shape[0], art.X.shape[0] - 1)
                    nx0 = min(grid.shape[1], art.X.shape[1] - 1)
                    grid = grid[:ny0, :nx0]
                else:
                    ny0, nx0 = grid.shape
                xmin, xmax, ymin, ymax = art.extent()
                # Store z row-major with row 0 = ymin so a clicked cell maps back.
                z0 = np.flipud(grid) if (is_img and art.origin == "upper") else grid
                # A grid over the cap is downsampled, not dropped -- a click
                # still answers with a real (if coarser) value instead of
                # falling back to a bare x/y readout. See _downsample_grid.
                z = _downsample_grid(z0, max_mesh_cells)
                ny, nx = z.shape
                entry = {
                    "extent": [round(xmin, 6), round(xmax, 6),
                               round(ymin, 6), round(ymax, 6)],
                    "shape": [int(ny), int(nx)],
                    "z": _round_list(z),
                    "name": "z",
                    "curvilinear": bool(curvilinear),
                }
                if curvilinear:
                    # No separable 1-D edges on a warped grid -- picking
                    # matches the click to the nearest cell *center* instead
                    # of bucketing it into a rectangular extent division
                    # (which was wrong: it reported whichever cell the click
                    # fell into on a *uniform* grid overlaid on the extent,
                    # unrelated to where the warped cells actually are).
                    cx, cy = _curvilinear_centers(art.X, art.Y, ny0, nx0)
                    if (ny, nx) != (ny0, nx0):
                        cx, cy = _downsample_grid(cx, max_mesh_cells), _downsample_grid(cy, max_mesh_cells)
                    entry["xc"], entry["yc"] = _round_list(cx), _round_list(cy)
                else:
                    # Non-uniform rectilinear spacing (matplotlib explicitly
                    # allows uneven pcolormesh edges) needs the real
                    # boundaries too -- an evenly-divided extent silently
                    # picked the wrong cell for anything but a uniform grid.
                    if (ny, nx) == (ny0, nx0) and not is_img:
                        xe, ye = art.cell_edges()
                    else:
                        # Downsampling coarsens to a uniform block grid, and a
                        # plain Image is already a uniform raster over its
                        # extent -- an evenly spaced division is exact here,
                        # not an approximation.
                        xe = np.linspace(xmin, xmax, nx + 1)
                        ye = np.linspace(ymin, ymax, ny + 1)
                    entry["xedges"], entry["yedges"] = _round_list(xe), _round_list(ye)
                meshes.append(entry)
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
        _render_colorbar(ax, tr, *alloc, clip_id, body)
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

    xticks = (ax._xticks if ax._xticks is not None else
              (log_ticks(xmin, xmax) if ax._xscale == "log" else nice_ticks(xmin, xmax)))
    yticks = (ax._yticks if ax._yticks is not None else
              (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))

    # Grid + ticks live in one group so client-side per-axes zoom can rebuild
    # them from new limits (see _interactive.py).
    body.append(f'<g id="ticks{index}">')
    if ax._grid and not ax._axis_off and not overlay:
        grid_alpha = ax._grid_alpha if ax._grid_alpha is not None else st.grid_alpha
        _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body,
                    grid_alpha)
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
            xlabels = _resolve_tick_labels(ax._xticklabels, xticks) if is_x else []
            ylabels = _resolve_tick_labels(ax._yticklabels, yticks) if not is_x else []
            _render_ticks(xst, yst, tr, xticks if is_x else [], yticks if not is_x else [],
                          xlabels, ylabels, px_left, px_top, px_w, px_h, body,
                          xside=ax._xtick_side, yside=ax._ytick_side)
        else:
            xlabels = _resolve_tick_labels(ax._xticklabels, xticks)
            ylabels = _resolve_tick_labels(ax._yticklabels, yticks)
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
            _render_bars(artist, tr, index, k, body)
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


# -- artists ---------------------------------------------------------------
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
    """Markers as zero-length round-capped strokes -> circular dots.

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


def _emit_prim(p) -> str:
    """Serialize one backend-agnostic primitive to an SVG element."""
    if isinstance(p, PImage):
        uri = png_data_uri(p.rgba)
        style = "" if p.smooth else ' style="image-rendering:pixelated"'
        # class/data-label match every other series (see _emit_prim's PLine/PRect
        # branches below) so the legend's click-to-hide toggle -- which matches
        # on .plotpress-series + data-label -- can find a raster mesh/image the
        # same way it already finds a vectorized one.
        return (f'<image class="plotpress-series" data-label="{_esc(p.label)}" '
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
        if p.element == "polygon":
            pts = p.subpaths[0]
            coords = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in pts
                              if np.isfinite([x, y]).all())
            stroke = (f'stroke="{p.stroke}" stroke-width="{p.stroke_width}"'
                      if p.stroke else 'stroke="none"')
            return (f'<polygon class="plotpress-series"{idattr} data-label="{lbl}" '
                    f'points="{coords}" fill="{p.fill}" '
                    f'fill-opacity="{p.fill_opacity}" {stroke}/>')
        d = _path_d(p.subpaths, p.closed)
        if p.fill and not p.stroke:
            return (f'<path class="plotpress-series"{idattr} data-label="{lbl}" '
                    f'd="{d}" fill="{p.fill}" fill-opacity="{p.fill_opacity}" '
                    f'stroke="none"/>')
        attrs = (f'fill="none" stroke="{p.stroke}" stroke-width="{p.stroke_width}" '
                 f'stroke-linejoin="round" stroke-linecap="round"')
        dash = _DASH.get(p.linestyle)
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        if p.stroke_opacity < 1:
            attrs += f' stroke-opacity="{p.stroke_opacity}"'
        return (f'<path class="plotpress-series"{idattr} data-label="{lbl}" '
                f'd="{d}" {attrs}/>')
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
    body.append(
        f'<image class="plotpress-series plotpress-framemesh" id="s{ai}_{k}" '
        f'data-label="{label}" x="{_fmt(p.x)}" y="{_fmt(p.y)}" '
        f'width="{_fmt(p.w)}" height="{_fmt(p.h)}" preserveAspectRatio="none" '
        f'style="image-rendering:pixelated" href="{uri}"/>'
    )


def frame_data(fig, max_mesh_cells=60000):
    """Per-axes slider-frame data for JS to redraw on scrub: all frames' x/Y
    for a line, or every frame's rendered image (for JS to swap in) plus its
    z grid (for picking) for a mesh.
    """
    frames = {}
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar:
            continue
        entries = []
        tr = None  # built lazily: only a FrameQuadMesh needs it, and every
                   # frame of one shares an X/Y grid, so once per axes suffices.
        for k, art in enumerate(ax.artists):
            if isinstance(art, FrameLine2D):
                shared = art.X.ndim == 1
                entry = {"id": f"s{i}_{k}", "unit": art.slider_unit,
                         "shared_x": bool(shared)}
                if shared:
                    entry["x"] = _round_list(art.X)
                else:
                    entry["x"] = [_round_list(art.X[f]) for f in range(art.n_frames)]
                entry["Y"] = [_round_list(art.Y[f]) for f in range(art.n_frames)]
                entries.append(entry)
            elif isinstance(art, FrameQuadMesh):
                if tr is None:
                    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
                    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
                    px_left, px_top, px_w, px_h = _effective_rect(
                        ax, *_pixel_rect(ax, W, H), (xmin, xmax), (ymin, ymax))
                    xlim_t = (xmax, xmin) if ax._xinverted else (xmin, xmax)
                    ylim_t = (ymax, ymin) if ax._yinverted else (ymin, ymax)
                    tr = LinearTransform(xlim_t, ylim_t, (px_left, px_top, px_w, px_h),
                                         xscale=ax._xscale, yscale=ax._yscale)
                hrefs, zs, geom = [], [], None
                for f in range(art.n_frames):
                    fm = art.frame_mesh(f)
                    mesh_prims = artist_to_prims(fm, tr, i, k)
                    hrefs.append(png_data_uri(mesh_prims[0].rgba) if mesh_prims else "")
                    # Every frame shares one X/Y grid (see FrameQuadMesh's own
                    # docstring), so the geometry half of the pick entry --
                    # extent/shape/edges or curvilinear centers -- is identical
                    # frame to frame; keep it once instead of repeating it
                    # n_frames times, and collect only the part that actually
                    # varies (z) into its own per-frame list.
                    entry = _quadmesh_pick_entry(fm, max_mesh_cells, precision=6)
                    zs.append(entry.pop("z"))
                    if geom is None:
                        geom = entry
                mesh_entry = {"id": f"s{i}_{k}", "unit": art.slider_unit,
                              "hrefs": hrefs, "z": zs}
                if geom is not None:
                    mesh_entry.update(geom)
                entries.append(mesh_entry)
        if entries:
            frames[i] = entries
    return frames


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

    body.append(
        f'<g class="plotpress-series" id="s{ai}_{k}" data-label="{label}"{op}>'
        f'{"".join(rects.tolist())}</g>'
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
            y0, y1 = tr.y_base(ba), tr.y_base(ba + ln)
        else:
            y0, y1 = tr.y(p - th / 2), tr.y(p + th / 2)
            x0, x1 = tr.x_base(ba), tr.x_base(ba + ln)
        rx, ry = min(x0, x1), min(y0, y1)
        rects.append(
            f'<rect x="{_fmt(rx)}" y="{_fmt(ry)}" width="{_fmt(abs(x1 - x0))}" '
            f'height="{_fmt(abs(y1 - y0))}" fill="{bars.colors[i]}"{edge}/>'
        )
    body.append(
        f'<g class="plotpress-series" id="s{ai}_{k}" data-label="{label}"{op}>'
        f'{"".join(rects)}</g>'
    )


def _render_stem(stem: Stem, tr, st, fig, body):
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
    if eb.yerr is not None:
        # An error bar reaching below zero on a log axis has no pixel to land
        # on; clamp the whisker to the frame rather than emitting NaN, which
        # drops the whole bar and quietly understates the uncertainty.
        ylo, yhi = tr.y_base(eb.y - eb.yerr), tr.y_base(eb.y + eb.yerr)
        for x, a, b in zip(xb, ylo, yhi):
            whiskers.append(f'<line x1="{_fmt(x)}" y1="{_fmt(a)}" x2="{_fmt(x)}" y2="{_fmt(b)}"/>')
            caps.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(a)}" x2="{_fmt(x + cap)}" y2="{_fmt(a)}"/>')
            caps.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(b)}" x2="{_fmt(x + cap)}" y2="{_fmt(b)}"/>')
    if eb.xerr is not None:
        xlo, xhi = tr.x_base(eb.x - eb.xerr), tr.x_base(eb.x + eb.xerr)
        for y, a, b in zip(yb, xlo, xhi):
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
    dots = [f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{_fmt(r)}" fill="{eb.color}"/>'
            for x, y in zip(xb, yb) if np.isfinite(x) and np.isfinite(y)]
    body.append("".join(dots))


def _render_pie(pie: Pie, tr, body):
    """Draw wedges in axes-pixel space so the pie stays circular."""
    cx = tr.px_left + tr.px_w / 2.0
    cy = tr.px_top + tr.px_h / 2.0
    R = 0.42 * min(tr.px_w, tr.px_h) * pie.radius
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
        am = (a0 + a1) / 2.0
        if pie.labels is not None:
            lx, ly = cx + 1.15 * R * math.cos(am), cy - 1.15 * R * math.sin(am)
            anchor = "start" if math.cos(am) >= 0 else "end"
            labels.append(
                f'<text x="{_fmt(lx)}" y="{_fmt(ly)}" text-anchor="{anchor}" '
                f'font-size="10" dominant-baseline="middle">{_esc(pie.labels[i])}</text>'
            )
        pct = pie.pct_text(frac)
        if pct is not None:
            px, py = cx + 0.6 * R * math.cos(am), cy - 0.6 * R * math.sin(am)
            labels.append(
                f'<text x="{_fmt(px)}" y="{_fmt(py)}" text-anchor="middle" '
                f'font-size="10" dominant-baseline="middle">{_esc(pct)}</text>'
            )
        ang = a1
    body.append("".join(parts) + "".join(labels))


_HA = {"left": "start", "center": "middle", "right": "end"}
_VA = {"baseline": "alphabetic", "bottom": "text-after-edge",
       "center": "central", "top": "hanging"}


#: How far a text anchor sits from the box corner, as a fraction of the box.
_HA_FRAC = {"left": 0.0, "center": -0.5, "right": -1.0}
_VA_FRAC = {"baseline": -0.78, "bottom": -1.0, "center": -0.5, "top": 0.0}

#: Per-line spacing for multi-line text -- text_box()'s block-height math and
#: _text_svg()'s tspan stepping both key off this; keep the two in sync.
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


#: How far a multi-line block's *first* line needs shifting from the anchor
#: point so the block as a whole (not just line one) lands where ``va`` says --
#: "top" already puts the block's top at the anchor via dominant-baseline
#: alone (line one just hangs from it, rest cascade below), and "baseline"
#: has no natural multi-line convention beyond "first line sits at the
#: anchor", so both are 0. "bottom"/"center" need the first line pulled up so
#: the *last* line's bottom, or the block's midpoint, lands on the anchor.
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
    tspans = "".join(
        f'<tspan x="{_fmt(x)}"{"" if i == 0 else f" dy=\"{_fmt(line_height)}\""}>'
        f'{_esc(ln)}</tspan>'
        for i, ln in enumerate(lines))
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
    # A boxed label is a "text box" the toolbar's Hide All toggle
    # (see _interactive.py's .plotpress-textbox rule) can hide alongside every
    # pin/annotation -- a plain unboxed label has no comparable "hide the
    # callout" reading, so it stays outside the group and always shows.
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
        arrow_color = (an.arrowprops.get("color", an.color)
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
    # Hide All can toggle off.
    if an.bbox is not None:
        body.append('<g class="plotpress-textbox">')
        body.append(_bbox_svg(box, an.bbox))
    body.append(_text_svg(tx, ty, an.text, an.color, an.size, an.ha, an.va,
                          0.0, an.outline, an.alpha, bold=an.bold, italic=an.italic))
    if an.bbox is not None:
        body.append("</g>")
    if cscale:
        body.append("</g>")


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
    for lvl, color, segs in ct.line_segments:
        if not segs:
            continue
        d = "".join(
            f"M{_fmt(tr.x(a))},{_fmt(tr.y(b))}L{_fmt(tr.x(c))},{_fmt(tr.y(e))}"
            for a, b, c, e in segs
        )
        body.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.2"{op}/>')


# -- axes furniture --------------------------------------------------------
def _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body,
                 alpha=None):
    lines = []
    for xt in xticks:
        x = tr.x(xt)
        lines.append(f'<line x1="{_fmt(x)}" y1="{_fmt(px_top)}" x2="{_fmt(x)}" y2="{_fmt(px_top + px_h)}"/>')
    for yt in yticks:
        y = tr.y(yt)
        lines.append(f'<line x1="{_fmt(px_left)}" y1="{_fmt(y)}" x2="{_fmt(px_left + px_w)}" y2="{_fmt(y)}"/>')
    body.append(
        f'<g stroke="{st.grid_color}" stroke-width="{st.grid_width}" '
        f'stroke-opacity="{st.grid_alpha if alpha is None else alpha}">'
        f'{"".join(lines)}</g>'
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


def _render_ticks(xst, yst, tr, xticks, yticks, xlabels, ylabels,
                  px_left, px_top, px_w, px_h, body,
                  xside="bottom", yside="left"):
    xts, xfs = xst.tick_size, xst.tick_label_size
    yts, yfs = yst.tick_size, yst.tick_label_size
    xmarks, ymarks, labels = [], [], []
    x_axis = px_top if xside == "top" else px_top + px_h
    xsign = -1 if xside == "top" else 1
    y_axis = px_left if yside == "left" else px_left + px_w
    ysign = -1 if yside == "left" else 1

    for xt, lab in zip(xticks, xlabels):
        x = tr.x(xt)
        xmarks.append(f'<line x1="{_fmt(x)}" y1="{_fmt(x_axis)}" x2="{_fmt(x)}" '
                      f'y2="{_fmt(x_axis + xsign * xts)}"/>')
        ly = x_axis + xsign * xts + (xfs if xside == "bottom" else -3)
        labels.append(
            f'<text x="{_fmt(x)}" y="{_fmt(ly)}" text-anchor="middle" '
            f'font-size="{xfs}" fill="{xst.text_color}">{_esc(lab)}</text>'
        )
    for yt, lab in zip(yticks, ylabels):
        y = tr.y(yt)
        ymarks.append(f'<line x1="{_fmt(y_axis)}" y1="{_fmt(y)}" '
                      f'x2="{_fmt(y_axis + ysign * yts)}" y2="{_fmt(y)}"/>')
        anchor = "end" if yside == "left" else "start"
        lx = y_axis + ysign * yts + (-2 if yside == "left" else 2)
        labels.append(
            f'<text x="{_fmt(lx)}" y="{_fmt(y + yfs * 0.35)}" text-anchor="{anchor}" '
            f'font-size="{yfs}" fill="{yst.text_color}">{_esc(lab)}</text>'
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
    x_axis = px_top if xside == "top" else px_top + px_h
    xsign = -1 if xside == "top" else 1
    y_axis = px_left if yside == "left" else px_left + px_w
    ysign = -1 if yside == "left" else 1

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
    cx = px_left + px_w / 2.0
    ts, fs = st.tick_size, st.tick_label_size
    if ax._xlabel and not ax._axis_off:
        if ax._xlabel_y_override is not None:
            y = ax._xlabel_y_override
        elif ax._xtick_side == "top":
            y = px_top - ts - fs - st.label_size
        else:
            y = px_top + px_h + ts + fs + st.label_size + 4
        body.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'font-size="{st.label_size}" fill="{st.text_color}">{_esc(ax._xlabel)}</text>'
        )
    if ax._ylabel and not ax._axis_off:
        cy = px_top + px_h / 2.0
        if ax._ylabel_x_override is not None:
            x, angle = ax._ylabel_x_override, -90
        elif ax._ytick_side == "right":
            x = px_left + px_w + ts + _max_ytick_width(ax, st) + st.label_size + 4
            angle = 90
        else:
            x = px_left - ts - _max_ytick_width(ax, st) - st.label_size - 4
            angle = -90
        body.append(
            f'<text x="{_fmt(x)}" y="{_fmt(cy)}" text-anchor="middle" '
            f'font-size="{st.label_size}" fill="{st.text_color}" '
            f'transform="rotate({angle} {_fmt(x)} {_fmt(cy)})">{_esc(ax._ylabel)}</text>'
        )
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
        if ax._xlabel:
            h += st.label_size + 6
    for other in ax.figure.axes:
        is_twiny = other._twin_of is ax and other._twin_shared == "y"
        is_secondary_top = (other._secondary_of is ax
                            and other._secondary_dim == "x"
                            and other._xtick_side == "top")
        if is_twiny or is_secondary_top:
            th = st.tick_size + st.tick_label_size + 4
            if other._xlabel:
                th += st.label_size + 6
            h = max(h, th)
    return h


def _max_ytick_width(ax, st):
    """Width of the widest y tick label, as drawn.

    Must mirror the tick selection the renderer uses -- explicit ``set_yticks``
    and ``set_yticklabels`` included -- or the y label gets placed on top of
    labels this never measured.
    """
    (_, _), (ymin, ymax) = ax._resolved_limits()
    ticks = (ax._yticks if ax._yticks is not None else
             (log_ticks(ymin, ymax) if ax._yscale == "log"
              else nice_ticks(ymin, ymax)))
    labels = _resolve_tick_labels(ax._yticklabels, ticks)
    return max((st.text_width(l, st.tick_label_size) for l in labels), default=0.0)


# loc name -> (fx, fy) fractions of the free space inside the axes: 0 = left/top.
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
            if label and label not in seen:
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
        [a for a in source if getattr(a, "label", None)],
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
    text_w = max(st.text_width(a.label, fs) for a in entries)
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


# Which figure edge a figure-level legend reserves space against. "center" and
# the corner placements overlay instead: there is no unambiguous edge to shrink
# away from, and matplotlib's fig.legend overlays for those too.
FIGURE_LEGEND_EDGE = {
    "lower center": "bottom", "upper center": "top",
    "right": "right", "center right": "right", "center left": "left",
}


def figure_legend_layout(fig):
    """Legend geometry for ``fig.legend()``, or ``None`` if nothing is labelled."""
    spec = fig._figure_legend
    if spec is None:
        return None
    sources = spec["axes"] or [a for a in fig.axes if not a._is_colorbar]
    return legend_box(legend_entries(sources), fig.style,
                      spec["ncol"], spec["title"], fontsize=spec.get("fontsize"),
                      framealpha=spec.get("framealpha", 0.85))


def figure_legend_origin(spec, lay, W, H, pad_px):
    """Top-left corner of the figure legend, in figure pixels."""
    edge = FIGURE_LEGEND_EDGE.get(spec["loc"])
    box_w, box_h = lay["box_w"], lay["box_h"]
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
    fx, fy = _LEGEND_ANCHORS.get(spec["loc"], (1.0, 0.0))
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
    _render_spines(ax, px_left, px_top, px_w, px_h, body)

    st = ax.style
    _, fracs, tlabels = colorbar_ticks(norm)
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
