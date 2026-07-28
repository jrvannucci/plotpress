"""Axes plotting methods, autoscaling, and limits."""

import numpy as np
import pytest

import plotpress
from plotpress.artists import Line2D, QuadMesh, ScatterCollection
from plotpress.axes import Axes


def test_plot_single_and_pair_args():
    _, ax = plotpress.subplots()
    l1 = ax.plot([3, 4, 5])           # y only -> x = 0,1,2
    np.testing.assert_array_equal(l1.x, [0, 1, 2])
    l2 = ax.plot([0, 10], [1, 2])     # x, y
    np.testing.assert_array_equal(l2.x, [0, 10])
    assert isinstance(l1, Line2D)


def test_plot_requires_args():
    _, ax = plotpress.subplots()
    with pytest.raises(TypeError):
        ax.plot()


def test_scatter_creates_collection_and_mappable():
    _, ax = plotpress.subplots()
    plain = ax.scatter([0, 1], [0, 1])
    assert isinstance(plain, ScatterCollection)
    assert not plain.mappable
    mapped = ax.scatter([0, 1], [0, 1], c=[0.0, 1.0], cmap="viridis")
    assert mapped.mappable
    colors = mapped.face_colors()
    assert len(colors) == 2 and colors[0].startswith("#")


def test_pcolormesh_signatures():
    _, ax = plotpress.subplots()
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
    _, ax = plotpress.subplots()
    ax.plot([0, 10], [-5, 5])
    (xlo, xhi), (ylo, yhi) = ax._resolved_limits()
    # 5% padding on a span of 10 -> 0.5.
    assert xlo == pytest.approx(-0.5) and xhi == pytest.approx(10.5)
    assert ylo == pytest.approx(-5.5) and yhi == pytest.approx(5.5)


def test_explicit_limits_override_autoscale():
    _, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    ax.set_xlim(0, 5)
    ax.set_ylim(-1, 1)
    assert ax.get_xlim() == (0, 5)
    assert ax.get_ylim() == (-1, 1)


def test_one_sided_limits_autoscale_the_open_end():
    """A half-set limit used to be stored verbatim and blow up at render time
    with a bare float(None) TypeError from the transform."""
    _, ax = plotpress.subplots()
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
    _, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    call(ax)
    assert ax.get_xlim() == (0, 5)


def test_set_lim_with_both_ends_none_clears_to_autoscale():
    _, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    auto = ax.get_xlim()
    ax.set_xlim(0, 5)
    ax.set_xlim(None, None)
    assert ax.get_xlim() == auto


def test_one_sided_limit_renders():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    ax.set_xlim(0, None)
    ax.set_ylim(None, 100)
    assert fig.to_svg().startswith("<svg")


def test_hexbin_layout_is_independent_of_the_y_units():
    """Rescaling y must not change the hex lattice.

    Deriving the row count from the ratio of the data ranges made it scale with
    the units, so plotting kilowatts against metres per second asked for
    thousands of rows and every bin rendered as a sub-pixel dash.
    """
    rng = np.random.default_rng(0)
    x, y = rng.normal(0, 1, 4000), rng.normal(0, 1, 4000)
    counts = []
    for scale in (1.0, 1e3, 1e-3):
        _, ax = plotpress.subplots()
        counts.append(len(ax.hexbin(x, y * scale, gridsize=30).verts))
    assert len(set(counts)) == 1, counts


def test_explicit_limit_propagates_across_a_share_group():
    """sharey means shared *limits*, not just a shared autoscale.

    Setting a limit on one panel and leaving its neighbours where they were is
    how a shared grid silently comes apart -- and on the panels whose ticks are
    hidden because they are shared, nothing on screen says so.
    """
    _, axes = plotpress.subplots(1, 2, sharey=True)
    axes[0].plot([0, 5])
    axes[1].plot([0, 50])
    shared_hi = axes[0].get_ylim()[1]
    axes[0].set_ylim(0, None)
    # The pinned end applies to the group; the open end keeps autoscaling.
    assert axes[0].get_ylim() == (0, shared_hi)
    assert axes[1].get_ylim() == (0, shared_hi)


def test_explicit_limit_stays_local_without_sharing():
    _, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 5])
    axes[1].plot([0, 50])
    axes[0].set_ylim(0, 2)
    assert axes[0].get_ylim() == (0, 2)
    assert axes[1].get_ylim() != (0, 2)


