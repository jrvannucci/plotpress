"""SVG/HTML serialization: well-formedness, structure, and file output."""

import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import simpleplot

NS = "{http://www.w3.org/2000/svg}"


def _parse(svg):
    return ET.fromstring(svg)


def test_svg_is_well_formed_and_sized():
    fig, ax = simpleplot.subplots(figsize=(6, 4))
    ax.plot([0, 1, 2], [0, 1, 4])
    root = _parse(fig.to_svg())
    assert root.tag == NS + "svg"
    assert root.attrib["width"] == "600"   # 6in * 100dpi
    assert root.attrib["height"] == "400"


def test_line_becomes_single_path():
    fig, ax = simpleplot.subplots()
    ax.plot(np.linspace(0, 1, 500), np.linspace(0, 1, 500))
    root = _parse(fig.to_svg())
    # One <path> for the whole 500-point series -- not 500 nodes.
    assert len(root.findall(".//" + NS + "path")) == 1


def test_nan_splits_path_into_subpaths():
    fig, ax = simpleplot.subplots()
    y = np.array([0.0, 1.0, np.nan, 2.0, 3.0])
    ax.plot([0, 1, 2, 3, 4], y)
    d = _parse(fig.to_svg()).find(".//" + NS + "path").attrib["d"]
    assert d.count("M") == 2  # gap creates two move-to segments


def test_scatter_emits_constant_size_marker_dots():
    fig, ax = simpleplot.subplots()
    ax.scatter([0, 1, 2], [0, 1, 2])
    root = _parse(fig.to_svg())
    # Single color/size scatter -> one round-capped marker path with 3 dots.
    g = [e for e in root.iter(NS + "g")
         if e.get("class") == "simpleplot-series"][0]
    path = g.find(NS + "path")
    assert path is not None
    assert path.get("stroke-linecap") == "round"
    assert path.get("d").count("M") == 3   # three points


def _element_counts(svg):
    root = _parse(svg)
    return (
        len(root.findall(".//" + NS + "image")),
        len(root.findall(".//" + NS + "rect")),
    )


def test_pcolormesh_is_one_image_and_o1_nodes():
    # One embedded <image>, and node count must NOT scale with mesh size.
    small_fig, small_ax = simpleplot.subplots()
    small_ax.pcolormesh(np.random.rand(10, 10))
    big_fig, big_ax = simpleplot.subplots()
    big_ax.pcolormesh(np.random.rand(400, 400))

    small_images, small_rects = _element_counts(small_fig.to_svg())
    big_images, big_rects = _element_counts(big_fig.to_svg())

    assert small_images == big_images == 1
    assert small_rects == big_rects  # O(1): 160,000 cells add zero nodes


def test_colorbar_adds_second_image():
    fig, ax = simpleplot.subplots()
    m = ax.pcolormesh(np.random.rand(20, 20))
    fig.colorbar(m, ax=ax)
    assert len(_parse(fig.to_svg()).findall(".//" + NS + "image")) == 2


def test_labels_and_title_present():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.set_title("hello")
    texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    assert "time" in texts and "value" in texts and "hello" in texts


def test_xml_special_chars_escaped():
    fig, ax = simpleplot.subplots()
    ax.set_title("a < b & c > d")
    svg = fig.to_svg()
    assert "&lt;" in svg and "&amp;" in svg and "&gt;" in svg
    _parse(svg)  # still well-formed


def test_save_svg(tmp_path):
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "out.svg"
    fig.save(str(p))
    assert p.exists()
    _parse(p.read_text(encoding="utf-8"))


def test_save_html_interactive_includes_script(tmp_path):
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.legend()
    p = tmp_path / "out.html"
    fig.save(str(p), interactive=True)
    html = p.read_text(encoding="utf-8")
    assert "<script>" in html
    assert 'id="simpleplot-svg"' in html
    assert "viewBox" in html


def test_static_html_has_no_script():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    assert "<script>" not in fig.to_html(interactive=False)


def test_save_rejects_unknown_extension(tmp_path):
    fig, _ = simpleplot.subplots()
    with pytest.raises(ValueError):
        fig.save(str(tmp_path / "out.xyz"))


