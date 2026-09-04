"""Figure.to_vega(): a real Vega v5 JSON spec, not a rendered artifact.

Asserts on the returned dict's own structure/values (scale domains/ranges,
mark encode fields, data rows) rather than pixel output -- the same "assert
on parsed output" convention test_svg_output.py's XML parsing follows,
just for a dict instead of an ElementTree. Actually rendering the spec
needs a real Vega engine (vega-cli/vega-embed), which isn't a test
dependency here -- that was verified manually against every script in the
docs/examples and docs/applications galleries instead (278 figures across
240 scripts exported and rendered correctly via vg2png, zero blank or
malformed; see the accompanying CHANGELOG entry).
"""
import math

import numpy as np
import pytest

import plotpress


def _marks_of_type(group, mark_type):
    # Data marks live inside an inner, clipped "<name>_data" child group
    # (see vega.py's _axes_to_group) -- unwrap one level in, transparently,
    # so tests can ask "what marks does this axes have" without caring
    # about that inner-group implementation detail.
    inner = group["marks"][0]["marks"] if group["marks"] and group["marks"][0].get("type") == "group" else group["marks"]
    return [m for m in inner if m.get("type") == mark_type]


def _data(spec, name):
    for d in spec["data"]:
        if d["name"] == name:
            return d["values"]
    raise KeyError(name)


def test_top_level_shape():
    fig, ax = plotpress.subplots(figsize=(5.0, 4.0))
    ax.plot([0, 1, 2], [0, 1, 4])
    spec = fig.to_vega()
    assert spec["$schema"] == "https://vega.github.io/schema/vega/v5.json"
    assert spec["width"] == pytest.approx(500.0)   # figsize * default dpi (100)
    assert spec["height"] == pytest.approx(400.0)
    assert isinstance(spec["marks"], list) and len(spec["marks"]) == 1
    assert spec["marks"][0]["type"] == "group"
    assert "data" in spec


def test_line_uses_real_field_scale_encoding_not_frozen_pixels():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2, 3], [0.0, 1.0, 4.0, 9.0])
    spec = fig.to_vega()
    group = spec["marks"][0]
    lines = _marks_of_type(group, "line")
    assert len(lines) == 1
    enc = lines[0]["encode"]["enter"]
    assert enc["x"]["scale"] == "x0" and enc["x"]["field"] == "x"
    assert enc["y"]["scale"] == "y0" and enc["y"]["field"] == "y"
    values = _data(spec, lines[0]["from"]["data"])
    assert [v["x"] for v in values] == [0.0, 1.0, 2.0, 3.0]
    assert [v["y"] for v in values] == [0.0, 1.0, 4.0, 9.0]


