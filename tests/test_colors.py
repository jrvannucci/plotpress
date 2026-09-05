"""Normalize / LogNorm / PowerNorm / SymLogNorm, and the colormap LUTs.

No dedicated file existed for this before -- colors.py was only exercised
incidentally through axes.py/svg.py/vega*.py tests. Focuses on the norm
classes' shared contract (autoscale-from-data, a degenerate vmin==vmax span,
and -- the reason this file exists at all -- LogNorm's floor for a
non-positive vmin agreeing with ticker.log_ticks' own floor for the same
case) rather than re-testing what test_render_all.py/test_svg_output.py
already cover end to end.
"""
import numpy as np
import pytest

from plotpress.colors import LogNorm, Normalize, PowerNorm, SymLogNorm, to_hex
from plotpress.ticker import log_floor, log_ticks


@pytest.mark.parametrize("norm_cls, kwargs", [
    (Normalize, {}),
    (LogNorm, {}),
    (PowerNorm, {"gamma": 2.0}),
    (SymLogNorm, {"linthresh": 1.0}),
])
def test_autoscale_from_data(norm_cls, kwargs):
    n = norm_cls(**kwargs)
    data = np.array([1.0, 10.0, 100.0])
    n.autoscale_none(data)
    assert n.vmin == pytest.approx(1.0)
    assert n.vmax == pytest.approx(100.0)


@pytest.mark.parametrize("norm_cls, kwargs", [
    (Normalize, {"vmin": 5.0, "vmax": 5.0}),
    (LogNorm, {"vmin": 5.0, "vmax": 5.0}),
    (PowerNorm, {"gamma": 2.0, "vmin": 5.0, "vmax": 5.0}),
    (SymLogNorm, {"linthresh": 1.0, "vmin": 5.0, "vmax": 5.0}),
])
def test_degenerate_vmin_equals_vmax_does_not_divide_by_zero(norm_cls, kwargs):
    """vmin == vmax (a flat/constant field) used to divide by a literal
    zero span in three of these four classes' own bespoke guards
    (drifted syntax, same idea) -- now one shared _nonzero_span()."""
    n = norm_cls(**kwargs)
    result = n(np.array([5.0]))
    assert np.all(np.isfinite(result))


def test_lognorm_floor_agrees_with_log_ticks_floor():
    """LogNorm(vmin<=0, ...) used to floor its own color-mapping domain at
    a fixed 1e-300 while colorbar_ticks() -> ticker.log_ticks() floored the
    *same* vmin/vmax at "three decades below vmax" -- for a real dataset,
    that meant almost the entire visible range collapsed into one end of
    the colormap, while the colorbar's own ticks looked normal. Both now
    share ticker.log_floor(), so the lowest real tick lands at fraction 0,
    not somewhere deep in the tail of an effectively 300-decade-wide scale.
    """
    norm = LogNorm(vmin=0, vmax=100)
    lowest_tick = log_ticks(0, 100).min()
    assert lowest_tick == pytest.approx(log_floor(100))
    assert norm(np.array([lowest_tick]))[0] == pytest.approx(0.0, abs=1e-9)


def test_lognorm_floor_is_a_noop_for_ordinary_positive_data():
    """The floor only ever matters for an explicit non-positive vmin --
    autoscale_none() already keeps vmin > 0 whenever there's real positive
    data, so this must produce the same mapping either way."""
    a = LogNorm(vmin=1.0, vmax=100.0)
    b = LogNorm(vmin=1.0, vmax=100.0)
    data = np.array([1.0, 10.0, 100.0])
    assert np.allclose(a(data), b(data))


def test_to_hex_rgb_and_rgba_tuples():
    assert to_hex((1.0, 0.0, 0.0)) == "#ff0000"
    assert to_hex((0, 128, 255)) == "#0080ff"


def test_to_hex_unknown_color_raises():
    with pytest.raises(ValueError, match="Unknown color"):
        to_hex("not-a-real-color")
