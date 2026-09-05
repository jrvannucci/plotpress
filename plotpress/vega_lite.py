"""Export a Figure as a real Vega-Lite v5 JSON specification.

Vega-Lite is a stricter, more declarative grammar than Vega -- a closed mark
vocabulary (``line``/``bar``/``point``/``arc``/``errorbar``/``area``/``rule``/
``text``/... -- no raw path-with-literal-d mark the way Vega has) and a
grid-like composition model (``hconcat``/``vconcat``), not Vega's arbitrary
pixel-positioned ``group`` marks. Both are real, structural mismatches with
plotpress's own ``Figure``/``Axes`` model, not just missing artist-type
coverage the way most of :mod:`plotpress.vega`'s gaps were -- so this module
is honest about three separate kinds of gap, not one:

**Tier 1 -- native mark, direct field mapping.** ``Line2D``, ``ScatterCollection``,
``Bars``, ``ErrorBar`` (Vega-Lite's own ``errorbar`` mark, with precomputed
``yError``/``xError`` fields -- genuinely simpler than :mod:`plotpress.vega`'s
hand-built whisker/cap geometry), ``Pie`` (Vega-Lite's ``arc`` mark
auto-stacks ``theta``, no manual per-wedge trig), a monotonic-x two-boundary
``FillBetween`` (Vega-Lite's ``area`` mark), and ``QuadMesh``/``Image``
(``pcolormesh``/``imshow``) as a real ``image`` mark, reusing the same
rasterized RGBA + data extent every other backend already computes rather
than re-deriving anything. Log/inverted/custom-tick axis properties map
onto Vega-Lite's own ``encoding.<channel>.scale``/``.axis``.

**Tier 2 -- a layered workaround within Vega-Lite's own vocabulary,** more
code, more fragile: reference lines/spans (``VLine``/``HLine``/``AxLine``/
``Span``) and ``LineCollection`` (``hlines()``/``vlines()``, violin inner
quartile/whisker lines, ``acorr()``/``xcorr()``) via a tiny inline literal
dataset, since Vega-Lite has no scale-independent constant shorthand the way
Vega's ``{"value": ...}`` is; ``Rug`` the same way, plus a literal *pixel*
value (not a data scale) for its fixed-fraction tick length; ``Stem`` (three
layers: stems, baseline, tips); dashed lines (a plain ``strokeDash`` mark
property); simple ``Text``/``Annotation`` with no ``bbox``/arrow; custom tick
*labels* via ``axis.labelExpr`` (capped at ~12 ticks -- fragile past that);
pie wedge labels/``autopct`` (frozen per-wedge positions via a real Vega-Lite
``area`` mark, and an explicit arc center/radius the labels are positioned
against, rather than trusting Vega-Lite's own undocumented auto-sizing --
same trig walk :mod:`plotpress.vega`'s ``_pie_marks`` uses); ``Polygon``
(``fill()``, and critically ``fill_betweenx()`` -- built the same
forward-one-boundary-back-the-other way as ``fill_between()`` internally,
see ``axes.py``) as a real ``area`` mark, but *only* when the polygon
actually has that two-boundary-strip shape -- detected structurally, not
by which call built it.

**Tier 3 -- no reasonable mapping, warns and skips** (the same
"degrade a part, not the whole" policy :func:`plotpress.vega.figure_to_vega`
already follows): everything already unsupported there (``BoxPlot``,
``Violin``, ``Quiver``, ``Contour``, ``EventPlot``, ``Barbs``, ``Table``,
the slider-driven ``FrameLine2D``/``FrameQuadMesh``, legends), plus
``PolyCollection`` (no closed-vocabulary polygon-batch mark),
a non-monotonic ``FillBetween``, a ``Polygon`` that isn't a two-boundary
strip (an arbitrary closed ``fill()`` shape -- a filled circle, a hexbin
cell -- has no Vega-Lite closed-vocabulary mark either), annotation
*arrows* specifically (kept as text, the arrow itself has no Vega-Lite
mark), and ``Figure.group()`` boxes (no cross-panel drawing surface in
Vega-Lite's per-view composition at all).

**The figure-level composition problem** is the one Vega itself never
forced: plotpress allows arbitrary grid spans, ``add_axes()`` free rects,
``inset_axes()``, ``twinx()``/``twiny()``, secondary axes, and colorbar
axes, none of which ``hconcat``/``vconcat`` can express as freely as a Vega
``group`` mark's own explicit pixel position can. :func:`figure_to_vega_lite`
partitions a figure's axes into what composes cleanly into one nested
``hconcat``/``vconcat`` grid, a twin merged into its parent's own view via
Vega-Lite's ``resolve.scale`` independence, and everything else exported as
an independent standalone spec rather than forced into a layout Vega-Lite
was never asked to represent -- see that function's own docstring for the
exact algorithm and the return shape.
"""

from __future__ import annotations

import math
import warnings

import numpy as np

from .artists import (
    AxLine, Bars, ErrorBar, FillBetween, HLine, Image, Line2D, LineCollection,
    Pie, Polygon, QuadMesh, Rug, ScatterCollection, Span, Stem, Text,
    Annotation, VLine,
)
from .png import png_data_uri
from .svg import _effective_rect, _pixel_rect
from .vega import (
    _color, _dash_array, _mesh_cell_rows, _mesh_data_reason, _mesh_scheme,
    _symbol_size,
)

_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"

# Artist kinds with a Tier-1/Tier-2 mapping below; anything else falls
# through to the generic "no Vega-Lite mapping yet" warning, mirroring
# plotpress.vega's own artist_to_prims() fallback -- except this module has
# no shared pixel-space fallback layer to reuse (Vega-Lite's mark
# vocabulary is closed), so unmapped here really does mean unmapped.
_UNSUPPORTED_NAMES = (
    "box plots, violins, quiver, contour, event plots, wind barbs, tables, "
    "arbitrary polygon batches (e.g. hexbin), and plot_frames()/"
    "pcolormesh_frames() sliders"
)

# The one aggregate structural warning figure_to_vega_lite() emits, exposed
# so a caller (docs/conf.py's own Vega-Lite page) can recognize and skip it
# when it's already showing the same `caveats` list individually, rather
# than duplicating every entry as one more warning-derived bullet.
_STRUCTURAL_WARNING_PREFIX = (
    "figure_to_vega_lite(): this figure's structure isn't fully "
    "captured in the Vega-Lite result -- "
)


