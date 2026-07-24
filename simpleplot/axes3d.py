"""3-D axes: (x, y, z) plotting on top of the 2-D Cartesian core.

Like :class:`~simpleplot.polar.PolarAxes`, an :class:`Axes3D` is an ordinary
:class:`~simpleplot.axes.Axes` with equal aspect and the rectangular frame off.
It normalizes data into a unit cube, applies an orthographic camera set by
``elev``/``azim``, and emits the projected geometry through existing artists
(``scatter``/``plot``/``PolyCollection``/``LineCollection``). The renderer never
learns that 3-D exists.

Because the camera and the per-axis normalization both change what every point
projects to, the raw 3-D data is *retained* as a list of drawing commands and
the whole scene is reprojected on any change -- so ``view_init`` works after
plotting, and mixing series with different ranges stays consistent.

Supported: ``scatter``/``scatter3D``, ``plot``/``plot3D`` (lines),
``plot_surface`` (depth-sorted, colormapped), ``plot_wireframe``; plus
``view_init``, ``set_xlim3d``/``ylim3d``/``zlim3d`` and ``set_zlabel``.
"""

from __future__ import annotations

import numpy as np

from .axes import Axes
from .artists import LineCollection, PolyCollection, Text
from .colors import Normalize, apply_colormap, get_cmap


