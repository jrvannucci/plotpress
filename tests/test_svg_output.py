"""SVG/HTML serialization: well-formedness, structure, and file output."""

import json
import math
import re
import os
import time
import xml.etree.ElementTree as ET

import numpy as np
import pytest

import plotpress

NS = "{http://www.w3.org/2000/svg}"


def _parse(svg):
    return ET.fromstring(svg)


def test_svg_is_well_formed_and_sized():
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.plot([0, 1, 2], [0, 1, 4])
    root = _parse(fig.to_svg())
    assert root.tag == NS + "svg"
    assert root.attrib["width"] == "600"   # 6in * 100dpi
    assert root.attrib["height"] == "400"


def test_line_becomes_single_path():
    fig, ax = plotpress.subplots()
    ax.plot(np.linspace(0, 1, 500), np.linspace(0, 1, 500))
    root = _parse(fig.to_svg())
    # One <path> for the whole 500-point series -- not 500 nodes.
    assert len(root.findall(".//" + NS + "path")) == 1


def test_nan_splits_path_into_subpaths():
    fig, ax = plotpress.subplots()
    y = np.array([0.0, 1.0, np.nan, 2.0, 3.0])
    ax.plot([0, 1, 2, 3, 4], y)
    d = _parse(fig.to_svg()).find(".//" + NS + "path").attrib["d"]
    assert d.count("M") == 2  # gap creates two move-to segments


def test_scatter_emits_constant_size_marker_dots():
    fig, ax = plotpress.subplots()
    ax.scatter([0, 1, 2], [0, 1, 2])
    root = _parse(fig.to_svg())
    # Single color/size scatter -> one round-capped marker path with 3 dots.
    g = [e for e in root.iter(NS + "g")
         if e.get("class") == "plotpress-series"][0]
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
    small_fig, small_ax = plotpress.subplots()
    small_ax.pcolormesh(np.random.rand(10, 10))
    big_fig, big_ax = plotpress.subplots()
    big_ax.pcolormesh(np.random.rand(400, 400))

    small_images, small_rects = _element_counts(small_fig.to_svg())
    big_images, big_rects = _element_counts(big_fig.to_svg())

    assert small_images == big_images == 1
    assert small_rects == big_rects  # O(1): 160,000 cells add zero nodes


def test_colorbar_adds_second_image():
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(np.random.rand(20, 20))
    fig.colorbar(m, ax=ax)
    assert len(_parse(fig.to_svg()).findall(".//" + NS + "image")) == 2


def test_labels_and_title_present():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.set_title("hello")
    texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    assert "time" in texts and "value" in texts and "hello" in texts


def test_xml_special_chars_escaped():
    fig, ax = plotpress.subplots()
    ax.set_title("a < b & c > d")
    svg = fig.to_svg()
    assert "&lt;" in svg and "&amp;" in svg and "&gt;" in svg
    _parse(svg)  # still well-formed


def test_save_svg(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "out.svg"
    fig.save(str(p))
    assert p.exists()
    _parse(p.read_text(encoding="utf-8"))


def test_save_html_interactive_includes_script(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.legend()
    p = tmp_path / "out.html"
    fig.save(str(p), interactive=True)
    html = p.read_text(encoding="utf-8")
    assert "<script>" in html
    assert 'id="plotpress-svg"' in html
    assert "viewBox" in html


def test_static_html_has_no_script():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    assert "<script>" not in fig.to_html(interactive=False)


def test_save_rejects_unknown_extension(tmp_path):
    fig, _ = plotpress.subplots()
    with pytest.raises(ValueError):
        fig.save(str(tmp_path / "out.xyz"))


def test_save_png(tmp_path):
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4]); ax.scatter([0, 1], [0, 1])
    ax.set_title("t"); ax.grid(True); ax.legend()
    p = tmp_path / "o.png"
    fig.savefig(str(p))                       # matplotlib-style alias
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_pdf(tmp_path):
    pytest.importorskip("svglib")
    pytest.importorskip("reportlab")
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "o.pdf"
    fig.save(str(p))
    assert p.read_bytes()[:5] == b"%PDF-"


def test_save_gif(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    fig, ax = plotpress.subplots()
    x = np.linspace(0, 2 * np.pi, 40)
    t = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    ax.plot_frames(x, np.sin(x[None, :] - t[:, None]))
    p = tmp_path / "o.gif"
    fig.save(str(p), fps=5)

    assert p.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
    im = Image.open(str(p))
    assert im.n_frames == 6
    assert im.info["duration"] == 200          # 1000 / 5 fps
    assert im.info["loop"] == 0                # loops forever

    im.seek(0)
    first = np.array(im.convert("RGB"))
    im.seek(3)
    later = np.array(im.convert("RGB"))
    assert not np.array_equal(first, later)    # the sine wave actually moved


def test_save_gif_requires_plot_frames(tmp_path):
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])                    # no plot_frames() series
    with pytest.raises(ValueError, match="plot_frames"):
        fig.save(str(tmp_path / "o.gif"))


