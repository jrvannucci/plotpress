"""Axes plotting methods, autoscaling, and limits."""

import numpy as np
import pytest

import simpleplot
from simpleplot.artists import Line2D, QuadMesh, ScatterCollection
from simpleplot.axes import Axes


def test_plot_single_and_pair_args():
    _, ax = simpleplot.subplots()
    l1 = ax.plot([3, 4, 5])           # y only -> x = 0,1,2
    np.testing.assert_array_equal(l1.x, [0, 1, 2])
    l2 = ax.plot([0, 10], [1, 2])     # x, y
    np.testing.assert_array_equal(l2.x, [0, 10])
    assert isinstance(l1, Line2D)


def test_plot_requires_args():
    _, ax = simpleplot.subplots()
    with pytest.raises(TypeError):
        ax.plot()


def test_scatter_creates_collection_and_mappable():
    _, ax = simpleplot.subplots()
    plain = ax.scatter([0, 1], [0, 1])
    assert isinstance(plain, ScatterCollection)
    assert not plain.mappable
    mapped = ax.scatter([0, 1], [0, 1], c=[0.0, 1.0], cmap="viridis")
    assert mapped.mappable
    colors = mapped.face_colors()
    assert len(colors) == 2 and colors[0].startswith("#")


def test_pcolormesh_signatures():
    _, ax = simpleplot.subplots()
    C = np.arange(12).reshape(3, 4).astype(float)
    m1 = ax.pcolormesh(C)
    assert m1.extent() == (0, 4, 0, 3)
    x = np.linspace(0, 1, 4)
    y = np.linspace(0, 2, 3)
    m2 = ax.pcolormesh(x, y, C)
    assert m2.extent() == (0.0, 1.0, 0.0, 2.0)
    assert isinstance(m2, QuadMesh)
    with pytest.raises(TypeError):
        ax.pcolormesh(x, y)  # 2 args is invalid


def test_autoscale_from_data():
    _, ax = simpleplot.subplots()
    ax.plot([0, 10], [-5, 5])
    (xlo, xhi), (ylo, yhi) = ax._resolved_limits()
    # 5% padding on a span of 10 -> 0.5.
    assert xlo == pytest.approx(-0.5) and xhi == pytest.approx(10.5)
    assert ylo == pytest.approx(-5.5) and yhi == pytest.approx(5.5)


def test_explicit_limits_override_autoscale():
    _, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 10])
    ax.set_xlim(0, 5)
    ax.set_ylim(-1, 1)
    assert ax.get_xlim() == (0, 5)
    assert ax.get_ylim() == (-1, 1)


def test_one_sided_limits_autoscale_the_open_end():
    """A half-set limit used to be stored verbatim and blow up at render time
    with a bare float(None) TypeError from the transform."""
    _, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 10])
    auto_hi = ax.get_xlim()[1]

    ax.set_xlim(0, None)                    # pin left, autoscale right
    assert ax.get_xlim() == (0, auto_hi)
    ax.set_ylim(None, 100)                  # pin right, autoscale left
    assert ax.get_ylim()[1] == 100
    assert ax.get_ylim()[0] == pytest.approx(-0.5)


@pytest.mark.parametrize("call", [
    lambda ax: ax.set_xlim(0, 5),
    lambda ax: ax.set_xlim((0, 5)),
    lambda ax: ax.set_xlim([0, 5]),
    lambda ax: ax.set_xlim(np.array([0, 5])),
])
def test_set_xlim_accepts_pair_and_sequence_forms(call):
    _, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 10])
    call(ax)
    assert ax.get_xlim() == (0, 5)


def test_set_lim_with_both_ends_none_clears_to_autoscale():
    _, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 10])
    auto = ax.get_xlim()
    ax.set_xlim(0, 5)
    ax.set_xlim(None, None)
    assert ax.get_xlim() == auto


def test_one_sided_limit_renders():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 10])
    ax.set_xlim(0, None)
    ax.set_ylim(None, 100)
    assert fig.to_svg().startswith("<svg")


def test_one_sided_limit_stays_local_to_its_axes_when_shared():
    _, axes = simpleplot.subplots(1, 2, sharey=True)
    axes[0].plot([0, 5])
    axes[1].plot([0, 50])
    shared_hi = axes[0].get_ylim()[1]
    axes[0].set_ylim(0, None)
    assert axes[0].get_ylim() == (0, shared_hi)   # pin applies here only
    assert axes[1].get_ylim()[0] != 0             # ...not to the whole group


def test_mesh_autoscale_is_tight():
    _, ax = simpleplot.subplots()
    ax.pcolormesh(np.zeros((5, 5)))
    (xlo, xhi), _ = ax._resolved_limits()
    assert xlo == 0 and xhi == 5  # no padding for meshes


def test_subplots_grid_shapes():
    _, single = simpleplot.subplots()
    assert isinstance(single, Axes)
    _, row = simpleplot.subplots(1, 3)
    assert row.shape == (3,)
    _, grid = simpleplot.subplots(2, 2)
    assert grid.shape == (2, 2)
    assert isinstance(grid[0, 0], Axes)
