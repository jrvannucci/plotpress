"""Render-time layout helpers: collapsing empty grid rows/cols, text-overflow
detection/auto-scaling, figure-legend/inset/colorbar placement, and the
Vega/Vega-Lite compatibility report `Figure.print_layout_summary()` and
`Axes.print_summary()` share. A leaf module -- nothing here calls back into
`_core`.
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

def _cbar_label_width(cax) -> float:
    """Figure-fraction width the colorbar's tick labels need to its right.

    The renderer draws them outside the bar, so without this the labels spill
    past the space stolen from the parent -- into the next subplot, or off the
    figure edge. Measuring needs the mappable's ``vmin``/``vmax``, which every
    mappable resolves when it is constructed, so this is safe to call before
    anything has been drawn.
    """
    from ..style.colors import resolve_colorbar_ticks

    st = cax.style
    _, _, labels = resolve_colorbar_ticks(cax._cbar_source.norm, cax._cbar_ticks,
                                          cax._cbar_format)
    text_px = max((st.text_width(t, st.tick_label_size) for t in labels),
                  default=0.0)
    return (st.tick_size + 2 + text_px) / (cax.figure.figsize[0] * st.dpi)


def _collapse_empty_grid_rows_and_cols(fig):
    """Shrink each of the figure's grids to skip any row/column that is now
    entirely empty -- every axes that used to occupy it has been
    :meth:`~plotpress.axes.Axes.remove`-d -- for
    :meth:`Figure.tight_layout`'s ``collapse="grid"``.

    A grid axes' position lives entirely in its own :class:`SubplotSpec`
    (``nrows``/``ncols``/``row0``/``row1``/``col0``/``col1``); nothing else
    in the figure is indexed by row/column (``group_spacing()``'s
    ``wspace``/``hspace`` are single figure-wide values, not per-boundary),
    so shrinking a grid is just remapping those six fields. Every unique
    spec is mutated **in place** rather than replaced -- ``twinx()``/
    ``twiny()``/``secondary_xaxis()``/``secondary_yaxis()`` all set their
    own ``_subplotspec`` to their parent's *exact same object* (not a copy)
    specifically to "stay aligned through tight_layout()" (see their own
    assignments), so mutating that shared object in place keeps every twin/
    secondary correct for free -- replacing it with a new object per axes
    would silently leave any twin/secondary still pointing at the old one.

    Specs are grouped by their own ``(nrows, ncols)`` first, and every step
    below (occupancy, remapping, the new shape) runs *within* one group at
    a time. ``Figure.add_subplot()``/``subplots()`` can be called more than
    once on one figure, each call producing its own independently-shaped
    grid -- without this grouping, a completely unrelated standalone axes
    (say, its own ``1x1`` "grid") got its ``nrows``/``ncols`` silently
    overwritten to whatever some *other*, differently-shaped grid on the
    same figure collapsed down to, just because both grids' specs were
    mutated by the same final ``spec.nrows, spec.ncols = new_nrows,
    new_ncols`` line. Two independent grids that happen to share the exact
    same shape are still pooled together here (nothing marks which cells
    belong to which call) -- the same "one shared grid" assumption
    :meth:`tight_layout`'s own placement math already makes elsewhere, so
    this doesn't regress anything that worked correctly before it.
    """
    specs_axes = [ax for ax in fig.axes
                 if ax._subplotspec is not None and not ax._is_colorbar]
    if not specs_axes:
        return
    # Dedupe by identity: a twin/secondary shares its parent's exact
    # SubplotSpec object, so mutating it once (below) is enough for both.
    unique_specs = list({id(ax._subplotspec): ax._subplotspec for ax in specs_axes}.values())

    by_shape = {}
    for spec in unique_specs:
        by_shape.setdefault((spec.nrows, spec.ncols), []).append(spec)

    for (nrows, ncols), specs in by_shape.items():
        occupied_rows, occupied_cols = set(), set()
        for spec in specs:
            occupied_rows.update(range(spec.row0, spec.row1 + 1))
            occupied_cols.update(range(spec.col0, spec.col1 + 1))

        row_map = {old: new for new, old in enumerate(r for r in range(nrows) if r in occupied_rows)}
        col_map = {old: new for new, old in enumerate(c for c in range(ncols) if c in occupied_cols)}
        if len(row_map) == nrows and len(col_map) == ncols:
            continue   # every row/column in this grid is still in use

        new_nrows, new_ncols = len(row_map), len(col_map)
        for spec in specs:
            spec.row0, spec.row1 = row_map[spec.row0], row_map[spec.row1]
            spec.col0, spec.col1 = col_map[spec.col0], col_map[spec.col1]
            spec.nrows, spec.ncols = new_nrows, new_ncols


def _require_one_grid_shape(specs, caller):
    """Raise a clear error if ``specs`` spans more than one ``(nrows,
    ncols)`` shape -- ``add_subplot()``/``subplots()`` can be called more
    than once on one figure, each producing its own independently-shaped
    grid, but :func:`_place_spec_rects` (shared by :meth:`Figure.tight_layout`
    and :meth:`Figure.subplots_adjust`) assumes one uniform grid: its
    ``col_left``/``row_bottom`` arrays are sized for just the *first* grid's
    shape, so a later grid's own column/row index used to run past them and
    raise a bare, uninformative ``IndexError`` instead of explaining what
    happened. (:func:`_collapse_empty_grid_rows_and_cols` already handles
    this case correctly, by grouping specs per shape -- it just has no
    placement step of its own to protect.)
    """
    shapes = {(ax._subplotspec.nrows, ax._subplotspec.ncols) for ax in specs}
    if len(shapes) > 1:
        named = ", ".join(f"{r}x{c}" for r, c in sorted(shapes))
        raise ValueError(
            f"{caller}(): this figure has more than one independently-"
            f"shaped grid ({named} -- from separate add_subplot()/"
            f"subplots() calls on the same figure). {caller}() only knows "
            "how to fit one shared grid at a time; lay each grid out on "
            "its own Figure, or position these axes by hand with "
            "set_position() instead."
        )


_MIN_TICK_LABEL_SIZE = 6.0    # below this, shrinking further stops helping


_MIN_TITLE_SIZE = 8.0


_TEXT_FIT_MARGIN = 0.9        # target 90% of the available space, not exactly 100%


def _ax_ident(fig, ax):
    """A short, human phrase naming ``ax`` for a warning message -- its own
    id/title when it has one (what a caller actually recognizes it by),
    falling back to its position in :attr:`Figure.axes`."""
    if ax._id:
        return f"axes {ax._id!r}"
    if ax._title:
        return f"the {ax._title!r}-titled axes"
    try:
        return f"axes index {fig.axes.index(ax)}"
    except ValueError:
        return "an axes"


def _iter_text_overflows(fig, specs, Wpx, Hpx):
    """Yield one dict per measured text extent that doesn't fit where
    :meth:`Figure.tight_layout` placed it: unrotated x tick labels wider
    than their own average spacing, or a title/xlabel/group title wider
    than the box it's centered over.

    tight_layout()'s own margin math only ever reserves *one text row* per
    tick/label -- correct for the common case, but never enough to notice
    an unrotated label simply being too long for its own tick spacing, or
    a title wider than its axes, since fixing that means picking one of
    several genuinely different remedies (a smaller font, rotated labels,
    shorter text, a wider figure) that only the caller can choose. This is
    the shared detector behind both the advisory warning
    (:func:`_warn_about_text_overflow`) and the opt-in auto-fix
    (:func:`_auto_scale_overlapping_labels`, ``tight_layout(auto_label_scale=
    True)``) -- each dict's ``"fix"`` is a zero-arg callable that shrinks
    the relevant font just enough to fit, calling back into whichever
    per-instance size that text already has (:meth:`~plotpress.axes.
    Axes.set_title`/:meth:`~plotpress.axes.Axes.set_xlabel`/
    :meth:`~plotpress.axes.Axes.set_ylabel`'s own ``size``, or :meth:`group`'s
    ``fontsize``) rather than ``Style``'s figure-wide default, so shrinking
    one piece of text never touches any other axes'.
    """
    st = fig.style
    for ax in specs:
        if ax._axis_off or ax._is_colorbar:
            continue
        axes_w_px = ax._rect[2] * Wpx
        xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
        if not xst.tick_label_rotation:
            xticks = ax._resolve_xticks()
            if len(xticks) >= 2:
                xlabels = ax._resolve_xticklabels(xticks)
                max_w = max((xst.text_width(l, xst.tick_label_size) for l in xlabels),
                           default=0.0)
                avail = axes_w_px / len(xticks)
                if max_w > avail:
                    cur_size = xst.tick_label_size

                    def fix(ax=ax, cur_size=cur_size, max_w=max_w, avail=avail):
                        new_size = max(_MIN_TICK_LABEL_SIZE,
                                     cur_size * avail / max_w * _TEXT_FIT_MARGIN)
                        if new_size >= cur_size:
                            return False
                        ax.tick_params(axis="x", labelsize=new_size)
                        return True

                    yield {"kind": "xtick", "ax": ax, "measured_px": max_w,
                           "avail_px": avail, "fix": fix}
        if ax._title:
            size = ax._title_size or st.title_size
            w = st.text_width(ax._title, size)
            if w > axes_w_px:
                def fix(ax=ax, size=size, w=w, avail=axes_w_px):
                    new_size = max(_MIN_TITLE_SIZE, size * avail / w * _TEXT_FIT_MARGIN)
                    if new_size >= size:
                        return False
                    ax.set_title(ax._title, size=new_size)
                    return True

                yield {"kind": "title", "ax": ax, "measured_px": w,
                       "avail_px": axes_w_px, "fix": fix}
        if ax._shown_xlabel():
            size = ax._xlabel_size or st.label_size
            w = st.text_width(ax._xlabel, size)
            if w > axes_w_px:
                def fix(ax=ax, size=size, w=w, avail=axes_w_px):
                    new_size = max(_MIN_TITLE_SIZE, size * avail / w * _TEXT_FIT_MARGIN)
                    if new_size >= size:
                        return False
                    ax.set_xlabel(ax._xlabel, visible=ax._xlabel_visible, size=new_size)
                    return True

                yield {"kind": "xlabel", "ax": ax, "measured_px": w,
                       "avail_px": axes_w_px, "fix": fix}

    for g in fig._groups:
        if not g["visible"] or g["title_position"] not in ("top", "bottom"):
            continue
        g_specs = [a for a in g["axes"] if a._subplotspec is not None]
        if not g_specs:
            continue
        box_left = min(a._rect[0] for a in g_specs)
        box_right = max(a._rect[0] + a._rect[2] for a in g_specs)
        box_w_px = (box_right - box_left) * Wpx
        size = g["fontsize"] or st.title_size
        w = st.text_width(g["title"], size, bold=True)
        if w > box_w_px:
            def fix(g=g, size=size, w=w, avail=box_w_px):
                new_size = max(_MIN_TITLE_SIZE, size * avail / w * _TEXT_FIT_MARGIN)
                if new_size >= size:
                    return False
                g["fontsize"] = new_size
                return True

            yield {"kind": "group_title", "group": g, "measured_px": w,
                   "avail_px": box_w_px, "fix": fix}


def _auto_scale_overlapping_labels(fig, specs, Wpx, Hpx):
    """``tight_layout(auto_label_scale=True)``: shrink every overflowing
    text this can (see :func:`_iter_text_overflows`) down to its
    legibility floor. Returns whether anything actually changed, so the
    caller knows whether a second, full ``tight_layout()`` pass (to
    re-size the margin for the now-smaller fonts) is worth running.
    """
    changed = False
    for item in _iter_text_overflows(fig, specs, Wpx, Hpx):
        if item["fix"] is not None and item["fix"]():
            changed = True
    return changed


def _warn_about_text_overflow(fig, specs, Wpx, Hpx):
    """Advisory pass: warn about whatever :func:`_iter_text_overflows`
    still finds, naming a concrete fix for each -- run after
    ``auto_label_scale`` (if requested) has already had its turn, so this
    only ever reports what's still a problem afterward."""
    for item in _iter_text_overflows(fig, specs, Wpx, Hpx):
        kind, mpx, apx = item["kind"], item["measured_px"], item["avail_px"]
        if kind == "xtick":
            ident = _ax_ident(fig, item["ax"])
            warnings.warn(
                f"tight_layout(): {ident}'s x tick labels are wider "
                f"(~{mpx:.0f}px) than their average spacing (~{apx:.0f}px) "
                "and may overlap -- try tick_params(axis='x', "
                "labelrotation=45) to angle them, tick_params(axis='x', "
                "labelsize=<smaller>) to shrink them, "
                "tight_layout(auto_label_scale=True) to shrink them "
                "automatically, or set_xticks(...) to thin them out.",
                UserWarning, stacklevel=3)
        elif kind == "title":
            ident = _ax_ident(fig, item["ax"])
            warnings.warn(
                f"tight_layout(): {ident}'s title (~{mpx:.0f}px) is wider "
                f"than its own axes (~{apx:.0f}px) and may run past its "
                "edges -- try set_title(..., size=<smaller>), shorter "
                "text, tight_layout(auto_label_scale=True) to shrink it "
                "automatically, or a wider figure.",
                UserWarning, stacklevel=3)
        elif kind == "xlabel":
            ident = _ax_ident(fig, item["ax"])
            warnings.warn(
                f"tight_layout(): {ident}'s xlabel (~{mpx:.0f}px) is wider "
                f"than its own axes (~{apx:.0f}px) and may run past its "
                "edges -- try set_xlabel(..., size=<smaller>), shorter "
                "text, tight_layout(auto_label_scale=True) to shrink it "
                "automatically, or a wider figure.",
                UserWarning, stacklevel=3)
        else:                                        # group_title
            title = item["group"]["title"]
            warnings.warn(
                f"tight_layout(): the {title!r} group's title "
                f"(~{mpx:.0f}px) is wider than its own box (~{apx:.0f}px) "
                "and may run past its edges -- try a smaller fontsize= on "
                "Figure.group(), shorter text, "
                "tight_layout(auto_label_scale=True) to shrink it "
                "automatically, or a wider figure.",
                UserWarning, stacklevel=3)