def test_save_gif_animates_requested_slider_unit_only(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    fig, axes = plotpress.subplots(1, 2)
    x = np.arange(5)
    axes[0].plot_frames(x, np.arange(4 * 5).reshape(4, 5).astype(float))  # "main", n=4
    axes[1].plot_frames(x, np.arange(3 * 5).reshape(3, 5).astype(float),   # "ax1", n=3
                        shared=False)

    p_main = tmp_path / "main.gif"
    fig.save(str(p_main), slider_unit="main")
    assert Image.open(str(p_main)).n_frames == 4

    p_ax1 = tmp_path / "ax1.gif"
    fig.save(str(p_ax1), slider_unit="ax1")
    assert Image.open(str(p_ax1)).n_frames == 3


def test_bar_and_barh_render_rects():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].bar([0, 1, 2], [3, 5, 2])
    axes[1].barh([0, 1, 2], [3, 5, 2])
    rects = _parse(fig.to_svg()).findall(".//" + NS + "rect")
    assert len(rects) >= 6   # 3 bars in each axes, plus backgrounds/spines


def test_hist_returns_counts_and_edges():
    fig, ax = plotpress.subplots()
    counts, edges, bars = ax.hist([1, 1, 2, 3, 3, 3], bins=3)
    assert counts.sum() == 6
    assert len(edges) == 4
    assert len(_parse(fig.to_svg()).findall(".//" + NS + "rect")) >= 3


def test_fill_between_closed_path():
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1, 2], [0, 1, 0], [1, 2, 1])
    paths = _parse(fig.to_svg()).findall(".//" + NS + "path")
    assert any(p.attrib["d"].endswith("Z") for p in paths)  # filled polygon


@pytest.mark.parametrize("y1, y2", [
    ([0, 1, 0], [1, 2, 1]),      # both arrays
    ([0, 1, 0], 0.5),            # scalar upper bound
    (0.5, [1, 2, 1]),            # scalar *lower* bound -- used to crash
    (0.0, 1.0),                  # both scalar
])
def test_fill_between_broadcasts_either_bound(y1, y2):
    fig, ax = plotpress.subplots()
    ax.fill_between([0, 1, 2], y1, y2)
    paths = _parse(fig.to_svg()).findall(".//" + NS + "path")
    assert any(p.attrib["d"].endswith("Z") for p in paths)


def _no_nan_geometry(fig):
    """SVG with base64 payloads stripped contains no literal NaN coordinate."""
    svg = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "IMG", fig.to_svg())
    return re.search(r"(?i)(?<![a-z0-9])nan(?![a-z0-9])", svg) is None


def test_bars_render_on_a_log_axis():
    """A bar sits on zero, which a log axis cannot map.

    Transforming the baseline gave NaN, so the whole rectangle's geometry became
    NaN and the series vanished -- a log-scaled histogram drew an empty panel.
    """
    fig, ax = plotpress.subplots()
    ax.bar([1, 2, 3], [10, 100, 1000])
    ax.set_yscale("log")
    ax.set_ylim(1, 2000)
    assert _no_nan_geometry(fig)
    rects = _parse(fig.to_svg()).findall(".//" + NS + "g/" + NS + "rect")
    assert len(rects) >= 3


def test_empty_histogram_bins_on_a_log_axis():
    fig, ax = plotpress.subplots()
    ax.hist([0.0, 0.0, 0.05, 5.0], bins=12, density=True)
    ax.set_yscale("log")
    assert _no_nan_geometry(fig)


def test_errorbar_below_zero_on_a_log_axis():
    """Whiskers reaching past zero clamp to the frame; unmappable dots are dropped."""
    fig, ax = plotpress.subplots()
    ax.errorbar([1, 2, 3], [1.0, 0.1, 0.01], yerr=[0.5, 0.5, 0.5])
    ax.set_yscale("log")
    ax.set_ylim(1e-3, 10)
    assert _no_nan_geometry(fig)


def test_imshow_is_one_image():
    fig, ax = plotpress.subplots()
    ax.imshow(np.arange(9, dtype=float).reshape(3, 3))
    assert len(_parse(fig.to_svg()).findall(".//" + NS + "image")) == 1


def test_pie_draws_wedges_and_hides_axis():
    fig, ax = plotpress.subplots()
    ax.pie([35, 25, 40], labels=["a", "b", "c"])
    assert ax._axis_off is True
    root = _parse(fig.to_svg())
    wedges = [p for p in root.findall(".//" + NS + "path")
              if "A" in p.attrib.get("d", "")]
    assert len(wedges) == 3


def test_stem_step_errorbar_render_and_wellformed():
    fig, axes = plotpress.subplots(1, 3)
    axes[0].stem([0, 1, 2, 3], [1, 3, 2, 4])
    axes[1].step([0, 1, 2, 3], [1, 3, 2, 4], where="mid")
    axes[2].errorbar([0, 1, 2], [1, 2, 1], yerr=0.2, xerr=0.1)
    root = _parse(fig.to_svg())              # parses => well-formed
    assert len(root.findall(".//" + NS + "circle")) >= 4  # stem/errorbar markers


def test_axis_off_hides_spines_and_ticks():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("kept")
    before = len(_parse(fig.to_svg()).findall(".//" + NS + "text"))
    ax.set_axis_off()
    after_texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    assert "kept" in after_texts           # title stays
    assert len(after_texts) < before       # tick labels gone


def test_set_aspect_equal_shrinks_box_to_square(monkeypatch):
    from plotpress.svg import axes_metadata

    fig, ax = plotpress.subplots(figsize=(8, 4))   # wide figure
    ax.plot([0, 10], [0, 10])                  # equal data spans
    ax.set_aspect("equal")
    m = axes_metadata(fig)[0]
    assert m["w"] == pytest.approx(m["h"], rel=1e-3)   # square box


