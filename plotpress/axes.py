"""The Axes object: a self-contained plotting region on a figure.

Mirrors the subset of matplotlib's ``Axes`` API needed for line, scatter, and
pcolormesh plots. Holds its own artists, limits, labels, and a reference to the
owning figure's :class:`~plotpress.style.Style` -- there is no global current-axes
state anywhere.
"""

from __future__ import annotations

import math
import warnings

import numpy as np

from .artists import (
    Annotation, AxLine, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, HLine, Image, Line2D, LineCollection, Pie,
    PolyCollection, Polygon, QuadMesh, Quiver, Rug, ScatterCollection, Span,
    Stem, Text, Violin, VLine, _VECTOR_CELL_LIMIT,
)
from .colors import Normalize, apply_colormap, get_cmap, resolve_norm
from .ticker import log_ticks, nice_ticks
from . import _spectral

#: Sentinel for ``text(transform=ax.transAxes)`` -- identity, not value, is
#: what matters (there is nothing to configure per-axes), so every axes
#: shares this one object rather than each carrying its own copy.
_TRANS_AXES = object()


def _finite_datasets(data, positions):
    """Drop non-finite values, then any dataset left with no observations.

    Each surviving dataset keeps its own position, so one empty column shifts
    nothing. Without this, ``boxplot``/``violinplot`` reach ``np.percentile``
    or ``d.min()`` on an empty array and fail well away from the caller.
    """
    positions = np.atleast_1d(np.asarray(positions, dtype=float))
    kept = [(d[np.isfinite(d)], p) for d, p in zip(data, positions)]
    kept = [(d, p) for d, p in kept if d.size]
    if not kept:
        return [], np.empty(0, dtype=float)
    return [d for d, _ in kept], np.array([p for _, p in kept], dtype=float)


def _kde_bandwidth(data):
    """Silverman's rule-of-thumb bandwidth for a 1-D sample."""
    n = data.size
    std = data.std(ddof=1) if n > 1 else 1.0
    return (1.06 * (std or 1.0) * n ** (-1 / 5)) or 1.0


# Above this many observations the exact estimator's ``(grid, n)`` intermediate
# is the bottleneck (~0.9s and 20M floats at 100k), so switch to linear binning.
# Below it, keep the exact sum so small-sample plots are unchanged to the bit.
_KDE_BINNING_MIN = 4000


def _gaussian_kde(data, grid):
    """Gaussian KDE (Silverman bandwidth) evaluated on a uniform ``grid``.

    Exact for small samples. For large ones it bins the data onto the grid and
    convolves with the kernel, which is accurate to a fraction of a percent but
    drops the cost from ``O(grid x n)`` to ``O(n) + O(grid x kernel)`` -- so a
    100k-point density is milliseconds instead of ~a second.
    """
    data = np.asarray(data, float)
    n = data.size
    bw = _kde_bandwidth(data)
    if n < _KDE_BINNING_MIN:
        u = (grid[:, None] - data[None, :]) / bw
        k = np.exp(-0.5 * u * u) / np.sqrt(2 * np.pi)
        return k.sum(axis=1) / (n * bw)
    return _binned_gaussian_kde(data, grid, bw, n)


def _binned_gaussian_kde(data, grid, bw, n):
    """KDE by linear binning + convolution, for large ``n``.

    Each observation is spread across its two bracketing grid nodes (linear
    binning -- markedly more accurate than snapping to the nearest), giving a
    weight per node. The density is then that weight array convolved with the
    Gaussian sampled on the grid spacing. Both operations are independent of the
    per-point work that made the exact estimator scale with ``n``.
    """
    lo, hi = grid[0], grid[-1]
    m = grid.size
    dx = (hi - lo) / (m - 1)

    pos = np.clip((data - lo) / dx, 0.0, m - 1)   # data lies within the grid span
    left = np.minimum(np.floor(pos).astype(np.intp), m - 2)
    frac = pos - left                             # weight going to the right node
    weights = (np.bincount(left, weights=1.0 - frac, minlength=m)
               + np.bincount(left + 1, weights=frac, minlength=m))

    half = int(np.ceil(4.0 * bw / dx))            # truncate the kernel past 4 bw
    t = np.arange(-half, half + 1) * (dx / bw)
    kernel = np.exp(-0.5 * t * t)
    # Normalize the *discrete* kernel to sum to 1 rather than using the analytic
    # constant. The two agree when the grid resolves the bandwidth, but only the
    # discrete sum keeps the density integrating to 1 when heavy-tailed outliers
    # stretch the grid so coarse that dx approaches bw.
    kernel /= kernel.sum()
    return np.convolve(weights, kernel, mode="same") / (n * dx)


class Spine:
    """One side of an axes' box outline (top/bottom/left/right).

    ``None`` for ``color``/``linewidth`` means "use the figure style's
    ``spine_color``/``spine_width``" -- matches the ``_tick_overrides``
    convention of a sentinel meaning "inherit" rather than baking the current
    style value in at construction time.
    """

    def __init__(self, axes, side):
        self._axes = axes
        self.side = side
        self._visible = True
        self._color = None
        self._linewidth = None
        self._alpha = None

    def set_visible(self, visible):
        """Show or hide this side of the box outline."""
        self._visible = bool(visible)

    def get_visible(self):
        """Whether this side of the box outline is drawn."""
        return self._visible

    def set_color(self, color):
        """Set this side's color; ``None`` reverts to the figure style's default."""
        self._color = color

    def get_color(self):
        """This side's color, falling back to the figure style's ``spine_color``."""
        return self._color if self._color is not None else self._axes.style.spine_color

    set_edgecolor = set_color
    get_edgecolor = get_color

    def set_linewidth(self, width):
        """Set this side's line width; ``None`` reverts to the figure style's default."""
        self._linewidth = width

    def get_linewidth(self):
        """This side's line width, falling back to the figure style's ``spine_width``."""
        return (self._linewidth if self._linewidth is not None
                else self._axes.style.spine_width)

    def set_alpha(self, alpha):
        """Set this side's opacity; ``None`` reverts to fully opaque."""
        self._alpha = alpha

    def get_alpha(self):
        """This side's opacity (``1.0`` unless :meth:`set_alpha` overrode it)."""
        return self._alpha if self._alpha is not None else 1.0


class Spines(dict):
    """Dict-like container of an axes' four :class:`Spine` objects."""


def _merge_share_group(a, b, attr):
    """Union two axes' share groups (post-hoc ``sharex``/``sharey``).

    Every member of both former groups must end up pointing at the *same*
    list object -- ``_resolved_limits``/``invert_xaxis`` etc. all assume that,
    so a partial reassignment would silently split the group.
    """
    ga = getattr(a, attr) or [a]
    gb = getattr(b, attr) or [b]
    merged = ga if ga is gb else list(dict.fromkeys(ga + gb))
    for ax in merged:
        setattr(ax, attr, merged)
    return merged