def _place_spec_rects(specs, nrows, ncols, left, bottom, axw, axh, gap_w, gap_h):
    """Write each axes' ``_rect`` from its ``SubplotSpec`` span, a uniform
    cell size, and per-boundary gaps, shared by :meth:`Figure.tight_layout`
    and :meth:`Figure.subplots_adjust` (they differ only in how ``axw``/
    ``axh``/``gap_w``/``gap_h`` were derived -- measured pixels vs.
    matplotlib's fraction-of-cell ``wspace``/``hspace``).

    ``gap_w``/``gap_h`` are lists of ``ncols - 1``/``nrows - 1`` values, one
    per interior boundary -- not necessarily uniform, since
    :meth:`Figure.group_spacing` only widens the boundaries that actually
    border a group's own bounding box, not every row/col gap alike.
    """
    col_left = []
    x = left
    for c in range(ncols):
        col_left.append(x)
        x += axw + (gap_w[c] if c < ncols - 1 else 0.0)
    row_bottom = [0.0] * nrows
    y = bottom
    for r in range(nrows - 1, -1, -1):
        row_bottom[r] = y
        if r > 0:
            y += axh + gap_h[r - 1]
    for ax in specs:
        spec = ax._subplotspec
        x0 = col_left[spec.col0]
        x1 = col_left[spec.col1] + axw
        y0 = row_bottom[spec.row1]
        y1 = row_bottom[spec.row0] + axh
        ax._rect = (x0, y0, x1 - x0, y1 - y0)


