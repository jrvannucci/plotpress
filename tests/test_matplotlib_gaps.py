"""Tests for the matplotlib-compatibility features added to close API gaps:
colormaps + norms, reference lines/spans, fill/line helpers, tick labels,
axis inversion, and legend placement.
"""
import numpy as np
import pytest

import simpleplot
from simpleplot.colors import (
    LogNorm, PowerNorm, SymLogNorm, apply_colormap, get_cmap, to_hex,
)


# -- colormaps & norms ------------------------------------------------------
def test_new_colormaps_and_reversed():
    for name in ("inferno", "magma", "cividis", "coolwarm", "RdBu"):
        assert get_cmap(name).shape == (256, 3)
    v = get_cmap("viridis")
    assert np.array_equal(get_cmap("viridis_r"), v[::-1])
    assert "viridis_r" in simpleplot.available_colormaps()


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
    from simpleplot.raster import figure_to_image

    fig, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 1])
    ax.axhline(0.5, color="k")
    ax.axvspan(2, 3, color="orange", alpha=0.2)
    ax.axhspan(0.2, 0.4, color="green", alpha=0.2)
    svg = fig.to_svg()
    assert svg.count('fill-opacity="0.2"') == 2      # two spans
    figure_to_image(fig, scale=1)                    # raster must not raise


def test_spans_and_reflines_do_not_autoscale():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    ax.axhline(999); ax.axvspan(-50, -40)
    (x0, x1), (y0, y1) = ax._resolved_limits()
    assert y1 < 10 and x0 > -10                       # ref artists ignored


# -- fill / hlines / vlines -------------------------------------------------
def test_fill_and_line_helpers():
    fig, ax = simpleplot.subplots()
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
    fig, ax = simpleplot.subplots()
    ax.bar([0, 1, 2], [1, 2, 3])
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["a", "b", "c"])
    svg = fig.to_svg()
    assert all(f">{t}<" in svg for t in ("a", "b", "c"))


def test_invert_yaxis_flips_transform():
    from simpleplot.svg import _effective_rect, _pixel_rect
    from simpleplot.transform import LinearTransform

    fig, ax = simpleplot.subplots()
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
    fig, ax = simpleplot.subplots()
    for i in range(4):
        ax.plot([0, 1], [i, i], label=f"s{i}")
    ax.legend(loc="lower left", ncol=2, title="Series")
    svg = fig.to_svg()
    assert ">Series<" in svg
    assert all(f">s{i}<" in svg for i in range(4))


def test_legend_default_still_works():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1], label="line")
    ax.legend()
    assert "simpleplot-legend" in fig.to_svg()


# -- shared colorbar --------------------------------------------------------
def test_shared_colorbar_over_axes_list():
    fig, axes = simpleplot.subplots(2, 2)
    m = None
    for ax in axes.ravel():
        m = ax.pcolormesh(np.ones((4, 4)), vmin=0, vmax=1)
    cax = fig.colorbar(m, ax=axes)
    assert sum(1 for a in fig.axes if a._is_colorbar) == 1
    # the squeezed grid ends to the left of the colorbar
    right = max(a._rect[0] + a._rect[2] for a in axes.ravel())
    assert right <= cax._rect[0] + 1e-9


def test_single_axes_colorbar_still_works():
    fig, ax = simpleplot.subplots()
    m = ax.pcolormesh(np.arange(9.0).reshape(3, 3))
    fig.colorbar(m, ax=ax)
    assert fig.to_svg().count("<image") == 2


# -- contourf / hexbin ------------------------------------------------------
def test_contourf_is_banded_image_and_mappable():
    g = np.linspace(-2, 2, 20)
    X, Y = np.meshgrid(g, g)
    fig, ax = simpleplot.subplots()
    cf = ax.contourf(g, g, np.exp(-(X ** 2 + Y ** 2)), levels=6, cmap="plasma")
    fig.colorbar(cf, ax=ax)                 # returns a valid mappable
    assert fig.to_svg().count("<image") == 2


def test_hexbin_makes_hexagons_and_is_mappable():
    rng = np.random.default_rng(0)
    x = rng.normal(size=2000)
    y = rng.normal(size=2000)
    fig, ax = simpleplot.subplots()
    hb = ax.hexbin(x, y, gridsize=15)
    assert len(hb.verts) > 10
    assert all(v.shape == (6, 2) for v in hb.verts)   # hexagons
    assert hb.lut is not None and hb.norm is not None  # colorbar-ready
    assert fig.to_svg().count("<polygon") == len(hb.verts)


# -- sharex / sharey --------------------------------------------------------
def test_sharey_links_limits_and_hides_inner_labels():
    fig, axes = simpleplot.subplots(1, 2, sharey=True)
    axes[0].plot([0, 1], [0, 2])
    axes[1].plot([0, 1], [0, 100])
    assert axes[0].get_ylim() == axes[1].get_ylim()   # shared span
    assert axes[0]._yticklabels is None               # left column shows labels
    assert axes[1]._yticklabels == []                 # right column hidden


def test_unshared_axes_stay_independent():
    fig, axes = simpleplot.subplots(1, 2)
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
    fig, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 1])
    ax2 = ax.twinx()
    ax2.plot([0, 10], [0, 1000])
    assert ax2._twin_of is ax and ax2._twin_shared == "x"
    assert ax._resolved_limits()[0] == ax2._resolved_limits()[0]    # shared x
    assert ax._resolved_limits()[1] != ax2._resolved_limits()[1]    # own y
    ax2.set_ylabel("right")
    assert ">right<" in fig.to_svg()


def test_twiny_shares_y():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 10])
    ax2 = ax.twiny()
    ax2.plot([0, 500], [0, 10])
    assert ax._resolved_limits()[1] == ax2._resolved_limits()[1]    # shared y
    assert ax._resolved_limits()[0] != ax2._resolved_limits()[0]    # own x


# -- margins / bounds -------------------------------------------------------
def test_margins_and_bounds():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 10], [0, 5])
    ax.margins(0.1)
    x0, x1 = ax.get_xlim()
    assert x0 < 0 and x1 > 10                       # padded outward
    ax.set_xbound(0, 100)
    assert ax.get_xlim() == (0, 100)


# -- CN colors / matshow / spy / tick_params --------------------------------
def test_cn_color_notation():
    fig, ax = simpleplot.subplots()
    cyc = ax.style.color_cycle
    assert ax.plot([0, 1], [0, 1], color="C0").color == cyc[0]
    assert ax.plot([0, 1], [1, 2], color="C3").color == cyc[3]
    assert ax.plot([0, 1], [2, 3], color="r").color == "r"   # named still passes


def test_matshow_and_spy():
    fig, ax = simpleplot.subplots()
    ax.matshow(np.arange(9.0).reshape(3, 3))
    assert ax._aspect == 1.0 and "<image" in fig.to_svg()

    A = np.eye(5)
    fig2, ax2 = simpleplot.subplots()
    ax2.spy(A)
    assert "<image" in fig2.to_svg() and ax2._aspect == 1.0


def test_tick_params_styles_ticks():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_params(labelsize=14, color="red", labelcolor="blue")
    svg = fig.to_svg()
    assert 'font-size="14"' in svg
    assert 'stroke="red"' in svg and 'fill="blue"' in svg