class Axes:
    #: Pass to ``text()``/``annotate()``'s ``transform=`` for an axes-fraction
    #: position -- ``(0, 0)`` bottom-left, ``(1, 1)`` top-right -- instead of
    #: data coordinates, e.g. a label pinned to a corner regardless of xlim/ylim.
    transAxes = _TRANS_AXES

    def __init__(self, figure, rect):
        self.figure = figure
        self.style = figure.style
        self._rect = tuple(rect)  # (left, bottom, w, h) in figure fractions

        self.artists = []
        self._xlim = None  # None => autoscale
        self._ylim = None
        self._xticks = None  # None => automatic "nice" ticks; [] => none
        self._yticks = None
        self._xticklabels = None  # None => format tick values; else explicit text
        self._yticklabels = None
        self._xinverted = False
        self._yinverted = False
        self._sharex_group = None   # list of axes sharing x limits, or None
        self._sharey_group = None
        self._twin_of = None        # parent axes when this is a twinx/twiny overlay
        self._twin_shared = None    # 'x' (twinx) or 'y' (twiny)
        self._secondary_of = None   # parent axes when this is a secondary_xaxis/yaxis
        self._secondary_dim = None  # 'x' or 'y' -- which dimension is mirrored
        self._inset_parent = None   # parent axes when this is an inset_axes
        self._inset_bounds = None   # (x0, y0, w, h) in the parent's own fractions
        self._tick_overrides = {"x": {}, "y": {}}   # per-axis tick style (Style field -> value)
        self._minor_ticks_on = False
        self._minor_tick_overrides = {"x": {}, "y": {}}
        self._xtick_side = "bottom"
        self._ytick_side = "left"
        self._xlabel = ""
        self._ylabel = ""
        self._xlabel_y_override = None   # figure pixels; set by Figure.align_xlabels
        self._ylabel_x_override = None   # figure pixels; set by Figure.align_ylabels
        self._title = ""
        self._title_size = None    # None -> the style's title_size
        self._grid = False
        self._color_idx = 0
        self._color_cycle_override = None  # per-axes prop cycle; style.color_cycle is shared

        self._xscale = "linear"
        self._yscale = "linear"
        self._aspect = None        # None='auto'; 1.0='equal'; float=y/x ratio
        self._axis_off = False
        self._visible = True
        self._facecolor = None     # None -> the style's axes_facecolor
        self._pickable = True      # False excludes this axes from Point Pick/Annotate Point
        self._pick_context = {}    # extra key/value pairs merged onto this axes' pick records
        self._xmargin = 0.05
        self._ymargin = 0.05
        self._subplotspec = None   # SubplotSpec (figure.py) for tight_layout
        self.spines = Spines((side, Spine(self, side))
                             for side in ("top", "bottom", "left", "right"))
        self._is_3d = False        # Axes3D.__init__ overrides this to True

        # Colorbar bookkeeping. On a colorbar axes, _cbar_parents/_fraction/_pad
        # record the space it stole, so tight_layout can re-apply it.
        self._is_colorbar = False
        self._cbar_source = None
        self._cbar_parents = None
        self._cbar_fraction = 0.05
        self._cbar_pad = 0.02

    # -- style / color cycle ------------------------------------------------
    def _next_color(self):
        cycle = (self._color_cycle_override if self._color_cycle_override is not None
                 else self.style.color_cycle)
        color = cycle[self._color_idx % len(cycle)]
        self._color_idx += 1
        return color

    def set_prop_cycle(self, color):
        """Set this axes' own color cycle, independent of the figure's.

        ``ax.style`` is the *same object* as ``ax.figure.style`` (not a
        per-axes copy), so this stores the override on the axes rather than
        mutating ``self.style.color_cycle`` -- that would leak the override to
        every other axes on the figure.
        """
        self._color_cycle_override = list(color)
        self._color_idx = 0

    def _resolve_color(self, color):
        """None -> next cycle color; ``'C0'``..``'CN'`` -> that cycle entry."""
        if color is None:
            return self._next_color()
        if (isinstance(color, str) and len(color) >= 2
                and color[0] in "Cc" and color[1:].isdigit()):
            cyc = self.style.color_cycle
            return cyc[int(color[1:]) % len(cyc)]
        return color

    # -- plotting methods ---------------------------------------------------
    def plot(self, *args, color=None, linewidth=None, linestyle="-",
             label=None, alpha=1.0, values=None, marker=None, markersize=None,
             markerfacecolor=None, zorder=0):
        """Plot ``y`` or ``x, y`` as a line. Returns the :class:`Line2D`.

        ``values`` is an optional ``{name: array}`` of extra per-point
        dimensions (e.g. ``z``) surfaced when a point is picked interactively.

        ``marker`` draws a dot at each vertex in addition to the line itself
        (``markersize`` in points, default matches the style's own marker
        size; ``markerfacecolor`` defaults to the line's own ``color``).
        Only round markers are drawn (see :func:`_warn_marker_shape`); any
        other ``marker`` is accepted for matplotlib compatibility but warns,
        the same limitation :meth:`scatter`/:meth:`errorbar` already have.
        """
        if len(args) == 1:
            y = np.asarray(args[0], dtype=float)
            x = np.arange(y.size, dtype=float)
        elif len(args) >= 2:
            x = np.asarray(args[0], dtype=float)
            y = np.asarray(args[1], dtype=float)
        else:
            raise TypeError("plot() requires y or x, y")

        if marker:
            _warn_marker_shape(marker, "plot")
        line = Line2D(
            x, y,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha, values=values,
            marker=marker,
            markersize=self.style.marker_size if markersize is None else markersize,
            markerfacecolor=(self._resolve_color(markerfacecolor)
                            if markerfacecolor is not None else None),
        )
        line.zorder = zorder
        self.artists.append(line)
        return line

    def scatter(self, x, y, s=None, c=None, color=None, marker="o",
                label=None, alpha=1.0, cmap="viridis", norm=None,
                vmin=None, vmax=None, values=None, zorder=0,
                edgecolors=None, linewidths=None):
        """Scatter ``y`` vs ``x``. ``c`` maps values through ``cmap``.

        ``values`` is an optional ``{name: array}`` of extra per-point
        dimensions (e.g. ``z`` or a 4th value) surfaced by point picking; the
        color dimension ``c`` is included automatically.

        ``edgecolors``/``linewidths`` outline every marker in the collection
        (one color/width for the whole call, not per-point) -- the same
        contrast marker matplotlib draws to keep overlapping same-color
        points distinguishable. Giving ``edgecolors`` with no ``linewidths``
        still draws a visible outline, at matplotlib's own default width.

        Only round markers are drawn (see :func:`_warn_marker_shape`); any other
        ``marker`` is accepted for matplotlib compatibility but warns.
        """
        _warn_marker_shape(marker, "scatter")
        if norm is None and (vmin is not None or vmax is not None):
            norm = Normalize(vmin, vmax)
        coll = ScatterCollection(
            x, y,
            s=self.style.marker_size if s is None else s,
            color=self._resolve_color(color) if c is None else None,
            marker=marker, label=label, alpha=alpha,
            c=c, cmap=cmap, norm=norm, values=values,
            edgecolors=(self._resolve_color(edgecolors)
                       if edgecolors is not None else None),
            linewidths=linewidths,
        )
        coll.zorder = zorder
        self.artists.append(coll)
        return coll

    def plot_frames(self, x, Y, slider_values=None, slider_label="frame",
                    shared=True, slider_group=None,
                    color=None, linewidth=None, linestyle="-", label=None,
                    alpha=1.0, zorder=0):
        """Plot 3-D data as a line with a slider over the extra dimension.

        ``Y`` has shape ``(n_frames, n_points)``; ``x`` is shared
        ``(n_points,)`` or per-frame ``(n_frames, n_points)``.

        Slider scope:

        * ``shared=True`` (default) -- this series joins the figure's single
          global slider, so all shared ``plot_frames`` panels scrub together.
        * ``shared=False`` -- this axes gets its own slider docked beneath it.
          Pass ``slider_group="name"`` to give several axes the same *connection
          index*: each still has its own docked slider, but the UI shows an index
          badge and a checkbox to link them so they scrub together on demand.

        ``slider_values`` labels the extra axis (defaults to ``0..n-1``).
        """
        Y = np.asarray(Y, dtype=float)
        if Y.ndim != 2:
            raise ValueError("plot_frames() requires Y with shape (n_frames, n_points)")
        art = FrameLine2D(
            x, Y,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha,
        )
        axes_index = self.figure.axes.index(self)
        if shared:
            unit, index, is_global, axes_key = "main", None, True, None
        else:
            unit = f"ax{axes_index}"
            index = slider_group if slider_group is not None else unit
            is_global, axes_key = False, axes_index
        art.slider_unit = unit
        art.zorder = zorder
        self.artists.append(art)
        self.figure._register_slider(
            unit, index, Y.shape[0], slider_values, slider_label,
            is_global, axes_key,
        )
        return art

    def pcolormesh(self, *args, cmap="viridis", norm=None, vmin=None, vmax=None,
                   shading="flat", zorder=0, alpha=1.0, label=None, rasterized=None):
        """Pseudocolor plot of a 2-D array.

        Signatures: ``pcolormesh(C)`` or ``pcolormesh(X, Y, C)``. ``X``/``Y`` may
        be 2-D for a curvilinear grid. ``shading="gouraud"`` smoothly
        interpolates the color between grid nodes instead of flat cells.
        ``alpha``/``label`` match :meth:`imshow` -- its own animated sibling
        :meth:`pcolormesh_frames` already had both; this one just hadn't
        caught up.

        A **non-uniform** rectilinear grid (cell widths that vary) normally has
        to be resampled into the SVG's one embedded raster image, which can lose
        a cell narrower than one output pixel entirely -- see
        :doc:`/auto_examples/limitations/plot_04_pcolormesh_vs_imshow`.
        ``rasterized`` controls how that grid is drawn:

        * ``None`` (default) -- automatic. A uniform grid rasterizes (its fast
          path is already a lossless, byte-identical copy, so there is nothing
          to gain from vectors). A non-uniform grid under
          :data:`~plotpress.artists._VECTOR_CELL_LIMIT` (~2000) cells draws as
          exact vector ``<rect>`` elements instead -- no resampling, so no
          cell can ever be too thin to draw. Past that cell count it falls
          back to the raster path, to keep the file size from scaling with
          cell count the way one-mark-per-point artists do.
        * ``True``/``False`` -- force raster or vector outright, overriding
          the automatic choice above (even on a uniform grid, or a huge one --
          ``False`` there warns that the SVG will scale with cell count, since
          :data:`_VECTOR_CELL_LIMIT` is only ever consulted by auto mode). A
          *curvilinear* grid (2-D ``X``/``Y``) has no vector path at all --
          its cells aren't axis-aligned rects -- so it always rasterizes and
          ``rasterized=False`` there warns that it was ignored, rather than
          silently drawing raster when exact cells were asked for.

        Either way, if the raster path ends up dropping a cell, a warning names
        it. Vector cells are an SVG/PDF-only fix -- a PNG export always takes
        the raster path regardless of this setting (a PNG is pixels by
        definition), so a mesh that vectorized fine for SVG can still drop the
        same cell if you also export it as PNG; pass ``rasterized=True`` once
        to see what that export would actually lose.

        The returned :class:`~plotpress.artists.QuadMesh` exposes the
        resolved decision for introspection: ``.rasterized`` (what you passed),
        ``.vectorized`` (what actually happened), ``.n_cells``, and
        ``.dropped_x``/``.dropped_y`` (the cell indices, if any, the raster
        path would drop along each axis -- see
        ``docs/examples/limitations/plot_05_pcolormesh_vector_cell_limit.py``
        for a worked example reading them).
        """
        if len(args) == 1:
            X = Y = None
            C = args[0]
        elif len(args) == 3:
            X, Y, C = args
        else:
            raise TypeError("pcolormesh() takes C or X, Y, C")

        mesh = QuadMesh(X, Y, C, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                        shading=shading, alpha=alpha, label=label,
                        rasterized=rasterized)
        _warn_curvilinear_ignores_vector(mesh, "pcolormesh")
        _warn_vector_mesh_size(mesh, "pcolormesh")
        if not mesh.curvilinear:
            xe, ye = mesh.cell_edges()
            _warn_dropped_cells(mesh, "pcolormesh", xe, ye, suggest_vector=True)
        mesh.zorder = zorder
        self.artists.append(mesh)
        return mesh

    def pcolormesh_frames(self, *args, slider_values=None, slider_label="frame",
                          shared=True, slider_group=None, cmap="viridis",
                          norm=None, vmin=None, vmax=None, shading="flat",
                          label=None, alpha=1.0, zorder=0):
        """Plot 4-D data as a pcolormesh with a slider over the extra dimension.

        Signatures: ``pcolormesh_frames(C)`` or ``pcolormesh_frames(X, Y, C)``,
        matching :meth:`pcolormesh` except ``C`` carries a leading frame axis --
        shape ``(n_frames, ny, nx)`` rather than ``(ny, nx)``. ``X``/``Y`` are
        shared across every frame; only the color data animates. The colour
        scale is autoscaled to every frame's data at once, so it stays fixed
        while scrubbing rather than jumping frame to frame.

        Slider scope and ``slider_values``/``slider_label`` match
        :meth:`plot_frames` exactly -- see there for ``shared``/``slider_group``.

        Unlike :meth:`pcolormesh`, this always rasterizes -- there is no
        ``rasterized`` kwarg here -- since the interactive slider scrubs by
        swapping one embedded image per frame, and per-cell vector geometry
        would need it to rewrite every cell's fill on every frame instead. A
        non-uniform grid can still silently drop a thin cell the same way a
        static mesh can; a warning names it if so.
        """
        if len(args) == 1:
            X = Y = None
            C = args[0]
        elif len(args) == 3:
            X, Y, C = args
        else:
            raise TypeError("pcolormesh_frames() takes C or X, Y, C")

        art = FrameQuadMesh(X, Y, C, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                            shading=shading, label=label, alpha=alpha)
        if not art.curvilinear:
            xe, ye = art.frames[0].cell_edges()
            _warn_dropped_cells(art, "pcolormesh_frames", xe, ye, suggest_vector=False)
        axes_index = self.figure.axes.index(self)
        if shared:
            unit, index, is_global, axes_key = "main", None, True, None
        else:
            unit = f"ax{axes_index}"
            index = slider_group if slider_group is not None else unit
            is_global, axes_key = False, axes_index
        art.slider_unit = unit
        art.zorder = zorder
        self.artists.append(art)
        self.figure._register_slider(
            unit, index, art.n_frames, slider_values, slider_label,
            is_global, axes_key,
        )
        return art

    def bar(self, x, height, width=0.8, bottom=0.0, color=None, edgecolor=None,
            linewidth=0.8, label=None, alpha=1.0, yerr=None, xerr=None,
            capsize=3.0, ecolor=None, zorder=0):
        """Vertical bar chart.

        ``yerr``/``xerr`` draw error bars centered at each bar's own top
        (``bottom + height``), composed from the same whiskers-and-caps
        :meth:`errorbar` already draws (no connecting line, no marker) --
        so they autoscale and render exactly like a standalone error bar
        would. ``ecolor`` (default black, independent of the bars' own
        ``color``) matches matplotlib's own bar-error-bar default.
        """
        b = Bars(x, height, width, bottom, "vertical",
                 color=self._resolve_color(color), edgecolor=edgecolor,
                 linewidth=linewidth, label=label, alpha=alpha)
        b.zorder = zorder
        self.artists.append(b)
        if yerr is not None or xerr is not None:
            top = b.base + b.length
            self.errorbar(b.pos, top, yerr=yerr, xerr=xerr,
                         color=self._resolve_color(ecolor) if ecolor else "#000000",
                         marker=None, markersize=0.0, linestyle="none",
                         capsize=capsize)
        return b

    def barh(self, y, width, height=0.8, left=0.0, color=None, edgecolor=None,
             linewidth=0.8, label=None, alpha=1.0, xerr=None, yerr=None,
             capsize=3.0, ecolor=None, zorder=0):
        """Horizontal bar chart. ``xerr``/``yerr``/``capsize``/``ecolor``
        match :meth:`bar`, centered at each bar's own right edge
        (``left + width``)."""
        b = Bars(y, width, height, left, "horizontal",
                 color=self._resolve_color(color), edgecolor=edgecolor,
                 linewidth=linewidth, label=label, alpha=alpha)
        b.zorder = zorder
        self.artists.append(b)
        if xerr is not None or yerr is not None:
            right = b.base + b.length
            self.errorbar(right, b.pos, yerr=yerr, xerr=xerr,
                         color=self._resolve_color(ecolor) if ecolor else "#000000",
                         marker=None, markersize=0.0, linestyle="none",
                         capsize=capsize)
        return b

    def hist(self, x, bins=10, range=None, color=None, edgecolor="#ffffff",
             label=None, alpha=1.0, density=False, zorder=0, histtype="bar",
             cumulative=False, weights=None, stacked=False):
        """Histogram. Returns ``(counts, edges, bars)``.

        ``x`` may be a single array or a sequence of arrays -- multiple
        datasets share one set of bin edges (from their combined range when
        ``bins`` is a count rather than explicit edges), overlaid by
        default or, with ``stacked=True``, stacked bottom-to-top in the
        order given. ``color``/``label`` may then be a matching list, one
        per dataset (a bare value applies to all, same as a single dataset).

        ``histtype`` is ``"bar"`` (default: filled bars with dividers
        between them), ``"step"`` (unfilled outline, no dividers) or
        ``"stepfilled"`` (filled outline, no dividers) -- matplotlib's own
        three. ``bars`` is a :class:`Bars` for ``"bar"`` (one per dataset,
        a list if there's more than one) or a :class:`Polygon` staircase
        outline for ``"step"``/``"stepfilled"``.

        ``cumulative`` running-sums each dataset's own counts left to
        right. ``weights`` (matching ``x``'s own shape, or one array per
        dataset) weights each sample instead of counting it as 1.
        """
        # A list/tuple of *arrays* is multiple datasets (boxplot's own
        # convention); a list/tuple of plain numbers -- by far the more
        # common call, e.g. hist([1, 1, 2, 3])) -- is one, same as before
        # this existed.
        multi = (isinstance(x, (list, tuple)) and len(x) > 0
                and isinstance(x[0], (list, tuple, np.ndarray)))
        datasets = [np.asarray(d, float) for d in x] if multi else [np.asarray(x, float)]
        if weights is not None and multi and isinstance(weights, (list, tuple)):
            wlist = [None if w is None else np.asarray(w, float) for w in weights]
        elif weights is not None:
            w = np.asarray(weights, float)
            wlist = [w] * len(datasets)
        else:
            wlist = [None] * len(datasets)

        # histogram_bin_edges() ignores range when bins is already a sequence
        # of edges, so this covers both "bins is a count" and "bins is
        # explicit edges" without branching on which one it is.
        combined = np.concatenate(datasets) if datasets else np.array([0.0, 1.0])
        edges = np.histogram_bin_edges(combined, bins=bins, range=range)

        all_counts = []
        for d, w in zip(datasets, wlist):
            counts, edges = np.histogram(d, bins=edges, weights=w, density=density)
            if cumulative:
                counts = np.cumsum(counts)
            all_counts.append(counts)

        colors_in = color if isinstance(color, (list, tuple)) else [color] * len(datasets)
        labels_in = label if isinstance(label, (list, tuple)) else [label] * len(datasets)
        resolved_colors = [self._resolve_color(c) for c in colors_in]

        centers = (edges[:-1] + edges[1:]) / 2.0
        widths = np.diff(edges)

        if histtype == "bar":
            bars = []
            running = np.zeros_like(edges[:-1])
            for counts, c, lbl in zip(all_counts, resolved_colors, labels_in):
                base = running.copy() if stacked else 0.0
                b = Bars(centers, counts, widths, base, "vertical",
                         color=c, edgecolor=edgecolor, linewidth=0.6,
                         label=lbl, alpha=alpha)
                b.zorder = zorder
                self.artists.append(b)
                bars.append(b)
                if stacked:
                    running = running + counts
            bars_out = bars if multi else bars[0]
        else:   # "step" / "stepfilled" -- one staircase outline per dataset
            fill = histtype == "stepfilled"
            bars = []
            running = np.zeros_like(edges[:-1])
            for counts, c, lbl in zip(all_counts, resolved_colors, labels_in):
                top = (running + counts) if stacked else counts
                base = running if stacked else np.zeros_like(counts)
                xs = np.repeat(edges, 2)
                ys = np.concatenate([[base[0]], np.repeat(top, 2), [base[-1]]])
                p = Polygon(xs, ys, color=(c if fill else None), alpha=alpha,
                           edgecolor=(edgecolor if fill else c), linewidth=1.5,
                           label=lbl)
                p.zorder = zorder
                self.artists.append(p)
                bars.append(p)
                if stacked:
                    running = top
            bars_out = bars if multi else bars[0]

        counts_out = all_counts if multi else all_counts[0]
        return counts_out, edges, bars_out

    def step(self, x, y, where="pre", color=None, linewidth=None, label=None,
             alpha=1.0):
        """Step (staircase) plot."""
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        if where == "mid":
            edges = np.concatenate([[x[0]], (x[:-1] + x[1:]) / 2, [x[-1]]])
            xs, ys = np.repeat(edges, 2)[1:-1], np.repeat(y, 2)
        elif where == "post":
            xs, ys = np.repeat(x, 2)[1:], np.repeat(y, 2)[:-1]
        else:  # 'pre'
            xs, ys = np.repeat(x, 2)[:-1], np.repeat(y, 2)[1:]
        return self.plot(xs, ys, color=self._resolve_color(color),
                         linewidth=linewidth, label=label, alpha=alpha)

    def fill_between(self, x, y1, y2=0.0, color=None, alpha=0.4, label=None,
                     edgecolor=None, linewidth=0.0, zorder=0):
        """Fill the area between ``y1`` and ``y2``.

        ``edgecolor``/``linewidth`` outline the filled region -- the same
        two options :meth:`fill` already has, since both draw the same
        closed-path primitive; there was no reason the outline was
        ``fill()``-only.
        """
        fb = FillBetween(x, y1, y2, color=self._resolve_color(color),
                         alpha=alpha, label=label, edgecolor=edgecolor,
                         linewidth=linewidth)
        fb.zorder = zorder
        self.artists.append(fb)
        return fb

    def fill_betweenx(self, y, x1, x2=0.0, color=None, alpha=0.4, label=None,
                      edgecolor=None, linewidth=0.0, zorder=0):
        """Fill the horizontal area between ``x1`` and ``x2`` across ``y``.

        ``edgecolor``/``linewidth`` match :meth:`fill_between`."""
        y = np.asarray(y, float)
        x1 = np.broadcast_to(np.asarray(x1, float), y.shape)
        x2 = np.broadcast_to(np.asarray(x2, float), y.shape)
        px = np.concatenate([x1, x2[::-1]])
        py = np.concatenate([y, y[::-1]])
        p = Polygon(px, py, color=self._resolve_color(color), alpha=alpha,
                    edgecolor=edgecolor, linewidth=linewidth, label=label)
        p.zorder = zorder
        self.artists.append(p)
        return p

    def fill(self, x, y, color=None, alpha=1.0, edgecolor=None, linewidth=0.0,
             label=None, zorder=0):
        """Fill an arbitrary polygon given by vertices ``x``/``y``."""
        p = Polygon(x, y, color=self._resolve_color(color), alpha=alpha,
                    edgecolor=edgecolor, linewidth=linewidth, label=label)
        p.zorder = zorder
        self.artists.append(p)
        return p

    def hlines(self, y, xmin, xmax, color=None, linewidth=None, linestyle="-",
               label=None, alpha=1.0, zorder=0):
        """Draw horizontal line segments at each ``y`` from ``xmin`` to ``xmax``."""
        y = np.atleast_1d(np.asarray(y, float))
        xmin = np.broadcast_to(np.asarray(xmin, float), y.shape)
        xmax = np.broadcast_to(np.asarray(xmax, float), y.shape)
        segs = np.column_stack([xmin, y, xmax, y])
        lc = LineCollection(
            segs, color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha)
        lc.zorder = zorder
        self.artists.append(lc)
        return lc

    def vlines(self, x, ymin, ymax, color=None, linewidth=None, linestyle="-",
               label=None, alpha=1.0, zorder=0):
        """Draw vertical line segments at each ``x`` from ``ymin`` to ``ymax``."""
        x = np.atleast_1d(np.asarray(x, float))
        ymin = np.broadcast_to(np.asarray(ymin, float), x.shape)
        ymax = np.broadcast_to(np.asarray(ymax, float), x.shape)
        segs = np.column_stack([x, ymin, x, ymax])
        lc = LineCollection(
            segs, color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha)
        lc.zorder = zorder
        self.artists.append(lc)
        return lc

    def stem(self, x, y=None, baseline=0.0, linecolor=None, markercolor=None,
             label=None, zorder=0):
        """Stem plot."""
        if y is None:
            y = np.asarray(x, float)
            x = np.arange(y.size, dtype=float)
        lc = self._resolve_color(linecolor)
        s = Stem(x, y, baseline, linecolor=lc,
                 markercolor=self._resolve_color(markercolor) if markercolor else lc,
                 label=label)
        s.zorder = zorder
        self.artists.append(s)
        return s

    def errorbar(self, x, y, yerr=None, xerr=None, color=None, marker="o",
                 markersize=None, capsize=3.0, linestyle="-", linewidth=None,
                 label=None, alpha=1.0, zorder=0, ecolor=None, elinewidth=None,
                 capthick=None):
        """Line/markers with error bars. Only round markers are drawn.

        ``ecolor``/``elinewidth`` style the whiskers/caps independently of
        the connecting line and marker -- each falls back to ``color``
        (resolved the same way) / ``linewidth`` if not given, so nothing
        changes unless you pass them. ``capthick`` (the caps' own width)
        falls back to ``elinewidth`` in turn.
        """
        _warn_marker_shape(marker, "errorbar")
        eb = ErrorBar(
            x, y, yerr=yerr, xerr=xerr, color=self._resolve_color(color),
            marker=marker,
            markersize=self.style.marker_size if markersize is None else markersize,
            capsize=capsize, linestyle=linestyle,
            linewidth=self.style.line_width if linewidth is None else linewidth,
            label=label, alpha=alpha,
            ecolor=self._resolve_color(ecolor) if ecolor is not None else None,
            elinewidth=elinewidth, capthick=capthick)
        eb.zorder = zorder
        self.artists.append(eb)
        return eb

    def imshow(self, X, cmap="viridis", norm=None, vmin=None, vmax=None,
               extent=None, origin="upper", alpha=1.0, label=None, zorder=0,
               interpolation="nearest"):
        """Display an image / 2-D array.

        ``interpolation="nearest"`` (default) draws each data cell as a
        crisp pixel block, however far the SVG scales it -- anything else
        (``"bilinear"``, ``"antialiased"``, ...) lets the browser smooth it
        instead. Only affects SVG output: raster (PNG/PDF) output already
        samples at its own fixed resolution, so there's no separate scaling
        step for this to change.
        """
        im = Image(X, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax, extent=extent,
                   origin=origin, alpha=alpha, label=label,
                   interpolation=interpolation)
        im.zorder = zorder
        self.artists.append(im)
        return im

    def matshow(self, A, cmap="viridis", norm=None, vmin=None, vmax=None, alpha=1.0):
        """Display a matrix as an image (origin at top, square cells)."""
        im = self.imshow(A, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                         origin="upper", alpha=alpha)
        self.set_aspect("equal")
        return im

    def spy(self, A, alpha=1.0):
        """Show the sparsity pattern of ``A`` -- nonzero entries drawn dark."""
        nz = (np.asarray(A, float) != 0).astype(float)
        im = self.imshow(nz, cmap="gray_r", origin="upper", vmin=0, vmax=1,
                         alpha=alpha)
        self.set_aspect("equal")
        return im

    def pie(self, x, labels=None, colors=None, startangle=90.0, radius=1.0,
            autopct=None, alpha=1.0, zorder=0):
        """Pie chart. Hides the axis and fixes an equal-aspect square view."""
        n = len(x)
        if colors is None:
            cyc = self.style.color_cycle
            colors = [cyc[i % len(cyc)] for i in range(n)]
        p = Pie(x, colors, labels=labels, startangle=startangle,
                radius=radius, autopct=autopct, alpha=alpha)
        p.zorder = zorder
        self.artists.append(p)
        self.set_axis_off()
        self.set_xlim(-1.3, 1.3)
        self.set_ylim(-1.3, 1.3)
        return p

    def boxplot(self, x, positions=None, widths=0.5, color=None,
                orientation="vertical", label=None, alpha=1.0, zorder=0,
                whis=1.5, showfliers=True):
        """Box-and-whisker plot of one or more datasets.

        ``whis`` sets the whisker reach in IQRs past ``q1``/``q3`` (matching
        matplotlib's own default of ``1.5``); points past that are drawn as
        fliers unless ``showfliers=False`` drops them instead.
        """
        if isinstance(x, np.ndarray) and x.ndim == 1:
            x = [x]
        data = [np.asarray(d, float) for d in x]
        if positions is None:
            positions = np.arange(1, len(data) + 1)
        data, positions = _finite_datasets(data, positions)
        stats = []
        for d in data:
            q1, med, q3 = np.percentile(d, [25, 50, 75])
            iqr = q3 - q1
            lo_in = d[d >= q1 - whis * iqr]
            hi_in = d[d <= q3 + whis * iqr]
            lo = lo_in.min() if lo_in.size else q1
            hi = hi_in.max() if hi_in.size else q3
            fliers = d[(d < lo) | (d > hi)] if showfliers else np.array([])
            stats.append({"q1": q1, "med": med, "q3": q3, "lo": lo, "hi": hi,
                          "fliers": fliers})
        b = BoxPlot(positions, stats, widths, color=self._resolve_color(color),
                    orientation=orientation, label=label, alpha=alpha)
        b.zorder = zorder
        self.artists.append(b)
        return b

    def violinplot(self, data, positions=None, widths=0.5, color=None,
                   orientation="vertical", label=None, points=100, cut=0.0,
                   inner=None, alpha=0.55, zorder=0):
        """Violin plot (kernel-density silhouettes).

        ``cut`` extends each density past its data extremes by that many
        bandwidths (seaborn's default is 2; 0 clips at the observed range).
        ``inner`` overlays a summary of the raw data inside each violin:
        ``'box'`` (IQR bar + 1.5-IQR whiskers + median dot), ``'quartile'``
        (lines across the density at Q1/median/Q3), ``'stick'`` (one line per
        observation), or ``None``.
        """
        if isinstance(data, np.ndarray) and data.ndim == 1:
            data = [data]
        data = [np.asarray(d, float) for d in data]
        if positions is None:
            positions = np.arange(1, len(data) + 1)
        data, positions = _finite_datasets(data, positions)
        grids, halfwidths = [], []
        for d in data:
            pad = cut * _kde_bandwidth(d)
            grid = np.linspace(d.min() - pad, d.max() + pad, points)
            dens = _gaussian_kde(d, grid)
            peak = dens.max() or 1.0
            grids.append(grid)
            halfwidths.append(dens / peak * (widths / 2.0))
        v = Violin(positions, grids, halfwidths,
                   color=self._resolve_color(color), orientation=orientation,
                   label=label, alpha=alpha)
        v.zorder = zorder
        self.artists.append(v)
        if inner:
            self._violin_inner(data, positions, grids, halfwidths, inner,
                               orientation)
        return v

    def _violin_inner(self, data, positions, grids, halfwidths, inner,
                      orientation):
        """Draw the inner summary marks for :meth:`violinplot`.

        Composed from existing artists (``vlines``/``hlines``/``scatter``) so
        neither backend needs to learn a new primitive.
        """
        vertical = orientation == "vertical"
        along = self.vlines if vertical else self.hlines     # spans the value axis
        across = self.hlines if vertical else self.vlines    # spans the density
        for d, p, grid, hw in zip(data, positions, grids, halfwidths):
            q1, med, q3 = np.percentile(d, [25, 50, 75])
            if inner == "box":
                iqr = q3 - q1
                lo_in = d[d >= q1 - 1.5 * iqr]
                hi_in = d[d <= q3 + 1.5 * iqr]
                lo = lo_in.min() if lo_in.size else q1
                hi = hi_in.max() if hi_in.size else q3
                along(p, lo, hi, color="#333333", linewidth=1.0)
                along(p, q1, q3, color="#333333", linewidth=5.0)
                mx, my = ([p], [med]) if vertical else ([med], [p])
                self.scatter(mx, my, s=5.0, color="#ffffff")
            elif inner == "quartile":
                for q, lw in ((q1, 0.9), (med, 1.4), (q3, 0.9)):
                    half = float(np.interp(q, grid, hw))
                    across(q, p - half, p + half, color="#ffffff",
                           linewidth=lw, linestyle="--")
            elif inner == "stick":
                half = np.interp(d, grid, hw)
                across(d, p - half, p + half, color="#ffffff", linewidth=0.6,
                       alpha=0.7)

    def kdeplot(self, data, color=None, linewidth=None, fill=False, alpha=0.3,
                points=200, cut=3.0, label=None):
        """Kernel-density estimate of a 1-D sample.

        ``cut`` extends the evaluation grid past the data extremes by that many
        bandwidths, so the tails decay to zero instead of being clipped.
        """
        d = np.asarray(data, float)
        d = d[np.isfinite(d)]
        color = self._resolve_color(color)
        if d.size == 0:      # nothing to estimate; draw nothing, like plot([])
            return self.plot([], [], color=color, linewidth=linewidth,
                             label=label)
        pad = cut * _kde_bandwidth(d)
        grid = np.linspace(d.min() - pad, d.max() + pad, points)
        dens = _gaussian_kde(d, grid)
        if fill:
            self.fill_between(grid, dens, 0.0, color=color, alpha=alpha)
        return self.plot(grid, dens, color=color, linewidth=linewidth,
                         label=label)

    def ecdfplot(self, data, color=None, linewidth=None, complementary=False,
                 label=None, alpha=1.0):
        """Empirical cumulative distribution of a 1-D sample."""
        d = np.asarray(data, float)
        d = np.sort(d[np.isfinite(d)])
        if d.size == 0:
            return self.plot([], [], color=self._resolve_color(color),
                             linewidth=linewidth, label=label, alpha=alpha)
        y = np.arange(1, d.size + 1) / d.size
        if complementary:
            y = 1.0 - y
        # Repeat the first observation so the curve starts flat at 0 (or 1).
        x = np.concatenate([d[:1], d])
        y = np.concatenate([[1.0 if complementary else 0.0], y])
        return self.step(x, y, where="post", color=color, linewidth=linewidth,
                         label=label, alpha=alpha)

    def rugplot(self, x, height=0.03, side="bottom", color=None, linewidth=1.0,
                label=None, alpha=1.0, zorder=0):
        """Tick marks at each observation along one edge of the axes.

        ``height`` is a fraction of the axes rectangle, resolved at draw time,
        so repeated rugs share a baseline and never shift the autoscale.
        ``side='left'`` rugs the y axis instead of the x axis.
        """
        d = np.asarray(x, float)
        d = d[np.isfinite(d)]
        r = Rug(d, height=height, side=side, color=self._resolve_color(color),
                linewidth=linewidth, label=label, alpha=alpha)
        r.zorder = zorder
        self.artists.append(r)
        return r

    def eventplot(self, positions, lineoffsets=None, linelengths=0.8, color=None,
                  orientation="horizontal", label=None, alpha=1.0, zorder=0):
        """Raster of event lines (one row per sequence)."""
        if np.ndim(positions[0]) == 0:
            positions = [positions]
        rows = [np.asarray(r, float) for r in positions]
        if lineoffsets is None:
            lineoffsets = np.arange(1, len(rows) + 1)
        e = EventPlot(rows, lineoffsets, linelengths, color=self._resolve_color(color),
                      orientation=orientation, label=label, alpha=alpha)
        e.zorder = zorder
        self.artists.append(e)
        return e

    def quiver(self, X, Y, U, V, scale=None, color=None, label=None, alpha=1.0,
              zorder=0):
        """Field of arrows. ``scale`` maps (U, V) to data units (auto if None)."""
        X = np.asarray(X, float); Y = np.asarray(Y, float)
        U = np.asarray(U, float); V = np.asarray(V, float)
        if scale is None:
            mag = np.hypot(U, V)
            mmax = mag.max() or 1.0
            span = max(X.max() - X.min(), Y.max() - Y.min()) or 1.0
            n = max(U.size, 1)
            scale = 0.9 * (span / np.sqrt(n)) / mmax
        q = Quiver(X, Y, U, V, scale, color=self._resolve_color(color), label=label,
                  alpha=alpha)
        q.zorder = zorder
        self.artists.append(q)
        return q

    def contour(self, *args, levels=8, colors=None, cmap="viridis", vmin=None,
                vmax=None, label=None, alpha=1.0, zorder=0):
        """Contour lines. ``contour(Z)`` or ``contour(x, y, Z)``.

        Colors (when ``colors`` isn't given explicitly) come from mapping
        each level's own *value* through ``cmap``, normalized by
        ``vmin``/``vmax`` (defaulting to ``Z``'s own min/max) -- the same
        normalization :meth:`contourf` uses, so an explicit ``vmin``/``vmax``
        colors both the same way, and non-uniform ``levels`` (e.g.
        ``[0, 1, 2, 10]``) get each level's true position on the scale,
        not just its rank among them.
        """
        if len(args) == 1:
            Z = np.asarray(args[0], float)
            x = np.arange(Z.shape[1], dtype=float)
            y = np.arange(Z.shape[0], dtype=float)
        elif len(args) == 3:
            Z = np.asarray(args[2], float)
            x, y = _rectilinear_grid(args[0], args[1], "contour")
        else:
            raise TypeError("contour() takes Z or x, y, Z")
        if np.ndim(levels) == 0:
            levels = np.linspace(Z.min(), Z.max(), int(levels) + 2)[1:-1]
        if colors is None:
            zmin = float(Z.min() if vmin is None else vmin)
            zmax = float(Z.max() if vmax is None else vmax)
            norm = Normalize(zmin, zmax)
            lut = get_cmap(cmap)
            idx = np.clip((norm(np.asarray(levels, float)) * 255).astype(int),
                         0, 255)
            colors = ["#%02x%02x%02x" % tuple(lut[i]) for i in idx]
        elif isinstance(colors, str):
            colors = [colors]
        c = Contour(x, y, Z, levels, colors, label=label, alpha=alpha)
        c.zorder = zorder
        self.artists.append(c)
        return c

    def contourf(self, *args, levels=8, cmap="viridis", vmin=None, vmax=None,
                 alpha=1.0, label=None, zorder=0):
        """Filled contours. ``contourf(Z)`` or ``contourf(x, y, Z)``.

        Rendered as a single embedded image whose colormap is *banded* (one flat
        color per level interval), so the returned value works with
        ``fig.colorbar``. ``levels`` is a band count or explicit boundaries.
        """
        if len(args) == 1:
            Z = np.asarray(args[0], float)
            x = np.arange(Z.shape[1], dtype=float)
            y = np.arange(Z.shape[0], dtype=float)
        elif len(args) == 3:
            Z = np.asarray(args[2], float)
            # contourf only needs the extent, so 2-D input never crashed here --
            # it silently drew a curvilinear field into its bounding box. Share
            # contour's check so both reject what neither can actually render.
            x, y = _rectilinear_grid(args[0], args[1], "contourf")
        else:
            raise TypeError("contourf() takes Z or x, y, Z")

        zmin = float(Z.min() if vmin is None else vmin)
        zmax = float(Z.max() if vmax is None else vmax)
        if np.ndim(levels) == 0:
            boundaries = np.linspace(zmin, zmax, int(levels) + 1)
        else:
            boundaries = np.unique(np.asarray(levels, float))
        nbands = max(len(boundaries) - 1, 1)

        base = get_cmap(cmap)
        centers = np.linspace(0, 255, nbands).astype(int)
        band_colors = base[centers]                       # (nbands, 3)
        banded = _banded_lut(band_colors, boundaries, zmin, zmax)

        fine = _bilinear_upsample(Z)
        img = Image(fine, cmap=banded, norm=Normalize(zmin, zmax),
                    extent=(float(x.min()), float(x.max()),
                            float(y.min()), float(y.max())),
                    origin="lower", alpha=alpha, label=label)
        img.zorder = zorder
        self.artists.append(img)
        return img

    def hexbin(self, x, y, gridsize=20, cmap="viridis", mincnt=1, label=None,
               norm=None, vmin=None, vmax=None, alpha=1.0, zorder=0):
        """Hexagonal 2-D binning of points ``x``/``y`` (colormapped counts).

        Returns a mappable collection of hexagons (works with ``fig.colorbar``).

        ``norm``/``vmin``/``vmax`` normalize the counts exactly as they do for
        ``pcolormesh`` and ``imshow``. Bin counts routinely span several decades
        -- a density plot's peak can hold a thousand times what its tails do --
        and a linear ramp then paints everything but the peak the same colour,
        so ``norm=LogNorm()`` is often the difference between a readable density
        map and two blobs.
        """
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        verts, counts = _hexbin(x, y, gridsize, mincnt)
        lut = get_cmap(cmap)
        norm = resolve_norm(norm, vmin, vmax)
        if len(counts):
            norm.autoscale_none(counts)
        facecolors = apply_colormap(counts, lut, norm)[:, :3] if len(counts) else []
        pc = PolyCollection(verts, facecolors, label=label, alpha=alpha)
        pc.lut, pc.norm = lut, norm      # make it a colorbar mappable
        pc.counts = counts               # picking reports the raw count per hexagon
        pc.zorder = zorder
        self.artists.append(pc)
        return pc

    def hist2d(self, x, y, bins=20, range=None, cmap="viridis", norm=None,
               vmin=None, vmax=None, alpha=1.0):
        """2-D histogram rendered as an image. Returns ``(counts, image)``.

        Takes the same ``norm``/``vmin``/``vmax`` as :meth:`hexbin`, and for the
        same reason: counts are rarely uniform enough for a linear ramp.
        """
        counts, xe, ye = np.histogram2d(np.asarray(x, float), np.asarray(y, float),
                                        bins=bins, range=range)
        # counts is (nx, ny) indexed [xbin, ybin]; image rows are y, cols x.
        im = self.imshow(counts.T, cmap=cmap, origin="lower", norm=norm,
                         vmin=vmin, vmax=vmax, alpha=alpha,
                         extent=(xe[0], xe[-1], ye[0], ye[-1]))
        return counts, im

    def stackplot(self, x, *ys, colors=None, alpha=0.8, labels=None):
        """Stacked area plot."""
        x = np.asarray(x, float)
        layers = [np.asarray(y, float) for y in ys]
        cyc = self.style.color_cycle
        base = np.zeros_like(x)
        out = []
        for i, layer in enumerate(layers):
            top = base + layer
            color = (colors[i] if colors is not None else cyc[i % len(cyc)])
            lbl = labels[i] if labels is not None else None
            out.append(self.fill_between(x, base, top, color=color, alpha=alpha,
                                         label=lbl))
            base = top
        return out

    # -- signal processing --------------------------------------------------
    # Each estimator lives in ``_spectral`` (pure NumPy); these methods only
    # compute-then-delegate to an existing artist, so no backend learns a new
    # primitive. ``window`` defaults to a Hann window; pass a callable
    # ``n -> weights`` or a length-``NFFT`` array to override.
    def psd(self, x, NFFT=256, Fs=2, noverlap=0, detrend=True, window=None,
            color=None, linewidth=None, label=None, alpha=1.0):
        """Power spectral density (Welch). Returns ``(Pxx, freqs, line)``."""
        win = np.hanning if window is None else window
        Pxx, freqs = _spectral.psd(x, NFFT, Fs, noverlap, win, detrend)
        line = self.plot(freqs, 10.0 * np.log10(Pxx), color=color,
                         linewidth=linewidth, label=label, alpha=alpha)
        self.set_xlabel("Frequency")
        self.set_ylabel("Power Spectral Density (dB/Hz)")
        return Pxx, freqs, line

    def csd(self, x, y, NFFT=256, Fs=2, noverlap=0, detrend=True, window=None,
            color=None, linewidth=None, label=None, alpha=1.0):
        """Cross spectral density magnitude. Returns ``(Pxy, freqs, line)``."""
        win = np.hanning if window is None else window
        Pxy, freqs = _spectral.csd(x, y, NFFT, Fs, noverlap, win, detrend)
        line = self.plot(freqs, 10.0 * np.log10(np.abs(Pxy)), color=color,
                         linewidth=linewidth, label=label, alpha=alpha)
        self.set_xlabel("Frequency")
        self.set_ylabel("Cross Spectral Density (dB/Hz)")
        return Pxy, freqs, line

    def cohere(self, x, y, NFFT=256, Fs=2, noverlap=0, detrend=True, window=None,
               color=None, linewidth=None, label=None, alpha=1.0):
        """Magnitude-squared coherence. Returns ``(Cxy, freqs, line)``."""
        win = np.hanning if window is None else window
        Cxy, freqs = _spectral.cohere(x, y, NFFT, Fs, noverlap, win, detrend)
        line = self.plot(freqs, Cxy, color=color, linewidth=linewidth,
                         label=label, alpha=alpha)
        self.set_xlabel("Frequency")
        self.set_ylabel("Coherence")
        return Cxy, freqs, line

    def magnitude_spectrum(self, x, Fs=2, detrend=True, window=None, scale=None,
                           color=None, linewidth=None, label=None, alpha=1.0):
        """Magnitude spectrum ``|X(f)|``. ``scale='dB'`` plots decibels.

        Returns ``(spectrum, freqs, line)``.
        """
        win = np.hanning if window is None else window
        mag, freqs = _spectral.magnitude_spectrum(x, Fs, win, detrend)
        y = 20.0 * np.log10(mag) if scale == "dB" else mag
        line = self.plot(freqs, y, color=color, linewidth=linewidth, label=label,
                         alpha=alpha)
        self.set_xlabel("Frequency")
        self.set_ylabel("Magnitude (dB)" if scale == "dB" else "Magnitude")
        return mag, freqs, line

    def angle_spectrum(self, x, Fs=2, detrend=True, window=None,
                       color=None, linewidth=None, label=None, alpha=1.0):
        """Wrapped phase spectrum (radians). Returns ``(angles, freqs, line)``."""
        win = np.hanning if window is None else window
        ang, freqs = _spectral.angle_spectrum(x, Fs, win, detrend)
        line = self.plot(freqs, ang, color=color, linewidth=linewidth,
                         label=label, alpha=alpha)
        self.set_xlabel("Frequency")
        self.set_ylabel("Angle (radians)")
        return ang, freqs, line

    def phase_spectrum(self, x, Fs=2, detrend=True, window=None,
                       color=None, linewidth=None, label=None, alpha=1.0):
        """Unwrapped phase spectrum (radians). Returns ``(phase, freqs, line)``."""
        win = np.hanning if window is None else window
        ph, freqs = _spectral.phase_spectrum(x, Fs, win, detrend)
        line = self.plot(freqs, ph, color=color, linewidth=linewidth,
                         label=label, alpha=alpha)
        self.set_xlabel("Frequency")
        self.set_ylabel("Phase (radians)")
        return ph, freqs, line

    def specgram(self, x, NFFT=256, Fs=2, noverlap=128, detrend=True,
                 window=None, cmap="viridis", norm=None, vmin=None, vmax=None,
                 alpha=1.0):
        """Spectrogram (power in dB). Returns ``(spectrum, freqs, t, image)``."""
        win = np.hanning if window is None else window
        P, freqs, t = _spectral.specgram(x, NFFT, Fs, noverlap, win, detrend)
        Z = 10.0 * np.log10(np.maximum(P, 1e-20))
        dt = (t[1] - t[0]) / 2.0 if t.size > 1 else 0.5
        df = (freqs[1] - freqs[0]) / 2.0 if freqs.size > 1 else 0.5
        im = self.imshow(Z, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                         origin="lower", alpha=alpha,
                         extent=(t[0] - dt, t[-1] + dt,
                                 freqs[0] - df, freqs[-1] + df))
        self.set_xlabel("Time")
        self.set_ylabel("Frequency")
        return P, freqs, t, im

    def xcorr(self, x, y, normed=True, detrend=False, maxlags=10, usevlines=True,
              color=None, marker="o", markersize=None, linewidth=None,
              label=None, alpha=1.0):
        """Cross-correlation of ``x`` and ``y`` over ``+-maxlags``.

        Returns ``(lags, c, lines, markers)`` where ``lines`` is the stem
        collection (``usevlines``) or connecting line, and ``markers`` is the
        dot at each lag. ``alpha`` applies to both.
        """
        lags, c = _spectral.correlation(x, y, detrend, normed, maxlags)
        col = self._resolve_color(color)
        self.axhline(0.0, color="#333333", linewidth=0.8, linestyle="-")
        if usevlines:
            lines = self.vlines(lags, 0.0, c, color=col, linewidth=linewidth,
                               alpha=alpha)
        else:
            lines = self.plot(lags, c, color=col, linewidth=linewidth, alpha=alpha)
        markers = self.scatter(lags, c, s=markersize, color=col, marker=marker,
                               label=label, alpha=alpha)
        return lags, c, lines, markers

    def acorr(self, x, **kwargs):
        """Autocorrelation -- :meth:`xcorr` of ``x`` with itself."""
        return self.xcorr(x, x, **kwargs)

    def set_xscale(self, scale):
        """Set the x-axis scale: ``'linear'`` or ``'log'``."""
        if scale not in ("linear", "log"):
            raise ValueError("scale must be 'linear' or 'log'")
        self._xscale = scale

    def set_yscale(self, scale):
        """Set the y-axis scale: ``'linear'`` or ``'log'``."""
        if scale not in ("linear", "log"):
            raise ValueError("scale must be 'linear' or 'log'")
        self._yscale = scale

    def set_aspect(self, aspect):
        """Set the axes aspect. ``'equal'`` = 1 data-unit is equal in x and y;
        ``'auto'`` fills the box (default); a number sets the y/x unit ratio.
        Implemented box-adjust: the drawn box shrinks to honor the ratio."""
        if aspect == "equal":
            self._aspect = 1.0
        elif aspect == "auto":
            self._aspect = None
        else:
            self._aspect = float(aspect)

    def semilogx(self, *args, **kwargs):
        self.set_xscale("log")
        return self.plot(*args, **kwargs)

    def semilogy(self, *args, **kwargs):
        self.set_yscale("log")
        return self.plot(*args, **kwargs)

    def loglog(self, *args, **kwargs):
        self.set_xscale("log")
        self.set_yscale("log")
        return self.plot(*args, **kwargs)

    def text(self, x, y, s, color=None, fontsize=None, ha="left", va="baseline",
             rotation=0.0, outline=None, alpha=1.0, bbox=None, zorder=0,
             fontweight="normal", fontstyle="normal", transform=None):
        """Draw text ``s`` at data coordinates ``(x, y)``.

        ``outline`` is a halo color drawn behind the glyphs so the label stays
        readable over whatever it lands on. The default picks white or black by
        the text's own luminance; pass ``False`` to switch it off, or a color to
        choose your own. It only ever helps -- on a plain background the halo is
        the background color and invisible -- and a label in the data area is
        placed before anyone knows what will end up underneath it.

        ``alpha`` fades the glyphs themselves, independent of ``bbox``'s own
        ``alpha`` (the box's fill can be more or less transparent than the text
        drawn over it).

        ``bbox`` draws a filled/bordered box behind the text instead of (or as
        well as) the ``outline`` halo -- matplotlib's ``bbox=`` dict, a subset
        of its keys: ``facecolor``/``fc`` (default white), ``edgecolor``/``ec``
        (default none), ``alpha`` (default ``1.0``), ``pad`` (pixels around the
        text, default ``4.0``), ``boxstyle`` (``"square"`` or ``"round"``), and
        ``linewidth``. Pass ``{}`` for the defaults.

        ``fontweight`` (``"normal"``/``"bold"``, or any matplotlib weight name/
        number -- ``>= 600`` counts as bold) and ``fontstyle`` (``"normal"``/
        ``"italic"``/``"oblique"``) select the glyph face; both also feed the
        width measurement ``bbox`` sizes against and the leader in
        :meth:`annotate` anchors to, so a bold or italic label still gets a
        tight box/leader rather than one sized for the regular face.

        ``s`` may contain ``\\n`` for a multi-line label -- each line is
        independently aligned per ``ha`` (matplotlib's default
        ``multialignment``), and the block as a whole is placed per ``va``
        (``"top"`` anchors the block's top edge, ``"bottom"`` its bottom edge,
        ``"center"`` its middle, ``"baseline"`` the first line's baseline).

        ``transform=ax.transAxes`` places ``(x, y)`` as an axes-fraction
        position instead of data coordinates -- ``(0, 0)`` is the axes'
        bottom-left corner, ``(1, 1)`` its top-right, regardless of the current
        xlim/ylim -- e.g. a corner label or watermark that should stay put
        under autoscaling, panning, or a data zoom::

            ax.text(0.95, 0.95, "top right", transform=ax.transAxes,
                    ha="right", va="top")
        """
        t = Text(x, y, s, color=color or self.style.text_color,
                 size=self.style.font_size if fontsize is None else fontsize,
                 ha=ha, va=va, rotation=rotation, outline=outline, alpha=alpha,
                 bbox=bbox, fontweight=fontweight, fontstyle=fontstyle,
                 axes_fraction=transform is self.transAxes)
        t.zorder = zorder
        self.artists.append(t)
        return t

    def annotate(self, text, xy, xytext=None, color=None, fontsize=None,
                 ha="left", va="baseline", arrowprops=None, outline=None,
                 alpha=1.0, bbox=None, zorder=0, fontweight="normal",
                 fontstyle="normal", textcoords=None):
        """Annotate the point ``xy`` with ``text`` placed at ``xytext``.

        Pass ``arrowprops={"color": ...}`` (or ``{}``) to draw an arrow from the
        text to ``xy``. ``arrowprops`` also accepts ``alpha``, applied to the
        arrow only -- independent of the text's own ``alpha``. The leader
        starts at the edge of the text's bounding box nearest ``xy`` --
        preferring the middle of an edge -- so it never sets off across its own
        label; with ``bbox`` set, that edge is the box's own edge, not the bare
        text's, so the leader visibly touches the box instead of stopping short
        of it. ``outline``/``alpha``/``bbox``/``fontweight``/``fontstyle``/
        multi-line ``text`` all match :meth:`text`.

        ``textcoords=ax.transAxes`` places ``xytext`` as an axes-fraction
        position -- the label sits at a fixed spot on the axes frame while its
        arrow still points at the data coordinate ``xy``, e.g. a callout
        pinned to a corner regardless of where the data it labels ends up
        after a pan or zoom. ``xy`` itself always stays data coordinates.
        """
        a = Annotation(text, xy, xytext, color=color or self.style.text_color,
                       size=self.style.font_size if fontsize is None else fontsize,
                       ha=ha, va=va, arrowprops=arrowprops, outline=outline,
                       alpha=alpha, bbox=bbox, fontweight=fontweight,
                       fontstyle=fontstyle,
                       axes_fraction=textcoords is self.transAxes)
        a.zorder = zorder
        self.artists.append(a)
        return a

    def set_axis_off(self):
        """Hide the spines, ticks, grid, and axis labels (keep the title)."""
        self._axis_off = True

    def set_axis_on(self):
        """Undo :meth:`set_axis_off`."""
        self._axis_off = False

    def axis(self, *args, **kwargs):
        """matplotlib's overloaded ``axis()`` convenience.

        ``axis('off')``/``axis('on')`` toggle the whole axis decoration;
        ``axis('equal')`` sets a 1:1 aspect ratio; ``axis([xmin, xmax, ymin,
        ymax])`` sets both limits at once; with no arguments, returns the
        current ``(xmin, xmax, ymin, ymax)``. Always returns that 4-tuple.
        """
        if args:
            arg = args[0]
            if arg == "off":
                self.set_axis_off()
            elif arg == "on":
                self.set_axis_on()
            elif arg in ("equal", "scaled"):
                self.set_aspect("equal")
            else:
                xmin, xmax, ymin, ymax = arg
                self.set_xlim(xmin, xmax)
                self.set_ylim(ymin, ymax)
        (x0, x1), (y0, y1) = self.get_xlim(), self.get_ylim()
        return (x0, x1, y0, y1)

    def set_facecolor(self, color):
        """Set this axes' own background color (independent of the figure)."""
        self._facecolor = color

    def get_facecolor(self):
        return self._facecolor if self._facecolor is not None else self.style.axes_facecolor

    def set_visible(self, visible):
        """Show/hide this axes. A hidden axes still reserves its grid cell."""
        self._visible = bool(visible)

    def get_visible(self):
        return self._visible

    def set_pickable(self, pickable=True):
        """Include or exclude this axes from Point Pick / Annotate Point.

        ``False`` makes this axes behave, for those two tools only, as if a
        click there landed outside every axes -- so restricting picking to
        one panel of a figure is ``set_pickable(False)`` on the others. Span,
        Zoom, and Annotate Free are unaffected; every axes is pickable by
        default.
        """
        self._pickable = bool(pickable)

    def get_pickable(self):
        return self._pickable

    def set_pick_context(self, **kwargs):
        """Attach extra key/value context to this axes' point-picking output.

        Every marker/annotation record extracted from this axes -- CSV/JSON
        via the toolbar's Extract panel, or ``window.plotpressGetMarkers()``
        -- carries these keys alongside its own fields, e.g.::

            ax.set_pick_context(edge_color=ax.spines["top"].get_color())

        so a click on that panel reports which one it came from by more than
        a bare index or title. A context key that collides with a structured
        field the record already sets (``x``, ``y``, ``kind``, ...) is
        ignored for that record -- the picked data always wins. Calling this
        again adds to, rather than replaces, the existing context.
        """
        self._pick_context.update(kwargs)

    def get_pick_context(self):
        return dict(self._pick_context)

    def remove(self):
        """Detach this axes from its figure.

        Also drops it from any ``sharex``/``sharey`` group it belonged to
        (those lists are shared by reference with every sibling, so removing
        from them in place -- not reassigning -- detaches from all of them at
        once). Colorbar/legend space this axes' neighbors ceded to it is not
        automatically reclaimed; call ``tight_layout()`` again for that.
        """
        if self in self.figure.axes:
            self.figure.axes.remove(self)
        if self._sharex_group is not None and self in self._sharex_group:
            self._sharex_group.remove(self)
        if self._sharey_group is not None and self in self._sharey_group:
            self._sharey_group.remove(self)

    def cla(self):
        """Reset this axes to a freshly-created state, keeping its position.

        Detaches from any ``sharex``/``sharey`` group first, using the same
        in-place-removal trick as :meth:`remove` (those lists are shared by
        reference with every sibling), since the constructor about to run
        would otherwise just drop the reference and leave the group missing
        its own member -- a cleared axes contributing no data is autoscale-
        neutral, but it would still receive a shared explicit limit from a
        sibling's ``set_xlim``/``set_ylim``.

        Re-runs the constructor (so subclasses like ``PolarAxes``/``Axes3D``
        reset their own extra state too) without duplicating the attribute
        list here, then restores the figure position and grid membership that
        the constructor doesn't know about.
        """
        if self._sharex_group is not None and self in self._sharex_group:
            self._sharex_group.remove(self)
        if self._sharey_group is not None and self in self._sharey_group:
            self._sharey_group.remove(self)
        subplotspec = self._subplotspec
        type(self).__init__(self, self.figure, self._rect)
        self._subplotspec = subplotspec

    clear = cla

    def axvline(self, x, color=None, linewidth=None, linestyle="--",
                label=None, alpha=1.0, zorder=0):
        """Draw a vertical line at data coordinate ``x`` (like matplotlib)."""
        vl = VLine(
            x,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha,
        )
        vl.zorder = zorder
        self.artists.append(vl)
        return vl

    def axline(self, xy1, xy2=None, slope=None, color=None, linewidth=None,
               linestyle="-", label=None, alpha=1.0, zorder=0):
        """Draw an infinite line through ``xy1`` (via ``slope`` or a second point).

        Spans the whole axes and does not affect autoscaling, like matplotlib.
        """
        if (xy2 is None) == (slope is None):
            raise TypeError("axline() needs exactly one of xy2 or slope")
        x1, y1 = float(xy1[0]), float(xy1[1])
        if slope is None:
            x2, y2 = float(xy2[0]), float(xy2[1])
            slope = np.inf if x2 == x1 else (y2 - y1) / (x2 - x1)
        a = AxLine(x1, y1, slope, color=self._resolve_color(color),
                   linewidth=self.style.line_width if linewidth is None else linewidth,
                   linestyle=linestyle, label=label, alpha=alpha)
        a.zorder = zorder
        self.artists.append(a)
        return a

    def broken_barh(self, xranges, yrange, color=None, alpha=1.0, label=None, zorder=0):
        """Draw a row of rectangles from ``(xstart, xwidth)`` spans at ``yrange``.

        ``yrange`` is ``(ystart, yheight)``. Handy for Gantt / timeline charts.
        """
        y0, h = float(yrange[0]), float(yrange[1])
        verts = [np.array([[x, y0], [x + w, y0], [x + w, y0 + h], [x, y0 + h]],
                          dtype=float) for x, w in xranges]
        col = self._resolve_color(color)
        pc = PolyCollection(verts, [col] * len(verts), alpha=alpha, label=label)
        pc.zorder = zorder
        self.artists.append(pc)
        return pc

    def stairs(self, values, edges=None, color=None, linewidth=None,
               linestyle="-", label=None, alpha=1.0):
        """Step outline from bin ``edges`` (len ``values`` + 1), like matplotlib."""
        values = np.asarray(values, float)
        edges = (np.arange(values.size + 1, dtype=float) if edges is None
                 else np.asarray(edges, float))
        x = np.repeat(edges, 2)[1:-1]
        y = np.repeat(values, 2)
        return self.plot(x, y, color=color, linewidth=linewidth,
                         linestyle=linestyle, label=label, alpha=alpha)

    def axhline(self, y, color=None, linewidth=None, linestyle="--",
                label=None, alpha=1.0, zorder=0):
        """Draw a horizontal line at data coordinate ``y`` (like matplotlib)."""
        hl = HLine(
            y,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha,
        )
        hl.zorder = zorder
        self.artists.append(hl)
        return hl

    def axvspan(self, xmin, xmax, color="#1f77b4", alpha=0.3, label=None, zorder=0):
        """Shade a vertical band between x=``xmin`` and x=``xmax``."""
        sp = Span(xmin, xmax, "vertical", color=color, alpha=alpha, label=label)
        sp.zorder = zorder
        self.artists.append(sp)
        return sp

    def axhspan(self, ymin, ymax, color="#1f77b4", alpha=0.3, label=None, zorder=0):
        """Shade a horizontal band between y=``ymin`` and y=``ymax``."""
        sp = Span(ymin, ymax, "horizontal", color=color, alpha=alpha, label=label)
        sp.zorder = zorder
        self.artists.append(sp)
        return sp

    # -- limits / labels ----------------------------------------------------
    def set_xlim(self, left=None, right=None):
        """Set the x limits. Returns the stored ``(left, right)``.

        Accepts ``set_xlim(lo, hi)``, ``set_xlim((lo, hi))``, or ``None`` on
        either side to autoscale just that end -- ``set_xlim(0, None)`` pins the
        left edge and lets the data decide the right. Both ``None`` clears back
        to full autoscaling.
        """
        self._xlim = _norm_limits(left, right)
        return self._xlim

    def set_ylim(self, bottom=None, top=None):
        """Set the y limits; same forms as :meth:`set_xlim`."""
        self._ylim = _norm_limits(bottom, top)
        return self._ylim

    def tick_params(self, axis="both", which="major", labelsize=None, length=None,
                    width=None, color=None, labelcolor=None):
        """Style this axes' tick marks and labels (a subset of matplotlib's).

        ``labelsize`` (tick-label font), ``length``/``width`` (tick marks),
        ``color`` (mark color), ``labelcolor`` (label color). ``axis`` selects
        ``"x"``, ``"y"``, or ``"both"`` (default) -- each axis keeps its own
        override, so ``tick_params(axis='x', color='red')`` recolors only the
        x ticks. ``which`` selects ``"major"``, ``"minor"``, or ``"both"``;
        minor ticks have no labels, so ``labelsize``/``labelcolor`` only ever
        affect major ticks.
        """
        if axis not in ("x", "y", "both"):
            raise ValueError("axis must be 'x', 'y', or 'both'")
        axes = ("x", "y") if axis == "both" else (axis,)
        for a in axes:
            if which in ("major", "both"):
                ov = self._tick_overrides[a]
                if labelsize is not None:
                    ov["tick_label_size"] = labelsize
                if length is not None:
                    ov["tick_size"] = length
                if width is not None:
                    ov["tick_width"] = width
                if color is not None:
                    ov["spine_color"] = color    # tick-mark color (box spine unchanged)
                if labelcolor is not None:
                    ov["text_color"] = labelcolor
            if which in ("minor", "both"):
                mov = self._minor_tick_overrides[a]
                if length is not None:
                    mov["tick_size"] = length
                if width is not None:
                    mov["tick_width"] = width
                if color is not None:
                    mov["spine_color"] = color
        return self

    def minorticks_on(self):
        """Draw unlabeled minor tick marks between the major ones."""
        self._minor_ticks_on = True

    def minorticks_off(self):
        self._minor_ticks_on = False

    def tick_bottom(self):
        """Draw x-axis ticks/labels along the bottom edge (the default)."""
        self._xtick_side = "bottom"

    def tick_top(self):
        """Draw x-axis ticks/labels along the top edge."""
        self._xtick_side = "top"

    def tick_left(self):
        """Draw y-axis ticks/labels along the left edge (the default)."""
        self._ytick_side = "left"

    def tick_right(self):
        """Draw y-axis ticks/labels along the right edge."""
        self._ytick_side = "right"

    def set_xbound(self, lower, upper):
        """Set the x data limits (alias of :meth:`set_xlim`)."""
        return self.set_xlim(lower, upper)

    def set_ybound(self, lower, upper):
        """Set the y data limits (alias of :meth:`set_ylim`)."""
        return self.set_ylim(lower, upper)

    def margins(self, m=None, x=None, y=None):
        """Set fractional padding around the autoscaled data (like matplotlib).

        ``margins(0.1)`` pads both axes 10%; per-axis via ``x=``/``y=``. This is
        a *persistent* setting -- unlike a one-shot ``set_xlim`` nudge, it keeps
        re-applying as the resolved data limits change (e.g. after more data is
        plotted), because it's consumed inside :func:`_pad` on every autoscale
        resolve rather than baked into ``_xlim``/``_ylim`` here.
        """
        mx = x if x is not None else m
        my = y if y is not None else m
        if mx is not None:
            self._xmargin = mx
        if my is not None:
            self._ymargin = my
        return self

    def set_xmargin(self, m):
        self._xmargin = m

    def set_ymargin(self, m):
        self._ymargin = m

    def get_xmargin(self):
        return self._xmargin

    def get_ymargin(self):
        return self._ymargin

    def autoscale(self, enable=True, axis="both", tight=None):
        """Re-enable (or freeze) autoscaling on ``axis`` (``'x'``/``'y'``/``'both'``).

        ``enable=False`` freezes the axis at its current resolved limits.
        ``tight=True`` also zeroes that axis' margin.
        """
        (x0, x1), (y0, y1) = self._resolved_limits()
        if axis in ("x", "both"):
            self._xlim = None if enable else (x0, x1)
            if tight:
                self._xmargin = 0.0
        if axis in ("y", "both"):
            self._ylim = None if enable else (y0, y1)
            if tight:
                self._ymargin = 0.0
        return self

    def set_xticks(self, ticks, labels=None):
        """Set explicit x tick locations. Pass ``[]`` to hide ticks.

        ``labels`` optionally sets the tick label strings in the same call
        (matplotlib's combined ``set_xticks(ticks, labels)`` form).
        """
        self._xticks = None if ticks is None else np.asarray(ticks, dtype=float)
        if labels is not None:
            self.set_xticklabels(labels)

    def set_yticks(self, ticks, labels=None):
        """Set explicit y tick locations. Pass ``[]`` to hide ticks.

        ``labels`` optionally sets the tick label strings in the same call
        (matplotlib's combined ``set_yticks(ticks, labels)`` form).
        """
        self._yticks = None if ticks is None else np.asarray(ticks, dtype=float)
        if labels is not None:
            self.set_yticklabels(labels)

    def set_xticklabels(self, labels):
        """Set explicit x tick label strings (pair with :meth:`set_xticks`)."""
        self._xticklabels = None if labels is None else [str(s) for s in labels]

    def set_yticklabels(self, labels):
        """Set explicit y tick label strings (pair with :meth:`set_yticks`)."""
        self._yticklabels = None if labels is None else [str(s) for s in labels]

    def invert_xaxis(self):
        """Reverse the x-axis direction (larger values to the left).

        Applies to every axes sharing this x-axis. Direction is part of a shared
        axis just as its limits are, and inverting one panel of a ``sharex``
        column while its neighbours keep counting the other way produces a grid
        that lines up numerically and reads backwards -- with no tick labels on
        the inner panels to give it away.
        """
        for ax in (self._sharex_group or [self]):
            ax._xinverted = not ax._xinverted

    def invert_yaxis(self):
        """Reverse the y-axis direction (larger values at the bottom).

        Applies to every axes sharing this y-axis; see :meth:`invert_xaxis`.
        """
        for ax in (self._sharey_group or [self]):
            ax._yinverted = not ax._yinverted

    def sharex(self, other):
        """Link this axes' x-limits/autoscale to ``other``'s, after the fact.

        Unlike ``plotpress.subplots(sharex=True)`` (set up at grid-creation
        time), this merges two already-existing axes' share groups.
        """
        _merge_share_group(self, other, "_sharex_group")

    def sharey(self, other):
        """Link this axes' y-limits/autoscale to ``other``'s, after the fact."""
        _merge_share_group(self, other, "_sharey_group")

    def label_outer(self):
        """Hide tick labels except on the bottom row / left column of its grid.

        No-op for an axes that isn't part of an ``add_subplot``/``subplots``
        grid (``_subplotspec is None``).
        """
        if self._subplotspec is None:
            return
        spec = self._subplotspec
        if spec.row1 != spec.nrows - 1:
            self.set_xticklabels([])
        if spec.col0 != 0:
            self.set_yticklabels([])

    def twinx(self):
        """Return an overlaid axes sharing this x-axis, y-axis drawn on the right."""
        tw = self.figure.add_axes(self._rect)
        tw._twin_of = self
        tw._twin_shared = "x"
        tw._subplotspec = self._subplotspec   # stay aligned through tight_layout
        return tw

    def twiny(self):
        """Return an overlaid axes sharing this y-axis, x-axis drawn on the top."""
        tw = self.figure.add_axes(self._rect)
        tw._twin_of = self
        tw._twin_shared = "y"
        tw._subplotspec = self._subplotspec
        return tw

    def secondary_xaxis(self, location="top", label=None):
        """Return an axis mirroring this axes' x-limits (same units).

        Unlike :meth:`twiny`, a secondary axis draws no data of its own -- it
        just tracks this axes' x-limits wherever they end up, drawn along
        ``location`` (``'top'`` or ``'bottom'``). Custom unit-conversion
        (matplotlib's ``functions=``) is not supported; use :meth:`twiny` if
        the second axis needs independent data.
        """
        sec = self.figure.add_axes(self._rect)
        sec._secondary_of = self
        sec._secondary_dim = "x"
        sec._xtick_side = location
        sec._subplotspec = self._subplotspec
        if label is not None:
            sec.set_xlabel(label)
        return sec

    def secondary_yaxis(self, location="right", label=None):
        """Return an axis mirroring this axes' y-limits (same units).

        See :meth:`secondary_xaxis`; ``location`` is ``'left'`` or ``'right'``.
        """
        sec = self.figure.add_axes(self._rect)
        sec._secondary_of = self
        sec._secondary_dim = "y"
        sec._ytick_side = location
        sec._subplotspec = self._subplotspec
        if label is not None:
            sec.set_ylabel(label)
        return sec

    def inset_axes(self, bounds, projection=None):
        """Add a small axes inset within this one.

        ``bounds = (x0, y0, w, h)`` are fractions of *this axes'* box, not the
        figure's -- ``[0.6, 0.6, 0.35, 0.35]`` puts a inset in the upper-right
        corner. Tracks this axes through later ``tight_layout``/
        ``subplots_adjust`` calls (it is not itself a grid member).
        """
        x0, y0, w, h = bounds
        pl, pb, pw, ph = self._rect
        rect = (pl + x0 * pw, pb + y0 * ph, w * pw, h * ph)
        ax = self.figure.add_axes(rect, projection=projection)
        ax._inset_parent = self
        ax._inset_bounds = tuple(bounds)
        return ax

    def set_position(self, pos):
        """Move this axes to an explicit ``(left, bottom, width, height)``
        (figure fractions), opting it out of grid auto-layout: a later
        ``tight_layout``/``subplots_adjust`` will no longer reposition it,
        matching matplotlib.
        """
        self._rect = tuple(float(v) for v in pos)
        self._subplotspec = None

    def get_position(self):
        """This axes' ``(left, bottom, width, height)`` in figure fractions.

        Returns the nominal rect, not the ``set_aspect``-adjusted box used at
        render time (matching matplotlib's own ``get_position()``/
        ``apply_aspect()`` split).
        """
        return self._rect

    def set_xlabel(self, xlabel):
        """Set the x-axis label."""
        self._xlabel = xlabel
        self.figure._layout_dirty = True

    def set_ylabel(self, ylabel):
        """Set the y-axis label."""
        self._ylabel = ylabel
        self.figure._layout_dirty = True

    def set_title(self, label, size=None, fontsize=None):
        """Set this axes' title. ``size`` overrides the style's title size.

        Worth having per-axes rather than only on the style: a small-multiples
        grid of several hundred panels needs a title a few points high, and the
        alternative -- a whole ``Style`` copy per figure -- changes every other
        title too. ``fontsize`` is accepted as matplotlib spells it.
        """
        self._title = label
        self._title_size = size if size is not None else fontsize
        self.figure._layout_dirty = True

    def grid(self, visible=True, alpha=None):
        """Show or hide the gridlines at the major tick positions.

        ``alpha`` overrides this axes' gridline opacity; ``None`` (the
        default) falls back to the figure style's own ``grid_alpha``, the
        same "override vs. style default" convention ``Spine`` and the
        per-axes tick overrides already use.
        """
        self._grid = bool(visible)
        self._grid_alpha = alpha

    def legend(self, loc="upper right", ncol=1, title=None, handles=None,
               labels=None, fontsize=None, framealpha=0.85):
        """Enable a legend (by default, drawn from artists that have a
        ``label``).

        ``loc`` is a matplotlib-style corner/edge name (e.g. ``"upper left"``,
        ``"lower center"``, ``"center"``; ``"best"`` maps to upper right).
        ``ncol`` lays the entries out in that many columns; ``title`` adds a
        heading row. ``fontsize`` overrides the entry/title text size
        (default: the style's own tick label size). ``framealpha`` is the
        legend box's own background opacity (matplotlib's default is ``0.8``;
        ``0.85`` matches what this box already drew before the value was
        configurable).

        ``handles`` overrides which artists appear -- any plotpress artist
        (from this axes, another, or never added to one at all), in the
        order given, regardless of their own ``label``. Pair with
        ``labels`` to also override the text shown for each, positionally;
        without it, each handle's own ``label`` is used.
        """
        self._show_legend = True
        self._legend_loc = loc
        self._legend_ncol = max(1, int(ncol))
        self._legend_title = title
        self._legend_fontsize = fontsize
        self._legend_framealpha = framealpha
        if handles is not None:
            handles = list(handles)
            if labels is not None:
                for h, lbl in zip(handles, labels):
                    h.label = lbl
        self._legend_handles = handles

    _show_legend = False
    _legend_loc = "upper right"
    _legend_ncol = 1
    _legend_title = None
    _legend_fontsize = None
    _legend_framealpha = 0.85
    _legend_handles = None
    _grid_alpha = None

    # -- autoscaling --------------------------------------------------------
    def get_xlim(self):
        return self._resolved_limits()[0]

    def get_ylim(self):
        return self._resolved_limits()[1]

    def get_xlabel(self):
        return self._xlabel

    def get_ylabel(self):
        return self._ylabel

    def get_title(self):
        return self._title

    def get_xscale(self):
        return self._xscale

    def get_yscale(self):
        return self._yscale

    def get_xticks(self):
        """The resolved x tick locations (explicit if set, else auto "nice" ticks)."""
        (xmin, xmax), _ = self._resolved_limits()
        if self._xticks is not None:
            return self._xticks
        return log_ticks(xmin, xmax) if self._xscale == "log" else nice_ticks(xmin, xmax)

    def get_yticks(self):
        """The resolved y tick locations (explicit if set, else auto "nice" ticks)."""
        _, (ymin, ymax) = self._resolved_limits()
        if self._yticks is not None:
            return self._yticks
        return log_ticks(ymin, ymax) if self._yscale == "log" else nice_ticks(ymin, ymax)

    @staticmethod
    def _group_bounds(axes_list, ix):
        """Data (lo, hi) for dimension ``ix`` (0=x, 2=y) across a set of axes."""
        lo, hi, has_mesh = np.inf, -np.inf, False
        for ax in axes_list:
            for a in ax.artists:
                b = a.data_bounds()
                if b is None:
                    continue
                if np.isfinite(b[ix]):
                    lo = min(lo, b[ix])
                if np.isfinite(b[ix + 1]):
                    hi = max(hi, b[ix + 1])
            has_mesh = has_mesh or any(isinstance(a, (QuadMesh, Image))
                                       for a in ax.artists)
        if not np.isfinite(lo) or not np.isfinite(hi):
            lo, hi = 0.0, 1.0
        return lo, hi, has_mesh

    def _resolved_limits(self):
        """Return ``((xmin, xmax), (ymin, ymax))``, autoscaling if unset.

        With ``sharex``/``sharey`` the autoscale spans every axes in the share
        group, *and* an explicit ``set_xlim`` on any member applies to them all.
        Sharing only the autoscale was not enough: calling ``set_xlim`` on one
        panel of a ``sharex=True`` column moved that panel alone, so the grid
        silently came apart along the axis it was built to share -- and the
        panels whose ticks are hidden are exactly the ones where the reader
        cannot see it happen.

        A secondary axis has no data of its own and mirrors *both* of its
        parent's dimensions wholesale, regardless of which one it actually
        draws -- there is nothing of its own to reconcile against.
        """
        if self._secondary_of is not None:
            return self._secondary_of._resolved_limits()
        xgroup = self._sharex_group or [self]
        ygroup = self._sharey_group or [self]
        xlim = _group_limits(self, xgroup, "_xlim")
        ylim = _group_limits(self, ygroup, "_ylim")
        if _both_set(xlim) and _both_set(ylim):
            return xlim, ylim

        axmin, axmax, mesh_x = self._group_bounds(xgroup, 0)
        aymin, aymax, mesh_y = self._group_bounds(ygroup, 2)
        px = _pad(axmin, axmax, self._xscale, tight=mesh_x, frac=self._xmargin)
        py = _pad(aymin, aymax, self._yscale, tight=mesh_y, frac=self._ymargin)
        # A one-sided limit takes the autoscaled value for the end left open.
        rx, ry = _fill_limits(xlim, px), _fill_limits(ylim, py)
        # A twin overlay inherits the shared axis' limits from its parent.
        if self._twin_of is not None:
            pxl, pyl = self._twin_of._resolved_limits()
            if self._twin_shared == "x":
                rx = pxl
            else:
                ry = pyl
        return rx, ry


