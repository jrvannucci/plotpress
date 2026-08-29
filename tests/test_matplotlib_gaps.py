"""Tests for the matplotlib-compatibility features added to close API gaps:
colormaps + norms, reference lines/spans, fill/line helpers, tick labels,
axis inversion, and legend placement.
"""
import numpy as np
import pytest

import plotpress
from plotpress.colors import (
    LogNorm, PowerNorm, SymLogNorm, apply_colormap, get_cmap, to_hex,
)


# -- colormaps & norms ------------------------------------------------------
def test_new_colormaps_and_reversed():
    for name in ("inferno", "magma", "cividis", "coolwarm", "RdBu",
                 "Spectral", "PiYG", "BrBG", "seismic", "Blues", "Greens",
                 "Oranges", "Reds", "Purples", "YlOrRd", "twilight", "jet",
                 "turbo", "hot", "cool"):
        assert get_cmap(name).shape == (256, 3)
    v = get_cmap("viridis")
    assert np.array_equal(get_cmap("viridis_r"), v[::-1])
    assert "viridis_r" in plotpress.available_colormaps()


def test_twilight_is_cyclic():
    """A cyclic colormap's own first and last LUT entries must match --
    otherwise data that wraps (a phase, an angle) shows a visible seam at
    the point where the ramp restarts."""
    lut = get_cmap("twilight")
    assert np.array_equal(lut[0], lut[-1])


def test_lognorm_maps_decades_and_masks_nonpositive():
    ln = LogNorm(vmin=1, vmax=1000)
    np.testing.assert_allclose(ln(np.array([1.0, 10.0, 100.0, 1000.0])),
                               [0.0, 1 / 3, 2 / 3, 1.0], atol=1e-9)
    rgba = apply_colormap(np.array([[1.0, -5.0]]), get_cmap("viridis"), LogNorm(1, 100))
    assert rgba[0, 1, 3] == 0        # non-positive -> transparent


def test_named_colors_resolve():
    assert to_hex("red") == "#ff0000"
    assert to_hex("k") == "#000000"
    assert to_hex("#abc") == "#abc"


# -- reference lines & spans ------------------------------------------------
def test_axhline_axspans_render_in_both_backends():
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 1])
    ax.axhline(0.5, color="k")
    ax.axvspan(2, 3, color="orange", alpha=0.2)
    ax.axhspan(0.2, 0.4, color="green", alpha=0.2)
    svg = fig.to_svg()
    assert svg.count('fill-opacity="0.2"') == 2      # two spans
    figure_to_image(fig, scale=1)                    # raster must not raise


def test_spans_and_reflines_do_not_autoscale():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.axhline(999); ax.axvspan(-50, -40)
    (x0, x1), (y0, y1) = ax._resolved_limits()
    assert y1 < 10 and x0 > -10                       # ref artists ignored


# -- fill / hlines / vlines -------------------------------------------------
def test_fill_and_line_helpers():
    fig, ax = plotpress.subplots()
    y = np.linspace(0, 5, 20)
    ax.fill_betweenx(y, 0, np.sin(y) + 2, color="teal")
    ax.fill([0, 1, 1, 0], [0, 0, 1, 1], color="gold", edgecolor="k", linewidth=1)
    ax.hlines([1, 2, 3], 0, 4, color="r")
    ax.vlines([1, 2], 0, 5, color="b")
    svg = fig.to_svg()
    assert svg.count("<polygon") == 2
    # hlines/vlines autoscaling picks up their extent
    (x0, x1), _ = ax._resolved_limits()
    assert x1 >= 4


# -- tick labels & inversion ------------------------------------------------
def test_custom_tick_labels():
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [1, 2, 3])
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["a", "b", "c"])
    svg = fig.to_svg()
    assert all(f">{t}<" in svg for t in ("a", "b", "c"))


def test_invert_yaxis_flips_transform():
    from plotpress.svg import _effective_rect, _pixel_rect
    from plotpress.transform import LinearTransform

    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 2])
    ax.invert_yaxis()
    (x0, x1), (y0, y1) = ax._resolved_limits()
    L, T, Wp, Hp = _effective_rect(ax, *_pixel_rect(ax, 640, 480), (x0, x1), (y0, y1))
    tr = LinearTransform((x0, x1), (y1, y0), (L, T, Wp, Hp))
    # Inverted: data-min sits at the TOP (smaller pixel y) than data-max.
    assert float(tr.y(y0)) < float(tr.y(y1))
    assert ax._yinverted is True


# -- legend placement -------------------------------------------------------
def test_legend_loc_ncol_title():
    fig, ax = plotpress.subplots()
    for i in range(4):
        ax.plot([0, 1], [i, i], label=f"s{i}")
    ax.legend(loc="lower left", ncol=2, title="Series")
    svg = fig.to_svg()
    assert ">Series<" in svg
    assert all(f">s{i}<" in svg for i in range(4))


def test_legend_default_still_works():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="line")
    ax.legend()
    assert "plotpress-legend" in fig.to_svg()


# -- shared colorbar --------------------------------------------------------
def test_shared_colorbar_over_axes_list():
    fig, axes = plotpress.subplots(2, 2)
    m = None
    for ax in axes.ravel():
        m = ax.pcolormesh(np.ones((4, 4)), vmin=0, vmax=1)
    cax = fig.colorbar(m, ax=axes)
    assert sum(1 for a in fig.axes if a._is_colorbar) == 1
    # the squeezed grid ends to the left of the colorbar
    right = max(a._rect[0] + a._rect[2] for a in axes.ravel())
    assert right <= cax._rect[0] + 1e-9


@pytest.mark.parametrize("order", ["ct", "tc", "tct", "ctt"])
def test_colorbar_and_tight_layout_compose_in_any_order(order):
    """tight_layout resets each subplot to a full grid cell, which used to undo
    the space colorbar had taken and strand the bar on top of its own plot."""
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(np.arange(25.0).reshape(5, 5))
    for step in order:
        fig.colorbar(m, ax=ax) if step == "c" else fig.tight_layout()
    cax = next(a for a in fig.axes if a._is_colorbar)
    assert ax._rect[0] + ax._rect[2] <= cax._rect[0] + 1e-9


def test_shared_colorbar_survives_tight_layout():
    fig, axes = plotpress.subplots(2, 2)
    m = None
    for ax in axes.ravel():
        m = ax.pcolormesh(np.ones((4, 4)), vmin=0, vmax=1)
    cax = fig.colorbar(m, ax=axes)
    fig.tight_layout()
    right = max(a._rect[0] + a._rect[2] for a in axes.ravel())
    assert right <= cax._rect[0] + 1e-9


def test_tight_layout_leaves_non_subplot_colorbar_parents_alone():
    """A parent tight_layout does not reflow keeps its original steal, so the
    colorbar must not be re-applied on top of it."""
    fig = plotpress.Figure()
    ax = fig.add_axes((0.1, 0.1, 0.8, 0.8))
    m = ax.pcolormesh(np.arange(25.0).reshape(5, 5))
    fig.colorbar(m, ax=ax)
    stolen = ax._rect
    fig.tight_layout()
    assert ax._rect == stolen


def test_colorbar_reserves_room_for_its_tick_labels():
    """The renderer draws tick labels outside the bar, so the steal has to cover
    them too -- otherwise they spill into the next subplot or off the figure."""
    from plotpress.figure import _cbar_label_width

    fig, axes = plotpress.subplots(1, 2)
    m = None
    for ax in axes:
        m = ax.pcolormesh(np.arange(25.0).reshape(5, 5) * 1000)
    cax = fig.colorbar(m, ax=axes[0])
    fig.tight_layout()

    label_w = _cbar_label_width(cax)
    assert label_w > 0
    # Labels clear the bar without reaching the neighbouring subplot.
    assert cax._rect[0] + cax._rect[2] + label_w <= axes[1]._rect[0] + 1e-9


