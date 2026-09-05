"""Export a Figure as a real Vega (not Vega-Lite) JSON specification.

Vega's marks sit close to plotpress's own pixel-space primitives (a `path`
mark takes a literal SVG path string per datum, an `image` mark takes an
explicit x/y/width/height + URL) -- much closer than Vega-Lite's declarative,
scale-driven encoding wants to be. That match is what this module leans on:
most artist kinds reuse ``primitives.artist_to_prims`` (the same pixel-space
conversion ``svg.py``/``raster.py`` already share) and translate each prim
into the matching frozen-pixel Vega mark, rather than re-deriving geometry
from data + scales the way a from-scratch Vega-Lite exporter would have to.

That's a deliberate trade-off, not an oversight: a mark built this way is
visually exact but *not* reactive to Vega's own zoom/pan signals or a
runtime domain change, the way a real ``field``/``scale``-encoded mark would
be. Line/scatter/bar charts -- the common case, and the one most likely to
actually get re-scaled by something downstream -- get genuine ``field`` +
``scale`` encoding instead, referencing real per-axes Vega ``scales``. Only
the primitive-reuse path gives up that reactivity, and it does so for marks
(filled regions, reference lines, meshes) that are as related to it -- glued
to Vega's raw drawing primitives, exactly the way plotpress's own raster
mesh path is glued to pixels -- as they would be in any other real Vega
spec that embeds a precomputed image or path.

One :class:`~plotpress.figure.Axes` becomes one Vega ``group`` mark with its
own local ``scales``/``axes``/``marks`` -- a closer structural fit for an
arbitrary subplot grid than Vega-Lite's ``hconcat``/``vconcat``/``facet``
composition, which wants homogeneous, data-driven faceting. A twin/secondary
axes is simply another group at the same pixel rect, the same way it
overlays in every other backend. That outer group is deliberately *not*
clipped -- its axis ticks/labels/title are Vega child marks drawn outside
the plot rectangle by design, the same way svg.py's own tick/label ``<g>``
sits outside its separate clip-pathed zoom ``<g>``. Only a nested inner
group, matching the outer one's size and holding just the data marks, is
clipped -- confirmed by actually rendering a spec through ``vg2png``, since
a clipped-away mark is simply absent from the output, not an error visible
from the JSON alone. :meth:`~plotpress.figure.Figure.group`'s own labeled
boxes are a different, figure-pixel-space case -- they can span several
axes at once, so each becomes a top-level ``rect``+``text`` mark pair,
sibling to the axes groups rather than nested in any one of them.

Not carried over, honestly: plotpress's own interactive toolbar (Pan/Zoom,
Point Picking, Annotate, Extract) has no Vega equivalent -- a Vega render of
this export is a static picture unless the caller wires up Vega's own
``signals``. 3-D has no Vega grammar either, but that is moot: plotpress has
none itself (see the ``Removed`` changelog entry). An artist kind with no
mapping here yet (``BoxPlot``, ``Violin``, ``Quiver``, ``Contour``,
``EventPlot``, ``Barbs``, ``Table``, and the slider-driven ``FrameLine2D``/
``FrameQuadMesh`` from ``plot_frames()``/``pcolormesh_frames()`` -- a static
JSON spec has nothing to scrub with) is skipped with a ``UserWarning``
naming it and the axes it was on, not silently dropped and not a hard
failure for the rest of the figure -- the same "degrade a part, not the
whole" choice ``pick_data()`` already makes for an oversized series. A
legend (axes- or figure-level) is the same story -- it needs real layout
(``svg.py``'s ``figure_legend_layout()``/``draw_legend()``) this module
doesn't build -- and warns the same way, naming which axes or the figure
has one.
"""

from __future__ import annotations

import math
import warnings

import numpy as np

from .artists import (
    Bars, ErrorBar, Line2D, Pie, QuadMesh, ScatterCollection, Stem, Text,
    Annotation, _VECTOR_CELL_LIMIT,
)
from .colors import Normalize, to_hex
from .png import png_data_uri
from .primitives import artist_to_prims
from .primitives import pie_center_radius, pie_label_positions
from .primitives import ImagePrim as PImage
from .primitives import Line as PLine
from .primitives import Markers as PMarkers
from .primitives import Path as PPath
from .primitives import PolygonBatch as PPolyBatch
from .primitives import Rect as PRect
from .primitives import Segments as PSegments
from .svg import (
    _axes_fraction_xy, _bbox_pad, _DASH, _effective_rect, _group_axes_extra,
    _group_colorbar_extra, _group_colorbars, _pixel_rect, leader_anchor, text_box,
)
from .transform import LinearTransform

_SCHEMA = "https://vega.github.io/schema/vega/v5.json"


def figure_to_vega(fig, mesh_data: bool = False) -> dict:
    """Build a Vega v5 spec (a plain ``dict`` -- ``json.dumps(...)`` it, or
    hand it straight to a Vega runtime that already accepts a Python object,
    e.g. IPython's ``vega`` MIME renderer) for ``fig``.

    One axes becomes one Vega ``group`` mark, positioned at that axes' own
    pixel rect within the figure (the same rect ``svg.py`` itself resolves,
    honoring ``set_aspect``/``set_box_aspect``) -- see the module docstring
    for what is and isn't drawn faithfully, and what "faithfully" means here
    (frozen pixel geometry for most marks, real scale-driven encoding for
    line/scatter/bar).

    ``mesh_data=True`` opts a ``pcolormesh``/mesh-backed ``imshow`` into
    real per-cell ``rect`` marks with a genuine field+scale color encoding,
    instead of the default rasterized ``image`` mark -- reactive and
    queryable, but only offered for meshes small/simple enough to stay
    cheap and unambiguous (see :func:`_mesh_data_reason`); everything else
    still gets the image mark, with a ``UserWarning`` naming why when
    ``mesh_data=True`` was requested but couldn't be honored for that mesh.
    """
    dpi = fig.style.dpi
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi
    # Marker/line-width sizes are stored in points; every other backend
    # converts to pixels via this same dpi/72 factor before treating them as
    # pixel measurements (svg.py:1054, raster.py:427) -- to_vega() must too,
    # or every marked figure exports markers ~1.4x too small at the default
    # dpi=100 (worse at higher dpi).
    size_scale = dpi / 72.0
    groups = []
    legend_axes = []
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar or not ax._visible:
            continue
        groups.append(_axes_to_group(ax, i, W, H, size_scale, fig.style, mesh_data))
        if ax._show_legend:
            legend_axes.append(i)
    # Figure-level chrome and Figure.group()'s labeled boxes are both
    # figure-pixel-space marks, siblings of the per-axes groups rather than
    # nested in any one of them -- drawn in the same order svg.py's own body
    # list uses (_render_figtexts, then _render_figure_legend, then
    # _render_groups, all after every _render_axes() call).
    groups.extend(_figtexts_to_vega_marks(fig, W, H))
    if legend_axes or fig._figure_legend is not None:
        # A legend needs real layout (handle geometry per artist kind,
        # column wrapping, an anchor box relative to loc/bbox_to_anchor) --
        # svg.py's figure_legend_layout()/draw_legend() -- that this module
        # doesn't build yet. Warning, not silently dropping, matches the
        # policy every other unmapped case in this file already follows.
        where = (["the figure"] if fig._figure_legend is not None else []) + \
                [f"axes {i}" for i in legend_axes]
        warnings.warn(
            f"figure_to_vega(): {', '.join(where)} has a legend, which "
            "to_vega() does not export yet -- skipped.",
            UserWarning, stacklevel=2,
        )
    groups.extend(_groups_to_vega_marks(fig, W, H))
    spec = {
        "$schema": _SCHEMA,
        "width": round(float(W), 2),
        "height": round(float(H), 2),
        "padding": 0,
        "background": to_hex(fig.style.facecolor),
        "marks": groups,
    }
    return _finalize(spec)


