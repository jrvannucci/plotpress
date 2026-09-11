"""The Figure: the root object that owns everything needed to render itself.

There is no global "current figure" or "current axes". A figure holds its own
axes, its own :class:`~plotpress.style.Style`, and knows how to serialize itself to
SVG/HTML or show itself in a native pop-up window. Two figures never share
mutable state.
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

import numpy as np

from .artists import normalize_bbox, normalize_linestyle
from .axes import Axes
from .polar import PolarAxes
from .style import Style
from .svg import figure_to_svg

# Distinguishes "align_xlabels/ylabels never called" from "called with the
# default axes=None" (meaning "all axes, re-resolved each time") -- both would
# otherwise collapse to the same falsy None and the re-apply on relayout
# below would never fire for the (most common) no-argument call.
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
    :func:`subplots_from_layout` recovers every axes and group correctly,
    but -- since a group's own cells are spans on the shared grid, not
    single non-spanning ones -- ``axes`` on the way back is
    :func:`subplots_from_layout`'s own flat-list fallback, not reconstructed
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
            # Set by Axes.remove() the moment this group's last axes leaves
            # it -- see _group_bbox's own docstring for why: with no member
            # left to measure a box from, this frozen (figure-fraction)
            # rect stands in instead of dropping the group outright.
            "frozen_rect": None,
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
        leaves a gap rather than reflowing the rest of the grid to fill it.
        See :doc:`/auto_figure_layout/grouping/plot_15_dashboard_mixed_shapes_and_masks`
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

    def tight_layout(self, pad=0.02):
        """Auto-fit subplot margins so ticks/labels/titles never overflow.

        Measures each axes' decorations with the bundled font metrics and
        re-lays-out the subplot grid. Safe to call before or after
        :meth:`colorbar`; any colorbar over this grid is re-fitted afterwards.
        Also safe to call *before* the titles and axis labels exist: the fit is
        re-applied at render time if any of them change (see
        :meth:`_settle_layout`).
        """
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
            right_px = max(right_px, xst.tick_label_size * 0.6)  # last x label overhang

            # A twin draws its axis on the side *opposite* its parent, so its
            # decorations belong to the other margin. Measuring them into the
            # left/bottom bands padded the wrong side and left the twin's own
            # tick labels and axis label to overflow -- off the canvas for a
            # single axes, and into the next panel for a grid.
            if ax._twin_of is not None:
                if ax._twin_shared == "x":                   # twinx: y on the right
                    rdec = yst.tick_size + ytw + 4
                    if ax._shown_ylabel():
                        rdec += st.label_size + 6
                    right_px = max(right_px, rdec)
                else:                                        # twiny: x on the top
                    tdec = xst.tick_size + xst.tick_label_size + 4
                    if ax._shown_xlabel():
                        tdec += st.label_size + 6
                    twin_top_px = max(twin_top_px, tdec)
                continue

            # tick_top()/tick_right() move an axes' own ticks off the default
            # bottom/left edge, so their decoration band moves with them --
            # into the same top/right bands a twin's opposite-side ticks use,
            # rather than the bottom/left band the default side would need.
            ldec = yst.tick_size + ytw + 4
            if ax._shown_ylabel():
                ldec += st.label_size + 6
            if ax._ytick_side == "right":
                right_px = max(right_px, ldec)
            else:
                left_px = max(left_px, ldec)
            bdec = xst.tick_size + xst.tick_label_size + 4
            if ax._shown_xlabel():
                bdec += st.label_size + 6
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
            if not g_specs:
                continue
            size = g["fontsize"] or st.title_size
            pos = g["title_position"]
            # pad is (left, right, top, bottom) -- the margin this title's
            # own side needs to reserve is that side's own clearance, not
            # some other edge's (an asymmetric pad -- tight on the side
            # butting a neighboring group, loose on the title side -- would
            # otherwise reserve the wrong amount here).
            pad_l, pad_r, pad_t, pad_b = g["pad"]
            # Four independent per-edge extents, not one tied to
            # title_position -- a supxlabel/supylabel (below) always sits at
            # the bottom/left edge regardless of where the *title* sits, so
            # a group with title_position="bottom" *and* a supxlabel needs
            # both reserved on that same edge, stacked (the title outside
            # the box, the supxlabel inside it growing the box into the
            # title's own margin) -- additive, not a single value picked by
            # title_position alone.
            top_extent = bottom_extent = left_extent = right_extent = 0.0
            if pos in ("top", "bottom"):
                # 1.3x size -- not 1x -- for the same reason title_px above
                # adds a flat +8 rather than measuring real glyph ascent:
                # bundled font metrics only cover advance widths (see
                # fonts/), not vertical extents, so this errs generous
                # rather than risk the title's own glyphs clipping the
                # canvas edge.
                side_pad = pad_t if pos == "top" else pad_b
                title_extent = side_pad + size * 1.3 + 10
                if pos == "top":
                    top_extent += title_extent
                else:
                    bottom_extent += title_extent
            else:
                # A left/right title runs horizontally alongside the box, not
                # centered over it -- its own rendered *width* is what has to
                # fit in the reserved margin here, not a height allowance.
                side_pad = pad_l if pos == "left" else pad_r
                title_extent = side_pad + st.text_width(g["title"], size, bold=True) + 12
                if pos == "left":
                    left_extent += title_extent
                else:
                    right_extent += title_extent
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
                bottom_extent += sx_size * 1.2 + 10
            if g.get("supylabel"):
                sy_size = g.get("supylabel_size") or st.label_size * 1.2
                left_extent += sy_size + 10
            r0 = min(ax._subplotspec.row0 for ax in g_specs)
            r1 = max(ax._subplotspec.row1 for ax in g_specs)
            c0 = min(ax._subplotspec.col0 for ax in g_specs)
            c1 = max(ax._subplotspec.col1 for ax in g_specs)
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
            if top_extent:
                if r0 == 0:
                    group_top_px = max(group_top_px, top_extent)
                else:
                    row_below_px[r0 - 1] = max(row_below_px[r0 - 1], top_extent)
            if bottom_extent:
                if r1 == nrows - 1:
                    group_bottom_px = max(group_bottom_px, bottom_extent)
                else:
                    row_above_px[r1] = max(row_above_px[r1], bottom_extent)
            if left_extent:
                if c0 == 0:
                    group_left_px = max(group_left_px, left_extent)
                else:
                    col_right_px[c0 - 1] = max(col_right_px[c0 - 1], left_extent)
            if right_extent:
                if c1 == ncols - 1:
                    group_right_px = max(group_right_px, right_extent)
                else:
                    col_left_px[c1] = max(col_left_px[c1], right_extent)
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
        gap_w_list = [base_gap_w + px / Wpx for px in col_boundary_px]
        gap_h_list = [base_gap_h + px / Hpx for px in row_boundary_px]
        axw, gap_w_list = _fit_cells(right - left, ncols, gap_w_list)
        axh, gap_h_list = _fit_cells(top - bottom, nrows, gap_h_list)

        _place_spec_rects(specs, nrows, ncols, left, bottom, axw, axh, gap_w_list, gap_h_list)
        self._finish_grid_relayout(specs)
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
        nrows, ncols = specs[0]._subplotspec.nrows, specs[0]._subplotspec.ncols

        avail_w = sp["right"] - sp["left"]
        avail_h = sp["top"] - sp["bottom"]
        axw = avail_w / (ncols + sp["wspace"] * (ncols - 1))
        axh = avail_h / (nrows + sp["hspace"] * (nrows - 1))
        gap_w, gap_h = axw * sp["wspace"], axh * sp["hspace"]

        _place_spec_rects(specs, nrows, ncols, sp["left"], sp["bottom"], axw, axh,
                          [gap_w] * (ncols - 1), [gap_h] * (nrows - 1))
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
        from .svg import _effective_rect, _pixel_rect

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
                         + st.label_size + 4)
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
        from .svg import _effective_rect, _max_ytick_width, _pixel_rect

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
                         - st.label_size - 4)
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
        from .vega import figure_to_vega
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
        from .vega_lite import figure_to_vega_lite
        return figure_to_vega_lite(self, mesh_data=mesh_data)

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
                extra_js: str = None) -> str:
        """Serialize to a self-contained HTML document.

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
        svg = figure_to_svg(self)
        # Tag the root <svg> so the JS can grab it.
        svg = svg.replace("<svg ", '<svg id="plotpress-svg" ', 1)
        script = ""
        if interactive:
            from .svg import (
                axes_metadata, frame_data, layout_metadata, pick_data, style_payload,
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
            layout = _json_payload(layout_metadata(self, idx_of=idx_of))
            payloads = (
                f'<script type="application/json" id="plotpress-meta">{meta}</script>'
                f'<script type="application/json" id="plotpress-pick">{pick}</script>'
                f'<script type="application/json" id="plotpress-style">{styl}</script>'
                f'<script type="application/json" id="plotpress-layout">{layout}</script>'
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
            script = config + payloads
            if include_default_js:
                from ._interactive import INTERACTIVE_JS
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
             dpi: float = None, transparent: bool = False, format: str = None):
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
                                   extra_js=extra_js)
        elif ext == "svg":
            content = self.to_svg()
        elif ext == "png":
            from .raster import save_png
            return save_png(self, path, scale=scale, dpi=dpi, transparent=transparent)
        elif ext in ("jpg", "jpeg"):
            from .raster import save_jpeg
            return save_jpeg(self, path, scale=scale, dpi=dpi)
        elif ext == "webp":
            from .raster import save_webp
            return save_webp(self, path, scale=scale)
        elif ext == "pdf":
            from .raster import save_pdf
            return save_pdf(self, path)
        elif ext == "eps":
            from .raster import save_eps
            return save_eps(self, path)
        elif ext == "gif":
            from .raster import save_gif
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
    def show(self, interactive: bool = True, wait_for_extract: bool = False):
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
        html = self.to_html(interactive=interactive, wait_extract=wait_for_extract)
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
        from .qt import view
        return view(self, title=title, block=block, interactive=interactive,
                    pick_precision=pick_precision)

    def show_in_jupyter(self, width=None, height=None, interactive: bool = True,
                        pick_precision: int = 6, pick_max_mesh_cells: int = 250000,
                        pick_max_points: int = 20000, binary_pick_data: bool = True,
                        include_default_js: bool = True, extra_js: str = None):
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