def test_rightmost_colorbar_labels_stay_on_the_figure():
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(np.arange(25.0).reshape(5, 5) * 1e6)   # wide labels
    cax = fig.colorbar(m, ax=ax)
    fig.tight_layout()

    from plotpress.figure import _cbar_label_width
    assert cax._rect[0] + cax._rect[2] + _cbar_label_width(cax) <= 1.0 + 1e-9


def test_mappable_norms_are_scaled_before_anything_is_drawn():
    """Colorbar layout measures tick labels, which needs vmin/vmax up front."""
    fig, ax = plotpress.subplots()
    scat = ax.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], c=np.array([1.0, 5.0, 9.0]))
    mesh = ax.pcolormesh(np.arange(9.0).reshape(3, 3))
    for m in (scat, mesh):
        assert m.norm.vmin is not None and m.norm.vmax is not None


def test_single_axes_colorbar_still_works():
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(np.arange(9.0).reshape(3, 3))
    fig.colorbar(m, ax=ax)
    assert fig.to_svg().count("<image") == 2


def test_colorbar_honors_nonlinear_norm():
    from plotpress.colors import LogNorm, colorbar_ticks

    ln = LogNorm(vmin=1, vmax=1000)
    vals, fracs, labels = colorbar_ticks(ln)
    # decade tick values, positioned at log (not linear) fractions
    assert set(np.round(vals).astype(int)) <= {1, 10, 100, 1000}
    assert np.allclose(fracs, [0.0, 1 / 3, 2 / 3, 1.0], atol=1e-6)  # even in log space

    lin = plotpress.Normalize(0, 100)
    _, lfracs, _ = colorbar_ticks(lin)
    # linear norm -> evenly spaced fractions equal to value/100
    assert np.allclose(np.diff(lfracs), lfracs[1] - lfracs[0])


# -- contourf / hexbin ------------------------------------------------------
def test_contourf_is_banded_image_and_mappable():
    g = np.linspace(-2, 2, 20)
    X, Y = np.meshgrid(g, g)
    fig, ax = plotpress.subplots()
    cf = ax.contourf(g, g, np.exp(-(X ** 2 + Y ** 2)), levels=6, cmap="plasma")
    fig.colorbar(cf, ax=ax)                 # returns a valid mappable
    assert fig.to_svg().count("<image") == 2


def test_hexbin_makes_hexagons_and_is_mappable():
    rng = np.random.default_rng(0)
    x = rng.normal(size=2000)
    y = rng.normal(size=2000)
    fig, ax = plotpress.subplots()
    hb = ax.hexbin(x, y, gridsize=15)
    assert len(hb.verts) > 10
    assert all(v.shape == (6, 2) for v in hb.verts)   # hexagons
    assert hb.lut is not None and hb.norm is not None  # colorbar-ready
    assert fig.to_svg().count("<polygon") == len(hb.verts)


# -- sharex / sharey --------------------------------------------------------
def test_sharey_links_limits_and_hides_inner_labels():
    fig, axes = plotpress.subplots(1, 2, sharey=True)
    axes[0].plot([0, 1], [0, 2])
    axes[1].plot([0, 1], [0, 100])
    assert axes[0].get_ylim() == axes[1].get_ylim()   # shared span
    assert axes[0]._yticklabels is None               # left column shows labels
    assert axes[1]._yticklabels == []                 # right column hidden


def test_unshared_axes_stay_independent():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [0, 100])
    assert axes[0].get_ylim() != axes[1].get_ylim()


# -- PowerNorm / SymLogNorm -------------------------------------------------
def test_power_and_symlog_norms():
    p = PowerNorm(0.5, 0, 1)
    assert abs(float(p(np.array([0.25]))[0]) - 0.5) < 1e-9    # sqrt(0.25)
    s = SymLogNorm(1.0, -100, 100)
    out = s(np.array([-100.0, 0.0, 100.0]))
    np.testing.assert_allclose(out, [0.0, 0.5, 1.0], atol=1e-9)  # symmetric


# -- twinx / twiny ----------------------------------------------------------
def test_twinx_shares_x_independent_y():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 1])
    ax2 = ax.twinx()
    ax2.plot([0, 10], [0, 1000])
    assert ax2._twin_of is ax and ax2._twin_shared == "x"
    assert ax._resolved_limits()[0] == ax2._resolved_limits()[0]    # shared x
    assert ax._resolved_limits()[1] != ax2._resolved_limits()[1]    # own y
    ax2.set_ylabel("right")
    assert ">right<" in fig.to_svg()


def test_twiny_shares_y():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 10])
    ax2 = ax.twiny()
    ax2.plot([0, 500], [0, 10])
    assert ax._resolved_limits()[1] == ax2._resolved_limits()[1]    # shared y
    assert ax._resolved_limits()[0] != ax2._resolved_limits()[0]    # own x


# -- margins / bounds -------------------------------------------------------
def test_margins_and_bounds():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 5])
    ax.margins(0.1)
    x0, x1 = ax.get_xlim()
    assert x0 < 0 and x1 > 10                       # padded outward
    ax.set_xbound(0, 100)
    assert ax.get_xlim() == (0, 100)


# -- CN colors / matshow / spy / tick_params --------------------------------
def test_cn_color_notation():
    fig, ax = plotpress.subplots()
    cyc = ax.style.color_cycle
    assert ax.plot([0, 1], [0, 1], color="C0").color == cyc[0]
    assert ax.plot([0, 1], [1, 2], color="C3").color == cyc[3]
    assert ax.plot([0, 1], [2, 3], color="r").color == "r"   # named still passes


def test_matshow_and_spy():
    fig, ax = plotpress.subplots()
    ax.matshow(np.arange(9.0).reshape(3, 3))
    assert ax._aspect == 1.0 and "<image" in fig.to_svg()

    A = np.eye(5)
    fig2, ax2 = plotpress.subplots()
    ax2.spy(A)
    assert "<image" in fig2.to_svg() and ax2._aspect == 1.0


def test_tick_params_styles_ticks():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_params(labelsize=14, color="red", labelcolor="blue")
    svg = fig.to_svg()
    assert 'font-size="14"' in svg
    assert 'stroke="red"' in svg and 'fill="blue"' in svg


# -- axline / broken_barh / stairs ------------------------------------------
def test_axline_spans_without_autoscaling():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    ax.axline((0, 0), slope=0.5, color="r")
    ax.axline((0, 2), (10, 8), color="g")
    assert "plotpress-series" in fig.to_svg()
    _, (y0, y1) = ax._resolved_limits()
    assert y1 < 20                     # axline endpoints don't drive autoscale


def test_axline_requires_one_of_slope_or_point():
    fig, ax = plotpress.subplots()
    with pytest.raises(TypeError):
        ax.axline((0, 0))
    with pytest.raises(TypeError):
        ax.axline((0, 0), (1, 1), slope=2)


def test_broken_barh_and_stairs():
    fig, ax = plotpress.subplots()
    pc = ax.broken_barh([(1, 2), (5, 1)], (3, 1))
    assert len(pc.verts) == 2 and all(v.shape == (4, 2) for v in pc.verts)
    line = ax.stairs([1, 3, 2], edges=[0, 1, 2, 3])
    # step outline: doubled vertices, spans the edges
    assert line.x.min() == 0 and line.x.max() == 3


# -- huge-line decimation ---------------------------------------------------
def test_decimation_shrinks_huge_monotonic_line_but_keeps_envelope():
    from plotpress.primitives import _decimate_minmax

    x = np.linspace(0, 10, 50000)
    y = np.sin(x)
    y[25000] = 99.0                    # a spike that must survive
    dx, dy = _decimate_minmax(x, y, ncols=700)
    assert dx.size < 4000              # massively reduced from 50k
    assert dy.max() == 99.0            # min/max per column keeps the spike
    assert dx[0] == x[0] and dx[-1] == x[-1]   # endpoints preserved


