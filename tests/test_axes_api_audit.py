"""Coverage for the matplotlib-Axes-API-audit sweep: getters, set(),
set_box_aspect, minor-tick positions, get_legend*, and the new plotting
methods (pcolor, arrow, quiverkey, indicate_inset*, bar_label, clabel,
table, barbs). See CHANGELOG.md for the full list and what was
deliberately left out (datetime axes, streamplot, the tri* family).
"""
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import plotpress

NS = "{http://www.w3.org/2000/svg}"


def _parse(svg):
    return ET.fromstring(svg)


# -- getters ------------------------------------------------------------
def test_get_aspect_matches_what_was_set():
    fig, ax = plotpress.subplots()
    assert ax.get_aspect() == "auto"
    ax.set_aspect("equal")
    assert ax.get_aspect() == 1.0
    ax.set_aspect(2.5)
    assert ax.get_aspect() == 2.5


def test_get_xbound_get_ybound_always_sorted_regardless_of_direction():
    fig, ax = plotpress.subplots()
    ax.set_xlim(5, 1)   # reversed on purpose
    assert ax.get_xlim() == (5.0, 1.0)          # direction preserved
    assert ax.get_xbound() == (1.0, 5.0)        # always low, high
    ax.set_ylim(-2, 8)
    assert ax.get_ybound() == (-2.0, 8.0)


def test_get_xticklabels_get_yticklabels_reflect_explicit_and_auto():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    auto = ax.get_xticklabels()
    assert len(auto) == len(ax.get_xticks())
    ax.set_xticks([0, 1, 2], ["a", "b", "c"])
    assert ax.get_xticklabels() == ["a", "b", "c"]


def test_xaxis_inverted_yaxis_inverted_track_invert_calls():
    fig, ax = plotpress.subplots()
    assert ax.xaxis_inverted() is False
    ax.invert_xaxis()
    assert ax.xaxis_inverted() is True
    assert ax.yaxis_inverted() is False
    ax.invert_yaxis()
    assert ax.yaxis_inverted() is True


def test_autoscale_on_getters_track_explicit_limits():
    fig, ax = plotpress.subplots()
    assert ax.get_autoscalex_on() and ax.get_autoscaley_on()
    ax.set_autoscalex_on(False)
    assert ax.get_autoscalex_on() is False
    assert ax.get_autoscaley_on() is True
    ax.set_autoscalex_on(True)
    assert ax.get_autoscalex_on() is True


# -- set_box_aspect -------------------------------------------------------
def test_set_box_aspect_shrinks_and_centers_the_drawn_box():
    fig, ax = plotpress.subplots(figsize=(8, 4))
    ax.plot([0, 1], [0, 1])
    ax.set_box_aspect(1.0)   # square box in a wide figure -> must shrink width
    assert ax.get_box_aspect() == 1.0
    from plotpress.svg import _effective_rect, _pixel_rect

    dpi = fig.style.dpi
    rect = _effective_rect(ax, *_pixel_rect(ax, fig.figsize[0] * dpi, fig.figsize[1] * dpi),
                           (0, 1), (0, 1))
    assert rect[2] == pytest.approx(rect[3], rel=1e-6)   # width == height


def test_set_box_aspect_none_restores_full_allocated_box():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_box_aspect(0.3)
    ax.set_box_aspect(None)
    assert ax.get_box_aspect() is None


# -- minor ticks ----------------------------------------------------------
def test_set_xticks_minor_places_explicit_minor_tick_marks():
    fig, ax = plotpress.subplots()
    ax.plot([0, 4], [0, 4])
    ax.set_xticks([0.5, 1.5, 2.5, 3.5], minor=True)
    assert ax._minor_ticks_on is True   # matches matplotlib: implies visibility
    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 4], [0, 4])
    assert fig.to_svg() != fig2.to_svg()


def test_set_yticks_minor_reaches_the_per_axes_interactive_metadata():
    """Explicit minor ticks must count as "fixed" for the client-side
    zoom-rebuild gate (see svg.py's xfixed/yfixed) -- otherwise they render
    correctly once, then silently revert to the auto minor-tick algorithm
    the moment a reader zooms, the same regression class already fixed for
    tick_params() and grid(alpha=)."""
    import json
    import re

    fig, ax = plotpress.subplots()
    ax.plot([0, 4], [0, 4])
    ax.set_yticks([0.5, 1.5], minor=True)
    html = fig.to_html(interactive=True)
    m = re.search(r'"yfixed"\s*:\s*\[[^\]]*\]', html)
    assert m and "true" in m.group(0)