def _layout_figure_legend(fig):
    """Shrink the subplot grid away from the edge a figure legend occupies.

    Derived from the axes' *current* rects, like :func:`_layout_colorbar`, so
    tight_layout can re-run it after reflowing. Placements with no unambiguous
    edge overlay instead and reserve nothing.
    """
    from ..backends.svg import FIGURE_LEGEND_EDGE, figure_legend_layout

    spec = fig._figure_legend
    if spec is None:
        return
    edge = FIGURE_LEGEND_EDGE.get(spec["loc"])
    if edge is None:
        return
    lay = figure_legend_layout(fig)
    if lay is None:
        return
    specs = [ax for ax in fig.axes
             if ax._subplotspec is not None and not ax._is_colorbar]
    if not specs:
        return

    W = fig.figsize[0] * fig.style.dpi
    H = fig.figsize[1] * fig.style.dpi
    pad_px = spec["pad"] * min(W, H) + 4
    if edge in ("bottom", "top"):
        needed = (lay["box_h"] + 2 * pad_px) / H
    else:
        needed = (lay["box_w"] + 2 * pad_px) / W
    # The legend itself always renders at its own full, unshrunk size
    # (_render_figure_legend never scales it down) -- reserving anything
    # less than that for it, as a flat 60% cap used to unconditionally do,
    # left the difference for the legend to draw over the axes it had just
    # "made room" for. A legend can still need more room than is
    # comfortable (many entries, one column) -- 0.92 is a last-resort
    # safety ceiling against that degenerate case eating the whole figure,
    # not a routine limit, so it warns rather than silently clipping.
    if needed > 0.92:
        warnings.warn(
            "Figure.legend(): this legend needs about "
            f"{needed * 100:.0f}% of the figure's "
            f"{'height' if edge in ('bottom', 'top') else 'width'} to avoid "
            "overlapping the axes, more than tight_layout() will reserve "
            "for it -- pass a larger ncol=, fewer entries, or move it to "
            "loc='right'/'left' if there's more room on that axis.",
            UserWarning, stacklevel=3)
    band = min(needed, 0.92)
    keep = 1.0 - band

    for ax in specs:
        left, bottom, w, h = ax._rect
        if edge == "bottom":
            ax._rect = (left, band + bottom * keep, w, h * keep)
        elif edge == "top":
            ax._rect = (left, bottom * keep, w, h * keep)
        elif edge == "right":
            ax._rect = (left * keep, bottom, w * keep, h)
        else:                                   # left
            ax._rect = (band + left * keep, bottom, w * keep, h)


