"""JSON metadata payloads for the interactive HTML export: per-axes/template
decoration fields, the embedded pick/frame data pcolormesh clicking and
plot_frames()/pcolormesh_frames() sliders read from, and the figure-level
style payload. Called directly by figure.py -- nothing inside this package's
own render pipeline calls back into it.
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

from ._format import _pixel_rect
from ._render import _effective_rect, _render_axes
from ._group_layout import _colorbar_label

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
    rebuilt -- see :func:`template_metadata`, which needs the identical map and
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
        if ax._is_colorbar or not ax._visible:
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
            "grid_axis": ax._grid_axis, "grid_which": ax._grid_which,
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
            # Datetime/categorical/declarative-locator-or-format flavor, so
            # the client's own pan/zoom tick rebuild (see _interactive.py's
            # resolveAxisTicks) can replay the same priority chain
            # (categorical > locator/format > date > log/default) that
            # ticker.resolve_axis_ticks/resolve_axis_tick_labels apply here.
            # A callable xformat/yformat can't cross into JS -- it serializes
            # as None, so a zoomed date/plain axis with one just falls back
            # to default formatting client-side (documented on set_xformat).
            "xdate": bool(ax._xdate), "ydate": bool(ax._ydate),
            "xcategorical": bool(ax._xcategorical),
            "ycategorical": bool(ax._ycategorical),
            "xcategories": list(ax._xcategories) if ax._xcategorical else None,
            "ycategories": list(ax._ycategories) if ax._ycategorical else None,
            "xlocator": ax._xlocator, "ylocator": ax._ylocator,
            "xformat": ax._xformat if not callable(ax._xformat) else None,
            "yformat": ax._yformat if not callable(ax._yformat) else None,
            # A twin never sets either side itself -- the static renderer draws a
            # twinx's y-axis on the right and a twiny's x-axis on top regardless
            # (see _group_axes_clearance) -- so the client's own tick rebuild
            # (pan/zoom, the Slice companion layout) has to be told, or it redraws
            # a twin's ticks on the wrong edge.
            "xside": "top" if ax._twin_shared == "y" and ax._twin_of is not None else ax._xtick_side,
            "yside": "right" if ax._twin_shared == "x" and ax._twin_of is not None else ax._ytick_side,
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
            # The raw label, not _shown_*(): a label set visible=False is drawn
            # nowhere but is precisely the name an export still wants.
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
            # The axes this is an inset_axes() of (Slice leaves an inset out).
            "inset_of": (idx_of.get(id(ax._inset_parent))
                         if ax._inset_parent is not None else None),
            "twin_shared": ax._twin_shared,
            "secondary_of": (idx_of.get(id(ax._secondary_of))
                             if ax._secondary_of is not None else None),
            "secondary_dim": ax._secondary_dim,
        }
    return meta


def _axes_decoration_fields(ax):
    """One axes' own decorations (title, labels, limits, scale, grid,
    aspect, facecolor, legend) -- no grid-shape/projection fields, since a
    ``twinx()``/``twiny()``/``secondary_xaxis()``/``secondary_yaxis()``/
    ``inset_axes()`` overlay is placed relative to its *parent* axes
    (:func:`plotpress.figure.Figure.to_template`'s own ``"overlays"``/
    ``"insets"`` entries), not as a grid cell of its own the way
    :func:`_axes_layout_fields` below needs. Shared by both.
    """
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    return {
        "title": ax._title or None, "title_size": ax._title_size,
        "xlabel": ax._xlabel or None, "ylabel": ax._ylabel or None,
        "xlabel_size": ax._xlabel_size, "ylabel_size": ax._ylabel_size,
        # Only emitted when actually hidden -- a visible label (the common
        # case) carries no extra key, and an old layout without these
        # rebuilds visible, which is what it always was.
        **({"xlabel_visible": False} if ax._xlabel and not ax._xlabel_visible else {}),
        **({"ylabel_visible": False} if ax._ylabel and not ax._ylabel_visible else {}),
        # Always explicit, even for an originally auto-scaled axes --
        # "the same figure back" means the same rendered extent, not
        # whatever autoscale happens to recompute from however much of
        # the original data the caller chooses to replot.
        "xlim": [round(float(xmin), 6), round(float(xmax), 6)],
        "ylim": [round(float(ymin), 6), round(float(ymax), 6)],
        "xscale": ax._xscale, "yscale": ax._yscale,
        "xinverted": bool(ax._xinverted), "yinverted": bool(ax._yinverted),
        "grid": bool(ax._grid), "grid_alpha": ax._grid_alpha,
        "grid_axis": ax._grid_axis, "grid_which": ax._grid_which,
        "aspect": ax._aspect, "box_aspect": ax._box_aspect,
        "axis_off": bool(ax._axis_off),
        "facecolor": ax._facecolor,
        "legend": ({
            "loc": ax._legend_loc, "ncol": ax._legend_ncol,
            "title": ax._legend_title, "fontsize": ax._legend_fontsize,
            "framealpha": ax._legend_framealpha,
        } if ax._show_legend else None),
    }


def _axes_layout_fields(ax):
    """One grid axes' own grid-shape + decorations -- the part of
    :func:`template_metadata`'s per-axes payload that a plain, non-styling
    reconstruction needs. Pulled out on its own so :func:`_template_axes_extra`
    below can build on the same base dict instead of hand-duplicating it.
    """
    spec = ax._subplotspec
    return {
        "nrows": spec.nrows, "ncols": spec.ncols,
        "row0": spec.row0, "row1": spec.row1,
        "col0": spec.col0, "col1": spec.col1,
        # None for a plain Cartesian axes, so a round trip through
        # add_subplot(..., projection=...) reproduces it exactly.
        "projection": "polar" if getattr(ax, "_is_polar", False) else None,
        **_axes_decoration_fields(ax),
    }


def _template_axes_extra(ax):
    """The fields :func:`template_metadata` needs beyond
    :func:`_axes_layout_fields`: which axes id it had, its own per-side
    spine styling, and any ``tick_params()``/``tick_top()``-style
    overrides.

    Spine colors are the raw, possibly-``None`` override (see
    :class:`~plotpress.axes.Spine`'s own "``None`` means inherit the
    figure's ``Style``" convention) -- not the resolved color -- so a
    template that never touched a given side keeps inheriting whatever
    ``Style`` it's loaded with later, rather than baking in today's
    concrete color as if it had been set explicitly.
    """
    return {
        "id": ax.get_id(),
        "spines": {
            side: {"color": sp._color, "linewidth": sp._linewidth,
                  "visible": sp._visible, "alpha": sp._alpha}
            for side, sp in ax.spines.items()
        },
        "tick_overrides": {"x": dict(ax._tick_overrides["x"]),
                           "y": dict(ax._tick_overrides["y"])},
        "minor_tick_overrides": {"x": dict(ax._minor_tick_overrides["x"]),
                                 "y": dict(ax._minor_tick_overrides["y"])},
        "xtick_side": ax._xtick_side, "ytick_side": ax._ytick_side,
        "minor_ticks_on": bool(ax._minor_ticks_on),
    }


def template_metadata(fig, idx_of=None):
    """A reusable, data-free snapshot of ``fig``'s own structure and
    styling -- grid shape, :meth:`~plotpress.figure.Figure.group` boxes,
    every axes' own decorations, spine colors, tick overrides, ids, twin/
    secondary/inset overlays, colorbar styling, and this figure's own
    :class:`~plotpress.style.Style` -- everything
    :func:`plotpress.figure_from_template` needs to rebuild an identically
    laid-out, identically styled *blank* figure, with none of the data
    actually plotted into it.

    This is both :meth:`~plotpress.figure.Figure.to_template`'s own
    implementation and what ``to_html()`` embeds for
    :func:`plotpress.load_data` to read back under its ``"template"`` key
    -- one shape, one function, used by both the explicit "build a
    reusable template" path and the "recover a saved figure's own
    structure alongside its data" path. Independent of ``axes_metadata()``'s
    per-axes pixel/style payload above (built for the live interactive
    view, not for reconstruction -- the two overlap in a few fields, e.g.
    title, by coincidence of both needing it, not because one is derived
    from the other).

    ``idx_of`` (an ``id(axes) -> index`` map) is accepted rather than always
    rebuilt, so a caller that already has one -- ``to_html()`` builds one for
    :func:`axes_metadata` moments before calling this -- doesn't pay for the
    same O(axes) dict twice in the same save.

    Only axes placed via :meth:`Figure.add_subplot`/:meth:`Figure.subplots`
    (``ax._subplotspec is not None``) end up in ``"axes"`` -- a freeform
    :meth:`Figure.add_axes` rect has no grid cell to recover, so it is
    simply absent from the payload rather than guessed at; its index is
    still recorded in ``"omitted_axes"`` (colorbars excluded -- they were
    never expected to round-trip) so :func:`plotpress.figure_from_template`
    can warn that a real, once-visible axes won't come back, instead of the
    drop passing without any signal beyond the payload simply being smaller.

    A ``twinx()``/``twiny()``/``secondary_xaxis()``/``secondary_yaxis()``
    overlay also has ``_subplotspec is not None`` (copied from its parent
    verbatim, so it stays aligned through ``tight_layout()``) but is
    likewise excluded from ``"axes"`` -- it needs its parent axes to
    already exist, so it can't be a grid cell of its own; without this it
    would be captured as a second, unrelated grid axes at the exact same
    ``row0``/``row1``/``col0``/``col1`` as its parent, which
    :func:`plotpress.figure_from_template` would then rebuild as two
    overlapping ordinary axes rather than one primary + a real twin. It is
    instead captured properly, alongside its own decorations, in
    ``"overlays"`` (see below).

    Top-level keys beyond ``"axes"``/``"groups"``/``"omitted_axes"``/
    ``"figsize"``/``"suptitle"``/``"supxlabel"``/``"supylabel"``/
    ``"facecolor"``:

    - ``"style"``: ``dataclasses.asdict(fig.style)`` -- a flat dataclass,
      trivially rebuilt via ``Style(**d)``.
    - ``"overlays"``: one entry per twin/secondary axes, keyed by
      ``"parent"`` (an index into ``"axes"`` or another ``"overlays"``
      entry's own ``"index"``, for a twin/secondary built from another
      overlay), carrying its ``"kind"`` (``"twinx"``/``"twiny"``/
      ``"secondary_xaxis"``/``"secondary_yaxis"``), ``"location"``
      (secondary only), and its own decorations/spines/tick overrides/id.
    - ``"insets"``: one entry per ``inset_axes()``, keyed the same way,
      carrying its ``"bounds"``/``"projection"`` plus the same decorations.
    - ``"colorbars"``: one entry per colorbar axes -- which axes it
      belongs to (``"parents"``, indices into ``"axes"``/``"overlays"`` at
      capture time -- for cross-referencing this dict by hand, not
      positions in a rebuilt ``fig.axes``, which can renumber relative to
      them once overlays/insets are rebuilt after the grid) and its
      ``"fraction"``/``"pad"``/``"label"``/``"ticks"``/``"format"`` --
      never the color mapping itself, which needs a live mappable that
      doesn't exist until data is actually plotted. A colorbar's
      ``ticks``/``format`` is only carried over when it's a plain
      JSON-safe value (a list, or a ``%``-style format string) -- a
      callable can't survive JSON, so it's dropped with a ``UserWarning``
      naming which colorbar lost it, the same "degrade a part, not the
      whole" policy :meth:`~plotpress.figure.Figure.to_vega`/
      :meth:`~plotpress.figure.Figure.to_vega_lite` already use for their
      own unmappable cases.

    A :meth:`~plotpress.figure.Figure.group`'s own ``id`` round-trips too
    (it's a plain field on the group dict itself, not tied to any one
    axes).

    Deliberately NOT captured (real, currently unrecoverable gaps -- a
    caller that needs one of these still has to re-apply it by hand): a
    colorbar's actual color mapping (see above), and a non-JSON-safe
    colorbar ``ticks``/``format`` (also above). ``"legend"`` is captured
    but never auto-applied on reconstruction, for a narrower reason:
    :meth:`~plotpress.axes.Axes.legend` draws from already-plotted, labeled
    artists, none of which exist yet on a freshly rebuilt axes -- call
    ``ax.legend(**entry["legend"])`` yourself once you've replotted the
    recovered data into it.
    """
    if idx_of is None:
        idx_of = {id(a): i for i, a in enumerate(fig.axes)}
    axes = {}
    omitted = []
    for i, ax in enumerate(fig.axes):
        spec = ax._subplotspec
        if spec is None or ax._twin_of is not None or ax._secondary_of is not None:
            if not ax._is_colorbar:
                omitted.append(i)
            continue
        axes[i] = _axes_layout_fields(ax)
        axes[i].update(_template_axes_extra(ax))
    groups = [
        {
            "title": g["title"],
            # Only members that are themselves recoverable (present in
            # `axes` above) -- a freeform add_axes() member is real
            # (`id(a) in idx_of`) but has no grid cell of its own, the same
            # reason it's absent from `axes`; leaving it in here would have
            # figure_from_template() try to look it up among axes it was
            # never going to rebuild. `n_members` -- the ORIGINAL count,
            # before this filter -- is what lets that function tell a
            # group apart that lost a member from one that didn't.
            "axes": [idx_of[id(a)] for a in g["axes"]
                    if id(a) in idx_of and idx_of[id(a)] in axes],
            "n_members": len(g["axes"]),
            "id": g.get("id"),
            "linestyle": g["linestyle"], "color": g["color"],
            "linewidth": g["linewidth"], "title_position": g["title_position"],
            "pad": list(g["pad"]), "fontsize": g["fontsize"],
            "supxlabel": g["supxlabel"], "supylabel": g["supylabel"],
            "supxlabel_size": g["supxlabel_size"], "supylabel_size": g["supylabel_size"],
            "visible": g["visible"],
        }
        for g in fig._groups
    ]

    overlays = []
    for i, ax in enumerate(fig.axes):
        if ax._twin_of is not None:
            entry = {"index": i,
                    "kind": "twinx" if ax._twin_shared == "x" else "twiny",
                    "parent": idx_of[id(ax._twin_of)]}
        elif ax._secondary_of is not None:
            is_x = ax._secondary_dim == "x"
            entry = {"index": i,
                    "kind": "secondary_xaxis" if is_x else "secondary_yaxis",
                    "parent": idx_of[id(ax._secondary_of)],
                    "location": ax._xtick_side if is_x else ax._ytick_side}
        else:
            continue
        entry.update(_axes_decoration_fields(ax))
        entry.update(_template_axes_extra(ax))
        overlays.append(entry)

    insets = []
    for i, ax in enumerate(fig.axes):
        if ax._inset_parent is None:
            continue
        entry = {"index": i, "parent": idx_of[id(ax._inset_parent)],
                 "bounds": list(ax._inset_bounds),
                 "projection": "polar" if getattr(ax, "_is_polar", False) else None}
        entry.update(_axes_decoration_fields(ax))
        entry.update(_template_axes_extra(ax))
        insets.append(entry)

    colorbars = []
    for ax in fig.axes:
        if not ax._is_colorbar:
            continue
        entry = {"parents": [idx_of[id(p)] for p in (ax._cbar_parents or [])
                             if id(p) in idx_of],
                 "fraction": ax._cbar_fraction, "pad": ax._cbar_pad,
                 "label": ax._title or None}
        ticks = ax._cbar_ticks
        if ticks is None:
            entry["ticks"] = None
        elif isinstance(ticks, (list, tuple, np.ndarray)):
            entry["ticks"] = [float(v) for v in ticks]
        else:
            entry["ticks"] = None
            warnings.warn(
                "Figure.to_template(): a colorbar's ticks= was not a "
                "plain list -- dropped, since it can't survive JSON.",
                UserWarning, stacklevel=3)
        fmt = ax._cbar_format
        if fmt is None or isinstance(fmt, str):
            entry["format"] = fmt
        else:
            entry["format"] = None
            warnings.warn(
                "Figure.to_template(): a colorbar's format= is a "
                "callable -- dropped, since it can't survive JSON. Pass "
                "a %-style format string instead if this needs to "
                "round-trip through a template.",
                UserWarning, stacklevel=3)
        colorbars.append(entry)

    return {"figsize": list(fig.figsize), "axes": axes, "groups": groups,
           "omitted_axes": omitted,
           "suptitle": fig._suptitle, "supxlabel": fig._supxlabel,
           "supylabel": fig._supylabel, "facecolor": fig.style.facecolor,
           "style": dataclasses.asdict(fig.style),
           "overlays": overlays, "insets": insets, "colorbars": colorbars}


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

    What this actually costs, precisely, since it's easy to read "still
    answers with a real value" as "still answers with *the* value": a click
    on a downsampled cell reads the **mean** of every original cell folded
    into it, not the exact value at the point clicked, and that cell's own
    x/y is the wider block's center, not the original grid's -- both real,
    silent precision losses, not just a coarser click radius. The rendered
    image (never downsampled -- only the pick payload is) gives no visual
    hint that this happened; :func:`pick_data`/:func:`frame_data` warn about
    it instead, once per affected mesh, whenever it actually does.
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
        "kind": "pcolormesh",
        "vmin": float(art.norm.vmin), "vmax": float(art.norm.vmax),
    }
    if (ny, nx) != (ny0, nx0):
        # Internal-only -- frame_data() (the one caller) pops this back off
        # before the entry becomes part of the embedded payload; it's how
        # that caller learns downsampling happened without recomputing
        # ny0/nx0 (and the curvilinear clamping above) itself.
        entry["_downsampled_from"] = (ny0, nx0)
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


def pick_data(fig, max_points=20000, max_mesh_cells=250000, precision=6):
    """Per-axes data payload for point picking (values incl. z and beyond).

    For point series (line/scatter) embeds x, y and any extra named dimensions
    (``pick_values`` such as ``c`` or ``z``). For meshes/contours embeds the z
    grid so a clicked cell reports its value -- block-averaged down to
    ``max_mesh_cells`` for a grid over the cap (see :func:`_downsample_grid`
    for exactly what that costs: a click's z becomes the *mean* of the
    original cells folded into whichever coarser one it landed in, not the
    exact value at that point, and that cell's own x/y coarsens the same
    way), so even a huge mesh always answers a pick with a real value
    instead of falling back to a bare x/y readout. Emits one consolidated
    ``UserWarning`` naming every axes this actually happened to (shape
    before/after, and how to raise the cap) when it does -- the rendered
    image itself never downsamples, so there is otherwise no visual sign
    that a click's precision is coarser than what's drawn. Point series over
    ``max_points`` are still omitted outright (that fallback --
    nearest-vertex geometry -- has no missing-value problem to solve), so
    the HTML stays lean.

    ``precision`` sets the decimal places the embedded arrays are rounded to.
    Lower values shrink the payload (the mesh z grids dominate it); 6 keeps
    full readout fidelity.
    """
    # Local shadow so every _round_list(...) call below honors `precision`
    # without threading it through ~20 call sites.
    def _round_list(a):
        return _rl(a, precision)

    # (axes index, axes title or None, original (ny, nx), downsampled
    # (ny, nx)) for every mesh/contour that actually needed
    # _downsample_grid -- collected instead of warning inline so a figure
    # with several oversized meshes gets one summary, not one warning per
    # mesh (see the warnings.warn call at the end of this function).
    downsampled = []
    data = {}
    for i, ax in enumerate(fig.axes):
        if ax._is_colorbar or not ax._visible:
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
                    "vals": vals, "label": art.label, "color": art.color,
                })
            elif isinstance(art, Stem):
                series.append({"kind": "stem", "x": _round_list(art.x),
                               "y": _round_list(art.y), "vals": {},
                               "label": art.label, "color": art.linecolor})
            elif isinstance(art, ErrorBar):
                vals = {}
                if art.yerr is not None:
                    vals["yerr"] = _round_list(art.yerr)
                if art.xerr is not None:
                    vals["xerr"] = _round_list(art.xerr)
                series.append({"kind": "errorbar", "x": _round_list(art.x),
                               "y": _round_list(art.y), "vals": vals,
                               "label": art.label, "color": art.color})
            elif isinstance(art, Bars):
                if art.orientation == "vertical":
                    xs, ys = art.pos, art.base + art.length
                else:
                    xs, ys = art.base + art.length, art.pos
                # Bars.colors is always a per-bar list (_as_colors()
                # broadcasts a single color to one per bar) -- only when
                # every bar actually shares one color does that collapse to
                # one meaningful "color" here, matching the honest
                # "nothing to preserve" behavior a per-point scatter color
                # already has (see the line/scatter branch above).
                bar_color = (art.colors[0] if art.colors and
                            all(c == art.colors[0] for c in art.colors) else None)
                series.append({"kind": "bar", "x": _round_list(xs),
                               "y": _round_list(ys),
                               "vals": {"value": _round_list(art.length)},
                               "label": art.label, "color": bar_color})
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
                if (ny, nx) != (ny0, nx0):
                    downsampled.append((i, ax.get_title() or None, (ny0, nx0), (ny, nx)))
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
                if (ny, nx) != (ny0, nx0):
                    downsampled.append((i, ax.get_title() or None, (ny0, nx0), (ny, nx)))
                entry = {
                    "extent": [round(xmin, 6), round(xmax, 6),
                               round(ymin, 6), round(ymax, 6)],
                    "shape": [int(ny), int(nx)],
                    "z": _round_list(z),
                    "name": "z",
                    "curvilinear": bool(curvilinear),
                    # Distinguishes a pcolormesh from a plain imshow() for the
                    # interactive Slice tool -- both share this exact entry
                    # shape (z/xedges/yedges), so nothing else here needs to
                    # tell them apart, but Slice reports which kind of axes
                    # it's slicing.
                    "kind": "image" if is_img else "pcolormesh",
                    # The resolved color-scale bounds (after autoscale_none,
                    # so always real floats, whether the caller passed
                    # vmin=/vmax= or let them autoscale from the data) --
                    # exactly what the colorbar itself is drawn against.
                    # Slice's own "fix value axis to colorbar range" option
                    # reads these instead of each slice's own row/column
                    # min/max, so scrubbing through slices doesn't rescale
                    # the axis out from under the reader on every step.
                    "vmin": float(art.norm.vmin), "vmax": float(art.norm.vmax),
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
    if downsampled:
        _warn_downsampled(downsampled, max_mesh_cells)
    return data


def _warn_downsampled(downsampled, max_mesh_cells):
    """One consolidated UserWarning for every mesh/contour pick_data() (or
    frame_data()) had to block-average down to max_mesh_cells -- a caller
    with several oversized meshes gets one summary naming each of them, not
    one warning per mesh.

    Block-averaging (see _downsample_grid) means a click's z reads as the
    *mean* of every original cell folded into whichever coarser cell it
    landed in, not the exact value at the point clicked -- and that
    coarser cell's own x/y is wider too, so nearby clicks can resolve to
    the same pick, or skip past an original cell entirely, well before the
    rendered image (still full resolution) visually suggests either.
    Real, silent precision loss, not just a coarser click radius -- worth a
    warning on every save it happens on, not just a line in a docstring
    nobody reads until they already suspect something is off.
    """
    lines = []
    for i, title, (ny0, nx0), (ny, nx) in downsampled:
        label = f"axes {i}" + (f" ({title!r})" if title else "")
        lines.append(f"  {label}: {ny0}x{nx0} ({ny0 * nx0:,} cells) "
                      f"-> {ny}x{nx} ({ny * nx:,} cells)")
    warnings.warn(
        "Point Picking's embedded data is coarser than what's drawn for "
        f"{len(downsampled)} mesh/contour "
        f"{'panel' if len(downsampled) == 1 else 'panels'} over "
        f"pick_max_mesh_cells={max_mesh_cells:,} -- each was block-averaged "
        "down (a click reads the *mean* of the original cells folded into "
        "the one it landed in, not the exact value at that point):\n"
        + "\n".join(lines) +
        "\nPass a higher pick_max_mesh_cells= to Figure.save()/to_html() "
        "for full-resolution picking, at the cost of a larger embedded "
        "payload.",
        UserWarning, stacklevel=3)


def frame_data(fig, max_mesh_cells=250000):
    """Per-axes slider-frame data for JS to redraw on scrub: all frames' x/Y
    for a line, or every frame's rendered image (for JS to swap in) plus its
    z grid (for picking) for a mesh.

    A mesh's z grid is block-averaged down to ``max_mesh_cells`` the same
    way :func:`pick_data`'s does when it's over the cap -- see that
    function's own docstring, and :func:`_downsample_grid`, for exactly
    what a downsampled pick costs. Every frame shares one grid, so whether
    downsampling happened is identical frame to frame; the ``UserWarning``
    that names it fires once per animated mesh here, not once per frame.
    """
    downsampled = []   # see the matching list in pick_data() above
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
                        # Every frame shares one grid, so downsampling (if
                        # any) is identical frame to frame too -- check once,
                        # on frame 0, rather than once per frame.
                        orig_shape = entry.pop("_downsampled_from", None)
                        if orig_shape is not None:
                            downsampled.append(
                                (i, ax.get_title() or None, orig_shape, tuple(entry["shape"])))
                        geom = entry
                mesh_entry = {"id": f"s{i}_{k}", "unit": art.slider_unit,
                              "hrefs": hrefs, "z": zs}
                if geom is not None:
                    mesh_entry.update(geom)
                entries.append(mesh_entry)
        if entries:
            frames[i] = entries
    if downsampled:
        _warn_downsampled(downsampled, max_mesh_cells)
    return frames
