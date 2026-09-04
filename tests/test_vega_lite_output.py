"""Figure.to_vega_lite(): a real Vega-Lite v5 spec, not a rendered artifact.

Asserts on the returned ``(result, caveats)`` tuple's own structure/values --
the same "assert on parsed output" convention ``tests/test_vega_output.py``
follows for its Vega sibling. Actually rendering a spec needs a real
Vega-Lite engine (``vega-lite``/``vega``/``vega-cli``, or the ``vl2png`` CLI),
which isn't a test dependency here -- that was verified manually against
every ``docs/examples``/``docs/applications`` gallery script instead (see
the CHANGELOG entry for the real figure/script counts and caveat tally).
"""
import math

import pytest

import plotpress


def _layers(spec):
    return spec["layer"]


def _mark_types(spec):
    return [layer["mark"]["type"] for layer in _layers(spec)]


def test_single_axes_lands_in_grid_not_standalone():
    """A single axes always has a plain 1x1 SubplotSpec (from subplots()),
    so it's "cleanly composable" by definition -- it should end up as the
    (un-concatenated) grid spec, not the standalone list."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    result, caveats = fig.to_vega_lite()
    assert result["grid"] is not None
    assert result["standalone"] == []
    assert caveats == []
    assert result["grid"]["$schema"] == "https://vega.github.io/schema/vega-lite/v5.json"


def test_line_mark_and_field_encoding():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2, 3], [0.0, 1.0, 4.0, 9.0])
    result, _ = fig.to_vega_lite()
    layer = _layers(result["grid"])[0]
    assert layer["mark"]["type"] == "line"
    assert layer["encoding"]["x"]["field"] == "x"
    assert layer["encoding"]["y"]["field"] == "y"
    assert layer["encoding"]["x"]["type"] == "quantitative"
    values = layer["data"]["values"]
    assert [v["x"] for v in values] == [0.0, 1.0, 2.0, 3.0]
    assert [v["y"] for v in values] == [0.0, 1.0, 4.0, 9.0]


def test_nan_becomes_a_null_field_not_a_dropped_row():
    """Vega-Lite's own default invalid-data handling for line marks breaks
    the path at a null value -- so a non-finite point must become {x: ...,
    y: null} in the inline dataset, not be silently dropped (which would
    bridge the gap with a straight line instead of breaking it)."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2, 3], [0.0, 1.0, float("nan"), 3.0])
    result, _ = fig.to_vega_lite()
    values = _layers(result["grid"])[0]["data"]["values"]
    assert len(values) == 4
    assert values[2]["y"] is None
    assert values[2]["x"] is None


def test_dashed_line_gets_a_mark_level_strokedash():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], linestyle="--")
    result, _ = fig.to_vega_lite()
    assert _layers(result["grid"])[0]["mark"]["strokeDash"] == [6.0, 4.0]


def test_scale_domain_matches_resolved_limits_not_numpy_scalars():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    result, _ = fig.to_vega_lite()
    x_enc = _layers(result["grid"])[0]["encoding"]["x"]
    domain = x_enc["scale"]["domain"]
    assert domain == pytest.approx(list(xlim))
    # Regression: ax._resolved_limits() returns numpy floats; json.dumps
    # would still "work" on a bare np.float64 (it's a real float subclass)
    # but the domain values must be plain Python floats, not leak the
    # numpy type into the spec.
    assert all(type(v) is float for v in domain)


def test_log_scale_and_inverted_axis():
    fig, ax = plotpress.subplots()
    ax.plot([1, 10, 100], [1, 2, 3])
    ax.set_xscale("log")
    ax.invert_yaxis()
    result, _ = fig.to_vega_lite()
    enc = _layers(result["grid"])[0]["encoding"]
    assert enc["x"]["scale"]["type"] == "log"
    assert enc["y"]["scale"].get("reverse") is True
    assert "reverse" not in enc["x"]["scale"]