def test_save_png(tmp_path):
    pytest.importorskip("PIL")
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1, 2], [0, 1, 4]); ax.scatter([0, 1], [0, 1])
    ax.set_title("t"); ax.grid(True); ax.legend()
    p = tmp_path / "o.png"
    fig.savefig(str(p))                       # matplotlib-style alias
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_pdf(tmp_path):
    pytest.importorskip("svglib")
    pytest.importorskip("reportlab")
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "o.pdf"
    fig.save(str(p))
    assert p.read_bytes()[:5] == b"%PDF-"


def test_bar_and_barh_render_rects():
    fig, axes = simpleplot.subplots(1, 2)
    axes[0].bar([0, 1, 2], [3, 5, 2])
    axes[1].barh([0, 1, 2], [3, 5, 2])
    rects = _parse(fig.to_svg()).findall(".//" + NS + "rect")
    assert len(rects) >= 6   # 3 bars in each axes, plus backgrounds/spines


def test_hist_returns_counts_and_edges():
    fig, ax = simpleplot.subplots()
    counts, edges, bars = ax.hist([1, 1, 2, 3, 3, 3], bins=3)
    assert counts.sum() == 6
    assert len(edges) == 4
    assert len(_parse(fig.to_svg()).findall(".//" + NS + "rect")) >= 3


def test_fill_between_closed_path():
    fig, ax = simpleplot.subplots()
    ax.fill_between([0, 1, 2], [0, 1, 0], [1, 2, 1])
    paths = _parse(fig.to_svg()).findall(".//" + NS + "path")
    assert any(p.attrib["d"].endswith("Z") for p in paths)  # filled polygon


def test_imshow_is_one_image():
    fig, ax = simpleplot.subplots()
    ax.imshow(np.arange(9, dtype=float).reshape(3, 3))
    assert len(_parse(fig.to_svg()).findall(".//" + NS + "image")) == 1


def test_pie_draws_wedges_and_hides_axis():
    fig, ax = simpleplot.subplots()
    ax.pie([35, 25, 40], labels=["a", "b", "c"])
    assert ax._axis_off is True
    root = _parse(fig.to_svg())
    wedges = [p for p in root.findall(".//" + NS + "path")
              if "A" in p.attrib.get("d", "")]
    assert len(wedges) == 3


def test_stem_step_errorbar_render_and_wellformed():
    fig, axes = simpleplot.subplots(1, 3)
    axes[0].stem([0, 1, 2, 3], [1, 3, 2, 4])
    axes[1].step([0, 1, 2, 3], [1, 3, 2, 4], where="mid")
    axes[2].errorbar([0, 1, 2], [1, 2, 1], yerr=0.2, xerr=0.1)
    root = _parse(fig.to_svg())              # parses => well-formed
    assert len(root.findall(".//" + NS + "circle")) >= 4  # stem/errorbar markers


def test_axis_off_hides_spines_and_ticks():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("kept")
    before = len(_parse(fig.to_svg()).findall(".//" + NS + "text"))
    ax.set_axis_off()
    after_texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    assert "kept" in after_texts           # title stays
    assert len(after_texts) < before       # tick labels gone


def test_set_aspect_equal_shrinks_box_to_square(monkeypatch):
    from simpleplot.svg import axes_metadata

    fig, ax = simpleplot.subplots(figsize=(8, 4))   # wide figure
    ax.plot([0, 10], [0, 10])                  # equal data spans
    ax.set_aspect("equal")
    m = axes_metadata(fig)[0]
    assert m["w"] == pytest.approx(m["h"], rel=1e-3)   # square box


def test_log_scale_emits_decade_ticks_and_metadata():
    fig, ax = simpleplot.subplots()
    ax.plot([1, 10, 100, 1000], [1, 2, 3, 4])
    ax.set_xscale("log")
    from simpleplot.svg import axes_metadata
    assert axes_metadata(fig)[0]["xscale"] == "log"
    texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    # Decade labels present on the log x-axis.
    assert "10" in texts and "100" in texts and "1000" in texts


def test_set_xscale_rejects_bad_value():
    _, ax = simpleplot.subplots()
    with pytest.raises(ValueError):
        ax.set_xscale("linlog")