def test_log_scale_emits_decade_ticks_and_metadata():
    fig, ax = plotpress.subplots()
    ax.plot([1, 10, 100, 1000], [1, 2, 3, 4])
    ax.set_xscale("log")
    from plotpress.svg import axes_metadata
    assert axes_metadata(fig)[0]["xscale"] == "log"
    texts = [t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]
    # Decade labels present on the log x-axis.
    assert "10" in texts and "100" in texts and "1000" in texts


def test_set_xscale_rejects_bad_value():
    _, ax = plotpress.subplots()
    with pytest.raises(ValueError):
        ax.set_xscale("linlog")


def test_text_and_annotate_render():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "hello", rotation=30)
    ax.annotate("pt", xy=(1, 1), xytext=(0.2, 0.8), arrowprops={"color": "#d62728"})
    root = _parse(fig.to_svg())
    texts = [t.text for t in root.findall(".//" + NS + "text")]
    assert "hello" in texts and "pt" in texts
    hello = [t for t in root.findall(".//" + NS + "text") if t.text == "hello"][0]
    assert "rotate" in (hello.get("transform") or "")   # rotated label


def test_tight_layout_returns_self_and_relayouts():
    fig, axes = plotpress.subplots(2, 2, figsize=(6, 5))
    for ax in axes.ravel():
        ax.plot([0, 1], [0, 1]); ax.set_title("t"); ax.set_xlabel("x")
    before = [tuple(ax._rect) for ax in axes.ravel()]
    assert fig.tight_layout() is fig
    after = [tuple(ax._rect) for ax in axes.ravel()]
    assert before != after


def test_tight_layout_accounts_for_ylabel():
    f1, a1 = plotpress.subplots(figsize=(6, 4)); a1.plot([0, 1], [0, 1]); f1.tight_layout()
    f2, a2 = plotpress.subplots(figsize=(6, 4))
    a2.plot([0, 1], [0, 1]); a2.set_ylabel("value"); f2.tight_layout()
    assert a2._rect[0] > a1._rect[0]   # a y label widens the left margin


def test_figure_level_suptitle_and_labels():
    fig, axes = plotpress.subplots(2, 2)
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
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    assert fig._repr_svg_().startswith("<svg")


def test_axvline_is_dashed_and_full_height():
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.plot([0, 10], [0, 10])
    ax.axvline(5, linestyle="--")
    lines = _parse(fig.to_svg()).findall(".//" + NS + "line")
    vlines = [l for l in lines if l.get("stroke-dasharray")
              and l.get("x1") == l.get("x2")]
    assert vlines, "expected a dashed vertical line"


def test_axes_metadata_for_picking():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 10], [0, 5])
    m = axes[1].pcolormesh(np.zeros((4, 4)))
    fig.colorbar(m, ax=axes[1])
    meta = axes_metadata(fig)
    # Two data axes; the colorbar axes is excluded.
    assert len(meta) == 2
    for entry in meta.values():
        assert {"x", "y", "w", "h", "xmin", "xmax", "ymin", "ymax",
                "xscale", "yscale", "xinv", "yinv"} <= set(entry)


def test_axes_metadata_carries_title_for_extract():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[0].set_title("Sensor A")
    axes[1].plot([0, 1], [1, 0])   # no title
    meta = axes_metadata(fig)
    assert meta[0]["title"] == "Sensor A"
    assert meta[1]["title"] == ""


def test_axes_metadata_carries_pickable_flag():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    axes[1].set_pickable(False)
    meta = axes_metadata(fig)
    assert meta[0]["pickable"] is True
    assert meta[1]["pickable"] is False
    assert axes[0].get_pickable() is True
    assert axes[1].get_pickable() is False


def test_axes_metadata_carries_pick_context():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[0].set_pick_context(edge_color="#d62728")
    axes[0].set_pick_context(unit="V")   # accumulates, doesn't replace
    axes[1].plot([0, 1], [1, 0])
    meta = axes_metadata(fig)
    assert meta[0]["context"] == {"edge_color": "#d62728", "unit": "V"}
    assert meta[1]["context"] == {}
    assert axes[0].get_pick_context() == {"edge_color": "#d62728", "unit": "V"}


def test_axes_metadata_carries_xlabel_ylabel():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[0].set_xlabel("Time (s)")
    axes[0].set_ylabel("Amplitude (V)")
    axes[1].plot([0, 1], [1, 0])   # labels left unset
    meta = axes_metadata(fig)
    assert meta[0]["xlabel"] == "Time (s)"
    assert meta[0]["ylabel"] == "Amplitude (V)"
    assert meta[1]["xlabel"] == "" and meta[1]["ylabel"] == ""
    assert meta[0]["zlabel"] == ""   # no colorbar attached


def test_axes_metadata_carries_zlabel_from_colorbar():
    from plotpress.svg import axes_metadata

    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.zeros((4, 4)))
    fig.colorbar(mesh, ax=ax).set_title("power (dB)")
    assert axes_metadata(fig)[0]["zlabel"] == "power (dB)"