def figure_to_vega_lite(fig, mesh_data: bool = False) -> tuple[dict, list[str]]:
    """Build a Vega-Lite v5 spec for ``fig``.

    Returns ``(result, caveats)`` -- **not** a bare ``dict`` the way
    :meth:`~plotpress.figure.Figure.to_vega`/``to_svg``/``to_html`` are, a
    deliberate, documented asymmetry (see :meth:`~plotpress.figure.Figure.to_vega_lite`).
    ``result`` is ``{"grid": <spec> | None, "standalone": [<spec>, ...]}``:

    - ``"grid"`` is one combined ``hconcat``/``vconcat`` spec covering every
      axes that shares one consistent grid shape (see
      :func:`_is_cleanly_composable`), or ``None`` if no such grid exists
      (e.g. a single-axes figure, or a figure whose axes don't share one
      shape at all).
    - ``"standalone"`` is a list of independent specs for everything that
      couldn't join the grid: a single axes with nothing to grid against,
      axes from a mismatched-shape grid, and any axes Vega-Lite's own
      composition model has no slot for at all (``add_axes()`` free rects,
      ``inset_axes()``, secondary axes) -- a **twin** (``twinx``/``twiny``)
      is the one exception, merged into its parent's own spec as an extra
      ``layer`` with an independent scale on the shared channel
      (``resolve.scale.y: "independent"`` for ``twinx``, ``.x`` for
      ``twiny`` -- whichever axis the twin doesn't share) instead, since
      dropping an entire overlaid series is the worst of the fallbacks
      available. A colorbar axes has no artists of its own to export at
      all (``fig.colorbar()`` draws it through a separate path ``svg.py``
      reads, not ``ax.artists``) and no Vega-Lite gradient-legend mark to
      stand in for it, so it is simply dropped, with a caveat -- it never
      reaches ``"standalone"``.

    ``caveats`` lists every structural compromise made building the result
    (a dropped entangled axes, a grid-shape mismatch forcing the standalone
    list, a polar axes losing its aspect lock) -- data for a caller
    deciding what to do with a partially-composed figure, not just console
    noise. Every entry is also re-emitted as a ``UserWarning`` (one
    aggregate message), so a caller who ignores the tuple return still sees
    the same warning :func:`~plotpress.vega.figure_to_vega` callers already
    rely on. Per-artist-type and per-legend gaps (see the module docstring's
    Tier 3) warn individually instead, matching that function's own
    convention exactly.
    """
    dpi = fig.style.dpi
    size_scale = dpi / 72.0
    caveats: list[str] = []

    # A colorbar axes is never a grid/span member (it steals its rect from
    # an existing axes, not a fresh grid cell) -- it falls into
    # entangled_axes below like add_axes()/inset_axes(), NOT dropped
    # outright, so it still gets a standalone spec and a caveat.
    visible = [(i, ax) for i, ax in enumerate(fig.axes) if ax._visible]
    grid_axes, span_axes, entangled_axes = [], [], []
    for i, ax in visible:
        if _is_cleanly_composable(ax):
            grid_axes.append((i, ax))
        elif (ax._subplotspec is not None and ax._twin_of is None
              and ax._secondary_of is None and ax._inset_parent is None
              and not ax._is_colorbar):
            span_axes.append((i, ax))
        else:
            entangled_axes.append((i, ax))

    standalone: list[dict] = []
    grid_spec = None

    composable = grid_axes + span_axes
    if composable:
        shapes = {(ax._subplotspec.nrows, ax._subplotspec.ncols) for _, ax in composable}
        if len(shapes) == 1:
            grid_spec, span_caveats = _build_grid(composable, fig, size_scale, mesh_data)
            caveats.extend(span_caveats)
        else:
            caveats.append(
                f"{len(composable)} axes span {len(shapes)} different grid shapes "
                "(mixed add_subplot() calls on one figure) -- Vega-Lite's "
                "hconcat/vconcat composition needs one consistent shape, so "
                "each axes was exported as its own independent spec instead "
                "of one combined grid."
            )
            for _, ax in composable:
                spec, axcav = _axes_to_vl_spec(ax, size_scale, mesh_data)
                caveats.extend(axcav)
                if spec is not None:
                    standalone.append(spec)

    # Twins merge into their parent's own spec (already built above, inside
    # a grid cell or a standalone spec) as an extra layer -- find the
    # parent's spec and append rather than dropping the whole series.
    twins = [(i, ax) for i, ax in entangled_axes if ax._twin_of is not None]
    other_entangled = [(i, ax) for i, ax in entangled_axes if ax._twin_of is None]
    for i, ax in twins:
        merged = _merge_twin(ax, grid_spec, standalone, size_scale, mesh_data)
        if not merged:
            caveats.append(
                f"axes {i} is a twinx()/twiny() overlay whose parent axes "
                "wasn't found in the composed output (an unusual layout) -- "
                "exported as its own independent spec instead of merged."
            )
            spec, axcav = _axes_to_vl_spec(ax, size_scale, mesh_data)
            caveats.extend(axcav)
            if spec is not None:
                standalone.append(spec)

    for i, ax in other_entangled:
        if ax._is_colorbar:
            # A colorbar axes has no artists of its own (fig.colorbar()
            # draws it via a separate _cbar_source/_cbar_parents-reading
            # path, not ax.artists -- see svg.py's _render_colorbar), so
            # _axes_to_vl_spec always finds nothing exportable here. Say so
            # plainly rather than claim it was "exported independently"
            # when nothing actually was.
            caveats.append(
                f"axes {i} is a colorbar -- Vega-Lite has no standalone "
                "gradient-legend mark to export it as, so it was dropped."
            )
            continue
        kind = ("an inset_axes()" if ax._inset_parent is not None else
                "a secondary_xaxis()/secondary_yaxis()" if ax._secondary_of is not None else
                "a free-form add_axes() rect")
        caveats.append(
            f"axes {i} is {kind} -- Vega-Lite's hconcat/vconcat composition "
            "has no way to position it relative to the other axes, so it "
            "was exported as its own independent spec."
        )
        spec, axcav = _axes_to_vl_spec(ax, size_scale, mesh_data)
        caveats.extend(axcav)
        if spec is not None:
            standalone.append(spec)

    if caveats:
        warnings.warn(
            _STRUCTURAL_WARNING_PREFIX + " ".join(caveats),
            UserWarning, stacklevel=2,
        )
    return {"grid": grid_spec, "standalone": standalone}, caveats


def _vega_lite_has_content(result) -> bool:
    """True if ``result`` (the first element of :func:`figure_to_vega_lite`'s
    return) has at least one spec worth a reader's click -- mirrors
    :func:`plotpress.vega._vega_has_content`'s role for the plain-Vega
    export's own docs page.
    """
    return result["grid"] is not None or bool(result["standalone"])


def _is_cleanly_composable(ax) -> bool:
    """True if ``ax`` is a single, plain grid cell -- see the module
    docstring's composition section. ``_subplotspec`` alone is NOT enough:
    ``twinx()``/``twiny()``/``secondary_xaxis()``/``secondary_yaxis()`` all
    *copy* their parent's ``_subplotspec`` verbatim (axes.py's ``twinx``/
    ``twiny``/``secondary_xaxis``/``secondary_yaxis``), so a twin looks like
    an ordinary grid cell by that check alone -- ``_twin_of``/
    ``_secondary_of``/``_inset_parent`` must all be ``None`` too.
    """
    ss = ax._subplotspec
    return (ss is not None and ss.row0 == ss.row1 and ss.col0 == ss.col1
            and ax._twin_of is None and ax._secondary_of is None
            and ax._inset_parent is None and not ax._is_colorbar)