def test_text_and_annotate_render():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "hello", rotation=30)
    ax.annotate("pt", xy=(1, 1), xytext=(0.2, 0.8), arrowprops={"color": "#d62728"})
    root = _parse(fig.to_svg())
    texts = [t.text for t in root.findall(".//" + NS + "text")]
    assert "hello" in texts and "pt" in texts
    hello = [t for t in root.findall(".//" + NS + "text") if t.text == "hello"][0]
    assert "rotate" in (hello.get("transform") or "")   # rotated label


def test_tight_layout_returns_self_and_relayouts():
    fig, axes = simpleplot.subplots(2, 2, figsize=(6, 5))
    for ax in axes.ravel():
        ax.plot([0, 1], [0, 1]); ax.set_title("t"); ax.set_xlabel("x")
    before = [tuple(ax._rect) for ax in axes.ravel()]
    assert fig.tight_layout() is fig
    after = [tuple(ax._rect) for ax in axes.ravel()]
    assert before != after


def test_tight_layout_accounts_for_ylabel():
    f1, a1 = simpleplot.subplots(figsize=(6, 4)); a1.plot([0, 1], [0, 1]); f1.tight_layout()
    f2, a2 = simpleplot.subplots(figsize=(6, 4))
    a2.plot([0, 1], [0, 1]); a2.set_ylabel("value"); f2.tight_layout()
    assert a2._rect[0] > a1._rect[0]   # a y label widens the left margin


def test_figure_level_suptitle_and_labels():
    fig, axes = simpleplot.subplots(2, 2)
    for ax in axes.ravel():
        ax.plot([0, 1], [0, 1])
    fig.suptitle("Global Title")
    fig.supxlabel("shared x")
    fig.supylabel("shared y")
    texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    assert "Global Title" in texts
    assert "shared x" in texts
    assert "shared y" in texts


def test_repr_svg_for_jupyter():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    assert fig._repr_svg_().startswith("<svg")


def test_axvline_is_dashed_and_full_height():
    fig, ax = simpleplot.subplots(figsize=(6, 4))
    ax.plot([0, 10], [0, 10])
    ax.axvline(5, linestyle="--")
    lines = _parse(fig.to_svg()).findall(".//" + NS + "line")
    vlines = [l for l in lines if l.get("stroke-dasharray")
              and l.get("x1") == l.get("x2")]
    assert vlines, "expected a dashed vertical line"


def test_axes_metadata_for_picking():
    from simpleplot.svg import axes_metadata

    fig, axes = simpleplot.subplots(1, 2)
    axes[0].plot([0, 10], [0, 5])
    m = axes[1].pcolormesh(np.zeros((4, 4)))
    fig.colorbar(m, ax=axes[1])
    meta = axes_metadata(fig)
    # Two data axes; the colorbar axes is excluded.
    assert len(meta) == 2
    for entry in meta.values():
        assert {"x", "y", "w", "h", "xmin", "xmax", "ymin", "ymax",
                "xscale", "yscale", "xinv", "yinv"} <= set(entry)


def _meta_to_pixel(entry, dx, dy):
    """Data -> pixel exactly as the client's toPixel() does, from metadata alone.

    Mirrors the ``edges()``/``toPixel()`` pair in ``_interactive.py``; kept in
    step with it so a drift between the metadata contract and the renderer
    shows up here rather than as a mis-picked point in the browser.
    """
    fx = math.log10 if entry["xscale"] == "log" else (lambda v: v)
    fy = math.log10 if entry["yscale"] == "log" else (lambda v: v)
    fx0, fx1 = fx(entry["xmin"]), fx(entry["xmax"])
    fy0, fy1 = fy(entry["ymin"]), fy(entry["ymax"])
    if entry["xinv"]:
        fx0, fx1 = fx1, fx0
    if entry["yinv"]:
        fy0, fy1 = fy1, fy0
    return (entry["x"] + (fx(dx) - fx0) / (fx1 - fx0) * entry["w"],
            entry["y"] + (fy1 - fy(dy)) / (fy1 - fy0) * entry["h"])