def test_small_and_nonmonotonic_lines_are_not_decimated():
    from plotpress.primitives import _decimate_minmax, _is_monotonic

    # a parametric loop (non-monotonic x) must not be per-column collapsed
    t = np.linspace(0, 2 * np.pi, 10000)
    assert not _is_monotonic(np.cos(t))
    # short line: below threshold, output vertices unchanged
    fig, ax = plotpress.subplots()
    ax.plot(np.arange(100), np.arange(100))
    assert fig.to_svg().count("L") >= 99   # all ~100 vertices present


# -- curvilinear pcolormesh -------------------------------------------------
def test_curvilinear_pcolormesh_scan_converts():
    n = 20
    r = np.linspace(0.3, 1, n)
    th = np.linspace(0, 1.5 * np.pi, n)
    R, TH = np.meshgrid(r, th)
    X, Y = R * np.cos(TH), R * np.sin(TH)      # 2-D warped node coords
    C = np.sin(3 * TH) * R

    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(X, Y, C, cmap="plasma")
    assert m.curvilinear is True
    img = m.rgba()
    assert img.ndim == 3 and img.shape[2] == 4      # scan-converted RGBA image
    assert (img[..., 3] > 0).any()                  # some cells filled
    assert (img[..., 3] == 0).any()                 # background transparent (concave region)
    assert fig.to_svg().count("<image") == 1


def test_rectilinear_pcolormesh_uses_fast_path():
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(np.arange(5.0).reshape(5, 1) * np.ones(5))  # 1-arg -> 1-D path
    assert m.curvilinear is False
    assert m.rgba().shape == (5, 5, 4)              # no upsizing, direct colormap


def test_meshgrid_shaped_rectilinear_pcolormesh_uses_fast_path():
    """Regression: ``X, Y = np.meshgrid(x, y)`` then ``pcolormesh(X, Y, Z)`` is
    a common, perfectly rectilinear grid, but its coordinates arrive 2-D --
    indistinguishable in shape from a genuinely curvilinear grid. Without
    detecting this, every such call fell into curvilinear scan-conversion's
    per-cell Python loop, ~1000x slower than the vectorized rectilinear path
    for the identical grid passed as 1-D vectors."""
    x = np.linspace(0.0, 10.0, 60)
    y = np.linspace(0.0, 5.0, 40)
    X, Y = np.meshgrid(x, y)
    Z = np.sin(X) * np.cos(Y)

    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(X, Y, Z, cmap="viridis")
    assert m.curvilinear is False
    assert m.X.ndim == 1 and m.Y.ndim == 1
    np.testing.assert_allclose(m.X, x)
    np.testing.assert_allclose(m.Y, y)
    assert m.rgba().shape == (40, 60, 4)            # direct colormap, no scan conversion


def test_gouraud_shading_smoothly_interpolates():
    g = np.linspace(0, 1, 12)
    X, Y = np.meshgrid(g, g)
    C = X + Y                                        # smooth ramp
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(X, Y, C, cmap="viridis", shading="gouraud")
    assert m.shading == "gouraud"
    img = m.rgba()
    assert img.ndim == 3 and img.shape[:2] != C.shape   # upsampled raster
    # A smooth ramp should produce many distinct colors (not 12x12 flat cells)
    filled = img[img[..., 3] > 0][:, :3]
    assert len({tuple(px) for px in filled[::37]}) > 50
    assert fig.to_svg().count("<image") == 1


# -- shared primitive layer -------------------------------------------------
def test_geometric_artists_share_one_render_path():
    # The geometric family is converted to backend-agnostic primitives once;
    # both svg and raster consume the same converter (no per-backend renderer).
    from plotpress.primitives import artist_to_prims

    fig, ax = plotpress.subplots()
    line = ax.plot([0, 1, 2], [0, 1, 4])
    span = ax.axvspan(0.5, 1.5)
    hl = ax.hlines([1, 2], 0, 2)

    class _T:  # minimal transform stub
        xmin, xmax = 0.0, 2.0
        px_left = px_top = 0.0
        px_w = px_h = 100.0
        x = staticmethod(lambda v: np.asarray(v, float) * 50)
        y = staticmethod(lambda v: np.asarray(v, float) * 25)
        xy = staticmethod(lambda x, y: np.column_stack([np.asarray(x, float) * 50,
                                                        np.asarray(y, float) * 25]))

    for art in (line, span, hl):
        assert artist_to_prims(art, _T(), 0, 0) is not None   # migrated
    # a not-yet-migrated artist returns None (uses its legacy renderer)
    bars = ax.bar([0, 1], [1, 2])
    assert artist_to_prims(bars, _T(), 0, 0) is None


# -- backend parity regressions (found in the code audit) -------------------
def _nonbg_pixels(fig, scale=2):
    """Count pixels that differ from the figure background, for raster checks."""
    from plotpress.raster import figure_to_image
    arr = np.asarray(figure_to_image(fig, scale=scale))
    return int((arr < 250).any(axis=2).sum())


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_boxplot_renders_in_both_orientations_and_backends(orientation):
    """Regression: the raster backend only drew *vertical* boxplots, so a
    horizontal boxplot exported to PNG/PDF came out empty."""
    pytest.importorskip("PIL")
    rng = np.random.RandomState(0)
    data = [rng.normal(size=100) for _ in range(3)]
    fig, ax = plotpress.subplots()
    ax.boxplot(data, orientation=orientation)

    # An empty axes (just frame + ticks) for the same figure size, to prove the
    # boxes themselves add substantial ink in either orientation.
    empty, _ = plotpress.subplots()
    assert _nonbg_pixels(fig) > _nonbg_pixels(empty) * 2
    assert "<rect" in fig.to_svg()


def test_boxplot_fliers_render_in_raster():
    """Outliers past the whiskers draw as open circles in both backends."""
    pytest.importorskip("PIL")
    data = np.array([0.0, 1.0, 1.0, 1.0, 2.0, 100.0])   # 100 is a clear flier
    fig, ax = plotpress.subplots()
    ax.boxplot([data])
    assert "<circle" in fig.to_svg()
    with_flier = _nonbg_pixels(fig)
    fig2, ax2 = plotpress.subplots()
    ax2.boxplot([data[:-1]])                              # same data, no flier
    assert with_flier > _nonbg_pixels(fig2)


def test_pie_autopct_labels_render_in_both_backends():
    """Regression: ``autopct`` was accepted but never drawn by either backend,
    and the raster backend drew no wedge labels at all."""
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.pie([25, 25, 25, 25], labels=["AAAA", "BBBB", "CCCC", "DDDD"],
           autopct="%.0f%%")
    svg = fig.to_svg()
    assert "AAAA" in svg and "25%" in svg

    labelled = _nonbg_pixels(fig)
    fig2, ax2 = plotpress.subplots()
    ax2.pie([25, 25, 25, 25])                             # no labels / no pct
    assert labelled > _nonbg_pixels(fig2)


def test_pie_autopct_accepts_a_callable():
    fig, ax = plotpress.subplots()
    ax.pie([1, 3], autopct=lambda pct: f"[{pct:.0f}]")
    svg = fig.to_svg()
    assert "[25]" in svg and "[75]" in svg


@pytest.mark.parametrize("method,kw", [
    ("imshow", {}),
    ("hist2d", {}),
])
def test_image_autoscale_is_tight(method, kw):
    """Images pin the limits to their extent, like ``pcolormesh`` and
    matplotlib -- no 5% autoscale margin framing the raster in background."""
    fig, ax = plotpress.subplots()
    if method == "imshow":
        ax.imshow(np.arange(12).reshape(3, 4))
        assert ax.get_xlim() == (0.0, 4.0)
        assert ax.get_ylim() == (0.0, 3.0)
    else:
        x = np.array([0.0, 1.0, 2.0, 3.0])
        counts, im = ax.hist2d(x, x, bins=2)
        xlo, xhi = ax.get_xlim()
        assert xlo == pytest.approx(x.min()) and xhi == pytest.approx(x.max())