class Axes3D(Axes):
    def __init__(self, figure, rect):
        super().__init__(figure, rect)
        self._is_3d = True
        self.set_aspect("equal")
        self.set_axis_off()
        self.elev = 30.0
        self.azim = -60.0
        self._zlabel = ""
        self._xlim3d = self._ylim3d = self._zlim3d = None
        self._commands = []          # retained (kind, arrays, kwargs) to reproject
        self._frame_artists = []

    # -- camera / limits ----------------------------------------------------
    def view_init(self, elev=None, azim=None):
        """Set the camera elevation / azimuth (degrees) and reproject."""
        if elev is not None:
            self.elev = float(elev)
        if azim is not None:
            self.azim = float(azim)
        self._rebuild()
        return self

    def set_zlabel(self, text):
        self._zlabel = text
        self._rebuild()
        return self

    def set_xlim3d(self, lo, hi):
        self._xlim3d = (float(lo), float(hi)); self._rebuild(); return self

    def set_ylim3d(self, lo, hi):
        self._ylim3d = (float(lo), float(hi)); self._rebuild(); return self

    def set_zlim3d(self, lo, hi):
        self._zlim3d = (float(lo), float(hi)); self._rebuild(); return self

    # -- data-space limits over every retained command ----------------------
    def _axis_bounds(self):
        xs, ys, zs = [], [], []
        for kind, arrs, _ in self._commands:
            x, y, z = arrs[:3]
            xs.append(np.ravel(x)); ys.append(np.ravel(y)); zs.append(np.ravel(z))
        if not xs:
            return (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)

        def span(parts, override):
            if override is not None:
                return override
            v = np.concatenate(parts)
            v = v[np.isfinite(v)]
            if v.size == 0:
                return (0.0, 1.0)
            lo, hi = float(v.min()), float(v.max())
            return (lo, hi) if hi > lo else (lo - 0.5, hi + 0.5)

        return (span(xs, self._xlim3d), span(ys, self._ylim3d),
                span(zs, self._zlim3d))

    def _normalizer(self):
        (x0, x1), (y0, y1), (z0, z1) = self._axis_bounds()

        def norm(x, y, z):
            xn = (np.asarray(x, float) - (x0 + x1) / 2) / ((x1 - x0) or 1.0)
            yn = (np.asarray(y, float) - (y0 + y1) / 2) / ((y1 - y0) or 1.0)
            zn = (np.asarray(z, float) - (z0 + z1) / 2) / ((z1 - z0) or 1.0)
            return xn, yn, zn

        return norm, ((x0, x1), (y0, y1), (z0, z1))

    # -- orthographic projection of normalized (cube) coordinates -----------
    def _project_norm(self, xn, yn, zn):
        a, e = np.radians(self.azim), np.radians(self.elev)
        ca, sa, ce, se = np.cos(a), np.sin(a), np.cos(e), np.sin(e)
        sx = -xn * sa + yn * ca
        sy = -xn * ca * se - yn * sa * se + zn * ce
        depth = xn * ca * ce + yn * sa * ce + zn * se
        return sx, sy, depth

    # -- public plotting: record a command, then rebuild --------------------
    def scatter(self, xs, ys, zs, **kwargs):
        """Scatter points at ``(xs, ys, zs)``."""
        # Resolve the cycle color once, now -- the scene is reprojected on every
        # camera/data change, so an unresolved color=None would drift each time.
        if kwargs.get("c") is None:
            kwargs["color"] = self._resolve_color(kwargs.get("color"))
        self._commands.append(("scatter", (np.asarray(xs, float),
                                           np.asarray(ys, float),
                                           np.asarray(zs, float)), kwargs))
        return self._rebuild()

    scatter3D = scatter

    def plot(self, xs, ys, zs, **kwargs):
        """Plot a 3-D polyline through ``(xs, ys, zs)``."""
        kwargs["color"] = self._resolve_color(kwargs.get("color"))
        self._commands.append(("plot", (np.asarray(xs, float),
                                        np.asarray(ys, float),
                                        np.asarray(zs, float)), kwargs))
        return self._rebuild()

    plot3D = plot

    def plot_surface(self, X, Y, Z, cmap="viridis", edgecolor=None, alpha=1.0,
                     **kwargs):
        """Colormapped surface over the grid ``X``/``Y``/``Z`` (all 2-D)."""
        self._commands.append(("surface", (np.asarray(X, float), np.asarray(Y, float),
                                           np.asarray(Z, float)),
                               dict(cmap=cmap, edgecolor=edgecolor, alpha=alpha,
                                    **kwargs)))
        return self._rebuild()

    def plot_wireframe(self, X, Y, Z, color=None, linewidth=0.6, **kwargs):
        """Wireframe over the grid ``X``/``Y``/``Z`` (all 2-D)."""
        color = self._resolve_color(color)      # resolve once (see scatter)
        self._commands.append(("wire", (np.asarray(X, float), np.asarray(Y, float),
                                        np.asarray(Z, float)),
                               dict(color=color, linewidth=linewidth, **kwargs)))
        return self._rebuild()

    # -- scene rebuild ------------------------------------------------------
    def _rebuild(self):
        """Clear and re-emit the whole scene under the current camera/limits."""
        self.artists = []
        self._frame_artists = []
        norm, bounds = self._normalizer()

        self._build_frame(norm, bounds)          # drawn first -> behind the data

        last = None
        for kind, arrs, kwargs in self._commands:
            if kind == "scatter":
                sx, sy, _ = self._project_norm(*norm(*arrs))
                last = Axes.scatter(self, sx, sy, **kwargs)
            elif kind == "plot":
                sx, sy, _ = self._project_norm(*norm(*arrs))
                last = Axes.plot(self, sx, sy, **kwargs)
            elif kind == "surface":
                last = self._emit_surface(norm, arrs, kwargs)
            elif kind == "wire":
                last = self._emit_wire(norm, arrs, kwargs)

        pad = 0.75
        Axes.set_xlim(self, -pad, pad)
        Axes.set_ylim(self, -pad, pad)
        return last if last is not None else self

    def _emit_surface(self, norm, arrs, kwargs):
        X, Y, Z = arrs
        m, n = Z.shape
        xn, yn, zn = norm(X, Y, Z)
        sx, sy, depth = self._project_norm(xn, yn, zn)

        verts, face_z, face_depth = [], [], []
        for i in range(m - 1):
            for j in range(n - 1):
                idx = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
                verts.append(np.array([[sx[a, b], sy[a, b]] for a, b in idx]))
                face_z.append(np.mean([Z[a, b] for a, b in idx]))
                face_depth.append(np.mean([depth[a, b] for a, b in idx]))

        lut = get_cmap(kwargs.get("cmap", "viridis"))
        znorm = Normalize()
        if not verts:                            # grid smaller than 2x2 -> no faces
            pc = PolyCollection([], [], label=kwargs.get("label"))
            pc.lut, pc.norm = lut, znorm
            self.artists.append(pc)
            return pc

        order = np.argsort(face_depth)           # farthest first (painter's order)
        verts = [verts[k] for k in order]
        face_z = np.array(face_z)[order]

        znorm.autoscale_none(face_z)
        facecolors = apply_colormap(face_z, lut, znorm)[:, :3]
        pc = PolyCollection(verts, facecolors,
                            edgecolor=kwargs.get("edgecolor"),
                            alpha=kwargs.get("alpha", 1.0),
                            label=kwargs.get("label"))
        pc.lut, pc.norm = lut, znorm             # colorbar mappable
        self.artists.append(pc)
        return pc

    def _emit_wire(self, norm, arrs, kwargs):
        X, Y, Z = arrs
        sx, sy, _ = self._project_norm(*norm(X, Y, Z))
        segs = []
        # lines along each row, then each column
        for i in range(sx.shape[0]):
            for j in range(sx.shape[1] - 1):
                segs.append((sx[i, j], sy[i, j], sx[i, j + 1], sy[i, j + 1]))
        for j in range(sx.shape[1]):
            for i in range(sx.shape[0] - 1):
                segs.append((sx[i, j], sy[i, j], sx[i + 1, j], sy[i + 1, j]))
        lc = LineCollection(np.array(segs, float),
                            color=kwargs.get("color"),      # resolved at record time
                            linewidth=kwargs.get("linewidth", 0.6))
        self.artists.append(lc)
        return lc

    # -- 3-D frame (cube edges + axis labels + end ticks) -------------------
    def _build_frame(self, norm, bounds):
        (x0, x1), (y0, y1), (z0, z1) = bounds
        # 8 cube corners in normalized space
        corners = {}
        for cx in (-0.5, 0.5):
            for cy in (-0.5, 0.5):
                for cz in (-0.5, 0.5):
                    px, py, _ = self._project_norm(np.array([cx]), np.array([cy]),
                                                   np.array([cz]))
                    corners[(cx, cy, cz)] = (float(px[0]), float(py[0]))

        edges = [
            # bottom square
            ((-.5, -.5, -.5), (.5, -.5, -.5)), ((.5, -.5, -.5), (.5, .5, -.5)),
            ((.5, .5, -.5), (-.5, .5, -.5)), ((-.5, .5, -.5), (-.5, -.5, -.5)),
            # top square
            ((-.5, -.5, .5), (.5, -.5, .5)), ((.5, -.5, .5), (.5, .5, .5)),
            ((.5, .5, .5), (-.5, .5, .5)), ((-.5, .5, .5), (-.5, -.5, .5)),
            # verticals
            ((-.5, -.5, -.5), (-.5, -.5, .5)), ((.5, -.5, -.5), (.5, -.5, .5)),
            ((.5, .5, -.5), (.5, .5, .5)), ((-.5, .5, -.5), (-.5, .5, .5)),
        ]
        segs = [(*corners[a], *corners[b]) for a, b in edges]
        lc = LineCollection(np.array(segs, float), color="#c0c0c0", linewidth=0.8)
        self.artists.append(lc)
        self._frame_artists.append(lc)

        size = self.style.tick_label_size
        lbl_size = self.style.label_size

        def txt(pt, s, sz):
            t = Text(pt[0], pt[1], s, color="#555555", size=sz,
                     ha="center", va="center")
            self.artists.append(t)
            self._frame_artists.append(t)

        def fmt(v):
            return ("%.3g" % v)

        # one representative edge per axis: label its name at the midpoint and
        # its data min/max at the two ends.
        axis_edges = [
            (self._xlabel or "x", (-.5, -.5, -.5), (.5, -.5, -.5), (x0, x1)),
            (self._ylabel or "y", (.5, -.5, -.5), (.5, .5, -.5), (y0, y1)),
            (self._zlabel or "z", (-.5, -.5, -.5), (-.5, -.5, .5), (z0, z1)),
        ]
        for name, a, b, (lo, hi) in axis_edges:
            pa, pb = corners[a], corners[b]
            mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            out = (mid[0] + (mid[0]) * 0.12, mid[1] + (mid[1]) * 0.12 - 0.04)
            txt(_offset(pa, pb, 0.12), fmt(lo), size)
            txt(_offset(pb, pa, 0.12), fmt(hi), size)
            txt(out, name, lbl_size)


def _offset(p, other, frac):
    """Push point ``p`` a little away from segment ``p->other`` (for labels)."""
    return (p[0] - (other[0] - p[0]) * frac, p[1] - (other[1] - p[1]) * frac)
