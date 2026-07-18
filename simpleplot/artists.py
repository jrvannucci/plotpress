"""Lightweight scene primitives.

Artists are *data holders*, not renderers. ``ax.plot(...)`` just stashes arrays
and style and returns immediately -- no drawing happens until the figure is
serialized. This is what keeps construction cheap and lets a future Rust backend
consume whole arrays across the FFI boundary in one call. All rendering logic
lives in :mod:`simpleplot.svg`.
"""

from __future__ import annotations

import numpy as np

from .colors import Normalize, apply_colormap, get_cmap


class Artist:
    """Base class: exposes a data bounding box for autoscaling."""

    label = None

    def data_bounds(self):
        """Return ``(xmin, xmax, ymin, ymax)`` or ``None`` if empty."""
        raise NotImplementedError


class Line2D(Artist):
    def __init__(self, x, y, color, linewidth, linestyle="-", label=None, alpha=1.0,
                 values=None):
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

    def data_bounds(self):
        if self.x.size == 0:
            return None
        with np.errstate(invalid="ignore"):
            return (
                np.nanmin(self.x), np.nanmax(self.x),
                np.nanmin(self.y), np.nanmax(self.y),
            )


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
        with np.errstate(invalid="ignore"):
            return (
                np.nanmin(self.X), np.nanmax(self.X),
                np.nanmin(self.Y), np.nanmax(self.Y),
            )


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
                 c=None, cmap="viridis", norm=None, values=None):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.s = s  # diameter in points (scalar or array)
        self.color = color  # used when c is None
        self.marker = marker
        self.label = label
        self.alpha = alpha

        # Optional data-mapped face colors.
        self.c = None if c is None else np.asarray(c, dtype=float)
        self.lut = get_cmap(cmap)
        self.norm = norm if norm is not None else Normalize()

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
        with np.errstate(invalid="ignore"):
            return (
                np.nanmin(self.x), np.nanmax(self.x),
                np.nanmin(self.y), np.nanmax(self.y),
            )


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


class QuadMesh(Artist):
    """Color mesh, rasterized to a single embedded ``<image>``.

    ``X``/``Y`` may be **1-D** rectilinear edge/center coordinates (uniform grid,
    fast path) or **2-D** node coordinates for a *curvilinear* grid, which is
    scan-converted to the image in pure NumPy (no Rust needed). The data extent
    is taken from their min/max.
    """

    def __init__(self, X, Y, C, cmap="viridis", norm=None, vmin=None, vmax=None,
                 shading="flat"):
        self.C = np.asarray(C, dtype=float)
        self.X = None if X is None else np.asarray(X, dtype=float)
        self.Y = None if Y is None else np.asarray(Y, dtype=float)
        self.shading = shading
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
        self.norm = norm if norm is not None else Normalize(vmin, vmax)
        self.norm.autoscale_none(self.C)

    def extent(self):
        ny, nx = self.C.shape
        if self.X is None:
            xmin, xmax = 0, nx
        else:
            xmin, xmax = float(np.min(self.X)), float(np.max(self.X))
        if self.Y is None:
            ymin, ymax = 0, ny
        else:
            ymin, ymax = float(np.min(self.Y)), float(np.max(self.Y))
        return xmin, xmax, ymin, ymax

    def rgba(self):
        """Return the mesh as an RGBA uint8 image (row 0 = top = max y)."""
        if self.shading == "gouraud":
            return self._rgba_gouraud()
        if self.curvilinear:
            return self._rgba_curvilinear()
        rgba = apply_colormap(self.C, self.lut, self.norm)
        # Image rows go top-down; data y increases upward -> flip vertically.
        return np.flipud(rgba)

    def _out_grid(self, max_side):
        """Blank output image + node pixel coords (row 0 = ymax)."""
        xmin, xmax, ymin, ymax = self.extent()
        aspect = (ymax - ymin) / ((xmax - xmin) or 1.0)
        if aspect >= 1:
            out_h, out_w = max_side, max(1, int(round(max_side / aspect)))
        else:
            out_w, out_h = max_side, max(1, int(round(max_side * aspect)))
        img = np.zeros((out_h, out_w, 4), np.uint8)
        sx = (out_w - 1) / ((xmax - xmin) or 1.0)
        sy = (out_h - 1) / ((ymax - ymin) or 1.0)
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
    def __init__(self, x, y1, y2, color, alpha=0.4, label=None):
        self.x = np.asarray(x, float)
        self.y1 = np.asarray(y1, float)
        self.y2 = np.broadcast_to(np.asarray(y2, float), self.x.shape).copy()
        self.color = color
        self.alpha = alpha
        self.label = label

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
                 label=None, alpha=1.0):
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
                 extent=None, origin="upper", alpha=1.0, label=None):
        self.A = np.asarray(A, float)
        self.lut = get_cmap(cmap)
        self.norm = norm if norm is not None else Normalize(vmin, vmax)
        if self.A.ndim == 2:
            self.norm.autoscale_none(self.A)
        self.origin = origin
        self.alpha = alpha
        self.label = label
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
        # Renderer places row 0 at the top; 'lower' origin needs a flip.
        return rgba if self.origin == "upper" else np.flipud(rgba)

    def data_bounds(self):
        xmin, xmax, ymin, ymax = self._extent
        return (xmin, xmax, ymin, ymax)


class Text(Artist):
    """A text label anchored at data coordinates (``ax.text``)."""

    def __init__(self, x, y, text, color, size, ha="left", va="baseline",
                 rotation=0.0):
        self.x = float(x)
        self.y = float(y)
        self.text = text
        self.color = color
        self.size = size
        self.ha = ha
        self.va = va
        self.rotation = float(rotation)

    def data_bounds(self):
        return None  # text does not drive autoscaling


class Annotation(Artist):
    """Text at ``xytext`` optionally pointing an arrow to ``xy`` (``ax.annotate``)."""

    def __init__(self, text, xy, xytext, color, size, ha="left", va="baseline",
                 arrowprops=None):
        self.text = text
        self.xy = (float(xy[0]), float(xy[1]))
        self.xytext = (float(xytext[0]), float(xytext[1])) if xytext else self.xy
        self.color = color
        self.size = size
        self.ha = ha
        self.va = va
        self.arrowprops = arrowprops  # dict (e.g. {"color": ...}) or None

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
        self.fracs = self.values / self.values.sum()
        self.colors = colors
        self.labels = labels
        self.startangle = startangle
        self.radius = radius
        self.autopct = autopct

    def data_bounds(self):
        return None  # pie manages its own (hidden) axes
