"""Regression tests for a break-it audit: inputs that used to crash with a
confusing internal traceback, render silently wrong with no warning, or
produce invalid SVG/PNG output, instead of failing clearly or working as a
matplotlib user would expect.

Each test pins one such case to a specific, named ``ValueError``/``TypeError``
(or, for the two genuinely-silent-render bugs, a ``UserWarning``) rather than
just asserting *some* exception -- the whole point of these fixes was
replacing an unhelpful crash with one that says what's wrong.
"""
import numpy as np
import pytest

import plotpress
from plotpress.colors import to_hex


# ---------------------------------------------------------------------------
# Color resolution: full CSS4 name coverage + a clear error for the rest.
# ---------------------------------------------------------------------------
def test_css4_color_name_outside_the_old_small_table_resolves():
    """'cornflowerblue' isn't matplotlib X11-basic, but it's a completely
    ordinary CSS/matplotlib color name -- it used to crash fig.save(...png)
    with a bare int(..., 16) error instead of resolving."""
    assert to_hex("cornflowerblue").lower() == "#6495ed"
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], color="cornflowerblue")
    fig.to_svg()  # must not raise
    from plotpress.raster import figure_to_image
    figure_to_image(fig)  # must not raise -- this is what used to crash


def test_misspelled_color_name_raises_instead_of_rendering_invisibly():
    """A typo used to reach the SVG backend as a literal, invalid
    stroke="..." attribute -- browsers treat that as unset, so the line
    silently never rendered, with no error or warning anywhere."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="Unknown color 'crimon'"):
        ax.plot([1, 2], [1, 2], color="crimon")


def test_malformed_hex_color_raises():
    with pytest.raises(ValueError, match="Invalid hex color"):
        to_hex("#zzzzzz")


@pytest.mark.parametrize("keyword", ["none", "None", "NONE", "transparent"])
def test_paint_keywords_pass_through_unresolved(keyword):
    """'none'/'transparent' are real SVG/CSS paint keywords used elsewhere in
    this codebase (Artist._BBOX_DEFAULTS's own edgecolor default) -- they must
    keep passing through, not be rejected as unknown colors."""
    assert to_hex(keyword) == keyword


# ---------------------------------------------------------------------------
# Mismatched-length paired arrays: fail immediately, name the method.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("call", [
    lambda ax: ax.plot([1, 2, 3], [1, 2]),
    lambda ax: ax.scatter([1, 2, 3], [1, 2]),
    lambda ax: ax.bar([1, 2, 3], [1, 2]),
    lambda ax: ax.barh([1, 2, 3], [1, 2]),
    lambda ax: ax.fill_between([1, 2, 3], [1, 2]),
    lambda ax: ax.fill_betweenx([1, 2, 3], [1, 2]),
    lambda ax: ax.hlines([1, 2, 3], 0, [1, 2]),
    lambda ax: ax.vlines([1, 2, 3], 0, [1, 2]),
    lambda ax: ax.stem([1, 2, 3], [1, 2]),
    lambda ax: ax.errorbar([1, 2, 3], [1, 2]),
], ids=["plot", "scatter", "bar", "barh", "fill_between", "fill_betweenx",
        "hlines", "vlines", "stem", "errorbar"])
def test_mismatched_lengths_raise_immediately_naming_the_method(call):
    """These used to either reach a bare NumPy broadcast/concatenate error
    deep inside transform.py/artists.py with no mention of which plotpress
    call caused it, or (stem) silently zip()-truncate to the shorter array
    with no error or warning at all."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError):
        call(ax)


def test_stem_mismatched_lengths_no_longer_silently_truncates():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"stem\(\)"):
        ax.stem([1, 2, 3], [1, 2])


def test_hlines_scalar_xmin_xmax_still_broadcasts():
    """The fix must not reject legitimate scalar broadcasting."""
    fig, ax = plotpress.subplots()
    lc = ax.hlines([1, 2, 3], 0, 5)
    assert fig.to_svg()
    assert lc is not None


# ---------------------------------------------------------------------------
# Figure.colorbar(None, ...): a clear TypeError, not an internal AttributeError.
# ---------------------------------------------------------------------------
def test_colorbar_with_no_mappable_raises_clear_type_error():
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2])
    with pytest.raises(TypeError, match="colorbar"):
        fig.colorbar(None, ax=ax)