def _vega_has_content(spec) -> bool:
    """True if ``spec`` (from :func:`figure_to_vega`) has at least one real
    data mark somewhere in it.

    A figure built entirely from artist kinds this module has no mapping
    for yet (a lone ``boxplot()``/``violinplot()``/etc. example, say) still
    produces a spec -- axis chrome, a title -- with nothing behind it; the
    docs build (``docs/conf.py``) uses this to skip linking to a Vega
    export page for exactly those figures, per the module docstring's
    "skip a part, not the whole" policy for unsupported artists.
    """
    for m in spec.get("marks", []):
        if m.get("type") != "group":
            continue  # a Figure.group() box, not an axes -- never on its own
        for inner in m.get("marks", []):
            if inner.get("marks"):
                return True
    return False


def _axis_def(orient, scale_name, label, grid, custom_ticks, custom_labels, scales):
    """One entry for ``_axes_to_group``'s ``axes`` list.

    Also appends an ordinal label-lookup scale to ``scales`` (in place)
    when custom tick *labels* are set -- Vega's axis grammar has no direct
    "arbitrary string per tick position" property; mapping tick value to
    label string via a small ordinal scale, referenced from
    ``encode.labels``, is the standard way to express it.
    """
    axis = {"orient": orient, "scale": scale_name, "title": label or None,
            "grid": bool(grid), "domain": True}
    if custom_ticks is not None:
        ticks = list(custom_ticks)
        axis["values"] = [float(t) for t in ticks]
        # Custom *labels* only line up against custom tick *positions* --
        # resolving them against svg.py's own nice_ticks()/log_ticks()
        # auto-generated positions would mean reimplementing that ticking
        # algorithm here just to know which position gets which label, so
        # this only fires for the (overwhelmingly common) paired case.
        if custom_labels is not None:
            # svg.py's own _resolve_tick_labels() truncate/pad convention:
            # extra labels are dropped, missing ones render blank.
            labels = list(custom_labels)[:len(ticks)]
            labels += [""] * (len(ticks) - len(labels))
            label_scale = f"{scale_name}_labels"
            scales.append({"name": label_scale, "type": "ordinal",
                           "domain": [float(t) for t in ticks], "range": labels})
            axis["encode"] = {"labels": {"update": {
                "text": {"scale": label_scale, "field": "value"},
            }}}
    return axis


def _axes_to_group(ax, i, W, H, size_scale, st, mesh_data=False):
    alloc = _pixel_rect(ax, W, H)
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    px_left, px_top, px_w, px_h = _effective_rect(ax, *alloc, (xmin, xmax), (ymin, ymax))
    xlim_t = (xmax, xmin) if ax._xinverted else (xmin, xmax)
    ylim_t = (ymax, ymin) if ax._yinverted else (ymin, ymax)
    # Local origin (0, 0) -- artist_to_prims()' own pixel output becomes the
    # group's own local marks, positioned relative to the group itself
    # (encode.enter.x/y below), not the whole figure.
    tr_local = LinearTransform(xlim_t, ylim_t, (0.0, 0.0, px_w, px_h),
                               xscale=ax._xscale, yscale=ax._yscale)
    x_name, y_name = f"x{i}", f"y{i}"

    px_w, px_h = max(px_w, 0.0), max(px_h, 0.0)
    scales = [
        # Ascending domain, direction encoded in `range` instead -- Vega
        # scale domains are not guaranteed to preserve a manually descending
        # order (some scale types silently re-sort), so flipping the
        # *range* array is the unambiguous way to get a high-at-top y-axis
        # (and a high-at-left x-axis, if inverted).
        {"name": x_name, "type": "log" if ax._xscale == "log" else "linear",
         "domain": [xmin, xmax],
         "range": [px_w, 0] if ax._xinverted else [0, px_w], "zero": False},
        {"name": y_name, "type": "log" if ax._yscale == "log" else "linear",
         "domain": [ymin, ymax],
         "range": [0, px_h] if ax._yinverted else [px_h, 0], "zero": False},
    ]
    # Vega paints marks in list order, same as SVG paints elements in
    # document order -- draw by zorder (ties broken by insertion order),
    # exactly svg.py's own draw_order, or an artist added later but drawn
    # "underneath" (ax.fill_between(..., zorder=1) after a zorder=3 line)
    # would incorrectly paint over what it's meant to sit behind. `k` stays
    # each artist's ORIGINAL index (not its draw position) since primitives
    # builds series_id as f"s{ai}_{k}" -- the same id convention every other
    # backend uses. `scales` is built above (not after, the way it reads
    # more naturally) specifically so a mesh_data=True QuadMesh can append
    # its own color scale into it here, the same mutate-in-place convention
    # _axis_def already uses for a custom tick-label scale.
    marks = []
    draw_order = sorted(enumerate(ax.artists), key=lambda ka: (ka[1].zorder, ka[0]))
    for k, art in draw_order:
        marks.extend(_artist_to_vega_marks(art, tr_local, i, k, x_name, y_name,
                                           size_scale, st, mesh_data, scales, ax))
    # ax.pie() calls set_axis_off() (axes.py) precisely because a pie has no
    # x/y axis to show -- svg.py gates ticks/grid on this same flag
    # (svg.py:1001/1005). Omitting it entirely wrapped every pie (and any
    # ax.axis("off") panel) in a spurious 0..1 tick frame no to_svg() output
    # ever shows.
    axes_defs = [] if ax._axis_off else [
        _axis_def("bottom", x_name, ax._xlabel, ax._grid, ax._xticks, ax._xticklabels, scales),
        _axis_def("left", y_name, ax._ylabel, ax._grid, ax._yticks, ax._yticklabels, scales),
    ]
    return {
        "type": "group",
        "name": f"axes{i}",
        # NOT clipped: axis ticks/labels/titles and this group's own title
        # are Vega child marks drawn *outside* the plot rectangle by design
        # (the same way svg.py's own tick/label <g> sits outside its
        # separate clip-pathed zoom <g>) -- clipping this outer group cut
        # all of that away, discovered by actually rendering a spec with
        # every axis decoration through vg2png, not by inspecting the JSON.
        # `fill` paints the axes' own background (ax.get_facecolor()) --
        # a group's fill always renders under both its axes and its marks,
        # matching where svg.py paints this same rect (svg.py:987-991,
        # before ticks/grid/data are drawn at all). A twin/secondary axes
        # occupies the EXACT SAME pixel rect as its parent (twinx()/twiny()/
        # secondary_xaxis()/secondary_yaxis() all copy it verbatim) and is
        # drawn AFTER its parent in fig.axes order, so its own opaque
        # background would paint directly over the parent's already-drawn
        # content -- svg.py skips this rect entirely for exactly that
        # reason ("twins/secondaries overlay their parent, so neither draws
        # one", svg.py:985-987); this group must too, or a figure's
        # primary curve/bars vanish behind the twin's own blank background,
        # confirmed by actually rendering a twinx() figure through vg2png.
        "encode": {"enter": {
            "x": {"value": round(float(px_left), 2)},
            "y": {"value": round(float(px_top), 2)},
            "width": {"value": round(float(px_w), 2)},
            "height": {"value": round(float(px_h), 2)},
            **({} if (ax._twin_of is not None or ax._secondary_of is not None)
               else {"fill": {"value": _color(ax.get_facecolor(), "#ffffff")}}),
        }},
        "scales": scales,
        "axes": axes_defs,
        "title": ax._title or None,
        # The data marks alone live in an inner, clipped group at the same
        # local size -- clipping *just* this layer keeps a zoomed/panned or
        # inverted-limit series from overflowing into a neighboring axes,
        # without touching the chrome above, which resolves "x{i}"/"y{i}"
        # up through this nesting exactly like a promoted __data__ source
        # resolves up to the spec's top-level `data` (see _finalize).
        "marks": [{
            "type": "group",
            "name": f"axes{i}_data",
            "encode": {"enter": {
                "x": {"value": 0}, "y": {"value": 0},
                "width": {"value": round(float(px_w), 2)},
                "height": {"value": round(float(px_h), 2)},
                "clip": {"value": True},
            }},
            "marks": marks,
        }],
    }