def test_axes_metadata_zlabel_from_shared_colorbar_reaches_every_parent():
    """A colorbar shared across several pcolormesh axes must report its label
    for *every* axes it covers, not just the one it happened to steal space
    from -- fig.colorbar(mesh, ax=[ax0, ax1, ax2]) is the documented way to
    build a shared bar over a grid of meshes."""
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 3, figsize=(9, 3))
    meshes = [ax.pcolormesh(np.full((4, 4), i), vmin=0, vmax=2)
              for i, ax in enumerate(axes)]
    fig.colorbar(meshes[0], ax=list(axes)).set_title("temperature (degC)")

    meta = axes_metadata(fig)
    # Three data axes plus the one shared colorbar axes -- the colorbar
    # itself must not appear as a fourth "data" entry.
    assert len(meta) == 3
    for i in range(3):
        assert meta[i]["zlabel"] == "temperature (degC)", (
            "axes %d did not get the shared colorbar's label" % i)

    # And the fully-embedded interactive payload must agree.
    html = fig.to_html(interactive=True)
    m = re.search(r'id="plotpress-meta">(.*?)</script>', html, re.S)
    payload = json.loads(m.group(1))
    for i in range(3):
        assert payload[str(i)]["zlabel"] == "temperature (degC)"


def test_axes_metadata_carries_tick_style_overrides():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[0].tick_params(axis="x", color="#d62728", labelsize=14)
    axes[0].tick_params(axis="y", color="#2ca02c")
    axes[0].minorticks_on()
    axes[0].tick_params(which="minor", width=2.0)
    axes[1].plot([0, 1], [1, 0])   # no overrides
    meta = axes_metadata(fig)

    ts0 = meta[0]["tick_style"]
    assert ts0["x"] == {"spine_color": "#d62728", "tick_label_size": 14}
    assert ts0["y"] == {"spine_color": "#2ca02c"}
    # tick_params(which='minor') with axis='both' (the default) writes both.
    assert ts0["xminor"] == {"tick_width": 2.0}
    assert ts0["yminor"] == {"tick_width": 2.0}

    ts1 = meta[1]["tick_style"]
    assert ts1 == {"x": None, "y": None, "xminor": None, "yminor": None}

    # And the embedded interactive payload must carry the same overrides, so
    # the client's pan/zoom tick-rebuild can reproduce them.
    html = fig.to_html(interactive=True)
    m = re.search(r'id="plotpress-meta">(.*?)</script>', html, re.S)
    payload = json.loads(m.group(1))
    assert payload["0"]["tick_style"]["x"] == {"spine_color": "#d62728", "tick_label_size": 14}


def test_axes_metadata_carries_minor_ticks_flag():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[0].minorticks_on()
    axes[1].plot([0, 1], [1, 0])
    meta = axes_metadata(fig)
    assert meta[0]["minor"] is True
    assert meta[1]["minor"] is False


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
    from plotpress.svg import _effective_rect, _pixel_rect, axes_metadata
    from plotpress.transform import LinearTransform

    data = [1.0, 10.0, 100.0, 1000.0] if scale == "log" else [0.0, 1.0, 2.0, 3.0]
    fig, ax = plotpress.subplots()
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
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    html = fig.to_html(interactive=True)
    assert 'id="plotpress-meta"' in html
    assert 'id="plotpress-pick"' in html
    assert 'application/json' in html
    # Static output must not carry the metadata payload.
    assert 'plotpress-meta' not in fig.to_html(interactive=False)


def test_interactive_html_pick_payload_survives_nan_and_inf():
    """A masked/missing measurement (NaN, or +-inf from a divide-by-zero) must
    not corrupt the embedded JSON. ``json.dumps``'s default ``allow_nan=True``
    emits bare ``NaN``/``Infinity``/``-Infinity`` tokens -- valid Python, not
    valid JSON -- so the browser's strict ``JSON.parse`` throws on the very
    first one and the *entire* interactive toolbar silently stops working, not
    just picking on the affected series. Real measurements have gaps (a
    masked heatmap region, a dropped-out channel) often enough that this has
    to hold generally, not just for the common finite case.
    """
    fig, (ax1, ax2) = plotpress.subplots(1, 2)
    ax1.plot([0, 1, 2, 3], [0.0, float("nan"), 2.0, float("inf")])
    Z = np.array([[0.0, np.nan], [np.nan, float("-inf")]])
    ax2.pcolormesh(Z)
    html = fig.to_html(interactive=True)

    def _reject_bare_constant(name):
        raise ValueError(
            "payload embeds a bare %r token -- not valid JSON, "
            "JSON.parse() would throw in the browser" % name)

    for pid in ("plotpress-meta", "plotpress-pick", "plotpress-style"):
        start = html.index('id="%s">' % pid) + len('id="%s">' % pid)
        end = html.index("</script>", start)
        json.loads(html[start:end], parse_constant=_reject_bare_constant)


def test_pick_data_includes_z_c_and_extra_dims():
    from plotpress.svg import pick_data

    fig, axes = plotpress.subplots(1, 3)
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


def test_downsample_grid_preserves_small_grids_and_shrinks_large_ones():
    from plotpress.svg import _downsample_grid

    small = np.arange(12.0).reshape(3, 4)
    assert _downsample_grid(small, max_cells=60000) is small  # untouched

    large = np.arange(300 * 300, dtype=float).reshape(300, 300)
    down = _downsample_grid(large, max_cells=60000)
    assert down.size <= 60000
    # A monotonic ramp downsamples to a coarser monotonic ramp -- the block
    # average preserves the overall trend, not just cell count.
    assert down[0, 0] < down[-1, -1]


