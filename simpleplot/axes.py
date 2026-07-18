"""The Axes object: a self-contained plotting region on a figure.

Mirrors the subset of matplotlib's ``Axes`` API needed for line, scatter, and
pcolormesh plots. Holds its own artists, limits, labels, and a reference to the
owning figure's :class:`~simpleplot.style.Style` -- there is no global current-axes
state anywhere.
"""

from __future__ import annotations

import math

import numpy as np

from .artists import (
    Annotation, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, HLine, Image, Line2D, LineCollection, Pie, PolyCollection,
    Polygon, QuadMesh, Quiver, ScatterCollection, Span, Stem, Text, Violin,
    VLine,
)
from .colors import Normalize, apply_colormap, get_cmap


def _gaussian_kde(data, grid):
    """Simple Gaussian KDE (Silverman bandwidth) evaluated on ``grid``."""
    data = np.asarray(data, float)
    n = data.size
    std = data.std(ddof=1) if n > 1 else 1.0
    bw = 1.06 * (std or 1.0) * n ** (-1 / 5)
    if bw == 0:
        bw = 1.0
    u = (grid[:, None] - data[None, :]) / bw
    k = np.exp(-0.5 * u * u) / np.sqrt(2 * np.pi)
    return k.sum(axis=1) / (n * bw)