# -- set() bulk setter ------------------------------------------------------
def test_set_dispatches_each_kwarg_to_its_setter():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ret = ax.set(xlabel="X", ylabel="Y", title="T", xlim=(0, 5), aspect="equal")
    assert ret is ax
    assert ax.get_xlabel() == "X"
    assert ax.get_ylabel() == "Y"
    assert ax.get_title() == "T"
    assert ax.get_xlim() == (0.0, 5.0)
    assert ax.get_aspect() == 1.0


def test_set_raises_naming_every_unknown_keyword_at_once():
    fig, ax = plotpress.subplots()
    with pytest.raises(AttributeError) as exc:
        ax.set(bogus_one=1, xlabel="ok", bogus_two=2)
    msg = str(exc.value)
    assert "bogus_one" in msg and "bogus_two" in msg
    assert ax.get_xlabel() == "ok"   # the valid keyword still applied


# -- legend introspection --------------------------------------------------
def test_legend_returns_a_legend_handle_and_get_legend_matches_it():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="line")
    leg = ax.legend()
    assert leg is not None
    assert leg.get_visible() is True
    assert ax.get_legend() is not None
    assert ax.get_legend().get_visible() is True


def test_get_legend_is_none_before_legend_called_and_after_removal():
    fig, ax = plotpress.subplots()
    assert ax.get_legend() is None
    ax.plot([0, 1], [0, 1], label="line")
    leg = ax.legend()
    leg.remove()
    assert ax.get_legend() is None
    assert leg.get_visible() is False


def test_get_legend_handles_labels_matches_what_legend_would_draw():
    fig, ax = plotpress.subplots()
    a = ax.plot([0, 1], [0, 1], label="first")
    ax.plot([0, 1], [1, 0])   # unlabeled -- must be excluded
    b = ax.scatter([0], [0], label="second")
    handles, labels = ax.get_legend_handles_labels()
    assert labels == ["first", "second"]
    assert handles == [a, b]


def test_get_legend_handles_labels_honors_legend_handles_override():
    fig, ax = plotpress.subplots()
    a = ax.plot([0, 1], [0, 1], label="a")
    b = ax.plot([0, 1], [1, 0], label="b")
    ax.legend(handles=[b, a])
    handles, labels = ax.get_legend_handles_labels()
    assert handles == [b, a]
    assert labels == ["b", "a"]


def test_legend_get_texts_and_set_title():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="x")
    leg = ax.legend()
    assert leg.get_texts() == ["x"]
    leg.set_title("Legend")
    assert leg.get_title() == "Legend"
    assert ax._legend_title == "Legend"


# -- pcolor -----------------------------------------------------------------
def test_pcolor_is_a_true_alias_of_pcolormesh():
    fig, ax = plotpress.subplots()
    Z = np.random.default_rng(0).random((4, 4))
    mesh = ax.pcolor(Z)
    fig2, ax2 = plotpress.subplots()
    mesh2 = ax2.pcolormesh(Z)
    assert fig.to_svg() == fig2.to_svg()
    assert type(mesh) is type(mesh2)


# -- arrow --------------------------------------------------------------
def test_arrow_draws_exactly_the_given_offset_no_autoscaling():
    fig, ax = plotpress.subplots()
    q = ax.arrow(1.0, 2.0, 3.0, -1.0, color="red")
    assert q.X[0] == 1.0 and q.Y[0] == 2.0
    assert q.U[0] == 3.0 and q.V[0] == -1.0
    assert q.scale == 1.0   # exact offset, no quiver-style auto-scaling
    assert q.tips() == (np.array([4.0]), np.array([1.0]))


def test_arrow_renders_without_error_in_all_backends():
    fig, ax = plotpress.subplots()
    ax.arrow(0, 0, 1, 1)
    pytest.importorskip("PIL")
    import tempfile

    from plotpress.raster import figure_to_image, save_pdf
    figure_to_image(fig)
    save_pdf(fig, tempfile.mktemp(suffix=".pdf"))


# -- quiverkey --------------------------------------------------------------
def test_quiverkey_places_a_reference_arrow_and_label():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    Q = ax.quiver([0.5], [0.5], [0.2], [0.0])
    n_before = len(ax.artists)
    ax.quiverkey(Q, 0.5, 0.9, 0.2, "key label")
    assert len(ax.artists) == n_before + 2   # the key arrow + its label text
    svg = fig.to_svg()
    assert "key label" in svg


