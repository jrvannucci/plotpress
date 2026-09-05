"""Style: the per-figure rcParams replacement.

Field validation (Style.__setattr__'s >0 / >=0 checks) already lives in
tests/test_input_validation.py, alongside the other eager-validation tests
it mirrors -- not duplicated here. This file covers what that one doesn't:
defaults, copy()'s independence-from-the-source semantics (the actual
"replaces global rcParams" contract), and text_width()'s delegation.
"""
import pytest

from plotpress.style import DEFAULT_COLOR_CYCLE, Style


def test_defaults_match_the_documented_values():
    st = Style()
    assert st.facecolor == "#ffffff"
    assert st.dpi == 100.0
    assert st.font_family == "Helvetica, Arial, sans-serif"
    assert st.line_width == 1.5
    assert st.color_cycle == DEFAULT_COLOR_CYCLE


def test_two_default_styles_are_equal_but_independent():
    a, b = Style(), Style()
    assert a == b
    b.line_width = 3.0
    assert a != b
    assert a.line_width == 1.5


def test_color_cycle_is_a_distinct_list_per_instance():
    """DEFAULT_COLOR_CYCLE is a module-level list -- if Style's own
    default_factory ever handed out the same list object instead of a copy,
    mutating one figure's cycle would mutate every figure's."""
    a, b = Style(), Style()
    assert a.color_cycle is not b.color_cycle
    assert a.color_cycle is not DEFAULT_COLOR_CYCLE
    a.color_cycle.append("#000000")
    assert "#000000" not in b.color_cycle
    assert "#000000" not in DEFAULT_COLOR_CYCLE


def test_copy_applies_overrides_without_mutating_the_source():
    base = Style()
    variant = base.copy(line_width=4.0, dpi=150.0)
    assert variant.line_width == 4.0
    assert variant.dpi == 150.0
    assert base.line_width == 1.5
    assert base.dpi == 100.0


def test_copy_gives_the_variant_its_own_color_cycle_list():
    """copy()'s own docstring: "Mutable fields are duplicated so two figures
    never share a list" -- even when color_cycle isn't one of the overrides
    passed in."""
    base = Style()
    variant = base.copy(line_width=4.0)
    assert variant.color_cycle is not base.color_cycle
    variant.color_cycle.append("#123456")
    assert "#123456" not in base.color_cycle


def test_copy_explicit_color_cycle_override_is_used_verbatim():
    base = Style()
    custom = ["#111111", "#222222"]
    variant = base.copy(color_cycle=custom)
    assert variant.color_cycle == custom


def test_copy_rejects_the_same_invalid_values_as_direct_assignment():
    base = Style()
    with pytest.raises(ValueError, match="dpi"):
        base.copy(dpi=0)


def test_text_width_delegates_to_the_fonts_module():
    from plotpress.fonts import text_width as fonts_text_width

    st = Style(font_family="Helvetica, Arial, sans-serif")
    expected = fonts_text_width("Hello", 12.0, st.font_family, False, False,
                                measure_installed=False)
    assert st.text_width("Hello", 12.0) == expected


def test_text_width_bold_and_italic_flags_are_forwarded():
    st = Style()
    regular = st.text_width("Hello", 12.0)
    bold = st.text_width("Hello", 12.0, bold=True)
    # Bold Helvetica runs wider than regular on real label strings (see
    # font_files()'s own docstring) -- if the bold flag weren't forwarded,
    # these would be identical.
    assert bold != regular