def test_y_scale_puts_high_data_values_toward_pixel_zero():
    """Regression: the y scale's domain must stay ascending, with the flip
    encoded in `range` instead -- a manually-descending domain array is not
    guaranteed to survive some Vega scale types' own internal re-sorting,
    which silently re-inverts the axis back the wrong way. Caught by
    actually rendering a spec with vg2png during development -- a y=x**2
    line rendered sloping *down* left-to-right until this was fixed."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    spec = fig.to_vega()
    y_scale = spec["marks"][0]["scales"][1]
    assert y_scale["name"] == "y0"
    assert y_scale["domain"] == pytest.approx(list(ylim))    # ascending
    assert ylim[0] < ylim[1]
    assert y_scale["range"] == [pytest.approx(spec["marks"][0]["encode"]["enter"]["height"]["value"]), 0]


def test_x_scale_puts_low_data_values_toward_pixel_zero():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    xlim = ax.get_xlim()
    spec = fig.to_vega()
    x_scale = spec["marks"][0]["scales"][0]
    assert x_scale["name"] == "x0"
    assert x_scale["domain"] == pytest.approx(list(xlim))    # ascending
    assert xlim[0] < xlim[1]
    assert x_scale["range"] == [0, pytest.approx(spec["marks"][0]["encode"]["enter"]["width"]["value"])]


def test_inverted_axes_flip_the_range_not_the_domain():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.invert_xaxis()
    ax.invert_yaxis()
    xlim, ylim = ax.get_xlim(), ax.get_ylim()   # already ascending -- inversion flips only the range
    spec = fig.to_vega()
    group = spec["marks"][0]
    x_scale, y_scale = group["scales"]
    w = group["encode"]["enter"]["width"]["value"]
    h = group["encode"]["enter"]["height"]["value"]
    assert x_scale["domain"] == pytest.approx(list(xlim))
    assert x_scale["range"] == [pytest.approx(w), 0]     # flipped from the normal case
    assert y_scale["domain"] == pytest.approx(list(ylim))
    assert y_scale["range"] == [0, pytest.approx(h)]     # flipped from the normal case


def test_log_scale_type():
    fig, ax = plotpress.subplots()
    ax.plot([1, 10, 100], [1, 2, 3])
    ax.set_xscale("log")
    spec = fig.to_vega()
    assert spec["marks"][0]["scales"][0]["type"] == "log"
    assert spec["marks"][0]["scales"][1]["type"] == "linear"


def test_scatter_marks_carry_color_and_size():
    """Regression: `s` is a diameter in points (the same convention every
    other backend uses), so the exported Vega `size` (pixel *area*, per
    Vega's own symbol-mark semantics -- not diameter squared) must go
    through both the dpi/72 points->pixels conversion svg.py/raster.py
    always apply, and pi*(d/2)**2, not `s ** 2` -- a figure at the library's
    default dpi=100 rendered ~28% too-small, ~27% too little area, markers
    until both conversions were added."""
    fig, ax = plotpress.subplots()
    ax.scatter([0, 1, 2], [0, 1, 2], c=[0.0, 0.5, 1.0], cmap="viridis", s=20)
    spec = fig.to_vega()
    symbols = _marks_of_type(spec["marks"][0], "symbol")
    assert len(symbols) == 1
    values = _data(spec, symbols[0]["from"]["data"])
    assert len(values) == 3
    assert all(v["color"].startswith("#") and len(v["color"]) == 7 for v in values)
    dpi = fig.style.dpi
    diameter_px = 20.0 * (dpi / 72.0)
    expected_size = math.pi * (diameter_px / 2.0) ** 2
    assert all(v["size"] == pytest.approx(expected_size) for v in values)
    # Distinct colormap positions must not all collapse to the same color.
    assert len({v["color"] for v in values}) > 1


def test_bars_and_scatter_carry_their_edge_when_set():
    """Regression: both _bars_marks and _scatter_marks independently dropped
    the edge/outline (bar edgecolor, scatter marker edgecolor) that
    svg.py/raster.py and primitives.py's own ScatterCollection->Markers
    conversion both draw -- silently losing it in the Vega export for any
    figure that sets one. (Line2D's own per-vertex marker has no edge
    concept in plotpress at all -- plot() exposes no markeredgecolor -- so
    there's nothing to regression-test for that artist type here.)"""
    fig, axes = plotpress.subplots(1, 2, figsize=(6.0, 3.0))
    axes[0].bar([0, 1], [1, 2], edgecolor="black", linewidth=2.0)
    axes[1].scatter([0, 1], [0, 1], edgecolors="black", linewidths=1.5)

    bar_enc = _marks_of_type(fig.to_vega()["marks"][0], "rect")[0]["encode"]["enter"]
    assert bar_enc["stroke"]["value"] == "#000000"
    assert bar_enc["strokeWidth"]["value"] == pytest.approx(2.0)

    scatter_enc = _marks_of_type(fig.to_vega()["marks"][1], "symbol")[0]["encode"]["enter"]
    assert scatter_enc["stroke"]["value"] == "#000000"
    assert scatter_enc["strokeWidth"]["value"] > 0


def test_bars_and_scatter_have_no_stroke_when_edge_not_set():
    fig, axes = plotpress.subplots(1, 2, figsize=(6.0, 3.0))
    axes[0].bar([0, 1], [1, 2])
    axes[1].scatter([0, 1], [0, 1])
    bar_enc = _marks_of_type(fig.to_vega()["marks"][0], "rect")[0]["encode"]["enter"]
    scatter_enc = _marks_of_type(fig.to_vega()["marks"][1], "symbol")[0]["encode"]["enter"]
    assert "stroke" not in bar_enc
    assert "stroke" not in scatter_enc


def test_pie_marks_have_a_real_data_transform_and_a_visible_radius():
    """Regression: the "pie" transform belongs on a *data* entry, not on the
    mark itself -- Vega marks have no `transform` property and silently
    ignore one there. The original version put it on the mark, left
    startAngle hardcoded to 0 and never set endAngle at all, and never set
    outerRadius or a real x/y center -- every wedge was a zero-angle,
    zero-radius arc at the group's local (0, 0) corner. Confirmed by
    actually rendering a pie spec through vg2png: nothing appeared at all."""
    fig, ax = plotpress.subplots(figsize=(5.0, 5.0))
    ax.pie([35, 25, 20, 20], labels=list("ABCD"))
    spec = fig.to_vega()
    group = spec["marks"][0]
    arcs = _marks_of_type(group, "arc")
    assert len(arcs) == 1
    arc = arcs[0]
    enc = arc["encode"]["enter"]
    assert enc["startAngle"] == {"field": "startAngle"}
    assert enc["endAngle"] == {"field": "endAngle"}
    assert enc["outerRadius"]["value"] > 0
    # Centered on the axes' own pixel rect, not left at the local origin.
    assert enc["x"]["value"] > 0 and enc["y"]["value"] > 0
    pie_data = arc["from"]["data"]
    entry = next(d for d in spec["data"] if d["name"] == pie_data)
    assert entry["transform"] == [
        {"type": "pie", "field": "value", "startAngle": pytest.approx(0.0)}
    ]
    assert len(entry["values"]) == 4
    assert sum(v["value"] for v in entry["values"]) == pytest.approx(1.0)


def test_bars_marks_have_correct_rect_geometry():
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [3, 7, 2], width=0.8)
    spec = fig.to_vega()
    rects = _marks_of_type(spec["marks"][0], "rect")
    assert len(rects) == 1
    values = _data(spec, rects[0]["from"]["data"])
    assert len(values) == 3
    v = sorted(values, key=lambda r: r["x0"])[1]   # the bar at x=1, height 7
    assert v["x0"] == pytest.approx(0.6) and v["x1"] == pytest.approx(1.4)
    assert v["y0"] == pytest.approx(0.0) and v["y1"] == pytest.approx(7.0)


def test_mesh_becomes_an_image_mark_with_a_real_data_uri():
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(6, dtype=float), np.arange(6, dtype=float),
                  np.arange(25, dtype=float).reshape(5, 5))
    spec = fig.to_vega()
    images = _marks_of_type(spec["marks"][0], "image")
    assert len(images) == 1
    url = images[0]["encode"]["enter"]["url"]["value"]
    assert url.startswith("data:image/png;base64,")