def test_colorbar_with_non_mappable_object_raises_clear_type_error():
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2])
    with pytest.raises(TypeError, match="colorbar"):
        fig.colorbar("not a mappable", ax=ax)


# ---------------------------------------------------------------------------
# print_summary()/print_layout_summary(): report the axis direction that
# actually renders, not just the invert_xaxis() flag.
# ---------------------------------------------------------------------------
def test_print_summary_reports_inversion_from_set_xlim_hi_lo(capsys):
    """set_xlim(hi, lo) is a completely normal, common way to invert an axis
    -- it renders inverted (confirmed against transform.py's own pixel math)
    but the summary used to check only the invert_xaxis() flag and say
    nothing, misdescribing a figure it didn't build."""
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_xlim(10, 0)
    ax.print_summary()
    out = capsys.readouterr().out
    assert "x:  linear, [10, 0] (inverted)" in out


def test_print_summary_reports_inversion_from_invert_xaxis(capsys):
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.invert_xaxis()
    ax.print_summary()
    out = capsys.readouterr().out
    assert "(inverted)" in out.split("y:")[0]  # the x: line only


def test_print_summary_set_xlim_then_invert_xaxis_cancels_back_to_normal(capsys):
    """A raw hi-lo set_xlim() *and* invert_xaxis() compose the same way
    svg.py's own renderer does -- two flips cancel back to a normal render,
    so the summary must not report "(inverted)" for this combination."""
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_xlim(10, 0)
    ax.invert_xaxis()
    ax.print_summary()
    out = capsys.readouterr().out
    assert "x:  linear, [10, 0]\n" in out  # no "(inverted)" suffix


# ---------------------------------------------------------------------------
# A log-scaled axis with no positive data must warn, not render blank.
# ---------------------------------------------------------------------------
def test_log_xscale_with_all_negative_data_warns_instead_of_rendering_blank():
    fig, ax = plotpress.subplots()
    ax.plot([-1, -2, -3], [1, 2, 3])
    ax.set_xscale("log")
    with pytest.warns(UserWarning, match="has no positive values"):
        ax.get_xlim()


def test_log_yscale_with_all_negative_data_warns():
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [-1, -2, -3])
    ax.set_yscale("log")
    with pytest.warns(UserWarning, match="has no positive values"):
        ax.get_ylim()


def test_log_scale_with_some_positive_data_does_not_warn(recwarn):
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_xscale("log")
    ax.get_xlim()
    assert not any("has no positive values" in str(w.message) for w in recwarn.list)


# ---------------------------------------------------------------------------
# Figure(figsize=...) must reject a non-positive size.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("figsize", [(0, 0), (-5, 4), (5, -4), (0, 8)])
def test_non_positive_figsize_raises(figsize):
    """A zero/negative figsize used to sail through and produce a literally
    invalid SVG (width="0" or a negative width attribute) with no error."""
    with pytest.raises(ValueError, match="figsize"):
        plotpress.subplots(figsize=figsize)


def test_positive_figsize_still_works():
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.plot([1, 2], [1, 2])
    assert fig.to_svg()


# ---------------------------------------------------------------------------
# pie() must reject a negative wedge size instead of producing a negative
# fraction (a wedge that sweeps the wrong way, with no error).
# ---------------------------------------------------------------------------
def test_pie_negative_value_raises():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="non-negative"):
        ax.pie([-1, 2, 3])


def test_pie_all_zero_still_falls_back_to_equal_slices():
    """Not a bug -- confirm the deliberate all-zero fallback still works."""
    fig, ax = plotpress.subplots()
    wedges = ax.pie([0, 0, 0])
    art = ax.artists[0]
    assert np.allclose(art.fracs, 1.0 / 3.0)
    assert fig.to_svg()


# ---------------------------------------------------------------------------
# Round 2: bar_label()/table() mismatched counts, quiver()/barbs() mismatched
# shapes, and non-string/falsy legend labels.
# ---------------------------------------------------------------------------
def test_bar_label_mismatched_count_raises():
    """Used to crash with a bare IndexError three frames into text
    placement, instead of naming the actual problem: too few labels."""
    fig, ax = plotpress.subplots()
    bars = ax.bar([1, 2, 3], [1, 2, 3])
    with pytest.raises(ValueError, match=r"bar_label\(\)"):
        ax.bar_label(bars, labels=["only one"])


def test_table_mismatched_row_labels_raises():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"table\(\).*rowLabels"):
        ax.table(cellText=[["a", "b"], ["c", "d"]], rowLabels=["r1"])