def _layout_inset(iax):
    """Re-derive an ``inset_axes``' rect from its parent's *current* rect.

    Mirrors :func:`_layout_colorbar`'s reasoning: bounds are fractions of the
    parent's box, recorded once at ``inset_axes()`` time, but the parent's box
    moves whenever the grid reflows -- re-deriving here is what keeps the
    inset from drifting off it.
    """
    x0, y0, w, h = iax._inset_bounds
    pl, pb, pw, ph = iax._inset_parent._rect
    iax._rect = (pl + x0 * pw, pb + y0 * ph, w * pw, h * ph)


def _layout_colorbar(cax):
    """Steal space from ``cax``'s parent axes and place the bar in the gap.

    Derived from the parents' *current* rects rather than baked in at creation,
    so :meth:`Figure.tight_layout` can re-run it after reflowing the grid. Each
    call assumes the parents are at their full, un-stolen-from size -- which is
    exactly the state tight_layout leaves them in.

    The steal covers the gap, the bar, *and* the tick labels to its right, so
    the whole assembly fits inside the parents' original footprint.
    """
    axlist = cax._cbar_parents
    fraction, pad = cax._cbar_fraction, cax._cbar_pad
    label_w = _cbar_label_width(cax)
    if len(axlist) == 1:
        left, bottom, w, h = axlist[0]._rect
        bar_w = w * fraction
        plot_w = max(w - (w * pad + bar_w + label_w), w * 0.1)
        axlist[0]._rect = (left, bottom, plot_w, h)
        cax._rect = (left + plot_w + w * pad, bottom, bar_w, h)
        return
    rects = np.array([a._rect for a in axlist])
    gl, gb = rects[:, 0].min(), rects[:, 1].min()
    gr = (rects[:, 0] + rects[:, 2]).max()
    gt = (rects[:, 1] + rects[:, 3]).max()
    span_w = gr - gl
    bar_w = span_w * fraction
    keep = max(span_w - (span_w * pad + bar_w + label_w), span_w * 0.1)
    scale = keep / span_w
    for a in axlist:                       # squeeze the group leftward
        left, bottom, w, h = a._rect
        a._rect = (gl + (left - gl) * scale, bottom, w * scale, h)
    cax._rect = (gl + keep + span_w * pad, gb, bar_w, gt - gb)


