"""Datetime axis support, general categorical/string axis support, and
declarative tick locator/formatter specs.

Three complementary features, all funneling through one coercion entry point
(``Axes._as_axis_data``): a datetime-like x/y converts to real floating-point
days since epoch (proportional to elapsed time, matching matplotlib's own
``date2num``); a plain string x/y maps to an integer category position in
first-seen order, shared across plotting calls on the same axis; and
``set_x/ylocator``/``set_x/yformat`` take a small JSON-serializable spec
(not a matplotlib-style Locator/Formatter object) so the same rule replays in
the interactive HTML's client-side zoom/pan rebuild -- see
``plotpress/_interactive.py``'s ``resolveAxisTicks``, which this file's
``test_interactive_...`` cases check via the serialized metadata it consumes.
"""
import datetime as dt

import numpy as np
import pytest

import plotpress
from plotpress.dates import (
    date_ticks, days_to_datetime64, format_date_ticks, is_datetime_like, to_days,
)
from plotpress.ticker import (
    apply_locator, apply_tick_format, multiple_ticks, resolve_axis_tick_labels,
    resolve_axis_ticks, resolve_tick_format, resolve_tick_locations,
)

from conftest import SVG_NS as NS, parse_svg as _parse


# ---------------------------------------------------------------------------
# plotpress.dates
# ---------------------------------------------------------------------------

def test_is_datetime_like():
    assert is_datetime_like(np.datetime64("2024-01-01"))
    assert is_datetime_like(dt.date(2024, 1, 1))
    assert is_datetime_like(dt.datetime(2024, 1, 1, 12, 0))
    assert is_datetime_like(np.array(["2024-01-01", "2024-01-02"], dtype="datetime64[D]"))
    assert is_datetime_like([dt.date(2024, 1, 1), dt.date(2024, 1, 2)])
    assert not is_datetime_like([1, 2, 3])
    assert not is_datetime_like(["a", "b"])
    assert not is_datetime_like(np.array([]))


def test_to_days_and_back_round_trips():
    assert to_days(np.datetime64("1970-01-01")) == 0.0  # exactly the epoch
    days = to_days(np.array(["2024-01-01", "2024-06-15"], dtype="datetime64[D]"))
    back = days_to_datetime64(days).astype("datetime64[D]")
    assert list(back.astype(str)) == ["2024-01-01", "2024-06-15"]


def test_to_days_accepts_python_dates_and_scalars():
    assert to_days(dt.date(1970, 1, 2)) == pytest.approx(1.0)
    assert to_days("2024-01-01") == pytest.approx(to_days(np.datetime64("2024-01-01")))


def test_date_ticks_picks_a_calendar_tier():
    # A one-year span should tier to months, landing on the first of each.
    lo, hi = to_days("2024-01-01"), to_days("2024-12-25")
    ticks = date_ticks(float(lo), float(hi))
    labels = format_date_ticks(ticks)
    assert all(len(l) == 7 and l[4] == "-" for l in labels)  # "YYYY-MM"
    # Every tick lands on the 1st of its month.
    for t in ticks:
        assert str(days_to_datetime64(t).astype("datetime64[D]")).endswith("-01")


def test_date_ticks_handles_degenerate_ranges():
    same = date_ticks(5.0, 5.0)
    assert same.size >= 2 and np.all(np.diff(same) > 0)  # non-empty, strictly increasing
    non_finite = date_ticks(float("nan"), 5.0)
    assert np.isnan(non_finite[0]) and non_finite[1] == 5.0
    reversed_ticks = date_ticks(10.0, 0.0)
    assert list(reversed_ticks) == list(date_ticks(0.0, 10.0))


def test_format_date_ticks_empty():
    assert format_date_ticks([]) == []


# ---------------------------------------------------------------------------
# plotpress.ticker: locator/formatter specs
# ---------------------------------------------------------------------------

def test_multiple_ticks():
    ticks = multiple_ticks(0, 3 * np.pi, np.pi / 2)
    assert ticks.size == 7
    assert ticks[0] == pytest.approx(0.0)
    assert ticks[-1] == pytest.approx(3 * np.pi)


def test_multiple_ticks_rejects_nonpositive_base():
    with pytest.raises(ValueError):
        multiple_ticks(0, 10, 0.0)
    with pytest.raises(ValueError):
        multiple_ticks(0, 10, -1.0)