def test_quiverkey_label_stays_inside_the_axes_even_near_a_corner():
    """Regression: a key placed near a corner, plus its own outward label
    offset and the arrow's own length, could push the label's anchor past
    the visible range -- invisible behind the axes' clip rect rather than
    just close to the edge."""
    fig, ax = plotpress.subplots(figsize=(6, 5))
    X, Y = np.meshgrid(np.linspace(0.5, 3.5, 4), np.linspace(0.5, 3.5, 4))
    Q = ax.quiver(X, Y, np.ones_like(X) * 0.3, np.ones_like(Y) * 0.1)
    ax.set_xlim(0, 4.5)
    ax.set_ylim(0, 4.5)
    ax.quiverkey(Q, 0.85, 0.95, 0.3, "0.3 u/step", coordinates="axes")
    text_el = next(el for el in _parse(fig.to_svg()).iter(f"{NS}text")
                   if "u/step" in "".join(el.itertext()))
    (xmin, xmax), (ymin, ymax) = ax.get_xlim(), ax.get_ylim()
    from plotpress.svg import _effective_rect, _pixel_rect

    dpi = fig.style.dpi
    L, T, W, H = _effective_rect(ax, *_pixel_rect(ax, fig.figsize[0] * dpi,
                                                  fig.figsize[1] * dpi),
                                 (xmin, xmax), (ymin, ymax))
    x = float(text_el.get("x"))
    assert L <= x <= L + W, "the label's own anchor must stay inside the axes rect"


def test_quiverkey_data_coordinates_mode():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    Q = ax.quiver([5], [5], [1], [0])
    ax.quiverkey(Q, 8, 8, 1, "k", coordinates="data")
    # the key arrow anchor should sit exactly at the given data point
    key = ax.artists[-2]   # the key arrow (label text is last)
    assert key.X[0] == 8.0 and key.Y[0] == 8.0


# -- indicate_inset / indicate_inset_zoom -----------------------------------
def test_indicate_inset_draws_a_closed_rectangle_at_the_given_bounds():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    line = ax.indicate_inset((2.0, 3.0, 4.0, 1.0))
    assert list(line.x) == [2.0, 6.0, 6.0, 2.0, 2.0]
    assert list(line.y) == [3.0, 3.0, 4.0, 4.0, 3.0]


def test_indicate_inset_zoom_reads_bounds_from_the_inset_axes_limits():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    inset = ax.inset_axes([0.6, 0.6, 0.3, 0.3])
    inset.set_xlim(2, 5)
    inset.set_ylim(1, 3)
    line = ax.indicate_inset_zoom(inset)
    assert list(line.x) == [2.0, 5.0, 5.0, 2.0, 2.0]
    assert list(line.y) == [1.0, 1.0, 3.0, 3.0, 1.0]


def test_indicate_inset_zoom_handles_an_inverted_inset_view():
    fig, ax = plotpress.subplots()
    ax.plot([0, 10], [0, 10])
    inset = ax.inset_axes([0.6, 0.6, 0.3, 0.3])
    inset.set_xlim(5, 2)   # reversed
    line = ax.indicate_inset_zoom(inset)
    assert min(line.x) == 2.0 and max(line.x) == 5.0


# -- bar_label ----------------------------------------------------------
def test_bar_label_places_text_above_positive_and_below_negative_bars():
    fig, ax = plotpress.subplots()
    bars = ax.bar([0, 1], [5, -3])
    texts = ax.bar_label(bars)
    assert len(texts) == 2
    assert texts[0].text == "5" and texts[0].va == "bottom"
    assert texts[1].text == "-3" and texts[1].va == "top"
    assert texts[0].x == 0.0 and texts[1].x == 1.0


def test_bar_label_custom_labels_override_the_formatted_value():
    fig, ax = plotpress.subplots()
    bars = ax.bar([0, 1], [5, 3])
    texts = ax.bar_label(bars, labels=["five", "three"])
    assert [t.text for t in texts] == ["five", "three"]


def test_bar_label_horizontal_bars_place_text_left_or_right_of_the_tip():
    fig, ax = plotpress.subplots()
    bars = ax.barh([0, 1], [4, -2])
    texts = ax.bar_label(bars)
    assert texts[0].ha == "left" and texts[1].ha == "right"
    assert texts[0].y == 0.0 and texts[1].y == 1.0


