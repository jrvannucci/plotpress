"""Unit tests for transforms, tickers, and colors."""

import numpy as np
import pytest

from plotpress.style import colors
from plotpress.style.ticker import format_tick, format_ticks, log_ticks, nice_ticks
from plotpress.core.transform import LinearTransform


# -- transform -------------------------------------------------------------
def test_transform_maps_corners():
    tr = LinearTransform((0, 10), (0, 5), (100, 50, 200, 100))
    # x: left edge -> px_left, right edge -> px_left + width
    assert tr.x(0) == pytest.approx(100)
    assert tr.x(10) == pytest.approx(300)
    # y is flipped: ymax -> top, ymin -> bottom
    assert tr.y(5) == pytest.approx(50)
    assert tr.y(0) == pytest.approx(150)


def test_transform_is_vectorized():
    tr = LinearTransform((0, 1), (0, 1), (0, 0, 100, 100))
    out = tr.xy([0, 1], [0, 1])
    assert out.shape == (2, 2)


def test_transform_degenerate_span_does_not_divide_by_zero():
    tr = LinearTransform((3, 3), (0, 1), (0, 0, 100, 100))
    assert np.isfinite(tr.x(3))


def test_log_transform_maps_decades_evenly():
    tr = LinearTransform((1, 100), (0, 1), (0, 0, 200, 100), xscale="log")
    assert tr.x(1) == pytest.approx(0)
    assert tr.x(10) == pytest.approx(100)   # decade midpoint
    assert tr.x(100) == pytest.approx(200)


def test_log_transform_nonpositive_is_nan():
    tr = LinearTransform((1, 100), (0, 1), (0, 0, 200, 100), xscale="log")
    assert np.isnan(tr.x(0))
    assert np.isnan(tr.x(-5))


def test_log_ticks_are_decades():
    from plotpress.style.ticker import log_ticks
    np.testing.assert_array_equal(log_ticks(1, 1000), [1, 10, 100, 1000])
    np.testing.assert_array_equal(log_ticks(0.01, 10), [0.01, 0.1, 1, 10])


def test_log_ticks_nonpositive_vmin_stays_near_vmax():
    # A non-positive lower bound (e.g. user set_xlim(0, 100) on a log axis)
    # must clamp to three decades below vmax, not blow up to ~300 decades.
    from plotpress.style.ticker import log_ticks
    np.testing.assert_array_equal(log_ticks(0.0, 100.0), [0.1, 1, 10, 100])
    np.testing.assert_array_equal(log_ticks(-5.0, 1000.0), [1, 10, 100, 1000])


# -- ticker ----------------------------------------------------------------
def test_nice_ticks_within_range_and_spaced():
    ticks = nice_ticks(0, 10, n=5)
    assert ticks.min() >= 0 and ticks.max() <= 10
    diffs = np.diff(ticks)
    assert np.allclose(diffs, diffs[0])  # evenly spaced


def test_nice_ticks_handles_equal_bounds():
    ticks = nice_ticks(5, 5)
    assert len(ticks) >= 1


@pytest.mark.parametrize("v,expected", [
    (0, "0"),
    (1, "1"),
    (2.5, "2.5"),
    (1000, "1000"),
    (0.0001, "1e-4"),
    (123456, "1.2e5"),
])
def test_format_tick(v, expected):
    assert format_tick(v) == expected


@pytest.mark.parametrize("lo,hi", [(-0.06, 0.04), (-0.2, 0.2), (-0.6, 0.3)])
def test_nice_ticks_snaps_the_zero_tick_exactly(lo, hi):
    """For an unlucky step (0.02) np.arange lands the zero tick at ~1e-17, which
    then formats as "1.4e-17" instead of "0"."""
    ticks = nice_ticks(lo, hi)
    assert (ticks == 0.0).sum() == 1          # exactly one true zero
    assert "0" in format_ticks(ticks)
    assert not any("e-1" in lab for lab in format_ticks(ticks))  # no dust label


@pytest.mark.parametrize("lo,hi", [
    (100000, 101000),      # narrow band high above the 1e5 sci threshold
    (1e6, 1.00002e6),
    (0.0001, 0.00012),     # and below the 1e-3 threshold
    (123456, 123460),
])
def test_format_ticks_never_duplicates_labels(lo, hi):
    """Per-value formatting rounds these to one mantissa digit, collapsing a
    whole axis to repeats of "1e5"; the set-level formatter must separate them."""
    labels = format_ticks(nice_ticks(lo, hi))
    assert len(set(labels)) == len(labels), labels