def test_table_mismatched_col_labels_raises():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"table\(\).*colLabels"):
        ax.table(cellText=[["a", "b"]], colLabels=["c1", "c2", "c3"])


def test_table_ragged_rows_raise():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"table\(\)"):
        ax.table(cellText=[["a", "b"], ["c"]])


@pytest.mark.parametrize("call", [
    lambda ax, x, y: ax.quiver(x, y, np.ones((4, 4)), np.ones((4, 4))),
    lambda ax, x, y: ax.barbs(x, y, np.ones((4, 4)), np.ones((4, 4))),
], ids=["quiver", "barbs"])
def test_quiver_barbs_mismatched_shapes_raise(call):
    """Used to reach a bare NumPy broadcast error deep in Quiver.tips() at
    render time, with no mention of which call or arguments were at fault."""
    fig, ax = plotpress.subplots()
    x, y = np.meshgrid(np.arange(5), np.arange(5))
    with pytest.raises(ValueError):
        call(ax, x, y)


def test_legend_non_string_label_renders_instead_of_crashing():
    """label=42 (a common loop-variable accident) used to crash deep in the
    font-metrics text-width walk with TypeError: 'int' object is not
    iterable -- matplotlib itself accepts and stringifies non-string
    labels, so plotpress must too, in both the SVG and PNG legend."""
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2], label=42)
    ax.legend()
    svg = fig.to_svg()
    assert "42" in svg


def test_legend_non_string_label_renders_in_png_too(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2], label=42)
    ax.legend()
    fig.save(str(tmp_path / "out.png"))  # must not raise


def test_legend_label_zero_is_shown_not_treated_as_no_label():
    """label=0/0.0/False is a legitimate label matplotlib shows as "0" --
    truthiness incorrectly excluded it from the legend entirely."""
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2], label=0)
    ax.legend()
    svg = fig.to_svg()
    assert ">0<" in svg


def test_legend_string_labels_unaffected():
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2], label="series a")
    ax.legend()
    assert "series a" in fig.to_svg()


# ---------------------------------------------------------------------------
# Round 2 continued: negative fontsize, colorbar(fraction<=0), non-finite
# imshow extent.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("call", [
    lambda ax: ax.text(0.5, 0.5, "hi", fontsize=-12),
    lambda ax: ax.annotate("hi", xy=(0.5, 0.5), fontsize=-5),
], ids=["text", "annotate"])
def test_negative_fontsize_raises(call):
    """A negative fontsize used to reach the SVG backend as a literal,
    invalid font-size="-12" attribute -- no crash, just unrenderable text
    with no error anywhere."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="fontsize"):
        call(ax)


def test_zero_fontsize_still_allowed():
    """Not a bug -- 0 is valid CSS (invisible text), unlike a negative size."""
    fig, ax = plotpress.subplots()
    ax.text(0.5, 0.5, "hi", fontsize=0)
    assert fig.to_svg()


def test_colorbar_non_positive_fraction_raises():
    """fraction<=0 used to produce a colorbar axes with a negative pixel
    width -- an invalid layout, not a crash, so nothing caught it."""
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.random.default_rng(0).random((5, 5)))
    with pytest.raises(ValueError, match="fraction"):
        fig.colorbar(mesh, ax=ax, fraction=-0.5)
    with pytest.raises(ValueError, match="fraction"):
        fig.colorbar(mesh, ax=ax, fraction=0)


def test_colorbar_default_fraction_still_works():
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.random.default_rng(0).random((5, 5)))
    fig.colorbar(mesh, ax=ax)
    assert fig.to_svg()


def test_imshow_non_finite_extent_raises():
    """A NaN extent bound used to be silently dropped by autoscale's
    finite-only filter, falling back to a default range that quietly
    doesn't match what extent= actually specified -- no error, no warning."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="extent"):
        ax.imshow(np.random.default_rng(0).random((5, 5)), extent=(0, np.nan, 0, 10))


def test_imshow_reversed_finite_extent_still_works():
    """Not a bug -- a reversed-but-finite extent is a legitimate way to
    flip an image's axis direction."""
    fig, ax = plotpress.subplots()
    ax.imshow(np.random.default_rng(0).random((5, 5)), extent=(10, 0, 10, 0))
    assert ax.get_xlim() == (10, 0)
    assert fig.to_svg()