class Axes:
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
        self._tick_overrides = {}   # per-axes tick style (Style field -> value)
        self._xlabel = ""
        self._ylabel = ""
        self._title = ""
        self._grid = False
        self._color_idx = 0

        self._xscale = "linear"
        self._yscale = "linear"
        self._aspect = None        # None='auto'; 1.0='equal'; float=y/x ratio
        self._axis_off = False
        self._subplotspec = None   # (nrows, ncols, index) for tight_layout

        # Colorbar bookkeeping.
        self._is_colorbar = False
        self._cbar_source = None

    # -- style / color cycle ------------------------------------------------
    def _next_color(self):
        cycle = self.style.color_cycle
        color = cycle[self._color_idx % len(cycle)]
        self._color_idx += 1
        return color

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
             label=None, alpha=1.0, values=None):
        """Plot ``y`` or ``x, y`` as a line. Returns the :class:`Line2D`.

        ``values`` is an optional ``{name: array}`` of extra per-point
        dimensions (e.g. ``z``) surfaced when a point is picked interactively.
        """
        if len(args) == 1:
            y = np.asarray(args[0], dtype=float)
            x = np.arange(y.size, dtype=float)
        elif len(args) >= 2:
            x = np.asarray(args[0], dtype=float)
            y = np.asarray(args[1], dtype=float)
        else:
            raise TypeError("plot() requires y or x, y")

        line = Line2D(
            x, y,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha, values=values,
        )
        self.artists.append(line)
        return line

    def scatter(self, x, y, s=None, c=None, color=None, marker="o",
                label=None, alpha=1.0, cmap="viridis", norm=None,
                vmin=None, vmax=None, values=None):
        """Scatter ``y`` vs ``x``. ``c`` maps values through ``cmap``.

        ``values`` is an optional ``{name: array}`` of extra per-point
        dimensions (e.g. ``z`` or a 4th value) surfaced by point picking; the
        color dimension ``c`` is included automatically.
        """
        if norm is None and (vmin is not None or vmax is not None):
            norm = Normalize(vmin, vmax)
        coll = ScatterCollection(
            x, y,
            s=self.style.marker_size if s is None else s,
            color=self._resolve_color(color) if c is None else None,
            marker=marker, label=label, alpha=alpha,
            c=c, cmap=cmap, norm=norm, values=values,
        )
        self.artists.append(coll)
        return coll

    def plot_frames(self, x, Y, slider_values=None, slider_label="frame",
                    shared=True, slider_group=None,
                    color=None, linewidth=None, linestyle="-", label=None,
                    alpha=1.0):
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
        self.artists.append(art)
        self.figure._register_slider(
            unit, index, Y.shape[0], slider_values, slider_label,
            is_global, axes_key,
        )
        return art

    def pcolormesh(self, *args, cmap="viridis", norm=None, vmin=None, vmax=None):
        """Pseudocolor plot of a 2-D array.

        Signatures: ``pcolormesh(C)`` or ``pcolormesh(X, Y, C)``.
        """
        if len(args) == 1:
            X = Y = None
            C = args[0]
        elif len(args) == 3:
            X, Y, C = args
        else:
            raise TypeError("pcolormesh() takes C or X, Y, C")

        mesh = QuadMesh(X, Y, C, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax)
        self.artists.append(mesh)
        return mesh

    def bar(self, x, height, width=0.8, bottom=0.0, color=None, edgecolor=None,
            linewidth=0.8, label=None, alpha=1.0):
        """Vertical bar chart."""
        b = Bars(x, height, width, bottom, "vertical",
                 color=self._resolve_color(color), edgecolor=edgecolor,
                 linewidth=linewidth, label=label, alpha=alpha)
        self.artists.append(b)
        return b

    def barh(self, y, width, height=0.8, left=0.0, color=None, edgecolor=None,
             linewidth=0.8, label=None, alpha=1.0):
        """Horizontal bar chart."""
        b = Bars(y, width, height, left, "horizontal",
                 color=self._resolve_color(color), edgecolor=edgecolor,
                 linewidth=linewidth, label=label, alpha=alpha)
        self.artists.append(b)
        return b

    def hist(self, data, bins=10, range=None, color=None, edgecolor="#ffffff",
             label=None, alpha=1.0, density=False):
        """Histogram. Returns ``(counts, edges, bars)``."""
        counts, edges = np.histogram(np.asarray(data, float), bins=bins,
                                     range=range, density=density)
        centers = (edges[:-1] + edges[1:]) / 2.0
        widths = np.diff(edges)
        b = Bars(centers, counts, widths, 0.0, "vertical",
                 color=self._resolve_color(color), edgecolor=edgecolor,
                 linewidth=0.6, label=label, alpha=alpha)
        self.artists.append(b)
        return counts, edges, b

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

    def fill_between(self, x, y1, y2=0.0, color=None, alpha=0.4, label=None):
        """Fill the area between ``y1`` and ``y2``."""
        fb = FillBetween(x, y1, y2, color=self._resolve_color(color),
                         alpha=alpha, label=label)
        self.artists.append(fb)
        return fb

    def fill_betweenx(self, y, x1, x2=0.0, color=None, alpha=0.4, label=None):
        """Fill the horizontal area between ``x1`` and ``x2`` across ``y``."""
        y = np.asarray(y, float)
        x1 = np.broadcast_to(np.asarray(x1, float), y.shape)
        x2 = np.broadcast_to(np.asarray(x2, float), y.shape)
        px = np.concatenate([x1, x2[::-1]])
        py = np.concatenate([y, y[::-1]])
        p = Polygon(px, py, color=self._resolve_color(color), alpha=alpha,
                    label=label)
        self.artists.append(p)
        return p

    def fill(self, x, y, color=None, alpha=1.0, edgecolor=None, linewidth=0.0,
             label=None):
        """Fill an arbitrary polygon given by vertices ``x``/``y``."""
        p = Polygon(x, y, color=self._resolve_color(color), alpha=alpha,
                    edgecolor=edgecolor, linewidth=linewidth, label=label)
        self.artists.append(p)
        return p

    def hlines(self, y, xmin, xmax, color=None, linewidth=None, linestyle="-",
               label=None, alpha=1.0):
        """Draw horizontal line segments at each ``y`` from ``xmin`` to ``xmax``."""
        y = np.atleast_1d(np.asarray(y, float))
        xmin = np.broadcast_to(np.asarray(xmin, float), y.shape)
        xmax = np.broadcast_to(np.asarray(xmax, float), y.shape)
        segs = np.column_stack([xmin, y, xmax, y])
        lc = LineCollection(
            segs, color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha)
        self.artists.append(lc)
        return lc

    def vlines(self, x, ymin, ymax, color=None, linewidth=None, linestyle="-",
               label=None, alpha=1.0):
        """Draw vertical line segments at each ``x`` from ``ymin`` to ``ymax``."""
        x = np.atleast_1d(np.asarray(x, float))
        ymin = np.broadcast_to(np.asarray(ymin, float), x.shape)
        ymax = np.broadcast_to(np.asarray(ymax, float), x.shape)
        segs = np.column_stack([x, ymin, x, ymax])
        lc = LineCollection(
            segs, color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha)
        self.artists.append(lc)
        return lc

    def stem(self, x, y=None, baseline=0.0, linecolor=None, markercolor=None,
             label=None):
        """Stem plot."""
        if y is None:
            y = np.asarray(x, float)
            x = np.arange(y.size, dtype=float)
        lc = self._resolve_color(linecolor)
        s = Stem(x, y, baseline, linecolor=lc,
                 markercolor=self._resolve_color(markercolor) if markercolor else lc,
                 label=label)
        self.artists.append(s)
        return s

    def errorbar(self, x, y, yerr=None, xerr=None, color=None, marker="o",
                 markersize=None, capsize=3.0, linestyle="-", linewidth=None,
                 label=None, alpha=1.0):
        """Line/markers with error bars."""
        eb = ErrorBar(
            x, y, yerr=yerr, xerr=xerr, color=self._resolve_color(color),
            marker=marker,
            markersize=self.style.marker_size if markersize is None else markersize,
            capsize=capsize, linestyle=linestyle,
            linewidth=self.style.line_width if linewidth is None else linewidth,
            label=label, alpha=alpha)
        self.artists.append(eb)
        return eb

    def imshow(self, A, cmap="viridis", norm=None, vmin=None, vmax=None,
               extent=None, origin="upper", alpha=1.0, label=None):
        """Display an image / 2-D array."""
        im = Image(A, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax, extent=extent,
                   origin=origin, alpha=alpha, label=label)
        self.artists.append(im)
        return im

    def matshow(self, A, cmap="viridis", norm=None, vmin=None, vmax=None):
        """Display a matrix as an image (origin at top, square cells)."""
        im = self.imshow(A, cmap=cmap, norm=norm, vmin=vmin, vmax=vmax,
                         origin="upper")
        self.set_aspect("equal")
        return im

    def spy(self, A):
        """Show the sparsity pattern of ``A`` -- nonzero entries drawn dark."""
        nz = (np.asarray(A, float) != 0).astype(float)
        im = self.imshow(nz, cmap="gray_r", origin="upper", vmin=0, vmax=1)
        self.set_aspect("equal")
        return im

    def pie(self, values, labels=None, colors=None, startangle=90.0, radius=1.0,
            autopct=None):
        """Pie chart. Hides the axis and fixes an equal-aspect square view."""
        n = len(values)
        if colors is None:
            cyc = self.style.color_cycle
            colors = [cyc[i % len(cyc)] for i in range(n)]
        p = Pie(values, colors, labels=labels, startangle=startangle,
                radius=radius, autopct=autopct)
        self.artists.append(p)
        self.set_axis_off()
        self.set_xlim(-1.3, 1.3)
        self.set_ylim(-1.3, 1.3)
        return p

    def boxplot(self, data, positions=None, widths=0.5, color=None,
                orientation="vertical", label=None):
        """Box-and-whisker plot of one or more datasets."""
        if isinstance(data, np.ndarray) and data.ndim == 1:
            data = [data]
        data = [np.asarray(d, float) for d in data]
        if positions is None:
            positions = np.arange(1, len(data) + 1)
        stats = []
        for d in data:
            q1, med, q3 = np.percentile(d, [25, 50, 75])
            iqr = q3 - q1
            lo_in = d[d >= q1 - 1.5 * iqr]
            hi_in = d[d <= q3 + 1.5 * iqr]
            lo = lo_in.min() if lo_in.size else q1
            hi = hi_in.max() if hi_in.size else q3
            fliers = d[(d < lo) | (d > hi)]
            stats.append({"q1": q1, "med": med, "q3": q3, "lo": lo, "hi": hi,
                          "fliers": fliers})
        b = BoxPlot(positions, stats, widths, color=self._resolve_color(color),
                    orientation=orientation, label=label)
        self.artists.append(b)
        return b

    def violinplot(self, data, positions=None, widths=0.5, color=None,
                   orientation="vertical", label=None, points=100):
        """Violin plot (kernel-density silhouettes)."""
        if isinstance(data, np.ndarray) and data.ndim == 1:
            data = [data]
        data = [np.asarray(d, float) for d in data]
        if positions is None:
            positions = np.arange(1, len(data) + 1)
        grids, halfwidths = [], []
        for d in data:
            grid = np.linspace(d.min(), d.max(), points)
            dens = _gaussian_kde(d, grid)
            peak = dens.max() or 1.0
            grids.append(grid)
            halfwidths.append(dens / peak * (widths / 2.0))
        v = Violin(positions, grids, halfwidths,
                   color=self._resolve_color(color), orientation=orientation,
                   label=label)
        self.artists.append(v)
        return v

    def eventplot(self, positions, lineoffsets=None, linelengths=0.8, color=None,
                  orientation="horizontal", label=None):
        """Raster of event lines (one row per sequence)."""
        if np.ndim(positions[0]) == 0:
            positions = [positions]
        rows = [np.asarray(r, float) for r in positions]
        if lineoffsets is None:
            lineoffsets = np.arange(1, len(rows) + 1)
        e = EventPlot(rows, lineoffsets, linelengths, color=self._resolve_color(color),
                      orientation=orientation, label=label)
        self.artists.append(e)
        return e

    def quiver(self, X, Y, U, V, scale=None, color=None, label=None):
        """Field of arrows. ``scale`` maps (U, V) to data units (auto if None)."""
        X = np.asarray(X, float); Y = np.asarray(Y, float)
        U = np.asarray(U, float); V = np.asarray(V, float)
        if scale is None:
            mag = np.hypot(U, V)
            mmax = mag.max() or 1.0
            span = max(X.max() - X.min(), Y.max() - Y.min()) or 1.0
            n = max(U.size, 1)
            scale = 0.9 * (span / np.sqrt(n)) / mmax
        q = Quiver(X, Y, U, V, scale, color=self._resolve_color(color), label=label)
        self.artists.append(q)
        return q

    def contour(self, *args, levels=8, colors=None, cmap="viridis", label=None):
        """Contour lines. ``contour(Z)`` or ``contour(x, y, Z)``."""
        if len(args) == 1:
            Z = np.asarray(args[0], float)
            x = np.arange(Z.shape[1], dtype=float)
            y = np.arange(Z.shape[0], dtype=float)
        elif len(args) == 3:
            x, y, Z = (np.asarray(a, float) for a in args)
        else:
            raise TypeError("contour() takes Z or x, y, Z")
        if np.ndim(levels) == 0:
            levels = np.linspace(Z.min(), Z.max(), int(levels) + 2)[1:-1]
        if colors is None:
            lut = get_cmap(cmap)
            idx = np.linspace(0, 255, len(levels)).astype(int)
            colors = ["#%02x%02x%02x" % tuple(lut[i]) for i in idx]
        elif isinstance(colors, str):
            colors = [colors]
        c = Contour(x, y, Z, levels, colors, label=label)
        self.artists.append(c)
        return c

    def contourf(self, *args, levels=8, cmap="viridis", vmin=None, vmax=None,
                 alpha=1.0, label=None):
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
            x, y, Z = (np.asarray(a, float) for a in args)
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
        self.artists.append(img)
        return img

    def hexbin(self, x, y, gridsize=20, cmap="viridis", mincnt=1, label=None):
        """Hexagonal 2-D binning of points ``x``/``y`` (colormapped counts).

        Returns a mappable collection of hexagons (works with ``fig.colorbar``).
        """
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        verts, counts = _hexbin(x, y, gridsize, mincnt)
        lut = get_cmap(cmap)
        norm = Normalize()
        norm.autoscale_none(counts) if len(counts) else None
        facecolors = apply_colormap(counts, lut, norm)[:, :3] if len(counts) else []
        pc = PolyCollection(verts, facecolors, label=label)
        pc.lut, pc.norm = lut, norm      # make it a colorbar mappable
        self.artists.append(pc)
        return pc

    def hist2d(self, x, y, bins=20, range=None, cmap="viridis"):
        """2-D histogram rendered as an image. Returns ``(counts, image)``."""
        counts, xe, ye = np.histogram2d(np.asarray(x, float), np.asarray(y, float),
                                        bins=bins, range=range)
        # counts is (nx, ny) indexed [xbin, ybin]; image rows are y, cols x.
        im = self.imshow(counts.T, cmap=cmap, origin="lower",
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
             rotation=0.0):
        """Draw text ``s`` at data coordinates ``(x, y)``."""
        t = Text(x, y, s, color=color or self.style.text_color,
                 size=self.style.font_size if fontsize is None else fontsize,
                 ha=ha, va=va, rotation=rotation)
        self.artists.append(t)
        return t

    def annotate(self, text, xy, xytext=None, color=None, fontsize=None,
                 ha="left", va="baseline", arrowprops=None):
        """Annotate the point ``xy`` with ``text`` placed at ``xytext``.

        Pass ``arrowprops={"color": ...}`` (or ``{}``) to draw an arrow from the
        text to ``xy``.
        """
        a = Annotation(text, xy, xytext, color=color or self.style.text_color,
                       size=self.style.font_size if fontsize is None else fontsize,
                       ha=ha, va=va, arrowprops=arrowprops)
        self.artists.append(a)
        return a

    def set_axis_off(self):
        """Hide the spines, ticks, grid, and axis labels (keep the title)."""
        self._axis_off = True

    def axvline(self, x, color=None, linewidth=None, linestyle="--",
                label=None, alpha=1.0):
        """Draw a vertical line at data coordinate ``x`` (like matplotlib)."""
        vl = VLine(
            x,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha,
        )
        self.artists.append(vl)
        return vl

    def axhline(self, y, color=None, linewidth=None, linestyle="--",
                label=None, alpha=1.0):
        """Draw a horizontal line at data coordinate ``y`` (like matplotlib)."""
        hl = HLine(
            y,
            color=self._resolve_color(color),
            linewidth=self.style.line_width if linewidth is None else linewidth,
            linestyle=linestyle, label=label, alpha=alpha,
        )
        self.artists.append(hl)
        return hl

    def axvspan(self, xmin, xmax, color="#1f77b4", alpha=0.3, label=None):
        """Shade a vertical band between x=``xmin`` and x=``xmax``."""
        sp = Span(xmin, xmax, "vertical", color=color, alpha=alpha, label=label)
        self.artists.append(sp)
        return sp

    def axhspan(self, ymin, ymax, color="#1f77b4", alpha=0.3, label=None):
        """Shade a horizontal band between y=``ymin`` and y=``ymax``."""
        sp = Span(ymin, ymax, "horizontal", color=color, alpha=alpha, label=label)
        self.artists.append(sp)
        return sp

    # -- limits / labels ----------------------------------------------------
    def set_xlim(self, left, right=None):
        self._xlim = (left, right) if right is not None else tuple(left)
        return self._xlim

    def set_ylim(self, bottom, top=None):
        self._ylim = (bottom, top) if top is not None else tuple(bottom)
        return self._ylim

    def tick_params(self, axis="both", labelsize=None, length=None, width=None,
                    color=None, labelcolor=None):
        """Style this axes' tick marks and labels (a subset of matplotlib's).

        ``labelsize`` (tick-label font), ``length``/``width`` (tick marks),
        ``color`` (mark color), ``labelcolor`` (label color). The ``axis``
        argument is accepted for compatibility but applies to both axes.
        """
        ov = self._tick_overrides
        if labelsize is not None:
            ov["tick_label_size"] = labelsize
        if length is not None:
            ov["tick_size"] = length
        if width is not None:
            ov["tick_width"] = width
        if color is not None:
            ov["spine_color"] = color        # tick-mark color (box spine unchanged)
        if labelcolor is not None:
            ov["text_color"] = labelcolor
        return self

    def set_xbound(self, lower, upper):
        """Set the x data limits (alias of :meth:`set_xlim`)."""
        return self.set_xlim(lower, upper)

    def set_ybound(self, lower, upper):
        """Set the y data limits (alias of :meth:`set_ylim`)."""
        return self.set_ylim(lower, upper)

    def margins(self, m=None, x=None, y=None):
        """Add fractional padding around the autoscaled data (like matplotlib).

        ``margins(0.1)`` pads both axes 10%; per-axis via ``x=``/``y=``.
        """
        mx = x if x is not None else m
        my = y if y is not None else m
        (x0, x1), (y0, y1) = self._resolved_limits()
        if mx:
            dx = (x1 - x0) * mx
            self.set_xlim(x0 - dx, x1 + dx)
        if my:
            dy = (y1 - y0) * my
            self.set_ylim(y0 - dy, y1 + dy)
        return self

    def set_xticks(self, ticks):
        """Set explicit x tick locations. Pass ``[]`` to hide ticks."""
        self._xticks = None if ticks is None else np.asarray(ticks, dtype=float)

    def set_yticks(self, ticks):
        """Set explicit y tick locations. Pass ``[]`` to hide ticks."""
        self._yticks = None if ticks is None else np.asarray(ticks, dtype=float)

    def set_xticklabels(self, labels):
        """Set explicit x tick label strings (pair with :meth:`set_xticks`)."""
        self._xticklabels = None if labels is None else [str(s) for s in labels]

    def set_yticklabels(self, labels):
        """Set explicit y tick label strings (pair with :meth:`set_yticks`)."""
        self._yticklabels = None if labels is None else [str(s) for s in labels]

    def invert_xaxis(self):
        """Reverse the x-axis direction (larger values to the left)."""
        self._xinverted = not self._xinverted

    def invert_yaxis(self):
        """Reverse the y-axis direction (larger values at the bottom)."""
        self._yinverted = not self._yinverted

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

    def set_xlabel(self, label):
        self._xlabel = label

    def set_ylabel(self, label):
        self._ylabel = label

    def set_title(self, title):
        self._title = title

    def grid(self, visible=True):
        self._grid = bool(visible)

    def legend(self, loc="upper right", ncol=1, title=None):
        """Enable a legend (drawn from artists that have a ``label``).

        ``loc`` is a matplotlib-style corner/edge name (e.g. ``"upper left"``,
        ``"lower center"``, ``"center"``; ``"best"`` maps to upper right).
        ``ncol`` lays the entries out in that many columns; ``title`` adds a
        heading row.
        """
        self._show_legend = True
        self._legend_loc = loc
        self._legend_ncol = max(1, int(ncol))
        self._legend_title = title

    _show_legend = False
    _legend_loc = "upper right"
    _legend_ncol = 1
    _legend_title = None

    # -- autoscaling --------------------------------------------------------
    def get_xlim(self):
        return self._resolved_limits()[0]

    def get_ylim(self):
        return self._resolved_limits()[1]

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
            has_mesh = has_mesh or any(isinstance(a, QuadMesh) for a in ax.artists)
        if not np.isfinite(lo) or not np.isfinite(hi):
            lo, hi = 0.0, 1.0
        return lo, hi, has_mesh

    def _resolved_limits(self):
        """Return ``((xmin, xmax), (ymin, ymax))``, autoscaling if unset.

        With ``sharex``/``sharey`` the autoscale spans every axes in the share
        group so linked plots line up.
        """
        xlim, ylim = self._xlim, self._ylim
        if xlim is not None and ylim is not None:
            return xlim, ylim

        xgroup = self._sharex_group or [self]
        ygroup = self._sharey_group or [self]
        axmin, axmax, mesh_x = self._group_bounds(xgroup, 0)
        aymin, aymax, mesh_y = self._group_bounds(ygroup, 2)
        px = _pad(axmin, axmax, self._xscale, tight=mesh_x)
        py = _pad(aymin, aymax, self._yscale, tight=mesh_y)
        rx, ry = (xlim or px), (ylim or py)
        # A twin overlay inherits the shared axis' limits from its parent.
        if self._twin_of is not None:
            pxl, pyl = self._twin_of._resolved_limits()
            if self._twin_shared == "x":
                rx = pxl
            else:
                ry = pyl
        return rx, ry


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
    """
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    nx = max(int(gridsize), 1)
    dx = (xmax - xmin) / nx or 1.0
    ny = max(int(nx * (ymax - ymin) / (xmax - xmin) / 1.732) if xmax > xmin else 1, 1)
    dy = (ymax - ymin) / ny or 1.0

    sx = (x - xmin) / dx
    sy = (y - ymin) / dy
    i1 = np.round(sx).astype(int); j1 = np.round(sy).astype(int)      # grid 1
    i2 = np.floor(sx).astype(int); j2 = np.floor(sy).astype(int)      # grid 2 (+half)
    d1 = (sx - i1) ** 2 + (sy - j1) ** 2
    d2 = (sx - (i2 + 0.5)) ** 2 + (sy - (j2 + 0.5)) ** 2
    use1 = d1 <= d2

    from collections import Counter
    cells = Counter()
    for k in range(len(x)):
        if use1[k]:
            cells[(int(i1[k]), int(j1[k]), 0)] += 1
        else:
            cells[(int(i2[k]), int(j2[k]), 1)] += 1

    # Hexagon vertex offsets (pointy-top), scaled to the cell size.
    ang = np.pi / 180 * (60 * np.arange(6) + 30)
    hx = (dx / 1.732) * np.cos(ang)
    hy = (dy / 1.5) * np.sin(ang)

    verts, counts = [], []
    for (i, j, g), c in cells.items():
        if c < mincnt:
            continue
        cx = xmin + i * dx + (dx / 2 if g else 0)
        cy = ymin + j * dy + (dy / 2 if g else 0)
        verts.append(np.column_stack([cx + hx, cy + hy]))
        counts.append(c)
    return verts, np.asarray(counts, float)


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