def test_format_ticks_leaves_well_behaved_sets_alone():
    assert format_ticks(nice_ticks(0, 10)) == ["0", "2", "4", "6", "8", "10"]
    assert format_ticks(nice_ticks(0, 1)) == ["0", "0.2", "0.4", "0.6", "0.8", "1"]
    # Zero keeps its bare form rather than picking up a shared exponent.
    assert "0" in format_ticks(nice_ticks(-2e5, 2e5))
    # Log decades are unevenly spaced: each label carries its own exponent.
    assert format_ticks(log_ticks(1e-3, 1e3))[0] == "0.001"


def test_format_ticks_degenerate_inputs():
    assert format_ticks([]) == []
    assert format_ticks([123456]) == ["1.2e5"]
    # Ticks that are float-identical cannot be separated by any formatting;
    # fall back rather than emitting a long meaningless mantissa.
    assert format_ticks([1.0, 1.0, 1.0]) == ["1", "1", "1"]


# -- colors ----------------------------------------------------------------
def test_normalize_basic():
    n = colors.Normalize(0, 10)
    assert n(0) == 0.0
    assert n(10) == 1.0
    assert n(5) == 0.5


def test_normalize_autoscale():
    n = colors.Normalize()
    out = n(np.array([2.0, 4.0, 6.0]))
    assert n.vmin == 2.0 and n.vmax == 6.0
    assert out[0] == 0.0 and out[-1] == 1.0


def test_normalize_constant_data_no_nan():
    n = colors.Normalize()
    out = n(np.array([7.0, 7.0, 7.0]))
    assert np.all(np.isfinite(out))


def test_colormap_lut_shape_and_range():
    lut = colors.get_cmap("viridis")
    assert lut.shape == (256, 3)
    assert lut.dtype == np.uint8


def test_unknown_colormap_raises():
    with pytest.raises(ValueError):
        colors.get_cmap("not_a_cmap")


def test_apply_colormap_nan_is_transparent():
    data = np.array([[0.0, np.nan], [1.0, 0.5]])
    lut = colors.get_cmap("viridis")
    rgba = colors.apply_colormap(data, lut, colors.Normalize(0, 1))
    assert rgba.shape == (2, 2, 4)
    assert rgba[0, 1, 3] == 0     # NaN -> alpha 0
    assert rgba[0, 0, 3] == 255   # finite -> opaque


# ---- tick locations are computed, not accumulated ---------------------------

def test_nice_ticks_lands_on_the_exact_step_multiples():
    """Stepping by repeated addition drifts: a [5, 5.5] axis' last tick came
    out at 5.499999999999998, which rounds to "5" under a 0-decimal format
    where the true 5.5 rounds to "6" -- so the static render and the
    interactive rebuild disagreed on a label."""
    ticks = nice_ticks(5, 5.5)
    assert ticks[-1] == 5.5
    assert list(ticks) == [5.0, 5.1, 5.2, 5.3, 5.4, 5.5]


def test_multiple_ticks_puts_the_zero_tick_exactly_on_zero():
    """Same drift, via the multiple locator: base=pi/2 over [-100, 100] put
    the multiple that should be 0 at -3.4e-13, and format_tick then printed
    "-3.4e-13" as an axis label."""
    import math

    from plotpress.style.ticker import multiple_ticks

    ticks = multiple_ticks(-100, 100, math.pi / 2)
    nearest = min(ticks, key=abs)
    assert nearest == 0.0
    assert format_tick(nearest) == "0"


def test_pow10_is_the_correctly_rounded_decade():
    """Neither `**` nor JavaScript's Math.pow is required to give the correctly
    rounded power of ten, and both miss in practice -- 10.0**23 and 10.0**126
    are not the 1e23/1e126 literals, and a CI runner's V8 returned a different
    double for 10**-5 than the development machine, which moved
    ceil(vmin / step) to the next integer and dropped an axis' first tick."""
    from plotpress.style.ticker import pow10

    for exp in range(-300, 301):
        assert pow10(exp) == float(f"1e{exp}"), exp

    # Which exponents `**` actually gets wrong is itself platform-dependent
    # (10.0**126 misses on Windows but not on the Linux CI runners), so that
    # is reported, not asserted -- the contract is only that pow10 is the
    # correctly rounded literal everywhere, which the loop above pins.
    drifts = [e for e in range(-300, 301) if 10.0 ** e != pow10(e)]
    print(f"`**` differs from the correctly rounded decade at: {drifts}")


def test_nice_ticks_keeps_the_first_tick_on_a_narrow_offset_range():
    """[1, 1.0001] ticks from 1.0; a decade off by one ulp pushed
    ceil(vmin / step) up an integer and lost that first tick entirely."""
    assert list(nice_ticks(1, 1.0001)) == [1.0, 1.00002, 1.00004,
                                           1.00006, 1.00008, 1.0001]
