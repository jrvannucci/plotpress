"""Lightweight scene primitives.

Artists are *data holders*, not renderers. ``ax.plot(...)`` just stashes arrays
and style and returns immediately -- no drawing happens until the figure is
serialized. This keeps construction cheap and keeps whole arrays intact for the
vectorized NumPy rendering pass. All rendering logic lives in
:mod:`plotpress.svg` and :mod:`plotpress.raster`.
"""

from __future__ import annotations

import numpy as np

from .colors import apply_colormap, get_cmap, resolve_norm


class Artist:
    """Base class: exposes a data bounding box for autoscaling."""

    label = None
    zorder = 0  # draw order within an axes; higher draws on top, ties keep call order

    def data_bounds(self):
        """Return ``(xmin, xmax, ymin, ymax)`` or ``None`` if empty."""
        raise NotImplementedError


def finite_range(a):
    """``(min, max)`` over the finite entries of ``a``; ``(nan, nan)`` if none.

    An artist whose data is entirely ``nan`` is a real case rather than a
    mistake -- a fully masked frame, a channel that dropped out for the whole
    record, a rug placed as a fraction of the axes. NumPy's ``nanmin`` emits a
    RuntimeWarning on an all-NaN slice, which ``errstate`` does not suppress
    because it is a warning and not a floating-point condition, so drawing such
    a figure printed noise to stderr. Autoscaling already ignores a non-finite
    bound, so returning NaN is the answer the caller wants.
    """
    a = np.asarray(a, dtype=float)
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return np.nan, np.nan
    return finite.min(), finite.max()


class Line2D(Artist):
    def __init__(self, x, y, color, linewidth, linestyle="-", label=None, alpha=1.0,
                 values=None, marker=None, markersize=None, markerfacecolor=None):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.label = label
        self.alpha = alpha
        # Extra per-point dimensions (name -> array) surfaced by point picking,
        # e.g. z or any 4th+ value beyond x/y.
        self.pick_values = dict(values) if values else {}
        # A marker at each vertex, in addition to the line itself -- only
        # round shapes render as anything but a dot (see _warn_marker_shape),
        # same limitation scatter()/errorbar() already have. markerfacecolor
        # defaults to the line's own color, matching matplotlib.
        self.marker = marker
        self.markersize = markersize
        self.markerfacecolor = markerfacecolor

    def data_bounds(self):
        if self.x.size == 0:
            return None
        return finite_range(self.x) + finite_range(self.y)


class FrameLine2D(Artist):
    """A line whose data has an extra dimension scrubbed by a slider.

    ``Y`` is ``(n_frames, n_points)``; ``X`` is either shared ``(n_points,)`` or
    per-frame ``(n_frames, n_points)``. The static render shows frame 0; in
    interactive output a slider redraws the selected frame. Autoscaling spans
    *all* frames so the axes limits stay fixed while sliding.
    """

    def __init__(self, X, Y, color, linewidth, linestyle="-", label=None, alpha=1.0):
        self.Y = np.asarray(Y, dtype=float)
        self.X = np.asarray(X, dtype=float)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.label = label
        self.alpha = alpha
        self.n_frames = self.Y.shape[0]
        self.slider_unit = "main"  # set by Axes.plot_frames

    def frame_xy(self, f):
        x = self.X if self.X.ndim == 1 else self.X[f]
        return x, self.Y[f]

    def data_bounds(self):
        if self.Y.size == 0:
            return None
        return finite_range(self.X) + finite_range(self.Y)


class VLine(Artist):
    """A vertical reference line spanning the full axes height at data x.

    Like matplotlib's ``axvline``, it does not participate in autoscaling
    (``data_bounds`` returns ``None``).
    """

    def __init__(self, x, color, linewidth, linestyle="--", label=None, alpha=1.0):
        self.x = float(x)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.label = label
        self.alpha = alpha

    def data_bounds(self):
        return None


class AxLine(Artist):
    """An infinite line through ``(x1, y1)`` with a given ``slope`` (``axline``).

    Spans the whole axes; ``slope = inf`` is a vertical line. Does not autoscale.
    """

    def __init__(self, x1, y1, slope, color, linewidth, linestyle="-",
                 label=None, alpha=1.0):
        self.x1 = float(x1)
        self.y1 = float(y1)
        self.slope = slope
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.label = label
        self.alpha = alpha

    def data_bounds(self):
        return None


class HLine(Artist):
    """A horizontal reference line spanning the full axes width at data y.

    Like matplotlib's ``axhline``; does not participate in autoscaling.
    """

    def __init__(self, y, color, linewidth, linestyle="--", label=None, alpha=1.0):
        self.y = float(y)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.label = label
        self.alpha = alpha

    def data_bounds(self):
        return None


class Span(Artist):
    """A shaded band across the axes (``axhspan`` / ``axvspan``).

    ``orientation`` is ``"horizontal"`` for ``axhspan`` (a band between two *y*
    values spanning the full width) or ``"vertical"`` for ``axvspan`` (between
    two *x* values spanning the full height). Does not drive autoscaling.
    """

    def __init__(self, lo, hi, orientation, color, alpha=0.3, label=None):
        self.lo = float(lo)
        self.hi = float(hi)
        self.orientation = orientation
        self.color = color
        self.alpha = alpha
        self.label = label

    def data_bounds(self):
        return None