def test_downsample_grid_with_masked_region_does_not_warn():
    """Regression: a block that's entirely NaN (e.g. land in an ocean field,
    or any masked/missing region) must not raise numpy's "Mean of empty
    slice" RuntimeWarning -- that's expected input, not a bug to surface on
    every large masked figure."""
    import warnings as _warnings

    from plotpress.svg import _downsample_grid

    large = np.full((300, 300), 1.0)
    large[:150, :150] = np.nan     # one whole quadrant masked out
    with _warnings.catch_warnings():
        _warnings.simplefilter("error")   # any warning fails the test
        down = _downsample_grid(large, max_cells=60000)
    assert down.size <= 60000
    assert np.isnan(down).any()     # the masked region stays NaN
    assert not np.isnan(down).all()  # the rest of the grid still has data


def test_contour_over_mesh_cap_still_reports_a_value():
    """Regression: a contour/mesh larger than max_mesh_cells used to be
    dropped from the pick payload entirely, so a click on a large field
    reported bare x/y with no data value -- exactly the case a "third
    dimension" plot type exists for."""
    from plotpress.svg import pick_data

    g = np.linspace(-3, 3, 300)
    X, Y = np.meshgrid(g, g)
    Z = np.sin(np.hypot(X, Y))

    fig, ax = plotpress.subplots()
    ax.contour(X, Y, Z)
    pd = pick_data(fig, max_mesh_cells=60000)
    meshes = pd[0]["meshes"]
    assert len(meshes) == 1
    ny, nx = meshes[0]["shape"]
    assert ny * nx <= 60000
    assert len(meshes[0]["z"]) == ny * nx
    assert any(v != 0 for v in meshes[0]["z"])   # real data, not a placeholder


def test_curvilinear_pick_data_handles_xy_shaped_like_c():
    """Regression: a curvilinear pcolormesh's X/Y the same shape as C (one
    center per cell, via np.meshgrid) rather than one-more-per-axis (node
    corners) is common and valid -- e.g. a polar radar scan built from
    meshgrid(range, azimuth). pick_data used the unclamped shape to build
    cell centers, indexing X/Y one column past their real width and raising
    a numpy shape-mismatch error building every such figure's interactive
    HTML."""
    from plotpress.svg import pick_data

    az = np.radians(np.linspace(0.0, 315.0, 8))
    rr = np.linspace(1.0, 6.0, 6)
    RR, AZ = np.meshgrid(rr, az)
    X, Y = RR * np.cos(AZ), RR * np.sin(AZ)
    Z = np.arange(X.size, dtype=float).reshape(X.shape)
    assert X.shape == Z.shape

    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(X, Y, Z, cmap="viridis")
    assert m.curvilinear
    fig.to_html(interactive=True)   # must not raise

    mesh = pick_data(fig)[0]["meshes"][0]
    ny, nx = mesh["shape"]
    assert ny == 7 and nx == 5      # clamped to min(shape, X.shape - 1), like the renderer
    assert len(mesh["xc"]) == len(mesh["yc"]) == len(mesh["z"]) == ny * nx


def test_to_html_exposes_pick_caps_for_mesh_heavy_figures():
    """A figure with many mesh-bearing axes has no way to bound the total pick
    payload unless the per-mesh caps are reachable from the public API --
    pick_max_mesh_cells/pick_max_points forward to pick_data()'s own caps."""
    g = np.linspace(-3, 3, 300)
    X, Y = np.meshgrid(g, g)
    Z = np.sin(np.hypot(X, Y))
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z)

    full = fig.to_html(interactive=True)
    capped = fig.to_html(interactive=True, pick_max_mesh_cells=1000)
    assert len(capped) < len(full)

    from plotpress.svg import pick_data
    mesh = pick_data(fig, max_mesh_cells=1000)[0]["meshes"][0]
    ny, nx = mesh["shape"]
    assert ny * nx <= 1000


def test_round_list_matches_python_rounding():
    # The vectorized _rl replaced a per-element round(float(v), nd) comprehension.
    # It agrees with it to within one quantum -- the two can differ only on exact
    # half-way ties at the last digit (numpy multiplies-then-rounds; Python rounds
    # the decimal). That last-digit difference is irrelevant for a pick readout.
    from plotpress.svg import _rl

    rng = np.random.default_rng(0)
    a = rng.standard_normal(2000) * 50.0
    for nd in (6, 4, 3):
        got = np.asarray(_rl(a, nd))
        ref = np.asarray([round(float(v), nd) for v in a])
        assert got.shape == ref.shape
        assert np.allclose(got, ref, atol=10.0 ** -nd)


def test_pick_precision_rounds_and_shrinks_payload():
    from plotpress.svg import pick_data

    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.linspace(0, 1, 400).reshape(20, 20))
    z6 = pick_data(fig, precision=6)[0]["meshes"][0]["z"]
    z2 = pick_data(fig, precision=2)[0]["meshes"][0]["z"]

    # Coarser precision actually rounds the embedded values...
    assert z2 == [round(v, 2) for v in z6]
    # ...and a lower-precision interactive HTML is no larger than the default.
    assert len(fig.to_html(pick_precision=2)) <= len(fig.to_html(pick_precision=6))


def test_plot_frames_registers_slider_and_embeds_frames():
    from plotpress.svg import frame_data

    fig, axes = plotpress.subplots(1, 2)
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
    assert 'id="plotpress-frames"' in html and 'id="plotpress-sliders"' in html
    # Static SVG shows a frame but carries no slider payload.
    assert "plotpress-frameline" in fig.to_svg()
    assert "plotpress-sliders" not in fig.to_html(interactive=False)


