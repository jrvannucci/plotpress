"""The root object itself: `Figure`, the grid/group machinery it's built from
(`SubplotSpec`/`GridSpec`/`GroupLayout`/`Group`/`subplots_from_groups`), and
`subplots()` -- all genuinely mutually coupled (`Figure.group()` returns a
`Group`; `subplots_from_groups()`/`subplots()` construct a `Figure`), so they
stay one file rather than being forced into a false acyclic split.
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

from ._layout import _auto_scale_overlapping_labels, _axes_summary_lines, _collapse_empty_grid_rows_and_cols, _layout_colorbar, _layout_figure_legend, _layout_inset, _place_spec_rects, _require_one_grid_shape, _vega_compat_report, _warn_about_text_overflow

from ._html_options import _columnarize_meta, _encode_binary_arrays, _json_payload, _resolve_options, _toolbar_clearance

_ALIGN_UNSET = object()


def _normalize_pad(pad):
    """A single number (uniform clearance) or a 4-item ``(left, right, top,
    bottom)`` sequence, always returned as that 4-tuple -- every consumer
    (the tight_layout margin reservation in this module, the box geometry in
    svg.py/raster.py) then indexes one side directly instead of each
    re-checking "was this a scalar or a sequence" on its own.

    Duck-typed on ``float(pad)`` succeeding, rather than ``isinstance(pad,
    (int, float))`` -- a numpy scalar (``np.int64``, ``np.float32``, a 0-d
    array) satisfies the former but not the latter (only ``np.float64``
    happens to subclass Python's own ``float``), and a caller deriving pad
    from other numpy computation is a realistic, not exotic, case. Strings
    are excluded up front despite ``float()`` accepting one: ``"5"`` would
    otherwise silently take the single-number branch instead of raising --
    a caller error (pad built from a config/CLI value that came through as
    text) worth surfacing clearly, not coercing quietly.
    """
    if isinstance(pad, (str, bytes)):
        raise TypeError(
            f"pad must be a number or a 4-item (left, right, top, bottom) "
            f"sequence, not a string: {pad!r}")
    try:
        p = float(pad)
    except TypeError:
        pass
    else:
        return (p, p, p, p)
    pad = tuple(float(v) for v in pad)
    if len(pad) != 4:
        raise ValueError(
            "pad must be a single number or a 4-item (left, right, top, "
            f"bottom) sequence, got {len(pad)} values")
    return pad


class SubplotSpec:
    """A (possibly multi-cell) placement within an ``nrows`` x ``ncols`` grid.

    ``row0``/``row1``/``col0``/``col1`` are inclusive, 0-based cell bounds --
    a single-cell spec (the ordinary ``add_subplot(nrows, ncols, index)``
    case) has ``row0 == row1`` and ``col0 == col1``. This is the one
    representation :meth:`Figure.tight_layout` and :meth:`Figure.subplots_adjust`
    place from, whether the axes came from a plain grid or a :class:`GridSpec`
    slice.
    """

    def __init__(self, nrows, ncols, row0, row1, col0, col1):
        self.nrows, self.ncols = nrows, ncols
        self.row0, self.row1, self.col0, self.col1 = row0, row1, col0, col1


def _cell_subplotspec(nrows, ncols, index) -> SubplotSpec:
    """``SubplotSpec`` for a single 1-based cell ``index`` (legacy add_subplot)."""
    idx = index - 1
    row, col = idx // ncols, idx % ncols
    return SubplotSpec(nrows, ncols, row, row, col, col)


def _slice_span(sel, n):
    """Inclusive 0-based ``(lo, hi)`` bounds from a ``GridSpec`` index or slice."""
    if isinstance(sel, slice):
        if sel.step not in (None, 1):
            raise ValueError("GridSpec only supports contiguous spans (step=1)")
        lo, hi, _ = sel.indices(n)
        if hi <= lo:
            raise ValueError("GridSpec slice selects no rows/columns")
        return lo, hi - 1
    idx = sel if sel >= 0 else sel + n
    return idx, idx


class GridSpec:
    """A grid layout descriptor supporting row/column spans.

    ``fig.add_gridspec(2, 3)[0, :2]`` returns a :class:`SubplotSpec` covering
    the first two columns of row 0; pass that to :meth:`Figure.add_subplot` in
    place of ``(nrows, ncols, index)``.

    ``left``/``right``/``top``/``bottom``/``wspace``/``hspace`` are accepted
    for signature familiarity with matplotlib's ``GridSpec``. Since the figure
    only ever sizes one uniform grid at a time, any given here are applied
    immediately as the figure's own margins (like calling
    :meth:`Figure.subplots_adjust` with the same values) -- a later
    ``tight_layout()``/``subplots_adjust()`` call still wins, same as it would
    over an explicit ``subplots_adjust`` call.
    """

    def __init__(self, figure, nrows, ncols, left=None, right=None, top=None,
                bottom=None, wspace=None, hspace=None):
        self.figure = figure
        self.nrows = nrows
        self.ncols = ncols
        self.left, self.right = left, right
        self.top, self.bottom = top, bottom
        self.wspace, self.hspace = wspace, hspace
        sp = figure._subplot_params
        for key, val in (("left", left), ("right", right), ("top", top),
                         ("bottom", bottom), ("wspace", wspace), ("hspace", hspace)):
            if val is not None:
                sp[key] = float(val)
        if any(v is not None for v in (left, right, top, bottom, wspace, hspace)):
            figure._tight_pad = None
            figure._layout_dirty = False

    def __getitem__(self, key) -> SubplotSpec:
        rows, cols = key if isinstance(key, tuple) else (key, slice(None))
        r0, r1 = _slice_span(rows, self.nrows)
        c0, c1 = _slice_span(cols, self.ncols)
        return SubplotSpec(self.nrows, self.ncols, r0, r1, c0, c1)


def _squeeze_grid(grid, nrows, ncols):
    """``subplots()``'s own squeeze rule -- a bare ``Axes`` for a 1x1 grid, a
    flat 1-D array for a single row/column, otherwise the 2-D array
    untouched. Shared with :meth:`GroupLayout._build` so both squeeze
    identically rather than keeping two copies of this in sync by hand.
    """
    if nrows == 1 and ncols == 1:
        return grid[0, 0]
    if nrows == 1 or ncols == 1:
        return grid.ravel()
    return grid


class GroupLayout:
    """Describes an outer grid of *groups*, each its own inner grid of axes
    -- so a figure like "four quadrants, each its own 2x2 cluster of plots"
    can be built by describing that shape directly, instead of hand-deriving
    which cells of one big flat grid each quadrant's axes actually occupy::

        layout = plotpress.GroupLayout(2, 2)
        layout.add_group(0, 0, 2, 2, title="Group (0,0)")
        layout.add_group(0, 1, 2, 2, title="Group (0,1)")
        layout.add_group(1, 0, 2, 2, title="Group (1,0)")
        layout.add_group(1, 1, 2, 2, title="Group (1,1)")
        fig, axes = plotpress.subplots_from_groups(layout, figsize=(12, 10))
        axes[0, 0][1, 1].plot(x, y)   # group (0,0)'s own bottom-right axes

    Every group may have a *different* inner shape -- there is no
    requirement that they match. Internally this is resolved onto one
    plain, flat grid (the least common multiple of every group's own
    row/column count, times this layout's own outer shape) with each
    group's axes as ordinary, non-overlapping ``SubplotSpec`` spans within
    it -- so once built, the figure is completely ordinary: every axes has
    one flat ``_subplotspec`` in one shared grid, exactly like
    :func:`~plotpress.figure.subplots`/:meth:`Figure.add_gridspec` already
    produce. :meth:`~plotpress.figure.Figure.tight_layout`,
    :meth:`~plotpress.figure.Figure.align_xlabels`/``align_ylabels``,
    ``Figure.to_vega``/``to_vega_lite``, and twin/secondary axes all keep
    working completely unmodified -- none of them ever finds out the
    figure was built this way.

    Only one level of grouping -- a group cannot itself contain groups.
    Every group also occupies exactly one outer cell (no outer row/column
    spans yet); pass a taller/wider inner shape instead if a group should
    take up more of the figure than its neighbors.

    Keep every group's row count sharing a small common multiple with its
    neighbors' (and likewise for columns): the shared grid's own size is
    the *least common multiple* of every group's own row/column count, so
    mixing incompatible shapes -- a 5-row group alongside 2-row and 3-row
    ones, say -- can need a far finer shared grid than any of them alone
    would suggest (``lcm(5, 2, 3) = 30``). Past about 40 rows or columns,
    ``tight_layout()``'s own cell-size floor (each cell needs at least 2%
    of the figure's width/height, an ordinary-grid safeguard that was
    never tuned for a resolution this fine) can silently drop *every*
    row/column gap -- including :meth:`~plotpress.figure.Figure.
    group_spacing`'s own deliberate reservation between groups -- to keep
    cells from shrinking to nothing, which reads as groups overlapping
    rather than a sizing problem. :func:`subplots_from_groups` warns when
    this happens; prefer shapes like 2, 4, and 8 over 2, 3, and 5 to avoid
    it in the first place.
    """

    def __init__(self, nrows: int, ncols: int):
        if nrows < 1 or ncols < 1:
            raise ValueError(
                f"GroupLayout(): nrows and ncols must both be >= 1, got "
                f"{nrows!r}, {ncols!r}"
            )
        self.nrows, self.ncols = nrows, ncols
        self._cells = {}   # (row, col) -> dict; see add()

    def add_group(self, row: int, col: int, nrows: int = None, ncols: int = None,
                 mask=None, axes_ids=None, axes_titles=None, title: str = None,
                 id=None, linestyle="--", color="black", linewidth=1.5,
                 title_position="top", pad=8.0, fontsize=None,
                 supxlabel=None, supylabel=None, supxlabel_size=None, supylabel_size=None,
                 visible=True):
        """Place a group at outer cell ``(row, col)`` with an ``nrows`` x
        ``ncols`` inner grid of axes. Returns ``self`` so calls can chain.

        Presence (which inner cells actually get an axes -- for an
        irregular group: an L-shape, a ring, a hole in the middle, instead
        of a plain rectangle) comes from whichever of these is given --
        ``nrows``/``ncols`` are then inferred from it, rather than needed
        separately:

        - ``mask``, an ``nrows`` x ``ncols`` array-like of truthy/falsy
          values -- falsy means no axes there. Pass real booleans/ints, not
          strings: ``numpy`` casts a non-empty string to ``True``
          regardless of its content (``"False"`` included), so a mask read
          back from text (a CSV column, say) needs converting first.
        - ``axes_ids``, an array-like of the same shape, ``str | None`` --
          a non-``None`` entry means an axes *and* sets its id (see
          :meth:`~plotpress.axes.Axes.set_id`) in one step, mosaic-style.
        - ``axes_titles``, the same idea for each axes' *title* (see
          :meth:`~plotpress.axes.Axes.set_title`) instead of its id.

        Giving more than one of these is fine as long as they agree on
        which cells are present -- raises, naming the cell, if they don't.
        With none of them, plain ``nrows``/``ncols`` (both required then)
        place a full rectangle with no per-axes id/title.

        ``title``/``id`` and the styling kwargs (``linestyle``/``color``/
        ``linewidth``/``title_position``/``pad``/``fontsize``/``supxlabel``/
        ``supylabel``/``supxlabel_size``/``supylabel_size``/``visible``) match
        :meth:`Figure.group` exactly -- passed straight through to it once
        this group's real axes exist. A group is only registered (and so
        only findable via :meth:`Figure.get_group`, including by ``id``)
        when it has a ``title`` -- ``id`` without one raises, since it
        would otherwise silently do nothing.
        """
        if not (0 <= row < self.nrows and 0 <= col < self.ncols):
            raise ValueError(
                f"GroupLayout.add_group(): ({row}, {col}) is outside this "
                f"layout's own {self.nrows}x{self.ncols} outer grid"
            )
        if (row, col) in self._cells:
            raise ValueError(
                f"GroupLayout.add_group(): outer cell ({row}, {col}) already "
                "has a group -- each outer cell holds exactly one"
            )
        if id is not None and title is None:
            raise ValueError(
                "GroupLayout.add_group(): id= needs title= too -- a group "
                "is only registered (and so only findable at all) when it "
                "has a title"
            )

        ids_arr = None if axes_ids is None else np.asarray(axes_ids, dtype=object)
        titles_arr = None if axes_titles is None else np.asarray(axes_titles, dtype=object)
        sources = [("mask", None if mask is None else np.asarray(mask, dtype=bool)),
                  ("axes_ids", None if ids_arr is None else ids_arr != None),   # noqa: E711
                  ("axes_titles", None if titles_arr is None else titles_arr != None)]  # noqa: E711
        given = [(name, m) for name, m in sources if m is not None]
        for name, m in given:
            if m.ndim != 2:
                raise ValueError(
                    f"GroupLayout.add_group(): {name} must be 2-D, got "
                    f"shape {m.shape!r}"
                )
        if given:
            first_name, mask_arr = given[0]
            for name, m in given[1:]:
                if m.shape != mask_arr.shape:
                    raise ValueError(
                        f"GroupLayout.add_group(): {name}'s shape {m.shape} "
                        f"doesn't match {first_name}'s shape {mask_arr.shape}"
                    )
                if not np.array_equal(m, mask_arr):
                    r0, c0 = map(int, np.argwhere(m != mask_arr)[0])
                    raise ValueError(
                        f"GroupLayout.add_group(): {name} and {first_name} "
                        f"disagree on whether cell ({r0}, {c0}) is present"
                    )
            if nrows is not None and nrows != mask_arr.shape[0]:
                raise ValueError(
                    f"GroupLayout.add_group(): nrows={nrows} doesn't match "
                    f"{first_name}'s own {mask_arr.shape[0]} rows"
                )
            if ncols is not None and ncols != mask_arr.shape[1]:
                raise ValueError(
                    f"GroupLayout.add_group(): ncols={ncols} doesn't match "
                    f"{first_name}'s own {mask_arr.shape[1]} columns"
                )
        else:
            if not (nrows and ncols and nrows >= 1 and ncols >= 1):
                raise ValueError(
                    "GroupLayout.add_group(): pass nrows/ncols (both >= 1), "
                    "or a mask/axes_ids/axes_titles to infer them from"
                )
            mask_arr = np.ones((nrows, ncols), dtype=bool)
        if not mask_arr.any():
            raise ValueError(
                f"GroupLayout.add_group(): ({row}, {col})'s mask has no "
                "present cells -- a group needs at least one axes"
            )
        self._cells[row, col] = {
            "mask": mask_arr, "axes_ids": ids_arr, "axes_titles": titles_arr,
            "title": title, "id": id,
            "linestyle": normalize_linestyle(linestyle, "GroupLayout.add_group", stacklevel=3),
            "color": color, "linewidth": float(linewidth),
            "title_position": title_position, "pad": _normalize_pad(pad),
            "fontsize": fontsize,
            "supxlabel": supxlabel, "supylabel": supylabel,
            "supxlabel_size": supxlabel_size, "supylabel_size": supylabel_size,
            "visible": visible,
        }
        return self

    def remove_group(self, row: int, col: int):
        """Remove the *planned* group at outer cell ``(row, col)`` -- before
        :func:`subplots_from_groups` builds anything, so that cell simply
        has no group (and no axes) at all. Raises if there's no group
        there. To remove a group from an already-built figure instead, see
        :meth:`Figure.remove_group`. See
        :doc:`/auto_figure_layout/grouping/plot_16_axes_titles_and_ordinary_lookup`
        for a worked example.
        """
        if (row, col) not in self._cells:
            raise ValueError(
                f"GroupLayout.remove_group(): no group at ({row}, {col})"
            )
        del self._cells[row, col]

    def _build(self, fig, squeeze=True, sharex=False, sharey=False, projection=None):
        """Resolve every group onto one flat super-grid and create its real
        axes -- see the class docstring for the shape of the returned
        array. Called by :func:`subplots_from_groups`; not meant to be
        called directly (it needs a fresh, empty ``fig`` to place into).
        """
        if not self._cells:
            raise ValueError(
                "GroupLayout has no groups -- call add_group() at least "
                "once before building a figure from it"
            )
        Lr = math.lcm(*(c["mask"].shape[0] for c in self._cells.values()))
        Lc = math.lcm(*(c["mask"].shape[1] for c in self._cells.values()))
        super_nrows, super_ncols = self.nrows * Lr, self.ncols * Lc
        # _fit_cells' own floor (each cell needs at least 2% of the figure's
        # width/height) silently drops *every* row/column gap -- including
        # group_spacing()'s own deliberate reservation between groups, not
        # just the ordinary tick-label one -- once a dimension has more
        # cells than that floor can possibly fit at once (1/0.02 = 50).
        # Groups with very different row/column counts (e.g. 5 and 3, whose
        # LCM is 15) reach that resolution with innocuous-looking shapes far
        # more easily than a plain subplots() grid ever does, so this is
        # worth a clear warning rather than a silently ungapped, overlapping
        # -looking figure -- exactly what motivated this warning.
        if super_nrows > 40 or super_ncols > 40:
            warnings.warn(
                f"subplots_from_groups(): this layout's groups need a shared "
                f"{super_nrows}x{super_ncols} grid to resolve their different "
                "row/column counts as clean spans -- past about 40 rows or "
                "columns, tight_layout() may drop every group_spacing() gap "
                "(and even the ordinary tick-label one) to keep cells from "
                "shrinking to nothing, which looks like groups overlapping. "
                "Prefer inner shapes whose row counts share a small common "
                "multiple (and likewise for columns) -- e.g. 2, 4, and 8 "
                "instead of 2, 3, and 5.",
                UserWarning, stacklevel=3)

        axes_grid = np.full((self.nrows, self.ncols), None, dtype=object)
        for (row, col), spec in self._cells.items():
            mask = spec["mask"]
            inr, inc = mask.shape
            row_scale, col_scale = Lr // inr, Lc // inc
            # Last-present-cell-per-column/row, for sharex/sharey's own
            # "hide every inner tick label but the outer edge" behavior
            # (mirrors Figure.subplots()) generalized to an irregular mask:
            # the edge is whichever present cell is actually last in that
            # column/row, not necessarily the mask's own last index.
            last_row_per_col = {c: max(r for r in range(inr) if mask[r, c])
                                for c in range(inc) if mask[:, c].any()}
            first_col_per_row = {r: min(c for c in range(inc) if mask[r, c])
                                 for r in range(inr) if mask[r, :].any()}
            inner = np.full((inr, inc), None, dtype=object)
            group_axes = []
            for r in range(inr):
                for c in range(inc):
                    if not mask[r, c]:
                        continue
                    sr0 = row * Lr + r * row_scale
                    sr1 = row * Lr + (r + 1) * row_scale - 1
                    sc0 = col * Lc + c * col_scale
                    sc1 = col * Lc + (c + 1) * col_scale - 1
                    ss = SubplotSpec(super_nrows, super_ncols, sr0, sr1, sc0, sc1)
                    ax = fig.add_subplot(ss, projection=projection)
                    if spec["axes_ids"] is not None and spec["axes_ids"][r, c] is not None:
                        ax.set_id(spec["axes_ids"][r, c])
                    if spec["axes_titles"] is not None and spec["axes_titles"][r, c] is not None:
                        ax.set_title(spec["axes_titles"][r, c])
                    inner[r, c] = ax
                    group_axes.append(ax)
            if sharex:
                for r in range(inr):
                    for c in range(inc):
                        if inner[r, c] is None:
                            continue
                        inner[r, c]._sharex_group = group_axes
                        if r != last_row_per_col[c]:
                            inner[r, c].set_xticklabels([])
            if sharey:
                for r in range(inr):
                    for c in range(inc):
                        if inner[r, c] is None:
                            continue
                        inner[r, c]._sharey_group = group_axes
                        if c != first_col_per_row[r]:
                            inner[r, c].set_yticklabels([])
            if spec["title"] is not None:
                fig.group(spec["title"], group_axes, id=spec["id"],
                         linestyle=spec["linestyle"], color=spec["color"],
                         linewidth=spec["linewidth"],
                         title_position=spec["title_position"], pad=spec["pad"],
                         fontsize=spec["fontsize"],
                         supxlabel=spec["supxlabel"], supylabel=spec["supylabel"],
                         supxlabel_size=spec["supxlabel_size"],
                         supylabel_size=spec["supylabel_size"],
                         visible=spec["visible"],
                         _outer_row=row, _outer_col=col, _axes_grid=inner)
            axes_grid[row, col] = _squeeze_grid(inner, inr, inc) if squeeze else inner
        return axes_grid


def subplots_from_groups(layout: GroupLayout, figsize=(6.4, 4.8), style: Style = None,
                         facecolor=None, squeeze=True, sharex=False, sharey=False,
                         projection=None):
    """Build a figure from a :class:`GroupLayout` -- see there for how to
    describe the outer/inner grid shapes. Mirrors :func:`subplots`'s own
    signature and creates a fresh, independent ``Figure`` the same way.

    Returns ``(fig, axes)``: ``axes`` is shaped like ``layout``'s own outer
    grid (a bare value for a 1x1 layout, a 1-D array for a single outer
    row/column, otherwise 2-D), and each present cell holds that group's
    own inner axes array -- whatever :func:`subplots` itself would return
    for that group's shape. An outer cell with no group registered is
    ``None``. ``sharex``/``sharey`` link limits *within* each group only
    (every group is its own independent cluster, the same as calling
    :func:`subplots` separately for each one) -- not across the whole
    figure.

    Call :meth:`Figure.tight_layout`/:meth:`Figure.group_spacing` on the
    returned figure afterward exactly as you would for any other grid; a
    group's own box comes from an ordinary :meth:`Figure.group` call this
    makes internally, so it works the same way in every respect --
    including :meth:`Figure.get_groups` reading it back later.

    Round-tripping a figure built this way through :func:`load_data`/
    :func:`figure_from_template` recovers every axes and group correctly,
    but -- since a group's own cells are spans on the shared grid, not
    single non-spanning ones -- ``axes`` on the way back is
    :func:`figure_from_template`'s own flat-list fallback, not reconstructed
    back into this same nested shape.
    """
    fig = Figure(figsize=figsize, style=style, facecolor=facecolor)
    axes = layout._build(fig, squeeze=squeeze, sharex=sharex, sharey=sharey,
                         projection=projection)
    if squeeze:
        axes = _squeeze_grid(axes, layout.nrows, layout.ncols)
    return fig, axes


def _resolve_lookup_key(row, col, title, id, who):
    """Validate that exactly one of ``(row, col)`` together / ``title`` /
    ``id`` was given for a ``get_group``/``get_ax`` style lookup, and
    return which one as ``(kind, key)``. Checks ``is not None`` throughout
    -- ``row=0``/``col=0`` are ordinary, valid positions, not "not given".
    """
    has_rowcol = row is not None or col is not None
    if has_rowcol and (row is None or col is None):
        raise ValueError(f"{who}(): pass both row= and col=, not just one")
    given = [has_rowcol, title is not None, id is not None]
    if sum(given) != 1:
        raise ValueError(
            f"{who}(): pass exactly one of (row= and col=), title=, or id="
        )
    if has_rowcol:
        return "rowcol", (row, col)
    if title is not None:
        return "title", title
    return "id", id


def _finish_lookup(matches, who, kind, key, many):
    """Shared not-found/ambiguous/``many=`` handling for
    :meth:`Figure.get_ax`/:meth:`Group.get_ax` -- :meth:`Figure.get_group`
    has its own (it never accepts ``many=``, see there for why).
    """
    if many:
        return matches
    if not matches:
        raise ValueError(f"{who}(): no axes matches {kind}={key!r}")
    if len(matches) > 1:
        raise ValueError(
            f"{who}(): {len(matches)} axes match {kind}={key!r} -- pass "
            "many=True to get all of them"
        )
    return matches[0]


class Group:
    """One of a figure's registered groups (see :meth:`Figure.group`/
    :meth:`Figure.get_groups`/:meth:`Figure.get_group`) -- a read-only
    snapshot, not something to construct directly.

    ``title``/``id`` match whatever :meth:`Figure.group` (or
    :meth:`GroupLayout.add_group`, which calls it internally) was given.
    ``outer_row``/``outer_col`` are this group's own position in its
    :class:`GroupLayout`'s outer grid -- ``None`` for a group built by a
    direct :meth:`Figure.group` call, which has no such position.
    ``axes`` is the 2-D ``(row, col)`` array :func:`subplots_from_groups`
    itself returned for this group (``None`` for an absent cell) when
    built from a shaped layout; otherwise (a direct :meth:`Figure.group`
    call, with no inherent grid shape) it's a plain flat list.
    """

    def __init__(self, raw: dict):
        self._raw = raw
        self.title = raw["title"]
        self.id = raw["id"]
        self.axes = raw["axes_grid"] if raw["axes_grid"] is not None else list(raw["axes"])
        self.outer_row = raw["outer_row"]
        self.outer_col = raw["outer_col"]
        self.linestyle = raw["linestyle"]
        self.color = raw["color"]
        self.linewidth = raw["linewidth"]
        self.title_position = raw["title_position"]
        self.pad = raw["pad"]
        self.fontsize = raw["fontsize"]
        self.supxlabel = raw["supxlabel"]
        self.supylabel = raw["supylabel"]
        self.supxlabel_size = raw["supxlabel_size"]
        self.supylabel_size = raw["supylabel_size"]
        # A snapshot, like every other attribute here -- toggling visibility
        # afterward goes through Figure.set_group_visible(), not by setting
        # this attribute directly (which wouldn't touch the raw dict
        # rendering actually reads). See that method's own docstring.
        self.visible = raw["visible"]

    def flat_axes(self):
        """Every real axes in this group as a plain flat list, regardless
        of whether :attr:`axes` itself is shaped (a ``(row, col)`` array,
        ``None`` for an absent cell skipped) or already flat (a manually
        built :meth:`~plotpress.figure.Figure.group` with no grid shape).
        See :doc:`/auto_figure_layout/grouping/plot_14_irregular_group_shapes`
        for a worked example.
        """
        if isinstance(self.axes, np.ndarray):
            return [a for a in self.axes.ravel().tolist() if a is not None]
        return list(self.axes)

    def get_ax(self, row: int = None, col: int = None, title: str = None,
              id=None, many: bool = False):
        """The axes matching exactly one of: ``(row, col)`` together (this
        group's own *inner* position -- raises if this group has no grid
        shape, i.e. it wasn't built from a :class:`GroupLayout`), ``title``,
        or ``id``, scoped to this group's own axes only. See
        :meth:`Figure.get_ax` for the ``many=`` behavior, and
        :doc:`/auto_figure_layout/grouping/plot_14_irregular_group_shapes` for
        a worked example.
        """
        kind, key = _resolve_lookup_key(row, col, title, id, "get_ax")
        if kind == "rowcol":
            if not isinstance(self.axes, np.ndarray):
                raise ValueError(
                    "get_ax(): this group has no inner grid shape (it "
                    "wasn't built from a GroupLayout) -- use title= or id= "
                    "instead"
                )
            r, c = key
            if not (0 <= r < self.axes.shape[0] and 0 <= c < self.axes.shape[1]):
                raise ValueError(
                    f"get_ax(): ({r}, {c}) is outside this group's own "
                    f"{self.axes.shape[0]}x{self.axes.shape[1]} shape"
                )
            ax = self.axes[r, c]
            matches = [] if ax is None else [ax]
        elif kind == "title":
            matches = [ax for ax in self.flat_axes() if ax.get_title() == key]
        else:
            matches = [ax for ax in self.flat_axes() if ax.get_id() == key]
        return _finish_lookup(matches, "get_ax", kind, key, many)


def _axes_class(projection):
    """Resolve a ``projection`` name to its Axes class."""
    if projection in (None, "rectilinear"):
        return Axes
    if projection == "polar":
        return PolarAxes
    raise ValueError(
        "unknown projection %r (use None or 'polar')" % projection)


class Figure:
    def __init__(self, figsize=(6.4, 4.8), style: Style = None, facecolor=None):
        w, h = figsize
        if not (w > 0 and h > 0):
            raise ValueError(
                f"Figure(): figsize must be (width, height) with both > 0, "
                f"got {tuple(figsize)!r} -- a non-positive size produces an "
                "invalid, invisible SVG/PNG with no error anywhere downstream."
            )
        self.figsize = tuple(figsize)
        # The size the *user* asked for, as opposed to ``self.figsize`` --
        # which tight_layout() may grow beyond this to fit group_spacing()'s
        # reservations without shrinking the axes. Kept separate so repeated
        # tight_layout() calls recompute growth from a fixed starting point
        # instead of compounding it onto an already-grown figsize.
        self._base_figsize = tuple(figsize)
        self.style = (style or Style()).copy()
        if facecolor is not None:
            self.style.facecolor = facecolor
        self.axes: list[Axes] = []
        self._id_index = {}         # axes id -> Axes; set by Axes.set_id()
        # Slider "units" -- each is one control bar. The global unit "main" is a
        # single bar driving all shared series; a docked unit ("ax<i>") sits
        # under one axes. Docked units may share a connection *index* so the UI
        # can offer a checkbox to link them.
        self._sliders = {}          # unit_id -> spec
        self._slider_index_n = {}   # connection index -> n_frames (validation)

        # Temp file backing show()'s browser fallback, reused across calls.
        self._show_path = None

        # Figure-level (global) text spanning all subplots.
        self._suptitle = None
        self._figure_legend = None   # set by Figure.legend()
        self._supxlabel = None
        self._supylabel = None
        self._fig_texts = []         # set by Figure.text(); each a dict of kwargs
        self._groups = []            # set by Figure.group(); each a dict of kwargs
        self._group_wspace = None    # set by Figure.group_spacing()
        self._group_hspace = None

        # The uniform-grid geometry (nrows/ncols plus the col/row placement
        # inputs _place_spec_rects itself takes) from the most recent
        # tight_layout()/subplots_adjust() call -- kept around so a group
        # that has lost some (not necessarily all) of its own axes (see
        # Axes.remove()) can still recompute where its box belongs from its
        # *other* members' current, correctly-relaid-out cells instead of a
        # pixel snapshot frozen back when it was removed -- see svg.py's
        # _ghost_group_rect.
        self._grid_placement = None

        # tight_layout is re-applied at render time if anything it measured has
        # changed since -- see _settle_layout.
        self._tight_pad = None
        self._layout_dirty = False

        # subplots_adjust's own margins, applied instead of a measured
        # tight_layout fit. Defaults match _subplot_rect's literals, so a
        # partial subplots_adjust(wspace=...) call only changes what it names.
        self._subplot_params = {"left": 0.125, "right": 0.9, "top": 0.88,
                                "bottom": 0.11, "wspace": 0.2, "hspace": 0.2}

        # Axes lists last passed to align_xlabels/align_ylabels, so
        # tight_layout/subplots_adjust can re-apply the alignment after they
        # reflow the grid (the same staleness problem colorbars/legends solve).
        self._align_x_axes = _ALIGN_UNSET
        self._align_y_axes = _ALIGN_UNSET

    def _settle_layout(self):
        """Re-fit the subplot grid if a measured decoration changed since.

        ``tight_layout`` sizes its margins from the titles and axis labels that
        exist when it runs, so anything set afterwards got no space reserved and
        was drawn over the axes -- which is exactly what a figure whose title
        reports its own build time has to do, since the number does not exist
        until the figure is built. Colorbars and figure legends already re-apply
        their reservations for the same reason; this extends that to text.

        Deferred to render rather than done eagerly on every setter: a grid of
        several hundred panels would otherwise re-lay out once per
        ``set_title``.
        """
        if self._layout_dirty and self._tight_pad is not None:
            self._layout_dirty = False
            self.tight_layout(self._tight_pad)

    def suptitle(self, text, size=None):
        """Set a global title centered across the whole figure."""
        self._suptitle = {"text": text, "size": size}
        self._layout_dirty = True

    def supxlabel(self, text, size=None):
        """Set a global x label centered along the bottom of the figure."""
        self._supxlabel = {"text": text, "size": size}
        self._layout_dirty = True

    def supylabel(self, text, size=None):
        """Set a global y label centered along the left of the figure."""
        self._supylabel = {"text": text, "size": size}
        self._layout_dirty = True

    def text(self, x, y, s, ha="left", va="baseline", fontsize=None, color=None,
             alpha=1.0, bbox=None):
        """Draw text at figure-fraction coordinates ``(x, y)`` -- ``(0, 0)`` is
        the bottom-left corner, ``(1, 1)`` the top-right, independent of any
        axes' data coordinates.

        ``alpha``/``bbox`` match :meth:`Axes.text` -- ``bbox`` draws a filled/
        bordered box behind the text (see there for its keys).
        """
        self._fig_texts.append({
            "x": float(x), "y": float(y), "s": s, "ha": ha, "va": va,
            "size": fontsize, "color": color, "alpha": alpha,
            "bbox": normalize_bbox(bbox),
        })

    def group(self, title, axes, id=None, linestyle="--", color="black", linewidth=1.5,
             title_position="top", pad=8.0, fontsize=None,
             supxlabel=None, supylabel=None, supxlabel_size=None, supylabel_size=None,
             visible=True, _outer_row=None, _outer_col=None, _axes_grid=None):
        """Draw a labeled box around a set of axes -- e.g. a cluster of
        related panels in a larger grid.

        The leading-underscore ``_outer_row``/``_outer_col``/``_axes_grid``
        are for :class:`GroupLayout` to record a group's own outer
        position and inner grid shape -- not meant to be passed directly;
        doing so with coordinates that collide with a real
        :class:`GroupLayout`'s own can make :meth:`get_group`'s
        ``row=``/``col=`` lookup ambiguous between the two.

        ``id`` is a second, exact-match way to find this group again later
        via :meth:`get_group`, alongside ``title`` -- unlike an axes' own
        ``id`` (see :meth:`Axes.set_id`), a group's ``id`` is not required
        to be unique; :meth:`get_group` raises if more than one group
        shares it, the same as it would for an ambiguous title.

        ``axes`` is any subset of this figure's own axes, typically adjacent
        cells in a subplot grid; the box is the tight bounding rectangle of
        their individual positions (nothing about grid adjacency is
        checked) -- expanded to also clear each axes' own tick labels, axis
        labels, and title, not just its bare plot rect -- plus ``pad`` pixels
        of clearance. ``pad`` is a single number for the same clearance on
        all four sides, or a 4-item ``(left, right, top, bottom)`` sequence
        for unequal padding -- e.g. tighter on the side that already butts
        against a neighboring group, looser on the side carrying the title.
        ``title_position`` is one of ``"top"``/``"bottom"``/``"left"``/
        ``"right"``, placing ``title`` just outside that edge of the box.

        ``supxlabel``/``supylabel`` are this group's own shared axis labels
        -- the group-scoped equivalent of :meth:`Figure.supxlabel`/
        :meth:`supylabel`, for a cluster of panels that all share one x/y
        quantity so no individual axes needs its own ``set_xlabel``/
        ``set_ylabel``. Unlike ``title``, which ``title_position`` can place
        on any of the four sides, these always draw at a fixed edge --
        ``supxlabel`` centered along the bottom, ``supylabel`` centered
        along the left, rotated -- the same fixed placement
        ``Figure.supxlabel``/``supylabel`` themselves use. The difference
        from the figure-level version is where: these draw *inside* the
        box, between its border and its member axes, rather than outside
        the whole grid -- the box grows to make room for them (the same way
        it already grows for ``pad``), rather than shrinking any axes.
        ``supxlabel_size``/``supylabel_size`` override the default size
        (:attr:`~plotpress.style.Style.label_size`-derived, matching
        ``Figure.supxlabel``/``supylabel``'s own default) independently of
        ``fontsize`` (which only ever sizes ``title``).

        ``visible=False`` hides the box, title, and any supxlabel/supylabel
        without forgetting any of it -- :meth:`Figure.set_group_visible`
        flips it back later by the same ``title``/``id``/:class:`Group`
        lookup :meth:`remove_group` uses. The same convention as
        :meth:`Axes.set_visible`: a hidden group still reserves its own
        margin in :meth:`tight_layout`, so toggling it doesn't reflow
        anything else -- unlike :meth:`remove_group`, which really does
        delete it (axes included).

        Returns ``self`` for chaining; several groups may be added to one
        figure.
        """
        if not axes:
            raise ValueError("group() needs at least one axes")
        for ax in axes:
            if ax not in self.axes:
                raise ValueError("group() axes must belong to this figure")
        if title_position not in ("top", "bottom", "left", "right"):
            raise ValueError(
                "title_position must be 'top', 'bottom', 'left', or 'right', "
                f"got {title_position!r}")
        self._groups.append({
            "title": title, "axes": list(axes), "id": id,
            "linestyle": normalize_linestyle(linestyle, "group", stacklevel=3),
            "color": color, "linewidth": float(linewidth),
            "title_position": title_position, "pad": _normalize_pad(pad),
            "fontsize": fontsize,
            "supxlabel": supxlabel, "supylabel": supylabel,
            "supxlabel_size": supxlabel_size, "supylabel_size": supylabel_size,
            "visible": bool(visible),
            "outer_row": _outer_row, "outer_col": _outer_col, "axes_grid": _axes_grid,
            # Set by Axes.remove() the moment any one of this group's own
            # axes first leaves it -- see _group_bbox's own docstring for
            # why: from then on this frozen (figure-fraction) rect stands
            # in for the usual live, axes-derived bounds, keeping the box
            # wrapping the group's original structure rather than
            # shrinking (or, once nothing is left, vanishing) removal by
            # removal. "_ghost_specs"/"_ghost_extras"/"_ghost_grid_shape",
            # set alongside it, let a later tight_layout() reposition this
            # same box at its members' *current* grid geometry instead of
            # leaving it pixel-locked to this exact moment -- see
            # svg._ghost_group_rects; None (a group with no shared grid to
            # begin with, e.g. built over a freeform add_axes() rect) just
            # falls back to the plain frozen pixel rect forever.
            "frozen_rect": None,
            "_ghost_specs": None, "_ghost_extras": None, "_ghost_grid_shape": None,
        })
        self._layout_dirty = True
        return self

    def get_groups(self) -> list:
        """This figure's registered groups (see :meth:`group`), each as a
        :class:`Group`.

        A snapshot for a group with no inherent grid shape (a direct
        :meth:`group` call) -- its ``Group.axes`` is a fresh list copy, so
        removing an axes afterward (see :meth:`Axes.remove`) never changes
        a ``Group`` already handed back here. For a :class:`GroupLayout`
        -built group, ``Group.axes`` *is* the shared underlying ``(row,
        col)`` grid, so a later removal does show up in one already held
        -- re-call :meth:`get_group`/:meth:`get_groups` instead of holding
        onto a stale reference if that distinction matters. Read it to
        find which axes already belong to a named group before combining
        it with another or extending it, or to answer "what groups does
        this figure have" for one you didn't build yourself. Works
        identically whether a group came from a direct :meth:`group` call,
        :func:`subplots_from_groups` (which calls :meth:`group` internally,
        once per group), or both mixed in one figure.
        """
        return [Group(g) for g in self._groups]

    def get_group(self, row: int = None, col: int = None, title: str = None,
                 id=None) -> "Group":
        """The one group matching exactly one of: ``(row, col)`` together
        (this group's own outer position -- only groups built via
        :class:`GroupLayout` have one; see :class:`Group`), ``title``, or
        ``id``. Raises if none or more than one group matches. See
        :doc:`/auto_figure_layout/grouping/plot_14_irregular_group_shapes` for
        a worked example.
        """
        kind, key = _resolve_lookup_key(row, col, title, id, "get_group")
        if kind == "rowcol":
            r, c = key
            matches = [g for g in self._groups
                      if g["outer_row"] == r and g["outer_col"] == c]
        elif kind == "title":
            matches = [g for g in self._groups if g["title"] == key]
        else:
            matches = [g for g in self._groups if g["id"] == key]
        if not matches:
            raise ValueError(f"get_group(): no group matches {kind}={key!r}")
        if len(matches) > 1:
            raise ValueError(
                f"get_group(): {len(matches)} groups match {kind}={key!r} "
                "-- ambiguous"
            )
        return Group(matches[0])

    def remove_group(self, group: "Group" = None, title: str = None, id=None):
        """Remove a group entirely: every one of its axes (via
        :meth:`Axes.remove`, so ``sharex``/``sharey`` links and any id stay
        consistent) and the group's own box/title registration.

        Pass the :class:`Group` object itself (from :meth:`get_groups`/
        :meth:`get_group`), or find it by ``title``/``id`` the same way
        :meth:`get_group` does -- exactly one of the three. Leaves a blank
        rectangle where the group was, the same as :meth:`Axes.remove`
        leaves a gap rather than reflowing the rest of the grid to fill it
        -- call ``fig.tight_layout(collapse="grid")`` afterward to shrink
        away any row/column that removal left completely empty. See
        :doc:`/auto_figure_layout/grouping/plot_15_dashboard_mixed_shapes_and_masks`
        for a worked example.
        """
        given = [group is not None, title is not None, id is not None]
        if sum(given) != 1:
            raise ValueError(
                "remove_group(): pass exactly one of group=, title=, or id="
            )
        if group is None:
            group = self.get_group(title=title, id=id)
        for ax in group.flat_axes():
            ax.remove()
        self._groups = [g for g in self._groups if g is not group._raw]

    def set_group_visible(self, visible: bool, group: "Group" = None,
                          title: str = None, id=None):
        """Show or hide a group's box/title/supxlabel/supylabel -- the same
        ``visible=`` :meth:`group` itself takes, settable again after the
        fact. Pass the :class:`Group` object itself (from
        :meth:`get_groups`/:meth:`get_group`), or find it by ``title``/
        ``id`` the same way :meth:`get_group` does -- exactly one of the
        three.

        Unlike :meth:`remove_group`, this never touches the group's own
        axes or deletes anything -- a hidden group still reserves its own
        margin in :meth:`tight_layout` (the same convention
        :meth:`Axes.set_visible` uses), so toggling it back and forth
        doesn't reflow the rest of the grid each time.
        """
        given = [group is not None, title is not None, id is not None]
        if sum(given) != 1:
            raise ValueError(
                "set_group_visible(): pass exactly one of group=, title=, or id="
            )
        if group is None:
            group = self.get_group(title=title, id=id)
        group._raw["visible"] = bool(visible)

    def get_ax(self, row: int = None, col: int = None, title: str = None,
              id=None, many: bool = False):
        """The axes matching exactly one of: ``(row, col)`` together (this
        axes' own position in a *plain, ungrouped* grid -- for an axes
        inside a :class:`GroupLayout`-built group, this is that group's
        position in the shared internal grid, not usually what you want;
        use :meth:`Group.get_ax` for that instead), ``title`` (see
        :meth:`Axes.set_title`), or ``id`` (see :meth:`Axes.set_id`).

        A ``twinx``/``twiny``/``secondary_xaxis``/``secondary_yaxis`` copies
        its parent's own ``(row, col)`` verbatim (they overlay the same
        cell), so a ``row=``/``col=`` lookup that reaches one reaches both
        -- give the twin its own ``id`` if it needs to be found
        unambiguously this way.

        Raises if no axes matches, or -- unless ``many=True`` -- if more
        than one does (impossible for ``id``, which is unique per figure by
        construction; titles may legitimately repeat, and a twin/secondary
        pair at one ``row=``/``col=`` counts as two). ``many=True``
        returns every match as a list instead (even a single one, so the
        return type doesn't depend on how many happened to match). See
        :doc:`/auto_figure_layout/grouping/plot_16_axes_titles_and_ordinary_lookup`
        for the plain-grid ``row=``/``col=`` case worked through.
        """
        kind, key = _resolve_lookup_key(row, col, title, id, "get_ax")
        if kind == "rowcol":
            r, c = key
            matches = [ax for ax in self.axes if ax._subplotspec is not None
                      and ax._subplotspec.row0 == ax._subplotspec.row1 == r
                      and ax._subplotspec.col0 == ax._subplotspec.col1 == c]
        elif kind == "title":
            matches = [ax for ax in self.axes if ax.get_title() == key]
        else:
            matches = [ax for ax in self.axes if ax.get_id() == key]
        return _finish_lookup(matches, "get_ax", kind, key, many)

    def group_spacing(self, wspace=None, hspace=None):
        """Reserve extra pixels between subplots for :meth:`group` boxes,
        without touching anything else :meth:`tight_layout` already sizes.

        Two groups facing each other across an *interior* grid boundary --
        neither one's title touching that boundary, so neither gets the
        outer-edge margin :meth:`tight_layout` reserves automatically -- can
        collide there: each box still needs room for its own tick labels
        and padding beyond its bare axes, and the ordinary column/row gap
        (sized only from the axes' own decorations) is not guaranteed to be
        enough. ``wspace``/``hspace`` (pixels, added on top of that gap, one
        or both) fix exactly that, independent of the tick-label-driven
        spacing itself -- unlike reaching for :meth:`subplots_adjust`,
        which would also throw away every margin :meth:`tight_layout`
        already computed (titles, tick labels, colorbars, a legend,
        ``suptitle``/``supxlabel``/``supylabel``) and require respecifying
        all of them by hand just to widen one gap.

        A title that *does* face an interior boundary (``title_position``
        pointing into the gap rather than out to the figure's own edge) is
        a different case, handled automatically without this method at
        all: it always gets at least enough clearance to avoid drawing on
        the neighboring group's own box, the same guarantee
        :meth:`tight_layout` already gives a title facing the true outer
        edge. Pass ``wspace``/``hspace`` here to reserve *more* than that
        automatic minimum (room to visually separate the two boxes, not
        just keep their titles from colliding), or when neither title
        faces the boundary at all -- the pure box-padding collision this
        method was originally written for, which nothing reserves for on
        its own.

        Applies only to the row/column boundaries that actually sit on the
        edge of a group's bounding box -- not every interior gap alike. Two
        rows paired inside the *same* group (a group spanning them both)
        stay exactly as tight as :meth:`tight_layout` would put them; only
        the boundary between that group and its neighbor -- where their two
        boxes would otherwise collide -- grows. A group spanning several
        rows/columns still only widens the boundaries at its own edges, not
        every boundary it happens to pass through.

        The figure grows to hold the extra room rather than shrinking the
        axes to fit it: :meth:`tight_layout` adds exactly the reserved
        pixels (each boundary that needs it, once) onto ``figsize`` itself,
        so a plot's own size is the same with or without this call, and
        calling it again with a different value re-derives the growth from
        the size last given to the constructor or :meth:`set_size_inches`
        rather than compounding onto an already-grown figure.

        Only takes effect through :meth:`tight_layout`; has no effect after
        a :meth:`subplots_adjust` call, which sets every margin manually.
        """
        if wspace is not None:
            self._group_wspace = float(wspace)
        if hspace is not None:
            self._group_hspace = float(hspace)
        self._layout_dirty = True
        return self

    def set_size_inches(self, w, h=None):
        """Resize the figure. Accepts ``(w, h)`` or two separate arguments."""
        if h is None:
            w, h = w
        self.figsize = (float(w), float(h))
        self._base_figsize = self.figsize
        if self._tight_pad is not None:
            self._layout_dirty = True   # re-fit: tight_layout bakes absolute pixels

    def get_size_inches(self):
        return self.figsize

    def set_dpi(self, dpi):
        self.style.dpi = float(dpi)
        if self._tight_pad is not None:
            self._layout_dirty = True

    def get_dpi(self):
        return self.style.dpi

    def delaxes(self, ax):
        """Remove ``ax`` from this figure (delegates to :meth:`Axes.remove`)."""
        ax.remove()

    def clf(self):
        """Clear the figure: drop every axes and figure-level decoration.

        Keeps ``figsize``/``style`` -- use a new :class:`Figure` for those.
        """
        self.axes = []
        self._id_index = {}
        self._sliders = {}
        self._slider_index_n = {}
        self._suptitle = None
        self._figure_legend = None
        self._supxlabel = None
        self._supylabel = None
        self._fig_texts = []
        self._groups = []
        self._group_wspace = None
        self._group_hspace = None
        self._tight_pad = None
        self._layout_dirty = False
        self._align_x_axes = _ALIGN_UNSET
        self._align_y_axes = _ALIGN_UNSET

    clear = clf

    def _register_slider(self, unit, index, n, values, label, is_global, axes_key):
        """Register (or validate) a slider unit and its connection index."""
        if unit in self._sliders:
            if self._sliders[unit]["n"] != n:
                raise ValueError(
                    f"plot_frames() series in slider unit {unit!r} must share "
                    f"n_frames (have {self._sliders[unit]['n']}, got {n})"
                )
            return
        if index is not None:
            if index in self._slider_index_n and self._slider_index_n[index] != n:
                raise ValueError(
                    f"plot_frames() series sharing slider index {index!r} must "
                    f"have the same n_frames (have {self._slider_index_n[index]}, "
                    f"got {n})"
                )
            self._slider_index_n[index] = n
        vals = ([float(v) for v in values] if values is not None
                else list(range(n)))
        if len(vals) != n:
            raise ValueError("slider_values length must equal n_frames")
        self._sliders[unit] = {
            "n": int(n), "values": vals, "label": label,
            "index": index, "global": bool(is_global), "axes": axes_key,
        }

    # -- axes construction --------------------------------------------------
    def add_axes(self, rect, projection=None) -> Axes:
        """Add an axes at ``rect = (left, bottom, width, height)`` (fractions).

        ``projection='polar'`` makes it a :class:`~plotpress.polar.PolarAxes`.
        """
        ax = _axes_class(projection)(self, rect)
        self.axes.append(ax)
        return ax

    def add_subplot(self, nrows=1, ncols=1, index=1, projection=None) -> Axes:
        """Add the ``index``-th axes (1-based) of an ``nrows`` x ``ncols`` grid.

        ``nrows`` may instead be a :class:`SubplotSpec` from
        ``fig.add_gridspec(...)[...]``, for an axes spanning multiple rows/
        columns -- its initial rect covers only the span's top-left cell;
        call :meth:`tight_layout`/:meth:`subplots_adjust` afterward to size it
        to the full span.

        ``projection`` accepts the same values as :meth:`add_axes`
        (``'polar'``).
        """
        if isinstance(nrows, SubplotSpec):
            spec = nrows
            placeholder = spec.row0 * spec.ncols + spec.col0 + 1
            ax = self.add_axes(
                _subplot_rect(spec.nrows, spec.ncols, placeholder, self._subplot_params),
                projection=projection)
            ax._subplotspec = spec
            return ax
        ax = self.add_axes(_subplot_rect(nrows, ncols, index, self._subplot_params),
                           projection=projection)
        ax._subplotspec = _cell_subplotspec(nrows, ncols, index)
        return ax

    def add_gridspec(self, nrows=1, ncols=1, **kwargs) -> GridSpec:
        """Return a :class:`GridSpec` for slicing into row/column spans.

        ``fig.add_subplot(fig.add_gridspec(2, 2)[0, :])`` spans both columns
        of the top row. Any ``left``/``right``/``top``/``bottom``/``wspace``/
        ``hspace`` kwargs become this figure's margins immediately -- see
        :class:`GridSpec`.
        """
        return GridSpec(self, nrows, ncols, **kwargs)

    def _check_id_available(self, id, owner):
        """Raise if ``id`` (an axes id, not ``None``) already belongs to a
        different axes in this figure. Shared by :meth:`Axes.set_id` and
        :meth:`adopt_axes` -- the two places an axes' id ever changes.
        """
        if id is None:
            return
        holder = self._id_index.get(id)
        if holder is not None and holder is not owner:
            raise ValueError(
                f"{id!r} is already used by another axes in this figure"
            )

    def adopt_axes(self, ax) -> Axes:
        """Merge an axes built standalone -- most commonly a copy that just
        crossed a process boundary -- into this figure, in place of
        whichever of this figure's own axes shares its grid position.

        A process boundary always hands back a *copy*: pickling an axes to
        send it into a ``joblib``/``multiprocessing`` worker and back never
        preserves object identity, however it looks -- ``ax.figure`` on
        what comes back is a copy of this figure too, not ``self``, and
        that copy's own ``ax.axes`` list still has the *worker's* version
        of everything, not this figure's. Passed straight to
        ``fig.axes.append(ax)``, it would render at the wrong position
        (or not enter the layout at all) and leave ``ax.figure`` pointing
        at that disconnected copy. ``adopt_axes`` fixes both: finds the
        axes already in ``self.axes`` whose :class:`SubplotSpec` matches
        ``ax``'s (same grid shape and cell span) and replaces it there --
        same list position, so :meth:`tight_layout`/:meth:`subplots_adjust`
        keep placing it exactly where that slot always was -- and
        reparents ``ax.figure`` to ``self``.

        A colorbar axes (``ax._subplotspec is None``, since it was never
        placed on the grid itself) has no slot to match -- it is appended
        instead, since :meth:`colorbar` always creates one that never
        existed in this figure to begin with. Adopt it and the axes it
        belongs to from the *same* returned result (e.g. both elements of
        a worker's ``return ax, cax``): pickling preserves the object
        graph *within* one call, so ``cax``'s own reference to ``ax``
        survives the round trip already pointing at the exact object this
        adopts, without anything further to fix up here.

        Only ever carries one axes' worth of state across that boundary --
        anything that compares axes by identity across *more than one* of
        them (:meth:`group`, a colorbar shared over several axes,
        :meth:`align_xlabels`) has to run after every worker's result has
        been adopted, against the real, adopted objects -- never before
        dispatch, and never inside the worker itself.

        An id set before crossing the process boundary (see
        :meth:`Axes.set_id`) is re-validated and re-registered against
        *this* figure's own id index here -- the worker's own figure never
        knew about this one's other axes, so a collision between two
        workers' independently-chosen ids is only ever catchable at the
        merge point, which is exactly this method. If the axes being
        replaced already belonged to a :meth:`group` (built, unusually,
        *before* dispatching it to a worker rather than after, the order
        the rest of this docstring recommends), every group referencing it
        -- its flat list and, for a :class:`GroupLayout`-built one, its own
        ``(row, col)`` grid -- is updated in place to reference the newly
        adopted axes instead, so a lookup through it doesn't keep pointing
        at the orphaned pre-adoption object.
        """
        ax.figure = self
        if ax._subplotspec is None:
            self._check_id_available(ax._id, ax)
            if ax._id is not None:
                self._id_index[ax._id] = ax
            self.axes.append(ax)
            return ax
        spec = ax._subplotspec
        for i, existing in enumerate(self.axes):
            s = existing._subplotspec
            if (s is not None and s.nrows == spec.nrows and s.ncols == spec.ncols
                    and s.row0 == spec.row0 and s.row1 == spec.row1
                    and s.col0 == spec.col0 and s.col1 == spec.col1):
                if existing._id is not None and self._id_index.get(existing._id) is existing:
                    del self._id_index[existing._id]
                self._check_id_available(ax._id, ax)
                if ax._id is not None:
                    self._id_index[ax._id] = ax
                self.axes[i] = ax
                for g in self._groups:
                    idx = [j for j, a in enumerate(g["axes"]) if a is existing]
                    for j in idx:
                        g["axes"][j] = ax
                    if g["axes_grid"] is not None:
                        g["axes_grid"][g["axes_grid"] == existing] = ax
                return ax
        raise ValueError(
            "adopt_axes(): no existing axes in this figure occupies "
            f"{spec.nrows}x{spec.ncols} rows {spec.row0}-{spec.row1}, "
            f"cols {spec.col0}-{spec.col1} -- adopt_axes() replaces an "
            "axes already on the grid, it does not create a new slot"
        )

    def subplots(self, nrows=1, ncols=1, squeeze=True, sharex=False, sharey=False,
                 projection=None):
        """Create a grid of axes; return a single Axes or a NumPy array of them.

        ``sharex``/``sharey`` link the grid so autoscaling spans every subplot
        (shared limits) and inner tick labels are hidden, like matplotlib.
        ``projection='polar'`` makes every axes in the grid polar.
        """
        grid = np.empty((nrows, ncols), dtype=object)
        for r in range(nrows):
            for c in range(ncols):
                index = r * ncols + c + 1
                ax = self.add_axes(_subplot_rect(nrows, ncols, index, self._subplot_params),
                                   projection=projection)
                ax._subplotspec = _cell_subplotspec(nrows, ncols, index)
                grid[r, c] = ax

        axlist = grid.ravel().tolist()
        if sharex:
            for r in range(nrows):
                for c in range(ncols):
                    grid[r, c]._sharex_group = axlist
                    if r != nrows - 1:            # hide labels off the bottom row
                        grid[r, c].set_xticklabels([])
        if sharey:
            for r in range(nrows):
                for c in range(ncols):
                    grid[r, c]._sharey_group = axlist
                    if c != 0:                    # hide labels off the left column
                        grid[r, c].set_yticklabels([])

        return _squeeze_grid(grid, nrows, ncols) if squeeze else grid

    def tight_layout(self, pad=0.02, collapse=None, auto_label_scale=False):
        """Auto-fit subplot margins so ticks/labels/titles never overflow.

        Measures each axes' decorations with the bundled font metrics and
        re-lays-out the subplot grid. Safe to call before or after
        :meth:`colorbar`; any colorbar over this grid is re-fitted afterwards.
        Also safe to call *before* the titles and axis labels exist: the fit is
        re-applied at render time if any of them change (see
        :meth:`_settle_layout`).

        The margin this reserves is only ever sized from one text row per
        tick/label -- it has no way to know an *unrotated* x tick label is
        wide enough to run into its neighbor, or that a title/group title is
        wider than the box it's centered over, without deciding on your
        behalf whether the right fix is a smaller font, rotated labels,
        shorter text, or a wider figure. By default this only warns about
        those cases, naming a concrete fix for each. Pass
        ``auto_label_scale=True`` to have it pick one of those fixes itself
        for the cases with a settable per-instance size -- x tick labels
        (:meth:`~plotpress.axes.Axes.tick_params`'s ``labelsize``), an axes
        title (:meth:`~plotpress.axes.Axes.set_title`'s ``size``), an axes
        x label (:meth:`~plotpress.axes.Axes.set_xlabel`'s ``size``), and a
        group title (:meth:`group`'s ``fontsize``) -- shrinking each just
        enough to fit, down to a legibility floor. Anything that still
        doesn't fit once its floor is reached still only warns.

        ``collapse`` reclaims whitespace :meth:`~plotpress.axes.Axes.remove`/
        :meth:`remove_group` leave behind, since neither reflows the grid on
        its own -- a removed axes' row/column keeps its ``nrows``/``ncols``
        exactly as it was (nothing else in the figure knows it's gone), and
        an emptied group's box freezes in its last position rather than
        disappearing (see :meth:`~plotpress.axes.Axes.remove`'s own
        docstring). Three values:

        - ``None`` (default): unchanged -- nothing collapses.
        - ``"grid"``: shrink any row/column of the grid that is now
          *entirely* empty (every axes that used to occupy it has been
          removed). A surviving axes never moves relative to its siblings --
          only whole empty rows/columns disappear, never a single gap inside
          an otherwise-populated one. Also drops any :meth:`group` whose
          members have all been removed, reclaiming the space its frozen
          box was holding.
        - ``"tight"``: pack groups and axes as close together as possible
          without breaking groupings -- not yet implemented (raises
          ``NotImplementedError``). Unlike ``"grid"``, this needs a real
          packing algorithm: a :meth:`group` can hold arbitrary,
          non-contiguous axes with no rectangular shape to pack, and a
          :class:`GroupLayout` group's cells share one grid with every
          other group, so packing one tighter can shift another's rows/
          columns too. Use ``"grid"`` for the well-defined subset of this
          in the meantime.
        """
        if collapse == "tight":
            raise NotImplementedError(
                "tight_layout(collapse='tight') isn't built yet -- packing "
                "groups and axes as tightly as possible without breaking "
                "groupings needs its own dedicated algorithm (a group() can "
                "hold arbitrary, non-contiguous axes with no rectangular "
                "shape to pack, and a GroupLayout group's cells share one "
                "grid with every other group, so packing one tighter can "
                "shift another's rows/columns too). Use collapse='grid' for "
                "the well-defined subset of this in the meantime: shrinking "
                "any row/column that's now entirely empty."
            )
        if collapse == "grid":
            _collapse_empty_grid_rows_and_cols(self)
            self._groups = [g for g in self._groups if g["axes"]]
        elif collapse is not None:
            raise ValueError(
                "tight_layout(): collapse must be None, 'grid', or 'tight', "
                f"got {collapse!r}"
            )

        self._tight_pad = float(pad)
        self._layout_dirty = False

        st = self.style
        # Base, un-grown pixel size -- group_spacing()'s reservations add to
        # this fresh each call (see Wpx/Hpx below), rather than compounding
        # onto whatever a previous tight_layout() call already grew figsize
        # to.
        Wpx0 = self._base_figsize[0] * st.dpi
        Hpx0 = self._base_figsize[1] * st.dpi
        specs = [ax for ax in self.axes
                 if ax._subplotspec is not None and not ax._is_colorbar]
        if not specs:
            return self
        _require_one_grid_shape(specs, "tight_layout")
        nrows, ncols = specs[0]._subplotspec.nrows, specs[0]._subplotspec.ncols

        # The top band stacks: a twiny's ticks and label sit directly above the
        # box, and the title goes above those. Taking the max of the two would
        # reserve room for whichever is taller and then draw them on each other.
        left_px = bottom_px = right_px = 0.0
        title_px = twin_top_px = 0.0
        for ax in specs:
            if ax._title:
                # 1.3x size, not 1x -- see the identical choice (and its own
                # reasoning) in the group-title extent below: the bundled
                # font metrics cover advance widths only, not vertical
                # extent, and a flat "+8" alone reserved just enough for the
                # title's own drawn offset from the box (_render_labels'
                # ``px_top - 8``), with none left over for the glyphs'
                # actual ascent above that baseline -- a title stacked over
                # the row above's own x label (a titled, x-labeled grid is
                # the ordinary case, not an edge case) rendered close enough
                # to touching that a browser's own font metrics, never
                # identical to the bundled advance-width tables to begin
                # with, tipped it into real overlap.
                title_px = max(title_px, (ax._title_size or st.title_size) * 1.3 + 8)
            if ax._axis_off:
                continue
            # tick_params(labelsize=...)/(length=...) overrides this axes' own
            # tick style -- svg.py already resolves them the same way (see
            # its own xst/yst) before drawing. Margin reservation has to
            # match what actually gets drawn, or a grid whose panels shrink
            # their tick labels to fit (a common move on small multiples)
            # keeps reserving margin sized for the figure-wide default,
            # over-widening every gap next to it.
            xst = st.copy(**ax._tick_overrides["x"]) if ax._tick_overrides["x"] else st
            yst = st.copy(**ax._tick_overrides["y"]) if ax._tick_overrides["y"] else st
            yt = ax._resolve_yticks()
            # Measure the labels as drawn: explicit set_yticklabels strings are
            # usually far wider than the numbers they replace (category names),
            # and sizing the margin from the tick *values* clips them.
            ylabels = ax._resolve_yticklabels(yt)
            ytw = max((yst.text_width(l, yst.tick_label_size) for l in ylabels),
                      default=0.0)
            if yst.tick_label_rotation:
                ytheta = math.radians(yst.tick_label_rotation)
                yc, ys = abs(math.cos(ytheta)), abs(math.sin(ytheta))
                ytw = ytw * yc + yst.tick_label_size * ys
            right_px = max(right_px, xst.tick_label_size * 0.6)  # last x label overhang

            # A twin draws its axis on the side *opposite* its parent, so its
            # decorations belong to the other margin. Measuring them into the
            # left/bottom bands padded the wrong side and left the twin's own
            # tick labels and axis label to overflow -- off the canvas for a
            # single axes, and into the next panel for a grid.
            # A rotated x tick label's own footprint depends on the string
            # it's rotating, not just one fixed text row -- _max_xtick_width
            # is only worth computing on this (uncommon) path, mirroring how
            # ytw above is always needed but this isn't.
            if xst.tick_label_rotation:
                xt_ = ax._resolve_xticks()
                xtlabels = ax._resolve_xticklabels(xt_)
                xtw = max((xst.text_width(l, xst.tick_label_size) for l in xtlabels),
                         default=0.0)
                theta = math.radians(xst.tick_label_rotation)
                c, s = abs(math.cos(theta)), abs(math.sin(theta))
                rot_w = xtw * c + xst.tick_label_size * s
                rot_h = xtw * s + xst.tick_label_size * c
                xdec = xst.tick_size + rot_h + 4
                # The label is anchored at its own end (see svg._render_ticks),
                # so it reaches away from the tick horizontally too -- past
                # the figure's own left edge for column 0, since nothing else
                # widens an *interior* column boundary for this (that's the
                # same unsolved interior-gap tick labels already have
                # unrotated -- rotation doesn't make it worse there, only the
                # outer edge, which would otherwise clip clean off the canvas
                # rather than merely crowd a neighbor, is handled here).
                # rot_w over-reserves slightly (it's the full rotated-box
                # width, not just the reach from an end anchor) -- generous
                # on purpose, the same tradeoff every other approximate
                # extent in this function makes.
                if ax._subplotspec.col0 == 0:
                    left_px = max(left_px, rot_w)
            else:
                xdec = xst.tick_size + xst.tick_label_size + 4

            if ax._twin_of is not None:
                if ax._twin_shared == "x":                   # twinx: y on the right
                    rdec = yst.tick_size + ytw + 4
                    if ax._shown_ylabel():
                        rdec += (ax._ylabel_size or st.label_size) + 6
                    right_px = max(right_px, rdec)
                else:                                        # twiny: x on the top
                    tdec = xdec
                    if ax._shown_xlabel():
                        tdec += (ax._xlabel_size or st.label_size) + 6
                    twin_top_px = max(twin_top_px, tdec)
                continue

            # tick_top()/tick_right() move an axes' own ticks off the default
            # bottom/left edge, so their decoration band moves with them --
            # into the same top/right bands a twin's opposite-side ticks use,
            # rather than the bottom/left band the default side would need.
            ldec = yst.tick_size + ytw + 4
            if ax._shown_ylabel():
                ldec += (ax._ylabel_size or st.label_size) + 6
            if ax._ytick_side == "right":
                right_px = max(right_px, ldec)
            else:
                left_px = max(left_px, ldec)
            bdec = xdec
            if ax._shown_xlabel():
                bdec += (ax._xlabel_size or st.label_size) + 6
            if ax._xtick_side == "top":
                twin_top_px = max(twin_top_px, bdec)
            else:
                bottom_px = max(bottom_px, bdec)

        top_px = title_px + twin_top_px

        # Figure-level titles/labels reserve their own outer-margin band --
        # kept apart from top_px/bottom_px/left_px themselves (which also
        # seed gap_w/gap_h below, the *interior* row/col gap) since, unlike a
        # per-axes title or tick label -- which can legitimately sit on any
        # interior row/col boundary and so must widen every gap along with
        # it -- a suptitle/supxlabel/supylabel draws once, outside the whole
        # grid, and must never widen an interior gap it is nowhere near.
        fig_top_px = fig_bottom_px = fig_left_px = 0.0
        if self._suptitle:
            fig_top_px += (self._suptitle.get("size") or st.title_size * 1.5) + 6
        if self._supxlabel:
            fig_bottom_px += (self._supxlabel.get("size") or st.label_size * 1.2) + 6
        if self._supylabel:
            fig_left_px += (self._supylabel.get("size") or st.label_size * 1.2) + 6

        # A group's title, when it faces the grid's own outer edge, needs the
        # same kind of band reserved -- otherwise it (or the box itself, for
        # a top-facing title over a titled top row) draws off the canvas or
        # over the outermost panels. A group that doesn't reach that edge
        # (an interior cluster) has its title facing a row/col gap instead --
        # handled separately below (row_hspace_title_px/col_wspace_title_px),
        # aimed at just the one boundary that title actually faces, not
        # folded in here: growing every row/col for one arbitrary interior
        # group's title would be wrong the same way it would be for
        # group_spacing() itself (see its own docstring on that). Kept
        # separate from left_px/top_px/etc. themselves too: those also seed
        # gap_w/gap_h below (the interior row/col gap), and a group's own
        # margin reservation -- whichever edge it faces -- must never widen
        # every interior gap along with it.
        group_top_px = group_bottom_px = group_left_px = group_right_px = 0.0
        # Which interior row/col boundaries actually border a group's own
        # bounding box -- group_spacing() only widens *these*, not every
        # boundary alike, so two rows paired inside the same group stay as
        # tight as tight_layout() would put them; only the seam between that
        # group and its neighbor grows. Every edge of the box counts here
        # (not just the title-facing one above): the box itself carries
        # ``pad`` clearance on all four sides regardless of where its title
        # sits, and two boxes facing each other across a boundary neither
        # title touches would otherwise collide with no reservation for
        # either of them.
        col_needs_wspace = [False] * (ncols - 1)
        row_needs_hspace = [False] * (nrows - 1)
        # A title (or supxlabel/supylabel-grown box) facing an *interior*
        # boundary (row/col > 0, i.e. NOT the figure's own outer edge --
        # group_top_px/etc. above already cover that case) needs exactly the
        # same clearance group_top_px would give it, just aimed at the one
        # boundary it actually sits next to rather than the figure's edge.
        # Tracked as two separate arrays per boundary, not one -- "above"
        # (a group whose bottom edge, r1, IS this boundary, pushing content
        # down into it) and "below" (a group whose top edge, r0, is the
        # *next* row, pushing content up into this same boundary from the
        # other side). Two different groups can face one interior boundary
        # from opposite sides at once (one ending a row-band with a
        # bottom-position title just below its own box, the next starting
        # right after with a top-position title just above its own) -- that
        # needs both extents *added*, not maxed, since they occupy different
        # halves of the same physical gap. Groups sharing the *same* side of
        # one boundary (two side by side in the same row-band, say) still
        # only need the single largest between them -- max() within each
        # array, sum() only across the two arrays -- or a grid with many
        # groups along one edge would accumulate every one of their extents
        # into one ever-growing gap instead of a fixed, correctly-sized one.
        row_above_px = [0.0] * (nrows - 1)
        row_below_px = [0.0] * (nrows - 1)
        col_left_px = [0.0] * (ncols - 1)
        col_right_px = [0.0] * (ncols - 1)
        for g in self._groups:
            g_specs = [ax for ax in g["axes"] if ax._subplotspec is not None]
            if g_specs:
                r0 = min(ax._subplotspec.row0 for ax in g_specs)
                r1 = max(ax._subplotspec.row1 for ax in g_specs)
                c0 = min(ax._subplotspec.col0 for ax in g_specs)
                c1 = max(ax._subplotspec.col1 for ax in g_specs)
            elif g["_ghost_specs"] and g["_ghost_grid_shape"] == (nrows, ncols):
                # Every one of this group's own axes has already left it
                # (see Axes.remove()), but it still draws a title/box (see
                # svg._ghost_group_rects) at its former cells -- which still
                # needs its own margin reserved here the same as a live
                # group's would, or a title facing an interior boundary
                # (row_below_px/etc. below) collides with the neighboring
                # row/column that boundary was never widened for.
                r0 = min(s[0] for s in g["_ghost_specs"])
                r1 = max(s[1] for s in g["_ghost_specs"])
                c0 = min(s[2] for s in g["_ghost_specs"])
                c1 = max(s[3] for s in g["_ghost_specs"])
            else:
                continue
            size = g["fontsize"] or st.title_size
            pos = g["title_position"]
            # pad is (left, right, top, bottom) -- the margin this title's
            # own side needs to reserve is that side's own clearance, not
            # some other edge's (an asymmetric pad -- tight on the side
            # butting a neighboring group, loose on the title side -- would
            # otherwise reserve the wrong amount here).
            pad_l, pad_r, pad_t, pad_b = g["pad"]
            # Four independent per-edge *text* extents, not one tied to
            # title_position -- a supxlabel/supylabel (below) always sits at
            # the bottom/left edge regardless of where the *title* sits, so
            # a group with title_position="bottom" *and* a supxlabel needs
            # both reserved on that same edge, stacked (the title outside
            # the box, the supxlabel inside it growing the box into the
            # title's own margin) -- additive, not a single value picked by
            # title_position alone. Deliberately *not* including pad here --
            # see the outer-edge extents just below for why that's a
            # separate concern, added on only there.
            top_text = bottom_text = left_text = right_text = 0.0
            if pos in ("top", "bottom"):
                # 1.3x size -- not 1x -- for the same reason title_px above
                # adds a flat +8 rather than measuring real glyph ascent:
                # bundled font metrics only cover advance widths (see
                # fonts/), not vertical extents, so this errs generous
                # rather than risk the title's own glyphs clipping the
                # canvas edge.
                title_extent = size * 1.3 + 10
                if pos == "top":
                    top_text += title_extent
                else:
                    bottom_text += title_extent
            else:
                # A left/right title runs horizontally alongside the box, not
                # centered over it -- its own rendered *width* is what has to
                # fit in the reserved margin here, not a height allowance.
                title_extent = st.text_width(g["title"], size, bold=True) + 12
                if pos == "left":
                    left_text += title_extent
                else:
                    right_text += title_extent
            # supxlabel/supylabel draw *inside* the box, near its bottom/left
            # edge (see _render_groups) -- unlike the title, always that one
            # fixed edge regardless of title_position, mirroring
            # Figure.supxlabel()/supylabel() themselves (always bottom/left,
            # no position argument). The box's own edge has to move outward
            # to hold this new inset band without shrinking the member axes
            # into it, so it needs the exact same margin reservation a
            # title facing that edge would.
            if g.get("supxlabel"):
                sx_size = g.get("supxlabel_size") or st.label_size * 1.2
                bottom_text += sx_size * 1.2 + 10
            if g.get("supylabel"):
                sy_size = g.get("supylabel_size") or st.label_size * 1.2
                left_text += sy_size + 10
            # Outer-edge extents fold this group's own pad on that side in
            # too, unconditionally -- interior boundaries (below) don't,
            # left exactly as they were. _group_bbox grows the box by pad on
            # *all four* sides regardless of where the title sits (that's
            # the whole point of pad's own (left, right, top, bottom) shape
            # -- tight on the side facing a neighbor, generous elsewhere),
            # but only group_spacing() -- an explicit, separately-tuned
            # request -- was ever meant to buy extra room at an *interior*
            # boundary (see its own docstring); the figure's own outer edge
            # has no such explicit knob, and nothing else was reserving pad
            # there at all. Missing this let a group's own box run past the
            # canvas edge outright (not just crowd something else)
            # whenever its pad on a non-title-facing outer edge exceeded
            # the ordinary tick-label margin that edge is otherwise sized
            # from.
            top_extent, bottom_extent = top_text + pad_t, bottom_text + pad_b
            left_extent, right_extent = left_text + pad_l, right_text + pad_r
            # "Touches that edge" -- the group's bounding box reaches row 0 /
            # the last row / column 0 / the last column -- not "every one of
            # its axes sits in that single row/col": a group spanning several
            # rows in a column-band (say) still needs a top-margin band for
            # its top-facing title even though most of its own axes are in
            # rows 1+, same as one spanning a single row would.
            # max(), not +=: every group touching a given outer edge shares
            # that same margin band (they're side by side along it, not
            # stacked), so the band only has to be tall/wide enough for the
            # single largest one reaching it -- not the sum of every group's
            # own extent. A grid with many groups along one edge (e.g. one
            # group per column, all title_position="top") used to accumulate
            # every one of their extents into one ever-growing top margin,
            # producing a band of blank space scaling with the number of
            # columns instead of a fixed, correctly-sized one.
            # The interior-boundary mirror of the outer-edge branches above:
            # a "top" title (or a supylabel-grown box, etc.) on a group that
            # does NOT reach row 0 sits in the gap *above* its own box
            # instead -- i.e. right on the boundary between rows r0-1 and
            # r0 -- so that's the one boundary that needs room for it, the
            # same way group_top_px reserves room at the figure's own top
            # edge. Without this, a group_spacing() value sized only for
            # ordinary tick-label/pad clearance (its own documented job)
            # leaves nothing for the title/supxlabel itself, and it draws
            # right on top of the neighboring group's own box. Raw extents
            # only here (max() within the same side -- see row_above_px's
            # own comment above for why); turned into an actual reserved
            # deficit, net of the ordinary gap and combined across both
            # sides of the boundary, once every group has contributed.
            if r0 == 0:
                group_top_px = max(group_top_px, top_extent)
            elif top_text:
                row_below_px[r0 - 1] = max(row_below_px[r0 - 1], top_text)
            if r1 == nrows - 1:
                group_bottom_px = max(group_bottom_px, bottom_extent)
            elif bottom_text:
                row_above_px[r1] = max(row_above_px[r1], bottom_text)
            if c0 == 0:
                group_left_px = max(group_left_px, left_extent)
            elif left_text:
                col_right_px[c0 - 1] = max(col_right_px[c0 - 1], left_text)
            if c1 == ncols - 1:
                group_right_px = max(group_right_px, right_extent)
            elif right_text:
                col_left_px[c1] = max(col_left_px[c1], right_text)
            if r0 > 0:
                row_needs_hspace[r0 - 1] = True
            if r1 < nrows - 1:
                row_needs_hspace[r1] = True
            if c0 > 0:
                col_needs_wspace[c0 - 1] = True
            if c1 < ncols - 1:
                col_needs_wspace[c1] = True

        # Now that every group has contributed its own raw extent to
        # whichever side(s) of whichever boundary it touches, each
        # boundary's total reservation is simply both sides added together
        # (see row_above_px's own comment above for why sides add but
        # same-side groups don't) -- added on top of the ordinary
        # tick-label-driven gap (bottom_px+top_px / left_px+right_px,
        # already baked into base_gap_h/base_gap_w below), not compared
        # against it. A group's own box already wraps *outward* from a
        # plain axes' own natural tick/title clearance (_group_axes_extra
        # mirrors bottom_px/top_px's exact formulas) -- pad/supxlabel/
        # supylabel/title reach *further* still, past where that natural
        # clearance already ends, so the two are always stacked, never
        # alternatives to pick the larger of. Comparing them with max()
        # here (an earlier version of this) reserved only whichever was
        # bigger, silently assuming the smaller one was already contained
        # within it -- true by coincidence for a single modest title in an
        # otherwise generously tick-labeled grid, false in general, and a
        # supxlabel/supylabel's own extent was reliably large enough to
        # expose it: two groups facing the same interior boundary from
        # opposite sides landed close enough to visibly overlap.
        row_hspace_title_px = [a + b for a, b in zip(row_above_px, row_below_px)]
        col_wspace_title_px = [a + b for a, b in zip(col_left_px, col_right_px)]

        # group_spacing() grows the figure to hold its reservation instead of
        # shrinking the axes to fit it -- each boundary that actually needs
        # it (computed above) adds the requested pixels once, on top of the
        # *base* size (the one last given to the constructor or
        # set_size_inches()), so a repeated tight_layout() call re-derives
        # this fresh rather than compounding growth onto an already-grown
        # figsize.
        # Each boundary gets the user's own explicit group_spacing() request
        # (its established, tested meaning: exactly this many pixels added
        # on top of the ordinary gap, whether or not a title is involved)
        # PLUS whatever minimum an interior-facing title needs to clear the
        # neighboring box (row_hspace_title_px/col_wspace_title_px, computed
        # above as a deficit already net of the ordinary gap) -- additive,
        # not max(), so group_spacing() still means something even on a
        # boundary a title already forces open: text width is an estimate,
        # not a measurement (see :ref:`limitations`), and the automatic
        # minimum alone can leave a long title only a few pixels of real
        # slack past that estimate -- group_spacing() is exactly how to ask
        # for genuinely more room than the minimum, the same as it already
        # was for a boundary with no title on it at all. A boundary neither
        # a title nor group_spacing() ever touches stays at 0, unchanged.
        col_boundary_px = [(self._group_wspace or 0.0) + title_px if needs else 0.0
                          for needs, title_px in zip(col_needs_wspace, col_wspace_title_px)]
        row_boundary_px = [(self._group_hspace or 0.0) + title_px if needs else 0.0
                          for needs, title_px in zip(row_needs_hspace, row_hspace_title_px)]
        extra_w_px = sum(col_boundary_px)
        extra_h_px = sum(row_boundary_px)
        Wpx = Wpx0 + extra_w_px
        Hpx = Hpx0 + extra_h_px
        self.figsize = (Wpx / st.dpi, Hpx / st.dpi)

        # The outer edge pad is sized from the figure's *base* dimensions --
        # group_spacing()'s growth is purely extra interior room, and must
        # not also inflate this independent margin.
        edge = pad * min(Wpx0, Hpx0) + 4
        left = (left_px + group_left_px + fig_left_px + edge) / Wpx
        right = 1 - (right_px + group_right_px + edge) / Wpx
        bottom = (bottom_px + group_bottom_px + fig_bottom_px + edge) / Hpx
        top = 1 - (top_px + group_top_px + fig_top_px + edge) / Hpx
        # An interior column gap has to hold the right-hand decorations of the
        # column to its left as well as the left-hand ones of the column to its
        # right -- the row gap has always summed both bands, and a twinx in a
        # grid is what makes the missing term visible. Groups are excluded
        # (see above): they never contribute to an interior gap.
        base_gap_w = (left_px + right_px) / Wpx          # interior column gap
        base_gap_h = (bottom_px + top_px) / Hpx          # interior row gap
        # group_spacing() (or an interior title's own minimum, computed
        # above into col_boundary_px/row_boundary_px) is the one deliberate
        # exception: extra room between subplots specifically for group
        # boxes, independent of what their tick labels alone would need --
        # added only to the boundaries that actually border a group, not
        # folded into left_px/etc. above, so it never touches the outer
        # margin those also seed.
        base_gap_w_list = [base_gap_w] * (ncols - 1)
        base_gap_h_list = [base_gap_h] * (nrows - 1)
        protected_w_list = [px / Wpx for px in col_boundary_px]
        protected_h_list = [px / Hpx for px in row_boundary_px]
        axw, gap_w_list = _fit_cells(right - left, ncols, base_gap_w_list, protected_w_list)
        axh, gap_h_list = _fit_cells(top - bottom, nrows, base_gap_h_list, protected_h_list)

        self._grid_placement = {
            "nrows": nrows, "ncols": ncols, "left": left, "bottom": bottom,
            "axw": axw, "axh": axh, "gap_w": gap_w_list, "gap_h": gap_h_list,
        }
        _place_spec_rects(specs, nrows, ncols, left, bottom, axw, axh, gap_w_list, gap_h_list)
        self._finish_grid_relayout(specs)
        if auto_label_scale and _auto_scale_overlapping_labels(self, specs, Wpx, Hpx):
            # Shrinking a tick/title font changes what tight_layout() itself
            # needs to reserve (a smaller bottom_px, mainly) -- re-run once,
            # fully, rather than leave the margin sized for the text that no
            # longer exists. auto_label_scale=False this time: shrinking
            # never needs a second correction once applied, and this also
            # bounds the recursion to exactly one extra pass.
            return self.tight_layout(pad=pad, collapse=collapse, auto_label_scale=False)
        _warn_about_text_overflow(self, specs, Wpx, Hpx)
        return self

    def _finish_grid_relayout(self, specs):
        """Shared tail of :meth:`tight_layout`/:meth:`subplots_adjust`.

        Both rewrite every grid axes' ``_rect`` from scratch, which undoes
        whatever a figure legend or colorbar had already stolen from it, and
        leaves any ``align_xlabels``/``align_ylabels`` override pointing at
        stale pixel offsets. Reapply all three, in this order: alignment must
        measure the *final* (already-shrunk) boxes, so it runs last.
        """
        # Take back the figure-legend band first, so a colorbar then fits
        # inside what is actually left (same ordering colorbar needs below).
        _layout_figure_legend(self)

        # Colorbars over axes this pass did not touch are left alone, since
        # their parents are still carrying the original steal.
        for cax in self.axes:
            if cax._is_colorbar and cax._cbar_parents:
                if all(p in specs for p in cax._cbar_parents):
                    _layout_colorbar(cax)

        # Insets are positioned as a fraction of their parent's rect, which
        # the reflow above may have just moved -- re-derive rather than let
        # them drift from where their parent ended up.
        for iax in self.axes:
            if iax._inset_parent is not None:
                _layout_inset(iax)

        if self._align_x_axes is not _ALIGN_UNSET:
            self.align_xlabels(self._align_x_axes)
        if self._align_y_axes is not _ALIGN_UNSET:
            self.align_ylabels(self._align_y_axes)

    def subplots_adjust(self, left=None, right=None, top=None, bottom=None,
                        wspace=None, hspace=None):
        """Directly set the subplot grid's margins (matplotlib's own knobs).

        Only the given kwargs change; the others keep their last value
        (initially matplotlib's own defaults). Mutually exclusive with
        :meth:`tight_layout` -- both rewrite every grid axes' rect from
        scratch, so whichever is called last wins; this also clears
        ``tight_layout``'s pending re-fit so :meth:`_settle_layout` doesn't
        undo it on the next render.
        """
        sp = self._subplot_params
        for key, val in (("left", left), ("right", right), ("top", top),
                         ("bottom", bottom), ("wspace", wspace), ("hspace", hspace)):
            if val is not None:
                sp[key] = float(val)
        self._tight_pad = None
        self._layout_dirty = False

        specs = [ax for ax in self.axes
                 if ax._subplotspec is not None and not ax._is_colorbar]
        if not specs:
            return self
        _require_one_grid_shape(specs, "subplots_adjust")
        nrows, ncols = specs[0]._subplotspec.nrows, specs[0]._subplotspec.ncols

        avail_w = sp["right"] - sp["left"]
        avail_h = sp["top"] - sp["bottom"]
        axw = avail_w / (ncols + sp["wspace"] * (ncols - 1))
        axh = avail_h / (nrows + sp["hspace"] * (nrows - 1))
        gap_w, gap_h = axw * sp["wspace"], axh * sp["hspace"]

        gap_w_list, gap_h_list = [gap_w] * (ncols - 1), [gap_h] * (nrows - 1)
        self._grid_placement = {
            "nrows": nrows, "ncols": ncols, "left": sp["left"], "bottom": sp["bottom"],
            "axw": axw, "axh": axh, "gap_w": gap_w_list, "gap_h": gap_h_list,
        }
        _place_spec_rects(specs, nrows, ncols, sp["left"], sp["bottom"], axw, axh,
                          gap_w_list, gap_h_list)
        self._finish_grid_relayout(specs)
        return self

    def align_xlabels(self, axes=None):
        """Align the x-axis labels of ``axes`` (default: all) to one baseline.

        Panels with different tick-label widths otherwise put their x label at
        different heights below the box. Only axes side by side in the same
        *row* (matching ``SubplotSpec`` row span) are aligned with each other
        -- like matplotlib, this does not pull together labels in different
        rows, which sit under different boxes at different y positions and
        have no shared "depth" worth matching. Axes with no ``_subplotspec``
        (a custom ``add_axes`` layout) form one fallback group together.
        Re-applied automatically after :meth:`tight_layout`/
        :meth:`subplots_adjust` reflow the grid.
        """
        from ..backends.svg import _effective_rect, _pixel_rect

        self._align_x_axes = axes
        axlist = [a for a in (axes if axes is not None else self.axes)
                 if a._shown_xlabel() and not a._axis_off]
        if not axlist:
            return self
        st = self.style
        W = self.figsize[0] * st.dpi
        H = self.figsize[1] * st.dpi

        def row_key(ax):
            spec = ax._subplotspec
            return None if spec is None else (spec.row0, spec.row1)

        for group in _group_by(axlist, row_key):
            ys = []
            for ax in group:
                (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
                _, px_top, _, px_h = _effective_rect(
                    ax, *_pixel_rect(ax, W, H), (xmin, xmax), (ymin, ymax))
                ys.append(px_top + px_h + st.tick_size + st.tick_label_size
                         + (ax._xlabel_size or st.label_size) + 4)
            y = max(ys)
            for ax in group:
                ax._xlabel_y_override = y
        return self

    def align_ylabels(self, axes=None):
        """Align the y-axis labels of ``axes`` (default: all) to one column.

        See :meth:`align_xlabels`: this aligns the *leftmost* position any
        panel's y label needs, but only among axes stacked in the same
        *column* (matching ``SubplotSpec`` column span) -- panels in
        different columns sit under different boxes and are not pulled
        together.
        """
        from ..backends.svg import _effective_rect, _max_ytick_width, _pixel_rect

        self._align_y_axes = axes
        axlist = [a for a in (axes if axes is not None else self.axes)
                 if a._shown_ylabel() and not a._axis_off]
        if not axlist:
            return self
        st = self.style
        W = self.figsize[0] * st.dpi
        H = self.figsize[1] * st.dpi

        def col_key(ax):
            spec = ax._subplotspec
            return None if spec is None else (spec.col0, spec.col1)

        for group in _group_by(axlist, col_key):
            xs = []
            for ax in group:
                (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
                px_left, _, _, _ = _effective_rect(
                    ax, *_pixel_rect(ax, W, H), (xmin, xmax), (ymin, ymax))
                xs.append(px_left - st.tick_size - _max_ytick_width(ax, st)
                         - (ax._ylabel_size or st.label_size) - 4)
            x = min(xs)
            for ax in group:
                ax._ylabel_x_override = x
        return self

    def align_labels(self, axes=None):
        """Align both x and y axis labels; see :meth:`align_xlabels`/:meth:`align_ylabels`."""
        self.align_xlabels(axes)
        self.align_ylabels(axes)
        return self

    # -- figure-level legend ------------------------------------------------
    def legend(self, ax=None, loc="lower center", ncol=1, title=None,
               pad=0.01, fontsize=None, framealpha=0.85, handles=None,
               labels=None, bbox_to_anchor=None) -> "Figure":
        """One legend for the whole figure, drawn from labelled artists.

        The counterpart to :meth:`colorbar` over a list of axes: a grid whose
        panels all plot the same series wants one legend, not the same entries
        repeated in every panel. Labels are de-duplicated across the axes, so
        each series appears once however many panels draw it.

        ``ax`` selects which axes contribute (default: all of them).
        ``fontsize``/``framealpha`` match :meth:`Axes.legend`.

        ``handles`` overrides which artists appear -- any plotpress artist,
        from any axes (or none), in the order given, regardless of their own
        ``label`` -- the only way to legend a figure whose panels are
        meshes/contours/filled regions with no labeled *line* artist to draw
        from. Pair with ``labels`` to also override the text shown for each,
        positionally; without it, each handle's own ``label`` is used.
        ``handles``/``labels`` take precedence over ``ax`` (a handle already
        names its own source).

        ``loc`` names a placement in **figure** coordinates. The four outside
        placements -- ``"lower center"``, ``"upper center"``, ``"right"`` and
        ``"center left"`` (also ``"center right"``) -- reserve a band at that
        edge and shrink the subplot grid to fit, so the legend never lands on a
        plot. Any other name overlays without reserving, matching how an axes
        legend sits inside its own rect. ``bbox_to_anchor=(x, y)``, in whole-
        figure fraction coordinates (``(0, 0)`` bottom-left, ``(1, 1)``
        top-right), places the ``loc`` corner of the legend box at that exact
        point instead of ``loc``'s own inset/edge position -- the common way
        to put a figure-level legend just outside every panel, e.g.
        ``loc="upper left", bbox_to_anchor=(1.0, 1.0)``. Whether space is
        reserved is still purely up to ``loc`` (one of the four named edges
        above, or not) -- ``bbox_to_anchor`` only fine-tunes where inside (or
        outside) that reservation, if any, the box actually lands, and can
        place it outside the figure canvas entirely.

        Order relative to :meth:`tight_layout` does not matter -- the reservation
        is re-applied whenever the grid is reflowed.
        """
        if handles is not None:
            handles = list(handles)
            if labels is not None:
                labels = list(labels)
                if len(labels) != len(handles):
                    # zip() truncates silently otherwise -- a caller who
                    # gave one fewer label than handle would get a legend
                    # where the last entry quietly keeps its old (often
                    # unset) label instead of anything reachable from this
                    # call, with no sign anything was wrong.
                    raise ValueError(
                        f"legend(): got {len(handles)} handles but "
                        f"{len(labels)} labels -- pass one label per handle"
                    )
                for h, lbl in zip(handles, labels):
                    h.label = lbl
        self._figure_legend = {
            "axes": _flatten_axes(ax) if ax is not None else None,
            "loc": loc,
            "ncol": max(1, int(ncol)),
            "title": title,
            "pad": float(pad),
            "fontsize": fontsize,
            "framealpha": framealpha,
            "handles": handles,
            "bbox_to_anchor": (None if bbox_to_anchor is None else
                              (float(bbox_to_anchor[0]), float(bbox_to_anchor[1]))),
        }
        _layout_figure_legend(self)
        return self

    # -- colorbar -----------------------------------------------------------
    def colorbar(self, mappable, ax, fraction=0.05, pad=0.02, label=None,
                 ticks=None, format=None) -> Axes:
        """Add a colorbar for ``mappable``.

        ``ax`` may be a single :class:`~plotpress.axes.Axes` (the colorbar
        steals space from it) or a list / array of axes (one **shared** colorbar
        spanning them all, placed on their right -- the grid is squeezed to make
        room). All the axes should share the mappable's ``vmin``/``vmax`` for the
        shared bar to describe them accurately.

        ``label`` sets what the color scale means (equivalent to, and just a
        convenience for, ``cax.set_title(label)`` on the returned axes --
        there is no separate ``set_label``). ``ticks`` fixes the bar's own
        tick positions instead of the norm's auto-generated ones (a
        ``BoundaryNorm``'s bin edges, or just a shorter list for a crowded
        scale); ``format`` overrides the tick labels' formatting -- a
        ``%``-style string (``"%.1f"``, ``"%d%%"``) or a callable taking one
        value and returning its label -- over whichever tick values end up
        in play.

        Order relative to :meth:`tight_layout` does not matter -- the steal is
        recorded and re-applied whenever the grid is reflowed.
        """
        if mappable is None or not hasattr(mappable, "norm"):
            raise TypeError(
                "colorbar(): mappable must be an artist with a color norm "
                "-- what pcolormesh()/imshow()/hexbin()/scatter(c=...) "
                f"returns -- got {mappable!r}"
            )
        if not (fraction > 0):
            raise ValueError(
                f"colorbar(): fraction must be > 0 (the share of the "
                f"parent axes' width the bar steals), got {fraction!r} -- "
                "zero/negative produces a colorbar axes with negative "
                "width, an invalid layout."
            )
        cax = self.add_axes((0.0, 0.0, 1.0, 1.0))   # rect set by _layout_colorbar
        cax._is_colorbar = True
        cax._cbar_source = mappable
        cax._cbar_parents = _flatten_axes(ax)
        cax._cbar_fraction = float(fraction)
        cax._cbar_pad = float(pad)
        cax._cbar_ticks = ticks
        cax._cbar_format = format
        if label is not None:
            cax.set_title(label)
        _layout_colorbar(cax)
        return cax

    # -- serialization ------------------------------------------------------
    def to_svg(self) -> str:
        return figure_to_svg(self)

    def to_vega(self, mesh_data: bool = False) -> dict:
        """A real Vega (not Vega-Lite) v5 JSON specification, as a plain
        ``dict`` -- ``json.dumps(fig.to_vega(), indent=2)`` for the string,
        or hand the dict itself to a Vega runtime that already accepts a
        Python object.

        Unlike ``to_svg()``/``to_html()``, the result needs a separate Vega
        renderer to actually draw (``vega-embed`` in a browser, the
        ``vg2svg``/``vg2png`` CLI tools, an Observable notebook, IPython's
        own ``vega`` MIME renderer, ...) -- it is a real, standalone,
        portable specification, not a rendered artifact, so no plotpress or
        Python is needed at render time. One axes becomes one Vega
        ``group`` mark with its own local scales/axes/marks, positioned at
        that axes' own resolved pixel rect. Line/scatter/bar charts use
        genuine ``field``/``scale``-encoded marks; everything else reuses
        the same pixel-space primitives ``to_svg()`` itself draws from
        (:mod:`plotpress.primitives`), so it is visually exact but frozen at
        this export's own size/limits -- not reactive to a Vega zoom/pan
        signal or a runtime domain change the way the line/scatter/bar
        marks are. See :mod:`plotpress.vega`'s own module docstring for the
        full design rationale, including what's skipped (box plots,
        violins, quiver, contour, event plots, wind barbs, tables -- each
        emits a ``UserWarning`` naming it and continues exporting the rest
        of the figure) and what never carries over regardless (plotpress's
        own interactive toolbar; Vega has its own separate interaction
        model instead, reachable by wiring up ``signals`` on the result).

        ``mesh_data=True`` opts a ``pcolormesh``/mesh-backed ``imshow``
        into real per-cell ``rect`` marks with a genuine field+scale color
        encoding, instead of the default rasterized ``image`` mark --
        reactive and queryable, but only for meshes small/simple enough to
        stay unambiguous (a rectilinear grid, a plain linear color norm, a
        colormap with a matching named Vega scheme, at most ~2000 cells --
        the same threshold ``pcolormesh(rasterized=None)``'s own auto-mode
        already uses). A mesh that doesn't qualify still gets the image
        mark, with a ``UserWarning`` naming why.
        """
        from ..backends.vega import figure_to_vega
        return figure_to_vega(self, mesh_data=mesh_data)

    def to_vega_lite(self, mesh_data: bool = False) -> tuple:
        """A Vega-Lite v5 specification for this figure.

        Unlike :meth:`to_svg`/:meth:`to_html`/:meth:`to_vega`, which all
        return one plain value, this returns ``(result, caveats)`` --
        a deliberate, documented departure from its siblings, not an
        oversight. ``result`` is ``{"grid": <spec> | None, "standalone":
        [<spec>, ...]}``: a combined spec for whatever axes compose
        cleanly into Vega-Lite's ``hconcat``/``vconcat`` grid, plus a list
        of independent specs for anything that doesn't (a single axes with
        nothing to grid against, a free-form ``add_axes()``/``inset_axes()``
        panel, a mismatched-shape multi-grid figure). ``caveats`` is a list
        of human-readable strings describing every structural compromise
        made building the result -- data for a caller deciding what to do
        with a partially-composed figure, not just console noise; every
        entry is also re-emitted as a ``UserWarning``, so a caller who
        ignores the tuple still sees the same warning.

        Vega-Lite's mark vocabulary is closed (no raw path-per-datum mark
        the way Vega has) and its composition model is grid-like, not
        arbitrary-pixel-positioned, so this is a stricter target than
        :meth:`to_vega` in both what a single axes can draw and how several
        axes can be arranged together -- see :mod:`plotpress.vega_lite`'s
        own module docstring for the full fidelity-tier breakdown (what
        maps natively, what needs a layered workaround, and what has no
        Vega-Lite mapping at all and warns instead) and the exact
        figure-composition algorithm.

        ``mesh_data=True`` opts a ``pcolormesh``/mesh-backed ``imshow``
        into real per-cell ``rect`` marks with a genuine field+scale color
        encoding, instead of the default rasterized ``image`` mark -- the
        same opt-in, same eligibility rules (a rectilinear grid, a plain
        linear color norm, a colormap with a matching named Vega scheme,
        at most ~2000 cells), and same warn-and-fall-back-to-image
        behavior otherwise, as :meth:`to_vega`'s own ``mesh_data``.
        """
        from ..backends.vega_lite import figure_to_vega_lite
        return figure_to_vega_lite(self, mesh_data=mesh_data)

    def to_template(self) -> dict:
        """A reusable, data-free snapshot of this figure's own structure
        and styling -- grid shape, :meth:`group` boxes, every axes' own
        decorations, spine colors, tick overrides, ids, twin/secondary/
        inset overlays, colorbar styling, and this figure's own
        :class:`~plotpress.style.Style` -- everything needed to rebuild an
        identically laid-out, identically styled *blank* figure via
        :func:`plotpress.figure_from_template`, with none of the data
        actually plotted into it.

        This is the exact same payload :meth:`to_html` embeds for
        :func:`plotpress.load_data` to read back under its own
        ``"template"`` key -- there is only one shape, used both when
        explicitly building a reusable template ahead of time (this
        method; :meth:`save_template` writes it as plain, human-editable
        JSON, with no plotted data anywhere in it) and when recovering a
        saved figure's structure alongside its data. See
        :func:`plotpress.svg.template_metadata` for the full field-by-field
        breakdown of what's captured and the real, still-irreducible gaps
        (a colorbar's actual color mapping, and a non-JSON-safe colorbar
        ``ticks``/``format``).
        """
        from ..backends.svg import template_metadata

        return template_metadata(self)

    def save_template(self, path) -> None:
        """Write :meth:`to_template`'s result to ``path`` as plain,
        indented JSON -- deliberately human-readable/diffable/editable,
        since a template is meant to be hand-tuned and checked into
        version control, not treated as an opaque blob. See
        :func:`plotpress.load_template`/:func:`plotpress.figure_from_template`
        to read it back.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_template(), f, indent=2)

    def print_layout_summary(self) -> None:
        """Print a plain-English orientation to this figure's layout --
        how many axes, how they're arranged (a grid, spans, twins,
        insets, colorbars, free-form panels), what's plotted on each one,
        and whether each would export cleanly to :meth:`to_vega`/
        :meth:`to_vega_lite`. Meant for a REPL/notebook, when a figure
        came from somewhere else (a saved layout, an imported HTML file,
        code you didn't write) and the fastest way to understand it is to
        just ask it -- not for programmatic use (nothing here is returned;
        see :meth:`~plotpress.axes.Axes.print_summary` for one axes at a
        time, or read ``fig.axes``/``ax.artists`` directly for that).

        Named ``print_*`` (not e.g. ``layout_summary``) so it tab-completes
        alongside every other summary method this library adds -- see
        :meth:`~plotpress.axes.Axes.print_summary` for the per-axes one.
        """
        visible = [ax for ax in self.axes if ax._visible]
        print(f"Figure: {len(self.axes)} axes ({len(visible)} visible), "
              f"figsize={self.figsize}")
        if self._groups:
            names = ", ".join(repr(g["title"]) for g in self._groups)
            print(f"  Figure.group() boxes: {names}")
        gaps = _vega_compat_report(self)
        fig_level = gaps.get(None)
        if fig_level and (fig_level["vega"] or fig_level["vega_lite"]):
            print("  figure-level export notes:")
            for msg in fig_level["vega"]:
                print(f"    - [vega] {msg}")
            for msg in fig_level["vega_lite"]:
                print(f"    - [vega-lite] {msg}")
        for i, ax in enumerate(self.axes):
            print(f"\nAxes {i}:")
            for line in _axes_summary_lines(ax, gaps.get(i, {"vega": [], "vega_lite": []})):
                print(line)

    def _repr_svg_(self) -> str:
        # Static inline SVG is the Jupyter default; use to_html for interactive.
        return figure_to_svg(self)

    def to_html(self, interactive: bool = True, wait_extract: bool = False,
                pick_precision: int = 6, pick_max_mesh_cells: int = 250000,
                pick_max_points: int = 20000, binary_pick_data: bool = True,
                standalone: bool = True, include_default_js: bool = True,
                extra_js: str = None, options=None) -> str:
        """Serialize to a self-contained HTML document.

        ``options`` adds optional toolbar menus, by name. Every page already
        has Pan/Zoom, Home, Fit Width, Axes, Point Picking, Annotate, and
        File; the rest are opt-in:

        - ``"slice"`` -- the Slice menu, scrubbing a row/column of a
          pcolormesh/imshow as a 1-D profile (shown only when the figure has
          a mesh to slice). A radio in the menu picks how the profile is
          shown: in a strip beside the heatmap (``"companion"``, the
          default), in the heatmap's place (``"replace"``), or not at all
          with just a cursor on the heatmap (``"cursor"``).

        Pass a list of names, or a dict to also set the tool's startup
        state: ``options={"slice": {"enabled": True, "view": "companion",
        "orientation": "y", "link_all": True, "range": "colorbar"}}``.
        The settings are ``enabled``, ``view``, ``orientation``
        (``"x"``/``"y"``), ``link_all``, ``snap_pins`` (mirror Point Picking
        pins onto the profile), ``grid`` (gridlines on the profile, default
        ``True``), ``range``
        (``"auto"``/``"colorbar"``/``"custom"``, the last with
        ``range_min``/``range_max``), ``index`` (the starting row/column),
        ``panel_size`` (the companion strip's fraction of the axes,
        0.1-0.6, default 0.3), and ``axes`` (``"all"``, or a list of the axes --
        or their indices -- to slice; the rest stay plain heatmaps). The embedded
        data payloads are the same either way, so :func:`load_data` reads any
        interactive HTML back regardless of which options it was saved with.

        ``standalone`` (default) centers the figure at its natural pixel size
        on a full-height page -- right for a file opened directly in its own
        tab. Set it ``False`` when this HTML is going into a container you
        don't control the size of (an ``<iframe>`` embedding it, say, as
        :class:`Report` does): the SVG instead scales to fill whatever width
        it is given, and the page no longer forces itself to at least a full
        viewport tall, which centering a shorter figure inside would
        otherwise pad with empty space above and below it.

        ``pick_precision`` sets the decimal places of the embedded point-pick
        arrays (the mesh z grids dominate the file size for mesh-heavy figures);
        lower it to shrink the HTML at the cost of readout precision.

        ``pick_max_mesh_cells``/``pick_max_points`` cap how much of each
        mesh's/series' own data is embedded for picking, per artist -- so a
        figure with *many* mesh-bearing axes (a grid of pcolormeshes, say)
        does not multiply the default cap by the axes count. A mesh over the
        cap is block-averaged down to it rather than dropped -- a click still
        answers with a real value, but it's the *mean* of every original cell
        folded into whichever coarser one the click landed in, not the exact
        value at that point, and that cell's own x/y is the wider block's
        center, not the original grid's. The rendered mesh itself is never
        downsampled (only the pick payload is), so nothing about the image
        hints this happened -- a ``UserWarning`` naming every affected axes
        does instead, whenever a mesh actually crosses the cap. Raise
        ``pick_max_mesh_cells`` for full-resolution picking on a mesh this
        large, at the cost of a bigger embedded payload. A series over the
        point cap falls back to a geometry-only x/y readout instead (dropped,
        not downsampled -- there's no missing-value problem an x/y-only click
        needs solving the way a mesh's z does).

        ``binary_pick_data`` embeds long numeric arrays (mesh z grids, animated
        line frames) as base64 float32/float16 bytes instead of JSON number
        text -- roughly half the size at effectively the same decode speed as
        JSON, benchmarked against gzip compressing the JSON instead (smaller,
        but 5-7x slower to decode: ``DecompressionStream`` overhead dominates
        at these payload sizes). It also restructures the per-axes metadata
        payload column-wise (one array per field instead of one object per
        axes), which matters once a figure has hundreds of axes: that
        payload has no long arrays of its own, so its cost is JSON key names
        repeated once per axes rather than a big number array -- columnar
        layout states each key once, and the numeric columns that leaves
        then get the same binary encoding. Set ``False`` for the exact
        plain-JSON payload, e.g. to inspect it by hand or diff it against an
        older plotpress version.

        ``include_default_js`` (default ``True``) controls whether
        plotpress's own toolbar/pan/zoom/pick JS (:data:`plotpress._interactive.INTERACTIVE_JS`)
        is included at all. Set it ``False`` to get the ``#plotpress-meta``/
        ``#plotpress-pick``/``#plotpress-style`` JSON payloads (assuming
        ``interactive=True``) with none of plotpress's own JS behavior
        layered on top -- for building interactivity entirely from scratch
        against that data and ``extra_js``, rather than extending what's
        already there. ``binary_pick_data=False`` is worth pairing with
        this: the default binary encoding needs plotpress's own decoder,
        which is exactly what this is turning off.

        ``extra_js`` is a raw JS string inlined as its own ``<script>``
        block, after plotpress's own (when ``include_default_js`` is
        ``True``) so ``window.plotpressAddTool``/``plotpressGetMarkers``
        already exist by the time it runs. With ``include_default_js=True``
        (the default), use it to *add* to the existing toolbar --
        ``window.plotpressAddTool({label, onClick})`` for an always-on
        action button, or ``{label, mode, onClick, onEnter, onExit,
        cursor}`` for one that joins the same single-selection group as
        Axis Span/Axis Zoom/Point Picking, called back with ``(event, userSpacePoint)``
        on a click the built-in modes don't already claim. With
        ``include_default_js=False``, it's the *only* JS this page gets --
        write your own toolbar/interactivity entirely, working from
        ``#plotpress-svg`` and the JSON payloads directly. Nothing about
        supplying this fetches anything external on its own -- it is
        inlined the same as plotpress's own JS, keeping the "no external
        requests" guarantee intact regardless of what it contains.
        """
        opts, opt_config = _resolve_options(options)
        listed = opt_config.get("slice", {}).get("axes")
        if isinstance(listed, (list, tuple)):
            resolved = []
            for a in listed:
                if isinstance(a, Axes):
                    if a not in self.axes:
                        raise ValueError(
                            "options['slice']['axes'] names an axes that isn't part of this figure")
                    a = self.axes.index(a)
                elif int(a) >= len(self.axes):
                    raise ValueError(
                        f"options['slice']['axes'] has index {a}, but this figure has "
                        f"{len(self.axes)} axes")
                resolved.append(int(a))
            opt_config["slice"]["axes"] = resolved
        elif listed == "all":
            del opt_config["slice"]["axes"]
        svg = figure_to_svg(self)
        # Tag the root <svg> so the JS can grab it.
        svg = svg.replace("<svg ", '<svg id="plotpress-svg" ', 1)
        script = ""
        if interactive:
            from ..backends.svg import (
                axes_metadata, frame_data, pick_data, style_payload, template_metadata,
            )

            pick_dict = pick_data(self, max_points=pick_max_points,
                                  max_mesh_cells=pick_max_mesh_cells,
                                  precision=pick_precision)
            idx_of = {id(a): i for i, a in enumerate(self.axes)}
            meta_dict = axes_metadata(self, idx_of=idx_of)
            if binary_pick_data:
                pick_dict = _encode_binary_arrays(pick_dict, precision=pick_precision)
                # meta has no long arrays of its own to swap for bytes -- its
                # cost on a many-axes figure is ~25 JSON key names repeated
                # once per axes instead of once total. Columnarizing states
                # each key once; the numeric columns that leaves (x/y/w/h/
                # xmin/xmax/ymin/ymax) then qualify for the same binary
                # encoding pick data just got. Only "cols" goes through the
                # encoder -- "index" is a short run of small sequential axes
                # indices, cheaper as plain JSON text than as a base64-wrapped
                # buffer, and the client indexes it directly as object keys.
                meta_dict = _columnarize_meta(meta_dict)
                meta_dict["cols"] = _encode_binary_arrays(meta_dict["cols"],
                                                          precision=pick_precision)
            meta = _json_payload(meta_dict)
            pick = _json_payload(pick_dict)
            styl = _json_payload(style_payload(self))
            # The embedded tag keeps its "plotpress-layout" id regardless of
            # this rename -- _load_template()'s _extract_json_block() call
            # looks for that exact id, and every already-saved HTML file on
            # disk has it under that name; changing it here would make
            # load_data() unable to find real, existing data in those files.
            template = _json_payload(template_metadata(self, idx_of=idx_of))
            payloads = (
                f'<script type="application/json" id="plotpress-meta">{meta}</script>'
                f'<script type="application/json" id="plotpress-pick">{pick}</script>'
                f'<script type="application/json" id="plotpress-style">{styl}</script>'
                f'<script type="application/json" id="plotpress-layout">{template}</script>'
            )
            if self._sliders:
                frames_dict = frame_data(self, max_mesh_cells=pick_max_mesh_cells)
                if binary_pick_data:
                    # frame_data() always rounds to 6 decimals (svg._round_list,
                    # module-level -- unlike pick_data() it takes no precision
                    # argument), so the float16 safety check has to match that,
                    # not whatever pick_precision the caller passed.
                    frames_dict = _encode_binary_arrays(frames_dict, precision=6)
                frames = _json_payload(frames_dict)
                sliders = _json_payload(self._sliders)
                payloads += (
                    f'<script type="application/json" id="plotpress-frames">{frames}</script>'
                    f'<script type="application/json" id="plotpress-sliders">{sliders}</script>'
                )
            config = ("<script>window.PLOTPRESS_WAIT_EXTRACT=true;</script>"
                      if wait_extract else "")
            config += ("<script>window.PLOTPRESS_OPTIONS="
                       f"{json.dumps(opts)};window.PLOTPRESS_OPTION_CONFIG="
                       f"{json.dumps(opt_config)};</script>")
            script = config + payloads
            if include_default_js:
                from ..backends._interactive import INTERACTIVE_JS
                script += f"<script>{INTERACTIVE_JS}</script>"
        if extra_js:
            script += f"<script>{extra_js}</script>"
        # The toolbar and a docked slider strip are both position:fixed --
        # see _interactive.py's .plotpress-menubar/.plotpress-sliders -- so
        # nothing stops either from drawing over the SVG unless something
        # else reserves the room for them. A full viewport tall of
        # flex-centering slack was assumed to make that a non-issue for a
        # standalone page (the toolbar just floats over its own top-left
        # corner, above wherever the centered figure starts) -- true only
        # while the figure fits inside the viewport. A sufficiently tall
        # figsize (or, same thing, a group's own title reserving margin
        # above the outermost row -- see Figure.group) leaves zero slack for
        # `margin: auto` to spend, so the SVG starts flush at the very top
        # of the page, right where the fixed toolbar already sits -- the
        # figure's own topmost content silently renders *underneath* it.
        # Reserving the same real top/bottom padding standalone=False
        # already uses removes the assumption entirely: a short figure
        # still centers, just within the viewport slice actually left below
        # the toolbar, and a too-tall one now always starts clear of it
        # regardless of how much (or how little) slack remains.
        top_pad, bottom_pad = _toolbar_clearance(
            interactive and include_default_js, len(self._sliders or {}))
        if standalone:
            # No justify-content/align-items:center here -- centering an
            # overflowing flex item that way is a well-known browser trap:
            # the browser clips the *start*-side overflow from the
            # scrollable area instead of just centering it, so a figure
            # wider or taller than the viewport (several hundred axes, a
            # large figsize/group_spacing) got its left/top portion pushed
            # off-screen with no way to scroll back to it -- scrolling only
            # ever reached further into the *end*-side overflow. `margin:
            # auto` on the flex item itself (below) is the standard escape:
            # it centers identically whenever there's free space to split
            # between the two auto margins, but degrades to a plain 0 margin
            # -- ordinary in-flow overflow, fully reachable by scrolling in
            # either direction -- the moment the item is larger than body.
            body_style = (f"body{{margin:0;background:#f5f5f5;display:flex;"
                          f"min-height:100vh;padding:{top_pad}px 0 {bottom_pad}px;"
                          f"box-sizing:border-box}}")
            wrap_display = "inline-block"   # shrink-wrapped to the SVG's own
                                             # size, so centering centers the
                                             # figure, not an oversized box
        else:
            body_style = f"body{{margin:0;padding:{top_pad}px 0 {bottom_pad}px}}"
            wrap_display = "block"   # stretches to the container's full width
                                     # -- #plotpress-svg's own width:100% (below)
                                     # needs a definite (non-auto) containing
                                     # block to resolve against, or the browser
                                     # falls back to its fixed width/height
                                     # attributes instead, undoing the scaling
        svg_style = (
            # flex-shrink:0 -- the SVG is a direct flex child of body (below)
            # with no wrapper div (that only exists for a plot_frames()/
            # pcolormesh_frames() figure's docked sliders, see above). Without
            # it, a figure wider than the viewport -- unremarkable at ordinary
            # sizes, real once the figure is genuinely large (hundreds of
            # axes) -- got shrunk by the flex container's default
            # flex-shrink:1 to fit the viewport's *width* only, since a
            # replaced element's flex-basis shrinks independently per axis
            # with no aspect-ratio preservation: the SVG's height stayed at
            # its full, unscaled attribute value while its width compressed,
            # rendering every element non-uniformly squashed rather than
            # simply centered with the page free to scroll to see the rest,
            # which is what happens with this set. margin:auto centers it
            # (see body_style above) without body's own justify-content/
            # align-items.
            "#plotpress-svg{cursor:default;box-shadow:0 1px 6px rgba(0,0,0,.2);"
            "flex-shrink:0;margin:auto}" if standalone
            else "#plotpress-svg{cursor:default;display:block;width:100%;height:auto}"
        )
        # A plot_frames()/pcolormesh_frames() figure wraps the SVG in a div
        # (for positioning docked sliders over it) -- position:relative in
        # both modes so a docked slider box (position:absolute inside it)
        # anchors correctly; only whether it shrink-wraps or stretches
        # differs. That wrap div, not the SVG, becomes body's direct flex
        # child once it exists, so it needs the same margin:auto -- the
        # SVG's own (above) no longer has an overflowing flex container to
        # center within at that point.
        wrap_style = (
            f".plotpress-svg-wrap{{position:relative;line-height:0;"
            f"display:{wrap_display};margin:auto}}" if standalone else
            f".plotpress-svg-wrap{{position:relative;line-height:0;display:{wrap_display}}}"
        )
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{body_style}{svg_style}{wrap_style}</style></head><body>"
            f"{svg}{script}</body></html>"
        )

    # NB: intentionally *no* _repr_html_. Jupyter prefers text/html over
    # image/svg+xml, and returning a full interactive HTML document renders
    # messily in an output cell (and its scripts don't run there). Notebooks
    # therefore fall back to the clean static SVG above; for an interactive
    # figure in a notebook, embed to_html() in an <iframe> (see the docs).

    def save(self, path, interactive: bool = False, scale: int = 2,
             pick_precision: int = 6, pick_max_mesh_cells: int = 250000,
             pick_max_points: int = 20000, binary_pick_data: bool = True,
             fps: int = 10, slider_unit: str = "main", label_frames: bool = True,
             include_default_js: bool = True, extra_js: str = None,
             dpi: float = None, transparent: bool = False, format: str = None,
             options=None):
        """Save by extension: ``.svg``, ``.html``, ``.png``, ``.pdf``,
        ``.gif``, ``.eps``, ``.jpg``/``.jpeg``, or ``.webp``.

        ``path`` may also be a file-like object (a ``BytesIO``, an open
        file) instead of a filename -- the standard ``fig.savefig(buf,
        format="png")`` idiom for serving a figure without touching disk.
        ``format`` names the format explicitly (a bare extension, with or
        without the leading dot); it is **required** when ``path`` is a
        file-like object, since there is no filename to read an extension
        from, and optional otherwise, where it overrides whatever the
        path's own extension would have picked.

        All formats work with the standard install (PNG/JPEG/WebP are a
        supersampled raster; PDF/EPS are vector). ``pick_precision``/
        ``pick_max_mesh_cells``/``pick_max_points``/``binary_pick_data``/
        ``include_default_js``/``extra_js`` apply only to interactive HTML
        (see :meth:`to_html`). ``.gif`` needs at least one
        :meth:`Axes.plot_frames` or :meth:`Axes.pcolormesh_frames` series --
        it animates through that series' frames at ``fps``, the same data an
        interactive HTML slider scrubs through, as a self-contained looping
        file; ``slider_unit`` picks which slider drives the animation for
        figures with more than one, and ``label_frames`` stamps each frame
        with its slider value since a GIF has no slider to show it on (see
        :func:`plotpress.raster.save_gif`).

        ``.jpg``/``.jpeg``/``.webp`` are raster, like ``.png`` (and share its
        ``scale``), but lossy -- JPEG and WebP compress dense mesh/image
        content smaller than PNG at some cost to sharp text/line edges; PNG
        stays the better default unless a downstream consumer specifically
        needs one of these. ``.eps`` is vector, like ``.pdf`` -- for
        submission pipelines that still require EPS specifically.

        ``dpi`` (PNG/JPEG only) overrides ``Style.dpi`` for this save alone,
        without mutating the figure -- a physically larger/smaller image at
        the same layout proportions (fonts, markers and margins all scale
        with it, exactly as they would if ``Style.dpi`` itself had been set
        that way), and the dpi value the saved file's own metadata reports.
        ``transparent`` (PNG only -- JPEG has no alpha channel) drops the
        figure's own background fill, leaving the outer canvas transparent
        instead of painted with ``Style.facecolor``; each axes' own
        ``facecolor`` is unaffected.
        """
        is_buffer = hasattr(path, "write")
        if format is not None:
            ext = format.lower().lstrip(".")
        elif is_buffer:
            raise ValueError(
                "save(): format= is required when path is a file-like "
                "object -- there is no filename to read an extension from"
            )
        else:
            ext = os.path.splitext(os.fspath(path))[1].lower().lstrip(".")

        if ext in ("html", "htm"):
            content = self.to_html(interactive=interactive,
                                   pick_precision=pick_precision,
                                   pick_max_mesh_cells=pick_max_mesh_cells,
                                   pick_max_points=pick_max_points,
                                   binary_pick_data=binary_pick_data,
                                   include_default_js=include_default_js,
                                   extra_js=extra_js, options=options)
        elif ext == "svg":
            content = self.to_svg()
        elif ext == "png":
            from ..backends.raster import save_png
            return save_png(self, path, scale=scale, dpi=dpi, transparent=transparent)
        elif ext in ("jpg", "jpeg"):
            from ..backends.raster import save_jpeg
            return save_jpeg(self, path, scale=scale, dpi=dpi)
        elif ext == "webp":
            from ..backends.raster import save_webp
            return save_webp(self, path, scale=scale)
        elif ext == "pdf":
            from ..backends.raster import save_pdf
            return save_pdf(self, path)
        elif ext == "eps":
            from ..backends.raster import save_eps
            return save_eps(self, path)
        elif ext == "gif":
            from ..backends.raster import save_gif
            return save_gif(self, path, fps=fps, scale=scale,
                           slider_unit=slider_unit, label_frames=label_frames)
        else:
            raise ValueError(
                "save() supports svg/html/png/jpg/jpeg/webp/pdf/eps/gif "
                f"(got path={path!r}, format={format!r})"
            )
        if is_buffer:
            # A binary buffer (BytesIO, a file opened "wb") is exactly as
            # valid a target as a text one here -- matplotlib's own
            # savefig(buf, format=...) doesn't distinguish, so this
            # shouldn't either. Try text first (the common StringIO/text-
            # mode-file case) and fall back to UTF-8 bytes on the
            # TypeError a binary buffer's write() raises for a str.
            try:
                path.write(content)
            except TypeError:
                path.write(content.encode("utf-8"))
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        return path

    def savefig(self, path, **kwargs):
        """Alias for :meth:`save` (matplotlib-compatible name)."""
        return self.save(path, **kwargs)

    # -- display ------------------------------------------------------------
    def show(self, interactive: bool = True, wait_for_extract: bool = False,
             options=None):
        """Display in a native pop-up window (via pywebview if installed).

        Returns the list of markers the user extracted in the window (each a
        dict of values: ``x``, ``y``, any extra dims, ``axes`` (index),
        ``axes_title`` (if that axes has one), ``kind``), or an empty list if
        none were extracted. Point Picking markers only -- Extract lives
        under the Point Picking menu and no longer includes annotation
        notes (dropped via any of the three Annotate tools), which have no
        export of their own.

        With ``wait_for_extract=True`` the call becomes an interactive point-
        picking session: the kernel blocks, the user drops markers and clicks
        **Extract**, and *that* returns the markers to the kernel and closes the
        window (no manual close needed).

        The native window needs the ``[gui]`` extra
        (``pip install plotpress[gui]``). Without it, this falls back to opening
        the figure in the default browser and returns ``None`` (use the in-page
        Extract panel to copy/download).
        """
        html = self.to_html(interactive=interactive, wait_extract=wait_for_extract,
                            options=options)
        w = int(self.figsize[0] * self.style.dpi) + 40
        h = int(self.figsize[1] * self.style.dpi) + 60
        try:
            import webview  # provided by the [gui] extra (pywebview)
        except ImportError:
            if wait_for_extract:
                raise RuntimeError(
                    "wait_for_extract=True needs the native window; install it "
                    "with: pip install plotpress[gui]"
                )
            import tempfile
            import webbrowser

            tmpdir = tempfile.gettempdir()
            _sweep_stale_tempfiles(tmpdir)
            if self._show_path is None:
                # One file per figure: re-showing overwrites it rather than
                # dropping another copy in the temp directory.
                fd, self._show_path = tempfile.mkstemp(
                    suffix=".html", prefix=_TEMP_PREFIX, dir=tmpdir)
                os.close(fd)
            with open(self._show_path, "w", encoding="utf-8") as f:
                f.write(html)
            webbrowser.open("file://" + os.path.abspath(self._show_path))
            return None

        api = _MarkerApi()
        window = webview.create_window("plotpress", html=html, js_api=api,
                                       width=w, height=h)
        if wait_for_extract:
            api._window = window   # Extract closes the window -> unblocks below
        webview.start()
        return api.markers

    def show_qt(self, title="plotpress", block=True, interactive=True,
                pick_precision=6):
        """Display in a native Qt window (PyQt/PySide), for Qt-based apps.

        Thin wrapper around ``plotpress.qt.view``. Needs a Qt binding with
        WebEngine (``pip install plotpress[qt]``). To embed the figure inside
        your own Qt layout instead of a standalone window, use
        ``plotpress.qt.PlotPressWidget`` directly.
        """
        from ..gui.qt import view
        return view(self, title=title, block=block, interactive=interactive,
                    pick_precision=pick_precision)

    def show_in_jupyter(self, width=None, height=None, interactive: bool = True,
                        pick_precision: int = 6, pick_max_mesh_cells: int = 250000,
                        pick_max_points: int = 20000, binary_pick_data: bool = True,
                        include_default_js: bool = True, extra_js: str = None,
                        options=None):
        """Display inline in a notebook cell with the full interactive toolbar.

        Evaluating a figure directly (``fig`` as a cell's last expression)
        renders it inline as static SVG via ``Figure._repr_svg_`` -- there is
        deliberately no ``_repr_html_``, since Jupyter prefers ``text/html``
        over ``image/svg+xml`` when a MIME bundle offers both, and a full
        interactive HTML document dropped into an output cell that way renders
        messily and its ``<script>`` doesn't run there regardless.

        This instead wraps the same self-contained HTML ``to_html()``
        produces in an ``<iframe>``, which does isolate and run the inlined
        JS -- so the toolbar, pan/zoom, and point-picking all work exactly as
        they do in a saved ``.html`` file opened in a browser.

        ``width``/``height`` default to the figure's own pixel size
        (``figsize`` x ``style.dpi``); pass either to override. The rest of
        the keyword arguments are forwarded to ``to_html()`` (see there for
        what each controls).

        Returns an ``IPython.display.HTML`` object -- return it as a cell's
        last expression, or pass it to ``IPython.display.display()``. Needs
        IPython (``pip install plotpress[jupyter]``), which any real Jupyter
        environment already has.
        """
        try:
            from IPython.display import HTML
        except ImportError as e:
            raise ImportError(
                "show_in_jupyter() needs IPython -- install it with: pip "
                "install plotpress[jupyter] (any Jupyter environment "
                "already has it)"
            ) from e
        if width is None:
            width = int(self.figsize[0] * self.style.dpi)
        if height is None:
            height = int(self.figsize[1] * self.style.dpi)
        # standalone=False: meant exactly for embedding in a container this
        # call doesn't control the size of, so the figure scales to fill the
        # iframe instead of sitting at a fixed pixel size with empty space
        # centered around it.
        html = self.to_html(
            interactive=interactive, standalone=False,
            pick_precision=pick_precision, pick_max_mesh_cells=pick_max_mesh_cells,
            pick_max_points=pick_max_points, binary_pick_data=binary_pick_data,
            include_default_js=include_default_js, extra_js=extra_js,
            options=options,
        ).replace('"', "&quot;")
        return HTML(
            f'<iframe srcdoc="{html}" width="{width}" height="{height}" '
            f'style="border:0"></iframe>'
        )


class _MarkerApi:
    """pywebview bridge: the in-window Extract button pushes markers to Python."""

    def __init__(self):
        self.markers = []
        self._window = None   # set when Extract should also close the window

    def extract(self, records):
        # Called from JS as window.pywebview.api.extract(records).
        self.markers = list(records) if records else []
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
        return True


_TEMP_PREFIX = "plotpress-"


_TEMP_MAX_AGE = 24 * 3600     # seconds


def _sweep_stale_tempfiles(directory, max_age=_TEMP_MAX_AGE):
    """Delete figures the browser fallback left behind in earlier sessions.

    That fallback cannot clean up after itself on the way out: ``webbrowser``
    hands the file to another process and returns immediately, so unlinking it
    -- at exit or otherwise -- races a script that exits right after calling
    ``show()``. Reaping by age sidesteps the race entirely, since a file this
    old belongs to a process that is long gone.
    """
    cutoff = time.time() - max_age
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if not (name.startswith(_TEMP_PREFIX) and name.endswith(".html")):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
        except OSError:
            pass          # vanished, or belongs to another user -- not ours to fix


def _group_by(items, key):
    """Partition ``items`` into groups sharing the same ``key(item)``, in
    first-seen order (plain equality grouping, not requiring sorted input).
    """
    groups = {}
    order = []
    for item in items:
        k = key(item)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(item)
    return [groups[k] for k in order]


def _flatten_axes(ax):
    """Normalize a single Axes / list / ndarray of axes to a flat list."""
    if isinstance(ax, Axes):
        return [ax]
    return [a for a in np.asarray(ax, dtype=object).ravel()]


def subplots(nrows=1, ncols=1, figsize=(6.4, 4.8), style: Style = None,
             facecolor=None, squeeze=True, sharex=False, sharey=False,
             projection=None):
    """Convenience constructor mirroring ``matplotlib.pyplot.subplots``.

    Unlike matplotlib, this creates and returns a fresh, fully independent
    figure -- there is no global state touched. ``sharex``/``sharey`` link the
    grid's limits and hide inner tick labels. ``projection='polar'`` makes the
    axes polar.
    """
    fig = Figure(figsize=figsize, style=style, facecolor=facecolor)
    axes = fig.subplots(nrows, ncols, squeeze=squeeze, sharex=sharex,
                        sharey=sharey, projection=projection)
    return fig, axes


def _apply_axes_decorations(ax, spec):
    """Re-apply everything ``template_metadata()``/``Figure.to_template()``
    captured about one axes' own decorations, so
    :func:`figure_from_template`'s caller never has to re-set a title/
    label/limit/scale/spine/tick override/id by hand. ``.get(...)``
    throughout, not direct indexing: a saved dict from before a given
    field existed simply has none of them, and every one is meant to
    no-op rather than raise then.

    Routed through :meth:`Axes.set` where possible (the single-value
    setters it already validates and dispatches) rather than one direct
    call per property -- keeps this in sync with ``Axes.set()``'s own
    growing coverage instead of hand-duplicating its dispatch table one
    property at a time.
    """
    bulk = {}
    for key in ("xscale", "yscale", "aspect", "box_aspect", "facecolor"):
        if spec.get(key) is not None:
            bulk[key] = spec[key]
    if spec.get("xlim") is not None:
        bulk["xlim"] = tuple(spec["xlim"])
    if spec.get("ylim") is not None:
        bulk["ylim"] = tuple(spec["ylim"])
    if bulk:
        ax.set(**bulk)
    # xlabel/ylabel/title carry a per-instance size (and, for the labels,
    # a visibility flag -- template_metadata() only records that key when
    # actually hidden) alongside their text, so each needs its own direct
    # call rather than .set()'s single-value-per-key dispatch.
    if spec.get("xlabel") is not None:
        ax.set_xlabel(spec["xlabel"], visible=spec.get("xlabel_visible", True),
                      size=spec.get("xlabel_size"))
    if spec.get("ylabel") is not None:
        ax.set_ylabel(spec["ylabel"], visible=spec.get("ylabel_visible", True),
                      size=spec.get("ylabel_size"))
    if spec.get("title") is not None:
        ax.set_title(spec["title"], size=spec.get("title_size"))
    if spec.get("axis_off"):
        ax.set_axis_off()
    if spec.get("xinverted"):
        ax.invert_xaxis()
    if spec.get("yinverted"):
        ax.invert_yaxis()
    if spec.get("grid"):
        ax.grid(True, axis=spec.get("grid_axis", "both"),
               which=spec.get("grid_which", "major"), alpha=spec.get("grid_alpha"))
    # Template-only fields (see plotpress.svg._template_axes_extra) -- never
    # present on a plain data-roundtrip layout, so every one of these is a
    # no-op there.
    if spec.get("id") is not None:
        ax.set_id(spec["id"])
    spines = spec.get("spines")
    if spines:
        for side, sv in spines.items():
            spine = ax.spines[side]
            spine.set_color(sv.get("color"))
            spine.set_linewidth(sv.get("linewidth"))
            spine.set_visible(sv.get("visible", True))
            spine.set_alpha(sv.get("alpha"))
    if spec.get("tick_overrides"):
        ax._tick_overrides = {"x": dict(spec["tick_overrides"].get("x") or {}),
                              "y": dict(spec["tick_overrides"].get("y") or {})}
    if spec.get("minor_tick_overrides"):
        ax._minor_tick_overrides = {
            "x": dict(spec["minor_tick_overrides"].get("x") or {}),
            "y": dict(spec["minor_tick_overrides"].get("y") or {})}
    if spec.get("xtick_side") is not None:
        (ax.tick_top if spec["xtick_side"] == "top" else ax.tick_bottom)()
    if spec.get("ytick_side") is not None:
        (ax.tick_right if spec["ytick_side"] == "right" else ax.tick_left)()
    if spec.get("minor_ticks_on"):
        ax.minorticks_on()


def _fit_cells(avail, n, base_gaps, protected_gaps=None, floor=0.02):
    """Cell size and per-boundary gaps that fit ``n`` cells into ``avail``.

    ``base_gaps`` is a list of ``n - 1`` inter-cell gaps -- not necessarily
    uniform, since a twin/title's own decorations only widen the boundaries
    that actually need them. The gap is what the decorations need; the
    cell is what is left over. When a dense grid cannot afford both, the
    *gap* gives way first -- panels squeezed together are still readable,
    and the alternative was worse than ugly: the cell size alone was clamped
    to a floor while the gap kept its full width, so the rows ran past the
    top of the canvas and the first nine rows of a 30x30 grid were simply
    not on the figure.

    ``protected_gaps`` (default: all zero) is added to each boundary's gap
    the same way, but is exempt from this rescue's shrinking -- reserved
    for :meth:`Figure.group_spacing`'s own explicit pixel request, which
    the figure has *already grown* (``Wpx``/``Hpx`` above) specifically to
    hold. A very wide/tall grid (a :class:`GroupLayout` supergrid's LCM
    dimension routinely dwarfs the handful of groups a caller actually
    asked for) can still push ``base_gaps`` below the floor on its own --
    without this split, the rescue used to shrink group_spacing()'s own
    pixels right along with the ordinary ones, so a figure that grew by
    exactly the requested ``wspace`` could still end up with barely half of
    it as real, visible gap. Only ``base_gaps`` ever shrinks; a caller who
    explicitly asked for room keeps getting it as long as ``avail`` can
    hold it at all.

    If even the floor does not fit, the cells shrink below it rather than
    overflow. Tiny but present beats absent. A non-uniform ``base_gaps``
    shrinks proportionally, keeping the ratio between one squeezable gap
    and another rather than collapsing both to the same value.
    """
    if protected_gaps is None:
        protected_gaps = [0.0] * len(base_gaps)
    if n <= 1:
        return max(avail, 1e-4), [b + p for b, p in zip(base_gaps, protected_gaps)]
    total_protected = sum(protected_gaps)
    total_base = sum(base_gaps)
    cell = (avail - total_base - total_protected) / n
    if cell >= floor:
        return cell, [b + p for b, p in zip(base_gaps, protected_gaps)]
    # Squeeze only the base gaps; protected ones stay exactly as requested
    # as long as there's room for them at all once every cell has its floor
    # and every base gap has shrunk to nothing.
    max_total_base = max(0.0, avail - n * floor - total_protected)
    scale = (max_total_base / total_base) if total_base > 0 else 0.0
    new_gaps = [b * scale + p for b, p in zip(base_gaps, protected_gaps)]
    new_cell = max((avail - max_total_base - total_protected) / n, 1e-4)
    return new_cell, new_gaps


def _subplot_rect(nrows, ncols, index, sp=None):
    """Compute an axes rect for a 1-based subplot ``index`` in an NxM grid.

    ``sp`` is a ``{left, right, top, bottom, wspace, hspace}`` dict (matching
    :attr:`Figure._subplot_params`); defaults to matplotlib's own margins when
    omitted.
    """
    if sp is None:
        sp = {"left": 0.125, "right": 0.9, "top": 0.88, "bottom": 0.11,
              "wspace": 0.2, "hspace": 0.2}
    left, right, bottom, top = sp["left"], sp["right"], sp["bottom"], sp["top"]
    wspace, hspace = sp["wspace"], sp["hspace"]
    avail_w = right - left
    avail_h = top - bottom
    axw = avail_w / (ncols + wspace * (ncols - 1))
    axh = avail_h / (nrows + hspace * (nrows - 1))

    idx = index - 1
    row = idx // ncols
    col = idx % ncols
    ax_left = left + col * axw * (1 + wspace)
    ax_bottom = bottom + (nrows - 1 - row) * axh * (1 + hspace)
    return (ax_left, ax_bottom, axw, axh)