class ScatterCollection(Artist):
    def __init__(self, x, y, s, color, marker="o", label=None, alpha=1.0,
                 c=None, cmap="viridis", norm=None, values=None,
                 edgecolors=None, linewidths=None):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.s = s  # diameter in points (scalar or array)
        self.color = color  # used when c is None
        self.marker = marker
        self.label = label
        self.alpha = alpha
        self.edgecolor = edgecolors
        # A given edgecolor with no explicit width still needs one to
        # actually show -- matplotlib's own default marker edge width.
        self.linewidths = (linewidths if linewidths is not None
                           else (1.0 if edgecolors is not None else 0.0))

        # Optional data-mapped face colors.
        self.c = None if c is None else np.asarray(c, dtype=float)
        self.lut = get_cmap(cmap)
        self.norm = resolve_norm(norm)
        if self.c is not None:
            # Scale now rather than lazily at render, matching QuadMesh/Image:
            # a colorbar over this needs vmin/vmax to size its tick labels
            # before anything has been drawn.
            self.norm.autoscale_none(self.c)

        # Extra per-point dimensions (name -> array) surfaced by point picking.
        # The color dimension `c` is included automatically when present.
        self.pick_values = dict(values) if values else {}
        if self.c is not None and "c" not in self.pick_values:
            self.pick_values["c"] = self.c

    @property
    def mappable(self):
        return self.c is not None

    def face_colors(self):
        """Return per-point ``#rrggbb`` strings when ``c`` is set, else None."""
        if self.c is None:
            return None
        rgba = apply_colormap(self.c, self.lut, self.norm)
        return ["#%02x%02x%02x" % (r, g, b) for r, g, b, _ in rgba]

    def data_bounds(self):
        if self.x.size == 0:
            return None
        return finite_range(self.x) + finite_range(self.y)


def _in_tri(px, py, ax, ay, bx, by, cx, cy):
    """Vectorized point-in-triangle (inclusive of edges) for pixel arrays."""
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    has_pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return ~(has_neg & has_pos)


def _fill_quad(img, qx, qy, color):
    """Fill a convex quad (as two triangles) with ``color`` into ``img``."""
    H, W = img.shape[:2]
    x0 = max(0, int(np.floor(min(qx)))); x1 = min(W - 1, int(np.ceil(max(qx))))
    y0 = max(0, int(np.floor(min(qy)))); y1 = min(H - 1, int(np.ceil(max(qy))))
    if x1 < x0 or y1 < y0:
        return
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    px, py = xx + 0.5, yy + 0.5
    inside = (_in_tri(px, py, qx[0], qy[0], qx[1], qy[1], qx[2], qy[2])
              | _in_tri(px, py, qx[0], qy[0], qx[2], qy[2], qx[3], qy[3]))
    img[y0:y1 + 1, x0:x1 + 1][inside] = color


def _fill_tri_gouraud(img, ax, ay, bx, by, cx, cy, ca, cb, cc):
    """Fill triangle ABC, interpolating corner RGBA colors (barycentric)."""
    H, W = img.shape[:2]
    x0 = max(0, int(np.floor(min(ax, bx, cx)))); x1 = min(W - 1, int(np.ceil(max(ax, bx, cx))))
    y0 = max(0, int(np.floor(min(ay, by, cy)))); y1 = min(H - 1, int(np.ceil(max(ay, by, cy))))
    if x1 < x0 or y1 < y0:
        return
    denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(denom) < 1e-12:
        return
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    px, py = xx + 0.5, yy + 0.5
    w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
    w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
    w2 = 1.0 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if not inside.any():
        return
    col = (w0[..., None] * ca + w1[..., None] * cb + w2[..., None] * cc)
    sub = img[y0:y1 + 1, x0:x1 + 1]
    sub[inside] = np.clip(col[inside], 0, 255).astype(np.uint8)


def _uniform(edges, rtol=1e-9):
    """True if ``edges`` are evenly spaced (the fast, exact mesh path)."""
    if edges.size < 3:
        return True
    d = np.diff(edges)
    return bool(np.allclose(d, d[0], rtol=rtol, atol=0.0))


def _resample_size(edges, n, max_side):
    """Pixels needed along an axis so the *narrowest* cell survives resampling.

    Sizing by cell count alone drops thin cells: a grid of five cells whose
    smallest is a thousandth of the span needs far more than five pixels before
    that cell claims one. Ask for enough to resolve the narrowest, then cap --
    past the cap a cell thinner than one pixel is genuinely unrepresentable in a
    single raster, which the limitations gallery shows.
    """
    widths = np.diff(edges)
    finest = float(np.min(widths[widths > 0.0])) if np.any(widths > 0.0) else 0.0
    span = float(edges[-1] - edges[0])
    need = int(np.ceil(span / finest)) if finest > 0.0 else n
    return int(min(max_side, max(need, n, 64)))


#: Above this many cells, one <rect> per cell would make the SVG bigger than
#: the raster path's near-flat cost (see docs/scale/plot_09_output_scaling.py:
#: a mesh's file size tracks how compressible the field is, not its cell
#: count -- N rects reintroduces exactly the one-mark-one-cost growth that
#: benchmark shows scatter paying and mesh not). Past this, auto mode falls
#: back to rasterizing even a non-uniform grid.
_VECTOR_CELL_LIMIT = 2000


def _dropped_indices(edges, n, max_side):
    """Cell indices along one axis that get zero samples when resampled.

    Reuses the exact pixel-center-to-cell lookup ``_rgba_rectilinear``
    performs (see there), so this reports what will actually be missing from
    the raster rather than an estimate of it. Empty on a uniform axis, since
    that path never resamples at all.
    """
    if _uniform(edges):
        return np.empty(0, dtype=int)
    out = _resample_size(edges, n, max_side)
    xs = edges[0] + (np.arange(out) + 0.5) * (edges[-1] - edges[0]) / out
    idx = np.clip(np.searchsorted(edges, xs) - 1, 0, n - 1)
    present = np.zeros(n, dtype=bool)
    present[idx] = True
    return np.flatnonzero(~present)