# -- spines, facecolor, visibility, lifecycle -------------------------------
def test_spines_visibility_and_per_side_color():
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_color("#123456")
    ax.spines["left"].set_linewidth(3.0)
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    # Spines are the only <line> elements carrying their own "stroke" attr --
    # everything else (ticks, grid) wraps its lines in a <g stroke=...> group.
    spine_lines = [el for el in root.iter(f"{ns}line") if "stroke" in el.attrib]
    assert len(spine_lines) == 3                       # top hidden
    assert {el.get("stroke") for el in spine_lines} >= {"#123456"}
    assert any(el.get("stroke-width") == "3.0" for el in spine_lines)
    assert ax.spines["top"].get_visible() is False
    assert ax.spines["right"].get_color() == "#123456"
    assert ax.spines["bottom"].get_color() == ax.style.spine_color  # untouched


def test_set_facecolor_is_per_axes():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    axes[0].set_facecolor("#ff00ff")
    svg = fig.to_svg()
    assert 'fill="#ff00ff"' in svg
    assert axes[1].get_facecolor() == axes[1].style.axes_facecolor  # untouched


def test_set_visible_hides_content_but_keeps_grid_cell():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    rect_before = axes[1]._rect
    axes[1].set_visible(False)
    assert axes[1].get_visible() is False
    # A hidden axes draws nothing and is excluded from point-picking metadata...
    from plotpress.svg import axes_metadata
    meta = axes_metadata(fig)
    assert 1 not in meta and 0 in meta
    # ...but still occupies its grid cell (unchanged rect).
    assert axes[1]._rect == rect_before


def test_axes_remove_detaches_from_figure_and_share_group():
    fig, axes = plotpress.subplots(1, 2, sharex=True)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    axes[1].remove()
    assert axes[1] not in fig.axes
    assert axes[1] not in axes[0]._sharex_group


def test_axes_cla_resets_state_but_keeps_position():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("hi")
    ax.set_xlim(2, 3)
    rect = ax._rect
    ax.cla()
    assert ax.get_title() == ""
    assert ax.artists == []
    assert ax._xlim is None
    assert ax._rect == rect
    assert ax in fig.axes


def test_axes_cla_detaches_from_its_share_group():
    """Regression: cla() re-ran the constructor, which sets _sharex_group to
    None on the cleared axes but never removed it from the *old* group's
    list -- so a sibling's set_xlim still updated the shared span using a
    member that no longer identifies as sharing anything."""
    fig, (ax1, ax2) = plotpress.subplots(1, 2, sharex=True)
    assert ax2 in ax1._sharex_group

    ax2.cla()
    assert ax2 not in ax1._sharex_group
    assert ax2._sharex_group is None

    ax1.set_xlim(5, 9)
    assert ax1.get_xlim() == (5, 9)
    assert ax2.get_xlim() != (5, 9)   # no longer shares the group


# -- getters ------------------------------------------------------------
def test_getters_mirror_setters():
    fig, ax = plotpress.subplots()
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("t")
    ax.set_xscale("log"); ax.plot([1, 10], [1, 2])
    assert ax.get_xlabel() == "x" and ax.get_ylabel() == "y" and ax.get_title() == "t"
    assert ax.get_xscale() == "log" and ax.get_yscale() == "linear"
    assert len(ax.get_xticks()) > 0 and len(ax.get_yticks()) > 0


# -- minor ticks / tick side -------------------------------------------------
def test_minorticks_on_adds_extra_marks():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    svg_before = fig.to_svg()
    ax.minorticks_on()
    svg_after = fig.to_svg()
    assert len(svg_after) > len(svg_before)
    ax.minorticks_off()
    assert fig.to_svg() == svg_before


def test_tick_top_and_right_move_tick_position():
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_top()
    ax.tick_right()
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    spine_lines = [el for el in root.iter(f"{ns}line") if "stroke" in el.attrib]
    top = next(el for el in spine_lines
              if float(el.get("y1")) == float(el.get("y2")) and
              float(el.get("y1")) < 100)  # the top edge sits near the figure top
    assert top is not None  # spines are unaffected by tick side (sanity)
    assert ax._xtick_side == "top" and ax._ytick_side == "right"


# -- sharex/sharey post-hoc, label_outer -------------------------------------
def test_tick_top_title_clears_the_moved_ticks():
    """Regression: tick_top() moves ticks into the title's band; the title
    must reserve room for them instead of being drawn on top."""
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_top()
    ax.set_title("t")
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    texts = [el for el in root.iter(f"{ns}text")]
    title_y = float(next(el for el in texts if el.text == "t").get("y"))
    tick_label_y = max(float(el.get("y")) for el in texts if el.text == "0")
    assert title_y < tick_label_y   # smaller y = higher on the page = above


def test_secondary_xaxis_title_clears_its_ticks_and_label():
    """Regression: twiny_headroom (which the title's y-position is computed
    from) checked for an attached twin but not an attached secondary_xaxis,
    so a title on the parent axes overlapped the secondary's top ticks/label."""
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("t")
    sec = ax.secondary_xaxis("top", label="secondary")
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    texts = list(root.iter(f"{ns}text"))
    title_y = float(next(e for e in texts if e.text == "t").get("y"))
    label_y = float(next(e for e in texts if e.text == "secondary").get("y"))
    assert title_y < label_y   # smaller y = higher on the page = above


def test_sharex_sharey_posthoc_merge_groups():
    fig, ax1 = plotpress.subplots()
    fig2, ax2 = plotpress.subplots()
    ax1.plot([0, 1], [0, 5])
    ax2.plot([0, 1], [0, 500])
    ax1.sharex(ax2)
    assert ax1._sharex_group is ax2._sharex_group
    assert ax1.get_xlim() == ax2.get_xlim()


def test_label_outer_hides_interior_labels_only():
    fig, axg = plotpress.subplots(2, 2)
    for a in axg.ravel():
        a.plot([0, 1], [0, 1])
    axg[0, 0].label_outer()   # top-left: not bottom row, is left column
    assert axg[0, 0]._xticklabels == []
    assert axg[0, 0]._yticklabels is None
    axg[1, 1].label_outer()   # bottom-right: is bottom row, not left column
    assert axg[1, 1]._xticklabels is None
    assert axg[1, 1]._yticklabels == []


# -- persistent margins / autoscale ------------------------------------------
def test_margins_persist_across_new_data():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 5])
    ax.margins(0.1)
    x0, x1 = ax.get_xlim()
    assert x0 < 0 and x1 > 10
    ax.plot([0, 100], [0, 5])   # more data after margins() -- must still pad
    x0b, x1b = ax.get_xlim()
    assert x0b < 0 and x1b > 100
    assert ax.get_xmargin() == pytest.approx(0.1)


def test_autoscale_freeze_and_reenable():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 5])
    ax.autoscale(enable=False, axis="x")
    frozen = ax.get_xlim()
    ax.plot([0, 1000], [0, 5])
    assert ax.get_xlim() == frozen        # frozen: new data doesn't move it
    ax.autoscale(enable=True, axis="x")
    assert ax.get_xlim() != frozen        # re-enabled: picks up the new data


# -- axis() convenience, set_prop_cycle --------------------------------------
def test_axis_convenience():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.axis("off")
    assert ax._axis_off is True
    ax.axis("on")
    assert ax._axis_off is False
    ax.axis("equal")
    assert ax._aspect == 1.0
    result = ax.axis([0, 5, -1, 1])
    assert result == (0, 5, -1, 1)
    assert ax.get_xlim() == (0, 5) and ax.get_ylim() == (-1, 1)


def test_set_prop_cycle_is_per_axes_not_shared_style():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].set_prop_cycle(["#111111", "#222222"])
    l0 = axes[0].plot([0, 1], [0, 1])
    l1 = axes[1].plot([0, 1], [0, 1])   # untouched axes keeps the default cycle
    assert l0.color == "#111111"
    assert l1.color == axes[1].style.color_cycle[0]
    assert axes[0].style.color_cycle == axes[1].style.color_cycle  # style untouched