@pytest.mark.parametrize("invert_x", [False, True])
@pytest.mark.parametrize("invert_y", [False, True])
@pytest.mark.parametrize("scale", ["linear", "log"])
def test_pick_metadata_matches_renderer_transform(invert_x, invert_y, scale):
    """The pick metadata must place a datum where the renderer draws it.

    Point picking maps a click back to data using only ``axes_metadata``, so if
    that disagrees with the renderer's transform every pick lands on the wrong
    point. Inverted axes regressed exactly this way: the renderer swaps the
    limits it feeds LinearTransform, and the metadata has to say so.
    """
    from simpleplot.svg import _effective_rect, _pixel_rect, axes_metadata
    from simpleplot.transform import LinearTransform

    data = [1.0, 10.0, 100.0, 1000.0] if scale == "log" else [0.0, 1.0, 2.0, 3.0]
    fig, ax = simpleplot.subplots()
    ax.plot(data, data)
    ax.set_xscale(scale)
    ax.set_yscale(scale)
    if invert_x:
        ax.invert_xaxis()
    if invert_y:
        ax.invert_yaxis()

    entry = axes_metadata(fig)[0]

    # The transform the renderer itself uses (see _render_axes).
    dpi = 100
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    rect = _effective_rect(ax, *_pixel_rect(ax, fig.figsize[0] * dpi,
                                            fig.figsize[1] * dpi),
                           (xmin, xmax), (ymin, ymax))
    tr = LinearTransform((xmax, xmin) if ax._xinverted else (xmin, xmax),
                         (ymax, ymin) if ax._yinverted else (ymin, ymax),
                         rect, xscale=ax._xscale, yscale=ax._yscale)

    for dx, dy in zip(data, data):
        px, py = _meta_to_pixel(entry, dx, dy)
        assert px == pytest.approx(float(tr.x(dx)), abs=1e-3)
        assert py == pytest.approx(float(tr.y(dy)), abs=1e-3)


def test_interactive_html_embeds_pick_metadata():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    html = fig.to_html(interactive=True)
    assert 'id="simpleplot-meta"' in html
    assert 'id="simpleplot-pick"' in html
    assert 'application/json' in html
    # Static output must not carry the metadata payload.
    assert 'simpleplot-meta' not in fig.to_html(interactive=False)


def test_pick_data_includes_z_c_and_extra_dims():
    from simpleplot.svg import pick_data

    fig, axes = simpleplot.subplots(1, 3)
    axes[0].pcolormesh(np.arange(12, dtype=float).reshape(3, 4))
    axes[1].scatter([0, 1, 2], [0, 1, 2], c=[10.0, 20.0, 30.0],
                    values={"temp": [1.0, 2.0, 3.0]})
    axes[2].plot([0, 1], [0, 1], values={"z": [5.0, 6.0]})
    pd = pick_data(fig)

    # Mesh: z grid embedded, row-major, row 0 = ymin.
    mesh = pd[0]["meshes"][0]
    assert mesh["shape"] == [3, 4]
    assert mesh["z"][0] == 0.0 and mesh["z"][-1] == 11.0
    assert mesh["name"] == "z"

    # Scatter: tagged kind + c auto-included plus the extra 'temp' dimension.
    assert pd[1]["series"][0]["kind"] == "scatter"
    svals = pd[1]["series"][0]["vals"]
    assert svals["c"] == [10.0, 20.0, 30.0]
    assert svals["temp"] == [1.0, 2.0, 3.0]

    # Line: tagged kind + attached z per vertex.
    assert pd[2]["series"][0]["kind"] == "line"
    assert pd[2]["series"][0]["vals"]["z"] == [5.0, 6.0]


def test_round_list_matches_python_rounding():
    # The vectorized _rl replaced a per-element round(float(v), nd) comprehension.
    # It agrees with it to within one quantum -- the two can differ only on exact
    # half-way ties at the last digit (numpy multiplies-then-rounds; Python rounds
    # the decimal). That last-digit difference is irrelevant for a pick readout.
    from simpleplot.svg import _rl

    rng = np.random.default_rng(0)
    a = rng.standard_normal(2000) * 50.0
    for nd in (6, 4, 3):
        got = np.asarray(_rl(a, nd))
        ref = np.asarray([round(float(v), nd) for v in a])
        assert got.shape == ref.shape
        assert np.allclose(got, ref, atol=10.0 ** -nd)


