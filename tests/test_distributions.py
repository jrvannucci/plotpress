"""Seaborn-style distribution methods: kdeplot, ecdfplot, rugplot, violin inner."""

import numpy as np
import pytest

import simpleplot
from simpleplot.artists import FillBetween, Rug, ScatterCollection, Violin
from simpleplot.primitives import Segments, artist_to_prims
from simpleplot.transform import LinearTransform


def _sample(n=400, loc=0.0, scale=1.0, seed=0):
    return np.random.default_rng(seed).normal(loc, scale, n)


# -- kdeplot ----------------------------------------------------------------
def test_kdeplot_is_a_normalised_density():
    _, ax = simpleplot.subplots()
    line = ax.kdeplot(_sample(2000))
    assert np.trapezoid(line.y, line.x) == pytest.approx(1.0, abs=1e-3)
    assert (line.y >= 0).all()


def test_kdeplot_cut_extends_past_the_data():
    d = _sample()
    _, ax = simpleplot.subplots()
    tight = ax.kdeplot(d, cut=0.0)
    wide = ax.kdeplot(d, cut=3.0)
    assert tight.x[0] == pytest.approx(d.min())
    assert tight.x[-1] == pytest.approx(d.max())
    assert wide.x[0] < d.min() and wide.x[-1] > d.max()
    # With room to decay, the tails reach ~zero.
    assert wide.y[0] < 1e-3 and wide.y[-1] < 1e-3


def test_kdeplot_fill_adds_a_filled_band():
    _, ax = simpleplot.subplots()
    ax.kdeplot(_sample(), fill=False)
    assert not any(isinstance(a, FillBetween) for a in ax.artists)
    ax.kdeplot(_sample(), fill=True)
    assert any(isinstance(a, FillBetween) for a in ax.artists)


# -- ecdfplot ---------------------------------------------------------------
def test_ecdfplot_spans_zero_to_one_and_is_monotonic():
    _, ax = simpleplot.subplots()
    step = ax.ecdfplot(_sample())
    assert step.y.min() == pytest.approx(0.0)
    assert step.y.max() == pytest.approx(1.0)
    assert (np.diff(step.y) >= 0).all()


def test_ecdfplot_hits_half_at_the_median():
    d = _sample(1001)
    _, ax = simpleplot.subplots()
    step = ax.ecdfplot(d)
    assert np.interp(np.median(d), step.x, step.y) == pytest.approx(0.5, abs=0.01)


def test_ecdfplot_complementary_is_the_mirror():
    d = _sample()
    _, ax = simpleplot.subplots()
    plain = ax.ecdfplot(d)
    comp = ax.ecdfplot(d, complementary=True)
    np.testing.assert_allclose(comp.y, 1.0 - plain.y)


# -- rugplot ----------------------------------------------------------------
def _prims(artist, height_px=50.0):
    tr = LinearTransform((0.0, 1.0), (0.0, 1.0), (10.0, 20.0, 100.0, height_px))
    return artist_to_prims(artist, tr, 0, 0)


def test_rugplot_does_not_move_the_autoscale():
    """Regression: the rug is placed in axes fractions, not data units."""
    _, ax = simpleplot.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    before = ax._resolved_limits()
    ax.rugplot([0.2, 0.5, 0.9])
    ax.rugplot([0.3, 0.7])
    assert ax._resolved_limits() == before


def test_rugplot_calls_share_one_baseline():
    """Regression: two rugs used to disagree because each re-read get_ylim()."""
    _, ax = simpleplot.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    a = ax.rugplot([0.2, 0.5])
    b = ax.rugplot([0.3, 0.7])
    (sa,), (sb,) = _prims(a), _prims(b)
    assert isinstance(sa, Segments)
    # Same baseline and same tip, independent of call order.
    np.testing.assert_allclose(np.unique(sa.segs[:, 1]), np.unique(sb.segs[:, 1]))
    np.testing.assert_allclose(np.unique(sa.segs[:, 3]), np.unique(sb.segs[:, 3]))


def test_rugplot_height_is_a_fraction_of_the_axes():
    _, ax = simpleplot.subplots()
    rug = ax.rugplot([0.25, 0.75], height=0.1)
    (seg,) = _prims(rug, height_px=50.0)
    np.testing.assert_allclose(seg.segs[:, 1] - seg.segs[:, 3], 0.1 * 50.0)


def test_rugplot_bounds_only_its_own_axis():
    _, ax = simpleplot.subplots()
    bottom = ax.rugplot([1.0, 3.0]).data_bounds()
    assert bottom[:2] == (1.0, 3.0)
    assert np.isnan(bottom[2]) and np.isnan(bottom[3])
    left = ax.rugplot([1.0, 3.0], side="left").data_bounds()
    assert left[2:] == (1.0, 3.0)
    assert np.isnan(left[0]) and np.isnan(left[1])


def test_rugplot_side_left_runs_horizontally():
    _, ax = simpleplot.subplots()
    (seg,) = _prims(ax.rugplot([0.25, 0.75], side="left"))
    np.testing.assert_allclose(seg.segs[:, 1], seg.segs[:, 3])  # constant y
    assert (seg.segs[:, 2] > seg.segs[:, 0]).all()              # extends right


def test_rugplot_renders_to_svg():
    fig, ax = simpleplot.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.rugplot([0.2, 0.5, 0.9])
    assert "<svg" in fig.to_svg()


# -- violinplot inner / cut -------------------------------------------------
def test_violin_inner_none_adds_only_the_violin():
    _, ax = simpleplot.subplots()
    ax.violinplot([_sample(), _sample(seed=1)])
    assert len(ax.artists) == 1 and isinstance(ax.artists[0], Violin)


def test_violin_inner_box_adds_summary_marks():
    _, ax = simpleplot.subplots()
    ax.violinplot([_sample()], inner="box")
    assert len(ax.artists) > 1
    assert any(isinstance(a, ScatterCollection) for a in ax.artists)


@pytest.mark.parametrize("inner", ["box", "quartile", "stick"])
def test_violin_inner_modes_render(inner):
    fig, ax = simpleplot.subplots()
    ax.violinplot([_sample(), _sample(seed=1)], inner=inner)
    assert "<svg" in fig.to_svg()


@pytest.mark.parametrize("orientation,ix", [("vertical", 1), ("horizontal", 0)])
def test_violin_median_dot_follows_orientation(orientation, ix):
    """Regression: the median dot used to be placed at (position, median)
    regardless of orientation, which misplaced it and skewed the autoscale."""
    d = _sample()
    _, ax = simpleplot.subplots()
    ax.violinplot([d], positions=[1.0], orientation=orientation, inner="box")
    dot = next(a for a in ax.artists if isinstance(a, ScatterCollection))
    value, position = (dot.y, dot.x) if ix else (dot.x, dot.y)
    assert value[0] == pytest.approx(np.median(d))
    assert position[0] == pytest.approx(1.0)


def test_violin_cut_widens_the_silhouette():
    d = _sample()
    _, ax = simpleplot.subplots()
    tight = ax.violinplot([d], cut=0.0)
    wide = ax.violinplot([d], cut=2.0)
    assert tight.grids[0][0] == pytest.approx(d.min())
    assert wide.grids[0][0] < d.min()
    assert wide.grids[0][-1] > d.max()