def _resolve_mesh_render(xe, ye, nx, ny, curvilinear, rasterized, max_side=1024):
    """Decide raster vs. vector for one rectilinear mesh, and what raster would drop.

    ``rasterized`` is the caller's request: ``True``/``False`` are honored as
    given -- an explicit choice always wins, even a wasteful one, the same way
    matplotlib's own ``rasterized=`` never second-guesses an artist that asked
    for it. ``None`` (auto) picks for itself: vector under
    :data:`_VECTOR_CELL_LIMIT` cells on a non-uniform grid, raster otherwise --
    a *uniform* grid stays raster in auto mode specifically, since its raster
    path is already a byte-identical, lossless copy (see
    ``QuadMesh._rgba_rectilinear``), so auto-selecting vector there would only
    add file size for no fidelity gain. A curvilinear mesh has no vector path
    here at all -- its cells aren't axis-aligned rects -- so it always
    rasterizes regardless of ``rasterized``.

    Dropped-cell indices are computed whenever the grid is non-uniform,
    independent of the vector/raster choice, so a caller that renders raster
    regardless of ``vectorized`` (:class:`FrameQuadMesh` -- see its own
    docstring) can still warn accurately.

    Returns ``(vectorized, n_cells, uniform_grid, dropped_x, dropped_y)``.
    """
    if curvilinear:
        empty = np.empty(0, dtype=int)
        return False, None, False, empty, empty
    n_cells = nx * ny
    uniform_grid = _uniform(xe) and _uniform(ye)
    if rasterized is True:
        vectorized = False
    elif rasterized is False:
        vectorized = True
    else:
        vectorized = (not uniform_grid) and n_cells <= _VECTOR_CELL_LIMIT
    if uniform_grid:
        empty = np.empty(0, dtype=int)
        dropped_x, dropped_y = empty, empty
    else:
        dropped_x = _dropped_indices(xe, nx, max_side)
        dropped_y = _dropped_indices(ye, ny, max_side)
    return vectorized, n_cells, uniform_grid, dropped_x, dropped_y


def _edges_from(coord, n):
    """``n + 1`` cell edges from a coordinate vector, or ``None`` for indices.

    ``n + 1`` values are edges already. ``n`` values are cell centers, so the
    edges sit at the midpoints between them, with the outermost half-cells
    mirrored outward -- the same convention as matplotlib's
    ``shading="nearest"``. Getting this wrong is not a cosmetic matter on a
    non-uniform grid: it decides where every cell boundary lands.
    """
    if coord is None:
        return np.arange(n + 1, dtype=float)
    c = np.asarray(coord, dtype=float).ravel()
    if c.size == n + 1:
        return c
    if c.size != n:
        raise ValueError(
            f"coordinate length {c.size} matches neither {n} cell centers "
            f"nor {n + 1} cell edges")
    if n == 1:
        return np.array([c[0] - 0.5, c[0] + 0.5])
    mid = 0.5 * (c[:-1] + c[1:])
    return np.concatenate(([2.0 * c[0] - mid[0]], mid, [2.0 * c[-1] - mid[-1]]))


def _as_rectilinear_1d(X, Y):
    """``(x, y)`` 1-D vectors if 2-D ``X``/``Y`` are secretly rectilinear.

    ``X, Y = np.meshgrid(x, y)`` then ``pcolormesh(X, Y, Z)`` is a common,
    perfectly ordinary way to build a rectilinear grid -- but it arrives as
    2-D coordinates, indistinguishable in shape from a genuinely curvilinear
    grid. Every row of ``X`` and every column of ``Y`` being constant is the
    tell: collapsing to the equivalent 1-D vectors lets the caller route
    through the vectorized rectilinear path (cheap at any resolution)
    instead of curvilinear scan-conversion's per-cell Python loop, which is
    the same grid, correctly rendered, orders of magnitude slower for no
    reason. Returns ``None`` for a grid that is actually curvilinear.
    """
    if not np.allclose(X, X[:1], equal_nan=True):
        return None
    if not np.allclose(Y, Y[:, :1], equal_nan=True):
        return None
    return X[0].copy(), Y[:, 0].copy()