# ---- artist -> Vega marks ---------------------------------------------

def _artist_to_vega_marks(art, tr, ai, k, x_name, y_name, size_scale, st,
                          mesh_data=False, scales=None, ax=None):
    # Real field/scale encoding for the common, high-value cases -- these
    # are the ones most worth staying reactive to a downstream domain
    # change, not just visually correct at export time. A Line2D with its
    # own per-vertex markers falls through to artist_to_prims() instead --
    # its marker-drawing already lives there, not worth reimplementing.
    if isinstance(art, ScatterCollection):
        return _scatter_marks(art, x_name, y_name, size_scale)
    if isinstance(art, Line2D) and art.marker is None:
        return _line_marks(art, x_name, y_name)
    if isinstance(art, Bars):
        return _bars_marks(art, x_name, y_name)
    if isinstance(art, ErrorBar):
        return _errorbar_marks(art, x_name, y_name, size_scale)
    if isinstance(art, Stem):
        return _stem_marks(art, x_name, y_name, size_scale, st)
    if isinstance(art, Pie):
        return _pie_marks(art, tr)
    if isinstance(art, (Text, Annotation)):
        return _text_marks(art, tr, st)
    if isinstance(art, QuadMesh):
        reason = _mesh_data_reason(art, mesh_data, ax)
        if reason is None:
            return _mesh_data_marks(art, x_name, y_name, scales)
        if mesh_data:
            warnings.warn(
                f"figure_to_vega(): axes {ai} requested mesh_data=True, but "
                f"this mesh has {reason} -- falling back to a rasterized "
                "image mark for it instead.",
                UserWarning, stacklevel=4,
            )
        # fall through to the generic artist_to_prims()/image-mark path below

    # Everything artist_to_prims() already shares with svg.py/raster.py --
    # frozen pixel geometry, see the module docstring for why. size_scale
    # (points -> pixels) matters here too: svg.py/raster.py always pass it
    # (svg.py:1054, raster.py:427) so a Line2D with its own marker, a
    # LineCollection, a Rug, etc. size correctly.
    prims = artist_to_prims(art, tr, ai, k, size_scale=size_scale)
    if prims is not None:
        marks = []
        for p in prims:
            marks.extend(_prim_to_vega(p))
        return marks

    warnings.warn(
        f"figure_to_vega(): axes {ai} has a {type(art).__name__} artist with "
        "no Vega mapping yet (box plots, violins, quiver, contour, "
        "event plots, wind barbs, tables, and plot_frames()/"
        "pcolormesh_frames() sliders aren't supported) -- skipped, "
        "the rest of the figure still exports.",
        UserWarning, stacklevel=4,
    )
    return []


def _symbol_size(diameter_px):
    """A Vega ``symbol`` mark's ``size`` channel is the shape's pixel *area*
    (``radius = sqrt(size / pi)`` for the default circle shape), not
    diameter squared -- ``diameter_px ** 2`` is the area of a *square* of
    that side length, which overstates a circle's actual area by ``4/pi``
    (~27%, ~13% too-large a rendered radius/diameter). This is the one
    formula every symbol-sized mark in this module should go through.
    """
    return math.pi * (diameter_px / 2.0) ** 2


def _dash_array(linestyle):
    """A Vega ``strokeDash`` array for a plotpress ``linestyle`` code, or
    ``None`` for a solid line -- the same ``_DASH`` lookup svg.py's own
    ``stroke-dasharray`` comes from (svg.py:37), just as a list of numbers
    (Vega's own array form) instead of a comma-joined SVG attribute string.
    """
    dash = _DASH.get(linestyle)
    return [float(n) for n in dash.split(",")] if dash else None