def test_pick_precision_rounds_and_shrinks_payload():
    from simpleplot.svg import pick_data

    fig, ax = simpleplot.subplots()
    ax.pcolormesh(np.linspace(0, 1, 400).reshape(20, 20))
    z6 = pick_data(fig, precision=6)[0]["meshes"][0]["z"]
    z2 = pick_data(fig, precision=2)[0]["meshes"][0]["z"]

    # Coarser precision actually rounds the embedded values...
    assert z2 == [round(v, 2) for v in z6]
    # ...and a lower-precision interactive HTML is no larger than the default.
    assert len(fig.to_html(pick_precision=2)) <= len(fig.to_html(pick_precision=6))


def test_plot_frames_registers_slider_and_embeds_frames():
    from simpleplot.svg import frame_data

    fig, axes = simpleplot.subplots(1, 2)
    Y = np.sin(np.linspace(0, 6, 5)[:, None] + np.linspace(0, 1, 10)[None, :])
    axes[0].plot_frames(np.linspace(0, 1, 10), Y, slider_values=range(5),
                        slider_label="t")
    axes[1].plot_frames(np.linspace(0, 1, 10), Y * 2)  # shares the slider

    # Both share the global "main" unit (linked).
    assert set(fig._sliders) == {"main"}
    assert fig._sliders["main"]["n"] == 5
    assert fig._sliders["main"]["label"] == "t"
    assert fig._sliders["main"]["global"] is True

    frames = frame_data(fig)
    assert set(frames) == {0, 1}
    entry = frames[0][0]
    assert entry["shared_x"] is True
    assert entry["unit"] == "main"
    assert len(entry["Y"]) == 5 and len(entry["Y"][0]) == 10

    html = fig.to_html(interactive=True)
    assert 'id="simpleplot-frames"' in html and 'id="simpleplot-sliders"' in html
    # Static SVG shows a frame but carries no slider payload.
    assert "simpleplot-frameline" in fig.to_svg()
    assert "simpleplot-sliders" not in fig.to_html(interactive=False)


def test_shared_false_gives_each_axes_its_own_docked_unit():
    from simpleplot.svg import frame_data

    fig, axes = simpleplot.subplots(1, 3)
    Y = np.zeros((4, 6))
    axes[0].plot_frames(np.arange(6), Y)                    # shared -> "main"
    axes[1].plot_frames(np.arange(6), Y)                    # shared -> "main"
    axes[2].plot_frames(np.arange(6), np.zeros((9, 6)),     # docked -> "ax2"
                        shared=False, slider_label="z")

    assert fig._sliders["main"]["global"] is True
    assert fig._sliders["ax2"]["global"] is False
    assert fig._sliders["ax2"]["axes"] == 2
    assert fig._sliders["ax2"]["n"] == 9

    units = {e["unit"] for entries in frame_data(fig).values() for e in entries}
    assert units == {"main", "ax2"}


def test_connection_index_shared_across_axes():
    # Same slider_group under shared=False -> separate docked units, same index.
    fig, axes = simpleplot.subplots(1, 2)
    axes[0].plot_frames(np.arange(5), np.zeros((6, 5)), shared=False,
                        slider_group="t", slider_label="t")
    axes[1].plot_frames(np.arange(5), np.zeros((6, 5)), shared=False,
                        slider_group="t", slider_label="t")
    assert fig._sliders["ax0"]["index"] == "t"
    assert fig._sliders["ax1"]["index"] == "t"
    # Distinct docked units (one per axes), not a single merged slider.
    assert fig._sliders["ax0"]["axes"] == 0 and fig._sliders["ax1"]["axes"] == 1


def test_connection_index_requires_matching_n_frames():
    fig, axes = simpleplot.subplots(1, 2)
    axes[0].plot_frames(np.arange(5), np.zeros((6, 5)), shared=False, slider_group="t")
    with pytest.raises(ValueError):
        axes[1].plot_frames(np.arange(5), np.zeros((8, 5)), shared=False, slider_group="t")


def test_independent_slider_allows_different_n_frames():
    # A docked slider with its own index need not match the global n_frames.
    fig, axes = simpleplot.subplots(1, 2)
    axes[0].plot_frames([0, 1, 2], np.zeros((4, 3)))               # main, n=4
    axes[1].plot_frames([0, 1, 2], np.zeros((7, 3)), shared=False)  # ax1, n=7
    assert set(fig._sliders) == {"main", "ax1"}