def test_own_limit_wins_over_a_shared_sibling():
    _, axes = plotpress.subplots(1, 2, sharex=True)
    axes[0].plot([0, 5])
    axes[1].plot([0, 50])
    axes[0].set_xlim(0, 1)
    axes[1].set_xlim(2, 3)
    assert axes[0].get_xlim() == (0, 1)
    assert axes[1].get_xlim() == (2, 3)


@pytest.mark.parametrize("setlim, scale", [
    (lambda ax: ax.set_xlim(3, 0), "linear"),
    (lambda ax: ax.set_ylim(3, 0), "linear"),
    (lambda ax: (ax.set_yscale("log"), ax.set_ylim(100, 1)), "log"),
])
def test_reversed_limits_render_like_matplotlib_inversion(setlim, scale):
    # set_xlim(hi, lo) reverses the axis in matplotlib. It used to crash the
    # linear tickers (math domain error) and silently drop all log ticks.
    fig, ax = plotpress.subplots()
    ax.plot([1, 10, 100], [1, 10, 100])
    setlim(ax)
    svg = fig.to_svg()
    assert svg.startswith("<svg")


def test_reversed_ticks_are_order_independent():
    from plotpress.ticker import log_ticks, nice_ticks
    np.testing.assert_array_equal(nice_ticks(3, 0), nice_ticks(0, 3))
    np.testing.assert_array_equal(log_ticks(100, 1), log_ticks(1, 100))
    assert len(log_ticks(100, 1)) > 0     # not silently empty


def test_mesh_autoscale_is_tight():
    _, ax = plotpress.subplots()
    ax.pcolormesh(np.zeros((5, 5)))
    (xlo, xhi), _ = ax._resolved_limits()
    assert xlo == 0 and xhi == 5  # no padding for meshes


def test_subplots_grid_shapes():
    _, single = plotpress.subplots()
    assert isinstance(single, Axes)
    _, row = plotpress.subplots(1, 3)
    assert row.shape == (3,)
    _, grid = plotpress.subplots(2, 2)
    assert grid.shape == (2, 2)
    assert isinstance(grid[0, 0], Axes)


# -- contour / contourf coordinate handling ---------------------------------

def _peak_grid(n=30):
    g = np.linspace(-3.0, 3.0, n)
    X, Y = np.meshgrid(g, g)
    return g, X, Y, np.exp(-(X ** 2 + Y ** 2))


@pytest.mark.parametrize("method", ["contour", "contourf"])
def test_contour_accepts_meshgrid_coordinates(method):
    """Passing the same 2-D X/Y used for pcolormesh must work.

    contour used to crash deep in the renderer -- _marching_squares indexes x/y
    as 1-D vectors, so a 2-D x made _fmt try to format a whole row -- while
    contourf silently accepted it. Overlaying isolines on a mesh is the obvious
    thing to do, so both now take either form.
    """
    g, X, Y, Z = _peak_grid()
    fig_1d, ax_1d = plotpress.subplots()
    getattr(ax_1d, method)(g, g, Z, levels=6)
    fig_2d, ax_2d = plotpress.subplots()
    getattr(ax_2d, method)(X, Y, Z, levels=6)
    assert fig_1d.to_svg() == fig_2d.to_svg()


@pytest.mark.parametrize("method", ["contour", "contourf"])
def test_contour_rejects_a_curvilinear_grid(method):
    """Marching squares walks a rectilinear grid, and contourf only keeps the
    extent -- so a warped mesh would be drawn into its bounding box. Refuse it
    instead of rendering something subtly wrong."""
    r = np.linspace(0.3, 1.0, 20)
    th = np.linspace(0.0, 1.7 * np.pi, 20)
    R, TH = np.meshgrid(r, th)
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="rectilinear"):
        getattr(ax, method)(R * np.cos(TH), R * np.sin(TH), R)


def test_contour_over_pcolormesh_renders():
    """The scientific idiom the fix exists for: isolines on a colormapped field."""
    g, X, Y, Z = _peak_grid()
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z, cmap="magma")
    ax.contour(X, Y, Z, levels=5, colors="white")
    assert "<svg" in fig.to_svg()