# -- Phase 2: figure-level layout --------------------------------------
def test_set_size_inches_and_dpi():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.set_size_inches(8, 5)
    fig.set_dpi(150)
    assert fig.get_size_inches() == (8.0, 5.0)
    assert fig.get_dpi() == 150.0
    svg = fig.to_svg()
    assert 'width="1200"' in svg and 'height="750"' in svg   # 8*150, 5*150


def test_set_size_inches_refits_after_tight_layout():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.tight_layout()
    rect_before = ax._rect
    fig.set_size_inches(20, 2)   # very different aspect -- margins must rescale
    fig.to_svg()                  # forces _settle_layout()
    assert ax._rect != rect_before


def test_gridspec_row_span():
    fig = plotpress.Figure(figsize=(6, 6))
    gs = fig.add_gridspec(2, 2)
    top = fig.add_subplot(gs[0, :])
    bl = fig.add_subplot(gs[1, 0])
    br = fig.add_subplot(gs[1, 1])
    for ax in (top, bl, br):
        ax.plot([0, 1], [0, 1])
    fig.tight_layout()
    # The spanning axes covers the same left/right extent as the two below it.
    assert top._rect[0] == pytest.approx(bl._rect[0])
    assert top._rect[0] + top._rect[2] == pytest.approx(br._rect[0] + br._rect[2])
    # The two bottom cells don't overlap and are each narrower than the span.
    assert bl._rect[0] + bl._rect[2] <= br._rect[0] + 1e-9
    assert bl._rect[2] < top._rect[2]


def test_gridspec_rejects_stepped_slice():
    fig = plotpress.Figure()
    gs = fig.add_gridspec(4, 4)
    with pytest.raises(ValueError):
        gs[::2, 0]


def test_subplots_adjust_moves_grid_and_is_partial():
    fig, axes = plotpress.subplots(2, 2)
    for a in axes.ravel():
        a.plot([0, 1], [0, 1])
    fig.subplots_adjust(left=0.3)
    left_after_first = axes[0, 0]._rect[0]
    assert left_after_first == pytest.approx(0.3)
    fig.subplots_adjust(wspace=0.6)          # partial call: left=0.3 must persist
    assert axes[0, 0]._rect[0] == pytest.approx(0.3)


def test_subplots_adjust_and_tight_layout_are_mutually_exclusive():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.tight_layout()
    fig.subplots_adjust(left=0.3)
    assert fig._tight_pad is None    # tight_layout's pending re-fit is cleared
    ax.set_title("t")                # would normally trigger a tight_layout re-fit
    fig.to_svg()
    assert ax._rect[0] == pytest.approx(0.3)   # subplots_adjust's margin held


def test_align_ylabels_matches_widest_tick_label():
    # Stacked in one column: this is the case align_ylabels is for.
    fig, (a1, a2) = plotpress.subplots(2, 1)
    a1.plot([0, 1], [0, 100000])   # wide tick labels
    a1.set_ylabel("y1")
    a2.plot([0, 1], [0, 1])
    a2.set_ylabel("y2")
    assert a1._ylabel_x_override is None
    fig.align_ylabels()
    assert a1._ylabel_x_override == a2._ylabel_x_override
    assert "y1" in fig.to_svg() and "y2" in fig.to_svg()


def test_align_labels_scoped_to_column_or_row():
    """align_ylabels only pulls together axes in the same column (stacked
    rows); side-by-side axes in different columns must not collapse onto the
    same override -- each keeps its own natural, unaligned position."""
    fig, (a1, a2) = plotpress.subplots(1, 2)
    a1.plot([0, 1], [0, 100000])
    a1.set_ylabel("y1")
    a2.plot([0, 1], [0, 1])
    a2.set_ylabel("y2")
    fig.align_ylabels()
    assert a1._ylabel_x_override != a2._ylabel_x_override


def test_align_labels_survives_tight_layout_relayout():
    """Regression: align_ylabels' override must track the *current* layout,
    not freeze the value from whenever it was first computed -- otherwise a
    later tight_layout()/subplots_adjust() (which moves every axes' rect)
    leaves the override pointing at a position that no longer matches either
    panel's actual box.
    """
    # Stacked in one column, so both panels' y labels are in the same group.
    fig, (a1, a2) = plotpress.subplots(2, 1)
    a1.plot([0, 1], [0, 100000]); a1.set_ylabel("y1")
    a2.plot([0, 1], [0, 1]); a2.set_ylabel("y2")
    fig.tight_layout(pad=0.02)
    fig.align_ylabels()
    small_pad_override = a1._ylabel_x_override
    assert a1._ylabel_x_override == a2._ylabel_x_override

    fig.tight_layout(pad=0.15)   # a much bigger pad moves every axes' rect
    # Without the re-apply, both would still read small_pad_override.
    assert a1._ylabel_x_override != small_pad_override
    assert a1._ylabel_x_override == a2._ylabel_x_override

    # Side by side in one row: both panels' x labels are in the same group.
    fig2, (b1, b2) = plotpress.subplots(1, 2)
    b1.plot([0, 1], [0, 1]); b1.set_xlabel("x1")
    b2.plot([0, 1], [0, 1]); b2.set_xlabel("x2")
    fig2.align_xlabels()
    assert b1._xlabel_y_override == b2._xlabel_y_override


def test_delaxes_and_clf():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.delaxes(ax)
    assert ax not in fig.axes

    fig2, axes2 = plotpress.subplots(1, 2)
    for a in axes2:
        a.plot([0, 1], [0, 1])
    fig2.suptitle("hi")
    fig2.clf()
    assert fig2.axes == []
    assert fig2._suptitle is None
    assert fig2.figsize == (6.4, 4.8)   # figsize/style survive clf()


def test_figure_text_positions_by_fraction():
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.text(0.5, 0.5, "watermark", ha="center", va="center", color="#ff0000")
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    el = next(e for e in root.iter(f"{ns}text") if e.text == "watermark")
    assert el.get("fill") == "#ff0000"
    assert el.get("text-anchor") == "middle"


def test_figure_text_renders_in_raster():
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.text(0.1, 0.1, "corner note")
    figure_to_image(fig, scale=1)   # must not raise


# -- Phase 3: secondary/inset axes, set_position ----------------------------
def test_secondary_xaxis_mirrors_parent_xlim():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 5])
    sec = ax.secondary_xaxis("top", label="mirrored")
    assert sec.get_xlim() == ax.get_xlim()
    ax.set_xlim(2, 8)             # parent moves...
    assert sec.get_xlim() == (2, 8)   # ...secondary follows, unconditionally
    assert sec._xtick_side == "top"
    svg = fig.to_svg()
    assert "mirrored" in svg


def test_secondary_yaxis_mirrors_parent_ylim():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 500])
    sec = ax.secondary_yaxis("right")
    assert sec.get_ylim() == ax.get_ylim()
    assert sec._ytick_side == "right"
    assert sec._secondary_of is ax and sec._secondary_dim == "y"


def test_secondary_axis_draws_only_its_own_dimension():
    """A secondary axis has no data of its own -- it must draw ticks for its
    mirrored dimension only, never a background rect or spines (which would
    obscure the parent it overlays)."""
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_facecolor("#123456")   # distinguishes the axes bg from the figure bg
    ax.secondary_xaxis("top")
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    # Exactly one background rect (the parent's) -- the secondary draws none.
    fills = [el.get("fill") for el in root.iter(f"{ns}rect")]
    assert fills.count("#123456") == 1
    # One set of 4 spine lines (the parent's box) -- the secondary draws none.
    spine_lines = [el for el in root.iter(f"{ns}line") if "stroke" in el.attrib]
    assert len(spine_lines) == 4