def _build_grid(composable, fig, size_scale, mesh_data=False):
    """One combined spec: an outer ``vconcat`` of rows, each an inner
    ``hconcat`` of that row's cells -- ``composable`` all share one grid
    shape (checked by the caller). A multi-cell span gets an explicit
    pixel ``width``/``height`` covering its cells (Vega-Lite's concat was
    never designed for asymmetric spans -- flagged as a caveat, not treated
    as an error, since the result is still visually proportioned right).
    """
    nrows, ncols = composable[0][1]._subplotspec.nrows, composable[0][1]._subplotspec.ncols
    dpi = fig.style.dpi
    W, H = fig.figsize[0] * dpi, fig.figsize[1] * dpi
    by_cell = {}
    caveats = []
    for i, ax in composable:
        ss = ax._subplotspec
        # This call chain (figure_to_vega_lite -> _build_grid ->
        # _axes_to_vl_spec -> _artist_layers) is one frame deeper than the
        # standalone/twin paths' stacklevel=4 default was tuned for, so
        # pass 5 to still blame figure_to_vega_lite's own caller rather
        # than a line inside _build_grid itself.
        spec, axcav = _axes_to_vl_spec(ax, size_scale, mesh_data, stacklevel=5)
        caveats.extend(axcav)
        if spec is None:
            continue
        if ss.row0 != ss.row1 or ss.col0 != ss.col1:
            caveats.append(
                f"axes {i} spans rows {ss.row0}-{ss.row1}/cols {ss.col0}-{ss.col1} -- "
                "Vega-Lite's hconcat/vconcat has no true spanning cell, so "
                f"it was placed once, at its own top-left cell (row {ss.row0}, "
                f"col {ss.col0}); the rest of the cells it would otherwise "
                "also cover are simply left empty, given an explicit pixel "
                "width/height so it's still sized right."
            )
            _, _, w, h = _pixel_rect(ax, W, H)
            spec["width"], spec["height"] = round(float(w), 2), round(float(h), 2)
        # A span is placed ONCE, at its own top-left cell -- Vega-Lite's
        # hconcat/vconcat has no way to merge a cell across several rows/
        # columns the way a real grid-spanning panel does, and inserting
        # the SAME spec dict into every cell it covers (the original,
        # buggy version of this) rendered it duplicated side by side
        # instead of spanning, confirmed by an actual is/is-not identity
        # check on the resulting hconcat list.
        by_cell[(ss.row0, ss.col0)] = spec
    rows = []
    for r in range(nrows):
        row_specs = [by_cell[(r, c)] for c in range(ncols) if (r, c) in by_cell]
        if row_specs:
            rows.append({"hconcat": row_specs} if len(row_specs) > 1 else row_specs[0])
    if not rows:
        return None, caveats
    grid = {"vconcat": rows} if len(rows) > 1 else rows[0]
    grid["$schema"] = _SCHEMA
    return grid, caveats


def _merge_twin(ax, grid_spec, standalone, size_scale, mesh_data=False):
    """Merge a twin axes' marks into its parent's own spec as an extra
    ``layer``, with an independent scale on whichever axis the twin does
    NOT share with its parent (real, documented Vega-Lite grammar for
    exactly this dual-axis case) -- returns True if the parent spec was
    found and merged into, False if not (caller falls back to a
    standalone spec).
    """
    parent = ax._twin_of
    target = _find_spec_for_axes(parent, grid_spec) or _find_spec_for_axes(parent, standalone)
    if target is None:
        return False
    layers, caveats = _artist_layers(ax, size_scale, mesh_data)
    if not layers:
        return True
    # Every spec _axes_to_vl_spec builds already has a top-level "layer"
    # list (that function returns None outright rather than a spec with
    # none) -- ax's own parent spec, found via _find_spec_for_axes, is
    # always one of those, so there's no "not yet layered" case to handle.
    target["layer"].extend(layers)
    # twinx() shares x, wants an independent y; twiny() shares y, wants an
    # independent x (axes.py's _twin_shared: "x" for twinx, "y" for
    # twiny) -- the independent channel is the one NOT shared.
    independent = "y" if ax._twin_shared == "x" else "x"
    target["resolve"] = {"scale": {independent: "independent"}}
    return True


def _find_spec_for_axes(ax, container):
    """Locate the single-view (or already-layered) spec built for ``ax``
    inside ``container`` (one spec, a ``vconcat``/``hconcat`` tree, or a
    list of specs) by the ``name`` every :func:`_axes_to_vl_spec` result
    carries (``f"axes{id(ax):x}"``, matching the ``f"data_{id(art):x}"``
    per-object-identity naming convention :mod:`plotpress.vega` already
    uses) -- the one piece of bookkeeping needed so a twin's merge target
    can be found again after the grid/standalone assembly above.
    """
    if container is None:
        return None
    name = f"axes{id(ax):x}"
    specs = container if isinstance(container, list) else [container]
    stack = list(specs)
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if node.get("name") == name:
            return node
        stack.extend(node.get("hconcat", []))
        stack.extend(node.get("vconcat", []))
    return None


# ---- one axes -> one Vega-Lite spec ------------------------------------

def _axes_to_vl_spec(ax, size_scale, mesh_data=False, stacklevel=4):
    """One axes' own content as a single-view (or layered) Vega-Lite spec,
    or ``(None, caveats)`` if nothing on it was exportable (mirrors
    :func:`plotpress.vega._vega_has_content`'s role for the Vega sibling).

    ``stacklevel`` is forwarded to :func:`_artist_layers` unchanged --
    this function adds no warning of its own, so it doesn't need to shift
    it, only pass along whatever depth its own caller (``_build_grid`` or
    ``figure_to_vega_lite`` directly) is at.
    """
    layers, caveats = _artist_layers(ax, size_scale, mesh_data, stacklevel)
    if not layers:
        return None, caveats
    fig = ax.figure
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    # _effective_rect, not the raw _pixel_rect -- set_aspect("equal")/
    # set_box_aspect() shrink the actually-used plotting box (centered
    # within the allocated cell), the same adjustment plotpress.vega's own
    # _axes_to_group already applies. Skipping it here left every
    # aspect-locked axes' view sized to its full *unadjusted* cell instead,
    # squashing/stretching everything drawn on it relative to what
    # set_aspect asked for -- confirmed by comparing a curvilinear,
    # aspect="equal" mesh's rendering against plotpress's own output,
    # where the mismatch showed up as the mesh's pattern appearing shifted
    # relative to its axis ticks, not just resized.
    xlim, ylim = ax._resolved_limits()
    _, _, w, h = _effective_rect(ax, *_pixel_rect(ax, W, H), xlim, ylim)
    spec = {
        "name": f"axes{id(ax):x}",
        "width": round(float(w), 2), "height": round(float(h), 2),
        "layer": layers,
    }
    if ax._title:
        spec["title"] = ax._title
    return spec, caveats


def _xy_axis(ax):
    """The ``x``/``y`` scale+axis portion of every layer's own encoding --
    repeated on each layer rather than hoisted to the spec's shared
    top-level ``encoding`` (layers here often carry different field names
    for the same channel, e.g. Bars' precomputed ``x0``/``x1`` vs. Line's
    plain ``x``), since Vega-Lite still shares/unions same-channel scales
    across layers by default regardless of where the scale properties are
    declared -- explicit ``domain`` on each layer keeps every layer showing
    the exact view plotpress itself already resolved, not Vega-Lite's own
    independently-recomputed auto-domain.
    """
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    caveats = []

    def axis_for(scale, inverted, ticks, ticklabels, label, grid):
        enc = {"type": "quantitative"}
        s = {"type": "log" if scale == "log" else "linear", "zero": False}
        if inverted:
            s["reverse"] = True
        enc["scale"] = s
        a = {"grid": bool(grid), "title": label or None}
        if ticks is not None:
            tvals = [float(t) for t in ticks]
            a["values"] = tvals
            if ticklabels is not None:
                if len(tvals) <= 12:
                    labels = list(ticklabels)[:len(tvals)]
                    labels += [""] * (len(tvals) - len(labels))
                    expr = " : ".join(
                        f"datum.value == {t!r} ? {lab!r}" for t, lab in zip(tvals, labels)
                    ) + " : ''"
                    a["labelExpr"] = expr
                else:
                    caveats.append(
                        "custom tick labels on an axis with more than 12 ticks "
                        "-- Vega-Lite's per-tick labelExpr gets impractically "
                        "long past that, so default numeric labels were kept "
                        "instead."
                    )
        enc["axis"] = None if ax._axis_off else a
        return enc

    x_enc = axis_for(ax._xscale, ax._xinverted, ax._xticks, ax._xticklabels,
                     ax._xlabel, ax._grid)
    x_enc["scale"]["domain"] = [float(xmin), float(xmax)]
    y_enc = axis_for(ax._yscale, ax._yinverted, ax._yticks, ax._yticklabels,
                     ax._ylabel, ax._grid)
    y_enc["scale"]["domain"] = [float(ymin), float(ymax)]
    return x_enc, y_enc, caveats