class QuadMesh(Artist):
    """Color mesh, drawn as a single embedded ``<image>`` or as per-cell vectors.

    ``X``/``Y`` may be **1-D** rectilinear edge/center coordinates (uniform grid,
    fast path) or **2-D** node coordinates for a *curvilinear* grid, which is
    scan-converted to the image in pure NumPy. The data extent
    is taken from their min/max.

    2-D ``X``/``Y`` that are actually rectilinear -- the common
    ``np.meshgrid(x, y)`` pattern -- are detected and collapsed back to 1-D
    (see :func:`_as_rectilinear_1d`), so that shape alone doesn't force the
    slow curvilinear path onto a grid that never needed it.

    ``rasterized`` controls the SVG output path for a non-uniform rectilinear
    grid -- see :func:`_resolve_mesh_render` for the full decision. The
    resolved outcome lives on the instance as ``.vectorized``, ``.n_cells``,
    ``.uniform_grid``, ``.dropped_x``/``.dropped_y`` (cell indices the raster
    path would drop, computed either way so a caller that always rasterizes
    regardless of this decision can still warn -- see :class:`FrameQuadMesh`).
    """

    def __init__(self, X, Y, C, cmap="viridis", norm=None, vmin=None, vmax=None,
                 shading="flat", alpha=1.0, label=None, rasterized=None):
        self.C = np.asarray(C, dtype=float)
        self.X = None if X is None else np.asarray(X, dtype=float)
        self.Y = None if Y is None else np.asarray(Y, dtype=float)
        self.shading = shading
        self.alpha = alpha
        self.label = label
        if self.X is not None and self.Y is not None \
                and self.X.ndim == 2 and self.Y.ndim == 2:
            collapsed = _as_rectilinear_1d(self.X, self.Y)
            if collapsed is not None:
                self.X, self.Y = collapsed
        # A coordinate vector given high-to-low is perfectly legitimate --
        # pressure, depth and wavelength axes are routinely stored descending --
        # but everything downstream (extent, which keeps only min/max; the
        # rasterizer, which assumes row 0 is ymax; the interactive pick arrays)
        # reads them ascending, so the field came out mirrored against its own
        # axis. Normalize once here, flipping the data with the coordinate so
        # every cell keeps the position it was given.
        if self.X is not None and self.X.ndim == 1 and self.X.size > 1 \
                and self.X[0] > self.X[-1]:
            self.X = np.ascontiguousarray(self.X[::-1])
            self.C = np.ascontiguousarray(self.C[:, ::-1])
        if self.Y is not None and self.Y.ndim == 1 and self.Y.size > 1 \
                and self.Y[0] > self.Y[-1]:
            self.Y = np.ascontiguousarray(self.Y[::-1])
            self.C = np.ascontiguousarray(self.C[::-1, :])
        # Gouraud shades between node values, so it needs 2-D node coords; build
        # them from 1-D edges (or default indices) if necessary.
        if shading == "gouraud":
            if self.X is None:
                ny, nx = self.C.shape
                self.X, self.Y = np.meshgrid(np.arange(nx, dtype=float),
                                             np.arange(ny, dtype=float))
            elif self.X.ndim == 1:
                self.X, self.Y = np.meshgrid(self.X, self.Y)
        self.curvilinear = (self.X is not None and self.Y is not None
                            and self.X.ndim == 2 and self.Y.ndim == 2)
        self.lut = get_cmap(cmap)
        self.norm = resolve_norm(norm, vmin, vmax)
        self.norm.autoscale_none(self.C)
        self.rasterized = rasterized
        if not self.curvilinear:
            # Resolve the edges now so a coordinate length that is neither
            # centers nor edges fails at the pcolormesh() call, not later inside
            # the renderer where the traceback says nothing about the caller.
            xe, ye = self.cell_edges()
            ny, nx = self.C.shape
            (self.vectorized, self.n_cells, self.uniform_grid,
             self.dropped_x, self.dropped_y) = _resolve_mesh_render(
                xe, ye, nx, ny, curvilinear=False, rasterized=rasterized)
        else:
            empty = np.empty(0, dtype=int)
            self.vectorized, self.n_cells, self.uniform_grid = False, None, False
            self.dropped_x, self.dropped_y = empty, empty

    def cell_edges(self):
        """``(x_edges, y_edges)`` for the rectilinear grid: one more than cells.

        ``None`` coordinates default to integer indices. A vector one longer
        than the cell count is taken as edges directly; one of equal length is
        taken as cell *centers* (matplotlib's ``shading="nearest"``), with edges
        at the midpoints and half a cell extrapolated at each end. Curvilinear
        meshes have no such vectors and are scan-converted instead.
        """
        ny, nx = self.C.shape
        return (_edges_from(self.X, nx), _edges_from(self.Y, ny))

    def extent(self):
        if self.curvilinear:
            return (float(np.min(self.X)), float(np.max(self.X)),
                    float(np.min(self.Y)), float(np.max(self.Y)))
        xe, ye = self.cell_edges()
        return float(xe[0]), float(xe[-1]), float(ye[0]), float(ye[-1])

    def rgba(self):
        """Return the mesh as an RGBA uint8 image (row 0 = top = max y)."""
        if self.shading == "gouraud":
            rgba = self._rgba_gouraud()
        elif self.curvilinear:
            rgba = self._rgba_curvilinear()
        else:
            rgba = self._rgba_rectilinear()
        if self.alpha != 1.0:
            rgba = rgba.copy()
            rgba[..., 3] = (rgba[..., 3].astype(np.float64) * self.alpha).round().astype(np.uint8)
        return rgba

    def _rgba_rectilinear(self, max_side=1024):
        """Rectilinear mesh as an image, honoring non-uniform cell widths.

        A uniform grid maps one cell to one pixel, which is exact and is the
        overwhelmingly common case. A *non-uniform* grid cannot: the image is
        stretched linearly across the extent, so equal-width pixels would put
        every cell boundary in the wrong place. Resample instead -- assign each
        output pixel the cell its center falls inside -- which costs one
        ``searchsorted`` per axis and puts every boundary where the data says.
        """
        cell = apply_colormap(self.C, self.lut, self.norm)
        xe, ye = self.cell_edges()
        if _uniform(xe) and _uniform(ye):
            # Image rows go top-down; data y increases upward -> flip.
            return np.flipud(cell)

        ny, nx = self.C.shape
        out_w = nx if _uniform(xe) else _resample_size(xe, nx, max_side)
        out_h = ny if _uniform(ye) else _resample_size(ye, ny, max_side)
        xs = xe[0] + (np.arange(out_w) + 0.5) * (xe[-1] - xe[0]) / out_w
        # Rows run top-down, so walk y from the top edge downward.
        ys = ye[-1] - (np.arange(out_h) + 0.5) * (ye[-1] - ye[0]) / out_h
        col = np.clip(np.searchsorted(xe, xs) - 1, 0, nx - 1)
        row = np.clip(np.searchsorted(ye, ys) - 1, 0, ny - 1)
        return cell[row[:, None], col[None, :]]

    def _out_grid(self, max_side):
        """Blank output image + node pixel coords (row 0 = ymax)."""
        xmin, xmax, ymin, ymax = self.extent()
        aspect = (ymax - ymin) / ((xmax - xmin) or 1.0)
        if aspect >= 1:
            out_h, out_w = max_side, max(1, int(round(max_side / aspect)))
        else:
            out_w, out_h = max_side, max(1, int(round(max_side * aspect)))
        img = np.zeros((out_h, out_w, 4), np.uint8)
        # Map the mesh onto pixel *edges*, not pixel centers. Scaling by
        # out_w - 1 put the boundary nodes at indices 0 and out_w - 1, while the
        # scan converter samples centers at index + 0.5 -- so the far row and
        # column sampled just outside the mesh and were left transparent,
        # showing as a hairline gap along two edges of every curvilinear mesh.
        sx = out_w / ((xmax - xmin) or 1.0)
        sy = out_h / ((ymax - ymin) or 1.0)
        PX = (self.X - xmin) * sx
        PY = (ymax - self.Y) * sy                  # flip: row 0 = ymax (top)
        return img, PX, PY

    def _rgba_curvilinear(self, max_side=512):
        """Scan-convert a 2-D quad mesh to an RGBA image (flat per-cell color)."""
        X, C = self.X, self.C
        ny = min(C.shape[0], X.shape[0] - 1)
        nx = min(C.shape[1], X.shape[1] - 1)
        cell_rgba = apply_colormap(C[:ny, :nx], self.lut, self.norm)
        img, PX, PY = self._out_grid(max_side)
        for i in range(ny):
            for j in range(nx):
                col = cell_rgba[i, j]
                if col[3] == 0:
                    continue
                qx = (PX[i, j], PX[i, j + 1], PX[i + 1, j + 1], PX[i + 1, j])
                qy = (PY[i, j], PY[i, j + 1], PY[i + 1, j + 1], PY[i + 1, j])
                _fill_quad(img, qx, qy, col)
        return img

    def _rgba_gouraud(self, max_side=512):
        """Scan-convert with per-node colors smoothly interpolated across cells."""
        node = apply_colormap(self.C, self.lut, self.norm).astype(np.float64)
        img, PX, PY = self._out_grid(max_side)
        ny, nx = self.C.shape
        for i in range(ny - 1):
            for j in range(nx - 1):
                x = (PX[i, j], PX[i, j + 1], PX[i + 1, j + 1], PX[i + 1, j])
                y = (PY[i, j], PY[i, j + 1], PY[i + 1, j + 1], PY[i + 1, j])
                c = (node[i, j], node[i, j + 1], node[i + 1, j + 1], node[i + 1, j])
                _fill_tri_gouraud(img, x[0], y[0], x[1], y[1], x[2], y[2], c[0], c[1], c[2])
                _fill_tri_gouraud(img, x[0], y[0], x[2], y[2], x[3], y[3], c[0], c[2], c[3])
        return img

    def data_bounds(self):
        return self.extent()