def test_tick_top_moves_xlabel_too():
    """Regression: tick_top()/tick_right() must move the axis *label* along
    with the ticks, not just the tick marks -- found while building
    secondary_xaxis, which relies on the same side-aware label placement."""
    import xml.etree.ElementTree as ET

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("moved")
    ax.tick_top()
    root = ET.fromstring(fig.to_svg())
    ns = "{http://www.w3.org/2000/svg}"
    label = next(e for e in root.iter(f"{ns}text") if e.text == "moved")
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    from plotpress.svg import _effective_rect, _pixel_rect
    px_left, px_top, px_w, px_h = _effective_rect(
        ax, *_pixel_rect(ax, 640, 480), (xmin, xmax), (ymin, ymax))
    assert float(label.get("y")) < px_top    # above the box, not below it


def test_inset_axes_tracks_parent_through_relayout():
    fig, axes = plotpress.subplots(1, 2)
    ax = axes[0]
    ax.plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    inset = ax.inset_axes([0.6, 0.6, 0.3, 0.3])
    inset.plot([0, 1], [0, 1])
    assert inset._inset_parent is ax
    fig.tight_layout()   # moves ax's rect -- inset must be re-derived from it
    pl, pb, pw, ph = ax._rect
    ex_left = pl + 0.6 * pw
    ex_bottom = pb + 0.6 * ph
    assert inset._rect[0] == pytest.approx(ex_left)
    assert inset._rect[1] == pytest.approx(ex_bottom)
    assert inset._subplotspec is None   # not itself a grid member


def test_set_position_opts_out_of_tight_layout():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_position((0.3, 0.3, 0.4, 0.4))
    assert ax.get_position() == (0.3, 0.3, 0.4, 0.4)
    assert ax._subplotspec is None
    fig.tight_layout()
    assert ax._rect == (0.3, 0.3, 0.4, 0.4)   # untouched: no longer a grid member


def test_hexbin_conserves_point_counts():
    """Every point lands in exactly one hexagon, so with mincnt=1 the counts
    sum to the number of points (guards the vectorized cell tally)."""
    from plotpress.axes import _hexbin
    rng = np.random.RandomState(1)
    x, y = rng.normal(size=2000), rng.normal(size=2000)
    verts, counts = _hexbin(x, y, 15, 1)
    assert counts.sum() == x.size
    assert len(verts) == len(counts)


# -- Tier 1/2 kwarg gaps closed (audit: "are there missing kwargs?") --------
def test_plot_marker_draws_a_dot_per_vertex():
    """Regression: the raster backend zips Markers.colors against
    points/diameters and silently truncates to the shortest -- passing a
    single-element colors list (rather than one entry per point, like
    ScatterCollection already does) drew only the *first* vertex's marker,
    with no error to reveal the other N-1 were silently dropped."""
    import numpy as np
    from plotpress.raster import figure_to_image

    x = np.linspace(0, 10, 12)
    fig, ax = plotpress.subplots()
    line = ax.plot(x, np.sin(x), marker="o", markersize=8,
                   markerfacecolor="#ff0000", color="#888888")
    assert line.marker == "o"

    svg = fig.to_svg()
    assert 'fill="none" stroke="#ff0000"' in svg   # the dot path's own stroke

    arr = np.asarray(figure_to_image(fig, scale=1))
    red_pixels = int(((arr[..., 0] > 200) & (arr[..., 1] < 80) & (arr[..., 2] < 80)).sum())
    # 12 markers of real size -- one lone pixel would mean only one survived.
    assert red_pixels > 50


def test_plot_without_marker_draws_no_dots():
    """Backward compatibility: a plain plot() (no marker=) must still emit
    exactly one path (the line itself) -- not stroke-linecap="round",
    which the line's own path already carries unconditionally regardless
    of markers, so that alone can't distinguish the two."""
    fig, ax = plotpress.subplots()
    line = ax.plot([0, 1, 2], [0, 1, 4])
    assert line.marker is None
    svg = fig.to_svg()
    assert svg.count("<path") == 1

    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 1, 2], [0, 1, 4], marker="o")
    assert fig2.to_svg().count("<path") == 2   # the line, plus the markers' own path


def test_plot_marker_warns_on_non_round_shape():
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning):
        ax.plot([0, 1], [0, 1], marker="s")   # square: accepted, drawn as a dot


def test_bar_yerr_draws_caps_and_whiskers_and_autoscales():
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [3, 5, 2], yerr=[0.5, 1.0, 0.3], capsize=5)
    svg = fig.to_svg()
    assert svg.count("<rect") >= 3               # the bars themselves
    assert svg.count("<line") >= 9                # 3 whiskers + 6 cap ends
    _, (ymin, ymax) = ax._resolved_limits()
    assert ymax >= 6.0                            # bar 1's top (5) + yerr (1)


def test_barh_xerr_draws_error_bars_on_the_value_axis():
    fig, ax = plotpress.subplots()
    ax.barh([0, 1], [4, 6], xerr=[1.0, 0.5])
    (xmin, xmax), _ = ax._resolved_limits()
    assert xmax >= 6.5                            # bar 2's right edge (6) + xerr (0.5)


def test_errorbar_xerr_renders_in_raster_backend():
    """Regression: raster._errorbar() had a branch for eb.yerr but none at
    all for eb.xerr -- errorbar(xerr=...) (and, composed on top of it,
    barh()'s own xerr) rendered correctly in SVG but drew nothing in
    PNG/PDF output, with no error to reveal the whiskers/caps were
    silently missing. Found via barh()'s new xerr= composing on top of
    errorbar(), the first real path to exercise xerr with no yerr."""
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.errorbar([0, 1, 2], [1, 1, 1], xerr=[0.3, 0.3, 0.3], linestyle="none",
               marker=None, markersize=0.0)
    with_xerr = _nonbg_pixels(fig)

    fig2, ax2 = plotpress.subplots()
    ax2.errorbar([0, 1, 2], [1, 1, 1], linestyle="none", marker=None,
                markersize=0.0)
    without_xerr = _nonbg_pixels(fig2)
    assert with_xerr > without_xerr


def test_barh_xerr_renders_in_raster_backend():
    """Same regression as test_errorbar_xerr_renders_in_raster_backend, via
    the composed bar()/barh() path. xlim is fixed identically on both
    figures -- otherwise adding xerr widens autoscale, which shrinks the
    bars themselves in pixel terms and can net *fewer* total ink pixels
    despite the whiskers/caps actually being there, confounding a bare
    ink-count comparison."""
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.barh([0, 1], [4, 6], xerr=[1.0, 0.5])
    ax.set_xlim(0, 8)
    with_xerr = _nonbg_pixels(fig)

    fig2, ax2 = plotpress.subplots()
    ax2.barh([0, 1], [4, 6])
    ax2.set_xlim(0, 8)
    without_xerr = _nonbg_pixels(fig2)
    assert with_xerr > without_xerr


def test_bar_without_yerr_adds_no_extra_artist():
    fig, ax = plotpress.subplots()
    ax.bar([0, 1], [3, 5])
    assert len(ax.artists) == 1                   # just the Bars, no ErrorBar


def test_bar_yerr_ecolor_is_independent_of_bar_color():
    fig, ax = plotpress.subplots()
    ax.bar([0], [3], yerr=[0.5], color="#00ff00", ecolor="#ff00ff")
    svg = fig.to_svg()
    assert 'fill="#00ff00"' in svg      # the bar itself
    assert "#ff00ff" in svg             # the error bar, independently colored


def test_fill_between_and_fill_betweenx_accept_edgecolor_and_linewidth():
    import numpy as np

    fig, ax = plotpress.subplots()
    fb = ax.fill_between([0, 1, 2], [0, 1, 0], edgecolor="#123456", linewidth=2.0)
    assert fb.edgecolor == "#123456" and fb.linewidth == 2.0
    svg = fig.to_svg()
    assert 'stroke="#123456"' in svg

    fig2, ax2 = plotpress.subplots()
    y = np.linspace(0, 5, 10)
    ax2.fill_betweenx(y, 0, np.ones_like(y), edgecolor="#654321", linewidth=1.5)
    assert 'stroke="#654321"' in fig2.to_svg()