def _artist_layers(ax, size_scale, mesh_data=False, stacklevel=4):
    """``stacklevel`` defaults to the depth that's correct when this is
    reached via ``figure_to_vega_lite -> _axes_to_vl_spec -> _artist_layers``
    or ``figure_to_vega_lite -> _merge_twin -> _artist_layers`` (3 frames
    below the caller of ``figure_to_vega_lite`` itself) -- ``_build_grid``'s
    own call chain is one frame deeper (it goes through ``_axes_to_vl_spec``
    too) and passes ``stacklevel=5`` to compensate, so the warning still
    blames the real external caller instead of a line inside this module.
    """
    layers, caveats = [], []
    draw_order = sorted(enumerate(ax.artists), key=lambda ka: (ka[1].zorder, ka[0]))
    for k, art in draw_order:
        if isinstance(art, ScatterCollection):
            l, c = _scatter_layer(art, ax, size_scale)
        elif isinstance(art, Line2D):
            l, c = _line_layer(art, ax, size_scale)
        elif isinstance(art, Bars):
            l, c = _bars_layer(art, ax)
        elif isinstance(art, ErrorBar):
            l, c = _errorbar_layers(art, ax, size_scale)
        elif isinstance(art, Stem):
            l, c = _stem_layers(art, ax)
        elif isinstance(art, Pie):
            l, c = _pie_layers(art, ax)
        elif isinstance(art, (VLine, HLine, AxLine)):
            l, c = _refline_layer(art, ax)
        elif isinstance(art, Span):
            l, c = _span_layer(art, ax)
        elif isinstance(art, FillBetween):
            l, c = _fillbetween_layer(art, ax)
        elif isinstance(art, LineCollection):
            l, c = _line_collection_layer(art, ax)
        elif isinstance(art, Polygon):
            l, c = _polygon_layer(art, ax)
        elif isinstance(art, Rug):
            l, c = _rug_layer(art, ax)
        elif isinstance(art, (Text, Annotation)):
            l, c = _text_layer(art, ax)
        elif isinstance(art, (QuadMesh, Image)):
            l, c = _mesh_layer(art, ax, mesh_data)
        else:
            warnings.warn(
                f"figure_to_vega_lite(): axes {_axes_index(ax)} has a "
                f"{type(art).__name__} artist with no Vega-Lite mapping yet "
                f"({_UNSUPPORTED_NAMES}) -- skipped, the rest of the figure "
                "still exports.", UserWarning, stacklevel=stacklevel,
            )
            l, c = [], []
        layers.extend(l)
        caveats.extend(c)
    if ax._show_legend:
        warnings.warn(
            f"figure_to_vega_lite(): axes {_axes_index(ax)} has a legend, "
            "which to_vega_lite() does not export yet -- skipped.",
            UserWarning, stacklevel=stacklevel,
        )
    return layers, caveats


def _axes_index(ax):
    try:
        return ax.figure.axes.index(ax)
    except ValueError:
        return "?"


# ---- Tier 1: native mark, direct field mapping -------------------------

def _line_layer(art, ax, size_scale):
    if art.linestyle == "none" and art.marker is None:
        return [], []
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return [], []
    x_enc, y_enc, caveats = _xy_axis(ax)
    # linestyle="none" with a marker (matplotlib's "markers only" idiom,
    # e.g. plot(x, y, marker="o", linestyle="none")) needs a `point`-only
    # mark, not a `line` mark with a `point: true` sub-mark -- the latter
    # still draws a solid connecting line regardless of dash settings
    # (_dash_array("none") has nothing to suppress it with), confirmed by
    # actually rendering: a marker-only plot came out with a spurious
    # solid line joining every point.
    if art.linestyle == "none":
        values = [{"x": float(xv), "y": float(yv)} for xv, yv in zip(x[finite], y[finite])]
        diam = float(art.markersize or 6.0) * size_scale
        mark = {"type": "point", "filled": True,
                "color": _color(art.markerfacecolor or art.color),
                "size": _symbol_size(diam), "opacity": float(art.alpha)}
        layer = {"data": {"values": values}, "mark": mark,
                 "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y")}}
        return [layer], caveats
    # A non-finite point becomes a null field value, not a dropped row --
    # Vega-Lite's own default "invalid data" handling for line/area marks
    # (config.mark.invalid, default "break-paths-filter-domains") breaks
    # the path at a null exactly the way plotpress.vega's `defined` channel
    # does for raw Vega, so no manual gap-splitting is needed here.
    values = [{"idx": i, "x": float(xv) if fv else None, "y": float(yv) if fv else None}
             for i, (xv, yv, fv) in enumerate(zip(x, y, finite))]
    mark = {"type": "line", "color": _color(art.color),
            "strokeWidth": float(art.linewidth), "opacity": float(art.alpha)}
    dash = _dash_array(art.linestyle)
    if dash:
        mark["strokeDash"] = dash
    if art.marker is not None:
        mark["point"] = True
    layer = {"data": {"values": values}, "mark": mark,
             "encoding": {
                 "x": dict(x_enc, field="x"), "y": dict(y_enc, field="y"),
                 # Vega-Lite's default line-mark point order sorts by the x
                 # field -- fine for the overwhelmingly common monotonic-x
                 # case, but a parametric/non-monotonic-x line (e.g.
                 # ax.plot(sin(t), t)) came out as a zigzag connecting
                 # points in x-sorted order instead of data order, confirmed
                 # by actually rendering one. `order` pins it back, the same
                 # fix already applied to _pie_layers for the analogous
                 # stack-order default.
                 "order": {"field": "idx", "type": "ordinal"},
             }}
    return [layer], caveats


def _scatter_layer(art, ax, size_scale):
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return [], []
    fc = art.face_colors()
    colors = fc if fc is not None else [_color(art.color)] * x.size
    s = np.broadcast_to(np.asarray(art.s, float), x.shape) * size_scale
    values = [
        {"x": float(xv), "y": float(yv), "size": _symbol_size(sv), "color": cv}
        for xv, yv, sv, cv, fv in zip(x, y, s, np.asarray(colors, dtype=object), finite)
        if fv
    ]
    x_enc, y_enc, caveats = _xy_axis(ax)
    layer = {
        "data": {"values": values},
        "mark": {"type": "point", "filled": True, "opacity": float(art.alpha)},
        "encoding": {
            "x": dict(x_enc, field="x"), "y": dict(y_enc, field="y"),
            "size": {"field": "size", "type": "quantitative", "legend": None},
            "color": {"field": "color", "type": "nominal", "scale": None,
                     "legend": {"title": None} if len(set(colors)) > 1 else None},
        },
    }
    return [layer], caveats