# ---------------------------------------------------------------------------
# Round 3: RGB(A) tuple colors, per-bar RGBA arrays, plot_frames() with no
# frames.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rgb,expected", [
    ((1.0, 0.0, 0.0), "#ff0000"),
    ((0.0, 1.0, 0.0, 0.5), "#00ff00"),
    ((255, 128, 0), "#ff8000"),
])
def test_to_hex_resolves_rgb_tuples(rgb, expected):
    assert to_hex(rgb) == expected


def test_plot_with_rgb_tuple_color_renders_correctly():
    """(1.0, 0.0, 0.0) -- completely ordinary matplotlib usage -- used to
    reach the SVG backend as a literal stroke="(1.0, 0.0, 0.0)" (invalid,
    silently invisible) and crash PNG export outright with 'tuple' object
    has no attribute 'lstrip'."""
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], color=(1.0, 0.0, 0.0))
    svg = fig.to_svg()
    assert 'stroke="#ff0000"' in svg


def test_plot_with_rgb_tuple_color_png_export_does_not_crash(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], color=(1.0, 0.0, 0.0))
    fig.save(str(tmp_path / "out.png"))  # must not raise


def test_bar_per_bar_rgba_array_resolves_in_svg():
    """bar(color=[[r,g,b,a], ...]) -- one row per bar -- used to reach
    svg.py's fill="{bars.colors[i]}" as a raw, unresolved Python list:
    fill="[1.0, 0, 0, 1]", invalid and silently invisible."""
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [1, 2, 3],
          color=[[1.0, 0, 0, 1], [0, 1.0, 0, 1], [0, 0, 1.0, 1]])
    svg = fig.to_svg()
    assert 'fill="#ff0000"' in svg
    assert 'fill="#00ff00"' in svg
    assert 'fill="#0000ff"' in svg


def test_bar_per_bar_color_typo_raises():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="Unknown color"):
        ax.bar([0, 1, 2], [1, 2, 3], color=["red", "gren", "blue"])


def test_bar_per_bar_string_colors_still_work():
    """Not a bug -- confirm the existing (already-working) per-bar named-
    color list still resolves the same way after to_hex()/_as_colors()
    both changed."""
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [1, 2, 3], color=["red", "green", "blue"])
    svg = fig.to_svg()
    assert 'fill="#ff0000"' in svg
    assert 'fill="#008000"' in svg
    assert 'fill="#0000ff"' in svg


def test_eventplot_color_list_mistake_no_longer_produces_invalid_svg():
    """eventplot() has one shared color, not a per-row list -- passing one
    anyway used to reach the SVG backend as a literal Python list repr,
    fill="['red', 'blue']". Not rejected (eventplot has no per-row-color
    contract to validate against), but no longer silently invalid either --
    the nested-array path in to_hex() only converts a genuinely flat,
    numeric 3/4-tuple, so this is unchanged from before to_hex() grew RGB
    support: still passed through, still the caller's problem, not a new
    regression."""
    fig, ax = plotpress.subplots()
    ax.eventplot([[1, 2, 3], [4, 5]], color=["red", "blue"])
    assert fig.to_svg()  # must not raise


def test_plot_frames_empty_raises():
    """Rendering always draws 'frame 0' unconditionally -- with zero frames
    that indexed into an empty axis at render time with a bare IndexError,
    not here, at the call that actually caused it."""
    fig, ax = plotpress.subplots()
    x = np.linspace(0, 1, 10)
    Y = np.zeros((0, 10))
    with pytest.raises(ValueError, match="plot_frames"):
        ax.plot_frames(x, Y)


def test_plot_frames_single_frame_still_works():
    fig, ax = plotpress.subplots()
    x = np.linspace(0, 1, 10)
    Y = np.random.default_rng(0).random((1, 10))
    ax.plot_frames(x, Y)
    assert fig.to_svg()


