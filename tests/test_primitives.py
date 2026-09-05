"""primitives.py: the backend-agnostic pixel-space layer artist_to_prims()
builds, shared by svg.py/raster.py (and, for the pie/tick helpers, by
vega.py/vega_lite.py too).

No dedicated file existed for this before -- it was only exercised
incidentally through axes.py/svg.py/vega*.py tests, several layers removed
from where a bug in the geometry itself would actually originate. Focuses on
what's genuinely untested elsewhere: the min/max line-decimation algorithm
(a real performance feature, not just an implementation detail -- see
CLAUDE.md), and the three small shared-math helpers (pie / tick-edge) that
now have call sites in three-plus modules apiece.
"""
import numpy as np
import pytest

from plotpress.primitives import (
    _decimate_minmax,
    _is_monotonic,
    artist_to_prims,
    pie_center_radius,
    pie_label_positions,
    tick_axis_edge,
)
from plotpress.artists import AxLine, Line2D, LineCollection, Rug, Span
from plotpress.transform import LinearTransform


def _tr(px_w=700.0, px_h=430.0):
    return LinearTransform((0.0, 1.0), (0.0, 1.0), (0.0, 0.0, px_w, px_h))


# -- _is_monotonic / _decimate_minmax ---------------------------------------
def test_is_monotonic_increasing_and_decreasing():
    assert _is_monotonic(np.array([1.0, 2.0, 2.0, 5.0]))
    assert _is_monotonic(np.array([5.0, 2.0, 2.0, 1.0]))
    assert not _is_monotonic(np.array([1.0, 3.0, 2.0]))


def test_decimate_minmax_keeps_first_and_last_point():
    x = np.linspace(0.0, 1.0, 20_000)
    y = np.sin(x * 50)
    dx, dy = _decimate_minmax(x, y, ncols=200)
    assert dx[0] == x[0] and dx[-1] == x[-1]
    assert dy[0] == y[0] and dy[-1] == y[-1]


def test_decimate_minmax_preserves_spikes():
    """A single huge outlier in the middle of an otherwise flat line must
    survive decimation -- that's the whole point of min/max-per-column
    over naive subsampling (CLAUDE.md: "visually lossless, spikes
    preserved")."""
    n = 20_000
    x = np.linspace(0.0, 1.0, n)
    y = np.zeros(n)
    spike_idx = n // 2
    y[spike_idx] = 100.0
    dx, dy = _decimate_minmax(x, y, ncols=200)
    assert dy.max() == pytest.approx(100.0)


def test_decimate_minmax_actually_reduces_point_count():
    x = np.linspace(0.0, 1.0, 20_000)
    y = np.sin(x * 50)
    dx, _ = _decimate_minmax(x, y, ncols=200)
    assert dx.size < x.size


def test_decimate_minmax_below_threshold_returns_input_unchanged():
    x = np.linspace(0.0, 1.0, 10)
    y = x.copy()
    dx, dy = _decimate_minmax(x, y, ncols=200)
    assert dx is x and dy is y


def test_line2d_huge_monotonic_line_is_decimated_end_to_end():
    n = 20_000
    x = np.linspace(0.0, 1.0, n)
    art = Line2D(x, np.sin(x * 50), color="#1f77b4", linewidth=1.5)
    prims = artist_to_prims(art, _tr(), 0, 0)
    assert len(prims) == 1
    assert prims[0].subpaths[0].shape[0] < n


def test_line2d_huge_non_monotonic_line_is_not_decimated():
    """_decimate_minmax assumes monotonic x (min/max-per-pixel-column only
    makes sense along a single sweep direction) -- a non-monotonic huge
    line must be left alone rather than silently scrambled."""
    n = 20_000
    t = np.linspace(0.0, 4 * np.pi, n)
    x = np.sin(t)   # non-monotonic
    art = Line2D(x, np.cos(t), color="#1f77b4", linewidth=1.5)
    prims = artist_to_prims(art, _tr(), 0, 0)
    assert prims[0].subpaths[0].shape[0] == n


