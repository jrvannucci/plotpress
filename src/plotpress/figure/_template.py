"""The template round-trip's build side: `figure_from_template()` and its
helpers, which construct a `Figure` from a template dict (`Figure.to_template`
/`save_template`/`load_template` producing that same shape lives with the
load side, in `_io.py`).
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import time
import warnings
from numbers import Integral

import numpy as np

from ..core.artists import normalize_bbox, normalize_linestyle
from ..axes import Axes
from ..polar import PolarAxes
from ..style import Style
from ..backends.svg import figure_to_svg

from ._core import Figure, GroupLayout, SubplotSpec, _apply_axes_decorations, _fit_cells, _squeeze_grid, _subplot_rect

def _rebuild_from_template(template, fig, explained=()):
    """Grid axes + :meth:`Figure.group` boxes for :func:`figure_from_template`
    -- every part of a template dict that isn't the overlay/inset/colorbar
    rebuilding it does afterward. ``explained`` is a set of
    ``omitted_axes`` indices the caller is going to recover some other way
    -- its own ``"overlays"``/``"insets"`` entries, since those *are*
    rebuilt (as a twin/secondary/inset of their parent, not a grid cell),
    so warning that they're "simply absent" the way a truly lost freeform
    axes is would be actively wrong for them. Returns ``(by_index, order,
    specs)``: ``by_index`` maps each saved index to its rebuilt
    :class:`~plotpress.axes.Axes`, ``order`` is those indices sorted for
    stable iteration, ``specs`` is each one's own spec dict in that same
    order -- what the caller needs for its own squeeze-or-flat-list
    return-shape logic afterward.
    """
    omitted = [i for i in (template.get("omitted_axes") or []) if i not in explained]
    if omitted:
        warnings.warn(
            f"figure_from_template(): {len(omitted)} axes from the saved "
            f"figure (index {omitted}) were placed with a freeform "
            "Figure.add_axes() rect, or are a twinx()/twiny()/"
            "secondary_xaxis()/secondary_yaxis() overlay of another axes, "
            "and could not be recovered as a grid cell of their own -- they "
            "are simply absent from the rebuilt figure.",
            UserWarning, stacklevel=3)
    axes_specs = template.get("axes") or {}
    order = sorted(axes_specs, key=int)
    # Each spec is looked up from `order` several times below (grid-shape
    # checks, the fill loop) -- fetched once here into a plain list aligned
    # with `order`, rather than re-indexing the dict by (already-int) key
    # over and over.
    specs = [axes_specs[i] for i in order]
    by_index = {}
    for i, spec in zip(order, specs):
        ss = SubplotSpec(spec["nrows"], spec["ncols"], spec["row0"], spec["row1"],
                         spec["col0"], spec["col1"])
        ax = fig.add_subplot(ss, projection=spec.get("projection"))
        _apply_axes_decorations(ax, spec)
        by_index[int(i)] = ax

    sup = template.get("suptitle")
    if sup:
        fig.suptitle(sup["text"], size=sup.get("size"))
    supx = template.get("supxlabel")
    if supx:
        fig.supxlabel(supx["text"], size=supx.get("size"))
    supy = template.get("supylabel")
    if supy:
        fig.supylabel(supy["text"], size=supy.get("size"))

    for g in template.get("groups") or []:
        members = [by_index[int(i)] for i in g["axes"] if int(i) in by_index]
        # n_members (the group's ORIGINAL size, before template_metadata()
        # filtered out members it already knew were unrecoverable) is what
        # tells apart a group that lost one of its own axes -- the
        # top-level omitted_axes warning above only says *an* axes was
        # dropped, never which group that broke.
        n_original = g.get("n_members", len(g["axes"]))
        if members and len(members) < n_original:
            warnings.warn(
                f"figure_from_template(): group {g['title']!r} had "
                f"{n_original} axes in the saved figure but only "
                f"{len(members)} could be recovered -- the rebuilt group "
                "box wraps fewer axes than the original.",
                UserWarning, stacklevel=3)
        if members:
            fig.group(g["title"], members, id=g.get("id"),
                     linestyle=g.get("linestyle", "--"),
                     color=g.get("color", "black"), linewidth=g.get("linewidth", 1.5),
                     title_position=g.get("title_position", "top"),
                     pad=tuple(g["pad"]) if g.get("pad") is not None else 8.0,
                     fontsize=g.get("fontsize"),
                     supxlabel=g.get("supxlabel"), supylabel=g.get("supylabel"),
                     supxlabel_size=g.get("supxlabel_size"),
                     supylabel_size=g.get("supylabel_size"),
                     visible=g.get("visible", True))
    return by_index, order, specs


def _squeeze_template_axes(by_index, order, specs):
    """The ``(fig, axes)`` return shape :func:`figure_from_template`
    documents: a bare ``Axes``/1-D/2-D array when every rebuilt axes is a
    single, non-spanning cell exactly tiling one ``nrows`` x ``ncols`` grid
    (mirroring ``plotpress.subplots(nrows, ncols)``'s own return, via the
    same :func:`_squeeze_grid` it uses), else a flat list in original save
    order.
    """
    ordered = [by_index[int(i)] for i in order]
    same_shape = len({(s["nrows"], s["ncols"]) for s in specs}) == 1
    single_cell = all(s["row0"] == s["row1"] and s["col0"] == s["col1"] for s in specs)
    if ordered and same_shape and single_cell:
        nrows, ncols = specs[0]["nrows"], specs[0]["ncols"]
        if len(ordered) == nrows * ncols:
            grid = np.empty((nrows, ncols), dtype=object)
            for i, s in zip(order, specs):
                grid[s["row0"], s["col0"]] = by_index[int(i)]
            return _squeeze_grid(grid, nrows, ncols)
    return ordered


def figure_from_template(template, figsize=None, style: Style = None, facecolor=None):
    """Rebuild a figure from a template dict: the same grid shape,
    :meth:`Figure.group` boxes, per-axes decorations, spine colors, tick
    overrides, ids, twin/secondary/inset overlays, colorbar styling, and
    :class:`~plotpress.style.Style` -- everything
    :meth:`~plotpress.figure.Figure.to_template`/
    :func:`plotpress.svg.template_metadata` capture. This is the one
    reconstruction function for two different starting points that produce
    the identical dict shape:

    - **A reusable, data-free template** -- built with
      :meth:`Figure.to_template`/:meth:`~Figure.save_template` and read
      back with :func:`plotpress.load_template`, with no plotted data
      anywhere in it. Replot into the returned (blank) axes the same way
      you would after ``plotpress.subplots(...)``.
    - **A figure recovered from a saved HTML export** -- read via
      :func:`plotpress.load_data`'s own ``"template"`` key, alongside that
      same call's ``"series"``/``"meshes"``/``"pies"`` data to replot. This
      also carries the recovered figure's real title/labels/limits/scale/
      grid/aspect/spines/ticks/style/overlays -- everything about how it
      looked, so nothing here needs re-setting by hand, only the data
      itself needs replotting back in.

    ``figsize``/``facecolor`` override the template's own saved values.
    ``style`` overrides ``template["style"]`` outright; a template saved
    before ``"style"`` existed falls back to a fresh, default
    :class:`~plotpress.style.Style` when no override is given, the same
    fallback shape ``figsize``/``facecolor`` already use for their own
    missing/older keys.

    Returns ``(fig, axes)``. When every recorded axes is a single,
    non-spanning cell that exactly tiles one ``nrows`` x ``ncols`` grid,
    ``axes`` mirrors what ``plotpress.subplots(nrows, ncols)`` itself would
    hand back -- a bare ``Axes`` for a 1x1 grid, a 1-D array for a single
    row/column, otherwise a 2-D array indexed ``axes[row, col]``. Anything
    else (row/column spans from ``add_gridspec``, mismatched grids across
    axes, or no grid-placed axes at all) falls back to a flat list of axes
    in their original save order -- still fully usable, just not
    array-indexable by row/column. Twins/secondaries/insets are already
    built and attached to ``fig.axes`` but are not folded into this return
    value -- the same way ``ax.twinx()`` isn't folded into
    ``plotpress.subplots()``'s own return either; give an axes (or its
    parent) an ``id`` before saving the template if a lookup afterward
    needs to find it reliably, via ``fig.get_ax(id=...)``.

    Colorbars are documented in ``template["colorbars"]`` (which axes had
    one, and its ``fraction``/``pad``/``label``/``ticks``/``format``) but
    never auto-built -- a colorbar needs a live mappable, which doesn't
    exist until real data is plotted. Call ``fig.colorbar(mesh, ax=...)``
    yourself once you've replotted, passing those same styling knobs back
    if you want them preserved. An axes that had a
    :meth:`~plotpress.axes.Axes.legend` is recorded too, but never
    auto-applied either -- a legend draws from already-plotted, labeled
    artists, none of which exist on a freshly rebuilt axes yet; call
    ``ax.legend(**entry["legend"])`` yourself once you've replotted into it.

    Warns (``UserWarning``) when ``template["omitted_axes"]`` has an axes
    beyond what ``"overlays"``/``"insets"`` account for -- a freeform
    :meth:`Figure.add_axes` rect has no recorded position to rebuild from,
    so it's simply missing from the returned figure; the warning is the
    only signal of that, since a caller with no other axes count to
    compare against would otherwise have no way to notice. A separate
    warning names any :meth:`Figure.group` whose own box lost a member to
    that same drop -- the group is still created around whichever of its
    axes did come back, just smaller than the original.
    """
    saved_style = template.get("style")
    fig = Figure(figsize=figsize or tuple(template.get("figsize") or (6.4, 4.8)),
                style=style if style is not None else (Style(**saved_style) if saved_style else None),
                facecolor=facecolor if facecolor is not None else template.get("facecolor"))
    explained = {e["index"] for e in template.get("overlays") or [] if "index" in e}
    explained |= {e["index"] for e in template.get("insets") or [] if "index" in e}
    by_index, order, specs = _rebuild_from_template(template, fig, explained=explained)

    # A twin/secondary/inset's own parent can itself be another overlay --
    # a secondary_yaxis() of a twinx(), say -- not just a grid axes, so each
    # rebuilt overlay/inset is registered into by_index under its own
    # original index (to_template() always visits a parent before any
    # overlay/inset built from it, since it iterates fig.axes in creation
    # order and nothing can be built from an axes that doesn't exist yet)
    # so a later entry can resolve it as *its* own parent.
    for e in template.get("overlays") or []:
        parent = by_index.get(int(e["parent"]))
        if parent is None:
            warnings.warn(
                "figure_from_template(): an overlay's parent (index "
                f"{e['parent']}) could not be rebuilt -- this twin/"
                "secondary is skipped too.", UserWarning, stacklevel=2)
            continue
        kind = e["kind"]
        if kind == "twinx":
            ax = parent.twinx()
        elif kind == "twiny":
            ax = parent.twiny()
        elif kind == "secondary_xaxis":
            ax = parent.secondary_xaxis(e.get("location", "top"))
        else:
            ax = parent.secondary_yaxis(e.get("location", "right"))
        _apply_axes_decorations(ax, e)
        if "index" in e:
            by_index[int(e["index"])] = ax

    for e in template.get("insets") or []:
        parent = by_index.get(int(e["parent"]))
        if parent is None:
            warnings.warn(
                "figure_from_template(): an inset's parent (index "
                f"{e['parent']}) could not be rebuilt -- this inset is "
                "skipped too.", UserWarning, stacklevel=2)
            continue
        ax = parent.inset_axes(tuple(e["bounds"]), projection=e.get("projection"))
        _apply_axes_decorations(ax, e)
        if "index" in e:
            by_index[int(e["index"])] = ax

    return fig, _squeeze_template_axes(by_index, order, specs)
