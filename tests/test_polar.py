"""Polar axes: projection correctness, frame construction, z-order, backends.

Polar is implemented by projecting (theta, r) to Cartesian and drawing the grid
from ordinary artists, so the tests check the projection math and that the frame
lands behind the data -- not just that a figure renders.
"""
import numpy as np
import pytest

import plotpress
from plotpress.polar import PolarAxes
from plotpress.artists import Line2D, Text


def _polar():
    fig, ax = plotpress.subplots(projection="polar")
    return fig, ax


def test_projection_places_points_correctly():
    _, ax = _polar()
    theta = np.array([0.0, np.pi / 2, np.pi])
    r = np.array([1.0, 2.0, 3.0])
    line = ax.plot(theta, r)
    # (r cos t, r sin t): (1,0), (0,2), (-3, ~0)
    np.testing.assert_allclose(line.x, [1.0, 0.0, -3.0], atol=1e-12)
    np.testing.assert_allclose(line.y, [0.0, 2.0, 0.0], atol=1e-12)


def test_theta_direction_and_zero_location():
    _, ax = _polar()
    ax.set_theta_zero_location("N")     # theta=0 -> +y
    ax.set_theta_direction(-1)          # clockwise
    line = ax.plot(np.array([0.0, np.pi / 2]), np.array([1.0, 1.0]))
    # theta=0 at North -> (0, 1); clockwise quarter-turn -> (+1, 0)
    np.testing.assert_allclose(line.x, [0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(line.y, [1.0, 0.0], atol=1e-12)


def test_frame_sits_behind_data():
    _, ax = _polar()
    data_line = ax.plot(np.linspace(0, 2 * np.pi, 50), np.ones(50))
    # the returned data artist must render after every frame artist
    frame_ids = set(map(id, ax._frame_artists))
    assert frame_ids, "no frame was built"
    data_index = ax.artists.index(data_line)
    frame_indices = [i for i, a in enumerate(ax.artists) if id(a) in frame_ids]
    assert max(frame_indices) < data_index


def test_frame_has_degree_labels_and_grid_circles():
    _, ax = _polar()
    ax.plot(np.linspace(0, 2 * np.pi, 20), np.ones(20))
    texts = [a for a in ax._frame_artists if isinstance(a, Text)]
    circles = [a for a in ax._frame_artists if isinstance(a, Line2D)]
    assert any("°" in t.text for t in texts)       # angular labels
    assert len(circles) >= 8                        # spokes + grid rings


def test_autoscale_and_set_rmax_fix_symmetric_limits():
    _, ax = _polar()
    ax.plot(np.linspace(0, 2 * np.pi, 30), np.full(30, 2.0))
    # autoscaled rmax == 2 -> symmetric view padded by 1.25
    assert ax._xlim == pytest.approx((-2.5, 2.5))
    assert ax._ylim == pytest.approx((-2.5, 2.5))
    ax.set_rmax(5.0)
    assert ax._xlim == pytest.approx((-6.25, 6.25))


def test_rebuild_does_not_leak_frame_artists():
    _, ax = _polar()
    theta = np.linspace(0, 2 * np.pi, 10)
    line1 = ax.plot(theta, np.ones(10))
    line2 = ax.plot(theta, 2 * np.ones(10))    # frame rebuilds, old frame dropped
    # both data lines survive the rebuild
    assert line1 in ax.artists and line2 in ax.artists
    # every current frame artist is present exactly once, with no stale leftovers
    frame_ids = set(map(id, ax._frame_artists))
    frames = [a for a in ax.artists if id(a) in frame_ids]
    assert len(frames) == len(ax._frame_artists)
    # the only Line2D/Text artists present are the 2 data lines + current frame
    data = [a for a in ax.artists if id(a) not in frame_ids]
    assert data == [line1, line2]


def test_orientation_after_plotting_is_rejected():
    _, ax = _polar()
    ax.plot(np.array([0.0, 1.0]), np.array([1.0, 1.0]))
    with pytest.raises(RuntimeError):
        ax.set_theta_direction(-1)


def test_scatter_and_fill_project_too():
    _, ax = _polar()
    theta = np.linspace(0, 2 * np.pi, 40)
    coll = ax.scatter(theta, np.ones(40))
    poly = ax.fill(theta, 0.5 * np.ones(40))
    # scatter x/y are the projected unit circle
    np.testing.assert_allclose(np.hypot(coll.x, coll.y), 1.0, atol=1e-9)
    assert poly in ax.artists


def test_plot_and_scatter_carry_theta_r_for_picking():
    """Regression: point-picking on a polar plot reported the projected
    Cartesian (x, y) -- meaningless read back on a polar chart -- instead of
    the (theta, r) the caller actually plotted."""
    _, ax = _polar()
    theta = np.linspace(0, 2 * np.pi, 20)
    r = np.linspace(1.0, 5.0, 20)
    line = ax.plot(theta, r)
    coll = ax.scatter(theta, r)
    for art in (line, coll):
        np.testing.assert_allclose(art.pick_values["theta"], theta)
        np.testing.assert_allclose(art.pick_values["r"], r)

    fig, ax2 = plotpress.subplots(projection="polar")
    ax2.plot(theta, r)
    from plotpress.svg import pick_data
    series = pick_data(fig)[0]["series"]
    with_theta = [s for s in series if "theta" in s["vals"]]
    assert len(with_theta) == 1
    # pick_data rounds to 6 decimals for the embedded payload.
    np.testing.assert_allclose(with_theta[0]["vals"]["theta"], theta, atol=1e-6)
    np.testing.assert_allclose(with_theta[0]["vals"]["r"], r, atol=1e-6)


def test_polar_renders_in_both_backends():
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots(projection="polar")
    theta = np.linspace(0, 2 * np.pi, 200)
    ax.plot(theta, 1 + 0.4 * np.cos(3 * theta))
    assert "°" in fig.to_svg()
    figure_to_image(fig, scale=1)              # raster must not raise