def test_plot_frames_requires_matching_n_frames():
    fig, axes = simpleplot.subplots(1, 2)
    axes[0].plot_frames([0, 1, 2], np.zeros((4, 3)))
    with pytest.raises(ValueError):
        axes[1].plot_frames([0, 1, 2], np.zeros((6, 3)))  # different n_frames


def test_plot_frames_rejects_1d():
    _, ax = simpleplot.subplots()
    with pytest.raises(ValueError):
        ax.plot_frames([0, 1, 2], [0, 1, 2])  # Y must be 2-D


def test_interactive_html_includes_marker_extraction():
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    html = fig.to_html(interactive=True)
    assert "simpleplotGetMarkers" in html   # programmatic extraction hook
    assert "Extract" in html           # toolbar button


def test_show_returns_extracted_markers(monkeypatch):
    import sys

    captured = {}

    class FakeWebview:
        def create_window(self, title, html=None, js_api=None, width=None, height=None):
            captured["api"] = js_api

        def start(self):
            # Simulate the user clicking Extract in the native window.
            captured["api"].extract([{"x": 1.0, "y": 2.0, "z": 9.0},
                                     {"x": 3.0, "y": 4.0, "z": 8.0}])

    monkeypatch.setitem(sys.modules, "webview", FakeWebview())
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    markers = fig.show()
    assert markers == [{"x": 1.0, "y": 2.0, "z": 9.0},
                       {"x": 3.0, "y": 4.0, "z": 8.0}]


def test_wait_for_extract_closes_window_and_returns(monkeypatch):
    import sys

    class FakeWindow:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    state = {}

    class FakeWebview:
        def create_window(self, title, html=None, js_api=None, width=None, height=None):
            state["api"] = js_api
            state["win"] = FakeWindow()
            return state["win"]

        def start(self):
            # User clicks Extract -> JS calls the bridge, which must close it.
            state["api"].extract([{"x": 7.0, "y": 8.0}])

    monkeypatch.setitem(sys.modules, "webview", FakeWebview())
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])

    # wait_extract injects the close-on-extract flag assignment into the page.
    assert "SIMPLEPLOT_WAIT_EXTRACT=true" in fig.to_html(interactive=True, wait_extract=True)
    assert "SIMPLEPLOT_WAIT_EXTRACT=true" not in fig.to_html(interactive=True)

    markers = fig.show(wait_for_extract=True)
    assert markers == [{"x": 7.0, "y": 8.0}]
    assert state["win"].destroyed is True   # Extract closed the window


def test_wait_for_extract_without_gui_raises(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_webview(name, *args, **kwargs):
        if name == "webview":
            raise ImportError("no pywebview")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_webview)
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1], [0, 1])
    with pytest.raises(RuntimeError):
        fig.show(wait_for_extract=True)


def test_html_payloads_cannot_break_out_of_their_script_block():
    """An HTML parser ends a <script> at the first "</script" in its text, so a
    label carrying one would close the JSON payload and run what follows."""
    import json

    evil = '</script><script>window.PWNED=1</script>'
    fig, ax = simpleplot.subplots()
    ax.plot([0, 1, 2], [0, 1, 2], values={evil: np.arange(3.0)})
    ax.plot_frames(np.arange(3), np.zeros((2, 3)), slider_label=evil)
    html = fig.to_html(interactive=True)

    assert "</script><script>window.PWNED=1</script>" not in html
    assert "\\u003c/script\\u003e" in html          # escaped, still inside JSON

    # Every payload block is intact and still parses back to the original text.
    for pid in ("simpleplot-pick", "simpleplot-sliders"):
        start = html.index('id="%s">' % pid) + len('id="%s">' % pid)
        end = html.index("</script>", start)
        assert evil in json.dumps(json.loads(html[start:end]))


def test_pick_data_omits_oversized_series_and_meshes():
    from simpleplot.svg import pick_data

    fig, axes = simpleplot.subplots(1, 2)
    axes[0].plot(np.arange(30000.0), np.arange(30000.0))  # over max_points
    axes[1].pcolormesh(np.zeros((300, 300)))              # over max_mesh_cells
    pd = pick_data(fig, max_points=20000, max_mesh_cells=60000)
    assert pd.get(0, {"series": []})["series"] == [] or 0 not in pd
    assert pd.get(1, {"meshes": []})["meshes"] == [] or 1 not in pd