class FrameQuadMesh(Artist):
    """A pcolormesh whose color data has an extra dimension scrubbed by a slider.

    ``C`` is ``(n_frames, ny, nx)``; ``X``/``Y`` are shared across every frame,
    exactly as ``pcolormesh()`` takes them -- only the color data animates, the
    grid itself does not. Each frame is built as its own fully-validated
    :class:`QuadMesh` (curvilinear detection, gouraud node coordinates,
    descending-axis normalization all included, rather than reimplemented),
    sharing one :class:`~plotpress.colors.Normalize` autoscaled to *every*
    frame's data at once -- so the colour scale stays fixed rather than
    jumping frame to frame, the same reason a shared colorbar is pinned to one
    ``vmin``/``vmax`` across several axes.

    Always rasterizes, regardless of :data:`_VECTOR_CELL_LIMIT` -- the
    interactive slider swaps one ``<image href>`` per scrub (see
    ``svg.frame_data``), and animating per-cell vector rects instead would need
    the client to rewrite every cell's fill on every frame rather than swap one
    attribute, considerably heavier for no fidelity gain in the common case.
    ``.dropped_x``/``.dropped_y`` are still computed (from the shared grid,
    identical every frame) so :func:`plotpress.axes._warn_dropped_cells` can
    warn accurately even though this artist never vectorizes.
    """

    def __init__(self, X, Y, C, cmap="viridis", norm=None, vmin=None, vmax=None,
                 shading="flat", label=None, alpha=1.0):
        C = np.asarray(C, dtype=float)
        if C.ndim != 3:
            raise ValueError(
                "pcolormesh_frames() requires C with shape (n_frames, ny, nx)")
        self.n_frames = C.shape[0]
        shared_norm = resolve_norm(norm, vmin, vmax)
        shared_norm.autoscale_none(C)          # fits every frame at once
        self.frames = [QuadMesh(X, Y, C[f], cmap=cmap, norm=shared_norm,
                                shading=shading) for f in range(self.n_frames)]
        self.lut = self.frames[0].lut
        self.norm = self.frames[0].norm
        self.label = label
        self.alpha = alpha
        self.slider_unit = "main"  # set by Axes.pcolormesh_frames
        self.curvilinear = self.frames[0].curvilinear
        self.vectorized = False  # see class docstring
        self.dropped_x = self.frames[0].dropped_x
        self.dropped_y = self.frames[0].dropped_y

    def frame_mesh(self, f):
        return self.frames[f]

    def data_bounds(self):
        return self.frames[0].extent()


def _as_colors(color, n):
    """Normalize a color arg to a per-item list of length n."""
    if isinstance(color, (list, tuple, np.ndarray)) and len(color) == n \
            and not isinstance(color, str):
        return list(color)
    return [color] * n