def test_shared_false_gives_each_axes_its_own_docked_unit():
    from plotpress.svg import frame_data

    fig, axes = plotpress.subplots(1, 3)
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
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot_frames(np.arange(5), np.zeros((6, 5)), shared=False,
                        slider_group="t", slider_label="t")
    axes[1].plot_frames(np.arange(5), np.zeros((6, 5)), shared=False,
                        slider_group="t", slider_label="t")
    assert fig._sliders["ax0"]["index"] == "t"
    assert fig._sliders["ax1"]["index"] == "t"
    # Distinct docked units (one per axes), not a single merged slider.
    assert fig._sliders["ax0"]["axes"] == 0 and fig._sliders["ax1"]["axes"] == 1


def test_connection_index_requires_matching_n_frames():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot_frames(np.arange(5), np.zeros((6, 5)), shared=False, slider_group="t")
    with pytest.raises(ValueError):
        axes[1].plot_frames(np.arange(5), np.zeros((8, 5)), shared=False, slider_group="t")


def test_independent_slider_allows_different_n_frames():
    # A docked slider with its own index need not match the global n_frames.
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot_frames([0, 1, 2], np.zeros((4, 3)))               # main, n=4
    axes[1].plot_frames([0, 1, 2], np.zeros((7, 3)), shared=False)  # ax1, n=7
    assert set(fig._sliders) == {"main", "ax1"}


def test_plot_frames_requires_matching_n_frames():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot_frames([0, 1, 2], np.zeros((4, 3)))
    with pytest.raises(ValueError):
        axes[1].plot_frames([0, 1, 2], np.zeros((6, 3)))  # different n_frames


def test_plot_frames_rejects_1d():
    _, ax = plotpress.subplots()
    with pytest.raises(ValueError):
        ax.plot_frames([0, 1, 2], [0, 1, 2])  # Y must be 2-D


def test_interactive_html_includes_marker_extraction():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    html = fig.to_html(interactive=True)
    assert "plotpressGetMarkers" in html   # programmatic extraction hook
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
    fig, ax = plotpress.subplots()
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
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])

    # wait_extract injects the close-on-extract flag assignment into the page.
    assert "PLOTPRESS_WAIT_EXTRACT=true" in fig.to_html(interactive=True, wait_extract=True)
    assert "PLOTPRESS_WAIT_EXTRACT=true" not in fig.to_html(interactive=True)

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
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    with pytest.raises(RuntimeError):
        fig.show(wait_for_extract=True)


def _without_pywebview(monkeypatch):
    """Force show() down its browser-fallback path."""
    import builtins

    real_import = builtins.__import__

    def no_webview(name, *args, **kwargs):
        if name == "webview":
            raise ImportError("no pywebview")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_webview)


def test_browser_fallback_reuses_one_temp_file_per_figure(tmp_path, monkeypatch):
    """It used to drop a fresh temp file on every call and never remove any."""
    import tempfile
    import webbrowser

    _without_pywebview(monkeypatch)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    for _ in range(4):
        fig.show()

    files = list(tmp_path.glob("plotpress-*.html"))
    assert len(files) == 1        # one per figure, not one per call
    assert len(opened) == 4       # ...and the browser still opens every time
    assert files[0].read_text(encoding="utf-8").startswith("<!doctype html>")


def test_browser_fallback_rewrites_the_file_when_the_figure_changes(tmp_path,
                                                                   monkeypatch):
    import tempfile
    import webbrowser

    _without_pywebview(monkeypatch)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: None)

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.show()
    first = next(tmp_path.glob("plotpress-*.html")).read_text(encoding="utf-8")
    ax.set_title("added later")
    fig.show()
    second = next(tmp_path.glob("plotpress-*.html")).read_text(encoding="utf-8")
    assert "added later" in second and "added later" not in first


def test_stale_browser_tempfiles_are_reaped_and_fresh_ones_survive(tmp_path):
    """Cleanup goes by age: the fallback hands its file to another process, so
    deleting on the way out would race a script that exits right after show()."""
    from plotpress.figure import _sweep_stale_tempfiles

    fresh = tmp_path / "plotpress-fresh.html"
    stale = tmp_path / "plotpress-stale.html"
    other = tmp_path / "someone-elses.html"
    for p in (fresh, stale, other):
        p.write_text("x", encoding="utf-8")
    long_ago = time.time() - 48 * 3600
    os.utime(stale, (long_ago, long_ago))

    _sweep_stale_tempfiles(str(tmp_path))

    assert fresh.exists()       # this session's figure must not be pulled away
    assert not stale.exists()
    assert other.exists()       # only our own prefix is ours to delete


def test_sweep_tolerates_a_missing_directory(tmp_path):
    from plotpress.figure import _sweep_stale_tempfiles

    _sweep_stale_tempfiles(str(tmp_path / "does-not-exist"))   # must not raise


def test_html_payloads_cannot_break_out_of_their_script_block():
    """An HTML parser ends a <script> at the first "</script" in its text, so a
    label carrying one would close the JSON payload and run what follows."""
    import json

    evil = '</script><script>window.PWNED=1</script>'
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 2], values={evil: np.arange(3.0)})
    ax.plot_frames(np.arange(3), np.zeros((2, 3)), slider_label=evil)
    html = fig.to_html(interactive=True)

    assert "</script><script>window.PWNED=1</script>" not in html
    assert "\\u003c/script\\u003e" in html          # escaped, still inside JSON

    # Every payload block is intact and still parses back to the original text.
    for pid in ("plotpress-pick", "plotpress-sliders"):
        start = html.index('id="%s">' % pid) + len('id="%s">' % pid)
        end = html.index("</script>", start)
        assert evil in json.dumps(json.loads(html[start:end]))