def test_scatter_encodes_size_and_color():
    fig, ax = plotpress.subplots()
    ax.scatter([0, 1, 2], [0, 1, 2], c=[0.0, 0.5, 1.0], cmap="viridis", s=20)
    result, _ = fig.to_vega_lite()
    layer = _layers(result["grid"])[0]
    assert layer["mark"]["type"] == "point"
    values = layer["data"]["values"]
    assert len(values) == 3
    dpi = ax.figure.style.dpi
    diameter_px = 20.0 * (dpi / 72.0)
    expected_size = math.pi * (diameter_px / 2.0) ** 2
    assert all(v["size"] == pytest.approx(expected_size) for v in values)
    assert len({v["color"] for v in values}) > 1


def test_bars_use_precomputed_extents_not_band_scale():
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [3, 7, 2], width=0.8)
    result, _ = fig.to_vega_lite()
    layer = _layers(result["grid"])[0]
    assert layer["mark"]["type"] == "bar"
    v = sorted(layer["data"]["values"], key=lambda r: r["x0"])[1]
    assert v["x0"] == pytest.approx(0.6) and v["x1"] == pytest.approx(1.4)
    assert v["y0"] == pytest.approx(0.0) and v["y1"] == pytest.approx(7.0)


def test_errorbar_uses_precomputed_yerror_not_aggregation():
    fig, ax = plotpress.subplots()
    ax.errorbar([1, 2, 3], [1, 2, 3], yerr=0.2, capsize=5)
    result, _ = fig.to_vega_lite()
    types = _mark_types(result["grid"])
    assert "errorbar" in types
    eb_layer = _layers(result["grid"])[types.index("errorbar")]
    assert eb_layer["encoding"]["yError"]["field"] == "yerr"
    assert eb_layer["mark"]["ticks"]  # caps enabled, not VL's off-by-default
    assert eb_layer["data"]["values"][0]["yerr"] == pytest.approx(0.2)
    # connecting line + point marker also present
    assert "line" in types and "point" in types


def test_pie_uses_native_arc_with_autostacked_theta():
    fig, ax = plotpress.subplots()
    ax.pie([35, 25, 20, 20], labels=list("ABCD"))
    result, _ = fig.to_vega_lite()
    layer = _layers(result["grid"])[0]
    assert layer["mark"]["type"] == "arc"
    assert layer["encoding"]["theta"]["field"] == "value"
    assert layer["encoding"]["theta"]["stack"] is True
    assert "x" not in layer["encoding"] and "y" not in layer["encoding"]
    assert sum(v["value"] for v in layer["data"]["values"]) == pytest.approx(1.0)


def test_stem_produces_three_layers_including_baseline():
    fig, ax = plotpress.subplots()
    ax.stem([1, 2, 3], [3, 1, 4], baseline=1.5)
    result, _ = fig.to_vega_lite()
    types = _mark_types(result["grid"])
    assert types.count("rule") == 2   # stems + baseline
    assert types.count("point") == 1  # tips
    baseline_layer = [l for l in _layers(result["grid"]) if l["mark"]["type"] == "rule"
                      and "x2" in l["encoding"]][0]
    assert baseline_layer["data"]["values"][0]["y"] == pytest.approx(1.5)


def test_reference_line_spans_the_resolved_limits():
    fig, ax = plotpress.subplots()
    ax.plot([0, 5], [0, 5])
    ax.axhline(3)
    result, _ = fig.to_vega_lite()
    types = _mark_types(result["grid"])
    rule_layers = [l for l in _layers(result["grid"]) if l["mark"]["type"] == "rule"]
    hline = next(l for l in rule_layers if l["data"]["values"][0].get("y") == 3.0)
    xlim = ax.get_xlim()
    assert hline["data"]["values"][0]["x0"] == pytest.approx(xlim[0])
    assert hline["data"]["values"][0]["x1"] == pytest.approx(xlim[1])


def test_monotonic_fill_between_uses_area_mark():
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1, 2, 3], [0, 0, 0, 0], [1, 2, 1, 2])
    result, caveats = fig.to_vega_lite()
    assert _mark_types(result["grid"]) == ["area"]
    assert caveats == []


def test_pcolormesh_becomes_a_real_image_mark():
    import numpy as np
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(6.0), np.arange(6.0), np.arange(25.0).reshape(5, 5))
    result, caveats = fig.to_vega_lite()
    assert caveats == []
    layer = _layers(result["grid"])[0]
    assert layer["mark"]["type"] == "image"
    row = layer["data"]["values"][0]
    assert row["url"].startswith("data:image/png;base64,")
    assert row["x"] == pytest.approx(0.0) and row["x2"] == pytest.approx(5.0)