def test_apply_locator_multiple_and_unknown():
    ticks = apply_locator({"kind": "multiple", "base": 2.0}, 0, 10)
    assert list(ticks) == [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    with pytest.raises(ValueError):
        apply_locator({"kind": "bogus"}, 0, 10)


def test_resolve_tick_locations_priority():
    # Explicit locator wins over date/log/default.
    loc = resolve_tick_locations(0, 10, locator={"kind": "multiple", "base": 5.0})
    assert list(loc) == [0.0, 5.0, 10.0]
    # No locator, is_date=True -> date ticks.
    lo, hi = to_days("2024-01-01"), to_days("2024-12-25")
    dloc = resolve_tick_locations(float(lo), float(hi), is_date=True)
    assert list(dloc) == list(date_ticks(float(lo), float(hi)))


@pytest.mark.parametrize("spec,expected", [
    ("percent", ["0%", "50%", "100%"]),
    ({"kind": "percent", "decimals": 1}, ["0.0%", "50.0%", "100.0%"]),
    ("comma", ["1,000", "2,000"]),
    ("%.2f", None),  # checked separately below
])
def test_apply_tick_format_named_specs(spec, expected):
    if spec in ("percent", {"kind": "percent", "decimals": 1}):
        out = apply_tick_format(spec, [0.0, 0.5, 1.0])
    elif spec == "comma":
        out = apply_tick_format(spec, [1000, 2000])
    else:
        out = apply_tick_format(spec, [3.14159])
        assert out == ["3.14"]
        return
    assert out == expected


def test_apply_tick_format_engineering_and_pi():
    assert apply_tick_format("eng", [1500.0]) == ["1.5k"]
    assert apply_tick_format({"kind": "eng", "decimals": 0}, [2_500_000.0]) == ["2M"]
    pi_labels = apply_tick_format("pi", [0.0, np.pi / 2, np.pi, 3 * np.pi / 2])
    assert pi_labels == ["0", "π/2", "π", "3π/2"]


def test_apply_tick_format_callable_and_raw_percent_string():
    assert apply_tick_format(lambda v: f"<{v}>", [1, 2]) == ["<1>", "<2>"]
    assert apply_tick_format("$%.0f", [42.0]) == ["$42"]


def test_apply_tick_format_rejects_unknown_spec():
    with pytest.raises(ValueError):
        apply_tick_format("not-a-real-format", [1.0])
    with pytest.raises(ValueError):
        apply_tick_format({"kind": "nonsense"}, [1.0])


def test_resolve_tick_format_priority():
    assert resolve_tick_format([0.5], fmt="percent") == ["50%"]
    lo, hi = to_days("2024-01-01"), to_days("2024-12-25")
    ticks = date_ticks(float(lo), float(hi))
    assert resolve_tick_format(ticks, is_date=True) == format_date_ticks(ticks)


def test_resolve_axis_ticks_and_labels_categorical():
    ticks = resolve_axis_ticks(0, 2, categorical=True, categories=["A", "B", "C"])
    assert list(ticks) == [0.0, 1.0, 2.0]
    labels = resolve_axis_tick_labels(ticks, categorical=True, categories=["A", "B", "C"])
    assert labels == ["A", "B", "C"]


def test_resolve_axis_ticks_explicit_wins_over_everything():
    ticks = resolve_axis_ticks(0, 10, explicit=[1.0, 2.0], categorical=True,
                               categories=["x", "y"], locator={"kind": "multiple", "base": 1})
    assert list(ticks) == [1.0, 2.0]
    labels = resolve_axis_tick_labels(ticks, explicit=["one", "two"], categorical=True,
                                      categories=["x", "y"])
    assert labels == ["one", "two"]


# ---------------------------------------------------------------------------
# Axes._as_axis_data / plotting methods
# ---------------------------------------------------------------------------

def test_plot_with_datetime_x_is_time_proportional_not_evenly_spaced():
    fig, ax = plotpress.subplots()
    # Irregular gaps: 1 day, then 100 days.
    dates = np.array(["2024-01-01", "2024-01-02", "2024-04-11"], dtype="datetime64[D]")
    ax.plot(dates, [0, 1, 2])
    assert ax._xdate is True
    xs = ax.artists[0].x
    gap1, gap2 = xs[1] - xs[0], xs[2] - xs[1]
    assert gap2 == pytest.approx(gap1 * 100, rel=0.05)


def test_plot_with_string_x_is_categorical_and_shared_across_calls():
    fig, ax = plotpress.subplots()
    ax.plot(["low", "mid", "high"], [1, 2, 3])
    assert ax._xcategorical is True
    assert ax._xcategories == ["low", "mid", "high"]
    assert list(ax.artists[0].x) == [0.0, 1.0, 2.0]
    # A second series naming an overlapping+new set of categories shares
    # positions for the ones already seen and appends the new one.
    ax.plot(["mid", "high", "extreme"], [4, 5, 6])
    assert ax._xcategories == ["low", "mid", "high", "extreme"]
    assert list(ax.artists[1].x) == [1.0, 2.0, 3.0]


def test_bar_and_barh_accept_categorical_axis():
    fig, ax = plotpress.subplots()
    bars = ax.bar(["Q1", "Q2", "Q3"], [10, 20, 15])
    assert ax._xcategorical
    assert list(bars.pos) == [0.0, 1.0, 2.0]

    fig2, ax2 = plotpress.subplots()
    hbars = ax2.barh(["Q1", "Q2"], [5, 7])
    assert ax2._ycategorical
    assert list(hbars.pos) == [0.0, 1.0]


def test_scatter_step_fill_between_accept_datetime():
    dates = np.array(["2024-01-01", "2024-02-01", "2024-03-01"], dtype="datetime64[D]")
    fig, ax = plotpress.subplots()
    ax.scatter(dates, [1, 2, 3])
    assert ax._xdate

    fig2, ax2 = plotpress.subplots()
    ax2.step(dates, [1, 2, 3])
    assert ax2._xdate

    fig3, ax3 = plotpress.subplots()
    ax3.fill_between(dates, [0, 1, 0], [2, 3, 2])
    assert ax3._xdate

    fig4, ax4 = plotpress.subplots()
    ax4.fill_betweenx(dates, [0, 1, 0], [2, 3, 2])
    assert ax4._ydate


def test_hlines_vlines_axhline_axvline_accept_datetime_and_categorical():
    dates = np.array(["2024-01-01", "2024-06-01"], dtype="datetime64[D]")
    fig, ax = plotpress.subplots()
    ax.hlines([1, 2], dates[0], dates[1])
    assert ax._xdate

    fig2, ax2 = plotpress.subplots()
    ax2.vlines(dates, 0, 1)
    assert ax2._xdate

    fig3, ax3 = plotpress.subplots()
    ax3.axvline("2024-03-01".__str__())  # plain string, not yet date-flavored
    # A bare string on a not-yet-categorical, not-yet-date axis becomes a
    # category of one -- matches plot()'s own general string handling.
    assert ax3._xcategorical

    fig4, ax4 = plotpress.subplots()
    ax4.plot(dates, [1, 2])
    ax4.axvline(np.datetime64("2024-03-01"))
    assert ax4._xdate


def test_errorbar_and_stem_accept_datetime():
    dates = np.array(["2024-01-01", "2024-02-01"], dtype="datetime64[D]")
    fig, ax = plotpress.subplots()
    ax.errorbar(dates, [1, 2], yerr=[0.1, 0.2])
    assert ax._xdate

    fig2, ax2 = plotpress.subplots()
    ax2.stem(dates, [1, 2])
    assert ax2._xdate


def test_broken_barh_accepts_datetime_starts_with_numeric_widths():
    starts = [dt.date(2024, 1, 1), dt.date(2024, 1, 10)]
    fig, ax = plotpress.subplots()
    pc = ax.broken_barh(list(zip(starts, [5, 3])), (0, 1))
    assert ax._xdate
    # First rect's left/right edges are 5 days apart in day-units.
    verts = pc.verts[0]
    assert verts[:, 0].max() - verts[:, 0].min() == pytest.approx(5.0)


def test_mixed_numeric_then_categorical_on_same_axis_is_left_undefined_but_does_not_crash():
    # Not a supported idiom (see plot()'s own docstring), but shouldn't raise
    # -- a plain number is passed through _as_axis_data untouched.
    fig, ax = plotpress.subplots()
    ax.plot(["a", "b"], [1, 2])
    ax.plot([5, 6], [3, 4])  # numeric x on an already-categorical axis
    assert list(ax.artists[1].x) == [5.0, 6.0]


# ---------------------------------------------------------------------------
# set_xlim / set_ylim with datetime/categorical bounds
# ---------------------------------------------------------------------------

def test_set_xlim_accepts_plain_numbers():
    fig, ax = plotpress.subplots()
    assert ax.set_xlim(0, 10) == (0.0, 10.0)


def test_set_xlim_accepts_datetime_strings_on_a_date_axis():
    fig, ax = plotpress.subplots()
    dates = np.array(["2024-01-01", "2024-06-01", "2024-12-01"], dtype="datetime64[D]")
    ax.plot(dates, [1, 2, 3])
    lo, hi = ax.set_xlim("2024-01-01", "2024-06-01")
    assert lo == pytest.approx(float(to_days("2024-01-01")))
    assert hi == pytest.approx(float(to_days("2024-06-01")))


def test_set_xlim_accepts_a_real_datetime_object_even_off_a_date_axis():
    fig, ax = plotpress.subplots()
    ax.set_xlim(dt.date(2024, 1, 1), dt.date(2024, 6, 1))
    assert ax._xlim[0] == pytest.approx(float(to_days(dt.date(2024, 1, 1))))


def test_set_xlim_accepts_known_categories():
    fig, ax = plotpress.subplots()
    ax.bar(["Q1", "Q2", "Q3", "Q4"], [1, 2, 3, 4])
    assert ax.set_xlim("Q1", "Q3") == (0.0, 2.0)


def test_set_xlim_raises_for_string_with_no_categories_yet():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="no categories"):
        ax.set_xlim("nope", 5)


