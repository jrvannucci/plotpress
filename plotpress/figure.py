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
from .axes3d import Axes3D
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


def _axes_class(projection):
    """Resolve a ``projection`` name to its Axes class."""
    if projection in (None, "rectilinear"):
        return Axes
    if projection == "polar":
        return PolarAxes
    if projection == "3d":
        return Axes3D
    raise ValueError(
        "unknown projection %r (use None, 'polar', or '3d')" % projection)


class Figure:
    def __init__(self, figsize=(6.4, 4.8), style: Style = None, facecolor=None):
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

    def group(self, title, axes, linestyle="--", color="black", linewidth=1.5,
             title_position="top", pad=8.0, fontsize=None):
        """Draw a labeled box around a set of axes -- e.g. a cluster of
        related panels in a larger grid.

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
            "title": title, "axes": list(axes),
            "linestyle": normalize_linestyle(linestyle, "group", stacklevel=3),
            "color": color, "linewidth": float(linewidth),
            "title_position": title_position, "pad": _normalize_pad(pad),
            "fontsize": fontsize,
        })
        self._layout_dirty = True
        return self

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

        ``projection='polar'`` makes it a :class:`~plotpress.polar.PolarAxes`;
        ``projection='3d'`` an :class:`~plotpress.axes3d.Axes3D`.
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
        (``'polar'`` / ``'3d'``).
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
        """
        ax.figure = self
        if ax._subplotspec is None:
            self.axes.append(ax)
            return ax
        spec = ax._subplotspec
        for i, existing in enumerate(self.axes):
            s = existing._subplotspec
            if (s is not None and s.nrows == spec.nrows and s.ncols == spec.ncols
                    and s.row0 == spec.row0 and s.row1 == spec.row1
                    and s.col0 == spec.col0 and s.col1 == spec.col1):
                self.axes[i] = ax
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

        if not squeeze:
            return grid
        if nrows == 1 and ncols == 1:
            return grid[0, 0]
        if nrows == 1 or ncols == 1:
            return grid.ravel()
        return grid

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
        from .svg import _resolve_tick_labels
        from .ticker import log_ticks, nice_ticks

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
                title_px = max(title_px, (ax._title_size or st.title_size) + 8)
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
            (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
            yt = (ax._yticks if ax._yticks is not None else
                  (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))
            # Measure the labels as drawn: explicit set_yticklabels strings are
            # usually far wider than the numbers they replace (category names),
            # and sizing the margin from the tick *values* clips them.
            ylabels = _resolve_tick_labels(ax._yticklabels, yt)
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
                    if ax._ylabel:
                        rdec += st.label_size + 6
                    right_px = max(right_px, rdec)
                else:                                        # twiny: x on the top
                    tdec = xst.tick_size + xst.tick_label_size + 4
                    if ax._xlabel:
                        tdec += st.label_size + 6
                    twin_top_px = max(twin_top_px, tdec)
                continue

            # tick_top()/tick_right() move an axes' own ticks off the default
            # bottom/left edge, so their decoration band moves with them --
            # into the same top/right bands a twin's opposite-side ticks use,
            # rather than the bottom/left band the default side would need.
            ldec = yst.tick_size + ytw + 4
            if ax._ylabel:
                ldec += st.label_size + 6
            if ax._ytick_side == "right":
                right_px = max(right_px, ldec)
            else:
                left_px = max(left_px, ldec)
            bdec = xst.tick_size + xst.tick_label_size + 4
            if ax._xlabel:
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
        # (an interior cluster) has its title in a row/col gap instead, which
        # this does not touch -- reserving hspace/wspace for one arbitrary
        # interior group would grow it for every row/col, not just that one.
        # Kept separate from left_px/top_px/etc. themselves: those also seed
        # gap_w/gap_h below (the interior row/col gap), and unlike a twin's
        # decorations -- which can genuinely sit on an interior boundary --
        # a group's title only ever faces an *outer* edge (checked below), so
        # it must never widen every interior gap along with it.
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
            if pos in ("top", "bottom"):
                # 1.3x size -- not 1x -- for the same reason title_px above
                # adds a flat +8 rather than measuring real glyph ascent:
                # bundled font metrics only cover advance widths (see
                # fonts/), not vertical extents, so this errs generous
                # rather than risk the title's own glyphs clipping the
                # canvas edge.
                side_pad = pad_t if pos == "top" else pad_b
                extent = side_pad + size * 1.3 + 10
            else:
                # A left/right title runs horizontally alongside the box, not
                # centered over it -- its own rendered *width* is what has to
                # fit in the reserved margin here, not a height allowance.
                side_pad = pad_l if pos == "left" else pad_r
                extent = side_pad + st.text_width(g["title"], size, bold=True) + 12
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
            if pos == "top" and r0 == 0:
                group_top_px += extent
            elif pos == "bottom" and r1 == nrows - 1:
                group_bottom_px += extent
            elif pos == "left" and c0 == 0:
                group_left_px += extent
            elif pos == "right" and c1 == ncols - 1:
                group_right_px += extent
            if r0 > 0:
                row_needs_hspace[r0 - 1] = True
            if r1 < nrows - 1:
                row_needs_hspace[r1] = True
            if c0 > 0:
                col_needs_wspace[c0 - 1] = True
            if c1 < ncols - 1:
                col_needs_wspace[c1] = True

        # group_spacing() grows the figure to hold its reservation instead of
        # shrinking the axes to fit it -- each boundary that actually needs
        # it (computed above) adds the requested pixels once, on top of the
        # *base* size (the one last given to the constructor or
        # set_size_inches()), so a repeated tight_layout() call re-derives
        # this fresh rather than compounding growth onto an already-grown
        # figsize.
        extra_w_px = self._group_wspace * sum(col_needs_wspace) if self._group_wspace else 0.0
        extra_h_px = self._group_hspace * sum(row_needs_hspace) if self._group_hspace else 0.0
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
        # group_spacing() is the one deliberate exception: an explicit ask
        # for more room between subplots specifically for group boxes,
        # independent of what their tick labels alone would need -- added
        # only to the boundaries that actually border a group (computed
        # above), not folded into left_px/etc. above, so it never touches
        # the outer margin those also seed.
        gap_w_list = [base_gap_w + (self._group_wspace / Wpx
                                   if needs and self._group_wspace else 0.0)
                     for needs in col_needs_wspace]
        gap_h_list = [base_gap_h + (self._group_hspace / Hpx
                                   if needs and self._group_hspace else 0.0)
                     for needs in row_needs_hspace]
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
                 if a._xlabel and not a._axis_off]
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
                 if a._ylabel and not a._axis_off]
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
               pad=0.01, fontsize=None, framealpha=0.85) -> "Figure":
        """One legend for the whole figure, drawn from labelled artists.

        The counterpart to :meth:`colorbar` over a list of axes: a grid whose
        panels all plot the same series wants one legend, not the same entries
        repeated in every panel. Labels are de-duplicated across the axes, so
        each series appears once however many panels draw it.

        ``ax`` selects which axes contribute (default: all of them).
        ``fontsize``/``framealpha`` match :meth:`Axes.legend`.

        ``loc`` names a placement in **figure** coordinates. The four outside
        placements -- ``"lower center"``, ``"upper center"``, ``"right"`` and
        ``"center left"`` (also ``"center right"``) -- reserve a band at that
        edge and shrink the subplot grid to fit, so the legend never lands on a
        plot. Any other name overlays without reserving, matching how an axes
        legend sits inside its own rect.

        Order relative to :meth:`tight_layout` does not matter -- the reservation
        is re-applied whenever the grid is reflowed.
        """
        self._figure_legend = {
            "axes": _flatten_axes(ax) if ax is not None else None,
            "loc": loc,
            "ncol": max(1, int(ncol)),
            "title": title,
            "pad": float(pad),
            "fontsize": fontsize,
            "framealpha": framealpha,
        }
        _layout_figure_legend(self)
        return self

    # -- colorbar -----------------------------------------------------------
    def colorbar(self, mappable, ax, fraction=0.05, pad=0.02) -> Axes:
        """Add a colorbar for ``mappable``.

        ``ax`` may be a single :class:`~plotpress.axes.Axes` (the colorbar
        steals space from it) or a list / array of axes (one **shared** colorbar
        spanning them all, placed on their right -- the grid is squeezed to make
        room). All the axes should share the mappable's ``vmin``/``vmax`` for the
        shared bar to describe them accurately.

        Order relative to :meth:`tight_layout` does not matter -- the steal is
        recorded and re-applied whenever the grid is reflowed.
        """
        cax = self.add_axes((0.0, 0.0, 1.0, 1.0))   # rect set by _layout_colorbar
        cax._is_colorbar = True
        cax._cbar_source = mappable
        cax._cbar_parents = _flatten_axes(ax)
        cax._cbar_fraction = float(fraction)
        cax._cbar_pad = float(pad)
        _layout_colorbar(cax)
        return cax

    # -- serialization ------------------------------------------------------
    def to_svg(self) -> str:
        return figure_to_svg(self)

    def _repr_svg_(self) -> str:
        # Static inline SVG is the Jupyter default; use to_html for interactive.
        return figure_to_svg(self)

    def to_html(self, interactive: bool = True, wait_extract: bool = False,
                pick_precision: int = 6, pick_max_mesh_cells: int = 60000,
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
        cap is block-averaged down to it rather than dropped, so a click still
        answers with a real, if coarser, value; a series over the point cap
        falls back to a geometry-only x/y readout.

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
        # flex-centering slack makes that a non-issue for a standalone page
        # (the toolbar just floats over its own top-left corner, same as it
        # always has); embedded, the SVG sits flush against the body's
        # edges, so real top/bottom padding takes over that job instead.
        if standalone:
            body_style = ("body{margin:0;background:#f5f5f5;display:flex;"
                          "justify-content:center;align-items:center;min-height:100vh}")
            wrap_display = "inline-block"   # shrink-wrapped to the SVG's own
                                             # size, so centering centers the
                                             # figure, not an oversized box
        else:
            top_pad, bottom_pad = _toolbar_clearance(
                interactive and include_default_js, len(self._sliders or {}))
            body_style = f"body{{margin:0;padding:{top_pad}px 0 {bottom_pad}px}}"
            wrap_display = "block"   # stretches to the container's full width
                                     # -- #plotpress-svg's own width:100% (below)
                                     # needs a definite (non-auto) containing
                                     # block to resolve against, or the browser
                                     # falls back to its fixed width/height
                                     # attributes instead, undoing the scaling
        svg_style = (
            "#plotpress-svg{cursor:default;box-shadow:0 1px 6px rgba(0,0,0,.2)}" if standalone
            else "#plotpress-svg{cursor:default;display:block;width:100%;height:auto}"
        )
        # A plot_frames()/pcolormesh_frames() figure wraps the SVG in a div
        # (for positioning docked sliders over it) -- position:relative in
        # both modes so a docked slider box (position:absolute inside it)
        # anchors correctly; only whether it shrink-wraps or stretches differs.
        wrap_style = f".plotpress-svg-wrap{{position:relative;line-height:0;display:{wrap_display}}}"
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

    def save(self, path: str, interactive: bool = False, scale: int = 2,
             pick_precision: int = 6, pick_max_mesh_cells: int = 60000,
             pick_max_points: int = 20000, binary_pick_data: bool = True,
             fps: int = 10, slider_unit: str = "main", label_frames: bool = True,
             include_default_js: bool = True, extra_js: str = None):
        """Save by extension: ``.svg``, ``.html``, ``.png``, ``.pdf``, or ``.gif``.

        All formats work with the standard install (PNG is a supersampled
        raster; PDF is vector). ``pick_precision``/``pick_max_mesh_cells``/
        ``pick_max_points``/``binary_pick_data``/``include_default_js``/
        ``extra_js`` apply only to interactive HTML (see :meth:`to_html`).
        ``.gif`` needs at least one :meth:`Axes.plot_frames` or
        :meth:`Axes.pcolormesh_frames` series -- it animates through that
        series' frames at ``fps``, the same data an interactive HTML slider
        scrubs through, as a self-contained looping file; ``slider_unit``
        picks which slider drives the animation for figures with more than
        one, and ``label_frames`` stamps each frame with its slider value
        since a GIF has no slider to show it on (see
        :func:`plotpress.raster.save_gif`).
        """
        lower = path.lower()
        if lower.endswith(".html") or lower.endswith(".htm"):
            content = self.to_html(interactive=interactive,
                                   pick_precision=pick_precision,
                                   pick_max_mesh_cells=pick_max_mesh_cells,
                                   pick_max_points=pick_max_points,
                                   binary_pick_data=binary_pick_data,
                                   include_default_js=include_default_js,
                                   extra_js=extra_js)
        elif lower.endswith(".svg"):
            content = self.to_svg()
        elif lower.endswith(".png"):
            from .raster import save_png
            return save_png(self, path, scale=scale)
        elif lower.endswith(".pdf"):
            from .raster import save_pdf
            return save_pdf(self, path)
        elif lower.endswith(".gif"):
            from .raster import save_gif
            return save_gif(self, path, fps=fps, scale=scale,
                           slider_unit=slider_unit, label_frames=label_frames)
        else:
            raise ValueError(
                "save() supports .svg/.html/.png/.pdf/.gif (got %r)" % path)
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
        under the Point Picking menu and no longer includes Annotation
        notes, which have no export of their own.

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
                        pick_precision: int = 6, pick_max_mesh_cells: int = 60000,
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
    from .colors import colorbar_ticks

    st = cax.style
    _, _, labels = colorbar_ticks(cax._cbar_source.norm)
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
    if spec.get("title") is not None:
        ax.set_title(spec["title"], size=spec.get("title_size"))
    if spec.get("axis_off"):
        ax.set_axis_off()
    if spec.get("xinverted"):
        ax.invert_xaxis()
    if spec.get("yinverted"):
        ax.invert_yaxis()
    if spec.get("grid"):
        ax.grid(True, alpha=spec.get("grid_alpha"))


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
    single label or title by hand. The figure's own :meth:`Figure.suptitle`/
    :meth:`~Figure.supxlabel`/:meth:`~Figure.supylabel` and background
    color come back the same way. Not carried over (real gaps, not
    oversights -- see :func:`plotpress.svg.layout_metadata`'s own
    docstring for why): colorbars, tick_params()/explicit tick overrides,
    twin/secondary/inset axes, and a custom ``Style``. An axes that had a
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
                     fontsize=g.get("fontsize"))

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
    ".plotpress-report-description{color:#555;margin:0 0 32px;max-width:70ch}"
    ".plotpress-report-entry{margin-bottom:44px}"
    ".plotpress-report-label{font-size:11px;font-weight:600;letter-spacing:.04em;"
    "text-transform:uppercase;color:#888;margin-bottom:4px}"
    ".plotpress-report-entry h2{font-size:18px;margin:0 0 4px}"
    ".plotpress-report-details{color:#555;margin:0 0 14px;max-width:70ch;"
    "white-space:pre-wrap}"
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
# aspect ratio, that means its needed height hasn't either.
_REPORT_RESIZE_JS = (
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
             pick_precision: int = 6, pick_max_mesh_cells: int = 60000,
             pick_max_points: int = 20000, binary_pick_data: bool = True) -> str:
        """Write every added figure, in order, to one self-contained HTML file.

        ``interactive`` and the ``pick_*``/``binary_pick_data`` arguments are
        forwarded to each figure's own :meth:`Figure.to_html` -- see there for
        what they mean. Every figure in the report shares the same settings;
        call :meth:`Figure.to_html` directly (and write the file yourself) for
        a mix of interactive and static figures on one page.
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
            # A starting guess only -- the resize script (_REPORT_RESIZE_JS)
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
            parts.append('<div class="plotpress-report-entry">')
            parts.append(f'<div class="plotpress-report-label">Figure {n}</div>')
            if title:
                parts.append(f"<h2>{html.escape(title)}</h2>")
            if details:
                parts.append('<p class="plotpress-report-details">'
                             f'{html.escape(details)}</p>')
            parts.append(
                f'<iframe srcdoc="{html.escape(doc)}" height="{h}" '
                f'loading="lazy" title="{iframe_title}"></iframe>')
            parts.append("</div>")
        parts.append(_REPORT_RESIZE_JS)
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
                    "vals": {name: array, ...}}, ...],
         "meshes": [{"x": array,          # 1-D cell centers (None if curvilinear)
                     "y": array,          # 1-D cell centers (None if curvilinear)
                     "z": array,          # 2-D, shape (ny, nx), row 0 = ymin
                     "extent": (xmin, xmax, ymin, ymax),
                     "curvilinear": bool}, ...],
         "pies": [...],
         "title": str | None, "xlabel": str | None, "ylabel": str | None,
         "zlabel": str | None, "xlim": (float, float) | None,
         "ylim": (float, float) | None, "xscale": str, "yscale": str}

    ``"layout"`` is the figure-level structure -- grid shape/position and
    every decoration (title, labels, limits, scale, ...) of each
    subplot-grid axes, plus any :meth:`Figure.group` boxes and the
    figure's own sup-title/label -- needed to rebuild an equivalent,
    already-labeled figure, independent of the per-axes data above::

        {"figsize": [w, h],
         "axes": {index: {"nrows": int, "ncols": int, "row0": int, "row1": int,
                          "col0": int, "col1": int,
                          "projection": "polar" | "3d" | None,
                          "title": str | None, "title_size": float | None,
                          "xlabel": str | None, "ylabel": str | None,
                          "xlim": [float, float], "ylim": [float, float],
                          "xscale": str, "yscale": str,
                          "xinverted": bool, "yinverted": bool,
                          "grid": bool, "grid_alpha": float | None,
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
    :doc:`/auto_examples/data_roundtrip/index`. Axes placed with a
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
    or capped on the way out.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    if 'srcdoc="' not in text:
        figures = [{"title": None, "details": None, "axes": _load_single_figure(text),
                    "layout": _load_layout(text)}]
    else:
        figures = []
        for chunk in _split_report_entries(text):
            srcdoc_m = re.search(r'srcdoc="(.*?)"', chunk, re.DOTALL)
            if not srcdoc_m:
                continue
            title_m = re.search(r"<h2>(.*?)</h2>", chunk, re.DOTALL)
            details_m = re.search(
                r'<p class="plotpress-report-details">(.*?)</p>', chunk, re.DOTALL)
            doc = html.unescape(srcdoc_m.group(1))
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
    every axes carries **exactly one** mesh (all the same shape,
    non-curvilinear) or **exactly one** line series (all the same length),
    never a mix of the two kinds, and never more than one series/mesh on a
    single axes. Raises ``ValueError``, naming exactly what about the
    figure didn't fit, for anything else -- a mixed grid, a span, multiple
    series per axes, differing mesh shapes -- pointing at
    :func:`load_data` (``by_index=True`` for the title-collision-proof
    form) as the fallback for a figure this doesn't cover.

    The returned ``Dataset`` has ``row``/``col`` coordinates plus each
    panel's own ``title``/``xlabel``/``ylabel`` as ``(row, col)`` string
    coordinates; a mesh grid's ``x``/``y`` are shared 1-D coordinates when
    every panel used the identical grid, else per-panel ``(row, col, x)``/
    ``(row, col, y)`` arrays -- and its data variable is ``z``, dimensioned
    ``(row, col, y, x)``. A line grid's data variable is ``y``, dimensioned
    ``(row, col, point)``, with ``x`` the same shared-or-per-panel choice.
    ``.attrs`` carries the recovered figure's own ``figsize`` and title.

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
    if len(order) != nrows * ncols:
        raise ValueError(
            f"load_data_xarray(): only {len(order)} of {nrows * ncols} grid "
            "cells have data -- every cell must be filled; use "
            "plotpress.load_data() instead for a figure with empty cells."
        )

    kinds = set()
    for i in order:
        a = axes[i]
        n_series, n_meshes, n_pies = len(a["series"]), len(a["meshes"]), len(a["pies"])
        if n_meshes == 1 and n_series == 0 and n_pies == 0:
            kinds.add("mesh")
        elif n_series == 1 and n_meshes == 0 and n_pies == 0:
            kinds.add("line")
        else:
            raise ValueError(
                f"load_data_xarray(): axes {i} ({a['title']!r}) has "
                f"{n_series} series, {n_meshes} mesh(es), {n_pies} pie(s) -- "
                "only a grid where every axes has exactly one mesh, or "
                "exactly one line series (never a mix, never more than "
                "one), is supported; use plotpress.load_data() instead."
            )
    if len(kinds) != 1:
        raise ValueError(
            "load_data_xarray(): a mix of mesh axes and line-series axes "
            "in the same grid isn't supported; use plotpress.load_data() "
            "instead."
        )
    kind = kinds.pop()

    def grid_of(values, dtype=object):
        g = np.empty((nrows, ncols), dtype=dtype)
        for i, v in zip(order, values):
            s = layout_axes[i]
            g[s["row0"], s["col0"]] = v
        return g

    coords = {
        "title": (("row", "col"), grid_of([axes[i]["title"] or "" for i in order])),
        "xlabel": (("row", "col"), grid_of([axes[i]["xlabel"] or "" for i in order])),
        "ylabel": (("row", "col"), grid_of([axes[i]["ylabel"] or "" for i in order])),
    }
    attrs = {"figsize": entry["layout"].get("figsize"), "title": entry["title"]}

    if kind == "mesh":
        meshes = [axes[i]["meshes"][0] for i in order]
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
        for i, m in zip(order, meshes):
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
            X = np.empty((nrows, ncols, nx)); Y = np.empty((nrows, ncols, ny))
            for i, m in zip(order, meshes):
                s = layout_axes[i]
                X[s["row0"], s["col0"], :] = m["x"]
                Y[s["row0"], s["col0"], :] = m["y"]
            coords["x"] = (("row", "col", "x"), X)
            coords["y"] = (("row", "col", "y"), Y)
            data_vars = {"z": (("row", "col", "y", "x"), z)}
    else:
        series = [axes[i]["series"][0] for i in order]
        lengths = {s["x"].size for s in series}
        if len(lengths) != 1:
            raise ValueError(
                f"load_data_xarray(): series differ in length across the "
                f"grid ({sorted(lengths)}) -- every panel must match; use "
                "plotpress.load_data() instead."
            )
        n = lengths.pop()
        y = np.full((nrows, ncols, n), np.nan)
        for i, s in zip(order, series):
            spec = layout_axes[i]
            y[spec["row0"], spec["col0"], :] = s["y"]

        x0 = series[0]["x"]
        shared = all(np.array_equal(s["x"], x0) for s in series)
        if shared:
            coords["point"] = ("point", x0)
            data_vars = {"y": (("row", "col", "point"), y)}
        else:
            X = np.empty((nrows, ncols, n))
            for i, s in zip(order, series):
                spec = layout_axes[i]
                X[spec["row0"], spec["col0"], :] = s["x"]
            coords["x"] = (("row", "col", "point"), X)
            data_vars = {"y": (("row", "col", "point"), y)}

    return xr.Dataset(data_vars, coords=coords, attrs=attrs)
