"""3-D axes: projection math, retained-command reprojection, surface/wire, frame.

3-D is projection + existing artists, so the tests check the orthographic math,
that the scene reprojects when the camera moves (data baked at plot time would
otherwise go stale), and that surface faces are depth-sorted and colorbar-ready.
"""
import numpy as np
import pytest

import plotpress
from plotpress.axes3d import Axes3D
from plotpress.artists import LineCollection, PolyCollection


def _ax3d():
    fig, ax = plotpress.subplots(projection="3d")
    return fig, ax


def test_projection_matches_orthographic_formula():
    _, ax = _ax3d()
    ax.azim, ax.elev = -60.0, 30.0
    xn = np.array([0.3]); yn = np.array([-0.2]); zn = np.array([0.5])
    sx, sy, depth = ax._project_norm(xn, yn, zn)
    a, e = np.radians(-60.0), np.radians(30.0)
    ca, sa, ce, se = np.cos(a), np.sin(a), np.cos(e), np.sin(e)
    np.testing.assert_allclose(sx, -xn * sa + yn * ca)
    np.testing.assert_allclose(sy, -xn * ca * se - yn * sa * se + zn * ce)
    np.testing.assert_allclose(depth, xn * ca * ce + yn * sa * ce + zn * se)


def test_view_init_reprojects_existing_data():
    _, ax = _ax3d()
    line = ax.plot([0, 1, 2], [0, 1, 0], [0, 2, 1], color="C0")
    before = (line.x.copy(), line.y.copy())
    ax.view_init(elev=10, azim=120)          # camera moves after plotting
    line2 = ax.artists[-1]                    # rebuilt data artist
    assert not np.allclose(line2.x, before[0])   # projection actually changed


def test_surface_face_count_sorted_and_colorbar_ready():
    fig, ax = _ax3d()
    X, Y = np.meshgrid(np.linspace(0, 1, 6), np.linspace(0, 1, 5))
    Z = X + Y
    surf = ax.plot_surface(X, Y, Z, cmap="viridis")
    assert isinstance(surf, PolyCollection)
    assert len(surf.verts) == (5 - 1) * (6 - 1)         # one quad per grid cell
    assert len(surf.facecolors) == len(surf.verts)
    assert surf.lut is not None and surf.norm is not None  # colorbar mappable
    fig.colorbar(surf, ax=ax)                            # must not raise


def test_surface_is_depth_sorted_back_to_front():
    _, ax = _ax3d()
    X, Y = np.meshgrid(np.linspace(0, 1, 8), np.linspace(0, 1, 8))
    Z = np.sin(3 * X) * np.cos(3 * Y)                # non-flat -> depths differ
    ax.plot_surface(X, Y, Z)
    surf = [a for a in ax.artists if isinstance(a, PolyCollection)][0]

    # Independently recompute face depths in the same cell order, sort, and
    # confirm the emitted verts are exactly that back-to-front order.
    norm, _ = ax._normalizer()
    sx, sy, depth = ax._project_norm(*norm(X, Y, Z))
    m, n = Z.shape
    verts, fdepth = [], []
    for i in range(m - 1):
        for j in range(n - 1):
            idx = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
            verts.append(np.array([[sx[a, b], sy[a, b]] for a, b in idx]))
            fdepth.append(np.mean([depth[a, b] for a, b in idx]))
    expected = [verts[k] for k in np.argsort(fdepth)]
    assert len(surf.verts) == len(expected)
    for got, exp in zip(surf.verts, expected):
        np.testing.assert_allclose(got, exp)


def test_wireframe_segment_count():
    _, ax = _ax3d()
    X, Y = np.meshgrid(np.linspace(0, 1, 5), np.linspace(0, 1, 4))
    Z = np.zeros_like(X)
    ax.plot_wireframe(X, Y, Z, color="C0")
    lc = [a for a in ax.artists if isinstance(a, LineCollection)
          and a not in ax._frame_artists][0]
    m, n = 4, 5
    assert lc.segments.shape[0] == m * (n - 1) + n * (m - 1)


def test_frame_is_a_12_edge_cube_behind_data():
    _, ax = _ax3d()
    ax.scatter([0, 1], [0, 1], [0, 1], color="C1")
    frame_lc = [a for a in ax._frame_artists if isinstance(a, LineCollection)][0]
    assert frame_lc.segments.shape[0] == 12          # cube edges
    # every frame artist is emitted before every data (non-frame) artist
    frame_ids = set(map(id, ax._frame_artists))
    last_frame = max(i for i, a in enumerate(ax.artists) if id(a) in frame_ids)
    first_data = min(i for i, a in enumerate(ax.artists) if id(a) not in frame_ids)
    assert last_frame < first_data


def test_different_ranges_share_one_normalized_cube():
    _, ax = _ax3d()
    # x in thousands, z tiny -- normalization must keep both inside the cube
    ax.scatter([0, 1000], [0, 5], [0, 0.01], color="C0")
    for art in ax.artists:
        if hasattr(art, "x"):
            assert np.all(np.abs(art.x) <= 1.0 + 1e-9)
            assert np.all(np.abs(art.y) <= 1.0 + 1e-9)


def test_set_xlim3d_changes_normalization():
    _, ax = _ax3d()
    line = ax.plot([0, 1], [0, 0], [0, 0])
    x_default = line.x.copy()
    ax.set_xlim3d(-10, 10)                # wider x range -> point sits nearer center
    line2 = ax.artists[-1]
    assert not np.allclose(line2.x, x_default)


def test_each_axis_gets_multiple_ticks_along_its_edge():
    # Regression for the "which axis does this number belong to?" ambiguity:
    # ticks must run along each edge (several per axis), not just sit on the two
    # shared corners, and each axis name must be present.
    from plotpress.artists import Text, LineCollection
    _, ax = _ax3d()
    ax.scatter([-3, 3], [-3, 3], [-0.5, 0.5], color="C0")
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
    texts = [t.text for t in ax._frame_artists if isinstance(t, Text)]
    for name in ("x", "y", "z"):
        assert name in texts
    numeric = [t for t in texts if t not in ("x", "y", "z")]
    assert len(numeric) >= 9            # >3 ticks per axis, not 2 corners each
    # a dedicated tick-mark collection ties numbers to their edges
    lcs = [a for a in ax._frame_artists if isinstance(a, LineCollection)]
    assert len(lcs) == 2                # cube edges + tick marks


def test_cycle_colors_are_stable_across_reprojection():
    # Colors are resolved once at plot time; a later view change (which reprojects
    # the whole scene) must not re-roll the cycle or change a series' color.
    _, ax = _ax3d()
    l1 = ax.plot([0, 1], [0, 1], [0, 1])          # C0
    l2 = ax.plot([0, 1], [1, 0], [1, 0])          # C1
    c1, c2 = l1.color, l2.color
    assert c1 != c2
    ax.view_init(elev=5, azim=200)                # reprojects both
    new1, new2 = ax.artists[-2], ax.artists[-1]
    assert new1.color == c1 and new2.color == c2


def test_3d_renders_in_both_backends():
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots(projection="3d")
    X, Y = np.meshgrid(np.linspace(-2, 2, 20), np.linspace(-2, 2, 20))
    ax.plot_surface(X, Y, np.sin(np.hypot(X, Y)), cmap="plasma")
    assert "<svg" in fig.to_svg()
    figure_to_image(fig, scale=1)          # raster must not raise