def test_set_xlim_raises_for_unknown_category():
    fig, ax = plotpress.subplots()
    ax.bar(["Q1", "Q2"], [1, 2])
    with pytest.raises(ValueError, match="own categories"):
        ax.set_xlim("Q1", "Q99")


def test_set_ylim_mirrors_set_xlim_for_datetime_and_categorical():
    fig, ax = plotpress.subplots()
    dates = np.array(["2024-01-01", "2024-06-01"], dtype="datetime64[D]")
    ax.plot([1, 2], dates)
    lo, hi = ax.set_ylim("2024-01-01", "2024-06-01")
    assert lo == pytest.approx(float(to_days("2024-01-01")))


# ---------------------------------------------------------------------------
# set_xticks / set_yticks with datetime/categorical positions
# ---------------------------------------------------------------------------

def test_set_xticks_accepts_datetime_positions():
    fig, ax = plotpress.subplots()
    ax.set_xticks(np.array(["2024-01-01", "2024-02-01"], dtype="datetime64[D]"))
    assert ax._xdate
    expected = to_days(np.array(["2024-01-01", "2024-02-01"], dtype="datetime64[D]"))
    assert list(ax._xticks) == pytest.approx(list(expected))


def test_set_xticks_accepts_category_strings_and_declares_them():
    fig, ax = plotpress.subplots()
    ax.set_xticks(["Q1", "Q2", "Q3"])
    assert ax._xcategorical
    assert ax._xcategories == ["Q1", "Q2", "Q3"]
    assert list(ax._xticks) == [0.0, 1.0, 2.0]