class Bars(Artist):
    """Rectangular bars (bar / barh / hist)."""

    def __init__(self, pos, length, thickness, base, orientation, color,
                 edgecolor=None, linewidth=0.8, label=None, alpha=1.0):
        self.pos = np.atleast_1d(np.asarray(pos, float))
        self.length = np.atleast_1d(np.asarray(length, float))
        self.thickness = np.broadcast_to(
            np.asarray(thickness, float), self.pos.shape).copy()
        self.base = np.broadcast_to(np.asarray(base, float), self.pos.shape).copy()
        self.orientation = orientation
        self.colors = _as_colors(color, len(self.pos))
        self.edgecolor = edgecolor
        self.linewidth = linewidth
        self.label = label
        self.alpha = alpha

    def data_bounds(self):
        lo = np.minimum(self.base, self.base + self.length)
        hi = np.maximum(self.base, self.base + self.length)
        cat0 = self.pos - self.thickness / 2
        cat1 = self.pos + self.thickness / 2
        if self.orientation == "vertical":
            return (cat0.min(), cat1.max(), min(lo.min(), 0.0), hi.max())
        return (min(lo.min(), 0.0), hi.max(), cat0.min(), cat1.max())


class FillBetween(Artist):
    def __init__(self, x, y1, y2, color, alpha=0.4, label=None, edgecolor=None,
                 linewidth=0.0):
        self.x = np.asarray(x, float)
        # Broadcast *both* bounds against x. Only y2 was, because its default
        # is the scalar 0.0 -- so filling from a constant baseline up to a
        # curve, ``fill_between(x, floor, series)``, crashed inside the
        # transform with an unrelated-looking column_stack shape error, while
        # the same call with the arguments the other way round worked.
        self.y1 = np.broadcast_to(np.asarray(y1, float), self.x.shape).copy()
        self.y2 = np.broadcast_to(np.asarray(y2, float), self.x.shape).copy()
        self.color = color
        self.alpha = alpha
        self.label = label
        # Matches Polygon's own edgecolor/linewidth (fill() already has
        # these) -- fill_between/fill_betweenx use the same closed-path
        # primitive, so there was no reason the outline was fill()-only.
        self.edgecolor = edgecolor
        self.linewidth = linewidth

    def data_bounds(self):
        ys = np.concatenate([self.y1, self.y2])
        return (self.x.min(), self.x.max(), ys.min(), ys.max())


class Polygon(Artist):
    """A filled polygon in data coordinates (``fill`` / ``fill_betweenx``)."""

    def __init__(self, x, y, color, alpha=1.0, edgecolor=None, linewidth=0.0,
                 label=None):
        self.x = np.asarray(x, float)
        self.y = np.asarray(y, float)
        self.color = color
        self.alpha = alpha
        self.edgecolor = edgecolor
        self.linewidth = linewidth
        self.label = label

    def data_bounds(self):
        if self.x.size == 0:
            return None
        return (self.x.min(), self.x.max(), self.y.min(), self.y.max())


class LineCollection(Artist):
    """A set of straight line segments (``hlines`` / ``vlines``).

    ``segments`` is an ``(N, 4)`` array of ``(x0, y0, x1, y1)`` rows.
    """

    def __init__(self, segments, color, linewidth, linestyle="-", label=None,
                 alpha=1.0):
        self.segments = np.asarray(segments, float).reshape(-1, 4)
        self.color = color
        self.linewidth = linewidth
        self.linestyle = linestyle
        self.label = label
        self.alpha = alpha

    def data_bounds(self):
        if self.segments.size == 0:
            return None
        s = self.segments
        xs = np.concatenate([s[:, 0], s[:, 2]])
        ys = np.concatenate([s[:, 1], s[:, 3]])
        return (xs.min(), xs.max(), ys.min(), ys.max())


class Rug(Artist):
    """Tick marks at each observation, anchored to one edge of the axes.

    ``height`` is a fraction of the axes rectangle, applied at draw time in
    pixel space (like :class:`VLine` spanning the full height). It therefore
    does *not* depend on the data limits: repeated rugs share one baseline, and
    a rug never drags the autoscale along the axis it is anchored to.
    """

    def __init__(self, x, height=0.03, side="bottom", color=None, linewidth=1.0,
                 label=None, alpha=1.0):
        self.x = np.asarray(x, dtype=float)
        self.height = float(height)
        self.side = side
        self.color = color
        self.linewidth = linewidth
        self.label = label
        self.alpha = alpha

    def data_bounds(self):
        if self.x.size == 0:
            return None
        lo, hi = finite_range(self.x)
        # NaN opts out of the perpendicular axis -- the rug is positioned there
        # as a fraction of the axes, so it must not influence autoscaling.
        if self.side == "left":
            return (np.nan, np.nan, lo, hi)
        return (lo, hi, np.nan, np.nan)


class PolyCollection(Artist):
    """Many filled polygons with per-polygon face colors (e.g. ``hexbin``).

    ``verts`` is a list of ``(k, 2)`` vertex arrays; ``facecolors`` is a matching
    list of ``(r, g, b)`` uint8 triples (or ``#rrggbb`` strings). May carry
    ``lut``/``norm`` so it can back a colorbar.
    """

    def __init__(self, verts, facecolors, edgecolor=None, alpha=1.0, label=None):
        self.verts = [np.asarray(v, float) for v in verts]
        self.facecolors = facecolors
        self.edgecolor = edgecolor
        self.alpha = alpha
        self.label = label
        self.lut = None
        self.norm = None

    def data_bounds(self):
        if not self.verts:
            return None
        allv = np.vstack(self.verts)
        return (allv[:, 0].min(), allv[:, 0].max(),
                allv[:, 1].min(), allv[:, 1].max())


class Stem(Artist):
    def __init__(self, x, y, baseline, linecolor, markercolor, label=None):
        self.x = np.asarray(x, float)
        self.y = np.asarray(y, float)
        self.baseline = float(baseline)
        self.linecolor = linecolor
        self.markercolor = markercolor
        self.label = label

    def data_bounds(self):
        return (self.x.min(), self.x.max(),
                min(self.y.min(), self.baseline), max(self.y.max(), self.baseline))


