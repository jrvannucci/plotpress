"""Vectorized data-space -> SVG-pixel-space transforms.

SVG's origin is the top-left corner with y increasing downward, so the y axis
is flipped relative to data space. All transforms operate on whole NumPy arrays
in one shot -- there is no per-point Python work.

A per-axis *scale* ('linear' or 'log') is applied as a forward function before
the affine map, exactly like matplotlib (scale transform, then affine). Log maps
non-positive values to NaN, which the renderers already skip.
"""

from __future__ import annotations

import numpy as np


def _forward(scale):
    if scale == "log":
        def f(v):
            v = np.asarray(v, dtype=float)
            with np.errstate(invalid="ignore", divide="ignore"):
                return np.where(v > 0, np.log10(np.where(v > 0, v, np.nan)), np.nan)
        return f
    return lambda v: np.asarray(v, dtype=float)


class LinearTransform:
    """Maps data coordinates to pixel coordinates for one axes.

    Parameters
    ----------
    xlim, ylim : (float, float)
        Data limits ``(min, max)``.
    pixel_rect : (float, float, float, float)
        Target rectangle in pixels as ``(left, top, width, height)`` using
        SVG's top-left origin.
    xscale, yscale : 'linear' | 'log'
        Per-axis scale applied before the affine map.
    """

    def __init__(self, xlim, ylim, pixel_rect, xscale="linear", yscale="linear"):
        self.xmin, self.xmax = float(xlim[0]), float(xlim[1])
        self.ymin, self.ymax = float(ylim[0]), float(ylim[1])
        self.px_left, self.px_top, self.px_w, self.px_h = pixel_rect
        self.xscale, self.yscale = xscale, yscale

        self._fx = _forward(xscale)
        self._fy = _forward(yscale)
        self._fxmin = float(self._fx(self.xmin))
        self._fxmax = float(self._fx(self.xmax))
        self._fymin = float(self._fy(self.ymin))
        self._fymax = float(self._fy(self.ymax))

        self._sx = self.px_w / ((self._fxmax - self._fxmin) or 1.0)
        self._sy = self.px_h / ((self._fymax - self._fymin) or 1.0)

    def x(self, x):
        """Data x -> pixel x (vectorized)."""
        return self.px_left + (self._fx(x) - self._fxmin) * self._sx

    def y(self, y):
        """Data y -> pixel y (vectorized, y-axis flipped)."""
        return self.px_top + (self._fymax - self._fy(y)) * self._sy

    def xy(self, x, y):
        """Return stacked ``(N, 2)`` pixel coordinates."""
        return np.column_stack([self.x(x), self.y(y)])