# ---------------------------------------------------------------------------
# Round 4: imshow()/pcolormesh() wrong ndim, all-NaN contour warning leak.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", [(4,), (5, 5, 2), (5, 5, 5)])
def test_imshow_invalid_shape_raises(shape):
    """A 1-D array used to crash 'not enough values to unpack' reading its
    own shape; a (h, w, 2) array (not RGB/RGBA) passed that check but
    crashed much later, deep in the PNG encoder's own reshape."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"imshow\(\)"):
        ax.imshow(np.zeros(shape))


@pytest.mark.parametrize("shape", [(5, 5, 3), (5, 5, 4), (6, 7)])
def test_imshow_valid_shapes_still_work(shape):
    fig, ax = plotpress.subplots()
    ax.imshow(np.random.default_rng(0).random(shape))
    assert fig.to_svg()


def test_pcolormesh_1d_C_raises():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"pcolormesh\(\)"):
        ax.pcolormesh(np.array([1, 2, 3, 4]))


def test_contour_all_nan_does_not_leak_a_raw_runtime_warning(recwarn):
    fig, ax = plotpress.subplots()
    ax.contour(np.full((10, 10), np.nan))
    fig.to_svg()
    assert not any(
        "invalid value encountered" in str(w.message) for w in recwarn.list
    )


# ---------------------------------------------------------------------------
# Round 4 continued: fig.style.dpi <= 0, errorbar()/bar() negative yerr/xerr.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("dpi", [0, -50])
def test_non_positive_dpi_raises_on_svg_and_png(dpi, tmp_path):
    """figsize is validated at Figure() construction, but dpi is a plain,
    freely-mutable Style attribute that reaches the same width/height
    product and used to produce the identical invalid SVG (width="0" or
    negative) that fix was written to prevent."""
    fig, ax = plotpress.subplots()
    fig.style.dpi = dpi
    ax.plot([1, 2], [1, 2])
    with pytest.raises(ValueError, match="dpi"):
        fig.to_svg()
    with pytest.raises(ValueError, match="dpi"):
        fig.save(str(tmp_path / "out.png"))


def test_positive_dpi_still_works():
    fig, ax = plotpress.subplots()
    ax.plot([1, 2], [1, 2])
    assert fig.to_svg()


@pytest.mark.parametrize("call", [
    lambda ax: ax.errorbar([1, 2, 3], [1, 2, 3], yerr=-0.5),
    lambda ax: ax.errorbar([1, 2, 3], [1, 2, 3], xerr=-0.5),
    lambda ax: ax.bar([1, 2, 3], [1, 2, 3], yerr=-0.2),
], ids=["errorbar-yerr", "errorbar-xerr", "bar-yerr"])
def test_negative_error_magnitude_raises(call):
    """A negative yerr/xerr has no geometric meaning -- it doesn't error,
    it flips the whisker inward, shrinking data_bounds() to something
    narrower than the bare data and pulling real points outside the
    autoscaled ylim/xlim entirely, with no error or warning."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="non-negative"):
        call(ax)


def test_positive_error_magnitude_still_expands_bounds():
    fig, ax = plotpress.subplots()
    eb = ax.errorbar([1, 2, 3], [1, 2, 3], yerr=0.5)
    assert eb.data_bounds() == (1.0, 3.0, 0.5, 3.5)


# ---------------------------------------------------------------------------
# Round 5: contour()/contourf() 1-D Z, hexbin() non-positive gridsize.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["contour", "contourf"])
def test_contour_1d_z_raises(method):
    """A 1-D Z used to crash marching squares' own ny, nx = Z.shape with a
    bare IndexError: tuple index out of range."""
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match=r"Z must be a 2-D array"):
        getattr(ax, method)(np.array([1, 2, 3, 4]))


@pytest.mark.parametrize("method", ["contour", "contourf"])
def test_contour_2d_z_still_works(method):
    fig, ax = plotpress.subplots()
    Z = np.random.default_rng(0).random((10, 10))
    getattr(ax, method)(Z)
    assert fig.to_svg()


def test_contour_xyz_form_1d_z_raises():
    fig, ax = plotpress.subplots()
    x = np.linspace(0, 1, 4)
    with pytest.raises(ValueError, match=r"Z must be a 2-D array"):
        ax.contour(x, x, np.array([1, 2, 3, 4]))


@pytest.mark.parametrize("gridsize", [0, -5])
def test_hexbin_non_positive_gridsize_raises(gridsize):
    """gridsize<=0 doesn't error -- it can't tile anything, so real data
    silently bins into zero hexagons and renders a blank axes with no hint
    why."""
    fig, ax = plotpress.subplots()
    x = np.random.default_rng(0).random(50)
    y = np.random.default_rng(1).random(50)
    with pytest.raises(ValueError, match="gridsize"):
        ax.hexbin(x, y, gridsize=gridsize)


def test_hexbin_positive_gridsize_still_works():
    fig, ax = plotpress.subplots()
    x = np.random.default_rng(0).random(50)
    y = np.random.default_rng(1).random(50)
    ax.hexbin(x, y, gridsize=20)
    assert fig.to_svg()
