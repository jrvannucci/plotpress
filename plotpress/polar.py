"""Polar axes: (theta, r) plotting on top of the Cartesian core.

A :class:`PolarAxes` is an ordinary :class:`~plotpress.axes.Axes` running with
equal aspect and the rectangular frame turned off. It projects ``(theta, r)``
data to ``(x, y) = (r cos theta, r sin theta)`` before handing it to the normal
plotting methods, and it builds its own polar frame -- radial grid circles,
angular spokes, and tick labels -- entirely out of existing ``plot``/``text``
artists. Nothing in the SVG or raster renderer needs to know polar exists, in
the same spirit as ``violinplot``'s inner marks.

Supported so far: ``plot``, ``scatter``, ``fill`` (the plot types that make
sense on a polar grid), plus ``set_rmax``/``set_rlim``/``set_rticks``,
``set_thetagrids``, ``set_theta_direction`` and ``set_theta_zero_location``.
"""

from __future__ import annotations

import numpy as np

from .axes import Axes
from .ticker import nice_ticks

_ZERO_LOC = {"E": 0.0, "N": np.pi / 2, "W": np.pi, "S": -np.pi / 2}


def _fmt_r(v):
    return ("%g" % v)


class PolarAxes(Axes):
    def __init__(self, figure, rect):
        super().__init__(figure, rect)
        self._is_polar = True
        self.set_aspect("equal")
        self.set_axis_off()
        self._theta_direction = 1        # +1 counter-clockwise (matplotlib default)
        self._theta_offset = 0.0         # radians; where theta=0 points
        self._rmax = None                # None -> autoscale from data
        self._rmin = 0.0
        self._rticks = None              # None -> "nice" ticks
        self._thetagrids = None          # None -> 8 evenly spaced spokes
        self._rdata = []                 # r arrays seen, for autoscale
        self._frame_artists = []         # rebuilt whenever data or limits change

    # -- projection ---------------------------------------------------------
    def _project(self, theta, r):
        theta = np.asarray(theta, float) * self._theta_direction + self._theta_offset
        r = np.asarray(r, float)
        return r * np.cos(theta), r * np.sin(theta)

    def _track_r(self, r):
        r = np.asarray(r, float)
        if r.size:
            self._rdata.append(r)

    def _auto_rmax(self):
        vals = [np.nanmax(np.abs(r)) for r in self._rdata
                if r.size and np.isfinite(r).any()]
        return max(vals) if vals else None

    # -- plotting (project, then delegate to the Cartesian core) ------------
    def plot(self, theta, r, **kwargs):
        """Plot ``r`` versus ``theta`` (radians) as a polar line."""
        x, y = self._project(theta, r)
        self._track_r(r)
        line = super().plot(x, y, **kwargs)
        self._rebuild_frame()
        return line

    def scatter(self, theta, r, **kwargs):
        """Scatter ``r`` versus ``theta`` (radians)."""
        x, y = self._project(theta, r)
        self._track_r(r)
        coll = super().scatter(x, y, **kwargs)
        self._rebuild_frame()
        return coll

    def fill(self, theta, r, **kwargs):
        """Fill the polygon traced by ``(theta, r)``."""
        x, y = self._project(theta, r)
        self._track_r(r)
        poly = super().fill(x, y, **kwargs)
        self._rebuild_frame()
        return poly

    # -- polar limits / grid API -------------------------------------------
    def set_rmax(self, rmax):
        self._rmax = float(rmax)
        self._rebuild_frame()
        return self

    def set_rlim(self, rmin=None, rmax=None):
        if rmin is not None:
            self._rmin = float(rmin)
        if rmax is not None:
            self._rmax = float(rmax)
        self._rebuild_frame()
        return self

    def set_rticks(self, ticks):
        self._rticks = None if ticks is None else [float(t) for t in ticks]
        self._rebuild_frame()
        return self

    def set_thetagrids(self, angles):
        """Place angular gridlines at ``angles`` (degrees), or an int count."""
        if angles is None or np.ndim(angles) == 0:
            self._thetagrids = None if angles is None else int(angles)
        else:
            self._thetagrids = [float(a) for a in angles]
        self._rebuild_frame()
        return self

    def set_theta_direction(self, direction):
        """``+1``/``'counterclockwise'`` or ``-1``/``'clockwise'``."""
        if direction in (-1, "clockwise", "cw"):
            self._theta_direction = -1
        else:
            self._theta_direction = 1
        self._reproject()
        return self

    def set_theta_zero_location(self, loc):
        """Point ``theta=0`` at compass location ``'N'``/``'E'``/``'S'``/``'W'``."""
        self._theta_offset = _ZERO_LOC[loc]
        self._reproject()
        return self

    def set_theta_offset(self, offset):
        """Set the angle (radians) at which ``theta=0`` is drawn."""
        self._theta_offset = float(offset)
        self._reproject()
        return self

    # -- frame construction -------------------------------------------------
    def _reproject(self):
        # Changing orientation after data exists would need re-projecting every
        # artist; keep it simple and supported by requiring orientation to be set
        # before plotting.
        if self._rdata:
            raise RuntimeError(
                "set orientation (theta direction/zero location/offset) before "
                "plotting into a polar axes"
            )
        self._rebuild_frame()

    def _theta_positions(self):
        if isinstance(self._thetagrids, list):
            return np.radians(self._thetagrids)
        n = self._thetagrids if isinstance(self._thetagrids, int) else 8
        return np.arange(n) * (2 * np.pi / n)

    def _frame_add(self, artist):
        self._frame_artists.append(artist)
        return artist

    def _rebuild_frame(self):
        """Recompute the polar frame from current data/limit state.

        Frame artists are stripped and rebuilt each call, then moved ahead of the
        data artists so the grid sits behind the plot (matplotlib z-order).
        """
        frame_ids = set(map(id, self._frame_artists))
        self.artists = [a for a in self.artists if id(a) not in frame_ids]
        self._frame_artists = []

        rmax = self._rmax if self._rmax is not None else self._auto_rmax()
        if not rmax or not np.isfinite(rmax) or rmax <= 0:
            return

        ticks = (self._rticks if self._rticks is not None
                 else nice_ticks(0.0, rmax))
        ticks = [t for t in ticks if 0 < t <= rmax * 1.0001]

        ang = np.linspace(0.0, 2 * np.pi, 120)
        cos_a, sin_a = np.cos(ang), np.sin(ang)
        grid_c, edge_c, txt_c = "#d0d0d0", "#a0a0a0", "#555555"

        # radial grid circles + outer boundary
        for t in ticks:
            self._frame_add(Axes.plot(self, t * cos_a, t * sin_a,
                                      color=grid_c, linewidth=0.8))
        self._frame_add(Axes.plot(self, rmax * cos_a, rmax * sin_a,
                                  color=edge_c, linewidth=1.0))

        # angular spokes + degree labels
        size = self.style.tick_label_size
        for th in self._theta_positions():
            a = th * self._theta_direction + self._theta_offset
            ca, sa = np.cos(a), np.sin(a)
            self._frame_add(Axes.plot(self, [0.0, rmax * ca], [0.0, rmax * sa],
                                      color=grid_c, linewidth=0.8))
            deg = int(round(np.degrees(th))) % 360
            self._frame_add(self.text(rmax * 1.12 * ca, rmax * 1.12 * sa,
                                      f"{deg}°", ha="center", va="center",
                                      fontsize=size, color=txt_c))

        # radial tick labels, along a lightly off-axis spoke so they clear it
        la = 0.12 + self._theta_offset
        for t in ticks:
            self._frame_add(self.text(t * np.cos(la), t * np.sin(la), _fmt_r(t),
                                      ha="center", va="center", fontsize=size,
                                      color=txt_c))

        # move the frame behind the data, and fix an equal, symmetric view
        fid = set(map(id, self._frame_artists))
        data = [a for a in self.artists if id(a) not in fid]
        frame = [a for a in self.artists if id(a) in fid]
        self.artists = frame + data

        pad = rmax * 1.25
        Axes.set_xlim(self, -pad, pad)
        Axes.set_ylim(self, -pad, pad)
