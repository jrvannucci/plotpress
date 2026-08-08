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
    Annotation, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Image, Line2D, LineCollection, Pie, Polygon,
    PolyCollection, QuadMesh, Quiver, ScatterCollection, Span, Stem, Text,
    Violin, _edges_from,
)
from .colors import colorbar_ticks
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
    body.append(
        f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="{anchor}" '
        f'font-size="{size}" fill="{color}">{_esc(t["s"])}</text>'
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


def axes_metadata(fig):
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
    """
    dpi = fig.style.dpi
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi
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
            "xscale": ax._xscale, "yscale": ax._yscale,
            # Axis direction, so the client maps data<->pixels the same way
            # _render_axes does (it swaps the limits it feeds the transform).
            "xinv": bool(ax._xinverted), "yinv": bool(ax._yinverted),
            # Whether ticks are user-fixed (don't auto-recompute on zoom).
            "xfixed": ax._xticks is not None, "yfixed": ax._yticks is not None,
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
            # False excludes this axes from Point Pick/Annotate Point --
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

    if not ax._visible:
        return

    if ax._is_colorbar:
        _render_colorbar(ax, tr, *alloc, clip_id, body)
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
        _render_grid(st, tr, xticks, yticks, px_left, px_top, px_w, px_h, body)
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
                xminor = minor_ticks(xticks, xmin, xmax, ax._xscale)
                yminor = minor_ticks(yticks, ymin, ymax, ax._yscale)
                _render_minor_ticks(mxst, myst, tr, xminor, yminor,
                                    px_left, px_top, px_w, px_h, body,
                                    xside=ax._xtick_side, yside=ax._ytick_side)
    body.append("</g>")

    # Artists: fixed clip to the axes rect, then a transformable zoom group that
    # per-axes data zoom remaps via one affine (old limits -> new limits).
    body.append(f'<g clip-path="url(#{clip_id})"><g id="zoom{index}" class="plotpress-zoom">')
    for k, artist in enumerate(ax.artists):
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
            _render_annotation(artist, tr, st, body)
    body.append("</g></g>")   # close zoom group + clip group

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
    """Markers as zero-length round-capped strokes -> constant-size dots.

    With the zoom group's non-scaling stroke they stay circular and a constant
    pixel size under per-axes zoom, unlike a scaled ``<circle>``.
    """
    pts, diam = p.points, p.diameters
    finite = np.isfinite(pts).all(axis=1)
    op = f' stroke-opacity="{p.alpha}"' if p.alpha < 1 else ""
    idattr = f' id="{p.series_id}"' if p.series_id else ""

    def dot(cx, cy):
        return f"M{_fmt(cx)},{_fmt(cy)}L{_fmt(cx)},{_fmt(cy)}"

    parts = []
    same_size = diam.size and float(np.ptp(diam)) < 1e-9
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
    return (f'<g class="plotpress-series"{idattr} data-label="{_esc(p.label)}"{op}>'
            f'{"".join(parts)}</g>')


def _emit_prim(p) -> str:
    """Serialize one backend-agnostic primitive to an SVG element."""
    if isinstance(p, PImage):
        uri = png_data_uri(p.rgba)
        return (f'<image x="{_fmt(p.x)}" y="{_fmt(p.y)}" width="{_fmt(p.w)}" '
                f'height="{_fmt(p.h)}" preserveAspectRatio="none" '
                f'style="image-rendering:pixelated" href="{uri}"/>')
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


def frame_data(fig):
    """Per-axes slider-frame data for JS to redraw on scrub: all frames' x/Y
    for a line, or every frame's rendered image for JS to swap in for a mesh.
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
                hrefs = []
                for f in range(art.n_frames):
                    mesh_prims = artist_to_prims(art.frame_mesh(f), tr, i, k)
                    hrefs.append(png_data_uri(mesh_prims[0].rgba) if mesh_prims else "")
                entries.append({"id": f"s{i}_{k}", "unit": art.slider_unit,
                                "hrefs": hrefs})
        if entries:
            frames[i] = entries
    return frames


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
    bars, cap = [], eb.capsize
    if eb.yerr is not None:
        # An error bar reaching below zero on a log axis has no pixel to land
        # on; clamp the whisker to the frame rather than emitting NaN, which
        # drops the whole bar and quietly understates the uncertainty.
        ylo, yhi = tr.y_base(eb.y - eb.yerr), tr.y_base(eb.y + eb.yerr)
        for x, a, b in zip(xb, ylo, yhi):
            bars.append(f'<line x1="{_fmt(x)}" y1="{_fmt(a)}" x2="{_fmt(x)}" y2="{_fmt(b)}"/>')
            bars.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(a)}" x2="{_fmt(x + cap)}" y2="{_fmt(a)}"/>')
            bars.append(f'<line x1="{_fmt(x - cap)}" y1="{_fmt(b)}" x2="{_fmt(x + cap)}" y2="{_fmt(b)}"/>')
    if eb.xerr is not None:
        xlo, xhi = tr.x_base(eb.x - eb.xerr), tr.x_base(eb.x + eb.xerr)
        for y, a, b in zip(yb, xlo, xhi):
            bars.append(f'<line x1="{_fmt(a)}" y1="{_fmt(y)}" x2="{_fmt(b)}" y2="{_fmt(y)}"/>')
            bars.append(f'<line x1="{_fmt(a)}" y1="{_fmt(y - cap)}" x2="{_fmt(a)}" y2="{_fmt(y + cap)}"/>')
            bars.append(f'<line x1="{_fmt(b)}" y1="{_fmt(y - cap)}" x2="{_fmt(b)}" y2="{_fmt(y + cap)}"/>')
    if bars:
        body.append(f'<g stroke="{eb.color}" stroke-width="1">{"".join(bars)}</g>')
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