def _cbar_label_width(cax) -> float:
    """Figure-fraction width the colorbar's tick labels need to its right.

    The renderer draws them outside the bar, so without this the labels spill
    past the space stolen from the parent -- into the next subplot, or off the
    figure edge. Measuring needs the mappable's ``vmin``/``vmax``, which every
    mappable resolves when it is constructed, so this is safe to call before
    anything has been drawn.
    """
    from .colors import resolve_colorbar_ticks

    st = cax.style
    _, _, labels = resolve_colorbar_ticks(cax._cbar_source.norm, cax._cbar_ticks,
                                          cax._cbar_format)
    text_px = max((st.text_width(t, st.tick_label_size) for t in labels),
                  default=0.0)
    return (st.tick_size + 2 + text_px) / (cax.figure.figsize[0] * st.dpi)


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
    from .svg import FIGURE_LEGEND_EDGE, figure_legend_layout

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
        band = min((lay["box_h"] + 2 * pad_px) / H, 0.6)
    else:
        band = min((lay["box_w"] + 2 * pad_px) / W, 0.6)
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

    from .vega_lite import _STRUCTURAL_WARNING_PREFIX

    report = {}

    def add(msg, target):
        idxs = [int(m) for m in re.findall(r"axes (\d+)", msg)] or [None]
        for i in idxs:
            report.setdefault(i, {"vega": [], "vega_lite": []})[target].append(msg)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            fig.to_vega()
        except Exception:
            pass
    for w in caught:
        add(str(w.message), "vega")

    with warnings.catch_warnings(record=True) as caught2:
        warnings.simplefilter("always")
        try:
            _, caveats = fig.to_vega_lite()
        except Exception:
            caveats = []
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


def _sanitize_nan(obj):
    """Replace non-finite floats (NaN/Infinity/-Infinity) with ``None``.

    ``json.dumps``'s default ``allow_nan=True`` emits those as bare, unquoted
    tokens -- valid Python literals but not valid JSON -- so the browser's
    strict ``JSON.parse`` throws on the very first one and the whole payload
    (meta, pick data, style, everything in one script element) fails to load,
    silently disabling the entire interactive toolbar. A masked or missing
    measurement is an ordinary case for real data (a heatmap's saturated
    pixels, a masked land/ocean field, a scatter's dropped-out channel), not a
    rare one, so this has to hold for every payload, not just the common one.
    """
    if isinstance(obj, np.generic):
        # A numpy scalar (np.int64, np.float64, ...) reaching here -- e.g.
        # from a set_xlocator()/set_xformat() spec built with a value pulled
        # out of a numpy array -- isn't JSON-serializable even though most
        # numpy float types happen to subclass the builtin float. .item()
        # unwraps it to the equivalent native Python type; recursing lets
        # the float branch below still catch a numpy NaN/Infinity.
        return _sanitize_nan(obj.item())
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _columnarize_meta(meta):
    """``{axes_index: {field: value, ...}, ...}`` -> one array per field.

    ``axes_metadata()`` has no long arrays of its own -- every field is a
    single scalar per axes -- so on a figure with hundreds of axes its cost
    is ~25 JSON key names (``"tick_style"``, ``"secondary_dim"``, ...)
    repeated in full for every one of them, not a big number array
    :func:`_encode_binary_arrays` could shrink. Restructuring to one array
    per field states each key name once total; the client rebuilds the exact
    original per-axes shape from it (see ``_interactive.py``'s
    ``expandColumnarMeta``), so nothing downstream that reads
    ``META[axesIndex].field`` has to change. The axes index itself isn't
    contiguous (colorbar/3-D/hidden axes are excluded upstream), so it rides
    along as its own array rather than being assumed to be ``range(n)``.
    """
    index = list(meta.keys())
    if not index:
        return {"keys": [], "index": [], "cols": {}}
    keys = list(next(iter(meta.values())).keys())
    cols = {k: [meta[i][k] for i in index] for k in keys}
    return {"keys": keys, "index": index, "cols": cols}


_BINARY_ARRAY_MIN_LEN = 32  # below this, base64+wrapper overhead loses to plain JSON


def _fits_float16(arr, precision):
    """Whether ``arr`` (float64) survives a float16 round trip losing nothing
    beyond what rounding to ``precision`` decimals already gave up.

    float16 has ~3 significant decimal digits and overflows past +-65504, so
    this can't be decided from ``precision`` alone -- a value in the
    thousands loses digits precision=6 promised to keep, and one past 65504
    overflows to Infinity outright. Casting down and back and comparing
    catches both: NaN/+Inf/-Inf must map to themselves exactly (an
    overflowing finite value shows up as a spurious Infinity here), and every
    finite value must still match to within half the last decimal place
    ``precision`` rounded to.
    """
    if arr.size == 0:
        return True
    nan, posinf, neginf = np.isnan(arr), np.isposinf(arr), np.isneginf(arr)
    finite = ~(nan | posinf | neginf)
    # A value past float16's range overflowing to Infinity here is expected
    # and handled below (it fails the mask comparison, so float32 is used
    # instead) -- not a bug to warn about on every large-magnitude figure,
    # which binary_pick_data's default-on status would otherwise do.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        f16_as_f64 = arr.astype(np.float16).astype(np.float64)
    if not (np.array_equal(np.isnan(f16_as_f64), nan)
            and np.array_equal(np.isposinf(f16_as_f64), posinf)
            and np.array_equal(np.isneginf(f16_as_f64), neginf)):
        return False
    if not finite.any():
        return True
    tol = 0.5 * 10.0 ** -precision
    return np.allclose(f16_as_f64[finite], arr[finite], atol=tol, rtol=0)


def _toolbar_clearance(interactive, n_sliders):
    """(top, bottom) pixels of vertical space the toolbar and any docked
    slider strip need -- both are real reserved space for the same reason:
    the menu bar (``.plotpress-menubar``) and a docked slider strip
    (``.plotpress-sliders``) are both ``position:fixed`` overlays (the bar
    pinned to the top of the viewport so Pan/Zoom's own whole-figure zoom
    can never scroll it out of reach -- see the CSS comment on
    ``.plotpress-menubar`` in ``_interactive.py``), so nothing else stops
    either from drawing over the figure unless this reserves the room for
    them. Used for a ``standalone=False`` document's own body padding
    (:meth:`Figure.to_html`) and for sizing an ``<iframe>`` around one
    (:meth:`Report.save`, and the docs build's own gallery/usage embeds in
    ``docs/conf.py``), so a figure looks the same either way it ends up on
    a page. A standalone page needs neither: a full viewport tall of
    flex-centering slack already keeps both from overlapping the centered
    figure.

    41px is the bar's own single row, measured live in a browser -- padding
    top/bottom, its 1px border-bottom, plus its button/label content's own
    line height, no separate group labels or stacked rows the old two-row
    toolbar needed. Does not budget for a caller's own ``plotpressAddTool()``
    menu (``extra_js=`` on :meth:`Figure.to_html`) -- it lands in the *same*
    row (a sixth menu, not an extra one), so it never changes the bar's own
    height regardless of how many custom tools it adds.

    60px per slider matches each docked strip's own footprint
    (``.plotpress-slider``).
    """
    if not interactive:
        return 0, 0
    return 41, 60 * n_sliders