def test_pick_data_omits_oversized_series_but_downsamples_oversized_meshes():
    """Point series over the cap have no missing-value problem to solve (the
    client falls back to nearest-vertex geometry), so they're omitted
    outright. A mesh over the cap still needs to answer a click with a real
    value, so it's block-averaged down to fit instead of being dropped."""
    from plotpress.svg import pick_data

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot(np.arange(30000.0), np.arange(30000.0))  # over max_points
    axes[1].pcolormesh(np.arange(300 * 300, dtype=float).reshape(300, 300))
    pd = pick_data(fig, max_points=20000, max_mesh_cells=60000)
    assert pd.get(0, {"series": []})["series"] == [] or 0 not in pd

    meshes = pd[1]["meshes"]
    assert len(meshes) == 1
    ny, nx = meshes[0]["shape"]
    assert ny * nx <= 60000                # downsampled to fit the cap
    assert len(meshes[0]["z"]) == ny * nx  # a real, usable value grid


def _mesh_alpha(draw):
    """Alpha channel of the raster a mesh embeds into the SVG."""
    import base64
    import io
    import re

    from PIL import Image

    fig, ax = plotpress.subplots(figsize=(5, 3))
    draw(ax)
    b64 = re.search(r'image/png;base64,([^"]+)"', fig.to_svg()).group(1)
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA"))[:, :, 3]


def test_rectangular_curvilinear_mesh_fills_its_raster():
    """A 2-D mesh covering a rectangle must paint every pixel of its image.

    _out_grid scaled by (out_w - 1), placing the boundary nodes on pixel
    *centers* while the scan converter samples centers at index + 0.5 -- so the
    far row and column fell outside the mesh and stayed transparent, drawing a
    hairline gap along two edges of every curvilinear mesh.
    """
    edges_x = np.array([0.0, 1.0, 2.0, 4.0, 8.0, 16.0])
    edges_y = np.array([0.0, 0.5, 1.0])
    field = np.tile(np.arange(5.0), (2, 1))
    X, Y = np.meshgrid(edges_x, edges_y)
    assert (_mesh_alpha(lambda ax: ax.pcolormesh(X, Y, field, cmap="viridis")) == 0).sum() == 0


def test_gouraud_mesh_fills_its_raster():
    g = np.linspace(-3.0, 3.0, 24)
    X, Y = np.meshgrid(g, g)
    C = np.exp(-(X ** 2 + Y ** 2))
    alpha = _mesh_alpha(
        lambda ax: ax.pcolormesh(X, Y, C, cmap="viridis", shading="gouraud"))
    assert (alpha == 0).sum() == 0


# -- figure-level legend ----------------------------------------------------

def _grid_with_labels(nrows=2, ncols=2):
    x = np.linspace(0.0, 10.0, 50)
    fig, axes = plotpress.subplots(nrows, ncols, figsize=(8.0, 5.0))
    for i, ax in enumerate(np.atleast_1d(axes).ravel()):
        ax.plot(x, np.sin(x + i), label="sin")
        ax.plot(x, np.cos(x + i), label="cos")
    fig.tight_layout()
    return fig, np.atleast_1d(axes).ravel()


def test_figure_legend_deduplicates_labels_across_axes():
    """Panels plotting the same series should contribute one entry, not one
    each -- otherwise a shared legend just repeats itself per panel."""
    from plotpress.svg import figure_legend_layout

    fig, _ = _grid_with_labels()
    fig.legend()
    assert [e.label for e in figure_legend_layout(fig)["entries"]] == ["sin", "cos"]


def test_figure_legend_reserves_space_at_its_edge():
    fig, axes = _grid_with_labels()
    before = [a._rect for a in axes]
    fig.legend(loc="lower center")
    after = [a._rect for a in axes]
    assert all(n[3] < b[3] for b, n in zip(before, after))      # shorter
    assert all(n[1] > b[1] for b, n in zip(before, after))      # pushed up


def test_figure_legend_reservation_survives_a_reflow():
    """tight_layout rebuilds full grid cells, which would otherwise drop the
    band and leave the legend sitting on the bottom row."""
    fig, axes = _grid_with_labels()
    fig.legend(loc="lower center")
    reserved = [a._rect for a in axes]
    fig.tight_layout()
    assert [a._rect for a in axes] == reserved


def test_figure_legend_overlay_placements_reserve_nothing():
    fig, axes = _grid_with_labels()
    before = [a._rect for a in axes]
    fig.legend(loc="upper right")
    assert [a._rect for a in axes] == before
    assert "sin" in fig.to_svg()


def test_figure_legend_renders_in_both_backends():
    from plotpress import raster

    fig, _ = _grid_with_labels()
    fig.legend(loc="lower center", ncol=2, title="Series")
    svg = fig.to_svg()
    assert "Series" in svg and svg.count(">sin<") == 1
    assert raster.figure_to_image(fig, scale=1) is not None


def test_figure_legend_absent_without_the_call():
    fig, _ = _grid_with_labels()
    assert "plotpress-legend" not in fig.to_svg()


# -- mesh orientation and inverted axes -------------------------------------

def _mesh_image_box(draw):
    """The x/y/width/height of the <image> a mesh emits."""
    import re

    fig, ax = plotpress.subplots(figsize=(4.0, 3.0))
    draw(ax)
    m = re.search(r'<image x="([-\d.]+)" y="([-\d.]+)" '
                  r'width="([-\d.]+)" height="([-\d.]+)"', fig.to_svg())
    assert m, "no <image> emitted"
    return [float(v) for v in m.groups()]