# -- reference-line / span / collection artists via artist_to_prims --------
def test_axline_with_slope_spans_the_full_pixel_width():
    art = AxLine(0.5, 0.5, slope=1.0, color="#000000", linewidth=1.0,
                 linestyle="-", alpha=1.0)
    tr = _tr()
    prims = artist_to_prims(art, tr, 0, 0)
    assert len(prims) == 1
    p0, p1 = prims[0].p0, prims[0].p1
    assert p0[0] == pytest.approx(tr.px_left)
    assert p1[0] == pytest.approx(tr.px_left + tr.px_w)


def test_span_vertical_covers_full_pixel_height():
    art = Span(0.2, 0.4, "vertical", color="#1f77b4", alpha=0.3)
    tr = _tr()
    prims = artist_to_prims(art, tr, 0, 0)
    rect = prims[0]
    assert rect.y == pytest.approx(tr.px_top)
    assert rect.h == pytest.approx(tr.px_h)


def test_linecollection_segments_transform_both_endpoints():
    segs = np.array([[0.0, 0.0, 1.0, 1.0], [0.2, 0.8, 0.8, 0.2]])
    art = LineCollection(segs, color="#000000", linewidth=1.0,
                         linestyle="-", alpha=1.0)
    tr = _tr()
    prims = artist_to_prims(art, tr, 0, 0)
    assert prims[0].segs.shape == (2, 4)


def test_rug_bottom_side_ticks_anchor_at_px_bottom():
    art = Rug(np.array([0.1, 0.5, 0.9]), height=0.05, side="bottom",
             color="#000000", linewidth=1.0, alpha=1.0)
    tr = _tr()
    prims = artist_to_prims(art, tr, 0, 0)
    segs = prims[0].segs
    assert segs.shape[0] == 3
    assert np.allclose(segs[:, 1], tr.px_top + tr.px_h)  # y0 at the bottom edge


# -- pie_center_radius / pie_label_positions --------------------------------
def test_pie_center_radius_uses_the_smaller_dimension():
    cx, cy, r = pie_center_radius(px_w=200.0, px_h=100.0, radius=1.0)
    assert cx == 100.0 and cy == 50.0
    assert r == pytest.approx(0.42 * 100.0)


def test_pie_center_radius_honors_origin_offset():
    cx, cy, r = pie_center_radius(100.0, 100.0, 1.0, origin_x=10.0, origin_y=20.0)
    assert cx == 60.0 and cy == 70.0


def test_pie_label_positions_first_wedge_starts_at_startangle():
    """A single full-circle wedge's mid-angle is startangle - 180 deg (half
    the sweep in) -- checked via its label position landing opposite the
    start angle, not by re-deriving the trig by hand here."""
    rows = pie_label_positions([1.0], startangle=0.0, cx=0.0, cy=0.0, R=1.0)
    assert len(rows) == 1
    # startangle=0, one full wedge -> mid-angle is -pi, landing at (-1.15, ~0).
    assert rows[0]["label_x"] == pytest.approx(-1.15, abs=1e-9)
    assert rows[0]["label_y"] == pytest.approx(0.0, abs=1e-9)


def test_pie_label_positions_right_side_flag_matches_the_angle():
    # Two even halves starting at 90 deg: first wedge's mid-angle is at 0 deg
    # (right side), second at 180 deg (left side).
    rows = pie_label_positions([0.5, 0.5], startangle=90.0, cx=0.0, cy=0.0, R=1.0)
    assert rows[0]["right_side"] is True
    assert rows[1]["right_side"] is False


# -- tick_axis_edge -----------------------------------------------------
@pytest.mark.parametrize("xside, yside, expect", [
    ("bottom", "left", (10.0 + 40.0, 1, 5.0, -1)),      # px_top+px_h, +1, px_left, -1
    ("top", "left", (10.0, -1, 5.0, -1)),
    ("bottom", "right", (10.0 + 40.0, 1, 5.0 + 30.0, 1)),
    ("top", "right", (10.0, -1, 5.0 + 30.0, 1)),
])
def test_tick_axis_edge_all_four_sides(xside, yside, expect):
    x_axis, x_sign, y_axis, y_sign = tick_axis_edge(
        px_left=5.0, px_w=30.0, px_top=10.0, px_h=40.0, xside=xside, yside=yside)
    assert (x_axis, x_sign, y_axis, y_sign) == expect