def test_multiple_axes_become_separate_correctly_positioned_groups():
    fig, axes = plotpress.subplots(1, 2, figsize=(8.0, 4.0))
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    spec = fig.to_vega()
    assert len(spec["marks"]) == 2
    left, right = spec["marks"]
    assert left["encode"]["enter"]["x"]["value"] < right["encode"]["enter"]["x"]["value"]
    # Each group's own scale names must not collide with the other's.
    assert left["scales"][0]["name"] != right["scales"][0]["name"]


def test_unsupported_artist_warns_and_skips_but_the_rest_of_the_figure_exports():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])          # supported -- must still be present
    ax.boxplot([[1, 2, 3, 4, 5]])           # not yet supported -- must be skipped, not fatal
    with pytest.warns(UserWarning, match="BoxPlot.*no Vega mapping yet"):
        spec = fig.to_vega()
    group = spec["marks"][0]
    assert len(_marks_of_type(group, "line")) == 1
    assert len(_marks_of_type(group, "rect")) == 0   # the boxplot itself never rendered


def test_colorbar_and_hidden_axes_are_excluded():
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.arange(4.0).reshape(2, 2))
    fig.colorbar(mesh, ax=ax)
    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 1], [0, 1])
    ax2.set_visible(False)

    spec = fig.to_vega()
    assert len(spec["marks"]) == 1   # the colorbar axes must not get its own group

    spec2 = fig2.to_vega()
    assert len(spec2["marks"]) == 0   # nothing visible to draw


def test_data_marks_are_clipped_but_axis_chrome_is_not():
    """Regression: axis ticks/labels/titles and a group's own `title` are
    Vega child marks drawn *outside* the plot rectangle by design -- putting
    `clip` on the outer axes group cut all of that away in a real Vega
    render (confirmed via vg2png; nothing about it is visible from the JSON
    structure alone, since Vega silently omits the clipped marks rather
    than erroring). Only the inner data-only group may clip."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    spec = fig.to_vega()
    outer = spec["marks"][0]
    assert "clip" not in outer["encode"]["enter"]
    assert len(outer["marks"]) == 1
    inner = outer["marks"][0]
    assert inner["type"] == "group"
    assert inner["encode"]["enter"]["clip"]["value"] is True
    assert inner["encode"]["enter"]["width"] == outer["encode"]["enter"]["width"]
    assert inner["encode"]["enter"]["height"] == outer["encode"]["enter"]["height"]
    assert any(m.get("type") == "line" for m in inner["marks"])


def test_figure_group_becomes_a_labeled_box_spanning_its_axes():
    fig, axes = plotpress.subplots(1, 2, figsize=(8.0, 4.0))
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    fig.group("My Group", list(axes), title_position="top", color="red")
    spec = fig.to_vega()
    # The group box is a figure-pixel-space mark, a sibling of the two
    # per-axes groups -- not nested inside either one.
    top_types = [m["type"] for m in spec["marks"]]
    assert top_types.count("group") == 2
    assert top_types.count("rect") == 1
    assert top_types.count("text") == 1
    box = next(m for m in spec["marks"] if m["type"] == "rect")
    title = next(m for m in spec["marks"] if m["type"] == "text")
    assert title["encode"]["enter"]["text"]["value"] == "My Group"
    assert box["encode"]["enter"]["stroke"]["value"] == "red"
    left_ax = next(m for m in spec["marks"] if m.get("name") == "axes0")
    right_ax = next(m for m in spec["marks"] if m.get("name") == "axes1")
    lx, ly = left_ax["encode"]["enter"]["x"]["value"], left_ax["encode"]["enter"]["y"]["value"]
    rx = right_ax["encode"]["enter"]["x"]["value"]
    # The box must wrap both axes, not sit inside/beside just one.
    assert box["encode"]["enter"]["x"]["value"] < lx
    assert box["encode"]["enter"]["y"]["value"] < ly
    assert (box["encode"]["enter"]["x"]["value"] + box["encode"]["enter"]["width"]["value"]) > rx


def test_axes_title_and_labels_carry_through():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("my title")
    ax.set_xlabel("time"); ax.set_ylabel("value")
    spec = fig.to_vega()
    group = spec["marks"][0]
    assert group["title"] == "my title"
    assert group["axes"][0]["title"] == "time"
    assert group["axes"][1]["title"] == "value"