@pytest.mark.parametrize("invert", ["x", "y", "both"])
def test_mesh_on_an_inverted_axis_has_a_positive_box(invert):
    """An inverted axis reversed the transformed corners, so the emitted image
    got a negative width or height. That is an error in SVG, so the element was
    dropped and the mesh vanished -- every depth, pressure and travel-time plot
    in the gallery rendered as bare axes."""
    g = np.linspace(0.0, 4.0, 24)
    Z = np.add.outer(g, g)

    def draw(ax):
        ax.pcolormesh(g, g, Z, cmap="viridis")
        if invert in ("x", "both"):
            ax.invert_xaxis()
        if invert in ("y", "both"):
            ax.invert_yaxis()

    _, _, w, h = _mesh_image_box(draw)
    assert w > 0 and h > 0


def _row_brightness(yvec, invert):
    """Mean pixel value near the top and bottom of a mesh whose value is its y."""
    import io

    from PIL import Image as PILImage

    from plotpress import raster

    x = np.linspace(0.0, 1.0, 16)
    Z = np.repeat(np.asarray(yvec, float)[:, None], x.size, axis=1)
    fig, ax = plotpress.subplots(figsize=(3.0, 3.0))
    ax.pcolormesh(x, yvec, Z, cmap="viridis", vmin=0.0, vmax=100.0)
    if invert:
        ax.invert_yaxis()
    ax.set_axis_off()
    buf = io.BytesIO()
    raster.figure_to_image(fig, scale=1).save(buf, format="PNG")
    im = np.asarray(PILImage.open(io.BytesIO(buf.getvalue())).convert("RGB")).astype(int)
    h = im.shape[0]
    return im[int(h * 0.12)].mean(), im[int(h * 0.88)].mean()


@pytest.mark.parametrize("descending", [False, True])
def test_mesh_row_order_follows_the_coordinate_not_the_array(descending):
    """A y vector given high-to-low is legitimate -- pressure and depth axes are
    routinely stored that way -- but the rasterizer assumed row 0 was ymax, so
    the field came out mirrored against its own axis while the ticks stayed
    put. Large y must render at the top either way."""
    y = np.linspace(0.0, 100.0, 24)
    if descending:
        y = y[::-1].copy()
    top, bottom = _row_brightness(y, invert=False)
    assert top > bottom


@pytest.mark.parametrize("descending", [False, True])
def test_inverting_the_axis_flips_the_mesh_with_it(descending):
    y = np.linspace(0.0, 100.0, 24)
    if descending:
        y = y[::-1].copy()
    top, bottom = _row_brightness(y, invert=True)
    assert top < bottom


def test_text_gets_a_contrasting_halo_by_default():
    """Labels in the data area are placed before anyone knows what is under them.

    The halo is painted under the fill (``paint-order``) so the glyph keeps its
    shape, and its color follows the text's luminance: white behind dark ink,
    black behind light.
    """
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "dark", color="#111111")
    ax.text(0.5, 0.6, "light", color="#ffffff")
    svg = fig.to_svg()
    dark = re.search(r'<text[^>]*>dark</text>', svg).group(0)
    light = re.search(r'<text[^>]*>light</text>', svg).group(0)
    assert 'paint-order="stroke"' in dark and 'stroke="#ffffff"' in dark
    assert 'stroke="#000000"' in light


def test_text_halo_can_be_switched_off():
    fig, ax = plotpress.subplots()
    ax.text(0.5, 0.5, "plain", outline=False)
    assert "paint-order" not in re.search(r'<text[^>]*>plain</text>',
                                          fig.to_svg()).group(0)


def test_axis_furniture_has_no_halo():
    """Only user-placed labels get one; titles and ticks sit off the data."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("a title")
    svg = fig.to_svg()
    assert "paint-order" not in re.search(r'<text[^>]*>a title</text>',
                                          svg).group(0)


@pytest.mark.parametrize("target, expect", [
    ((160, 40), "top"),          # straight above -> top edge centre
    ((160, 400), "bottom"),
    ((10, 215), "left"),
    ((400, 215), "right"),
])
def test_leader_attaches_to_the_nearest_edge_centre(target, expect):
    """A leader from the text anchor sets off across its own label."""
    from plotpress.svg import leader_anchor

    box = (100.0, 200.0, 220.0, 230.0)
    x, y = leader_anchor(box, target)
    cx, cy = 160.0, 215.0
    got = {"top": y < 200 and abs(x - cx) < 1,
           "bottom": y > 230 and abs(x - cx) < 1,
           "left": x < 100 and abs(y - cy) < 1,
           "right": x > 220 and abs(y - cy) < 1}
    assert got[expect], (x, y)


def test_annotation_leader_starts_off_the_text():
    fig, ax = plotpress.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.annotate("a fairly long label", xy=(9, 9), xytext=(1, 1),
                arrowprops={"color": "#d62728"})
    svg = fig.to_svg()
    leader = [p for p in _parse(svg).findall(".//" + NS + "path")
              if p.get("stroke") == "#d62728"][0]
    start = leader.get("d").split("L")[0].lstrip("M").split(",")
    text = _parse(svg).findall(".//" + NS + "text")
    anchor = [(t.get("x"), t.get("y")) for t in text if t.text.startswith("a fairly")][0]
    # The leader must not begin at the text anchor itself.
    assert (start[0], start[1]) != anchor