def text_box(x, y, text, size, ha, va, st):
    """Pixel bounding box ``(x0, y0, x1, y1)`` of a label drawn at ``(x, y)``.

    Measured with the same font metrics layout uses, so the box the leader
    attaches to is the box the glyphs actually occupy.
    """
    lines = text.split("\n")
    w = max((st.text_width(ln, size) for ln in lines), default=0.0)
    h = size * 1.25 * len(lines)
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


def _text_svg(x, y, text, color, size, ha, va, rotation=0.0, outline=None):
    anchor = _HA.get(ha, "start")
    baseline = _VA.get(va, "alphabetic")
    rot = (f' transform="rotate({_fmt(-rotation)} {_fmt(x)} {_fmt(y)})"'
           if rotation else "")
    # paint-order puts the halo stroke *under* the fill, so the glyph keeps its
    # shape and only gains a rim. Without it the stroke thickens every letter.
    halo = ("" if not outline else
            f' stroke="{outline}" stroke-width="{_fmt(size * 0.30)}" '
            'stroke-linejoin="round" paint-order="stroke"')
    return (f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="{anchor}" '
            f'dominant-baseline="{baseline}" font-size="{size}" '
            f'fill="{color}"{halo}{rot}>{_esc(text)}</text>')


def _render_text(t: Text, tr, body):
    body.append(_text_svg(float(tr.x(t.x)), float(tr.y(t.y)), t.text, t.color,
                          t.size, t.ha, t.va, t.rotation, t.outline))


def _render_annotation(an: Annotation, tr, st, body):
    tx, ty = float(tr.x(an.xytext[0])), float(tr.y(an.xytext[1]))
    if an.arrowprops is not None:
        px, py = float(tr.x(an.xy[0])), float(tr.y(an.xy[1]))
        color = (an.arrowprops.get("color", an.color)
                 if isinstance(an.arrowprops, dict) else an.color)
        # Start the leader at the edge of the text box nearest the target, not
        # at the text anchor -- from the anchor the line sets off across its own
        # label whenever the target is up and to the left of it.
        box = text_box(tx, ty, an.text, an.size, an.ha, an.va, st)
        sx, sy = leader_anchor(box, (px, py))
        ang = math.atan2(py - sy, px - sx)
        hl = 7.0
        h1 = (px - hl * math.cos(ang - 0.4), py - hl * math.sin(ang - 0.4))
        h2 = (px - hl * math.cos(ang + 0.4), py - hl * math.sin(ang + 0.4))
        body.append(
            f'<path d="M{_fmt(sx)},{_fmt(sy)} L{_fmt(px)},{_fmt(py)} '
            f'M{_fmt(px)},{_fmt(py)} L{_fmt(h1[0])},{_fmt(h1[1])} '
            f'M{_fmt(px)},{_fmt(py)} L{_fmt(h2[0])},{_fmt(h2[1])}" '
            f'fill="none" stroke="{color}" stroke-width="1.2"/>'
        )
    body.append(_text_svg(tx, ty, an.text, an.color, an.size, an.ha, an.va,
                          0.0, an.outline))


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
        body.append(
            f'<line x1="{_fmt(ex0)}" y1="{_fmt(ey0)}" x2="{_fmt(ex1)}" y2="{_fmt(ey1)}" '
            f'stroke="{color}" stroke-width="{width}"/>'
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
    """Compute legend geometry for an axes' own legend."""
    return legend_box(
        [a for a in ax.artists if getattr(a, "label", None)],
        st, ax._legend_ncol, ax._legend_title)


def legend_box(entries, st, ncol, title):
    """Compute legend geometry: entries, columns, cell size, box size."""
    if not entries:
        return None
    fs = st.tick_label_size
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
                      spec["ncol"], spec["title"])


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