def _bars_layer(art, ax):
    if art.pos.size == 0:
        return [], []
    vals = []
    for pos, length, thick, base, color in zip(art.pos, art.length, art.thickness,
                                                art.base, art.colors):
        hexc = _color(color)
        if art.orientation == "vertical":
            vals.append({"x0": float(pos - thick / 2), "x1": float(pos + thick / 2),
                        "y0": float(base), "y1": float(base + length), "color": hexc})
        else:
            vals.append({"x0": float(base), "x1": float(base + length),
                        "y0": float(pos - thick / 2), "y1": float(pos + thick / 2), "color": hexc})
    x_enc, y_enc, caveats = _xy_axis(ax)
    mark = {"type": "bar", "opacity": float(art.alpha)}
    if art.edgecolor:
        mark["stroke"] = _color(art.edgecolor)
        mark["strokeWidth"] = float(art.linewidth)
    # set() on the resolved hex strings in `vals`, not on art.colors
    # directly -- art.colors can be a list of raw per-bar RGB(A) numpy
    # arrays (Bars._as_colors() passes an array of color rows straight
    # through), which are unhashable and crash set().
    layer = {
        "data": {"values": vals}, "mark": mark,
        "encoding": {
            # x2/y2 in Vega-Lite take only field/datum, no scale/axis of
            # their own (they ride the x/y channel's own scale), so only
            # x/y carry the full scale+axis encoding from _xy_axis().
            "x": dict(x_enc, field="x0"), "x2": {"field": "x1"},
            "y": dict(y_enc, field="y0"), "y2": {"field": "y1"},
            "color": {"field": "color", "type": "nominal", "scale": None,
                     "legend": {"title": None} if len({v["color"] for v in vals}) > 1 else None},
        },
    }
    return [layer], caveats


def _errorbar_layers(art, ax, size_scale):
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return [], []
    x_enc, y_enc, caveats = _xy_axis(ax)
    layers = []
    color = _color(art.color)
    # capsize == 0 means no caps (matches svg.py:1547's own `cap = eb.capsize`
    # convention, where a zero cap length draws a zero-length tick, visually
    # nothing) -- Vega-Lite's `ticks` sub-mark defaults to *off*, and was
    # previously forced on unconditionally regardless of capsize.
    eb_mark = {"type": "errorbar", "color": _color(art.ecolor),
              "opacity": float(art.alpha),
              "rule": {"strokeWidth": float(art.elinewidth)}}
    if art.capsize:
        eb_mark["ticks"] = {"strokeWidth": float(art.capthick)}
    if art.yerr is not None:
        yerr = np.asarray(art.yerr, float)
        vals = [{"x": float(xv), "y": float(yv), "yerr": float(e)}
               for xv, yv, e, fv in zip(x, y, yerr, finite) if fv]
        layers.append({
            "data": {"values": vals}, "mark": dict(eb_mark),
            "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y"),
                        "yError": {"field": "yerr", "type": "quantitative"}},
        })
    if art.xerr is not None:
        xerr = np.asarray(art.xerr, float)
        vals = [{"x": float(xv), "y": float(yv), "xerr": float(e)}
               for xv, yv, e, fv in zip(x, y, xerr, finite) if fv]
        layers.append({
            "data": {"values": vals}, "mark": dict(eb_mark),
            "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y"),
                        "xError": {"field": "xerr", "type": "quantitative"}},
        })
    if art.linestyle and art.linestyle != "none":
        lvals = [{"x": float(xv) if fv else None, "y": float(yv) if fv else None}
                for xv, yv, fv in zip(x, y, finite)]
        mark = {"type": "line", "color": color, "strokeWidth": float(art.linewidth),
                "opacity": float(art.alpha)}
        dash = _dash_array(art.linestyle)
        if dash:
            mark["strokeDash"] = dash
        layers.append({"data": {"values": lvals}, "mark": mark,
                       "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y")}})
    values = [{"x": float(xv), "y": float(yv)} for xv, yv in zip(x[finite], y[finite])]
    layers.append({
        "data": {"values": values},
        "mark": {"type": "point", "filled": True, "color": color,
                "size": _symbol_size(float(art.markersize) * size_scale),
                "opacity": float(art.alpha)},
        "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y")},
    })
    return layers, caveats


def _pie_layers(art, ax):
    # Pie draws in fixed axes-pixel space, independent of any x/y data
    # scale (see plotpress.vega's own _pie_marks) -- Vega-Lite's `arc` mark
    # is the same story: it has no x/y quantitative encoding at all, just
    # theta/radius, so this deliberately does NOT call _xy_axis() the way
    # every other builder does. A pie sharing an axes with an x/y-scaled
    # artist (unusual -- ax.pie() calls set_axis_off(), so it is almost
    # always the axes' only content) would produce a layer with no x/y
    # scale mixed with ones that have one; Vega-Lite handles that by simply
    # not resolving x/y for the arc layer, which is correct here since the
    # arc genuinely has no data-space position to share.
    values = [{"idx": i, "value": float(v), "color": _color(c)}
             for i, (v, c) in enumerate(zip(art.fracs, art.colors))]
    # Explicit center/radius (plotpress.vega's own _pie_marks formula,
    # mirroring svg.py's _render_pie) rather than leaving Vega-Lite's own
    # arc mark to auto-center/auto-size itself -- needed so the label/pct
    # text below can be placed at a center and radius it actually knows,
    # not one it would have to guess at from Vega-Lite's undocumented
    # default arc sizing.
    fig = ax.figure
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    xlim, ylim = ax._resolved_limits()
    _, _, px_w, px_h = _effective_rect(ax, *_pixel_rect(ax, W, H), xlim, ylim)
    cx, cy = px_w / 2.0, px_h / 2.0
    R = 0.42 * min(px_w, px_h) * art.radius
    layers = [{
        "data": {"values": values},
        "mark": {"type": "arc", "opacity": float(art.alpha), "stroke": "#ffffff",
                "strokeWidth": 1.5},
        "encoding": {
            "theta": {"field": "value", "type": "quantitative", "stack": True},
            "color": {"field": "color", "type": "nominal", "scale": None, "legend": None},
            # Vega-Lite's default stack order for a nominal color field
            # sorts BY that field (here, ascending hex string) rather than
            # keeping row/input order -- confirmed by actually rendering:
            # wedge angular sizes came out right but which wedge sat where
            # was scrambled to color order, not data order, whenever the
            # colors weren't already ascending-hex. `order` pins it back
            # to plotpress's own wedge order (clockwise from 12 o'clock,
            # same as svg.py's _render_pie).
            "order": {"field": "idx", "type": "ordinal"},
            # x/y/radius are literal channel VALUES (not mark-level
            # properties -- Vega-Lite has no such shorthand), matching the
            # arc's own explicit cx/cy/R so labels below line up with the
            # actual wedges rather than guessing at Vega-Lite's own
            # undocumented auto-centering/auto-sizing.
            "x": {"value": round(float(cx), 2)}, "y": {"value": round(float(cy), 2)},
            "radius": {"value": round(float(R), 2)},
        },
    }]
    # Wedge label / autopct%% text: Vega-Lite's `arc` mark has no built-in
    # per-wedge label placement (unlike `theta`'s auto-stacking), so the
    # same wedge-midpoint trig walk plotpress.vega's own _pie_marks and
    # svg.py's _render_pie both do is repeated here, in Python, to get a
    # literal pixel x/y per label -- frozen positions via {"value": px}
    # (bypassing any data scale entirely, the same literal-pixel idiom
    # _rug_layer's tick length uses), matching the arc's own explicit
    # cx/cy/R above so labels land on their actual wedges regardless of
    # what Vega-Lite's own auto-sizing would have produced.
    if art.labels is not None or art.autopct is not None:
        ang = math.radians(art.startangle)
        label_rows, pct_rows = [], []
        for frac in art.fracs:
            sweep = frac * 2 * math.pi
            a0, a1 = ang, ang - sweep
            am = (a0 + a1) / 2.0
            ang = a1
            label_rows.append({
                "x": cx + 1.15 * R * math.cos(am), "y": cy - 1.15 * R * math.sin(am),
                "align": "left" if math.cos(am) >= 0 else "right",
            })
            pct_rows.append({"x": cx + 0.6 * R * math.cos(am), "y": cy - 0.6 * R * math.sin(am)})
        if art.labels is not None:
            for row, lbl in zip(label_rows, art.labels):
                layers.append({
                    # A layer with only literal {"value": ...} encodings and
                    # no "data" of its own has zero rows to instantiate the
                    # mark from -- and draws NOTHING, silently -- confirmed
                    # empirically (an isolated text-over-arc repro rendered
                    # blank until a trivial one-row dataset was added). Every
                    # other layer in this file gets its row(s) implicitly
                    # from a real per-point/per-cell dataset; this is the
                    # one case with no real data at all, so it needs an
                    # explicit placeholder row purely to exist.
                    "data": {"values": [{}]},
                    "mark": {"type": "text", "align": row["align"],
                            "baseline": "middle", "fontSize": 10},
                    "encoding": {
                        "x": {"value": round(float(row["x"]), 2)},
                        "y": {"value": round(float(row["y"]), 2)},
                        "text": {"value": str(lbl)},
                    },
                })
        if art.autopct is not None:
            for row, frac in zip(pct_rows, art.fracs):
                pct = art.pct_text(frac)
                if pct is None:
                    continue
                layers.append({
                    "data": {"values": [{}]},   # see the label loop above
                    "mark": {"type": "text", "align": "center",
                            "baseline": "middle", "fontSize": 10},
                    "encoding": {
                        "x": {"value": round(float(row["x"]), 2)},
                        "y": {"value": round(float(row["y"]), 2)},
                        "text": {"value": pct},
                    },
                })
    return layers, []