def test_fill_between_default_has_no_visible_edge():
    """Backward compatibility: no edgecolor given must render exactly as
    before -- no stroke attribute added to the fill path."""
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1, 2], [0, 1, 0])
    assert 'stroke="None"' not in fig.to_svg()


def _near_black_pixels(fig, scale=2, thresh=80):
    """Count pixels close to black, for checking a specific dark outline's
    thickness where the fill itself already makes the whole shape count as
    "non-background" -- _nonbg_pixels can't see a thicker edge drawn entirely
    inside an already-non-background fill."""
    from plotpress.raster import figure_to_image
    arr = np.asarray(figure_to_image(fig, scale=scale)).astype(int)
    return int((arr[:, :, :3].max(axis=2) < thresh).sum())


def test_fill_between_linewidth_renders_in_raster_backend():
    """Regression: raster._composite_polygon() passed a filled shape's
    outline *color* to PIL but never its *width* -- fill_between()/fill()'s
    linewidth= scaled the stroke correctly in SVG but always drew PIL's own
    default 1px outline in PNG/PDF, regardless of what was requested. A
    thin vs. a thick edge on the same fill must produce different ink."""
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1, 2], [0, 1, 0], edgecolor="#000000", linewidth=1.0)
    thin = _near_black_pixels(fig)

    fig2, ax2 = plotpress.subplots()
    ax2.fill_between([0, 1, 2], [0, 1, 0], edgecolor="#000000", linewidth=12.0)
    thick = _near_black_pixels(fig2)
    assert thick > thin


def test_contour_vmin_vmax_changes_level_colors():
    import numpy as np

    g = np.linspace(-2, 2, 20)
    X, Y = np.meshgrid(g, g)
    Z = np.exp(-(X ** 2 + Y ** 2))

    fig1, ax1 = plotpress.subplots()
    c1 = ax1.contour(g, g, Z, levels=[0.5], cmap="viridis")
    fig2, ax2 = plotpress.subplots()
    c2 = ax2.contour(g, g, Z, levels=[0.5], cmap="viridis", vmin=0, vmax=10)
    # Same level, same data, but a much wider vmax pushes 0.5 far down the
    # colormap compared to the default (auto vmin/vmax from Z itself).
    assert c1.colors[0] != c2.colors[0]


def test_contour_colors_non_uniform_levels_by_value_not_rank():
    """Regression: colors used to come from each level's *rank* in the
    levels array (np.linspace(0, 255, len(levels))), which only matched
    value-based normalization when levels happened to be evenly spaced.
    Two levels close in value must get close colors, even if a third,
    far-away level is also in the list."""
    import numpy as np

    g = np.linspace(-2, 2, 20)
    X, Y = np.meshgrid(g, g)
    Z = X + Y   # smooth linear ramp: color should track value linearly

    fig, ax = plotpress.subplots()
    c = ax.contour(g, g, Z, levels=[-3.9, -3.8, 4.0], cmap="viridis")
    lo, mid, hi = (tuple(int(c.colors[i][j:j + 2], 16) for j in (1, 3, 5))
                   for i in range(3))
    dist_lo_mid = sum((a - b) ** 2 for a, b in zip(lo, mid))
    dist_mid_hi = sum((a - b) ** 2 for a, b in zip(mid, hi))
    assert dist_lo_mid < dist_mid_hi   # -3.9 and -3.8 are near-identical values


def test_contour_default_vmin_vmax_matches_old_evenly_spaced_behavior():
    """Auto levels (evenly spaced across Z's own range) must still color
    exactly as before -- the fix only changes non-uniform/explicit-vmin
    cases, not the common default path."""
    import numpy as np

    g = np.linspace(-2, 2, 20)
    X, Y = np.meshgrid(g, g)
    Z = np.exp(-(X ** 2 + Y ** 2))
    fig, ax = plotpress.subplots()
    c = ax.contour(g, g, Z, levels=5, cmap="viridis")
    assert len(set(c.colors)) == len(c.levels)   # 5 distinct levels, 5 distinct colors


# -- Tier 0/1 gaps closed: imshow(alpha=) was a silent no-op; zorder was
# missing entirely, cross-cutting every artist type --------------------

def test_imshow_alpha_actually_renders():
    """Regression: Image.__init__ stored alpha but nothing ever read it back
    -- apply_colormap() always emitted a full-255 alpha channel, and no
    opacity ever reached the <image> tag, so imshow(alpha=...) rendered
    identically to alpha=1.0 in both backends despite being documented as
    a working parameter."""
    import numpy as np

    X = np.random.RandomState(0).rand(8, 8)
    fig1, ax1 = plotpress.subplots()
    ax1.imshow(X, alpha=1.0)
    fig2, ax2 = plotpress.subplots()
    ax2.imshow(X, alpha=0.2)
    assert fig1.to_svg() != fig2.to_svg()

    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image
    arr1 = np.asarray(figure_to_image(fig1))
    arr2 = np.asarray(figure_to_image(fig2))
    assert not np.array_equal(arr1, arr2)   # low alpha must blend toward the background


def test_imshow_alpha_still_respects_nan_transparency():
    """The alpha fix multiplies into the existing alpha channel rather than
    overwriting it -- a NaN cell (already transparent) must stay transparent
    regardless of the uniform alpha=, not partially "reappear"."""
    import numpy as np
    from plotpress.artists import Image

    A = np.array([[0.0, np.nan], [1.0, 0.5]])
    im = Image(A, alpha=0.5)
    rgba = im.rgba()
    assert rgba[0, 1, 3] == 0          # NaN cell: still fully transparent
    assert 0 < rgba[0, 0, 3] < 255     # finite cell: scaled down, not opaque


def test_zorder_default_is_call_order():
    """Backward compatibility: with no explicit zorder, later calls still
    draw on top, exactly as before zorder existed."""
    import re
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1], [0, 1], [1, 1], color="#0000ff")
    ax.fill_between([0, 1], [0, 0.5], [1.5, 1.5], color="#ff0000")
    order = [m for m in re.findall(r'fill="(#[0-9a-f]{6})"', fig.to_svg())
             if m in ("#0000ff", "#ff0000")]
    assert order == ["#0000ff", "#ff0000"]   # red (called second) drawn on top


def test_zorder_overrides_call_order_in_svg():
    """A lower zorder draws underneath even if it was called later."""
    import re
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1], [0, 1], [1, 1], color="#0000ff", zorder=1)
    ax.fill_between([0, 1], [0, 0.5], [1.5, 1.5], color="#ff0000", zorder=0)
    order = [m for m in re.findall(r'fill="(#[0-9a-f]{6})"', fig.to_svg())
             if m in ("#0000ff", "#ff0000")]
    assert order == ["#ff0000", "#0000ff"]   # red drawn first (underneath) despite being called second


def test_zorder_overrides_call_order_in_raster():
    """Same regression as the SVG version, checked against actual rendered
    pixels in the raster backend -- svg.py and raster.py sort independently,
    so each needs its own proof."""
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots()
    ax.bar([0], [1], width=2.0, color="#0000ff", zorder=0)
    ax.bar([0], [1], width=1.0, color="#ff0000", zorder=-1)   # narrower, called
                                                               # later, but lower zorder
    ax.set_xlim(-2, 2)
    ax.set_ylim(0, 1.2)
    arr = np.asarray(figure_to_image(fig, scale=1))
    h, w, _ = arr.shape
    cx, cy = w // 2, int(h * 0.6)   # inside both rects' overlap
    assert tuple(arr[cy, cx][:3]) == (0, 0, 255)   # blue on top despite red's later call


# -- Tier 2/3 gaps closed: pcolormesh alpha/label, scatter edge, legend
# handles/labels/fontsize, hist histtype/cumulative/weights/stacked,
# boxplot whis/showfliers, errorbar ecolor/elinewidth/capthick, imshow
# interpolation -----------------------------------------------------------