def _vega_compat_report(fig):
    """``{axes_index_or_None: {"vega": [str, ...], "vega_lite": [str, ...]}}``
    -- built by actually calling ``fig.to_vega()``/``fig.to_vega_lite()``
    and reading their real warnings/caveats, not a separately-maintained
    list of "supported artist types" that could drift out of sync with
    what those two exporters actually do. ``None`` collects a gap that
    isn't attributable to one specific axes (a whole-figure legend, a
    grid-shape mismatch spanning several axes). Shared by
    :meth:`Figure.print_layout_summary` and :meth:`~plotpress.axes.Axes.print_summary`
    so both report the exact same thing for the same figure.
    """
    import re

    from ..backends.vega_lite import _STRUCTURAL_WARNING_PREFIX

    report = {}

    def add(msg, target):
        idxs = [int(m) for m in re.findall(r"axes (\d+)", msg)] or [None]
        for i in idxs:
            report.setdefault(i, {"vega": [], "vega_lite": []})[target].append(msg)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            fig.to_vega()
        except Exception as exc:
            # A real crash is a gap too -- swallowing it here would have this
            # function (and print_layout_summary()/print_summary(), which
            # only ever see its output) claim "OK" for an exporter that
            # actually blew up, while a direct fig.to_vega() call raises.
            add(f"to_vega() raised {type(exc).__name__}: {exc}", "vega")
    for w in caught:
        add(str(w.message), "vega")

    with warnings.catch_warnings(record=True) as caught2:
        warnings.simplefilter("always")
        try:
            _, caveats = fig.to_vega_lite()
        except Exception as exc:
            caveats = []
            add(f"to_vega_lite() raised {type(exc).__name__}: {exc}", "vega_lite")
    # `caveats` already carries every structural gap once, deduplicated;
    # the aggregate warning built from `" ".join(caveats)` would otherwise
    # duplicate every one of them as a second, harder-to-parse blob (the
    # same problem docs/conf.py's own scraper already had to filter out).
    for msg in caveats:
        add(msg, "vega_lite")
    for w in caught2:
        msg = str(w.message)
        if not msg.startswith(_STRUCTURAL_WARNING_PREFIX):
            add(msg, "vega_lite")
    return report