def test_non_monotonic_fill_between_warns_and_skips():
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 2, 1, 3], [0, 0, 0, 0], [1, 1, 1, 1])
    with pytest.warns(UserWarning, match="non-monotonic"):
        result, caveats = fig.to_vega_lite()
    # Nothing exportable was on this axes at all -- no spec, not a spec
    # with empty layers (matches plotpress.vega's own _vega_has_content
    # convention: a figure with no real content behind it gets no spec).
    assert result["grid"] is None


def test_unsupported_artist_warns_and_skips_but_rest_of_figure_exports():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    ax.boxplot([[1, 2, 3, 4, 5]])
    with pytest.warns(UserWarning, match="BoxPlot.*no Vega-Lite mapping"):
        result, caveats = fig.to_vega_lite()
    assert _mark_types(result["grid"]) == ["line"]


def test_legend_warns_and_is_skipped():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.legend()
    with pytest.warns(UserWarning, match="legend"):
        fig.to_vega_lite()


# ---- figure-level composition -------------------------------------------

def test_regular_grid_composes_into_nested_concat():
    fig, axes = plotpress.subplots(2, 2, figsize=(8.0, 6.0))
    for ax in axes.flat:
        ax.plot([0, 1], [0, 1])
    result, caveats = fig.to_vega_lite()
    assert caveats == []
    assert "vconcat" in result["grid"]
    assert len(result["grid"]["vconcat"]) == 2
    for row in result["grid"]["vconcat"]:
        assert len(row["hconcat"]) == 2


def test_twin_axes_merge_with_independent_y_scale():
    """Regression: Axes._subplotspec is COPIED verbatim by twinx()/twiny(),
    so a naive "has a single-cell _subplotspec" check alone would treat a
    twin as an ordinary grid cell instead of an overlay to merge -- the
    real predicate must also check _twin_of is None."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], color="blue")
    ax2 = ax.twinx()
    ax2.plot([0, 1], [100, 200], color="red")
    result, caveats = fig.to_vega_lite()
    assert caveats == []
    assert result["standalone"] == []
    assert len(_layers(result["grid"])) == 2
    assert result["grid"]["resolve"] == {"scale": {"y": "independent"}}


def test_free_form_add_axes_becomes_a_standalone_spec_with_a_caveat():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    inset = fig.add_axes((0.6, 0.6, 0.25, 0.25))
    inset.plot([1, 0], [0, 1])
    result, caveats = fig.to_vega_lite()
    assert result["grid"] is not None       # the plain subplots() axes
    assert len(result["standalone"]) == 1   # the free-form add_axes() one
    assert any("add_axes" in c for c in caveats)


def test_mismatched_grid_shapes_fall_back_to_independent_specs():
    fig, axes = plotpress.subplots(1, 2)
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    extra = fig.add_subplot(2, 2, 1)
    extra.plot([1, 0], [0, 1])
    result, caveats = fig.to_vega_lite()
    assert result["grid"] is None
    assert len(result["standalone"]) == 3
    assert any("different grid shapes" in c for c in caveats)


def test_mesh_flips_raster_rows_on_an_inverted_axis():
    """Regression: reversing the Vega-Lite y-scale repositions an image
    mark's bounding box but does NOT re-flip the raster bitmap inside it
    (unlike a point/line/bar mark, whose geometry is computed from the
    data at render time) -- confirmed by actually rendering an
    inverted-axis mesh through vega-lite/vega and comparing to plotpress's
    own render, which came out upside-down without a manual row flip here.
    """
    import base64
    import io

    import numpy as np
    PIL = pytest.importorskip("PIL.Image", reason="decoding the embedded PNG needs Pillow")

    def top_row_rgb(result):
        url = _layers(result["grid"])[0]["data"]["values"][0]["url"]
        png_bytes = base64.b64decode(url.split(",", 1)[1])
        arr = np.asarray(PIL.open(io.BytesIO(png_bytes)).convert("RGB"))
        return arr[0, 0, :3]  # the RASTER's own row 0 -- what actually got embedded

    z = np.array([[0.0, 0.0], [1.0, 1.0]])  # row 0 (low y) dark, row 1 (high y) bright
    fig, ax = plotpress.subplots()
    ax.pcolormesh([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], z, cmap="viridis")
    upright = top_row_rgb(fig.to_vega_lite()[0])

    fig2, ax2 = plotpress.subplots()
    ax2.pcolormesh([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], z, cmap="viridis")
    ax2.invert_yaxis()
    inverted = top_row_rgb(fig2.to_vega_lite()[0])

    # The raster's own row 0 must be a DIFFERENT row of source data
    # (dark-low-y vs. bright-high-y) once the axis is inverted -- if the
    # flip weren't applied, both would embed the identical unflipped PNG.
    assert not np.array_equal(upright, inverted)


def test_grid_span_is_placed_once_not_duplicated():
    """Regression: a multi-cell span used to be inserted as the SAME dict
    object into every cell it covered, so it rendered duplicated side by
    side in that row's hconcat instead of spanning once."""
    fig = plotpress.Figure(figsize=(6.4, 4.8))
    gs = fig.add_gridspec(2, 2)
    top = fig.add_subplot(gs[0, :])
    bl = fig.add_subplot(gs[1, 0])
    br = fig.add_subplot(gs[1, 1])
    top.plot([1, 2], [1, 2])
    bl.plot([1, 2], [3, 4])
    br.plot([1, 2], [5, 6])
    result, caveats = fig.to_vega_lite()
    row0 = result["grid"]["vconcat"][0]
    assert "hconcat" not in row0   # one spec, not two duplicate entries
    row1 = result["grid"]["vconcat"][1]
    assert len(row1["hconcat"]) == 2
    assert row1["hconcat"][0] is not row1["hconcat"][1]
    assert any("spans rows" in c for c in caveats)