def test_pcolormesh_accepts_alpha_and_label():
    """pcolormesh's own animated sibling (pcolormesh_frames) already had
    both; the static one hadn't caught up."""
    X = np.random.RandomState(0).rand(6, 6)
    fig1, ax1 = plotpress.subplots()
    ax1.pcolormesh(X, alpha=1.0)
    fig2, ax2 = plotpress.subplots()
    ax2.pcolormesh(X, alpha=0.2)
    assert fig1.to_svg() != fig2.to_svg()

    fig3, ax3 = plotpress.subplots()
    ax3.pcolormesh(X, label="field")
    ax3.legend()
    assert "field" in fig3.to_svg()


def test_scatter_edgecolors_and_linewidths_render_in_both_backends():
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots()
    coll = ax.scatter([0, 1, 2], [0, 1, 0], s=20, color="#ffdd00",
                      edgecolors="black", linewidths=3.0)
    assert coll.edgecolor == "black" and coll.linewidths == 3.0
    svg = fig.to_svg()
    assert 'stroke="black"' in svg

    fig2, ax2 = plotpress.subplots()
    ax2.scatter([0, 1, 2], [0, 1, 0], s=20, color="#ffdd00")
    plain = np.asarray(figure_to_image(fig2))
    edged = np.asarray(figure_to_image(fig))
    assert not np.array_equal(plain, edged)   # the edge must add real ink


def test_scatter_edgecolors_default_linewidth_is_visible():
    """Giving edgecolors with no explicit linewidths must still draw a
    visible outline, not a zero-width (invisible) one."""
    fig, ax = plotpress.subplots()
    coll = ax.scatter([0], [0], edgecolors="red")
    assert coll.linewidths > 0


def test_legend_handles_and_labels_override_the_default_entries():
    """handles= picks specific artists (even ones never added to this
    axes) in the given order; labels= overrides their own label."""
    from plotpress.artists import Line2D

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="real")
    proxy = Line2D(np.array([0.0]), np.array([0.0]), color="red",
                   linewidth=2, label="proxy")
    ax.legend(handles=[proxy], labels=["custom"])
    svg = fig.to_svg()
    legend_svg = svg.split("plotpress-legend")[1]
    assert "custom" in legend_svg and "real" not in legend_svg


def test_legend_fontsize_changes_rendered_size_in_both_backends():
    """Regression: raster._raster_legend() recomputed entries/fontsize
    independently of svg.py's shared layout instead of reusing it, so
    legend(handles=, fontsize=) rendered correctly in SVG but was silently
    ignored in PNG/PDF -- every entry always came from ax.artists at the
    style's own fixed size in raster, regardless of what was requested."""
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    fig1, ax1 = plotpress.subplots()
    ax1.plot([0, 1], [0, 1], label="s")
    ax1.legend(fontsize=8)
    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 1], [0, 1], label="s")
    ax2.legend(fontsize=30)
    assert fig1.to_svg() != fig2.to_svg()
    img1 = np.asarray(figure_to_image(fig1))
    img2 = np.asarray(figure_to_image(fig2))
    assert not np.array_equal(img1, img2)


def test_hist_histtype_step_and_stepfilled():
    from plotpress.artists import Polygon, Bars

    x = np.array([0.0, 1, 1, 2, 2, 2, 3])
    fig, ax = plotpress.subplots()
    _, _, b = ax.hist(x, bins=4, histtype="bar")
    assert isinstance(b, Bars)

    fig2, ax2 = plotpress.subplots()
    _, _, p = ax2.hist(x, bins=4, histtype="step", color="red")
    assert isinstance(p, Polygon) and p.color is None and p.edgecolor == "red"

    fig3, ax3 = plotpress.subplots()
    _, _, pf = ax3.hist(x, bins=4, histtype="stepfilled", color="blue")
    assert isinstance(pf, Polygon) and pf.color == "blue"


def test_hist_cumulative_is_monotonic():
    x = np.random.RandomState(0).normal(size=200)
    fig, ax = plotpress.subplots()
    counts, edges, b = ax.hist(x, bins=10, cumulative=True)
    assert np.all(np.diff(counts) >= 0)
    assert counts[-1] == 200


def test_hist_weights_scale_counts():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    fig, ax = plotpress.subplots()
    counts, edges, b = ax.hist(x, bins=4, range=(0, 4))
    fig2, ax2 = plotpress.subplots()
    counts_w, _, _ = ax2.hist(x, bins=4, range=(0, 4), weights=np.full(4, 2.0))
    assert np.allclose(counts_w, counts * 2)


def test_hist_stacked_multiple_datasets():
    d1 = np.array([0.0, 1.0])
    d2 = np.array([0.0, 1.0])
    fig, ax = plotpress.subplots()
    counts, edges, bars = ax.hist([d1, d2], bins=2, range=(0, 2), stacked=True)
    assert len(bars) == 2
    # second dataset's base sits on top of the first's own counts
    assert np.allclose(bars[1].base, bars[0].length)


def test_hist_backward_compatible_single_dataset_default():
    """A bare hist(x) call must still return (counts, edges, bars) with
    bars a single Bars, not a list -- exactly as before these gaps closed."""
    from plotpress.artists import Bars

    x = np.random.RandomState(0).normal(size=100)
    fig, ax = plotpress.subplots()
    counts, edges, bars = ax.hist(x, bins=10)
    assert isinstance(bars, Bars)
    assert isinstance(counts, np.ndarray)


def test_boxplot_whis_widens_the_whiskers():
    data = np.array([0.0, 1, 1, 1, 2, 100.0])
    fig, ax = plotpress.subplots()
    tight = ax.boxplot([data], whis=1.5)
    fig2, ax2 = plotpress.subplots()
    wide = ax2.boxplot([data], whis=200.0)
    assert tight.stats[0]["hi"] < wide.stats[0]["hi"]
    assert len(tight.stats[0]["fliers"]) > len(wide.stats[0]["fliers"])


def test_boxplot_showfliers_false_drops_them():
    data = np.array([0.0, 1, 1, 1, 2, 100.0])
    fig, ax = plotpress.subplots()
    b = ax.boxplot([data], showfliers=False)
    assert len(b.stats[0]["fliers"]) == 0
    assert "<circle" not in fig.to_svg()


def test_errorbar_ecolor_elinewidth_capthick_are_independent():
    fig, ax = plotpress.subplots()
    eb = ax.errorbar([0, 1], [1, 1], yerr=[0.2, 0.2], color="blue",
                     ecolor="red", elinewidth=3.0, capthick=1.0)
    assert eb.color == "blue" and eb.ecolor == "red"
    assert eb.elinewidth == 3.0 and eb.capthick == 1.0
    svg = fig.to_svg()
    assert 'stroke="red"' in svg


def test_errorbar_ecolor_defaults_match_color_and_linewidth():
    """Backward compatibility: with nothing given, ecolor/elinewidth/
    capthick fall back to color/linewidth exactly, changing nothing for
    every pre-existing errorbar() call."""
    fig, ax = plotpress.subplots()
    eb = ax.errorbar([0, 1], [1, 1], yerr=[0.2, 0.2], color="blue", linewidth=2.0)
    assert eb.ecolor == eb.color == "blue"
    assert eb.elinewidth == eb.capthick == eb.linewidth == 2.0


def test_imshow_interpolation_nearest_vs_smooth():
    X = np.random.RandomState(0).rand(4, 4)
    fig1, ax1 = plotpress.subplots()
    ax1.imshow(X)
    fig2, ax2 = plotpress.subplots()
    ax2.imshow(X, interpolation="bilinear")
    assert "pixelated" in fig1.to_svg()
    assert "pixelated" not in fig2.to_svg()

    fig3, ax3 = plotpress.subplots()
    ax3.pcolormesh(X)
    assert "pixelated" in fig3.to_svg()   # unaffected -- imshow-only so far