def _color(c, fallback="#1f77b4"):
    """Resolve a color to ``#rrggbb`` -- a name/hex string (``to_hex``), or a
    raw RGB(A) array/tuple (``apply_colormap``'s own output, e.g. hexbin's
    per-cell facecolors) that ``to_hex`` passes through unchanged since it
    only handles strings. ``if c`` alone raises on a >1-element array
    (numpy's ambiguous-truth-value error), hence the explicit None check.
    """
    if c is None:
        return fallback
    if isinstance(c, str):
        return to_hex(c) or fallback
    c = np.asarray(c).ravel()
    if c.size not in (3, 4):
        return fallback
    rgb = c[:3]
    rgb = (rgb * 255).round() if rgb.dtype.kind == "f" and rgb.max() <= 1.0 else rgb
    r, g, b = (int(v) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


# ---- opt-in raw per-cell mesh data (small meshes only) --------------------
#
# A QuadMesh (pcolormesh/imshow) normally exports as a single rasterized
# `image` mark (see _prim_to_vega below, and vega_lite.py's _mesh_layer) --
# a picture of the data, not the data itself: nothing downstream can read a
# cell's real value, and the colors are frozen at whatever domain/scheme
# existed at export time. `to_vega(mesh_data=True)`/`to_vega_lite(mesh_data=
# True)` opt into real per-cell `rect` marks with a genuine field+scale
# color encoding instead -- reactive, and queryable -- for meshes small
# enough that this stays cheap. Above that size (or for anything this can't
# faithfully represent as named per-cell rows: a curvilinear grid, a non-
# linear color norm, an unrecognized colormap, or a plain Image rather than
# a scalar QuadMesh) it silently isn't offered -- callers fall back to the
# rasterized path with a caveat/warning naming why, never a wrong-colored
# or misshapen mesh. `_VECTOR_CELL_LIMIT` (~2000) is the same threshold
# axes.py's own pcolormesh(rasterized=None) auto-mode already uses for
# "how many discrete cells is reasonable to draw individually" -- the exact
# same tradeoff, reused rather than re-invented.
_MESH_DATA_CELL_LIMIT = _VECTOR_CELL_LIMIT

# plotpress colormap name (lowercased, `_r` suffix stripped separately) ->
# Vega/Vega-Lite's own built-in continuous scheme name. Only colormaps
# confirmed to share an exact scheme name are listed -- silently guessing a
# "close enough" scheme for anything else risks a mesh that LOOKS like
# real data but is colored wrong, which is worse than just not offering
# this path for that colormap.
_MESH_SCHEME_MAP = {
    "viridis": "viridis", "plasma": "plasma", "inferno": "inferno",
    "magma": "magma", "cividis": "cividis", "turbo": "turbo",
    "blues": "blues", "greens": "greens", "oranges": "oranges",
    "reds": "reds", "purples": "purples", "gray": "greys", "grey": "greys",
}


def _mesh_scheme(cmap):
    """``(scheme_name, reverse)`` for a plotpress colormap name/LUT, or
    ``(None, False)`` if it isn't one of the small set of colormaps known to
    share an exact Vega/Vega-Lite scheme name.
    """
    if not isinstance(cmap, str):
        return None, False   # a raw LUT array, not a name -- no scheme to map to
    name, reverse = cmap, False
    if name.endswith("_r"):
        name, reverse = name[:-2], True
    # Vega's built-in "greys" scheme follows ColorBrewer's convention
    # (light = low, dark = high) -- the SAME direction viridis/plasma/.../
    # Blues/Greens/Oranges/Reds/Purples already use, which is why the
    # generic `_r`-suffix handling above is correct for all of them. But
    # plotpress's own "gray" colormap follows matplotlib's literal-
    # luminance convention (black = low, white = high) -- the OPPOSITE
    # direction -- so "gray" needs reverse=True and "gray_r" needs
    # reverse=False, backwards from every other entry in this table.
    # Confirmed by sampling actual rendered pixel colors: cmap="gray_r" on
    # binary data rendered value=0 cells near-black instead of white.
    if name.lower() in ("gray", "grey"):
        reverse = not reverse
    return _MESH_SCHEME_MAP.get(name.lower()), reverse


def _mesh_data_reason(art, mesh_data, ax=None):
    """Why raw per-cell data can't be used for ``art`` (a QuadMesh/Image),
    or ``None`` if it can. Checked in the same order a caller would want
    explained: "did I even ask for this" first, then genuine capability
    gaps.
    """
    if not mesh_data:
        return "mesh_data=False (the default)"
    if not isinstance(art, QuadMesh):
        return "Image (raw pixel data has no per-cell colormap to encode)"
    if art.curvilinear:
        return "a curvilinear (non-rectilinear) grid, which needs per-cell polygons, not axis-aligned rects"
    if art.n_cells is not None and art.n_cells > _MESH_DATA_CELL_LIMIT:
        return f"{art.n_cells} cells, over the {_MESH_DATA_CELL_LIMIT}-cell mesh_data limit"
    if type(art.norm) is not Normalize:
        return f"a {type(art.norm).__name__} color norm (only a plain linear Normalize is supported)"
    if _mesh_scheme(art.cmap_name)[0] is None:
        return f"colormap {art.cmap_name!r} (not in the small set of colormaps with a matching Vega scheme)"
    # Unlike every other mark, a raw per-cell rect defers its x/y transform
    # to the SAME shared scale every other mark on the axes uses, computed
    # at render time by the Vega/Vega-Lite runtime itself -- not
    # pre-clamped in pixel space via transform.py the way the rasterized
    # image path (and every other backend) already is. A cell edge of
    # exactly 0 (an ordinary edge-based grid starting at the origin) fed
    # into a log-typed scale evaluates to NaN there, silently breaking
    # that cell -- confirmed by actually running the spec through the real
    # `vega` JS runtime. Excluding a log-scaled axis outright is simpler
    # and safer than trying to pre-clamp per-edge the way transform.py
    # does, and this path is meant to stay a narrow, unambiguous opt-in.
    if (ax is not None and (ax._xscale == "log" or ax._yscale == "log")):
        return "a log-scaled axis (a cell edge at or below zero would evaluate to NaN in a log scale)"
    if not np.isfinite(art.C).any():
        return "no finite cell values (nothing to draw)"
    return None


def _mesh_cell_rows(mesh):
    """One ``{x0, x1, y0, y1, value}`` row per finite cell of a rectilinear
    ``QuadMesh`` -- shared by :func:`figure_to_vega` and
    :func:`plotpress.vega_lite.figure_to_vega_lite`'s raw-data mesh path.
    """
    xe, ye = mesh.cell_edges()
    ny, nx = mesh.C.shape
    rows = []
    for i in range(ny):
        for j in range(nx):
            v = mesh.C[i, j]
            if not np.isfinite(v):
                continue
            rows.append({"x0": float(xe[j]), "x1": float(xe[j + 1]),
                        "y0": float(ye[i]), "y1": float(ye[i + 1]),
                        "value": float(v)})
    return rows


def _mesh_data_marks(art, x_name, y_name, scales):
    """Real per-cell ``rect`` marks with a field+scale color encoding for a
    QuadMesh eligible for ``mesh_data=True`` (see :func:`_mesh_data_reason`)
    -- reuses :func:`_mesh_cell_rows` for the per-cell rows and appends a
    matching named-scheme color scale into ``scales`` in place, the same
    mutate-in-place convention :func:`_axis_def` already uses for a custom
    tick-label scale.
    """
    rows = _mesh_cell_rows(art)
    if not rows:
        return []
    data_name = f"data_{id(art):x}"
    scheme, reverse = _mesh_scheme(art.cmap_name)
    color_scale = f"{data_name}_color"
    scales.append({
        "name": color_scale, "type": "linear",
        "domain": [float(art.norm.vmin), float(art.norm.vmax)],
        "range": {"scheme": scheme}, "reverse": reverse, "zero": False,
    })
    mark = {
        "type": "rect",
        "from": {"data": data_name},
        "encode": {"enter": {
            "x": {"scale": x_name, "field": "x0"}, "x2": {"scale": x_name, "field": "x1"},
            "y": {"scale": y_name, "field": "y0"}, "y2": {"scale": y_name, "field": "y1"},
            "fill": {"scale": color_scale, "field": "value"},
            "fillOpacity": {"value": float(art.alpha)},
        }},
    }
    return [{"__data__": (data_name, rows)}, mark]


def _line_marks(art, x_name, y_name):
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any() or art.linestyle == "none":
        return []
    data_name = f"data_{id(art):x}"
    # A non-finite point must not be dropped outright -- that would bridge
    # the gap with a spurious straight line across missing data (the
    # standard "y[50:60] = np.nan" idiom). Keep every point and let Vega's
    # own `defined` encoding channel break the line there instead of
    # connecting through it (Vega/D3 line semantics: false in `defined`
    # splits the path into separate segments) -- the same outcome as
    # svg.py's _line_path_d, which explicitly emits separate M...L...
    # subpaths on the same non-finite points. The x/y placeholder for an
    # undefined point is never rendered, so any finite number is fine.
    values = [
        {"x": float(xv) if fv else 0.0, "y": float(yv) if fv else 0.0, "valid": bool(fv)}
        for xv, yv, fv in zip(x, y, finite)
    ]
    dash = _dash_array(art.linestyle)
    enter = {
        "x": {"scale": x_name, "field": "x"},
        "y": {"scale": y_name, "field": "y"},
        "defined": {"field": "valid"},
        "stroke": {"value": _color(art.color)},
        "strokeWidth": {"value": float(art.linewidth)},
        "strokeOpacity": {"value": float(art.alpha)},
        "interpolate": {"value": "linear"},
    }
    if dash:
        enter["strokeDash"] = {"value": dash}
    mark = {
        "type": "line",
        "from": {"data": data_name},
        "encode": {"enter": enter},
    }
    return [{"__data__": (data_name, values)}, mark]


def _scatter_marks(art, x_name, y_name, size_scale):
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return []
    data_name = f"data_{id(art):x}"
    fc = art.face_colors()
    colors = fc if fc is not None else [_color(art.color)] * x.size
    # art.s is a diameter in points (matching every other backend's
    # convention) -- size_scale converts to pixels before _symbol_size
    # converts that pixel diameter to the area Vega's size channel wants.
    s = np.broadcast_to(np.asarray(art.s, float), x.shape) * size_scale
    values = [
        {"x": float(xv), "y": float(yv), "size": _symbol_size(sv), "color": cv}
        for xv, yv, sv, cv in zip(x[finite], y[finite], s[finite],
                                  np.asarray(colors, dtype=object)[finite])
    ]
    enter = {
        "x": {"scale": x_name, "field": "x"},
        "y": {"scale": y_name, "field": "y"},
        "size": {"field": "size"},
        "fill": {"field": "color"},
        "fillOpacity": {"value": float(art.alpha)},
    }
    # primitives.py's own ScatterCollection -> Markers conversion (used by
    # every other backend) only sets an outline when linewidths is truthy --
    # mirrored here since _scatter_marks bypasses that shared path entirely.
    if art.linewidths:
        enter["stroke"] = {"value": _color(art.edgecolor)}
        enter["strokeWidth"] = {"value": float(art.linewidths) * size_scale}
    mark = {
        "type": "symbol",
        "from": {"data": data_name},
        "encode": {"enter": enter},
    }
    return [{"__data__": (data_name, values)}, mark]


def _bars_marks(art, x_name, y_name):
    if art.pos.size == 0:
        return []
    data_name = f"data_{id(art):x}"
    # Bars.__init__ always normalizes color to a per-item list via
    # _as_colors(), regardless of what was passed in -- no fallback needed.
    colors = art.colors
    vals = []
    for pos, length, thick, base, color in zip(art.pos, art.length, art.thickness,
                                                art.base, colors):
        if art.orientation == "vertical":
            vals.append({"x0": pos - thick / 2, "x1": pos + thick / 2,
                        "y0": base, "y1": base + length, "color": _color(color)})
        else:
            vals.append({"x0": base, "x1": base + length,
                        "y0": pos - thick / 2, "y1": pos + thick / 2, "color": _color(color)})
    enter = {
        "x": {"scale": x_name, "field": "x0"}, "x2": {"scale": x_name, "field": "x1"},
        "y": {"scale": y_name, "field": "y0"}, "y2": {"scale": y_name, "field": "y1"},
        "fill": {"field": "color"}, "fillOpacity": {"value": float(art.alpha)},
    }
    # svg.py only draws a bar edge at all when edgecolor is set (svg.py:1493)
    # -- no edge, not a zero-width one, is the "unset" state to match.
    if art.edgecolor:
        enter["stroke"] = {"value": _color(art.edgecolor)}
        enter["strokeWidth"] = {"value": float(art.linewidth)}
    mark = {
        "type": "rect",
        "from": {"data": data_name},
        "encode": {"enter": enter},
    }
    return [{"__data__": (data_name, vals)}, mark]


def _errorbar_marks(art, x_name, y_name, size_scale):
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return []
    data_name = f"data_{id(art):x}"
    marks = []
    # svg.py's cap length (art.capsize) is used as-is, in raw pixels, with
    # no size_scale applied -- matched here rather than "corrected", since
    # the goal is fidelity to what to_svg() actually draws, not a separate
    # opinion about what capsize should mean.
    cap = float(art.capsize)
    if art.yerr is not None:
        yerr = np.asarray(art.yerr, float)
        whiskers = [{"x": float(xv), "y0": float(yv - e), "y1": float(yv + e)}
                   for xv, yv, e, fv in zip(x, y, yerr, finite) if fv]
        wdata = f"{data_name}_yerr"
        marks.append({"__data__": (wdata, whiskers)})
        marks.append({
            "type": "rule", "from": {"data": wdata},
            "encode": {"enter": {
                "x": {"scale": x_name, "field": "x"}, "x2": {"scale": x_name, "field": "x"},
                "y": {"scale": y_name, "field": "y0"}, "y2": {"scale": y_name, "field": "y1"},
                "stroke": {"value": _color(art.ecolor)},
                "strokeWidth": {"value": float(art.elinewidth)},
            }},
        })
        # One row per whisker END (not per whisker) -- a cap is a short
        # perpendicular tick at each tip, svg.py:1555-1556.
        caps = ([{"x": w["x"], "y": w["y0"]} for w in whiskers]
               + [{"x": w["x"], "y": w["y1"]} for w in whiskers])
        cdata = f"{data_name}_ycap"
        marks.append({"__data__": (cdata, caps)})
        marks.append({
            "type": "rule", "from": {"data": cdata},
            "encode": {"enter": {
                "y": {"scale": y_name, "field": "y"}, "y2": {"scale": y_name, "field": "y"},
                "x": {"scale": x_name, "field": "x", "offset": -cap},
                "x2": {"scale": x_name, "field": "x", "offset": cap},
                "stroke": {"value": _color(art.ecolor)},
                "strokeWidth": {"value": float(art.capthick)},
            }},
        })
    if art.xerr is not None:
        xerr = np.asarray(art.xerr, float)
        whiskers = [{"y": float(yv), "x0": float(xv - e), "x1": float(xv + e)}
                   for xv, yv, e, fv in zip(x, y, xerr, finite) if fv]
        wdata = f"{data_name}_xerr"
        marks.append({"__data__": (wdata, whiskers)})
        marks.append({
            "type": "rule", "from": {"data": wdata},
            "encode": {"enter": {
                "y": {"scale": y_name, "field": "y"}, "y2": {"scale": y_name, "field": "y"},
                "x": {"scale": x_name, "field": "x0"}, "x2": {"scale": x_name, "field": "x1"},
                "stroke": {"value": _color(art.ecolor)},
                "strokeWidth": {"value": float(art.elinewidth)},
            }},
        })
        caps = ([{"y": w["y"], "x": w["x0"]} for w in whiskers]
               + [{"y": w["y"], "x": w["x1"]} for w in whiskers])
        cdata = f"{data_name}_xcap"
        marks.append({"__data__": (cdata, caps)})
        marks.append({
            "type": "rule", "from": {"data": cdata},
            "encode": {"enter": {
                "x": {"scale": x_name, "field": "x"}, "x2": {"scale": x_name, "field": "x"},
                "y": {"scale": y_name, "field": "y", "offset": -cap},
                "y2": {"scale": y_name, "field": "y", "offset": cap},
                "stroke": {"value": _color(art.ecolor)},
                "strokeWidth": {"value": float(art.capthick)},
            }},
        })
    # The line connecting the points -- svg.py:1540-1546 draws it (through
    # _line_path_d, the same non-finite-splitting helper _line_marks
    # mirrors above) whenever linestyle isn't None/"none"; today's export
    # dropped it unconditionally.
    if art.linestyle and art.linestyle != "none":
        lvals = [{"x": float(xv) if fv else 0.0, "y": float(yv) if fv else 0.0, "valid": bool(fv)}
                for xv, yv, fv in zip(x, y, finite)]
        ldata = f"{data_name}_line"
        lenter = {
            "x": {"scale": x_name, "field": "x"}, "y": {"scale": y_name, "field": "y"},
            "defined": {"field": "valid"},
            "stroke": {"value": _color(art.color)},
            "strokeWidth": {"value": float(art.linewidth)},
            "strokeOpacity": {"value": float(art.alpha)},
            "interpolate": {"value": "linear"},
        }
        dash = _dash_array(art.linestyle)
        if dash:
            lenter["strokeDash"] = {"value": dash}
        marks.append({"__data__": (ldata, lvals)})
        marks.append({"type": "line", "from": {"data": ldata}, "encode": {"enter": lenter}})
    values = [{"x": float(xv), "y": float(yv)} for xv, yv in zip(x[finite], y[finite])]
    marks.append({"__data__": (data_name, values)})
    marks.append({
        "type": "symbol", "from": {"data": data_name},
        "encode": {"enter": {
            "x": {"scale": x_name, "field": "x"}, "y": {"scale": y_name, "field": "y"},
            "size": {"value": _symbol_size(float(art.markersize) * size_scale)},
            "fill": {"value": _color(art.color)},
            "fillOpacity": {"value": float(art.alpha)},
        }},
    })
    return marks


def _stem_marks(art, x_name, y_name, size_scale, st):
    # Stem has no markersize of its own -- svg.py:1531 uses the *figure
    # style's* st.marker_size (dpi/72-scaled), not a per-artist field, for
    # the tip dot. size_scale is exactly that conversion, already computed.
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return []
    data_name = f"data_{id(art):x}"
    values = [{"x": float(xv), "y0": art.baseline, "y1": float(yv)}
             for xv, yv in zip(x[finite], y[finite])]
    marks = [
        {"__data__": (data_name, values)},
        {"type": "rule", "from": {"data": data_name},
         "encode": {"enter": {
             "x": {"scale": x_name, "field": "x"}, "x2": {"scale": x_name, "field": "x"},
             "y": {"scale": y_name, "field": "y0"}, "y2": {"scale": y_name, "field": "y1"},
             "stroke": {"value": _color(art.linecolor)},
             "strokeWidth": {"value": 1.2},
         }}},
    ]
    # The reference line the stems sit on -- svg.py:1526-1530 always draws
    # it, spanning just the data's own x-range (not the full axes width);
    # dropping it silently loses the value (e.g. ax.stem(x, y, bottom=2))
    # a stem plot exists to show.
    if x[finite].size:
        xlo, xhi = float(x[finite].min()), float(x[finite].max())
        marks.append({
            "type": "rule",
            "encode": {"enter": {
                "x": {"scale": x_name, "value": xlo}, "x2": {"scale": x_name, "value": xhi},
                "y": {"scale": y_name, "value": art.baseline},
                "y2": {"scale": y_name, "value": art.baseline},
                "stroke": {"value": st.spine_color},
                "strokeWidth": {"value": 0.8},
            }}},
        )
    marks.append({
        "type": "symbol", "from": {"data": data_name},
        "encode": {"enter": {
            "x": {"scale": x_name, "field": "x"}, "y": {"scale": y_name, "field": "y1"},
            "size": {"value": _symbol_size(st.marker_size * size_scale)},
            "fill": {"value": _color(art.markercolor)},
        }}},
    )
    return marks


def _pie_marks(art, tr):
    # Pie draws in its own axes-pixel space already (see artists.Pie) -- the
    # same fixed circle regardless of x/y scales, so this is frozen pixel
    # geometry like the primitives.py-backed marks, not scale-driven.
    # Center/radius mirror svg.py's _render_pie exactly (tr is built with a
    # local (0, 0, px_w, px_h) rect -- see _axes_to_group -- so px_left/
    # px_top are already 0 here, same as that function's cx/cy math).
    cx, cy, R = pie_center_radius(tr.px_w, tr.px_h, art.radius, tr.px_left, tr.px_top)
    data_name = f"data_{id(art):x}"
    # art.fracs (not art.values) -- Pie.__init__ already turns an all-zero
    # total into equal fractions rather than dividing by zero; feeding Vega's
    # own pie transform art.values directly would NaN every angle for that
    # edge case instead.
    values = [{"value": float(v), "color": _color(c)}
             for v, c in zip(art.fracs, art.colors)]
    # Vega's `pie` transform is a *data* transform (it belongs in a data
    # entry's own "transform", not on the mark -- marks have no such
    # property and silently ignore one), and needs startAngle/endAngle
    # fields computed before the arc mark can read them via "field", not
    # "value" -- confirmed by rendering the earlier (broken) version through
    # vg2png: putting "transform" on the mark produced zero wedges, since
    # startAngle stayed 0 and endAngle was never set at all (defaults to 0).
    # Vega's own angle convention (0 at 12 o'clock, clockwise-positive) is
    # converted from plotpress's (0 at 3 o'clock, degrees, matplotlib-style
    # counterclockwise) the same way svg.py's `ang = radians(startangle)`
    # plus its clockwise sweep (`a1 = ang - sweep`, then y negated) works
    # out to: both sweep clockwise on screen, just measured from a
    # different zero point.
    transform = [{"type": "pie", "field": "value",
                  "startAngle": math.radians(90.0 - art.startangle)}]
    marks = [
        {"__data__": (data_name, values, transform)},
        {"type": "arc", "from": {"data": data_name},
         "encode": {"enter": {
             "x": {"value": round(float(cx), 2)}, "y": {"value": round(float(cy), 2)},
             "startAngle": {"field": "startAngle"},
             "endAngle": {"field": "endAngle"},
             "innerRadius": {"value": 0},
             "outerRadius": {"value": round(float(R), 2)},
             "fill": {"field": "color"},
             "fillOpacity": {"value": float(art.alpha)},
             "stroke": {"value": "#ffffff"},
             "strokeWidth": {"value": 1.5},
         }}},
    ]
    # Wedge label / autopct%% text -- svg.py's _render_pie draws both at
    # fixed points, one wedge-midpoint angle at a time; Vega's `pie` data
    # transform only computes angles for the arc mark that reads it (there's
    # no equivalent auto-placement for a *text* mark), so pie_label_positions()
    # (the shared trig walk every plotpress pie renderer uses) supplies a
    # literal x/y per label -- frozen pixel positions, matching how the arc
    # itself is frozen pixel geometry (see the module docstring).
    if art.labels is not None or art.autopct is not None:
        rows = pie_label_positions(art.fracs, art.startangle, cx, cy, R)
        label_rows = [{"x": r["label_x"], "y": r["label_y"],
                      "anchor": "start" if r["right_side"] else "end"} for r in rows]
        pct_rows = [{"x": r["pct_x"], "y": r["pct_y"]} for r in rows]
        if art.labels is not None:
            lvals = [{"x": round(float(r["x"]), 2), "y": round(float(r["y"]), 2),
                     "text": str(lbl), "align": r["anchor"]}
                    for r, lbl in zip(label_rows, art.labels)]
            ldata = f"{data_name}_labels"
            marks.append({"__data__": (ldata, lvals)})
            marks.append({
                "type": "text", "from": {"data": ldata},
                "encode": {"enter": {
                    "x": {"field": "x"}, "y": {"field": "y"}, "text": {"field": "text"},
                    "align": {"field": "align"}, "baseline": {"value": "middle"},
                    "fontSize": {"value": 10},
                }},
            })
        if art.autopct is not None:
            pvals = [{"x": round(float(r["x"]), 2), "y": round(float(r["y"]), 2), "text": pct}
                    for r, frac in zip(pct_rows, art.fracs)
                    for pct in [art.pct_text(frac)] if pct is not None]
            if pvals:
                pdata = f"{data_name}_pct"
                marks.append({"__data__": (pdata, pvals)})
                marks.append({
                    "type": "text", "from": {"data": pdata},
                    "encode": {"enter": {
                        "x": {"field": "x"}, "y": {"field": "y"}, "text": {"field": "text"},
                        "align": {"value": "center"}, "baseline": {"value": "middle"},
                        "fontSize": {"value": 10},
                    }},
                })
    return marks


# plotpress va -> Vega text-mark baseline. svg.py's own _VA maps to SVG's
# dominant-baseline vocabulary instead; Vega's baseline property uses a
# different (if overlapping) set of names.
_VEGA_VA = {"baseline": "alphabetic", "bottom": "bottom", "center": "middle", "top": "top"}


def _text_marks(art, tr, st):
    if isinstance(art, Annotation):
        x, y = art.xytext if art.xytext is not None else art.xy
    else:
        x, y = art.x, art.y
    if art.axes_fraction:
        px, py = (float(v) for v in _axes_fraction_xy(tr, x, y))
    else:
        px, py = float(tr.x(x)), float(tr.y(y))
    # `or 11` would treat a legitimate size=0 (e.g. a deliberately hidden
    # label) the same as "missing" and silently draw it at 11pt instead --
    # svg.py's own text renderers pass size straight through with no such
    # fallback, so this only substitutes when the attribute is truly absent.
    size = getattr(art, "size", None)
    size = 11.0 if size is None else float(size)
    ha = getattr(art, "ha", "left")
    va = getattr(art, "va", "baseline")
    bold = bool(getattr(art, "bold", False))
    italic = bool(getattr(art, "italic", False))
    alpha = float(getattr(art, "alpha", 1.0))
    color = _color(getattr(art, "color", None), "#000000")
    marks = []

    # A bbox= background box, measured with the same font metrics svg.py's
    # own text_box() uses (reused directly, not re-derived) -- so the box
    # actually wraps the glyphs it's drawn behind, matching svg.py:1851-1855.
    box = None
    bbox = getattr(art, "bbox", None)
    if bbox is not None:
        box = _bbox_pad(text_box(px, py, art.text, size, ha, va, st, bold=bold, italic=italic), bbox)
        x0, y0, x1, y1 = box
        rx = min(8.0, (x1 - x0) / 2.0, (y1 - y0) / 2.0) if bbox["boxstyle"] == "round" else 0.0
        rect_enter = {
            "x": {"value": round(float(x0), 2)}, "y": {"value": round(float(y0), 2)},
            "width": {"value": round(float(x1 - x0), 2)}, "height": {"value": round(float(y1 - y0), 2)},
            "cornerRadius": {"value": round(float(rx), 2)},
            "fill": {"value": _color(bbox["facecolor"])},
        }
        if bbox["alpha"] < 1:
            rect_enter["fillOpacity"] = {"value": float(bbox["alpha"])}
        if bbox["edgecolor"] not in (None, "none"):
            rect_enter["stroke"] = {"value": _color(bbox["edgecolor"])}
            rect_enter["strokeWidth"] = {"value": float(bbox["linewidth"])}
        marks.append({"type": "rect", "encode": {"enter": rect_enter}})

    # Annotation's leader line + arrowhead -- svg.py:1873-1898. leader_anchor
    # (reused, not re-derived) picks the nearest box edge midpoint rather
    # than the bare text anchor, so the line doesn't cut through the words
    # it's pointing away from.
    if isinstance(art, Annotation) and art.arrowprops is not None:
        if art.axes_fraction:
            tx, ty = (float(v) for v in _axes_fraction_xy(tr, *art.xy))
        else:
            tx, ty = float(tr.x(art.xy[0])), float(tr.y(art.xy[1]))
        arrow_color = _color(
            art.arrowprops.get("color", art.color) if isinstance(art.arrowprops, dict) else art.color)
        arrow_alpha = (art.arrowprops.get("alpha", 1.0)
                      if isinstance(art.arrowprops, dict) else 1.0)
        anchor_box = box if box is not None else text_box(px, py, art.text, size, ha, va, st,
                                                           bold=bold, italic=italic)
        sx, sy = leader_anchor(anchor_box, (tx, ty))
        ang = math.atan2(ty - sy, tx - sx)
        hl = 7.0
        h1 = (tx - hl * math.cos(ang - 0.4), ty - hl * math.sin(ang - 0.4))
        h2 = (tx - hl * math.cos(ang + 0.4), ty - hl * math.sin(ang + 0.4))
        d = (f"M{sx:.2f},{sy:.2f} L{tx:.2f},{ty:.2f} "
            f"M{tx:.2f},{ty:.2f} L{h1[0]:.2f},{h1[1]:.2f} "
            f"M{tx:.2f},{ty:.2f} L{h2[0]:.2f},{h2[1]:.2f}")
        arrow_enter = {
            "path": {"value": d}, "stroke": {"value": arrow_color}, "strokeWidth": {"value": 1.2},
        }
        if arrow_alpha < 1:
            arrow_enter["strokeOpacity"] = {"value": float(arrow_alpha)}
        marks.append({"type": "path", "encode": {"enter": arrow_enter}})

    text_enter = {
        "x": {"value": round(px, 2)}, "y": {"value": round(py, 2)},
        "text": {"value": art.text},
        "fill": {"value": color},
        "fontSize": {"value": size},
        "align": {"value": ha if ha in ("left", "right", "center") else "left"},
        "baseline": {"value": _VEGA_VA.get(va, "alphabetic")},
    }
    rotation = float(getattr(art, "rotation", 0.0) or 0.0)
    if rotation:
        # plotpress's own rotation is counterclockwise-positive (matplotlib
        # convention); Vega's `angle`, like SVG's rotate(), is
        # clockwise-positive -- svg.py:1686 negates for the same reason.
        text_enter["angle"] = {"value": -rotation}
    if bold:
        text_enter["fontWeight"] = {"value": "bold"}
    if italic:
        text_enter["fontStyle"] = {"value": "italic"}
    if alpha < 1:
        text_enter["fillOpacity"] = {"value": alpha}
    marks.append({"type": "text", "encode": {"enter": text_enter}})
    return marks


# ---- primitive -> Vega marks (frozen pixel geometry) -------------------

def _prim_to_vega(p):
    if isinstance(p, PMarkers):
        pts = p.points
        finite = np.isfinite(pts).all(axis=1)
        if not finite.any():
            return []
        data_name = f"prim_{id(p):x}"
        diam = np.broadcast_to(p.diameters, (pts.shape[0],))
        # p.colors is already one entry per point regardless of
        # single_color -- that flag is only a hint for a backend that wants
        # to skip redundant per-node color attributes, not a shorter list.
        colors = np.asarray(p.colors, dtype=object)
        values = [
            {"x": float(pt[0]), "y": float(pt[1]), "size": _symbol_size(float(d)), "color": _color(c)}
            for pt, d, c in zip(pts[finite], diam[finite], colors[finite])
        ]
        enter = {
            "x": {"field": "x"}, "y": {"field": "y"}, "size": {"field": "size"},
            "fill": {"field": "color"}, "fillOpacity": {"value": float(p.alpha)},
        }
        # p.edgewidth == 0 is Markers' own "no outline" convention (see its
        # docstring) -- matches every other backend drawing nothing rather
        # than a zero-width stroke.
        if p.edgewidth:
            enter["stroke"] = {"value": _color(p.edgecolor)}
            enter["strokeWidth"] = {"value": float(p.edgewidth)}
        return [{"__data__": (data_name, values)}, {
            "type": "symbol", "from": {"data": data_name},
            "encode": {"enter": enter},
        }]

    if isinstance(p, PLine):
        enter = {
            "x": {"value": float(p.p0[0])}, "y": {"value": float(p.p0[1])},
            "x2": {"value": float(p.p1[0])}, "y2": {"value": float(p.p1[1])},
            "stroke": {"value": _color(p.stroke)},
            "strokeWidth": {"value": float(p.stroke_width)},
            "strokeOpacity": {"value": float(p.stroke_opacity)},
        }
        dash = _dash_array(p.linestyle)
        if dash:
            enter["strokeDash"] = {"value": dash}
        return [{"type": "rule", "encode": {"enter": enter}}]

    if isinstance(p, PRect):
        return [{
            "type": "rect",
            "encode": {"enter": {
                "x": {"value": float(p.x)}, "y": {"value": float(p.y)},
                "width": {"value": float(p.w)}, "height": {"value": float(p.h)},
                "fill": {"value": _color(p.fill)},
                "fillOpacity": {"value": float(p.fill_opacity)},
            }},
        }]

    if isinstance(p, PSegments):
        if p.segs.size == 0:
            return []
        data_name = f"prim_{id(p):x}"
        values = [{"x0": float(s[0]), "y0": float(s[1]), "x1": float(s[2]), "y1": float(s[3])}
                 for s in p.segs]
        enter = {
            "x": {"field": "x0"}, "y": {"field": "y0"},
            "x2": {"field": "x1"}, "y2": {"field": "y1"},
            "stroke": {"value": _color(p.stroke)},
            "strokeWidth": {"value": float(p.stroke_width)},
            "strokeOpacity": {"value": float(p.stroke_opacity)},
        }
        dash = _dash_array(p.linestyle)
        if dash:
            enter["strokeDash"] = {"value": dash}
        return [{"__data__": (data_name, values)}, {
            "type": "rule", "from": {"data": data_name},
            "encode": {"enter": enter},
        }]

    if isinstance(p, PPath):
        marks = []
        for sub in p.subpaths:
            finite_sub = sub[np.isfinite(sub).all(axis=1)]
            if finite_sub.shape[0] < 2:
                continue
            d = _path_string(finite_sub, p.closed)
            enter = {"path": {"value": d}}
            if p.fill:
                enter["fill"] = {"value": _color(p.fill)}
                enter["fillOpacity"] = {"value": float(p.fill_opacity)}
            if p.stroke:
                enter["stroke"] = {"value": _color(p.stroke)}
                enter["strokeWidth"] = {"value": float(p.stroke_width)}
                enter["strokeOpacity"] = {"value": float(p.stroke_opacity)}
                dash = _dash_array(p.linestyle)
                if dash:
                    enter["strokeDash"] = {"value": dash}
            marks.append({"type": "path", "encode": {"enter": enter}})
        return marks

    if isinstance(p, PPolyBatch):
        marks = []
        for poly, fill in zip(p.polys, p.fills):
            finite_poly = poly[np.isfinite(poly).all(axis=1)]
            if finite_poly.shape[0] < 2:
                continue
            enter = {
                "path": {"value": _path_string(finite_poly, True)},
                "fill": {"value": _color(fill)},
                "fillOpacity": {"value": float(p.alpha)},
            }
            if p.edge:
                enter["stroke"] = {"value": _color(p.edge)}
                enter["strokeWidth"] = {"value": float(p.edge_width)}
            marks.append({"type": "path", "encode": {"enter": enter}})
        return marks

    if isinstance(p, PImage):
        return [{
            "type": "image",
            "encode": {"enter": {
                "x": {"value": float(p.x)}, "y": {"value": float(p.y)},
                "width": {"value": float(p.w)}, "height": {"value": float(p.h)},
                "url": {"value": png_data_uri(p.rgba)},
                "smooth": {"value": bool(p.smooth)},
                "aspect": {"value": False},
            }},
        }]

    return []


# Vertical-alignment y-offset fractions for fig.text(), matching svg.py's
# own _render_fig_text approximation exactly (not true font-metric centering).
_VA_DY = {"top": 0.8, "center": 0.35, "bottom": 0.0, "baseline": 0.0}


def _figtexts_to_vega_marks(fig, W, H):
    """``fig.suptitle()``/``supxlabel()``/``supylabel()``/``text()`` as
    top-level Vega ``text`` marks -- direct ports of ``svg.py``'s
    ``_render_figtexts`` (same position math, same fallback sizes), the
    same figure-pixel-space, sibling-of-the-axes-groups treatment
    :func:`_groups_to_vega_marks` already gives ``Figure.group()`` boxes.
    """
    st = fig.style
    marks = []
    if fig._suptitle:
        t = fig._suptitle
        size = t.get("size") or st.title_size * 1.5
        marks.append({"type": "text", "encode": {"enter": {
            "x": {"value": round(W / 2.0, 2)}, "y": {"value": round(size + 6, 2)},
            "text": {"value": t["text"]}, "align": {"value": "center"},
            "fontSize": {"value": float(size)}, "fontWeight": {"value": "bold"},
            "fill": {"value": _color(st.text_color)},
        }}})
    if fig._supxlabel:
        t = fig._supxlabel
        size = t.get("size") or st.label_size * 1.2
        marks.append({"type": "text", "encode": {"enter": {
            "x": {"value": round(W / 2.0, 2)}, "y": {"value": round(H - 6, 2)},
            "text": {"value": t["text"]}, "align": {"value": "center"},
            "fontSize": {"value": float(size)}, "fill": {"value": _color(st.text_color)},
        }}})
    if fig._supylabel:
        t = fig._supylabel
        size = t.get("size") or st.label_size * 1.2
        x, y = size + 4, H / 2.0
        marks.append({"type": "text", "encode": {"enter": {
            "x": {"value": round(float(x), 2)}, "y": {"value": round(float(y), 2)},
            "text": {"value": t["text"]}, "align": {"value": "center"},
            "angle": {"value": -90},
            "fontSize": {"value": float(size)}, "fill": {"value": _color(st.text_color)},
        }}})
    for t in fig._fig_texts:
        size = t["size"] or st.font_size
        x = t["x"] * W
        y = (1.0 - t["y"]) * H + _VA_DY.get(t["va"], 0.0) * size
        align = {"left": "left", "center": "center", "right": "right"}.get(t["ha"], "left")
        enter = {
            "x": {"value": round(float(x), 2)}, "y": {"value": round(float(y), 2)},
            "text": {"value": t["s"]}, "align": {"value": align},
            "fontSize": {"value": float(size)},
            "fill": {"value": _color(t["color"] or st.text_color)},
        }
        if t.get("alpha", 1.0) < 1:
            enter["fillOpacity"] = {"value": float(t["alpha"])}
        marks.append({"type": "text", "encode": {"enter": enter}})
    return marks


def _groups_to_vega_marks(fig, W, H):
    """``Figure.group()``'s labeled boxes as top-level Vega ``rect``+``text``
    marks -- a direct port of ``svg.py``'s ``_render_groups`` (same box
    geometry, same clearance/pad math, same title placement) onto Vega's
    mark model instead of raw SVG elements.
    """
    st = fig.style
    marks = []
    for gi, g in enumerate(fig._groups):
        members = g["axes"] + _group_colorbars(g["axes"], fig)
        rects = [_pixel_rect(ax, W, H) for ax in members]
        extras = [_group_colorbar_extra(ax, st) if ax._is_colorbar
                 else _group_axes_extra(ax, st) for ax in members]
        pad_l, pad_r, pad_t, pad_b = g["pad"]
        x0 = min(r[0] - e[2] for r, e in zip(rects, extras)) - pad_l
        y0 = min(r[1] - e[0] for r, e in zip(rects, extras)) - pad_t
        x1 = max(r[0] + r[2] + e[3] for r, e in zip(rects, extras)) + pad_r
        y1 = max(r[1] + r[3] + e[1] for r, e in zip(rects, extras)) + pad_b

        if g["linestyle"] == "none":
            stroke_enter = {"stroke": {"value": None}}
        else:
            dash = _DASH.get(g["linestyle"])
            stroke_enter = {
                "stroke": {"value": g["color"]},
                "strokeWidth": {"value": g["linewidth"]},
            }
            if dash:
                stroke_enter["strokeDash"] = {"value": [float(n) for n in dash.split(",")]}
        marks.append({
            "type": "rect",
            "name": f"group{gi}",
            "encode": {"enter": {
                "x": {"value": round(float(x0), 2)},
                "y": {"value": round(float(y0), 2)},
                "width": {"value": round(float(x1 - x0), 2)},
                "height": {"value": round(float(y1 - y0), 2)},
                "fill": {"value": None},
                **stroke_enter,
            }},
        })

        size = g["fontsize"] or st.title_size
        pos = g["title_position"]
        if pos == "top":
            tx, ty, align = (x0 + x1) / 2, y0 - 6, "center"
        elif pos == "bottom":
            tx, ty, align = (x0 + x1) / 2, y1 + size + 2, "center"
        elif pos == "left":
            tx, ty, align = x0 - 6, (y0 + y1) / 2 + 0.35 * size, "right"
        else:
            tx, ty, align = x1 + 6, (y0 + y1) / 2 + 0.35 * size, "left"
        marks.append({
            "type": "text",
            "name": f"group{gi}_title",
            "encode": {"enter": {
                "x": {"value": round(float(tx), 2)},
                "y": {"value": round(float(ty), 2)},
                "text": {"value": g["title"]},
                "align": {"value": align},
                "fontSize": {"value": size},
                "fontWeight": {"value": "bold"},
                "fill": {"value": g["color"]},
            }},
        })
    return marks


def _path_string(pts, closed):
    parts = [f"M{pts[0, 0]:.2f},{pts[0, 1]:.2f}"]
    parts.extend(f"L{x:.2f},{y:.2f}" for x, y in pts[1:])
    if closed:
        parts.append("Z")
    return "".join(parts)


# ---- assemble the final spec: promote inline __data__ markers ----------

def _finalize(spec):
    """Walk the marks tree, pulling every ``{"__data__": (name, values)}``
    (or ``(name, values, transform)``, for a data source that needs a real
    Vega data transform -- e.g. the ``pie`` transform computing
    ``startAngle``/``endAngle`` -- rather than raw literal rows) placeholder
    up into the spec's own top-level ``data`` array and dropping the
    placeholder itself -- lets every mark-building function above just emit
    its data inline next to the mark that reads it, rather than threading a
    shared ``data`` list through every one of them.
    """
    data = []
    seen = set()

    def walk(marks):
        out = []
        for m in marks:
            if "__data__" in m:
                name, values, *rest = m["__data__"]
                if name not in seen:
                    seen.add(name)
                    entry = {"name": name, "values": values}
                    if rest and rest[0]:
                        entry["transform"] = rest[0]
                    data.append(entry)
                continue
            if m.get("type") == "group":
                m["marks"] = walk(m["marks"])
            out.append(m)
        return out

    spec["marks"] = walk(spec["marks"])
    spec["data"] = data
    return spec