def test_set_xticks_minor_accepts_datetime_too():
    fig, ax = plotpress.subplots()
    ax.set_xticks(np.array(["2024-01-01", "2024-01-15"], dtype="datetime64[D]"), minor=True)
    assert ax._minor_ticks_on
    expected = to_days(np.array(["2024-01-01", "2024-01-15"], dtype="datetime64[D]"))
    assert list(ax._xticks_minor) == pytest.approx(list(expected))


# ---------------------------------------------------------------------------
# set_xlocator / set_ylocator / set_xformat / set_yformat + get_xticks/labels
# ---------------------------------------------------------------------------

def test_set_xlocator_overrides_default_ticks():
    fig, ax = plotpress.subplots()
    ax.plot([0, 3 * np.pi], [0, 1])
    ax.set_xlim(0, 3 * np.pi)
    ax.set_xlocator({"kind": "multiple", "base": np.pi / 2})
    ticks = ax.get_xticks()
    assert ticks[1] == pytest.approx(np.pi / 2)


def test_set_xformat_overrides_default_labels():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlim(0, 1)
    ax.set_xformat("percent")
    labels = ax.get_xticklabels()
    assert all(l.endswith("%") for l in labels)


def test_set_xformat_callable_works_for_static_output_but_not_metadata():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xformat(lambda v: f"<{v:.1f}>")
    labels = ax.get_xticklabels()
    assert all(l.startswith("<") for l in labels)