def _rectilinear_grid(x, y, who):
    """1-D coordinate vectors from ``contour``-style ``x``/``y`` input.

    ``meshgrid`` output is accepted, because passing the same ``X``/``Y`` to
    ``pcolormesh`` and to ``contour`` is the natural way to draw isolines over a
    field -- and ``pcolormesh`` genuinely wants the 2-D form. Marching squares
    walks a rectilinear grid, though, so a truly curvilinear ``X``/``Y`` cannot
    be honored: say so here rather than drawing something subtly wrong.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.ndim == 2:
        # meshgrid("xy") repeats the x vector down every row, and the y vector
        # across every column.
        if not np.allclose(x, x[:1], equal_nan=True):
            raise ValueError(
                f"{who}() needs a rectilinear grid, but every row of x differs. "
                "Use pcolormesh for a curvilinear mesh.")
        x = x[0]
    if y.ndim == 2:
        if not np.allclose(y, y[:, :1], equal_nan=True):
            raise ValueError(
                f"{who}() needs a rectilinear grid, but every column of y differs. "
                "Use pcolormesh for a curvilinear mesh.")
        y = y[:, 0]
    return x, y


def _bilinear_upsample(Z, max_side=480):
    """Bilinearly upsample a 2-D grid so filled bands get smooth boundaries."""
    ny, nx = Z.shape
    f = max(1, min(8, max_side // max(ny, nx, 1)))
    if f == 1:
        return Z
    yi = np.linspace(0, ny - 1, ny * f)
    xi = np.linspace(0, nx - 1, nx * f)
    y0 = np.floor(yi).astype(int); y1 = np.minimum(y0 + 1, ny - 1); ty = yi - y0
    x0 = np.floor(xi).astype(int); x1 = np.minimum(x0 + 1, nx - 1); tx = xi - x0
    top = Z[np.ix_(y0, x0)] * (1 - tx) + Z[np.ix_(y0, x1)] * tx
    bot = Z[np.ix_(y1, x0)] * (1 - tx) + Z[np.ix_(y1, x1)] * tx
    return top * (1 - ty)[:, None] + bot * ty[:, None]


def _banded_lut(band_colors, boundaries, zmin, zmax):
    """256-entry LUT that snaps each colormap slot to its level-band color."""
    slot_vals = np.linspace(zmin, zmax, 256)
    band = np.clip(np.searchsorted(boundaries, slot_vals, side="right") - 1,
                   0, len(band_colors) - 1)
    return band_colors[band].astype(np.uint8)


def _hexbin(x, y, gridsize, mincnt):
    """Assign points to a hexagonal lattice; return (hex_vertices, counts).

    Uses the classic two-interleaved-grid method: each point goes to whichever
    of the two candidate centers (rectangular grid, and the same grid shifted by
    half a cell) is nearest -- which tiles the plane with hexagons.

    The row count follows only ``gridsize``, as matplotlib's does, so the
    hexagons come out regular in *fractional axes* space and therefore on
    screen. Deriving it from the ratio of the data ranges instead made the bin
    count scale with the choice of units: wind speed against power, in m/s and
    kW, asked for three thousand rows across the axes and drew every bin as a
    sub-pixel dash.
    """
    if x.size == 0 or y.size == 0:
        return [], np.empty(0, dtype=float)
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    nx = max(int(gridsize), 1)
    ny = max(int(nx / 1.732), 1)
    dx = (xmax - xmin) / nx or 1.0
    dy = (ymax - ymin) / ny or 1.0

    sx = (x - xmin) / dx
    sy = (y - ymin) / dy
    i1 = np.round(sx).astype(int); j1 = np.round(sy).astype(int)      # grid 1
    i2 = np.floor(sx).astype(int); j2 = np.floor(sy).astype(int)      # grid 2 (+half)
    d1 = (sx - i1) ** 2 + (sy - j1) ** 2
    d2 = (sx - (i2 + 0.5)) ** 2 + (sy - (j2 + 0.5)) ** 2
    use1 = d1 <= d2

    # Each point lands on grid 1 (g=0) or the half-shifted grid 2 (g=1); tally
    # the (i, j, g) cells with a single vectorized unique-with-counts, not a
    # per-point Python loop.
    gi = np.where(use1, i1, i2)
    gj = np.where(use1, j1, j2)
    gg = np.where(use1, 0, 1)
    cells, cell_counts = np.unique(np.stack([gi, gj, gg], axis=1), axis=0,
                                   return_counts=True)

    # Hexagon vertex offsets (pointy-top), scaled to the cell size.
    ang = np.pi / 180 * (60 * np.arange(6) + 30)
    hx = (dx / 1.732) * np.cos(ang)
    hy = (dy / 1.5) * np.sin(ang)

    verts, counts = [], []
    for (i, j, g), c in zip(cells, cell_counts):
        if c < mincnt:
            continue
        cx = xmin + i * dx + (dx / 2 if g else 0)
        cy = ymin + j * dy + (dy / 2 if g else 0)
        verts.append(np.column_stack([cx + hx, cy + hy]))
        counts.append(c)
    return verts, np.asarray(counts, float)


def _norm_limits(lower, upper):
    """Normalize ``set_xlim``/``set_ylim`` arguments to a stored limit pair.

    Returns ``(lo, hi)`` with either entry ``None`` to mean "autoscale this
    end", or ``None`` for the whole pair when neither end is pinned. Accepting a
    ``None`` here rather than storing it verbatim is what keeps a half-set limit
    from reaching the transform, where it used to surface as a bare
    ``float(None)`` TypeError at render time.
    """
    if upper is None and lower is not None and np.ndim(lower) != 0:
        lower, upper = lower                      # a single (lo, hi) sequence
    lo = None if lower is None else float(lower)
    hi = None if upper is None else float(upper)
    return None if lo is None and hi is None else (lo, hi)


#: Marker specifications that render as drawn. Markers are emitted as
#: zero-length round-capped strokes so they keep a constant pixel size under the
#: interactive zoom's group transform (see ``svg._emit_markers``); a polygonal
#: marker would have to scale with the zoom, which is worse than being round.
_ROUND_MARKERS = frozenset({"o", ".", "", None})


def _warn_marker_shape(marker, who):
    """Warn that a non-round ``marker`` will still be drawn as a dot.

    ``marker`` is accepted for matplotlib compatibility, but only the round
    shapes are rendered. Silently drawing a circle where the caller asked for a
    cross is the worst option: shape often carries meaning -- censored versus
    observed, pass versus fail -- and a figure that quietly collapses that
    distinction is wrong in a way nothing on the page reveals.
    """
    if marker not in _ROUND_MARKERS:
        warnings.warn(
            f"{who}(marker={marker!r}) is not drawn: plotpress renders round "
            "markers only, so this will appear as a dot. Distinguish the series "
            "by color, size or a label instead.",
            UserWarning, stacklevel=3)


def _warn_vector_mesh_size(mesh, who):
    """Warn that ``rasterized=False`` was forced on a mesh too big to vectorize cheaply.

    Only fires when the caller explicitly forced vector rendering past
    :data:`_VECTOR_CELL_LIMIT` -- auto mode (``rasterized=None``) never picks
    vector above the limit in the first place, so this can't fire from it.
    """
    if mesh.vectorized and mesh.n_cells is not None and mesh.n_cells > _VECTOR_CELL_LIMIT:
        warnings.warn(
            f"{who}(rasterized=False) on {mesh.n_cells} cells will emit up to "
            f"{mesh.n_cells} SVG <rect> elements (fewer if some cells are NaN). "
            "Pass rasterized=True (or leave rasterized=None) to keep this an "
            "embedded image instead.",
            UserWarning, stacklevel=3)


def _warn_curvilinear_ignores_vector(mesh, who):
    """Warn that an explicit ``rasterized=False`` was silently dropped.

    A curvilinear grid has no vector path here (see
    ``artists._resolve_mesh_render``) -- its cells aren't axis-aligned rects
    -- so it always rasterizes regardless of what was asked for. Without this,
    a caller relying on ``rasterized=False`` to keep a thin curvilinear cell
    from vanishing gets silently downgraded to the very raster path they
    tried to opt out of.
    """
    if mesh.curvilinear and mesh.rasterized is False:
        warnings.warn(
            f"{who}(rasterized=False) has no effect on a curvilinear grid -- "
            "it always rasterizes (a curvilinear cell isn't an axis-aligned "
            "rect, so there is no vector path for it). A thin cell can still "
            "be dropped by the raster resample; watch for that warning "
            "separately.",
            UserWarning, stacklevel=3)


def _dropped_cell_desc(indices, edges, axis):
    """One clause naming which cell(s) along ``axis`` a raster resample lost."""
    i0 = int(indices[0])
    lo, hi = edges[i0], edges[i0 + 1]
    if indices.size == 1:
        return f"cell {i0} ({axis}={lo:.4g}..{hi:.4g})"
    return f"{indices.size} cells along {axis} (e.g. cell {i0}, {axis}={lo:.4g}..{hi:.4g})"


def _warn_dropped_cells(mesh, who, xe, ye, suggest_vector):
    """Warn that the raster path actually dropped one or more cells.

    Only meaningful when ``mesh`` rasterizes at all -- a uniform grid's fast
    path is lossless, and a vectorized mesh never resamples, so both leave
    ``dropped_x``/``dropped_y`` empty (see ``artists._resolve_mesh_render``).
    A cell this warns about is not drawn thin: it is entirely absent from the
    output, silently, because no raster pixel's center falls inside it. This
    is also exactly what a PNG/PDF raster export of *any* mesh -- including
    one that vectorized fine for SVG -- would drop, since only SVG has a
    vector path at all; that only matters for a mesh under the cell-count
    limit, where this warning itself never fires (nothing was dropped for
    SVG), so a mesh you only ever intend to export as PNG is worth checking
    with ``rasterized=True`` once to see what it actually loses.
    """
    if mesh.vectorized or (mesh.dropped_x.size == 0 and mesh.dropped_y.size == 0):
        return
    parts = []
    if mesh.dropped_x.size:
        parts.append(_dropped_cell_desc(mesh.dropped_x, xe, "x"))
    if mesh.dropped_y.size:
        parts.append(_dropped_cell_desc(mesh.dropped_y, ye, "y"))
    if not suggest_vector:
        fix = (" pcolormesh_frames() does not support rasterized=False; use "
               "a log scale if this axis spans decades.")
    elif mesh.n_cells is not None and mesh.n_cells <= _VECTOR_CELL_LIMIT:
        fix = (f" Pass rasterized=False to draw exact vector cells instead "
               f"(cheap here, under ~{_VECTOR_CELL_LIMIT} cells), or use a "
               "log scale if this axis spans decades.")
    else:
        fix = (f" This mesh has {mesh.n_cells} cells, past the "
               f"~{_VECTOR_CELL_LIMIT}-cell auto threshold, so "
               "rasterized=False will draw every cell exactly but produce a "
               "much larger SVG (see pcolormesh_vector_cell_limit.py) -- or "
               "use a log scale if this axis spans decades.")
    warnings.warn(
        f"{who}(): {'; '.join(parts)} narrower than one output pixel and will "
        f"not appear in the raster.{fix}",
        UserWarning, stacklevel=3)


def _both_set(lim):
    """True when ``lim`` pins both ends (so no autoscaling is needed)."""
    return lim is not None and lim[0] is not None and lim[1] is not None


def _group_limits(ax, group, attr):
    """Merge an explicit limit across a share group, ``ax``'s own winning.

    Each end is resolved independently, so ``set_xlim(0, None)`` on one panel
    still lets the shared autoscale decide the other end for the whole group.
    """
    own = getattr(ax, attr)
    if len(group) < 2 or _both_set(own):
        return own
    lo = None if own is None else own[0]
    hi = None if own is None else own[1]
    for other in group:
        if other is ax:
            continue
        lim = getattr(other, attr)
        if lim is None:
            continue
        if lo is None:
            lo = lim[0]
        if hi is None:
            hi = lim[1]
    return None if lo is None and hi is None else (lo, hi)


def _fill_limits(lim, auto):
    """Resolve a stored limit pair against autoscaled ``auto`` bounds."""
    if lim is None:
        return auto
    lo, hi = lim
    return (auto[0] if lo is None else lo, auto[1] if hi is None else hi)


def _pad(lo, hi, scale="linear", tight=False, frac=0.05):
    if scale == "log":
        if hi <= 0:
            hi = 1.0
        if lo <= 0:
            lo = hi * 1e-3            # data had non-positive values; clamp
        llo, lhi = math.log10(lo), math.log10(hi)
        if llo == lhi:
            llo -= 0.5; lhi += 0.5
        elif not tight:
            pad = (lhi - llo) * frac
            llo -= pad; lhi += pad
        return (10.0 ** llo, 10.0 ** lhi)
    if lo == hi:
        return (lo - 0.5, hi + 0.5)
    if tight:
        return (lo, hi)
    pad = (hi - lo) * frac
    return (lo - pad, hi + pad)