# -- clabel -------------------------------------------------------------
def test_clabel_adds_one_text_per_contour_level():
    fig, ax = plotpress.subplots()
    g = np.linspace(-2, 2, 30)
    X, Y = np.meshgrid(g, g)
    Z = np.exp(-(X ** 2 + Y ** 2))
    CS = ax.contour(g, g, Z, levels=[0.2, 0.5, 0.8])
    texts = ax.clabel(CS)
    levels_with_segments = [lvl for lvl, _, segs in CS.line_segments if segs]
    assert len(texts) == len(levels_with_segments)


def test_clabel_levels_kwarg_restricts_which_levels_get_labeled():
    fig, ax = plotpress.subplots()
    g = np.linspace(-2, 2, 30)
    X, Y = np.meshgrid(g, g)
    Z = np.exp(-(X ** 2 + Y ** 2))
    CS = ax.contour(g, g, Z, levels=[0.2, 0.5, 0.8])
    texts = ax.clabel(CS, levels=[0.5])
    assert len(texts) <= 1


# -- table --------------------------------------------------------------
def test_table_cell_count_matches_rows_and_columns_with_headers():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    t = ax.table(cellText=[["1", "2"], ["3", "4"]], rowLabels=["r1", "r2"],
                colLabels=["c1", "c2"])
    svg = fig.to_svg()
    root = _parse(svg)
    # 3 rows (header + 2 data) x 3 cols (row-label + 2 data) = 9 cells
    rects_after_table = [el for el in root.iter(f"{NS}rect")
                         if el.get("stroke") == "#888888"]
    assert len(rects_after_table) == 9


def test_table_is_positioned_outside_the_data_zoom_group():
    """A table describes the axes, not the data -- it must not move/scale
    with a per-axes interactive data zoom, the same as transform=
    ax.transAxes text."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.table(cellText=[["1"]])
    root = _parse(fig.to_svg())
    parent = {c: p for p in root.iter() for c in p}
    rect = next(el for el in root.iter(f"{NS}rect") if el.get("stroke") == "#888888")
    node = rect
    inside_zoom = False
    while node in parent:
        node = parent[node]
        if node.get("class") == "plotpress-zoom":
            inside_zoom = True
            break
    assert not inside_zoom


def test_table_renders_without_error_in_raster_and_pdf():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.table(cellText=[["1", "2"], ["3", "4"]], rowLabels=["r1", "r2"],
             colLabels=["c1", "c2"],
             cellColours=[["#eef", "#eef"], ["#fee", "#fee"]])
    pytest.importorskip("PIL")
    import tempfile

    from plotpress.raster import figure_to_image, save_pdf
    figure_to_image(fig)
    save_pdf(fig, tempfile.mktemp(suffix=".pdf"))


# -- barbs --------------------------------------------------------------
def test_barbs_decomposes_speed_into_pennants_full_and_half_ticks():
    from plotpress.svg import _barb_geometry

    # 65 -> nearest 5 = 65 = 1 pennant (50) + 1 full (10) + 1 half (5)
    lines, polys, calm = _barb_geometry(0.0, 0.0, 0.0, 65.0, 20.0)
    assert not calm
    assert len(polys) == 1                 # one 50-unit pennant
    assert len(lines) == 1 + 1 + 1          # shaft + one full tick + one half tick


def test_barbs_calm_speed_draws_a_circle_not_a_shaft():
    from plotpress.svg import _barb_geometry

    lines, polys, calm = _barb_geometry(0.0, 0.0, 0.0, 2.0, 20.0)   # rounds to 0
    assert calm
    assert lines == [] and polys == []


def test_barbs_renders_without_error_in_all_backends():
    fig, ax = plotpress.subplots()
    X, Y = np.meshgrid(np.arange(3), np.arange(3))
    U = np.array([[0, 15, 55], [8, 25, 62], [3, 12, 48]], dtype=float)
    V = np.full((3, 3), 10.0)
    b = ax.barbs(X, Y, U, V)
    assert b.length == 7.0
    svg = fig.to_svg()
    assert "<polygon" in svg   # at least one pennant among these speeds
    pytest.importorskip("PIL")
    import tempfile

    from plotpress.raster import figure_to_image, save_pdf
    figure_to_image(fig)
    save_pdf(fig, tempfile.mktemp(suffix=".pdf"))