def test_colorbar_axes_is_dropped_with_a_caveat_not_silently():
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh([0, 1], [0, 1], [[1]])
    fig.colorbar(mesh, ax=ax)
    result, caveats = fig.to_vega_lite()
    assert result["standalone"] == []
    assert any("colorbar" in c for c in caveats)


def test_twiny_gets_independent_x_not_y():
    """Regression: _merge_twin hardcoded resolve.scale.y independent for
    every twin, which is backwards for twiny() (shares y, wants x
    independent) -- only correct for twinx()."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 5, 10], [1, 2, 3])
    ax2 = ax.twiny()
    ax2.plot([1000, 1500, 2000], [1, 2, 3], color="red")
    result, caveats = fig.to_vega_lite()
    assert result["grid"]["resolve"] == {"scale": {"x": "independent"}}


def test_bars_with_per_bar_rgba_array_colors_does_not_crash():
    """Regression: set(art.colors) on raw (unhashable numpy row) colors
    crashed for a per-bar RGBA array -- must use the resolved hex strings."""
    fig, ax = plotpress.subplots()
    ax.bar([0, 1, 2], [1, 2, 3],
          color=[[1.0, 0, 0, 1], [0, 1.0, 0, 1], [0, 0, 1.0, 1]])
    result, _ = fig.to_vega_lite()  # must not raise
    assert result["grid"]["layer"][0]["mark"]["type"] == "bar"


def test_errorbar_capsize_zero_suppresses_ticks():
    fig, ax = plotpress.subplots()
    ax.errorbar([1, 2, 3], [1, 2, 3], yerr=0.2, capsize=0)
    result, _ = fig.to_vega_lite()
    eb = next(l for l in result["grid"]["layer"] if l["mark"]["type"] == "errorbar")
    assert "ticks" not in eb["mark"]


def test_text_rotation_and_va_are_applied():
    fig, ax = plotpress.subplots()
    ax.text(1, 1, "hi", rotation=90, va="top")
    result, _ = fig.to_vega_lite()
    text_layer = next(l for l in result["grid"]["layer"] if l["mark"]["type"] == "text")
    assert text_layer["mark"]["angle"] == -90
    assert text_layer["mark"]["baseline"] == "top"


def test_json_serializable_end_to_end():
    import json
    fig, axes = plotpress.subplots(1, 2)
    axes[0].errorbar([1, 2, 3], [1, 2, 3], yerr=0.3, capsize=4)
    axes[1].pie([1, 2, 3])
    result, caveats = fig.to_vega_lite()
    json.dumps(result)  # must not raise