def _axes_position_desc(ax):
    """One line describing where ``ax`` sits: a plain grid cell, a
    multi-cell span, or one of the ways an axes can be entangled with
    another (twin, secondary, inset, colorbar, free-form ``add_axes()``)
    -- the same classification :func:`plotpress.vega_lite._is_cleanly_composable`
    and its neighbors use to decide how a figure composes into Vega-Lite,
    reused here as plain English rather than re-derived.
    """
    axlist = ax.figure.axes
    if ax._is_colorbar:
        parents = [p for p in (ax._cbar_parents or []) if p in axlist]
        if not parents:
            return "colorbar"
        names = ", ".join(f"axes {axlist.index(p)}" for p in parents)
        return f"colorbar for {names}"
    if ax._twin_of is not None:
        kind = "twinx()" if ax._twin_shared == "x" else "twiny()"
        return f"{kind} overlay of axes {axlist.index(ax._twin_of)}"
    if ax._secondary_of is not None:
        return f"secondary axis of axes {axlist.index(ax._secondary_of)}"
    if ax._inset_parent is not None:
        return f"inset of axes {axlist.index(ax._inset_parent)}"
    ss = ax._subplotspec
    if ss is None:
        return "free-form add_axes() rect"
    if ss.row0 == ss.row1 and ss.col0 == ss.col1:
        return f"row {ss.row0}, col {ss.col0} of a {ss.nrows}x{ss.ncols} grid"
    return (f"spans rows {ss.row0}-{ss.row1}, cols {ss.col0}-{ss.col1} "
            f"of a {ss.nrows}x{ss.ncols} grid")