def _stem_layers(art, ax):
    x, y = np.asarray(art.x, float), np.asarray(art.y, float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.any():
        return [], []
    x_enc, y_enc, caveats = _xy_axis(ax)
    values = [{"x": float(xv), "y0": art.baseline, "y1": float(yv)}
             for xv, yv in zip(x[finite], y[finite])]
    stems = {
        "data": {"values": values},
        "mark": {"type": "rule", "color": _color(art.linecolor), "strokeWidth": 1.2},
        "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}},
    }
    xlo, xhi = float(x[finite].min()), float(x[finite].max())
    baseline = {
        "data": {"values": [{"x0": xlo, "x1": xhi, "y": art.baseline}]},
        "mark": {"type": "rule", "color": ax.style.spine_color, "strokeWidth": 0.8},
        "encoding": {"x": dict(x_enc, field="x0"), "x2": {"field": "x1"}, "y": dict(y_enc, field="y")},
    }
    tips = {
        "data": {"values": values},
        "mark": {"type": "point", "filled": True, "color": _color(art.markercolor)},
        "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y1")},
    }
    return [stems, baseline, tips], caveats


# ---- Tier 2: layered workarounds ----------------------------------------

def _refline_layer(art, ax):
    if art.linestyle == "none":
        return [], []
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    x_enc, y_enc, caveats = _xy_axis(ax)
    mark = {"type": "rule", "color": _color(art.color), "strokeWidth": float(art.linewidth),
            "opacity": float(art.alpha)}
    dash = _dash_array(art.linestyle)
    if dash:
        mark["strokeDash"] = dash
    xmin, xmax, ymin, ymax = float(xmin), float(xmax), float(ymin), float(ymax)
    if isinstance(art, VLine):
        row = {"x": art.x, "y0": ymin, "y1": ymax}
        enc = {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}}
    elif isinstance(art, HLine):
        row = {"y": art.y, "x0": xmin, "x1": xmax}
        enc = {"y": dict(y_enc, field="y"), "x": dict(x_enc, field="x0"), "x2": {"field": "x1"}}
    else:  # AxLine
        if not np.isfinite(art.slope):
            row = {"x": art.x1, "y0": ymin, "y1": ymax}
            enc = {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}}
        else:
            y0 = float(art.y1 + art.slope * (xmin - art.x1))
            y1 = float(art.y1 + art.slope * (xmax - art.x1))
            row = {"x0": xmin, "x1": xmax, "y0": y0, "y1": y1}
            enc = {"x": dict(x_enc, field="x0"), "x2": {"field": "x1"},
                  "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}}
    return [{"data": {"values": [row]}, "mark": mark, "encoding": enc}], caveats


def _line_collection_layer(art, ax):
    """``LineCollection`` (``hlines()``/``vlines()``, violin inner
    quartile/whisker lines, ``acorr()``/``xcorr()``) as a single ``rule``
    mark over a literal per-segment dataset -- the same pattern
    :func:`_refline_layer`/:func:`_span_layer` already use for one row,
    just N of them (``art.segments`` is already an ``(N, 4)`` array of
    ``x0, y0, x1, y1`` rows, one shared color/width/dash for the batch).
    """
    if art.linestyle == "none" or art.segments.size == 0:
        return [], []
    finite = np.isfinite(art.segments).all(axis=1)
    if not finite.any():
        return [], []
    x_enc, y_enc, caveats = _xy_axis(ax)
    values = [{"x0": float(s[0]), "y0": float(s[1]), "x1": float(s[2]), "y1": float(s[3])}
             for s in art.segments[finite]]
    mark = {"type": "rule", "color": _color(art.color), "strokeWidth": float(art.linewidth),
            "opacity": float(art.alpha)}
    dash = _dash_array(art.linestyle)
    if dash:
        mark["strokeDash"] = dash
    enc = {"x": dict(x_enc, field="x0"), "x2": {"field": "x1"},
          "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}}
    return [{"data": {"values": values}, "mark": mark, "encoding": enc}], caveats


def _rug_layer(art, ax):
    """``Rug`` (seaborn-style tick marks at each observation) as a ``rule``
    mark, one tick per point -- the tick's SPATIAL position rides the
    shared data scale like every other mark, but its short length is a
    fixed *pixel* fraction of the axes (``art.height``), independent of
    the data range (see ``artists.Rug``'s own docstring) -- expressed the
    same way ``primitives.py``'s own Rug branch does it (anchored in pixel
    space), via a literal, unscaled ``{"value": px}`` on the channel that
    carries the tick's length instead of the data scale.
    """
    if art.x.size == 0:
        return [], []
    finite = np.isfinite(art.x)
    if not finite.any():
        return [], []
    fig = ax.figure
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    xlim, ylim = ax._resolved_limits()
    _, _, px_w, px_h = _effective_rect(ax, *_pixel_rect(ax, W, H), xlim, ylim)
    x_enc, y_enc, caveats = _xy_axis(ax)
    color = _color(art.color, "#333333")
    mark = {"type": "rule", "color": color, "strokeWidth": float(art.linewidth),
            "opacity": float(art.alpha)}
    values = [{"pos": float(v)} for v in art.x[finite]]
    if art.side == "left":
        enc = {"y": dict(y_enc, field="pos"),
              "x": {"value": 0}, "x2": {"value": art.height * px_w}}
    else:
        enc = {"x": dict(x_enc, field="pos"),
              "y": {"value": px_h}, "y2": {"value": px_h - art.height * px_h}}
    return [{"data": {"values": values}, "mark": mark, "encoding": enc}], caveats


def _polygon_layer(art, ax):
    """``Polygon`` (``fill()``, and critically ``fill_betweenx()`` -- the
    direct sibling of the already-supported ``fill_between()``, built the
    same way internally: see ``axes.py``'s ``fill_betweenx``) as a real
    Vega-Lite ``area`` mark, when the polygon boundary is actually the
    "monotonic two-boundary strip" shape both ``fill_between``-style calls
    produce (go forward along one boundary, then back along the other) --
    a general closed polygon (a filled circle, a hexbin cell, an arbitrary
    ``fill()`` shape) has no such structure and no Vega-Lite closed-vocabulary
    mark to fall back to, so it warns instead, the same "degrade a part, not
    silently misrepresent it" policy :func:`_fillbetween_layer` already
    applies to a non-monotonic `fill_between`.
    """
    caveat = (
        "a fill()/fill_betweenx() polygon that isn't a simple two-boundary "
        "strip (go forward along one edge, back along the other -- what "
        "fill_between()/fill_betweenx() themselves always build) has no "
        "Vega-Lite mapping -- skipped."
    )
    x, y = art.x, art.y
    n = x.size
    if n < 4 or n % 2 != 0:
        return [], [caveat]
    half = n // 2
    # fill_between()/fill_betweenx() both close the ring as
    # [forward boundary, reversed(other boundary)] -- detect that shape on
    # EITHER axis (y constant-per-half-pair for a vertical strip like
    # fill_between, x constant-per-half-pair for a horizontal one like
    # fill_betweenx) rather than assuming which one built it.
    if np.allclose(y[:half], y[half:][::-1], equal_nan=True):
        # Horizontal strip (fill_betweenx-shaped): y is the shared axis,
        # x0/x1 are the two boundaries.
        yv, x0, x1 = y[:half], x[:half], x[half:][::-1]
        finite = np.isfinite(yv) & np.isfinite(x0) & np.isfinite(x1)
        if not finite.any():
            return [], []
        x_enc, y_enc, caveats = _xy_axis(ax)
        values = [{"y": float(yy), "x0": float(a), "x1": float(b)}
                 for yy, a, b in zip(yv[finite], x0[finite], x1[finite])]
        enc = {"y": dict(y_enc, field="y"),
              "x": dict(x_enc, field="x0"), "x2": {"field": "x1"}}
    elif np.allclose(x[:half], x[half:][::-1], equal_nan=True):
        # Vertical strip (fill_between-shaped): x is the shared axis,
        # y0/y1 are the two boundaries.
        xv, y0, y1 = x[:half], y[:half], y[half:][::-1]
        finite = np.isfinite(xv) & np.isfinite(y0) & np.isfinite(y1)
        if not finite.any():
            return [], []
        x_enc, y_enc, caveats = _xy_axis(ax)
        values = [{"x": float(xx), "y0": float(a), "y1": float(b)}
                 for xx, a, b in zip(xv[finite], y0[finite], y1[finite])]
        enc = {"x": dict(x_enc, field="x"),
              "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}}
    else:
        return [], [caveat]
    mark = {"type": "area", "color": _color(art.color), "opacity": float(art.alpha)}
    if art.edgecolor:
        mark["stroke"] = _color(art.edgecolor)
        mark["strokeWidth"] = float(art.linewidth)
    return [{"data": {"values": values}, "mark": mark, "encoding": enc}], caveats


def _span_layer(art, ax):
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    xmin, xmax, ymin, ymax = float(xmin), float(xmax), float(ymin), float(ymax)
    x_enc, y_enc, caveats = _xy_axis(ax)
    if art.orientation == "vertical":
        row = {"x0": art.lo, "x1": art.hi, "y0": ymin, "y1": ymax}
    else:
        row = {"y0": art.lo, "y1": art.hi, "x0": xmin, "x1": xmax}
    enc = {"x": dict(x_enc, field="x0"), "x2": {"field": "x1"},
          "y": dict(y_enc, field="y0"), "y2": {"field": "y1"}}
    mark = {"type": "rect", "color": _color(art.color), "opacity": float(art.alpha)}
    return [{"data": {"values": [row]}, "mark": mark, "encoding": enc}], caveats


def _fillbetween_layer(art, ax):
    x = np.asarray(art.x, float)
    finite = np.isfinite(x) & np.isfinite(art.y1) & np.isfinite(art.y2)
    if not finite.any():
        return [], []
    # Monotonicity is checked on the finite points only -- a NaN anywhere
    # makes every np.diff() comparison False regardless of the real x
    # order (NaN comparisons are always False), which mislabeled an
    # all-NaN series as "non-monotonic" instead of "nothing to draw".
    xf = x[finite]
    d = np.diff(xf)
    if xf.size > 1 and not (np.all(d >= 0) or np.all(d <= 0)):
        return [], [
            "a fill_between()/fill_betweenx() with non-monotonic x has no "
            "Vega-Lite mapping (its `area` mark needs a monotonic axis) -- "
            "skipped."
        ]
    x_enc, y_enc, caveats = _xy_axis(ax)
    values = [{"x": float(xv), "y1": float(y1v), "y2": float(y2v)}
             for xv, y1v, y2v in zip(x, art.y1, art.y2)
             if np.isfinite(xv) and np.isfinite(y1v) and np.isfinite(y2v)]
    if not values:
        return [], caveats
    mark = {"type": "area", "color": _color(art.color), "opacity": float(art.alpha)}
    if art.edgecolor:
        mark["stroke"] = _color(art.edgecolor)
        mark["strokeWidth"] = float(art.linewidth)
    layer = {"data": {"values": values}, "mark": mark,
             "encoding": {"x": dict(x_enc, field="x"),
                         "y": dict(y_enc, field="y1"), "y2": {"field": "y2"}}}
    return [layer], caveats


def _mesh_data_layer(art, ax):
    """Real per-cell ``rect`` marks with a field+scale color encoding for a
    QuadMesh eligible for ``mesh_data=True`` (see
    :func:`plotpress.vega._mesh_data_reason`) -- the Vega-Lite twin of
    :func:`plotpress.vega._mesh_data_marks`, reusing the same
    :func:`~plotpress.vega._mesh_cell_rows`/:func:`~plotpress.vega._mesh_scheme`
    helpers rather than re-deriving per-cell geometry or scheme-mapping
    logic a second time.
    """
    rows = _mesh_cell_rows(art)
    if not rows:
        return [], []
    x_enc, y_enc, caveats = _xy_axis(ax)
    scheme, reverse = _mesh_scheme(art.cmap_name)
    color_enc = {
        "field": "value", "type": "quantitative",
        "scale": {"scheme": scheme,
                 "domain": [float(art.norm.vmin), float(art.norm.vmax)],
                 "reverse": reverse},
        "legend": None,
    }
    layer = {
        "data": {"values": rows},
        "mark": {"type": "rect", "opacity": float(art.alpha)},
        "encoding": {
            "x": dict(x_enc, field="x0"), "x2": {"field": "x1"},
            "y": dict(y_enc, field="y0"), "y2": {"field": "y1"},
            "color": color_enc,
        },
    }
    return [layer], caveats


def _mesh_layer(art, ax, mesh_data=False):
    """``QuadMesh``/``Image`` (``pcolormesh``/``imshow``) as a Vega-Lite
    ``image`` mark -- the one mark in VL's vocabulary built for exactly
    this (a URL + a data-space extent), so this reuses the same rasterized
    RGBA + data extent every other backend already computes
    (``art.rgba()``/``art.extent()``, the same pair ``artist_to_prims``'s
    own ``(QuadMesh, Image)`` branch reads) rather than re-deriving
    anything.

    The image is placed via *data-space* x/x2/y/y2, through the same scale
    (inverted/log-aware) every other mark on this axes shares -- but unlike
    a point/line/bar mark, whose geometry is computed FROM the data at
    render time, an image mark's raster content is a fixed bitmap with its
    own baked-in "row 0 at the top of its own box" orientation; reversing
    the y-scale moves *where* the box sits, not which row of the bitmap
    ends up at which edge of it. Confirmed by actually rendering an
    inverted-y-axis mesh through vega-lite/vega: without the manual flip
    below, the raster came out upside-down relative to plotpress's own
    render, even though the box itself was correctly repositioned.

    ``mesh_data=True`` opts into :func:`_mesh_data_layer`'s real per-cell
    ``rect`` marks instead, for meshes small/simple enough to stay
    unambiguous -- everything else (including a plain ``Image``, which has
    no per-cell colormap to encode) still gets this rasterized path, with
    a ``UserWarning`` naming why when ``mesh_data=True`` was requested but
    couldn't be honored.
    """
    reason = _mesh_data_reason(art, mesh_data, ax)
    if reason is None:
        return _mesh_data_layer(art, ax)
    if mesh_data:
        warnings.warn(
            f"figure_to_vega_lite(): axes {_axes_index(ax)} requested "
            f"mesh_data=True, but this mesh has {reason} -- falling back "
            "to a rasterized image mark for it instead.",
            UserWarning, stacklevel=4,
        )
    xmin, xmax, ymin, ymax = art.extent()
    if not all(np.isfinite(v) for v in (xmin, xmax, ymin, ymax)):
        return [], []
    rgba = art.rgba()
    if ax._yinverted:
        rgba = rgba[::-1, :]
    if ax._xinverted:
        rgba = rgba[:, ::-1]
    rgba = np.ascontiguousarray(rgba)
    url = png_data_uri(rgba.astype(np.uint8) if rgba.dtype != np.uint8 else rgba)
    x_enc, y_enc, caveats = _xy_axis(ax)
    row = {"x": float(xmin), "x2": float(xmax), "y": float(ymin), "y2": float(ymax), "url": url}
    layer = {
        "data": {"values": [row]},
        # aspect: False -- Vega-Lite's image mark defaults to *preserving*
        # the raster's own native pixel aspect ratio (here, the mesh's
        # row/col resolution) inside the x/x2/y/y2 box instead of
        # stretching to fill it exactly, which every other backend does.
        # Confirmed by actually rendering: without this, a non-square mesh
        # (e.g. a wide axes panel with square data limits) came out as a
        # small square image left-aligned in its box, with blank space
        # filling the rest -- not visible from the JSON structure alone.
        "mark": {"type": "image", "aspect": False,
                "smooth": getattr(art, "interpolation", "nearest") != "nearest"},
        "encoding": {
            "x": dict(x_enc, field="x"), "x2": {"field": "x2"},
            "y": dict(y_enc, field="y"), "y2": {"field": "y2"},
            "url": {"field": "url", "type": "nominal"},
        },
    }
    return [layer], caveats


# plotpress va -> Vega-Lite text-mark baseline -- the same mapping
# plotpress.vega's own _VEGA_VA uses (Vega-Lite marks compile to real Vega
# marks, so the baseline vocabulary is identical).
_VL_VA = {"baseline": "alphabetic", "bottom": "bottom", "center": "middle", "top": "top"}


def _text_layer(art, ax):
    # bbox= (a background box behind the label) is out of scope for now --
    # it needs the label's own pixel-space bounding box (text_box() in
    # svg.py), which conflicts with this module's data-scale-encoded text
    # position (Vega-Lite's x/y here go through the same quantitative scale
    # every other mark on this axes uses, not a raw pixel value) without a
    # separate pixel->data inverse mapping this module doesn't build. The
    # label itself still exports; only its background box is dropped.
    if isinstance(art, Annotation):
        x, y = art.xytext if art.xytext is not None else art.xy
    else:
        x, y = art.x, art.y
    caveats = []
    if art.axes_fraction:
        # Vega-Lite has no per-mark axes-fraction escape hatch the way
        # svg.py/plotpress.vega's _axes_fraction_xy gives a fixed pixel
        # point regardless of the data scale -- approximated here by
        # converting the fraction to a literal *data-space* x/y at the
        # axes' own current resolved limits, which stays correct only
        # until the domain changes (e.g. via a Vega-Lite selection/zoom).
        (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
        x = xmin + x * (xmax - xmin)
        y = ymin + y * (ymax - ymin)
        caveats.append(
            "an axes-fraction-positioned Text/Annotation was placed at its "
            "current data-space equivalent -- unlike plotpress's own "
            "renderers, it will not stay fixed to the view if the chart is "
            "panned/zoomed in the Vega-Lite runtime."
        )
    size = getattr(art, "size", None)
    size = 11.0 if size is None else float(size)
    ha = getattr(art, "ha", "left")
    align = ha if ha in ("left", "right", "center") else "left"
    va = getattr(art, "va", "baseline")
    x_enc, y_enc, axcav = _xy_axis(ax)
    caveats.extend(axcav)
    mark = {"type": "text", "text": art.text, "align": align,
            "baseline": _VL_VA.get(va, "alphabetic"), "fontSize": size,
            "color": _color(getattr(art, "color", None), "#000000")}
    rotation = float(getattr(art, "rotation", 0.0) or 0.0)
    if rotation:
        # plotpress's own rotation is counterclockwise-positive
        # (matplotlib convention); Vega(-Lite)'s `angle` is
        # clockwise-positive, same negation plotpress.vega's _text_marks
        # applies for the same reason.
        mark["angle"] = -rotation
    if getattr(art, "bold", False):
        mark["fontWeight"] = "bold"
    if getattr(art, "italic", False):
        mark["fontStyle"] = "italic"
    alpha = float(getattr(art, "alpha", 1.0))
    if alpha < 1:
        mark["opacity"] = alpha
    layers = [{"data": {"values": [{"x": float(x), "y": float(y)}]}, "mark": mark,
              "encoding": {"x": dict(x_enc, field="x"), "y": dict(y_enc, field="y")}}]
    if isinstance(art, Annotation) and art.arrowprops is not None:
        warnings.warn(
            f"figure_to_vega_lite(): axes {_axes_index(ax)} has an "
            "Annotation with an arrow -- Vega-Lite has no arrow-drawing "
            "mark, so the arrow was dropped (the text label itself still "
            "exports).", UserWarning, stacklevel=4,
        )
    return layers, caveats