def _encode_binary_arrays(obj, precision=6):
    """Replace long flat number lists with a base64 float16/float32 buffer.

    A mesh z grid or a long line series embeds as JSON number *text*
    (``"0.707107,0.6,..."``) by default -- verbose, and every value has to be
    re-parsed digit by digit on the JS side. Swapping those arrays for
    ``{"__f32__": "<base64>"}`` (or ``{"__f16__": ...}`` where that loses
    nothing -- see :func:`_fits_float16`) and reinterpreting the bytes
    client-side benchmarked at roughly half the embedded size and stayed
    close to ``JSON.parse``-level decode speed, where matching that size with
    gzip instead cost 5-7x the decode time -- ``DecompressionStream``'s
    per-call overhead dominates at these payload sizes. See the benchmark
    this was validated against for the numbers.

    At the library's default ``precision=6``, float16's ~3 significant
    digits essentially never clears the round-trip check, so this only
    starts choosing float16 once a caller lowers ``pick_precision`` enough
    for it to matter -- consistent with what that parameter has always
    promised: lower precision, smaller file.

    Float32/float16 both natively represent NaN/Infinity, so a masked mesh
    cell or dropped-out channel survives the round trip without the ``None``
    substitution :func:`_sanitize_nan` has to do for plain JSON numbers --
    this only ever touches arrays that go through this encoder, not
    everything else in the payload, so short arrays keep exact ``_sanitize_nan``
    behavior.
    """
    if isinstance(obj, dict):
        return {k: _encode_binary_arrays(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        if (len(obj) >= _BINARY_ARRAY_MIN_LEN
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in obj)):
            arr = np.asarray(obj, dtype=np.float64)
            if _fits_float16(arr, precision):
                return {"__f16__": base64.b64encode(
                    arr.astype(np.float16).tobytes()).decode("ascii")}
            arr32 = arr.astype(np.float32)
            return {"__f32__": base64.b64encode(arr32.tobytes()).decode("ascii")}
        return [_encode_binary_arrays(v, precision) for v in obj]
    return obj


def _json_payload(obj) -> str:
    """JSON for embedding in an inline ``<script>`` block.

    An HTML parser ends a script element at the first ``</script`` in its text,
    wherever it appears -- so a label or dimension name carrying that substring
    would close the payload early and turn whatever followed into live markup.
    ``json.dumps`` does not escape ``<``, so escape it (plus ``>`` and ``&``) as
    ``\\uXXXX``. These are valid JSON string escapes, so ``JSON.parse`` still
    yields the original characters.
    """
    return (
        json.dumps(_sanitize_nan(obj))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


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
    """Re-apply everything ``layout_metadata()`` captured about one axes'
    own decorations, so :func:`subplots_from_layout`'s caller never has to
    re-set a title/label/limit/scale by hand. ``.get(...)`` throughout,
    not direct indexing: a layout loaded from a file saved before these
    fields existed (see ``_load_layout``'s old-file fallback) simply has
    none of them, and every one is meant to no-op rather than raise then.

    Routed through :meth:`Axes.set` where possible (the single-value
    setters it already validates and dispatches) rather than one direct
    call per property -- keeps this in sync with ``Axes.set()``'s own
    growing coverage instead of hand-duplicating its dispatch table one
    property at a time.
    """
    bulk = {}
    for key in ("xlabel", "ylabel", "xscale", "yscale", "aspect", "box_aspect",
               "facecolor"):
        if spec.get(key) is not None:
            bulk[key] = spec[key]
    if spec.get("xlim") is not None:
        bulk["xlim"] = tuple(spec["xlim"])
    if spec.get("ylim") is not None:
        bulk["ylim"] = tuple(spec["ylim"])
    if bulk:
        ax.set(**bulk)
    # Not covered by .set() -- see its own docstring on the no-argument
    # toggles and multi-value setters it deliberately excludes.
    # layout_metadata() only records these when a label is actually hidden.
    if spec.get("xlabel_visible") is False:
        ax.set_xlabel_visible(False)
    if spec.get("ylabel_visible") is False:
        ax.set_ylabel_visible(False)
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


def subplots_from_layout(layout, figsize=None, style: Style = None, facecolor=None):
    """Rebuild a figure with the exact axes grid and :meth:`Figure.group`
    boxes recorded in a ``load_data()`` ``"layout"`` dict.

    Lets recovered data (:func:`load_data`'s ``"series"``/``"meshes"``/
    ``"pies"``) be replotted into a figure structurally identical to the one
    it came from, without hand-matching ``nrows``/``ncols`` yourself the way
    :doc:`/auto_examples/data_roundtrip/index` used to before this existed.

    Returns ``(fig, axes)``. When every recorded axes is a single,
    non-spanning cell that exactly tiles one ``nrows`` x ``ncols`` grid,
    ``axes`` mirrors what ``plotpress.subplots(nrows, ncols)`` itself would
    hand back -- a bare ``Axes`` for a 1x1 grid, a 1-D array for a single
    row/column, otherwise a 2-D array indexed ``axes[row, col]``. Anything
    else (row/column spans from ``add_gridspec``, mismatched grids across
    axes, or no grid-placed axes at all) falls back to a flat list of axes
    in their original save order -- still fully usable, just not
    array-indexable by row/column.

    ``figsize`` overrides ``layout["figsize"]`` (falling back to plotpress's
    own default when a loaded layout predates that key and carries
    ``None``). ``style`` is the same as :class:`Figure`'s own constructor --
    it doesn't round-trip through ``layout`` at all (a custom
    :class:`~plotpress.Style` -- colors, fonts, dpi -- is a bigger,
    separate concern this doesn't attempt). ``facecolor`` overrides
    ``layout["facecolor"]`` the same way ``figsize`` overrides its own key.

    Every axes comes back already carrying its own title, x/y labels,
    limits, scale, grid, aspect, and inverted-axis state -- exactly as
    :meth:`Figure.group` boxes and the grid shape itself already did --
    so a caller only has to replot the recovered data, never re-set a
    single label or title by hand. A label hidden with
    ``set_xlabel(..., visible=False)`` comes back hidden (still stored,
    still drawn nowhere). The figure's own :meth:`Figure.suptitle`/
    :meth:`~Figure.supxlabel`/:meth:`~Figure.supylabel` and background
    color come back the same way. Not carried over (real gaps, not
    oversights -- see :func:`plotpress.svg.layout_metadata`'s own
    docstring for why): colorbars, tick_params()/explicit tick overrides,
    twin/secondary/inset axes, a custom ``Style``, and any axes' or
    group's own ``id`` (see :meth:`~plotpress.axes.Axes.set_id`) --
    silently, so re-apply one yourself after replotting if a later
    ``get_ax``/``get_group`` lookup depends on it. An axes that had a
    :meth:`~Axes.legend` is recorded too, but never auto-applied -- a
    legend draws from already-plotted, labeled artists, none of which
    exist on a freshly rebuilt axes yet; call
    ``ax.legend(**layout["axes"][i]["legend"])`` yourself once you've
    replotted into it.

    Warns (``UserWarning``) when ``layout["omitted_axes"]`` is non-empty --
    axes the source figure placed with a freeform :meth:`Figure.add_axes`
    rect rather than a subplot grid cell have no recorded position to
    rebuild from, so they are simply missing from the returned figure; the
    warning is the only signal of that, since a caller with no other axes
    count to compare against would otherwise have no way to notice. A
    separate warning names any :meth:`Figure.group` whose own box lost a
    member to that same drop -- the group is still created around whichever
    of its axes did come back, just smaller than the original.
    """
    omitted = layout.get("omitted_axes") or []
    if omitted:
        warnings.warn(
            f"subplots_from_layout(): {len(omitted)} axes from the saved "
            f"figure (index {omitted}) were placed with a freeform "
            "Figure.add_axes() rect, not a subplot grid cell, and could not "
            "be recovered -- they are simply absent from the rebuilt figure.",
            UserWarning, stacklevel=2)
    fig = Figure(figsize=figsize or tuple(layout.get("figsize") or (6.4, 4.8)),
                style=style,
                facecolor=facecolor if facecolor is not None else layout.get("facecolor"))
    axes_specs = layout.get("axes") or {}
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

    sup = layout.get("suptitle")
    if sup:
        fig.suptitle(sup["text"], size=sup.get("size"))
    supx = layout.get("supxlabel")
    if supx:
        fig.supxlabel(supx["text"], size=supx.get("size"))
    supy = layout.get("supylabel")
    if supy:
        fig.supylabel(supy["text"], size=supy.get("size"))

    for g in layout.get("groups") or []:
        members = [by_index[int(i)] for i in g["axes"] if int(i) in by_index]
        # n_members (the group's ORIGINAL size, before layout_metadata()
        # filtered out members it already knew were unrecoverable) is what
        # tells apart a group that lost one of its own axes -- the
        # top-level omitted_axes warning above only says *an* axes was
        # dropped, never which group that broke.
        n_original = g.get("n_members", len(g["axes"]))
        if members and len(members) < n_original:
            warnings.warn(
                f"subplots_from_layout(): group {g['title']!r} had "
                f"{n_original} axes in the saved figure but only "
                f"{len(members)} could be recovered -- the rebuilt group "
                "box wraps fewer axes than the original.",
                UserWarning, stacklevel=2)
        if members:
            fig.group(g["title"], members, linestyle=g.get("linestyle", "--"),
                     color=g.get("color", "black"), linewidth=g.get("linewidth", 1.5),
                     title_position=g.get("title_position", "top"),
                     pad=tuple(g["pad"]) if g.get("pad") is not None else 8.0,
                     fontsize=g.get("fontsize"),
                     supxlabel=g.get("supxlabel"), supylabel=g.get("supylabel"),
                     supxlabel_size=g.get("supxlabel_size"),
                     supylabel_size=g.get("supylabel_size"),
                     visible=g.get("visible", True))

    ordered = [by_index[int(i)] for i in order]
    same_shape = len({(s["nrows"], s["ncols"]) for s in specs}) == 1
    single_cell = all(s["row0"] == s["row1"] and s["col0"] == s["col1"] for s in specs)
    if ordered and same_shape and single_cell:
        nrows, ncols = specs[0]["nrows"], specs[0]["ncols"]
        if len(ordered) == nrows * ncols:
            grid = np.empty((nrows, ncols), dtype=object)
            for i, s in zip(order, specs):
                grid[s["row0"], s["col0"]] = by_index[int(i)]
            if nrows == 1 and ncols == 1:
                return fig, grid[0, 0]
            if nrows == 1 or ncols == 1:
                return fig, grid.ravel()
            return fig, grid
    return fig, ordered


def _fit_cells(avail, n, gaps, floor=0.02):
    """Cell size and per-boundary gaps that fit ``n`` cells into ``avail``.

    ``gaps`` is a list of ``n - 1`` inter-cell gaps -- not necessarily
    uniform, since :meth:`Figure.group_spacing` only widens the boundaries
    that actually border a group. The gap is what the decorations need; the
    cell is what is left over. When a dense grid cannot afford both, the
    *gap* gives way first -- panels squeezed together are still readable,
    and the alternative was worse than ugly: the cell size alone was clamped
    to a floor while the gap kept its full width, so the rows ran past the
    top of the canvas and the first nine rows of a 30x30 grid were simply
    not on the figure.

    If even the floor does not fit, the cells shrink below it rather than
    overflow. Tiny but present beats absent. A non-uniform ``gaps`` shrinks
    proportionally, keeping the ratio between a group boundary and a plain
    tick-label gap rather than collapsing both to the same value.
    """
    if n <= 1:
        return max(avail, 1e-4), list(gaps)
    total_gap = sum(gaps)
    cell = (avail - total_gap) / n
    if cell >= floor:
        return cell, list(gaps)
    max_total_gap = max(0.0, avail - n * floor)
    scale = (max_total_gap / total_gap) if total_gap > 0 else 0.0
    new_gaps = [g * scale for g in gaps]
    return max((avail - max_total_gap) / n, 1e-4), new_gaps


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


_REPORT_MAX_WIDTH = 1600   # .plotpress-report's own max-width, below --
                           # Report.save() reuses this for its iframes'
                           # starting height guess, so the two never drift
                           # apart the way a second hardcoded number would.

_REPORT_STYLE = (
    "<style>"
    "body{margin:0;padding:24px 16px;background:#f5f5f5;"
    "font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1a1a1a}"
    f".plotpress-report{{max-width:{_REPORT_MAX_WIDTH}px;margin:0 auto}}"
    ".plotpress-report>h1{font-size:24px;margin:0 0 6px}"
    ".plotpress-report-description{color:#555;margin:0 0 20px;max-width:70ch}"
    # Sits between the description and the first entry regardless of whether
    # a description was actually given -- margin-bottom on the button itself
    # (not a wrapping div) collapses to nothing extra when it directly
    # follows the description's own margin-bottom, so the gap above the
    # first entry stays the same either way.
    ".plotpress-report-toggle-all{margin:0 0 32px;padding:6px 14px;"
    "border:1px solid #ccc;border-radius:6px;background:#fff;color:#333;"
    "font:inherit;font-weight:600;cursor:pointer}"
    ".plotpress-report-toggle-all:hover{background:#f0f0f0}"
    ".plotpress-report-entry{margin-bottom:44px}"
    ".plotpress-report-toggle{display:flex;align-items:center;gap:6px;"
    "cursor:pointer;-webkit-user-select:none;user-select:none}"
    ".plotpress-report-chevron{display:inline-block;font-size:10px;color:#888;"
    "transition:transform .15s;flex:none}"
    ".plotpress-report-entry.plotpress-collapsed .plotpress-report-chevron{"
    "transform:rotate(-90deg)}"
    ".plotpress-report-heading{min-width:0}"
    ".plotpress-report-label{font-size:11px;font-weight:600;letter-spacing:.04em;"
    "text-transform:uppercase;color:#888;margin-bottom:4px}"
    ".plotpress-report-entry h2{font-size:18px;margin:0 0 4px}"
    ".plotpress-report-details{color:#555;margin:8px 0 14px;max-width:70ch;"
    "white-space:pre-wrap}"
    # Collapsed hides only the iframe -- the label/title/details above stay
    # visible, so a fully collapsed report still reads as a scannable outline
    # of what each figure is, not a bare list of "Figure N" headings.
    ".plotpress-report-entry.plotpress-collapsed iframe{display:none}"
    # width:100% (not max-width) -- this is what actually stretches each
    # figure to fill the report's own width instead of sitting at whatever
    # fixed pixel size the figure happened to be created at.
    ".plotpress-report-entry iframe{border:1px solid #ddd;border-radius:6px;"
    "background:#fff;display:block;width:100%}"
    "</style>"
)

# Resizes each report iframe to its actual rendered content height instead of
# a fixed guess -- the SVG inside scales to fill whatever width the iframe is
# given (see Figure.to_html's standalone=False), so a static height computed
# once at save() time would either clip it (a narrower guess than the reader's
# actual browser width lets the figure grow to) or leave empty space below it
# (a wider one). srcdoc iframes share their parent's origin, so the page can
# read contentDocument directly -- no postMessage handshake needed. Toolbar
# and docked-slider clearance need no separate accounting here: they're real
# body padding inside the embedded document itself (see Figure.to_html's
# standalone=False branch), so scrollHeight already includes them.
#
# fit() no-ops until an iframe's own `load` marks it dataset.loaded -- a
# below-the-fold entry (loading="lazy") can still receive the debounced
# resize handler's sweep before it has ever loaded, and measuring an
# unloaded/placeholder document's near-zero scrollHeight would collapse its
# still-showing initial height guess for no reason. It also skips an iframe
# whose rendered width hasn't changed since its last fit -- on a fixed
# aspect ratio, that means its needed height hasn't either. A collapsed
# entry's iframe measures 0 width (display:none), so expanding it always
# looks "changed" and re-fits -- the same reason setCollapsed() below calls
# fit() itself on expand, rather than waiting for a resize that may never come.
#
# Collapsing only ever toggles a CSS class -- an already-expanded entry's
# iframe (and, when interactive=True, its whole toolbar/pan/zoom/pick state)
# is never removed from the DOM, so re-expanding shows it exactly as it was
# left, no reload. A collapsed=True entry (Report.save()) is different: its
# iframe never gets a real srcdoc attribute at all, only a data-lazy-doc
# holding the identical escaped document -- measured directly (see the
# collapsed-report tests in test_pick_interactive.py), a display:none
# srcdoc iframe's own loading="lazy" does NOT defer anything in real engines;
# a never-laid-out element has no box for a viewport-*distance* heuristic to
# judge against, so it just loads immediately regardless of being hidden.
# setCollapsed() below does the deferral itself: the first time an entry
# expands, it moves data-lazy-doc onto the iframe's real .srcdoc property
# (triggering the actual parse/render right then, not before) and deletes
# the data attribute so the DOM isn't left holding two copies of a
# potentially large document. This is what actually delivers "a many-figure
# collapsed report opens instantly" -- collapsed=True alone, without this,
# would only have hidden the figures on screen while still parsing every one
# of them up front.
#
# data-lazy-doc, deliberately not e.g. data-deferred-srcdoc: load_data()'s
# own regex (see _split_report_entries's caller) looks for the literal
# substring ``srcdoc="`` to find each entry's embedded document -- a name
# that happened to still *contain* that substring would keep load_data()
# working by accident, a coincidence one future rename away from silently
# breaking it. load_data() instead checks for this attribute by name
# explicitly, as a real second case, not a lucky substring match.
_REPORT_SCRIPT = (
    "<script>(function(){"
    "function fit(f){"
    "var d=f.contentDocument;if(!d||!d.body||!f.dataset.loaded)return;"
    "var w=f.clientWidth;if(f.dataset.fitWidth===String(w))return;"
    "f.dataset.fitWidth=String(w);"
    "f.style.height=d.body.scrollHeight+'px';}"
    "var frames=document.querySelectorAll('.plotpress-report-entry iframe');"
    "frames.forEach(function(f){f.addEventListener('load',function(){"
    "f.dataset.loaded='1';fit(f);});});"
    "var t;window.addEventListener('resize',function(){"
    "clearTimeout(t);t=setTimeout(function(){frames.forEach(fit);},120);});"
    "function setCollapsed(entry,collapsed){"
    "entry.classList.toggle('plotpress-collapsed',collapsed);"
    "var h=entry.querySelector('.plotpress-report-toggle');"
    "if(h)h.setAttribute('aria-expanded',collapsed?'false':'true');"
    "if(!collapsed){var f=entry.querySelector('iframe');if(f){"
    "if(f.dataset.lazyDoc!==undefined){"
    "f.srcdoc=f.dataset.lazyDoc;delete f.dataset.lazyDoc;}"
    "fit(f);}}}"
    "document.querySelectorAll('.plotpress-report-toggle').forEach(function(h){"
    "h.addEventListener('click',function(){"
    "var entry=h.closest('.plotpress-report-entry');"
    "setCollapsed(entry,!entry.classList.contains('plotpress-collapsed'));});"
    "h.addEventListener('keydown',function(e){"
    "if(e.key==='Enter'||e.key===' '){e.preventDefault();h.click();}});});"
    "var allBtn=document.getElementById('plotpress-report-toggle-all');"
    "if(allBtn)allBtn.addEventListener('click',function(){"
    "var entries=document.querySelectorAll('.plotpress-report-entry');"
    "var anyExpanded=Array.prototype.some.call(entries,function(e){"
    "return!e.classList.contains('plotpress-collapsed');});"
    "entries.forEach(function(e){setCollapsed(e,anyExpanded);});"
    "allBtn.textContent=anyExpanded?'Expand All':'Collapse All';});"
    "})();</script>"
)


class Report:
    """An ordered collection of figures combined into one self-contained HTML file.

    Each figure keeps its own independent interactivity -- its own toolbar,
    pan/zoom, point-picking, annotations -- because it is embedded in its own
    ``<iframe>`` rather than spliced directly into the page. An interactive
    figure's JS (:mod:`plotpress._interactive`) assumes it owns the page: fixed
    element ids (``plotpress-svg``, ``plotpress-meta``, ...) and a
    document-level toolbar, so several figures sharing one page directly would
    collide -- the same reason the docs gallery embeds every live figure this
    way (see ``docs/conf.py``'s ``_interactive_embed``). An iframe gives each
    figure its own document instead, at no real cost to "one file": each
    figure's already-self-contained HTML (see :meth:`Figure.to_html`) is
    inlined via the iframe's ``srcdoc`` attribute rather than referenced as a
    separate file, so the report is still a single, self-contained HTML
    document with no external requests.

    Add figures with :meth:`add`, in the order they should appear, then write
    the combined file with :meth:`save`::

        report = plotpress.Report(title="Weekly QA sweep",
                                  description="Four sensor batches, one figure each.")
        report.add(fig_a, title="Batch A", details="Baseline run, no anomalies.")
        report.add(fig_b, title="Batch B", details="Elevated noise floor after 14:00.")
        report.save("qa_sweep.html")
    """

    def __init__(self, title: str = None, description: str = None):
        self.title = title
        self.description = description
        self._entries = []   # [(figure, title, details)], in add() order

    def add(self, figure: "Figure", title: str = None, details: str = None) -> "Report":
        """Append ``figure`` to the report; returns ``self`` so calls can chain.

        ``title`` (a short heading) and ``details`` (a longer description) are
        optional per-figure annotations rendered above the embedded figure.
        Figures appear in the HTML in the order they were added -- there is no
        separate ordering mechanism to keep in sync.
        """
        if not isinstance(figure, Figure):
            raise TypeError("Report.add() expects a Figure, got %r" % (figure,))
        self._entries.append((figure, title, details))
        return self

    def save(self, path: str, interactive: bool = True,
             pick_precision: int = 6, pick_max_mesh_cells: int = 250000,
             pick_max_points: int = 20000, binary_pick_data: bool = True,
             collapsed: bool = False) -> str:
        """Write every added figure, in order, to one self-contained HTML file.

        ``interactive`` and the ``pick_*``/``binary_pick_data`` arguments are
        forwarded to each figure's own :meth:`Figure.to_html` -- see there for
        what they mean. Every figure in the report shares the same settings;
        call :meth:`Figure.to_html` directly (and write the file yourself) for
        a mix of interactive and static figures on one page.

        Every entry is collapsible: a click anywhere on its "Figure N"/title
        header hides just that entry's figure, leaving its title and details
        visible -- a long report reads as a scannable outline instead of a
        wall of figures. A **Collapse All**/**Expand All** button above the
        first entry does the same for every one at once.

        ``collapsed=True`` starts every entry collapsed instead of open, and
        genuinely defers each one: rather than embed it as a live ``srcdoc``
        that just sits hidden, the escaped document is parked in a plain data
        attribute and only ever assigned to the iframe -- triggering the real
        parse/render -- the first time a reader actually expands that entry.
        A collapsed figure's own toolbar/pan-zoom/pick-data JS never runs
        until then, so a report with many (or heavy) figures opens instantly
        regardless of how many it holds, at the cost of a brief render on
        each entry's first expand instead.
        """
        if not self._entries:
            raise ValueError("Report has no figures -- call add() at least once")
        parts = [
            "<!doctype html><html><head><meta charset='utf-8'>",
            f"<title>{html.escape(self.title)}</title>" if self.title else "",
            _REPORT_STYLE,
            "</head><body><div class='plotpress-report'>",
        ]
        if self.title:
            parts.append(f"<h1>{html.escape(self.title)}</h1>")
        if self.description:
            parts.append('<p class="plotpress-report-description">'
                         f'{html.escape(self.description)}</p>')
        toggle_all_label = "Expand All" if collapsed else "Collapse All"
        parts.append(
            f'<button type="button" id="plotpress-report-toggle-all" '
            f'class="plotpress-report-toggle-all">{toggle_all_label}</button>')
        for n, (figure, title, details) in enumerate(self._entries, start=1):
            doc = figure.to_html(interactive=interactive,
                                 pick_precision=pick_precision,
                                 pick_max_mesh_cells=pick_max_mesh_cells,
                                 pick_max_points=pick_max_points,
                                 binary_pick_data=binary_pick_data,
                                 standalone=False)
            dpi = figure.style.dpi
            natural_w = figure.figsize[0] * dpi
            natural_h = figure.figsize[1] * dpi
            top_pad, bottom_pad = _toolbar_clearance(interactive, len(figure._sliders or {}))
            # A starting guess only -- the resize script (_REPORT_SCRIPT)
            # corrects this to the real rendered height right after the
            # iframe loads, once it knows how wide the reader's own browser
            # actually made it. Guessing at .plotpress-report's own max
            # rendered width (rather than the figure's own pixel size, often
            # much narrower) keeps that first correction small; toolbar/slider
            # clearance is exact, not guessed, since it's baked into the
            # embedded document's own body padding either way (Figure.to_html,
            # standalone=False) -- scrollHeight will already include it.
            guess_w = _REPORT_MAX_WIDTH - 2 * 16 - 2 * 1   # body padding, iframe border
            h = round(guess_w * natural_h / natural_w) + top_pad + bottom_pad
            iframe_title = html.escape(title) if title else "Figure %d" % n
            entry_class = "plotpress-report-entry plotpress-collapsed" if collapsed \
                else "plotpress-report-entry"
            parts.append(f'<div class="{entry_class}">')
            parts.append(
                '<div class="plotpress-report-toggle" role="button" tabindex="0" '
                f'aria-expanded="{"false" if collapsed else "true"}">'
                '<span class="plotpress-report-chevron">&#9662;</span>'
                '<div class="plotpress-report-heading">'
                f'<div class="plotpress-report-label">Figure {n}</div>')
            if title:
                parts.append(f"<h2>{html.escape(title)}</h2>")
            parts.append('</div></div>')
            if details:
                parts.append('<p class="plotpress-report-details">'
                             f'{html.escape(details)}</p>')
            if collapsed:
                # Not srcdoc=: a display:none iframe's own loading="lazy"
                # turned out not to defer anything in practice (see
                # _REPORT_SCRIPT's own comment on setCollapsed) -- real
                # engines have a viewport-*distance* heuristic to judge
                # "near enough to load", which a never-laid-out element has
                # no geometry for, so several just load it immediately
                # regardless. Parking the same escaped doc in a data
                # attribute instead means nothing is even parsed as HTML
                # until setCollapsed()'s own JS deliberately assigns it to
                # a real .srcdoc on that entry's first expand.
                parts.append(
                    f'<iframe data-lazy-doc="{html.escape(doc)}" '
                    f'height="{h}" title="{iframe_title}"></iframe>')
            else:
                parts.append(
                    f'<iframe srcdoc="{html.escape(doc)}" height="{h}" '
                    f'loading="lazy" title="{iframe_title}"></iframe>')
            parts.append("</div>")
        parts.append(_REPORT_SCRIPT)
        parts.append("</div></body></html>")
        content = "".join(parts)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path


def _decode_binary_arrays(obj):
    """Reverse :func:`_encode_binary_arrays`: a ``{"__f32__": b64}``/
    ``{"__f16__": b64}`` leaf becomes a real ``numpy`` array; everything else
    is walked unchanged. float16 decodes via ``numpy``'s native dtype (exact,
    unlike the JS side's hand-rolled ``halfToFloat`` -- there is no
    ``Float16Array`` in a browser, but Python has no such gap).
    """
    if isinstance(obj, dict):
        if set(obj) == {"__f32__"}:
            return np.frombuffer(base64.b64decode(obj["__f32__"]), dtype=np.float32)
        if set(obj) == {"__f16__"}:
            return np.frombuffer(base64.b64decode(obj["__f16__"]),
                                 dtype=np.float16).astype(np.float64)
        return {k: _decode_binary_arrays(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_binary_arrays(v) for v in obj]
    return obj


def _expand_columnar_meta(payload):
    """Reverse :func:`_columnarize_meta`: ``{"cols", "index", "keys"}`` (one
    array per field) back to ``{axes_index: {field: value, ...}, ...}``. A
    plain (non-columnarized) meta payload -- ``binary_pick_data=False`` never
    columnarizes -- is returned unchanged.
    """
    if not (isinstance(payload, dict)
            and {"cols", "index", "keys"} <= set(payload)):
        return payload
    cols, index, keys = payload["cols"], payload["index"], payload["keys"]
    return {i: {k: cols[k][pos] for k in keys} for pos, i in enumerate(index)}


def _extract_json_block(text, element_id):
    """The parsed JSON body of ``<script type="application/json" id="...">``,
    or ``None`` if that element isn't in ``text`` at all."""
    m = re.search(
        r'<script type="application/json" id="%s">(.*?)</script>' % re.escape(element_id),
        text, re.DOTALL)
    return json.loads(m.group(1)) if m else None


def _mesh_centers(mesh):
    """1-D cell-center coordinate arrays for a ``pick_data()`` mesh entry, or
    ``(None, None)`` for a curvilinear (warped) mesh, which has no separable
    per-axis coordinates -- only per-cell ``xc``/``yc`` centers.
    """
    if mesh.get("curvilinear"):
        return None, None
    if "xcoord" in mesh:
        # A contour's samples: the exact coordinate, not an edge midpoint --
        # see pick_data()'s own contour branch for why those can differ.
        return (np.asarray(mesh["xcoord"], dtype=float),
                np.asarray(mesh["ycoord"], dtype=float))
    xe = np.asarray(mesh["xedges"], dtype=float)
    ye = np.asarray(mesh["yedges"], dtype=float)
    return (xe[:-1] + xe[1:]) / 2.0, (ye[:-1] + ye[1:]) / 2.0


def _load_single_figure(text):
    """Every plotted axes' data out of one figure's own interactive HTML."""
    pick = _extract_json_block(text, "plotpress-pick")
    if pick is None:
        raise ValueError(
            "no embedded plot data found -- load_data() only works on HTML "
            "saved with interactive=True (Figure.to_html()/save(..., "
            "interactive=True) or Report.save()); a static SVG or "
            "interactive=False HTML embeds only drawn shapes, nothing to "
            "read back")
    pick = {int(k): v for k, v in _decode_binary_arrays(pick).items()}
    meta_raw = _extract_json_block(text, "plotpress-meta") or {}
    meta = _expand_columnar_meta(_decode_binary_arrays(meta_raw))
    meta = {int(k): v for k, v in meta.items()}

    axes = {}
    for i in sorted(set(pick) | set(meta)):
        entry = pick.get(i, {"series": [], "meshes": [], "pies": []})
        m = meta.get(i, {})
        series = []
        for s in entry.get("series", []):
            series.append({
                "kind": s.get("kind"),
                "x": np.asarray(s["x"], dtype=float),
                "y": np.asarray(s["y"], dtype=float),
                "vals": {k: np.asarray(v, dtype=float)
                        for k, v in s.get("vals", {}).items()},
                # None for a file saved before these existed, or a series
                # kind (box/violin/quiver/event/contour) that never carried
                # one meaningful color/label to begin with.
                "label": s.get("label"), "color": s.get("color"),
            })
        meshes = []
        for msh in entry.get("meshes", []):
            ny, nx = msh["shape"]
            z = np.asarray(msh["z"], dtype=float).reshape(ny, nx)
            xc, yc = _mesh_centers(msh)
            meshes.append({
                "x": xc, "y": yc, "z": z,
                "extent": tuple(msh["extent"]),
                "curvilinear": bool(msh.get("curvilinear", False)),
            })
        axes[i] = {
            "series": series, "meshes": meshes, "pies": entry.get("pies", []),
            "title": m.get("title"), "xlabel": m.get("xlabel"),
            "ylabel": m.get("ylabel"), "zlabel": m.get("zlabel"),
            "xlim": (m["xmin"], m["xmax"]) if "xmin" in m else None,
            "ylim": (m["ymin"], m["ymax"]) if "ymin" in m else None,
            "xscale": m.get("xscale"), "yscale": m.get("yscale"),
        }
    return axes


def _load_layout(text):
    """The ``plotpress-layout`` block (see ``svg.layout_metadata``), or the
    empty layout a figure with no grid-placed axes and no groups would embed
    -- older files saved before this block existed fall back to the same
    shape rather than raising, so ``load_data()`` keeps working on them.
    """
    raw = _extract_json_block(text, "plotpress-layout")
    if raw is None:
        return {"figsize": None, "axes": {}, "groups": [], "omitted_axes": [],
                "suptitle": None, "supxlabel": None, "supylabel": None,
                "facecolor": None}
    return {**raw, "axes": {int(k): v for k, v in raw["axes"].items()}}


def _split_report_entries(text):
    """One chunk of HTML per :class:`Report` entry, each starting at its
    ``plotpress-report-label`` div (always present, unlike the optional title/
    details) -- avoids needing to balance nested ``<div>`` tags with regex,
    which a proper (non-regular) HTML parse would need otherwise.
    """
    return text.split('<div class="plotpress-report-label">')[1:]


def _dedupe_keyed(pairs, noun, stacklevel):
    """Build a dict from ``[(key, item), ...]`` pairs (already in the order
    they should be tried), disambiguating any collision with a
    ``"<key> (2)"``, ``"<key> (3)"``, ... suffix -- rather than silently
    letting a later item overwrite, and lose, an earlier one that resolves
    to the identical key. Two axes (or two Report entries) sharing an
    explicit title is realistic authoring, not exotic input worth crashing
    or staying silent about -- a grid of identically-labeled panels, a
    report re-using a section name -- the same "accept it, don't crash,
    but don't stay silent" choice :func:`plotpress.artists.normalize_linestyle`
    already makes for an unrecognized linestyle. Warns once, naming every
    collision resolved, rather than the caller discovering a shorter dict
    than they expected with no signal why.

    ``noun`` is ``(singular, plural)`` (e.g. ``("figure", "figures")``),
    so the one-collision case reads naturally instead of always using the
    plural form regardless of count.
    """
    keyed = {}
    collisions = []
    for base, item in pairs:
        key, n = base, 2
        while key in keyed:
            key = f"{base} ({n})"
            n += 1
        if key != base:
            collisions.append((base, key))
        keyed[key] = item
    if collisions:
        singular, plural = noun
        word = singular if len(collisions) == 1 else plural
        detail = ", ".join(f"{b!r} -> {k!r}" for b, k in collisions)
        warnings.warn(
            f"load_data(): {len(collisions)} {word} shared a title with "
            f"another already-keyed one -- disambiguated ({detail}) so every "
            "one stays recoverable instead of a later one silently "
            "overwriting an earlier one with the same key. Pass "
            "by_index=True for a stable, collision-free key instead.",
            UserWarning, stacklevel=stacklevel)
    return keyed


def _title_keyed_axes(axes):
    """Re-key an int-indexed axes dict by each axes' own title, falling back
    to ``"axes {i}"`` when it has none -- the same fallback a picked record's
    ``axes_title`` already uses (see ``_interactive.py``'s
    ``resolvePickTarget``), so both surfaces name an untitled axes the same
    way. Two axes sharing an explicit title is disambiguated, not silently
    collapsed to one -- see :func:`_dedupe_keyed`.
    """
    pairs = [(axes[i].get("title") or f"axes {i}", axes[i]) for i in sorted(axes)]
    return _dedupe_keyed(pairs, ("axes", "axes"), stacklevel=4)


def load_data(path: str, by_index: bool = False):
    """Read back the plotted data embedded in a self-contained interactive
    HTML file written by :meth:`Figure.to_html`/:meth:`Figure.save` or
    :meth:`Report.save`.

    By default, returns a dict keyed by each figure's own title (a
    :class:`Report` entry's :meth:`Report.add` title; a generated
    ``"Figure N"`` -- 1-based, matching the label a :class:`Report` page
    itself shows -- for an entry with none, or for a bare :class:`Figure`'s
    HTML, which has no report-level title at all). Each figure's own value
    has ``"details"`` (a `Report` entry's longer description, or ``None``)
    ``"axes"`` (itself a dict keyed by each axes' own title, falling back to
    ``"axes {index}"`` -- matching a picked record's ``axes_title`` fallback
    -- for an untitled one), and ``"layout"``::

        {"series": [{"kind": "line", "x": array, "y": array,
                    "vals": {name: array, ...},
                    "label": str | None, "color": str | None}, ...],
         "meshes": [{"x": array,          # 1-D cell centers (None if curvilinear)
                     "y": array,          # 1-D cell centers (None if curvilinear)
                     "z": array,          # 2-D, shape (ny, nx), row 0 = ymin
                     "extent": (xmin, xmax, ymin, ymax),
                     "curvilinear": bool}, ...],
         "pies": [...],
         "title": str | None, "xlabel": str | None, "ylabel": str | None,
         "zlabel": str | None, "xlim": (float, float) | None,
         "ylim": (float, float) | None, "xscale": str, "yscale": str}

    A series' ``"label"``/``"color"`` are the artist's own ``label=``/
    (single, resolved) ``color=`` at save time -- ``None`` for a file saved
    before these existed, an unlabeled/uncolored series, a
    colormap-mapped ``scatter(c=...)`` (no one color to report), or a kind
    with no single meaningful color/label at all (box/violin/quiver/event/
    contour). Real for ``"line"``/``"scatter"``/``"stem"``/``"errorbar"``/
    ``"bar"``, which is enough to rebuild a labeled, colored legend after
    replotting recovered data -- see
    :func:`~plotpress.figure.subplots_from_layout`.

    ``"layout"`` is the figure-level structure -- grid shape/position and
    every decoration (title, labels, limits, scale, ...) of each
    subplot-grid axes, plus any :meth:`Figure.group` boxes and the
    figure's own sup-title/label -- needed to rebuild an equivalent,
    already-labeled figure, independent of the per-axes data above::

        {"figsize": [w, h],
         "axes": {index: {"nrows": int, "ncols": int, "row0": int, "row1": int,
                          "col0": int, "col1": int,
                          "projection": "polar" | None,
                          "title": str | None, "title_size": float | None,
                          "xlabel": str | None, "ylabel": str | None,
                          "xlim": [float, float], "ylim": [float, float],
                          "xscale": str, "yscale": str,
                          "xinverted": bool, "yinverted": bool,
                          "grid": bool, "grid_alpha": float | None,
                          "grid_axis": str, "grid_which": str,
                          "aspect": float | None, "box_aspect": float | None,
                          "axis_off": bool, "facecolor": str | None,
                          "legend": {"loc": str, "ncol": int, "title": str | None,
                                    "fontsize": float | None,
                                    "framealpha": float} | None}, ...},
         "groups": [{"title": str, "axes": [index, ...], "n_members": int,
                     "linestyle": str, "color": str, "linewidth": float,
                     "title_position": str, "pad": [l, r, t, b],
                     "fontsize": float | None}, ...],
         "omitted_axes": [index, ...],
         "suptitle": {"text": str, "size": float | None} | None,
         "supxlabel": {"text": str, "size": float | None} | None,
         "supylabel": {"text": str, "size": float | None} | None,
         "facecolor": str}

    Pass ``"layout"`` straight to :func:`subplots_from_layout` to recreate
    the source figure's grid, every axes' own decorations, and its groups
    before replotting recovered data into it -- see
    :doc:`/auto_examples/data_roundtrip/index`. A file saved before 3-D
    support was removed can still report the literal ``"3d"`` here (this
    function only reads back whatever string was stored, it doesn't
    validate it) -- :func:`subplots_from_layout` raises a clear "unknown
    projection" for that one, since it cannot rebuild an axes kind that no
    longer exists. Axes placed with a
    freeform :meth:`Figure.add_axes` rect (no grid cell) and colorbar axes
    are absent from ``"axes"`` -- their indices are listed in
    ``"omitted_axes"`` instead -- and a group's own ``"n_members"`` is its
    *original* member count, before any unrecoverable member was filtered
    out of its ``"axes"`` list, so a caller can tell a group that lost one
    apart from one that didn't. ``"legend"`` is recorded but not
    auto-applied by ``subplots_from_layout`` -- see that function's own
    docstring for why. A file saved before these keys existed loads as
    ``{"figsize": None, "axes": {}, "groups": [], "omitted_axes": [],
    "suptitle": None, "supxlabel": None, "supylabel": None, "facecolor": None}``,
    and one saved by an in-between version has ``"axes"`` entries with the
    grid-shape keys above but none of the decoration ones (each simply
    absent, not ``None``).

    Title keys are convenient but not guaranteed unique -- two figures (or
    two axes within one figure) sharing the same title no longer collide
    silently: the later one is disambiguated with a ``" (2)"``, ``" (3)"``,
    ... suffix rather than overwriting (and losing) the earlier one, and a
    ``UserWarning`` names every collision resolved this way. Pass
    ``by_index=True`` when even that renaming matters, or when a stable,
    order-based key is simply more useful than a name: this returns a list
    of per-figure dicts instead (one per figure embedded in the file, in
    the order they appear -- a bare figure's HTML still comes back as a
    one-item list), each with the same ``"title"``/``"details"``/``"axes"``/
    ``"layout"`` shape as above except ``"axes"`` is keyed by plain integer
    index rather than title -- and never renamed, since there is no title
    collision to resolve when the key is a position instead of a name.

    Only works on HTML saved with ``interactive=True``: a static SVG or an
    ``interactive=False`` HTML embeds no data to read back, only drawn
    shapes, and raises ``ValueError``. Recovered arrays reflect whatever
    precision/caps were in effect at save time (``pick_precision``,
    ``pick_max_points``, ``pick_max_mesh_cells``) -- they are not guaranteed
    bit-exact copies of the original data for a series/mesh that was rounded
    or capped on the way out. A mesh that crossed ``pick_max_mesh_cells`` at
    save time comes back at that coarser, block-averaged resolution, not the
    original grid's -- see :meth:`Figure.to_html`'s own docstring for
    exactly what that averaging costs.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # A Report entry saved with collapsed=True carries its document in
    # data-lazy-doc="..." instead of a live srcdoc="..." (see _REPORT_SCRIPT's
    # own comment on why) -- checked as a real second case by attribute name,
    # not left to the substring coincidence of a name that simply happens to
    # still contain "srcdoc=".
    if 'srcdoc="' not in text and 'data-lazy-doc="' not in text:
        figures = [{"title": None, "details": None, "axes": _load_single_figure(text),
                    "layout": _load_layout(text)}]
    else:
        figures = []
        for chunk in _split_report_entries(text):
            doc_m = (re.search(r'srcdoc="(.*?)"', chunk, re.DOTALL)
                    or re.search(r'data-lazy-doc="(.*?)"', chunk, re.DOTALL))
            if not doc_m:
                continue
            title_m = re.search(r"<h2>(.*?)</h2>", chunk, re.DOTALL)
            details_m = re.search(
                r'<p class="plotpress-report-details">(.*?)</p>', chunk, re.DOTALL)
            doc = html.unescape(doc_m.group(1))
            figures.append({
                "title": html.unescape(title_m.group(1)) if title_m else None,
                "details": html.unescape(details_m.group(1)) if details_m else None,
                "axes": _load_single_figure(doc),
                "layout": _load_layout(doc),
            })

    if by_index:
        return figures

    pairs = [(entry["title"] or f"Figure {n}", entry)
            for n, entry in enumerate(figures, start=1)]
    keyed = _dedupe_keyed(pairs, ("figure", "figures"), stacklevel=3)
    return {key: {**entry, "axes": _title_keyed_axes(entry["axes"])}
           for key, entry in keyed.items()}


def load_data_xarray(path: str, figure=None):
    """Read one figure's plotted data back as a single ``xarray.Dataset``,
    dimensioned by the figure's own axes grid (``row``/``col``, from the
    same layout :func:`load_data` already returns) instead of
    :func:`load_data`'s title-keyed dict of dicts.

    Needs the optional ``xarray`` dependency: ``pip install
    plotpress[xarray]``.

    Built for the case :doc:`/auto_examples/data_roundtrip/index` already
    showcases -- a uniform grid of same-shaped scientific measurements
    (every panel its own ``pcolormesh``, or its own single line series) --
    where a title-keyed dict of dicts is the wrong tool entirely: a caller
    wanting "the z value at row 2, column 3" has to already know that
    panel's title (or fall back to :func:`load_data`'s own
    ``by_index=True``, still just a flat list with no row/column
    structure of its own), loop over every panel by hand to stack them
    into one array, and hope no two panels happened to share a title --
    see :func:`load_data`'s own now-fixed collision handling, which this
    sidesteps structurally rather than by disambiguating: xarray indexes
    by integer row/column position, never by a string title, so there is
    no title to collide on in the first place.

    Only supports a *uniform* rectangular grid -- every axes a single,
    non-spanning cell (as :func:`plotpress.subplots`/:meth:`Figure.add_subplot`
    place them, never a row/column span from ``add_gridspec``) -- where
    every axes with data carries **exactly one** mesh (all the same shape,
    non-curvilinear) or **exactly one** line series (all the same length),
    never a mix of the two kinds, and never more than one series/mesh on a
    single axes. A cell with no axes at all, or an axes nothing was ever
    plotted on, is fine -- it comes back NaN (its ``x``/``y`` too, in the
    per-panel-coordinate case), distinguished from a panel whose real data
    legitimately happened to be all-NaN by the ``has_data`` coordinate
    below. Raises ``ValueError``, naming exactly what about the figure
    didn't fit, for anything else -- a mixed grid, a span, multiple series
    per axes, differing mesh shapes -- pointing at :func:`load_data`
    (``by_index=True`` for the title-collision-proof form) as the fallback
    for a figure this doesn't cover.

    The returned ``Dataset`` has ``row``/``col`` coordinates plus each
    panel's own ``title``/``xlabel``/``ylabel`` (``""`` for a missing
    panel) and ``has_data`` (``True`` for a grid cell an axes with plotted
    data actually occupies, ``False`` for one with no axes or nothing
    plotted) as ``(row, col)`` coordinates; a mesh grid's ``x``/``y`` are
    shared 1-D coordinates when every panel used the identical grid, else
    per-panel ``(row, col, x)``/``(row, col, y)`` arrays -- and its data
    variable is ``z``, dimensioned ``(row, col, y, x)``. A line grid's data
    variable is ``y``, dimensioned ``(row, col, point)``, with ``x`` the
    same shared-or-per-panel choice. ``.attrs`` carries the recovered
    figure's own ``figsize`` and title, plus ``"layout"`` -- the exact same
    dict :func:`load_data` returns under that key, ready to pass straight
    to :func:`subplots_from_layout` without a second, separate
    :func:`load_data` call just to get it -- ``ds.attrs["layout"]``, not a
    duplicate parse of the file.

    ``figure`` selects which figure to load from a multi-figure
    :class:`Report` file -- an int index (0-based, save order) or the
    exact string title a :class:`Report` entry was given. Left as
    ``None`` (the default), the file must have exactly one figure, or
    this raises naming how many it actually found.
    """
    try:
        import xarray as xr
    except ImportError as e:
        raise ImportError(
            "load_data_xarray() needs the optional xarray dependency -- "
            "install it with: pip install plotpress[xarray]"
        ) from e

    figures = load_data(path, by_index=True)
    if figure is None:
        if len(figures) != 1:
            raise ValueError(
                f"load_data_xarray(): this file has {len(figures)} figures, "
                "not 1 -- pass figure=<int index> or figure=<exact title "
                "str> to pick one (plotpress.load_data(path, by_index=True) "
                "lists every figure this file has, each with its own "
                "\"title\")."
            )
        entry = figures[0]
    elif isinstance(figure, int):
        try:
            entry = figures[figure]
        except IndexError:
            raise ValueError(
                f"load_data_xarray(): figure index {figure} out of range -- "
                f"this file has {len(figures)} figure(s)."
            ) from None
    else:
        matches = [f for f in figures if f["title"] == figure]
        if not matches:
            raise ValueError(
                f"load_data_xarray(): no figure titled {figure!r} in this "
                f"file -- available titles: {[f['title'] for f in figures]!r}"
            )
        entry = matches[0]

    axes = entry["axes"]   # int-indexed (this came from by_index=True above)
    layout_axes = entry["layout"].get("axes") or {}
    order = sorted(axes)
    if not order:
        raise ValueError("load_data_xarray(): this figure has no plotted axes.")
    missing_layout = [i for i in order if i not in layout_axes]
    if missing_layout:
        raise ValueError(
            f"load_data_xarray(): axes {missing_layout} have plotted data "
            "but no recorded grid cell (a freeform Figure.add_axes() rect, "
            "not a subplot grid cell) -- a uniform subplot grid is required; "
            "use plotpress.load_data() instead for this figure."
        )

    specs = [layout_axes[i] for i in order]
    if len({(s["nrows"], s["ncols"]) for s in specs}) != 1:
        raise ValueError(
            "load_data_xarray(): this figure's axes don't share one "
            "nrows x ncols grid shape -- not a uniform grid; use "
            "plotpress.load_data() instead."
        )
    if not all(s["row0"] == s["row1"] and s["col0"] == s["col1"] for s in specs):
        raise ValueError(
            "load_data_xarray(): a row/column span (from add_gridspec) is "
            "not a single grid cell -- not supported; use "
            "plotpress.load_data() instead."
        )
    nrows, ncols = specs[0]["nrows"], specs[0]["ncols"]

    # `order` is every axes the grid actually has, whether or not anything
    # was ever plotted on it (an empty axes still reports "" series/meshes/
    # pies, not an absent entry) -- `filled` narrows that to the ones with
    # real data, which is what the kind/shape checks and every data array
    # below care about. title/xlabel/ylabel below still read from `order`,
    # not `filled` -- an otherwise-empty panel can carry a real title.
    kinds = set()
    filled = []
    for i in order:
        a = axes[i]
        n_series, n_meshes, n_pies = len(a["series"]), len(a["meshes"]), len(a["pies"])
        if n_meshes == 0 and n_series == 0 and n_pies == 0:
            continue   # nothing plotted here -- a missing panel, not an error
        elif n_meshes == 1 and n_series == 0 and n_pies == 0:
            kinds.add("mesh"); filled.append(i)
        elif n_series == 1 and n_meshes == 0 and n_pies == 0:
            kinds.add("line"); filled.append(i)
        else:
            raise ValueError(
                f"load_data_xarray(): axes {i} ({a['title']!r}) has "
                f"{n_series} series, {n_meshes} mesh(es), {n_pies} pie(s) -- "
                "only a grid where every axes with data has exactly one "
                "mesh, or exactly one line series (never a mix, never more "
                "than one), is supported; use plotpress.load_data() instead."
            )
    if not filled:
        raise ValueError(
            "load_data_xarray(): this figure's grid has no plotted axes."
        )
    if len(kinds) != 1:
        raise ValueError(
            "load_data_xarray(): a mix of mesh axes and line-series axes "
            "in the same grid isn't supported; use plotpress.load_data() "
            "instead."
        )
    kind = kinds.pop()

    def grid_of(items, default="", dtype=object):
        # A cell no `items` entry ever touches (an axes with nothing
        # plotted, or no axes at all) keeps `default` rather than whatever
        # an object array happens to default-initialize to (None) --
        # title/xlabel/ylabel stay uniformly str either way, empty or not,
        # never a mix of "" and None.
        g = np.full((nrows, ncols), default, dtype=dtype)
        for i, v in items:
            s = layout_axes[i]
            g[s["row0"], s["col0"]] = v
        return g

    # True for every grid cell an axes with plotted data actually occupies,
    # False for one with no axes at all or an axes nothing was ever plotted
    # on. Missing cells stay NaN in every numeric array below too (they're
    # pre-filled with NaN, and only cells in `filled` are ever written into)
    # -- has_data is what lets a caller tell "this panel is genuinely empty"
    # apart from "this panel's own data legitimately happened to be
    # all-NaN".
    has_data = grid_of([(i, True) for i in filled], default=False, dtype=bool)

    coords = {
        "title": (("row", "col"), grid_of([(i, axes[i]["title"] or "") for i in order])),
        "xlabel": (("row", "col"), grid_of([(i, axes[i]["xlabel"] or "") for i in order])),
        "ylabel": (("row", "col"), grid_of([(i, axes[i]["ylabel"] or "") for i in order])),
        "has_data": (("row", "col"), has_data),
    }
    attrs = {"figsize": entry["layout"].get("figsize"), "title": entry["title"],
             "layout": entry["layout"]}

    if kind == "mesh":
        meshes = [axes[i]["meshes"][0] for i in filled]
        if any(m["curvilinear"] for m in meshes):
            raise ValueError(
                "load_data_xarray(): a curvilinear mesh (irregular per-cell "
                "x/y coordinates, no separable 1-D axes) isn't supported; "
                "use plotpress.load_data() instead."
            )
        shapes = {m["z"].shape for m in meshes}
        if len(shapes) != 1:
            raise ValueError(
                f"load_data_xarray(): meshes differ in shape across the "
                f"grid ({sorted(shapes)}) -- every panel must match; use "
                "plotpress.load_data() instead."
            )
        ny, nx = shapes.pop()
        # grid_of()'s own object-array shell doesn't fit here -- each cell
        # holds a whole 2-D mesh, not one scalar the way title/xlabel above
        # do -- so this one (nrows, ncols, ny, nx) float array is built
        # directly instead of routing through it.
        z = np.full((nrows, ncols, ny, nx), np.nan)
        for i, m in zip(filled, meshes):
            s = layout_axes[i]
            z[s["row0"], s["col0"], :, :] = m["z"]

        x0, y0 = meshes[0]["x"], meshes[0]["y"]
        shared = all(np.array_equal(m["x"], x0) and np.array_equal(m["y"], y0)
                    for m in meshes)
        if shared:
            coords["x"] = ("x", x0)
            coords["y"] = ("y", y0)
            data_vars = {"z": (("row", "col", "y", "x"), z)}
        else:
            # NaN-filled, not np.empty()'s uninitialized garbage -- a
            # missing cell's own x/y has no data to report either.
            X = np.full((nrows, ncols, nx), np.nan)
            Y = np.full((nrows, ncols, ny), np.nan)
            for i, m in zip(filled, meshes):
                s = layout_axes[i]
                X[s["row0"], s["col0"], :] = m["x"]
                Y[s["row0"], s["col0"], :] = m["y"]
            coords["x"] = (("row", "col", "x"), X)
            coords["y"] = (("row", "col", "y"), Y)
            data_vars = {"z": (("row", "col", "y", "x"), z)}
    else:
        series = [axes[i]["series"][0] for i in filled]
        lengths = {s["x"].size for s in series}
        if len(lengths) != 1:
            raise ValueError(
                f"load_data_xarray(): series differ in length across the "
                f"grid ({sorted(lengths)}) -- every panel must match; use "
                "plotpress.load_data() instead."
            )
        n = lengths.pop()
        y = np.full((nrows, ncols, n), np.nan)
        for i, s in zip(filled, series):
            spec = layout_axes[i]
            y[spec["row0"], spec["col0"], :] = s["y"]

        x0 = series[0]["x"]
        shared = all(np.array_equal(s["x"], x0) for s in series)
        if shared:
            coords["point"] = ("point", x0)
            data_vars = {"y": (("row", "col", "point"), y)}
        else:
            # NaN-filled, not np.empty()'s uninitialized garbage -- see the
            # matching comment in the mesh branch above.
            X = np.full((nrows, ncols, n), np.nan)
            for i, s in zip(filled, series):
                spec = layout_axes[i]
                X[spec["row0"], spec["col0"], :] = s["x"]
            coords["x"] = (("row", "col", "point"), X)
            data_vars = {"y": (("row", "col", "point"), y)}

    return xr.Dataset(data_vars, coords=coords, attrs=attrs)


def select_panel(ds, title=None, row=None, col=None, multiple=False):
    """Pull one panel out of a :func:`load_data_xarray` grid, dropping
    ``row``/``col`` entirely instead of leaving them behind as length-1
    dimensions -- ``ds.isel(row=r, col=c)`` already does exactly that for a
    scalar ``r``/``c``, which is all this is: that call, plus resolving
    ``title`` to the one ``(row, col)`` position it names.

    Pass **either** ``title`` (matched against ``ds["title"]``, the same
    string :func:`load_data`/a panel's own ``ax.set_title()`` used) **or**
    both ``row``/``col`` (plain 0-based grid position) -- not a mix of the
    two, and not neither. Raises ``ValueError`` when ``title`` matches no
    panel at all. When ``title`` matches more than one panel (two panels
    sharing a title, so there is no name left to disambiguate by), this
    raises too *unless* ``multiple=True``, which returns every match as a
    list instead of picking one.

    ``multiple=True`` always returns a ``list`` of ``Dataset``\\ s -- one
    item for a unique ``title`` or an explicit ``row=``/``col=``, or one
    per match for a duplicated ``title`` -- rather than a list only
    *sometimes* and a bare ``Dataset`` otherwise, so a caller that always
    wants to loop over the result doesn't have to branch on how many
    panels actually matched.

    Each returned ``Dataset`` keeps every data variable/coordinate
    :func:`load_data_xarray` built, just without ``row``/``col`` -- a mesh
    panel's ``z`` is ``(y, x)`` instead of ``(row, col, y, x)``, a line
    panel's ``y`` is ``(point,)`` instead of ``(row, col, point)``, and
    ``title``/``xlabel``/``ylabel``/``has_data`` come back as plain scalar
    attributes of that one panel rather than ``(row, col)`` arrays.

    ::

        ds = plotpress.load_data_xarray(path)
        panel = plotpress.select_panel(ds, title="panel 4")
        panel["z"].plot()   # a plain (y, x) DataArray, xarray's own .plot()

        # Two panels both titled "control" -- get both instead of raising.
        controls = plotpress.select_panel(ds, title="control", multiple=True)
        for p in controls:
            p["z"].plot()
    """
    if title is not None:
        if row is not None or col is not None:
            raise ValueError(
                "select_panel(): pass title=, or row=/col=, not both.")
        matches = np.argwhere(ds["title"].values == title)
        if len(matches) == 0:
            raise ValueError(
                f"select_panel(): no panel titled {title!r} -- available: "
                f"{sorted(set(ds['title'].values.ravel()))!r}"
            )
        positions = [(int(r), int(c)) for r, c in matches]
    elif row is None or col is None:
        raise ValueError("select_panel(): pass title=, or both row= and col=.")
    else:
        positions = [(row, col)]

    if len(positions) > 1 and not multiple:
        raise ValueError(
            f"select_panel(): {len(positions)} panels are titled {title!r} "
            "-- not unique, so title alone can't pick one; pass row=/col= "
            "for a specific one, or multiple=True for every match as a list."
        )
    panels = [ds.isel(row=r, col=c) for r, c in positions]
    return panels if multiple else panels[0]