def _axes_summary_lines(ax, gaps=None):
    """The lines :meth:`Figure.print_layout_summary` prints per axes and
    :meth:`~plotpress.axes.Axes.print_summary` prints for just one --
    shared so the two commands can never describe the same axes
    differently. ``gaps`` is one entry of :func:`_vega_compat_report`'s
    return value (``{"vega": [...], "vega_lite": [...]}``), or ``None`` to
    skip the export-compatibility lines entirely (a plain description,
    no exporters run).
    """
    from collections import Counter

    counts = Counter(type(a).__name__ for a in ax.artists)
    artists_desc = ", ".join(f"{n} {name}" for name, n in counts.items()) or "none"
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    # The axis actually renders reversed whenever an odd number of "flip"
    # sources apply: a raw hi-then-lo set_xlim()/set_ylim() call (matplotlib's
    # own common idiom for inverting without invert_xaxis()) XOR the explicit
    # _xinverted/_yinverted flag -- see svg.py's _render_axes, which combines
    # them the same way. Reporting the flag alone missed the set_xlim(hi, lo)
    # case entirely: the figure rendered inverted but the summary said nothing.
    x_inverted = (xlim[0] > xlim[1]) != ax._xinverted
    y_inverted = (ylim[0] > ylim[1]) != ax._yinverted
    lines = [
        f"  position:  {_axes_position_desc(ax)}",
        f"  visible:   {ax._visible}",
        f"  x:  {ax._xscale}, [{xlim[0]:.4g}, {xlim[1]:.4g}]"
        + (" (inverted)" if x_inverted else ""),
        f"  y:  {ax._yscale}, [{ylim[0]:.4g}, {ylim[1]:.4g}]"
        + (" (inverted)" if y_inverted else ""),
        f"  artists:   {artists_desc}",
    ]
    if ax._title:
        lines.append(f"  title:     {ax._title!r}")
    if ax._xlabel or ax._ylabel:
        xh = "" if ax._xlabel_visible else " (hidden)"
        yh = "" if ax._ylabel_visible else " (hidden)"
        lines.append(
            f"  labels:    xlabel={ax._xlabel!r}{xh} ylabel={ax._ylabel!r}{yh}")
    if getattr(ax, "_is_polar", False):
        lines.append("  polar:     yes")
    if gaps is not None:
        v = "OK" if not gaps["vega"] else f"{len(gaps['vega'])} gap(s)"
        vl = "OK" if not gaps["vega_lite"] else f"{len(gaps['vega_lite'])} gap(s)"
        lines.append(f"  to_vega():      {v}")
        lines.append(f"  to_vega_lite(): {vl}")
        for msg in gaps["vega"]:
            lines.append(f"    - [vega] {msg}")
        for msg in gaps["vega_lite"]:
            lines.append(f"    - [vega-lite] {msg}")
    return lines
