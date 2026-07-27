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
    for name in ("inferno", "magma", "cividis", "coolwarm", "RdBu"):
        assert get_cmap(name).shape == (256, 3)
    v = get_cmap("viridis")
    assert np.array_equal(get_cmap("viridis_r"), v[::-1])
    assert "viridis_r" in plotpress.available_colormaps()


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


def test_hexbin_conserves_point_counts():
    """Every point lands in exactly one hexagon, so with mincnt=1 the counts
    sum to the number of points (guards the vectorized cell tally)."""
    from plotpress.axes import _hexbin
    rng = np.random.RandomState(1)
    x, y = rng.normal(size=2000), rng.normal(size=2000)
    verts, counts = _hexbin(x, y, 15, 1)
    assert counts.sum() == x.size
    assert len(verts) == len(counts)