class ErrorBar(Artist):
    def __init__(self, x, y, yerr=None, xerr=None, color="#1f77b4", marker="o",
                 markersize=6.0, capsize=3.0, linestyle="-", linewidth=1.5,
                 label=None, alpha=1.0, ecolor=None, elinewidth=None,
                 capthick=None):
        self.x = np.asarray(x, float)
        self.y = np.asarray(y, float)
        self.yerr = None if yerr is None else np.broadcast_to(
            np.asarray(yerr, float), self.x.shape).copy()
        self.xerr = None if xerr is None else np.broadcast_to(
            np.asarray(xerr, float), self.x.shape).copy()
        self.color = color
        self.marker = marker
        self.markersize = markersize
        self.capsize = capsize
        self.linestyle = linestyle
        self.linewidth = linewidth
        self.label = label
        self.alpha = alpha
        # Each falls back to the previous if not given -- ecolor to the
        # line/marker color, elinewidth to the connecting line's own width
        # (previously hardcoded to 1px regardless of linewidth), capthick
        # to elinewidth -- matching matplotlib's own fallback chain.
        self.ecolor = ecolor if ecolor is not None else self.color
        self.elinewidth = elinewidth if elinewidth is not None else self.linewidth
        self.capthick = capthick if capthick is not None else self.elinewidth

    def data_bounds(self):
        xlo, xhi = self.x.copy(), self.x.copy()
        ylo, yhi = self.y.copy(), self.y.copy()
        if self.yerr is not None:
            ylo = self.y - self.yerr; yhi = self.y + self.yerr
        if self.xerr is not None:
            xlo = self.x - self.xerr; xhi = self.x + self.xerr
        return (xlo.min(), xhi.max(), ylo.min(), yhi.max())


class Image(Artist):
    """imshow: a 2-D (colormapped) or RGB(A) array drawn as one embedded image."""

    def __init__(self, A, cmap="viridis", norm=None, vmin=None, vmax=None,
                 extent=None, origin="upper", alpha=1.0, label=None,
                 interpolation="nearest"):
        self.A = np.asarray(A, float)
        self.lut = get_cmap(cmap)
        self.norm = resolve_norm(norm, vmin, vmax)
        if self.A.ndim == 2:
            self.norm.autoscale_none(self.A)
        self.origin = origin
        self.alpha = alpha
        self.label = label
        self.interpolation = interpolation
        ny, nx = self.A.shape[:2]
        self._extent = tuple(extent) if extent is not None else (0.0, nx, 0.0, ny)

    def extent(self):
        return self._extent

    def rgba(self):
        if self.A.ndim == 2:
            rgba = apply_colormap(self.A, self.lut, self.norm)
        else:
            arr = self.A
            if arr.max() <= 1.0:
                arr = arr * 255.0
            arr = arr.astype(np.uint8)
            if arr.shape[2] == 3:
                alpha = np.full(arr.shape[:2] + (1,), 255, np.uint8)
                rgba = np.concatenate([arr, alpha], axis=2)
            else:
                rgba = arr
        if self.alpha != 1.0:
            # Regression: alpha was accepted and stored but never read again --
            # scale the existing alpha channel (already 0 over NaN cells, or
            # whatever an RGBA input's own alpha carried) rather than
            # overwrite it, so both stay correct at once.
            rgba = rgba.copy()
            rgba[..., 3] = (rgba[..., 3].astype(np.float64) * self.alpha).round().astype(np.uint8)
        # Renderer places row 0 at the top; 'lower' origin needs a flip.
        return rgba if self.origin == "upper" else np.flipud(rgba)

    def data_bounds(self):
        xmin, xmax, ymin, ymax = self._extent
        return (xmin, xmax, ymin, ymax)


def auto_outline(color):
    """A halo color that contrasts with ``color``: white behind dark ink, black
    behind light. Picked from the text's own color rather than from the
    background, because the whole point of a halo is that what the label sits on
    is unknown at layout time -- a mesh cell, a filled band, another series."""
    from .colors import to_hex

    c = to_hex(color).lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return "#ffffff" if luma < 140 else "#000000"


class Text(Artist):
    """A text label anchored at data coordinates (``ax.text``)."""

    def __init__(self, x, y, text, color, size, ha="left", va="baseline",
                 rotation=0.0, outline=None):
        self.x = float(x)
        self.y = float(y)
        self.text = text
        self.color = color
        self.size = size
        self.ha = ha
        self.va = va
        self.rotation = float(rotation)
        self.outline = auto_outline(color) if outline is None else outline

    def data_bounds(self):
        return None  # text does not drive autoscaling


class Annotation(Artist):
    """Text at ``xytext`` optionally pointing an arrow to ``xy`` (``ax.annotate``)."""

    def __init__(self, text, xy, xytext, color, size, ha="left", va="baseline",
                 arrowprops=None, outline=None):
        self.text = text
        self.xy = (float(xy[0]), float(xy[1]))
        self.xytext = (float(xytext[0]), float(xytext[1])) if xytext else self.xy
        self.color = color
        self.size = size
        self.ha = ha
        self.va = va
        self.arrowprops = arrowprops  # dict (e.g. {"color": ...}) or None
        self.outline = auto_outline(color) if outline is None else outline

    def data_bounds(self):
        return None


class BoxPlot(Artist):
    """Box-and-whisker plot (one box per dataset)."""

    def __init__(self, positions, stats, width, color, orientation="vertical",
                 label=None):
        self.positions = np.asarray(positions, float)
        self.stats = stats  # list of dicts: q1, med, q3, lo, hi, fliers
        self.width = float(width)
        self.color = color
        self.orientation = orientation
        self.label = label

    def data_bounds(self):
        if not self.stats:
            return None
        vlo = min(min(s["lo"], *( [s["fliers"].min()] if len(s["fliers"]) else [s["lo"]] )) for s in self.stats)
        vhi = max(max(s["hi"], *( [s["fliers"].max()] if len(s["fliers"]) else [s["hi"]] )) for s in self.stats)
        clo = self.positions.min() - self.width
        chi = self.positions.max() + self.width
        if self.orientation == "vertical":
            return (clo, chi, vlo, vhi)
        return (vlo, vhi, clo, chi)