def test_get_xticks_categorical_priority_over_locator():
    fig, ax = plotpress.subplots()
    ax.bar(["A", "B", "C"], [1, 2, 3])
    ax.set_xlocator({"kind": "multiple", "base": 0.5})  # should be shadowed
    assert list(ax.get_xticks()) == [0.0, 1.0, 2.0]
    assert ax.get_xticklabels() == ["A", "B", "C"]


def test_explicit_xticks_still_win_over_categorical_and_locator():
    fig, ax = plotpress.subplots()
    ax.bar(["A", "B", "C"], [1, 2, 3])
    ax.set_xticks([0.5, 1.5])
    assert list(ax.get_xticks()) == [0.5, 1.5]


def test_xlocator_unknown_kind_raises_at_resolution_time():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlocator({"kind": "nonsense"})
    with pytest.raises(ValueError):
        ax.get_xticks()


# ---------------------------------------------------------------------------
# Rendering: SVG/raster/HTML metadata stay consistent with the new axis kinds
# ---------------------------------------------------------------------------

def test_svg_renders_date_axis_tick_labels():
    fig, ax = plotpress.subplots()
    dates = np.array(["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"],
                     dtype="datetime64[D]")
    ax.plot(dates, [1, 2, 3, 4])
    ax.set_xlim("2024-01-01", "2024-10-01")
    svg = fig.to_svg()
    root = _parse(svg)
    texts = [t.text for t in root.findall(".//" + NS + "text") if t.text]
    assert any("2024-" in t for t in texts)


def test_svg_renders_categorical_axis_tick_labels():
    fig, ax = plotpress.subplots()
    ax.bar(["Alpha", "Beta", "Gamma"], [3, 5, 2])
    svg = fig.to_svg()
    root = _parse(svg)
    texts = {t.text for t in root.findall(".//" + NS + "text") if t.text}
    assert {"Alpha", "Beta", "Gamma"} <= texts


def test_svg_renders_pi_formatted_ticks():
    fig, ax = plotpress.subplots()
    ax.plot([0, 3 * np.pi], [0, 1])
    ax.set_xlim(0, 3 * np.pi)
    ax.set_xlocator({"kind": "multiple", "base": np.pi})
    ax.set_xformat("pi")
    svg = fig.to_svg()
    root = _parse(svg)
    texts = {t.text for t in root.findall(".//" + NS + "text") if t.text}
    assert "π" in texts or "2π" in texts or "3π" in texts


def test_raster_renders_categorical_axis_without_crashing(tmp_path):
    pytest.importorskip("PIL", reason="PNG raster backend needs Pillow")
    fig, ax = plotpress.subplots()
    ax.bar(["A", "B", "C"], [1, 2, 3])
    out = tmp_path / "cat.png"
    fig.save(str(out))
    assert out.stat().st_size > 0


def test_tight_layout_measures_categorical_labels_for_margin():
    fig, ax = plotpress.subplots()
    ax.barh(["a very long category name indeed"], [1])
    fig.tight_layout()
    assert ax._rect[0] > 0.05  # widened past the default margin


def test_interactive_metadata_serializes_datetime_categorical_and_locator_flags():
    fig, ax = plotpress.subplots()
    dates = np.array(["2024-01-01", "2024-02-01"], dtype="datetime64[D]")
    ax.plot(dates, [1, 2])
    ax.set_xformat(lambda v: str(v))  # callable: must NOT leak into metadata

    fig2, ax2 = plotpress.subplots()
    ax2.bar(["A", "B"], [1, 2])

    fig3, ax3 = plotpress.subplots()
    ax3.plot([0, 1], [0, 1])
    ax3.set_xlocator({"kind": "multiple", "base": 0.25})

    from plotpress.svg import axes_metadata

    meta = axes_metadata(fig)
    assert meta[0]["xdate"] is True
    assert meta[0]["xformat"] is None  # callable dropped, not crashed

    meta2 = axes_metadata(fig2)
    assert meta2[0]["xcategorical"] is True
    assert meta2[0]["xcategories"] == ["A", "B"]

    meta3 = axes_metadata(fig3)
    assert meta3[0]["xlocator"] == {"kind": "multiple", "base": 0.25}

    # And the whole thing must actually serialize to JSON (this is what
    # to_html() embeds) without raising.
    html = fig.to_html()
    assert "xdate" in html
