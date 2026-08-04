"""The Figure: the root object that owns everything needed to render itself.

There is no global "current figure" or "current axes". A figure holds its own
axes, its own :class:`~plotpress.style.Style`, and knows how to serialize itself to
SVG/HTML or show itself in a native pop-up window. Two figures never share
mutable state.
"""

from __future__ import annotations

import json
import os
import time

import numpy as np

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
    for signature familiarity with matplotlib's ``GridSpec``, but are not
    (yet) honored by :meth:`Figure.tight_layout`/:meth:`Figure.subplots_adjust`
    -- both still size one uniform grid per figure. Use
    ``fig.subplots_adjust(...)`` for margin control instead.
    """

    def __init__(self, figure, nrows, ncols, left=None, right=None, top=None,
                bottom=None, wspace=None, hspace=None):
        self.figure = figure
        self.nrows = nrows
        self.ncols = ncols
        self.left, self.right = left, right
        self.top, self.bottom = top, bottom
        self.wspace, self.hspace = wspace, hspace

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

    def text(self, x, y, s, ha="left", va="baseline", fontsize=None, color=None):
        """Draw text at figure-fraction coordinates ``(x, y)`` -- ``(0, 0)`` is
        the bottom-left corner, ``(1, 1)`` the top-right, independent of any
        axes' data coordinates.
        """
        self._fig_texts.append({
            "x": float(x), "y": float(y), "s": s, "ha": ha, "va": va,
            "size": fontsize, "color": color,
        })

    def set_size_inches(self, w, h=None):
        """Resize the figure. Accepts ``(w, h)`` or two separate arguments."""
        if h is None:
            w, h = w
        self.figsize = (float(w), float(h))
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
            ax = self.add_axes(_subplot_rect(spec.nrows, spec.ncols, placeholder),
                               projection=projection)
            ax._subplotspec = spec
            return ax
        ax = self.add_axes(_subplot_rect(nrows, ncols, index), projection=projection)
        ax._subplotspec = _cell_subplotspec(nrows, ncols, index)
        return ax

    def add_gridspec(self, nrows=1, ncols=1, **kwargs) -> GridSpec:
        """Return a :class:`GridSpec` for slicing into row/column spans.

        ``fig.add_subplot(fig.add_gridspec(2, 2)[0, :])`` spans both columns
        of the top row.
        """
        return GridSpec(self, nrows, ncols, **kwargs)

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
                ax = self.add_axes(_subplot_rect(nrows, ncols, index),
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
        Wpx = self.figsize[0] * st.dpi
        Hpx = self.figsize[1] * st.dpi
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
            (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
            yt = (ax._yticks if ax._yticks is not None else
                  (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))
            # Measure the labels as drawn: explicit set_yticklabels strings are
            # usually far wider than the numbers they replace (category names),
            # and sizing the margin from the tick *values* clips them.
            ylabels = _resolve_tick_labels(ax._yticklabels, yt)
            ytw = max((st.text_width(l, st.tick_label_size) for l in ylabels),
                      default=0.0)
            right_px = max(right_px, st.tick_label_size * 0.6)  # last x label overhang

            # A twin draws its axis on the side *opposite* its parent, so its
            # decorations belong to the other margin. Measuring them into the
            # left/bottom bands padded the wrong side and left the twin's own
            # tick labels and axis label to overflow -- off the canvas for a
            # single axes, and into the next panel for a grid.
            if ax._twin_of is not None:
                if ax._twin_shared == "x":                   # twinx: y on the right
                    rdec = st.tick_size + ytw + 4
                    if ax._ylabel:
                        rdec += st.label_size + 6
                    right_px = max(right_px, rdec)
                else:                                        # twiny: x on the top
                    tdec = st.tick_size + st.tick_label_size + 4
                    if ax._xlabel:
                        tdec += st.label_size + 6
                    twin_top_px = max(twin_top_px, tdec)
                continue

            # tick_top()/tick_right() move an axes' own ticks off the default
            # bottom/left edge, so their decoration band moves with them --
            # into the same top/right bands a twin's opposite-side ticks use,
            # rather than the bottom/left band the default side would need.
            ldec = st.tick_size + ytw + 4
            if ax._ylabel:
                ldec += st.label_size + 6
            if ax._ytick_side == "right":
                right_px = max(right_px, ldec)
            else:
                left_px = max(left_px, ldec)
            bdec = st.tick_size + st.tick_label_size + 4
            if ax._xlabel:
                bdec += st.label_size + 6
            if ax._xtick_side == "top":
                twin_top_px = max(twin_top_px, bdec)
            else:
                bottom_px = max(bottom_px, bdec)

        top_px = title_px + twin_top_px

        # Figure-level titles/labels add their own bands.
        if self._suptitle:
            top_px += (self._suptitle.get("size") or st.title_size * 1.5) + 6
        if self._supxlabel:
            bottom_px += (self._supxlabel.get("size") or st.label_size * 1.2) + 6
        if self._supylabel:
            left_px += (self._supylabel.get("size") or st.label_size * 1.2) + 6

        edge = pad * min(Wpx, Hpx) + 4
        left = (left_px + edge) / Wpx
        right = 1 - (right_px + edge) / Wpx
        bottom = (bottom_px + edge) / Hpx
        top = 1 - (top_px + edge) / Hpx
        # An interior column gap has to hold the right-hand decorations of the
        # column to its left as well as the left-hand ones of the column to its
        # right -- the row gap has always summed both bands, and a twinx in a
        # grid is what makes the missing term visible.
        gap_w = (left_px + right_px) / Wpx          # interior column gap
        gap_h = (bottom_px + top_px) / Hpx          # interior row gap
        axw, gap_w = _fit_cells(right - left, ncols, gap_w)
        axh, gap_h = _fit_cells(top - bottom, nrows, gap_h)

        _place_spec_rects(specs, nrows, ncols, left, bottom, axw, axh, gap_w, gap_h)
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

        _place_spec_rects(specs, nrows, ncols, sp["left"], sp["bottom"],
                          axw, axh, gap_w, gap_h)
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
               pad=0.01) -> "Figure":
        """One legend for the whole figure, drawn from labelled artists.

        The counterpart to :meth:`colorbar` over a list of axes: a grid whose
        panels all plot the same series wants one legend, not the same entries
        repeated in every panel. Labels are de-duplicated across the axes, so
        each series appears once however many panels draw it.

        ``ax`` selects which axes contribute (default: all of them).

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
                pick_precision: int = 6) -> str:
        """Serialize to a self-contained HTML document.

        ``pick_precision`` sets the decimal places of the embedded point-pick
        arrays (the mesh z grids dominate the file size for mesh-heavy figures);
        lower it to shrink the HTML at the cost of readout precision.
        """
        svg = figure_to_svg(self)
        # Tag the root <svg> so the JS can grab it.
        svg = svg.replace("<svg ", '<svg id="plotpress-svg" ', 1)
        script = ""
        if interactive:
            from ._interactive import INTERACTIVE_JS
            from .svg import axes_metadata, frame_data, pick_data, style_payload

            meta = _json_payload(axes_metadata(self))
            pick = _json_payload(pick_data(self, precision=pick_precision))
            styl = _json_payload(style_payload(self))
            payloads = (
                f'<script type="application/json" id="plotpress-meta">{meta}</script>'
                f'<script type="application/json" id="plotpress-pick">{pick}</script>'
                f'<script type="application/json" id="plotpress-style">{styl}</script>'
            )
            if self._sliders:
                frames = _json_payload(frame_data(self))
                sliders = _json_payload(self._sliders)
                payloads += (
                    f'<script type="application/json" id="plotpress-frames">{frames}</script>'
                    f'<script type="application/json" id="plotpress-sliders">{sliders}</script>'
                )
            config = ("<script>window.PLOTPRESS_WAIT_EXTRACT=true;</script>"
                      if wait_extract else "")
            script = config + payloads + f"<script>{INTERACTIVE_JS}</script>"
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>body{margin:0;background:#f5f5f5;display:flex;"
            "justify-content:center;align-items:center;min-height:100vh}"
            "#plotpress-svg{cursor:default;box-shadow:0 1px 6px rgba(0,0,0,.2)}"
            "</style></head><body>"
            f"{svg}{script}</body></html>"
        )

    # NB: intentionally *no* _repr_html_. Jupyter prefers text/html over
    # image/svg+xml, and returning a full interactive HTML document renders
    # messily in an output cell (and its scripts don't run there). Notebooks
    # therefore fall back to the clean static SVG above; for an interactive
    # figure in a notebook, embed to_html() in an <iframe> (see the docs).

    def save(self, path: str, interactive: bool = False, scale: int = 2,
             pick_precision: int = 6):
        """Save by extension: ``.svg``, ``.html``, ``.png``, or ``.pdf``.

        All formats work with the standard install (PNG is a supersampled
        raster; PDF is vector). ``pick_precision`` applies only to interactive
        HTML (see :meth:`to_html`).
        """
        lower = path.lower()
        if lower.endswith(".html") or lower.endswith(".htm"):
            content = self.to_html(interactive=interactive,
                                   pick_precision=pick_precision)
        elif lower.endswith(".svg"):
            content = self.to_svg()
        elif lower.endswith(".png"):
            from .raster import save_png
            return save_png(self, path, scale=scale)
        elif lower.endswith(".pdf"):
            from .raster import save_pdf
            return save_pdf(self, path)
        else:
            raise ValueError("save() supports .svg/.html/.png/.pdf (got %r)" % path)
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
        dict of values: ``x``, ``y``, any extra dims, ``axes``, ``kind``), or
        an empty list if none were extracted.

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
    """Write each axes' ``_rect`` from its ``SubplotSpec`` span and a uniform
    cell size/gap, shared by :meth:`Figure.tight_layout` and
    :meth:`Figure.subplots_adjust` (they differ only in how ``axw``/``axh``/
    ``gap_w``/``gap_h`` were derived -- measured pixels vs. matplotlib's
    fraction-of-cell ``wspace``/``hspace``).
    """
    for ax in specs:
        spec = ax._subplotspec
        x0 = left + spec.col0 * (axw + gap_w)
        x1 = left + spec.col1 * (axw + gap_w) + axw
        y0 = bottom + (nrows - 1 - spec.row1) * (axh + gap_h)
        y1 = bottom + (nrows - 1 - spec.row0) * (axh + gap_h) + axh
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
        json.dumps(obj)
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


def _fit_cells(avail, n, gap, floor=0.02):
    """Cell size and inter-cell gap that fit ``n`` cells into ``avail``.

    The gap is what the decorations need; the cell is what is left over. When a
    dense grid cannot afford both, the *gap* gives way first -- panels squeezed
    together are still readable, and the alternative was worse than ugly: the
    cell size alone was clamped to a floor while the gap kept its full width, so
    the rows ran past the top of the canvas and the first nine rows of a 30x30
    grid were simply not on the figure.

    If even the floor does not fit, the cells shrink below it rather than
    overflow. Tiny but present beats absent.
    """
    if n <= 1:
        return max(avail, 1e-4), 0.0
    cell = (avail - (n - 1) * gap) / n
    if cell >= floor:
        return cell, gap
    gap = max(0.0, (avail - n * floor) / (n - 1))
    return max((avail - (n - 1) * gap) / n, 1e-4), gap


def _subplot_rect(nrows, ncols, index):
    """Compute an axes rect for a 1-based subplot ``index`` in an NxM grid."""
    left, right, bottom, top = 0.125, 0.9, 0.11, 0.88
    wspace, hspace = 0.2, 0.2
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