class Violin(Artist):
    """Violin plot: mirrored kernel-density silhouettes."""

    def __init__(self, positions, grids, halfwidths, color, orientation="vertical",
                 label=None):
        self.positions = np.asarray(positions, float)
        self.grids = grids            # list of 1-D value grids
        self.halfwidths = halfwidths  # list of 1-D half-widths (same shape)
        self.color = color
        self.orientation = orientation
        self.label = label

    def data_bounds(self):
        if not self.grids:
            return None
        vlo = min(g.min() for g in self.grids)
        vhi = max(g.max() for g in self.grids)
        hw = max(h.max() for h in self.halfwidths)
        clo = self.positions.min() - hw
        chi = self.positions.max() + hw
        if self.orientation == "vertical":
            return (clo, chi, vlo, vhi)
        return (vlo, vhi, clo, chi)


class EventPlot(Artist):
    """Raster of event ticks (one row per sequence)."""

    def __init__(self, rows, offsets, linelength, color, orientation="horizontal",
                 label=None):
        self.rows = [np.asarray(r, float) for r in rows]
        self.offsets = np.asarray(offsets, float)
        self.linelength = float(linelength)
        self.color = color
        self.orientation = orientation
        self.label = label

    def data_bounds(self):
        allev = np.concatenate(self.rows) if self.rows else np.array([0.0, 1.0])
        emin, emax = allev.min(), allev.max()
        omin = self.offsets.min() - self.linelength
        omax = self.offsets.max() + self.linelength
        if self.orientation == "horizontal":
            return (emin, emax, omin, omax)
        return (omin, omax, emin, emax)


class Quiver(Artist):
    """A field of arrows (X, Y, U, V) with a scale into data units."""

    def __init__(self, X, Y, U, V, scale, color, label=None):
        self.X = np.asarray(X, float).ravel()
        self.Y = np.asarray(Y, float).ravel()
        self.U = np.asarray(U, float).ravel()
        self.V = np.asarray(V, float).ravel()
        self.scale = scale
        self.color = color
        self.label = label

    def tips(self):
        return self.X + self.U * self.scale, self.Y + self.V * self.scale

    def data_bounds(self):
        tx, ty = self.tips()
        xs = np.concatenate([self.X, tx])
        ys = np.concatenate([self.Y, ty])
        return (xs.min(), xs.max(), ys.min(), ys.max())


def _marching_squares(x, y, Z, level):
    """Return contour segments [(x0,y0,x1,y1), ...] for one level."""
    segs = []
    ny, nx = Z.shape
    for i in range(ny - 1):
        yT, yB = y[i], y[i + 1]
        for j in range(nx - 1):
            xL, xR = x[j], x[j + 1]
            corners = ((xL, yT, Z[i, j]), (xR, yT, Z[i, j + 1]),
                       (xR, yB, Z[i + 1, j + 1]), (xL, yB, Z[i + 1, j]))
            cross = []
            for k in range(4):
                x0, y0, v0 = corners[k]
                x1, y1, v1 = corners[(k + 1) % 4]
                if (v0 > level) != (v1 > level):
                    t = (level - v0) / (v1 - v0)
                    cross.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
            if len(cross) == 2:
                segs.append((cross[0][0], cross[0][1], cross[1][0], cross[1][1]))
            elif len(cross) == 4:  # saddle: connect consecutive pairs
                segs.append((cross[0][0], cross[0][1], cross[1][0], cross[1][1]))
                segs.append((cross[2][0], cross[2][1], cross[3][0], cross[3][1]))
    return segs


class Contour(Artist):
    """Contour lines via marching squares (segments precomputed on build)."""

    def __init__(self, x, y, Z, levels, colors, label=None):
        self.x = np.asarray(x, float)
        self.y = np.asarray(y, float)
        self.Z = np.asarray(Z, float)
        self.levels = list(levels)
        self.colors = colors
        self.label = label
        self.line_segments = [
            (lvl, colors[k % len(colors)], _marching_squares(self.x, self.y, self.Z, lvl))
            for k, lvl in enumerate(self.levels)
        ]

    def data_bounds(self):
        return (self.x.min(), self.x.max(), self.y.min(), self.y.max())


class Pie(Artist):
    """A pie chart, drawn in axes-pixel space so it stays circular."""

    def __init__(self, values, colors, labels=None, startangle=90.0,
                 radius=1.0, autopct=None):
        self.values = np.asarray(values, float)
        total = self.values.sum()
        # An all-zero (or empty) pie has no wedges to size; fall back to equal
        # slices rather than dividing by zero into NaN fractions.
        if total == 0:
            n = self.values.size
            self.fracs = np.full(n, 1.0 / n) if n else self.values
        else:
            self.fracs = self.values / total
        self.colors = colors
        self.labels = labels
        self.startangle = startangle
        self.radius = radius
        self.autopct = autopct

    def pct_text(self, frac):
        """Formatted ``autopct`` label for a wedge holding ``frac`` of the total.

        ``autopct`` is a ``%``-style format string (e.g. ``"%.1f%%"``) or a
        callable ``pct -> str``; ``None`` means no percentage labels.
        """
        if self.autopct is None:
            return None
        pct = 100.0 * float(frac)
        return self.autopct(pct) if callable(self.autopct) else self.autopct % pct

    def data_bounds(self):
        return None  # pie manages its own (hidden) axes
