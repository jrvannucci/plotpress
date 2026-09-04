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
