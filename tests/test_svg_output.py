"""SVG/HTML serialization: well-formedness, structure, and file output."""

import base64
import json
import math
import re
import os
import time
import warnings
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
         if "plotpress-marker" in (e.get("class") or "").split()][0]
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


# -- rasterized= (vector vs. raster mesh cells) -----------------------------

def _nonuniform_extreme():
    """The pcolormesh_vs_imshow gallery example's grid: cell 0 is 1/4000 the span."""
    edges = np.array([0.0, 0.01, 2.0, 6.0, 16.0, 40.0])
    y_edges = np.array([0.0, 0.5, 1.0])
    field = np.tile(np.arange(5.0), (2, 1))
    return edges, y_edges, field


def _mesh_rects(svg):
    """<rect> count belonging to the mesh -- the axes background/clip rects a
    bare figure emits regardless of content are not part of what a mesh draws.
    """
    empty_fig, _ = plotpress.subplots()
    baseline = _element_counts(empty_fig.to_svg())[1]
    return _element_counts(svg)[1] - baseline


def test_pcolormesh_auto_vectorizes_small_nonuniform_grid():
    edges, y_edges, field = _nonuniform_extreme()
    fig, ax = plotpress.subplots()
    with warnings.catch_warnings():
        warnings.simplefilter("error")     # a small grid must not warn either way
        mesh = ax.pcolormesh(edges, y_edges, field, cmap="viridis")
    assert mesh.vectorized
    images, _ = _element_counts(fig.to_svg())
    assert images == 0
    assert _mesh_rects(fig.to_svg()) == 5 * 2  # every cell, incl. the 1/4000-wide one


def test_pcolormesh_uniform_grid_stays_raster_in_auto_mode():
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.random.rand(4, 4))   # default integer edges: uniform
    assert not mesh.vectorized
    images, _ = _element_counts(fig.to_svg())
    assert images == 1 and _mesh_rects(fig.to_svg()) == 0


def test_pcolormesh_rasterized_true_forces_raster_and_drops_the_thin_cell():
    edges, y_edges, field = _nonuniform_extreme()
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match="cell 0"):
        mesh = ax.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=True)
    assert not mesh.vectorized
    images, _ = _element_counts(fig.to_svg())
    assert images == 1 and _mesh_rects(fig.to_svg()) == 0
    assert mesh.dropped_x.tolist() == [0]   # exactly the cell the docs example loses


def test_pcolormesh_rasterized_false_keeps_every_cell_even_forced():
    edges, y_edges, field = _nonuniform_extreme()
    fig, ax = plotpress.subplots()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        mesh = ax.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=False)
    assert mesh.vectorized
    images, _ = _element_counts(fig.to_svg())
    assert images == 0 and _mesh_rects(fig.to_svg()) == 10


def test_pcolormesh_rasterized_false_on_a_huge_mesh_warns_about_size():
    fig, ax = plotpress.subplots()
    edges = np.concatenate([[0.0], np.cumsum(np.random.default_rng(0)
                                             .uniform(0.5, 1.5, 3000))])
    y_edges = np.array([0.0, 1.0])
    field = np.zeros((1, 3000))
    with pytest.warns(UserWarning, match="3000.*<rect>"):
        mesh = ax.pcolormesh(edges, y_edges, field, rasterized=False)
    assert mesh.vectorized  # the explicit request still wins -- it only warns


def test_pcolormesh_uniform_grid_never_drops_a_cell_even_forced_raster():
    fig, ax = plotpress.subplots()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ax.pcolormesh(np.random.rand(50, 50), rasterized=True)


def test_pcolormesh_dropped_cell_warning_names_the_axis_and_edges():
    edges, y_edges, field = _nonuniform_extreme()
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match=r"x=0\.\.0\.01"):
        ax.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=True)


def test_dropped_cell_warning_calls_the_fix_cheap_only_when_it_actually_is():
    """The suggested fix must not call rasterized=False 'cheap' for a mesh
    that is itself past the auto-vectorize threshold -- following that advice
    would immediately trip the size warning instead."""
    edges, y_edges, field = _nonuniform_extreme()
    with pytest.warns(UserWarning, match=r"cheap here, under"):
        fig, ax = plotpress.subplots()
        ax.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=True)

    big_edges = np.concatenate([[0.0], np.cumsum(np.random.default_rng(1)
                                                  .uniform(0.5, 1.5, 3000))])
    big_field = np.tile(np.arange(3000.0), (1, 1))
    with pytest.warns(UserWarning) as caught:
        fig2, ax2 = plotpress.subplots()
        ax2.pcolormesh(big_edges, np.array([0.0, 1.0]), big_field)
    msgs = [str(w.message) for w in caught if "narrower than one output pixel" in str(w.message)]
    assert msgs, "expected the dropped-cell warning to fire for the big mesh"
    assert "cheap" not in msgs[0], (
        "must not call rasterized=False 'cheap' for a >2000-cell mesh: %r" % msgs[0])
    assert "past the" in msgs[0] and "auto threshold" in msgs[0]


def test_vector_mesh_size_warning_hedges_the_rect_count():
    """NaN cells are skipped by _render_mesh_vector, so the size warning must
    not overclaim an exact count it can't guarantee."""
    edges = np.concatenate([[0.0], np.cumsum(np.random.default_rng(2)
                                             .uniform(0.5, 1.5, 3000))])
    field = np.full((1, 3000), np.nan)
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match="up to 3000"):
        ax.pcolormesh(edges, np.array([0.0, 1.0]), field, rasterized=False)
    # And it's telling the truth: every cell is NaN, so zero rects actually land.
    assert _mesh_rects(fig.to_svg()) == 0


def test_pcolormesh_label_toggles_in_the_legend_whether_raster_or_vector():
    """A pcolormesh(label=...) legend entry must be targetable by the click-to-
    hide toggle (class=plotpress-series + data-label) regardless of whether
    the mesh happened to render as an <image> or a <g> of <rect>s."""
    fig_raster, ax_raster = plotpress.subplots()
    ax_raster.pcolormesh(np.random.rand(4, 4), label="raster_mesh")  # uniform -> raster
    root = _parse(fig_raster.to_svg())
    img = root.find(".//" + NS + "image")
    assert img.attrib.get("class") == "plotpress-series"
    assert img.attrib.get("data-label") == "raster_mesh"

    edges, y_edges, field = _nonuniform_extreme()
    fig_vec, ax_vec = plotpress.subplots()
    ax_vec.pcolormesh(edges, y_edges, field, label="vector_mesh")  # auto -> vector
    g = [e for e in _parse(fig_vec.to_svg()).iter(NS + "g")
         if e.get("data-label") == "vector_mesh"]
    assert len(g) == 1 and g[0].get("class") == "plotpress-series"


def test_pcolormesh_frames_has_no_rasterized_kwarg_but_still_warns():
    edges, y_edges, _ = _nonuniform_extreme()
    C = np.stack([np.tile(np.arange(5.0), (2, 1)) for _ in range(3)])
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match="pcolormesh_frames"):
        art = ax.pcolormesh_frames(edges, y_edges, C)
    assert not art.vectorized  # frames always rasterize -- see FrameQuadMesh docstring
    with pytest.raises(TypeError):
        ax.pcolormesh_frames(edges, y_edges, C, rasterized=False)


def test_frame_quad_mesh_carries_the_same_render_attributes_as_quad_mesh():
    """FrameQuadMesh must expose .n_cells like QuadMesh does -- anything that
    reads it generically across both mesh types (e.g. _warn_vector_mesh_size)
    would otherwise AttributeError the moment it's ever pointed at a frame."""
    edges, y_edges, _ = _nonuniform_extreme()
    C = np.stack([np.tile(np.arange(5.0), (2, 1)) for _ in range(3)])
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match="pcolormesh_frames"):
        art = ax.pcolormesh_frames(edges, y_edges, C)
    assert art.n_cells == art.frames[0].n_cells == 10
    assert art.uniform_grid == art.frames[0].uniform_grid == False


def test_pcolormesh_vector_cells_keep_the_same_pick_geometry_as_raster():
    """Pick geometry comes from the mesh's own edges, not the rendering choice."""
    edges, y_edges, field = _nonuniform_extreme()
    from plotpress.svg import pick_data

    fig_v, ax_v = plotpress.subplots()
    ax_v.pcolormesh(edges, y_edges, field, cmap="viridis")                 # auto -> vector
    fig_r, ax_r = plotpress.subplots()
    with pytest.warns(UserWarning, match="cell 0"):     # forced raster drops it -- expected
        ax_r.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=True)

    xedges_v = pick_data(fig_v)[0]["meshes"][0]["xedges"]
    xedges_r = pick_data(fig_r)[0]["meshes"][0]["xedges"]
    assert xedges_v == pytest.approx([0.0, 0.01, 2.0, 6.0, 16.0, 40.0])
    assert xedges_r == pytest.approx([0.0, 0.01, 2.0, 6.0, 16.0, 40.0])


def test_curvilinear_mesh_never_vectorizes():
    x = np.linspace(0, 1, 4)
    y = np.linspace(0, 1, 3)
    X, Y = np.meshgrid(x, y)
    X = X + 0.05 * Y  # a genuine shear, not collapsible back to 1-D
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match="no effect on a curvilinear grid"):
        mesh = ax.pcolormesh(X, Y, np.random.rand(3, 4), rasterized=False)
    assert not mesh.vectorized  # no vector path for curvilinear cells at all
    images, _ = _element_counts(fig.to_svg())
    assert images == 1 and _mesh_rects(fig.to_svg()) == 0


def test_curvilinear_rasterized_false_warns_that_it_was_ignored():
    """rasterized=False on a curvilinear mesh must say so, not silently rasterize."""
    x = np.linspace(0, 1, 4)
    y = np.linspace(0, 1, 3)
    X, Y = np.meshgrid(x, y)
    X = X + 0.05 * Y
    fig, ax = plotpress.subplots()
    with pytest.warns(UserWarning, match="rasterized=False.*no effect"):
        ax.pcolormesh(X, Y, np.random.rand(3, 4), rasterized=False)
    # rasterized=True (the default outcome anyway) must NOT warn -- nothing
    # was ignored, that's what curvilinear always does.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ax2 = plotpress.subplots()[1]
        ax2.pcolormesh(X, Y, np.random.rand(3, 4), rasterized=True)
        ax3 = plotpress.subplots()[1]
        ax3.pcolormesh(X, Y, np.random.rand(3, 4))  # rasterized=None (auto) too


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


def test_report_requires_at_least_one_figure(tmp_path):
    report = plotpress.Report()
    with pytest.raises(ValueError):
        report.save(str(tmp_path / "empty.html"))


def test_report_add_rejects_non_figure():
    report = plotpress.Report()
    with pytest.raises(TypeError):
        report.add("not a figure")


def test_report_embeds_each_figure_via_its_own_iframe_in_order(tmp_path):
    fig1, ax1 = plotpress.subplots()
    ax1.plot([0, 1], [0, 1])
    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 1], [1, 0])
    fig3, ax3 = plotpress.subplots()
    ax3.plot([0, 1], [0, 0])

    report = plotpress.Report(title="Three lines", description="A B C")
    report.add(fig1, title="First")
    report.add(fig2, title="Second")
    report.add(fig3, title="Third")
    p = tmp_path / "report.html"
    report.save(str(p))
    out = p.read_text(encoding="utf-8")

    assert out.count("<iframe") == 3
    assert "Three lines" in out
    assert "A B C" in out
    # Order is document order: "First" before "Second" before "Third".
    i1, i2, i3 = out.index("First"), out.index("Second"), out.index("Third")
    assert i1 < i2 < i3
    # One embedded (escaped) figure document per iframe: the tagged root SVG
    # element's id appears exactly once per figure, however many times its
    # own JS separately references that same id by string.
    assert out.count("id=&quot;plotpress-svg&quot;") == 3


def test_report_srcdoc_round_trips_each_figures_own_html(tmp_path):
    """The escaped ``srcdoc`` must decode back to exactly what
    ``Figure.to_html(standalone=False)`` produces for that figure -- Report
    embeds each figure so its SVG fills the iframe's own width rather than
    centering at a fixed size, not a mangled or partially-escaped copy of the
    standalone document -- and non-default kwargs (here
    ``pick_precision``/``binary_pick_data``) must reach it unchanged."""
    import html as html_mod

    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(20, dtype=float).reshape(4, 5))
    expected = fig.to_html(interactive=True, pick_precision=2,
                           binary_pick_data=False, standalone=False)

    report = plotpress.Report()
    report.add(fig)
    p = tmp_path / "report_one.html"
    report.save(str(p), pick_precision=2, binary_pick_data=False)
    out = p.read_text(encoding="utf-8")

    start = out.index('srcdoc="') + len('srcdoc="')
    # html.escape() leaves no raw '"' inside the escaped blob, so the first
    # one found after the opening delimiter is unambiguously the closer.
    end = out.index('"', start)
    assert html_mod.unescape(out[start:end]) == expected


def test_report_static_mode_embeds_figures_without_the_toolbar(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    report = plotpress.Report()
    report.add(fig)
    p = tmp_path / "static_report.html"
    report.save(str(p), interactive=False)
    out = p.read_text(encoding="utf-8")
    assert "plotpress-toolbar" not in out
    assert "plotpress-svg" in out


def test_toolbar_clearance_reserves_space_only_when_interactive():
    from plotpress.figure import _toolbar_clearance

    assert _toolbar_clearance(False, 0) == (0, 0)
    assert _toolbar_clearance(False, 3) == (0, 0)   # static report: no toolbar either
    assert _toolbar_clearance(True, 0) == (112, 0)
    assert _toolbar_clearance(True, 2) == (112, 120)


def test_to_html_standalone_false_pads_body_for_toolbar_and_sliders():
    """Regression: standalone=False's SVG sits flush against the body's own
    edges (no flex-centering slack to silently absorb the fixed-position
    toolbar/slider strip the way standalone=True's full-viewport centering
    does) -- dropping the old (inaccurate) fixed-height guess this replaced
    left the toolbar with no reserved space at all, free to draw over
    whatever's in the figure's own top-right corner (a legend, a colorbar)."""
    import numpy as np

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    assert "padding:112px 0 0px" in fig.to_html(standalone=False)
    assert "padding:0px 0 0px" in fig.to_html(standalone=False, interactive=False)

    x = np.linspace(0, 1, 5)
    fig2, ax2 = plotpress.subplots()
    ax2.plot_frames(x, np.array([x, x * 2]))
    assert "padding:112px 0 60px" in fig2.to_html(standalone=False)


def test_to_html_standalone_false_scales_svg_and_drops_centering():
    """standalone=False is what Report (and anything else embedding the HTML
    in a container it doesn't control the size of) needs: the SVG must scale
    to fill whatever width it's given rather than sit at its own fixed pixel
    size, and the page must not force itself to a full viewport tall -- that
    combination is what left a large empty band above and below a figure
    centered in a shorter iframe."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])

    standalone = fig.to_html(standalone=True)
    assert "min-height:100vh" in standalone
    assert "width:100%;height:auto" not in standalone

    embedded = fig.to_html(standalone=False)
    assert "min-height:100vh" not in embedded
    assert "justify-content:center" not in embedded
    assert "width:100%;height:auto" in embedded


def _report_entry_doc(report_html, index=0):
    """Unescape and return the Nth embedded figure's own HTML document from
    a saved Report file's srcdoc-carrying iframes, in order."""
    import html as html_mod

    starts = [m.start() for m in re.finditer(r'srcdoc="', report_html)]
    start = starts[index] + len('srcdoc="')
    end = report_html.index('"', start)
    return html_mod.unescape(report_html[start:end])


def test_report_embeds_figures_at_full_width_not_a_fixed_pixel_size(tmp_path):
    """Regression: each iframe used to carry a fixed width/height matching
    the figure's own pixel size -- narrower than most browser windows, and
    centered by Figure.to_html's standalone body style, which together left
    a figure looking small and padded with empty space rather than filling
    the report."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    report = plotpress.Report()
    report.add(fig)
    p = tmp_path / "wide_report.html"
    report.save(str(p))
    out = p.read_text(encoding="utf-8")

    assert 'width="' not in out.split("<iframe", 1)[1].split(">", 1)[0]
    assert "width:100%" in out          # .plotpress-report-entry iframe CSS
    assert "contentDocument" in out     # the resize script that fits height
    # No sliders -- only the toolbar's own fixed 112px clearance, none below.
    assert "padding:112px 0 0px" in _report_entry_doc(out)


def test_report_reserves_space_per_docked_slider_via_body_padding(tmp_path):
    """Toolbar/slider clearance is real body padding inside the embedded
    figure's own document (Figure.to_html, standalone=False) -- not a
    separate out-of-band attribute the resize script has to add back in --
    so the iframe's measured scrollHeight already includes it."""
    x = np.linspace(0, 1, 5)
    Y = np.array([x, x * 2, x * 3])
    fig, ax = plotpress.subplots()
    ax.plot_frames(x, Y)
    report = plotpress.Report()
    report.add(fig)
    p = tmp_path / "slider_report.html"
    report.save(str(p))
    doc = _report_entry_doc(p.read_text(encoding="utf-8"))
    assert "padding:112px 0 60px" in doc

    # A static (non-interactive) report has no toolbar or slider strip to
    # reserve space for, regardless of the figure's own slider data.
    report2 = plotpress.Report()
    report2.add(fig)
    p2 = tmp_path / "slider_report_static.html"
    report2.save(str(p2), interactive=False)
    doc2 = _report_entry_doc(p2.read_text(encoding="utf-8"))
    assert "padding:0px 0 0px" in doc2


def test_load_data_recovers_single_figure_series_and_mesh(tmp_path):
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 4.0, 9.0])
    fig, (ax1, ax2) = plotpress.subplots(1, 2)
    ax1.plot(x, y)
    ax1.set_xlabel("t"); ax1.set_ylabel("amp"); ax1.set_title("line")

    xm = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    ym = np.array([0.0, 1.0, 2.0, 3.0])
    Z = np.arange(12.0).reshape(3, 4)
    m = ax2.pcolormesh(xm, ym, Z, cmap="viridis")
    ax2.set_title("mesh")
    fig.colorbar(m, ax=ax2).set_title("val")

    p = tmp_path / "load_single.html"
    fig.save(str(p), interactive=True)
    data = plotpress.load_data(str(p))

    # A bare figure has no report-level title, so it falls back to the same
    # 1-based "Figure N" label a Report page itself would show it under.
    assert list(data.keys()) == ["Figure 1"]
    fig_entry = data["Figure 1"]
    assert fig_entry["title"] is None and fig_entry["details"] is None
    axes = fig_entry["axes"]
    assert set(axes) == {"line", "mesh"}

    line = axes["line"]["series"][0]
    assert line["kind"] == "line"
    assert np.allclose(line["x"], x) and np.allclose(line["y"], y)
    assert axes["line"]["title"] == "line"
    assert axes["line"]["xlabel"] == "t" and axes["line"]["ylabel"] == "amp"

    mesh = axes["mesh"]["meshes"][0]
    assert np.allclose(mesh["x"], (xm[:-1] + xm[1:]) / 2.0)
    assert np.allclose(mesh["y"], (ym[:-1] + ym[1:]) / 2.0)
    assert np.allclose(mesh["z"], Z)
    assert axes["mesh"]["zlabel"] == "val"


def test_load_data_recovers_report_figures_keyed_by_title_in_order(tmp_path):
    fig1, ax1 = plotpress.subplots()
    ax1.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    fig2, ax2 = plotpress.subplots()
    z = np.arange(20.0).reshape(4, 5)
    ax2.pcolormesh(z, cmap="plasma")

    report = plotpress.Report(title="T", description="D")
    report.add(fig1, title="First", details="details one")
    report.add(fig2, title="Second", details="details two")
    p = tmp_path / "load_report.html"
    report.save(str(p))
    data = plotpress.load_data(str(p))

    assert list(data.keys()) == ["First", "Second"]   # in add() order
    assert data["First"]["title"] == "First" and data["First"]["details"] == "details one"
    assert data["Second"]["title"] == "Second" and data["Second"]["details"] == "details two"
    assert np.allclose(data["Second"]["axes"]["axes 0"]["meshes"][0]["z"], z)


def test_load_data_by_index_returns_a_list_keyed_by_position(tmp_path):
    """by_index=True is the escape hatch from title-keying -- e.g. for
    figures/axes whose titles aren't unique, or when a stable positional key
    is simply more useful than a name."""
    fig1, ax1 = plotpress.subplots()
    ax1.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    fig2, ax2 = plotpress.subplots()
    z = np.arange(20.0).reshape(4, 5)
    ax2.pcolormesh(z, cmap="plasma")

    report = plotpress.Report()
    report.add(fig1, title="First")
    report.add(fig2, title="Second")
    p = tmp_path / "load_report_by_index.html"
    report.save(str(p))

    figures = plotpress.load_data(str(p), by_index=True)
    assert isinstance(figures, list) and len(figures) == 2
    assert figures[0]["title"] == "First" and figures[1]["title"] == "Second"
    assert set(figures[0]["axes"]) == {0}   # int-keyed, not title-keyed
    assert np.allclose(figures[1]["axes"][0]["meshes"][0]["z"], z)


def test_load_data_falls_back_to_generated_titles_when_untitled(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [1.0, 0.0])   # no set_title() -- axes has none
    p = tmp_path / "load_untitled.html"
    fig.save(str(p), interactive=True)
    data = plotpress.load_data(str(p))
    assert list(data.keys()) == ["Figure 1"]
    assert list(data["Figure 1"]["axes"].keys()) == ["axes 0"]


def test_load_data_works_with_plain_json_meta(tmp_path):
    """binary_pick_data=False never columnarizes meta -- load_data() must
    handle both the columnar (int-keyed index) and plain (string-keyed dict)
    shapes the same way."""
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    p = tmp_path / "load_plain_json.html"
    fig.save(str(p), interactive=True, binary_pick_data=False)
    data = plotpress.load_data(str(p))
    assert np.allclose(data["Figure 1"]["axes"]["axes 0"]["series"][0]["y"],
                       [0.0, 1.0, 4.0])


def test_load_data_raises_on_static_html(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "static.html"
    fig.save(str(p), interactive=False)
    with pytest.raises(ValueError):
        plotpress.load_data(str(p))


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


def test_save_gif_labels_frames_with_the_slider_value(tmp_path):
    """An exported GIF has no slider to show the current value on, so each
    frame is stamped with it -- and the stamp changes what a bare frame would
    render as, since it draws real pixels over the top-right corner."""
    pytest.importorskip("PIL")
    from PIL import Image

    fig, ax = plotpress.subplots()
    x = np.linspace(0, 2 * np.pi, 40)
    t = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    ax.plot_frames(x, np.sin(x[None, :] - t[:, None]), slider_values=t,
                  slider_label="t")
    ax.set_ylim(-1.2, 1.2)

    labeled = tmp_path / "labeled.gif"
    bare = tmp_path / "bare.gif"
    fig.save(str(labeled), fps=5, label_frames=True)
    fig.save(str(bare), fps=5, label_frames=False)

    im_labeled = np.array(Image.open(str(labeled)).convert("RGB")).astype(int)
    im_bare = np.array(Image.open(str(bare)).convert("RGB")).astype(int)
    assert not np.array_equal(im_labeled, im_bare)
    # The difference is concentrated in the label corner, not the whole frame
    # -- the plotted data itself is identical either way. Outside the corner,
    # the two GIFs still aren't byte-identical: the labeled frame has extra
    # colors that nudge Pillow's per-file adaptive GIF palette, so a handful
    # of pixels elsewhere round to a neighboring palette entry. Allow that
    # quantization noise rather than requiring exact equality.
    corner_diff = np.abs(im_labeled[:30, -120:] - im_bare[:30, -120:])
    rest_diff = np.abs(im_labeled[40:, :] - im_bare[40:, :])
    corner_differs = corner_diff.sum() > 0
    rest_mostly_matches = (rest_diff.sum(axis=-1) > 0).mean() < 0.01
    assert corner_differs and rest_mostly_matches


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


def test_tight_layout_honors_tick_params_labelsize_and_length():
    """tight_layout()'s margin math must size an axes' own tick-label band
    from *its* tick_params(labelsize=...)/(length=...) override, not the
    figure-wide default -- otherwise a grid that shrinks its tick labels to
    fit small panels (a common move on dense small-multiples) still
    reserves margin sized for the bigger, unused default, over-widening
    every gap next to it for no reason."""
    f1, a1 = plotpress.subplots(2, 1, figsize=(4, 6))
    for ax in a1:
        ax.plot([0, 1], [0, 1])
    f1.tight_layout()
    default_gap = (a1[0]._rect[1] - (a1[1]._rect[1] + a1[1]._rect[3]))

    f2, a2 = plotpress.subplots(2, 1, figsize=(4, 6))
    for ax in a2:
        ax.plot([0, 1], [0, 1])
        ax.tick_params(labelsize=3, length=1)
    f2.tight_layout()
    shrunk_gap = (a2[0]._rect[1] - (a2[1]._rect[1] + a2[1]._rect[3]))

    assert shrunk_gap < default_gap, (
        "smaller tick_params(labelsize=..., length=...) must shrink the "
        "reserved margin, not leave it sized for the figure-wide default")


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


def test_axes_metadata_carries_group_title():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 3)
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    fig.group("Cluster A", [axes[0], axes[1]])
    meta = axes_metadata(fig)
    assert meta[0]["group"] == "Cluster A"
    assert meta[1]["group"] == "Cluster A"
    assert meta[2]["group"] == ""   # not a member of any group


def test_axes_metadata_joins_multiple_group_memberships():
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(1, 2)
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    fig.group("Row", list(axes))
    fig.group("Just the first", [axes[0]])
    meta = axes_metadata(fig)
    assert meta[0]["group"] == "Row, Just the first"
    assert meta[1]["group"] == "Row"


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
    payload = _meta_from_html(html)
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
    payload = _meta_from_html(html)
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


def _extract_script_json(html, script_id):
    start = html.index('id="%s">' % script_id) + len('id="%s">' % script_id)
    end = html.index("</script>", start)
    return html[start:end]


def _revive_binary(obj):
    """Python mirror of ``_interactive.py``'s ``reviveBinary``, for tests that
    need to assert on decoded values rather than just presence of a marker."""
    if isinstance(obj, dict):
        if set(obj) == {"__f32__"}:
            return _decode_f32(obj).tolist()
        if set(obj) == {"__f16__"}:
            return np.frombuffer(base64.b64decode(obj["__f16__"]),
                                 dtype=np.float16).astype(float).tolist()
        return {k: _revive_binary(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_revive_binary(v) for v in obj]
    return obj


def _meta_from_html(html):
    """The embedded ``plotpress-meta`` payload, decoded back to its logical
    ``{axes_index: {field: value}}`` shape regardless of whether
    ``binary_pick_data`` sent it column-wise (and any numeric column further
    binary-encoded) -- mirrors ``_interactive.py``'s ``expandColumnarMeta`` +
    ``reviveBinary`` so meta-content tests can assert on the actual default
    payload rather than opting out of it."""
    payload = json.loads(_extract_script_json(html, "plotpress-meta"))
    if isinstance(payload, dict) and {"keys", "index", "cols"} <= payload.keys():
        cols = _revive_binary(payload["cols"])
        return {str(idx): {k: cols[k][i] for k in payload["keys"]}
                for i, idx in enumerate(payload["index"])}
    return payload


def _decode_f32(marker):
    return np.frombuffer(base64.b64decode(marker["__f32__"]), dtype=np.float32)


def _big_mesh_fig():
    g = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(g, g)
    Z = np.sin(X) * np.cos(Y)
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z)
    return fig


def test_binary_pick_data_is_default_and_shrinks_mesh_payload():
    """A large mesh's pick payload embeds as base64 float32 bytes by default
    -- roughly half the size of JSON number text, at close to JSON.parse's own
    decode speed, benchmarked against gzip-compressing the JSON instead (also
    smaller, but 5-7x slower to decode: DecompressionStream's overhead
    dominates at these payload sizes, so it isn't what this defaults to)."""
    from plotpress.svg import pick_data

    fig = _big_mesh_fig()
    binary_html = fig.to_html(interactive=True)                       # default
    plain_html = fig.to_html(interactive=True, binary_pick_data=False)
    assert len(binary_html) < len(plain_html)

    pick = json.loads(_extract_script_json(binary_html, "plotpress-pick"))
    z_marker = pick["0"]["meshes"][0]["z"]
    assert isinstance(z_marker, dict) and set(z_marker) == {"__f32__"}

    expected = np.asarray(pick_data(fig)[0]["meshes"][0]["z"], dtype=np.float32)
    assert np.allclose(_decode_f32(z_marker), expected, atol=1e-5)


def test_binary_pick_data_false_matches_plain_json_structure():
    """Opting out reproduces exactly pick_data()'s own plain-list shape, with
    no __f32__ markers anywhere -- for hand inspection or diffing against an
    older plotpress version."""
    from plotpress.svg import pick_data

    fig = _big_mesh_fig()
    html = fig.to_html(interactive=True, binary_pick_data=False)
    pick_json = _extract_script_json(html, "plotpress-pick")
    pick = json.loads(pick_json)
    assert pick["0"]["meshes"][0]["z"] == pick_data(fig)[0]["meshes"][0]["z"]
    # The JS decoder's own source (always embedded) mentions "__f32__" too --
    # what matters is that the *pick payload itself* carries no markers.
    assert "__f32__" not in pick_json


def test_binary_pick_data_skips_short_arrays():
    """A handful of numbers (extent, shape) costs more as a base64-wrapped
    buffer -- the wrapper itself -- than as plain JSON text, so only arrays at
    or above the size where binary actually wins get encoded."""
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.linspace(0, 1, 16).reshape(4, 4))
    html = fig.to_html(interactive=True)
    pick = json.loads(_extract_script_json(html, "plotpress-pick"))
    mesh = pick["0"]["meshes"][0]
    assert isinstance(mesh["extent"], list)
    assert isinstance(mesh["shape"], list)
    assert isinstance(mesh["z"], list)   # 16 cells: also below the threshold


def test_binary_pick_data_preserves_nan_and_inf():
    """Float32 represents NaN/Infinity natively, so a masked cell in a large
    mesh survives the binary round trip instead of going through
    _sanitize_nan's None substitution -- and the surrounding JSON (a base64
    string) stays valid either way."""
    g = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(g, g)
    Z = np.sin(X) * np.cos(Y)
    Z[0, 0] = float("nan")
    Z[5, 5] = float("inf")
    Z[9, 9] = float("-inf")
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z)

    html = fig.to_html(interactive=True)   # must not raise, must stay valid JSON
    pick = json.loads(_extract_script_json(html, "plotpress-pick"))
    decoded = _decode_f32(pick["0"]["meshes"][0]["z"])
    assert np.isnan(decoded).any()
    assert np.isposinf(decoded).any()
    assert np.isneginf(decoded).any()


def test_save_html_binary_pick_data_flag(tmp_path):
    fig = _big_mesh_fig()
    binary_path = tmp_path / "binary.html"
    plain_path = tmp_path / "plain.html"
    fig.save(str(binary_path), interactive=True)
    fig.save(str(plain_path), interactive=True, binary_pick_data=False)
    assert binary_path.stat().st_size < plain_path.stat().st_size


def test_extra_js_is_inlined_after_plotpress_own_script():
    """extra_js must land in its own <script> block, after INTERACTIVE_JS --
    so window.plotpressAddTool/plotpressGetMarkers already exist by the
    time it runs (see the docstring's ordering promise)."""
    from plotpress._interactive import INTERACTIVE_JS

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    html = fig.to_html(interactive=True, extra_js="window.MY_MARKER = 1;")
    assert "window.MY_MARKER = 1;" in html
    assert html.index(INTERACTIVE_JS) < html.index("window.MY_MARKER = 1;")


def test_extra_js_works_without_interactive_payloads_too():
    """extra_js is not gated on interactive=True -- a caller building a
    fully custom page from a bare SVG should still be able to inline a
    script alongside it."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    html = fig.to_html(interactive=False, extra_js="window.MY_MARKER = 1;")
    assert "window.MY_MARKER = 1;" in html
    assert "plotpress-meta" not in html


def test_include_default_js_false_keeps_payloads_but_drops_plotpress_js():
    """The 'override' case: payloads (meta/pick/style) still ride along for
    a from-scratch script to read, but none of plotpress's own toolbar/pan/
    zoom/pick behavior does."""
    from plotpress._interactive import INTERACTIVE_JS

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    html = fig.to_html(interactive=True, include_default_js=False)
    assert "plotpress-meta" in html
    assert "plotpress-pick" in html
    assert "plotpress-style" in html
    assert INTERACTIVE_JS not in html
    assert "plotpressAddTool" not in html


def test_include_default_js_false_with_extra_js_is_the_only_script():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    html = fig.to_html(interactive=True, include_default_js=False,
                       extra_js="window.MY_MARKER = 1;")
    assert "window.MY_MARKER = 1;" in html
    assert "plotpressAddTool" not in html


def test_include_default_js_defaults_to_true():
    """Existing behavior (no include_default_js given at all) must be
    unaffected -- plotpress's own JS still ships by default."""
    from plotpress._interactive import INTERACTIVE_JS

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    html = fig.to_html(interactive=True)
    assert INTERACTIVE_JS in html


def test_save_html_passes_through_include_default_js_and_extra_js(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    path = tmp_path / "custom.html"
    fig.save(str(path), interactive=True, include_default_js=False,
             extra_js="window.MY_MARKER = 1;")
    text = path.read_text(encoding="utf-8")
    assert "window.MY_MARKER = 1;" in text
    assert "plotpressAddTool" not in text


def test_binary_pick_data_uses_float16_at_low_precision_for_bounded_data():
    """pick_precision has always promised 'lower it, get a smaller file' --
    but float32 is a fixed 4 bytes/value regardless of how many decimals were
    rounded off, so a bounded-range mesh (here in [-1, 1]) at low enough
    precision for float16's ~3 significant digits to lose nothing further
    should drop to the 2-byte encoding instead, honoring that promise again."""
    g = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(g, g)
    Z = np.sin(X) * np.cos(Y)          # bounded to [-1, 1]
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z)

    html2 = fig.to_html(interactive=True, pick_precision=2)
    html6 = fig.to_html(interactive=True, pick_precision=6)
    pick2 = json.loads(_extract_script_json(html2, "plotpress-pick"))
    pick6 = json.loads(_extract_script_json(html6, "plotpress-pick"))
    z2 = pick2["0"]["meshes"][0]["z"]
    z6 = pick6["0"]["meshes"][0]["z"]

    assert set(z2) == {"__f16__"}
    assert set(z6) == {"__f32__"}   # too fine for float16 -- see the module docstring
    assert len(html2) < len(html6)

    from plotpress.svg import pick_data
    expected = np.asarray(pick_data(fig, precision=2)[0]["meshes"][0]["z"])
    got = np.frombuffer(base64.b64decode(z2["__f16__"]), dtype=np.float16).astype(np.float64)
    assert np.allclose(got, expected, atol=0.005)


def test_binary_pick_data_float16_skips_out_of_range_values():
    """A value past float16's ~65504 ceiling must never be silently encoded
    as one -- it would overflow to Infinity and corrupt the readout. Even at
    pick_precision=0 (as coarse as it gets), a mesh with large-magnitude
    values has to stay on float32."""
    g = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(g, g)
    Z = (np.sin(X) * np.cos(Y)) * 200000.0   # peaks near +-200000, past float16
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z)

    html = fig.to_html(interactive=True, pick_precision=0)
    pick = json.loads(_extract_script_json(html, "plotpress-pick"))
    assert set(pick["0"]["meshes"][0]["z"]) == {"__f32__"}


def test_binary_pick_data_float16_preserves_nan_and_inf():
    g = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(g, g)
    Z = np.sin(X) * np.cos(Y)
    Z[0, 0] = float("nan")
    Z[5, 5] = float("inf")
    Z[9, 9] = float("-inf")
    fig, ax = plotpress.subplots()
    ax.pcolormesh(g, g, Z)

    html = fig.to_html(interactive=True, pick_precision=2)
    pick = json.loads(_extract_script_json(html, "plotpress-pick"))
    z_marker = pick["0"]["meshes"][0]["z"]
    assert set(z_marker) == {"__f16__"}
    decoded = np.frombuffer(base64.b64decode(z_marker["__f16__"]), dtype=np.float16)
    assert np.isnan(decoded).any()
    assert np.isposinf(decoded.astype(np.float64)).any()
    assert np.isneginf(decoded.astype(np.float64)).any()


def test_columnar_meta_is_default_and_shrinks_many_axes_payload():
    """A many-axes figure's meta has no long arrays of its own -- its cost is
    ~25 JSON key names repeated once per axes rather than a big number array
    -- so it needs its own structural fix distinct from _encode_binary_arrays,
    gated by the same binary_pick_data flag. See figure._columnarize_meta."""
    fig, axes = plotpress.subplots(6, 6)   # 36 axes: enough to cross both
    for ax in axes.ravel():                # the columnar AND binary-array
        ax.plot([0, 1], [0, 1])            # thresholds for its numeric columns

    binary_html = fig.to_html(interactive=True)                       # default
    plain_html = fig.to_html(interactive=True, binary_pick_data=False)
    binary_meta = _extract_script_json(binary_html, "plotpress-meta")
    plain_meta = _extract_script_json(plain_html, "plotpress-meta")
    assert len(binary_meta) < len(plain_meta)

    payload = json.loads(binary_meta)
    assert {"keys", "index", "cols"} <= payload.keys()
    assert payload["index"] == list(range(36))
    assert isinstance(payload["cols"]["x"], dict)   # 36 values: binary-encoded too


def test_columnar_meta_round_trips_exactly_including_excluded_axes():
    """Decoding the embedded (columnar, binary-numeric) meta payload must
    reproduce exactly what axes_metadata() itself computed -- including a
    gap in the surviving indices, since a hidden (or colorbar, or 3-D) axes
    is excluded from meta wherever it sits in fig.axes, which
    _columnarize_meta's own "index rides along as its own array" handling
    exists for."""
    from plotpress.svg import axes_metadata

    fig, axes = plotpress.subplots(3, 4)
    for i, ax in enumerate(axes.ravel()):
        ax.plot([0, i + 1], [i, 0])
    axes.ravel()[5].set_visible(False)   # a gap in the middle of the index run

    expected = axes_metadata(fig)
    html = fig.to_html(interactive=True)
    got = _meta_from_html(html)

    assert set(got.keys()) == {str(i) for i in expected.keys()}
    numeric_fields = {"x", "y", "w", "h", "xmin", "xmax", "ymin", "ymax"}
    for i, exp_entry in expected.items():
        got_entry = got[str(i)]
        for field, exp_val in exp_entry.items():
            if field in numeric_fields:
                assert got_entry[field] == pytest.approx(exp_val, abs=0.01), field
            else:
                assert got_entry[field] == exp_val, field


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


def test_pcolormesh_frames_registers_slider_and_embeds_hrefs():
    from plotpress.svg import frame_data

    fig, ax = plotpress.subplots()
    x = np.linspace(0, 1, 6)
    y = np.linspace(0, 1, 5)
    X, Y = np.meshgrid(x, y)
    C = np.stack([np.sin(X + phase) * np.cos(Y) for phase in np.linspace(0, 1, 4)])
    mesh = ax.pcolormesh_frames(x, y, C, slider_values=range(4), slider_label="t")

    assert set(fig._sliders) == {"main"}
    assert fig._sliders["main"]["n"] == 4
    assert fig._sliders["main"]["label"] == "t"
    assert mesh.n_frames == 4

    frames = frame_data(fig)
    entry = frames[0][0]
    assert entry["unit"] == "main"
    assert len(entry["hrefs"]) == 4
    assert all(h.startswith("data:image/png;base64,") for h in entry["hrefs"])
    # Frames genuinely differ -- not the same image four times.
    assert len(set(entry["hrefs"])) == 4

    # Regression: frame_data() used to embed only the rendered hrefs, nothing
    # numeric -- a pcolormesh_frames() axes had no pick data at all, at any
    # frame (see the meshframe picking tests in test_pick_interactive.py).
    assert entry["shape"] == [5, 6]
    assert len(entry["z"]) == 4                     # one z grid per frame, flattened
    assert np.allclose(entry["z"][0], mesh.frame_mesh(0).C.ravel())
    assert np.allclose(entry["z"][2], mesh.frame_mesh(2).C.ravel())
    assert entry["z"][0] != entry["z"][1]           # frames genuinely differ
    assert "xedges" in entry and "yedges" in entry  # rectilinear, not curvilinear

    html = fig.to_html(interactive=True)
    assert 'id="plotpress-frames"' in html and 'id="plotpress-sliders"' in html
    # Static SVG shows frame 0 as an <image>, no slider payload.
    svg = fig.to_svg()
    assert "plotpress-framemesh" in svg
    assert "plotpress-sliders" not in fig.to_html(interactive=False)


def test_pcolormesh_frames_shares_one_colour_scale_across_frames():
    fig, ax = plotpress.subplots()
    # Frame 0 alone spans [-1, 1]; frame 1 alone spans [-5, 5]. A colour scale
    # fitted per frame would jump; one fitted to the whole animation must not.
    C = np.stack([np.array([[-1.0, 1.0]]), np.array([[-5.0, 5.0]])])
    mesh = ax.pcolormesh_frames(C)
    assert mesh.norm.vmin == -5.0
    assert mesh.norm.vmax == 5.0
    assert mesh.frame_mesh(0).norm.vmin == -5.0
    assert mesh.frame_mesh(1).norm.vmax == 5.0


def test_pcolormesh_frames_rejects_2d_input():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="n_frames"):
        ax.pcolormesh_frames(np.zeros((4, 4)))  # missing the frame axis


def test_pcolormesh_frames_requires_matching_n_frames_with_plot_frames():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot_frames(np.arange(3), np.zeros((5, 3)))       # main, n=5
    with pytest.raises(ValueError):
        axes[1].pcolormesh_frames(np.zeros((4, 6, 6)))        # main, n=4 -- mismatch


def test_save_gif_animates_pcolormesh_frames(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    fig, ax = plotpress.subplots()
    x = np.linspace(0, 1, 8)
    y = np.linspace(0, 1, 6)
    X, Y = np.meshgrid(x, y)
    C = np.stack([np.sin(X + phase) for phase in np.linspace(0, 2, 5)])
    ax.pcolormesh_frames(x, y, C)

    p = tmp_path / "mesh.gif"
    fig.save(str(p), fps=5)
    im = Image.open(str(p))
    assert im.n_frames == 5
    im.seek(0)
    first = np.array(im.convert("RGB"))
    im.seek(2)
    later = np.array(im.convert("RGB"))
    assert not np.array_equal(first, later)


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

    This grid is small enough (10 cells) that auto mode would now draw it as
    exact vector rects, which have no such gap to test for -- rasterized=True
    forces the raster path this regression is actually about.
    """
    edges_x = np.array([0.0, 1.0, 2.0, 4.0, 8.0, 16.0])
    edges_y = np.array([0.0, 0.5, 1.0])
    field = np.tile(np.arange(5.0), (2, 1))
    X, Y = np.meshgrid(edges_x, edges_y)
    assert (_mesh_alpha(lambda ax: ax.pcolormesh(
        X, Y, field, cmap="viridis", rasterized=True)) == 0).sum() == 0


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


# -- Figure.group() ----------------------------------------------------------

def _grid_2x2():
    fig, axes = plotpress.subplots(2, 2, figsize=(6, 5))
    for ax in axes.ravel():
        ax.plot([0, 1], [0, 1])
    return fig, axes


def test_group_draws_a_box_wrapping_its_axes():
    fig, axes = _grid_2x2()
    fig.group("Left column", [axes[0, 0], axes[1, 0]])
    root = _parse(fig.to_svg())
    rects = root.findall(f".//{NS}rect")
    # background rect + one per axes' own facecolor + the group's own box.
    assert any(r.get("fill") == "none" for r in rects)
    texts = [t.text for t in root.findall(f".//{NS}text")]
    assert "Left column" in texts


def test_group_box_bounds_the_union_of_its_axes_with_padding():
    from plotpress.svg import _group_axes_extra, _pixel_rect

    fig, axes = _grid_2x2()
    fig.group("Top row", [axes[0, 0], axes[0, 1]], pad=5.0)
    svg = fig.to_svg()   # settles layout (incl. the group's own margin band)
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    st = fig.style
    r00, r01 = _pixel_rect(axes[0, 0], W, H), _pixel_rect(axes[0, 1], W, H)
    e00, e01 = _group_axes_extra(axes[0, 0], st), _group_axes_extra(axes[0, 1], st)
    root = _parse(svg)
    box = [r for r in root.findall(f".//{NS}rect") if r.get("fill") == "none"][0]
    x0 = min(r00[0] - e00[2], r01[0] - e01[2]) - 5.0
    y0 = min(r00[1] - e00[0], r01[1] - e01[0]) - 5.0
    x1 = max(r00[0] + r00[2] + e00[3], r01[0] + r01[2] + e01[3]) + 5.0
    y1 = max(r00[1] + r00[3] + e00[1], r01[1] + r01[3] + e01[1]) + 5.0
    assert float(box.get("x")) == pytest.approx(x0, abs=0.5)
    assert float(box.get("y")) == pytest.approx(y0, abs=0.5)
    assert float(box.get("width")) == pytest.approx(x1 - x0, abs=0.5)
    assert float(box.get("height")) == pytest.approx(y1 - y0, abs=0.5)


def test_group_title_position_and_style():
    fig, axes = _grid_2x2()
    fig.group("Right side", [axes[0, 1], axes[1, 1]], color="#d62728",
             linestyle=":", title_position="right")
    root = _parse(fig.to_svg())
    box = [r for r in root.findall(f".//{NS}rect") if r.get("fill") == "none"][0]
    assert box.get("stroke") == "#d62728"
    assert box.get("stroke-dasharray") == "1,3"
    title = [t for t in root.findall(f".//{NS}text") if t.text == "Right side"][0]
    assert title.get("text-anchor") == "start"   # sits to the right of the box
    assert float(title.get("x")) > float(box.get("x")) + float(box.get("width"))


def test_group_box_includes_axis_labels_and_tick_labels_not_just_the_plot_rect():
    """Regression: the box wrapped only ax._rect (the bare spine box), so an
    axes' own xlabel/ylabel and tick numbers -- all drawn *outside* that
    rect -- ended up sitting outside the group's box entirely, or with the
    box edge cutting straight through them."""
    from plotpress.svg import _pixel_rect

    fig, axes = _grid_2x2()
    ax = axes[0, 0]
    ax.set_xlabel("time (s)")
    ax.set_ylabel("value")
    fig.group("Group", [ax], pad=2.0)
    svg = fig.to_svg()
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    r = _pixel_rect(ax, W, H)
    root = _parse(svg)
    box = [b for b in root.findall(f".//{NS}rect") if b.get("fill") == "none"][0]
    bx0, by0 = float(box.get("x")), float(box.get("y"))
    bx1 = bx0 + float(box.get("width"))
    by1 = by0 + float(box.get("height"))
    # The box must reach further out than the bare plot rect in the
    # directions the axis labels/tick numbers actually occupy.
    assert bx0 < r[0], "box left edge does not clear the ylabel/tick numbers"
    assert by1 > r[1] + r[3], "box bottom edge does not clear the xlabel/tick numbers"
    # And every text element (xlabel, ylabel, tick numbers, the axes' own
    # title if any) must land strictly inside those bounds.
    for t in root.findall(f".//{NS}text"):
        if t.text in ("time (s)", "value"):
            tx, ty = float(t.get("x")), float(t.get("y"))
            assert bx0 <= tx <= bx1, "%r sits outside the box horizontally" % t.text
            assert by0 <= ty <= by1, "%r sits outside the box vertically" % t.text


def test_group_facing_the_outer_edge_reserves_layout_margin():
    """A group's title, when it faces the grid's own outer edge, needs a
    tight_layout() band reserved for it just like a suptitle/colorbar/figure
    legend does -- otherwise it (or the box, over a titled top row) draws
    off the canvas or on top of the outermost panels."""
    fig, axes = _grid_2x2()
    for ax in axes.ravel():
        ax.set_title("panel")
    fig.tight_layout()
    before = [a._rect for a in axes.ravel()]

    fig.group("Top row", [axes[0, 0], axes[0, 1]], title_position="top")
    fig.tight_layout()
    after = [a._rect for a in axes.ravel()]
    # Shorter, and its own top edge pushed further down the canvas -- more
    # top margin reserved than a plain per-axes title band alone would need.
    assert all(n[3] < b[3] for b, n in zip(before, after))
    assert all((n[1] + n[3]) < (b[1] + b[3]) for b, n in zip(before, after))


def test_group_left_right_title_reserves_width_not_a_height_allowance():
    """Regression: a left/right title runs horizontally alongside its box, so
    the margin tight_layout() reserves for it has to fit the title's own
    rendered *width* -- reusing the top/bottom formula (a height allowance)
    reserved far too little for anything but the shortest titles, clipping
    the text at the canvas edge or overlapping whatever's beside it."""
    fig1, axes1 = _grid_2x2()
    fig1.tight_layout()
    without_group = axes1[0, 0]._rect[0]

    fig2, axes2 = _grid_2x2()
    long_title = "A considerably long left-side group title"
    fig2.group(long_title, [axes2[0, 0], axes2[1, 0]], title_position="left")
    fig2.tight_layout()
    with_group = axes2[0, 0]._rect[0]

    from plotpress.style import Style

    expected_extent = 8.0 + Style().text_width(long_title, Style().title_size, bold=True) + 12
    left_before_px = without_group * fig1.figsize[0] * fig1.style.dpi
    left_after_px = with_group * fig2.figsize[0] * fig2.style.dpi
    assert (left_after_px - left_before_px) >= expected_extent - 1.0, (
        "reserved left margin does not fit the title's own rendered width")


def test_group_not_facing_the_outer_edge_reserves_no_margin():
    """An interior group (its title-facing edge is a row/col gap, not the
    figure's own outer edge) is left to that existing gap -- growing the
    whole grid's margin for it would be wrong for every other row/col."""
    fig1, axes1 = _grid_2x2()
    fig1.tight_layout()
    without_group = [a._rect for a in axes1.ravel()]

    fig2, axes2 = _grid_2x2()
    # Bottom row grouped with a *top*-facing title: doesn't reach row 0.
    fig2.group("Interior", [axes2[1, 0], axes2[1, 1]], title_position="top")
    fig2.tight_layout()
    with_group = [a._rect for a in axes2.ravel()]
    assert with_group == without_group


def test_group_spanning_multiple_rows_still_reserves_top_margin():
    """Regression: the outer-edge check used to require *every* axes in the
    group to share row0 == 0, so a group spanning a whole column-band (every
    row, a handful of columns) -- which does reach row 0, just not made up
    entirely of row-0 axes -- silently reserved no margin at all, and its
    title clipped the top of the canvas. The check has to be "the group's
    bounding box reaches row 0", i.e. the *minimum* row0 among its axes."""
    fig1, axes1 = plotpress.subplots(3, 3, figsize=(6, 6))
    for ax in axes1.ravel():
        ax.plot([0, 1], [0, 1])
    fig1.tight_layout()
    before = [a._rect for a in axes1.ravel()]

    fig2, axes2 = plotpress.subplots(3, 3, figsize=(6, 6))
    for ax in axes2.ravel():
        ax.plot([0, 1], [0, 1])
    # Spans all 3 rows of column 0 -- touches row 0, but most of its axes
    # (rows 1-2) do not have row0 == 0 themselves.
    fig2.group("Left column", list(axes2[:, 0]), title_position="top")
    fig2.tight_layout()
    after = [a._rect for a in axes2.ravel()]
    assert all((n[1] + n[3]) < (b[1] + b[3]) for b, n in zip(before, after)), (
        "a multi-row group touching the top edge reserved no top margin")


def test_group_margin_reservation_does_not_widen_interior_row_gaps():
    """Regression: the group's own margin reservation was added to the same
    top_px/bottom_px/etc. accumulators that also seed the *interior* row/col
    gap (gap_h/gap_w) -- a group's title only ever faces an outer edge, so
    folding its reservation into those inflated every gap between every row
    or column in the grid, not just the true outer margin."""
    fig1, axes1 = plotpress.subplots(3, 2, figsize=(6, 6))
    for ax in axes1.ravel():
        ax.plot([0, 1], [0, 1])
    fig1.tight_layout()
    gap_without_group = axes1[0, 0]._rect[1] - (axes1[1, 0]._rect[1] + axes1[1, 0]._rect[3])

    fig2, axes2 = plotpress.subplots(3, 2, figsize=(6, 6))
    for ax in axes2.ravel():
        ax.plot([0, 1], [0, 1])
    # A large title, so its reservation would be easy to spot leaking into
    # the interior row gap if it weren't properly excluded from it.
    fig2.group("A tall group title", list(axes2[:, 0]), title_position="top",
              fontsize=40)
    fig2.tight_layout()
    gap_with_group = axes2[0, 0]._rect[1] - (axes2[1, 0]._rect[1] + axes2[1, 0]._rect[3])

    assert gap_with_group == pytest.approx(gap_without_group, abs=0.5), (
        "a group's own margin reservation leaked into the interior row gap: "
        "%r vs %r" % (gap_with_group, gap_without_group))


def test_group_spacing_widens_only_the_interior_gap_not_the_outer_margin():
    """group_spacing()'s whole point: add room between subplots for group
    boxes without touching anything tight_layout() already sizes on its
    own. The figure grows to hold that room rather than shrinking the axes
    to fit it, so the outer margin and each axes' own size must land at
    exactly the same *pixel* position/size with or without it -- the plain
    axes-rect *fractions* do shift a little, since they are now measured
    against a taller canvas."""
    fig1, axes1 = plotpress.subplots(2, 2, figsize=(9, 7))
    for ax in axes1.ravel():
        ax.plot([0, 1], [0, 1])
        ax.set_title("panel")
    fig1.group("Group A", list(axes1[0, :]), title_position="top")
    fig1.group("Group B", list(axes1[1, :]), title_position="top")
    fig1.tight_layout()
    Hpx1 = fig1.figsize[1] * fig1.style.dpi
    top_frac_before = max(ax._rect[1] + ax._rect[3] for ax in axes1.ravel())
    bottom_frac_before = min(ax._rect[1] for ax in axes1.ravel())
    top_margin_before = (1 - top_frac_before) * Hpx1
    bottom_margin_before = bottom_frac_before * Hpx1
    axh_before = axes1[0, 0]._rect[3] * Hpx1
    row_gap_before = (min(axes1[0, 0]._rect[1], axes1[0, 1]._rect[1])
                     - max(axes1[1, 0]._rect[1] + axes1[1, 0]._rect[3],
                            axes1[1, 1]._rect[1] + axes1[1, 1]._rect[3])) * Hpx1

    fig2, axes2 = plotpress.subplots(2, 2, figsize=(9, 7))
    for ax in axes2.ravel():
        ax.plot([0, 1], [0, 1])
        ax.set_title("panel")
    fig2.group("Group A", list(axes2[0, :]), title_position="top")
    fig2.group("Group B", list(axes2[1, :]), title_position="top")
    fig2.group_spacing(hspace=40.0)
    fig2.tight_layout()
    Hpx2 = fig2.figsize[1] * fig2.style.dpi
    top_frac_after = max(ax._rect[1] + ax._rect[3] for ax in axes2.ravel())
    bottom_frac_after = min(ax._rect[1] for ax in axes2.ravel())
    top_margin_after = (1 - top_frac_after) * Hpx2
    bottom_margin_after = bottom_frac_after * Hpx2
    axh_after = axes2[0, 0]._rect[3] * Hpx2
    row_gap_after = (min(axes2[0, 0]._rect[1], axes2[0, 1]._rect[1])
                    - max(axes2[1, 0]._rect[1] + axes2[1, 0]._rect[3],
                           axes2[1, 1]._rect[1] + axes2[1, 1]._rect[3])) * Hpx2

    assert Hpx2 - Hpx1 == pytest.approx(40.0, abs=1e-6), (
        "group_spacing() must grow the figure by exactly the reserved "
        "pixels rather than shrinking the axes to make room for it")
    assert top_margin_after == pytest.approx(top_margin_before, abs=0.5)
    assert bottom_margin_after == pytest.approx(bottom_margin_before, abs=0.5)
    assert axh_after == pytest.approx(axh_before, abs=0.5), (
        "each axes' own pixel size must be unaffected by group_spacing() "
        "-- the figure grows instead of shrinking it")
    assert (row_gap_after - row_gap_before) == pytest.approx(40.0, abs=0.5)


def test_group_spacing_does_not_widen_a_gap_interior_to_a_single_group():
    """group_spacing() must only widen the boundary between two different
    groups, not a boundary the same group's own box straddles -- a group
    spanning rows 0-1 stays exactly as tight between those two rows as
    plain tight_layout() would put them; only the seam facing its neighbor
    (rows 1-2) needs the reserved room. Reported after group_spacing()
    widened every row gap uniformly, needlessly separating panels meant to
    read as one paired unit (see plot_05_many_small_row_pairs)."""
    def build(hspace):
        fig, axes = plotpress.subplots(4, 1, figsize=(4, 12))
        for ax in axes:
            ax.plot([0, 1], [0, 1])
        fig.group("Pair A", [axes[0], axes[1]], title_position="top")
        fig.group("Pair B", [axes[2], axes[3]], title_position="top")
        if hspace:
            fig.group_spacing(hspace=hspace)
        fig.tight_layout()
        return fig, axes

    fig0, axes0 = build(None)
    Hpx0 = fig0.figsize[1] * fig0.style.dpi
    within_pair_gap_before = (axes0[0]._rect[1]
                              - (axes0[1]._rect[1] + axes0[1]._rect[3])) * Hpx0

    fig1, axes1 = build(70.0)
    Hpx1 = fig1.figsize[1] * fig1.style.dpi
    within_pair_gap_after = (axes1[0]._rect[1]
                             - (axes1[1]._rect[1] + axes1[1]._rect[3])) * Hpx1
    between_pair_gap_after = (axes1[1]._rect[1]
                              - (axes1[2]._rect[1] + axes1[2]._rect[3])) * Hpx1

    assert within_pair_gap_after == pytest.approx(within_pair_gap_before, abs=0.5), (
        "group_spacing(hspace=...) widened the gap *inside* a single "
        "group's own pair of rows, not just the boundary between groups")
    assert between_pair_gap_after - within_pair_gap_before == pytest.approx(70.0, abs=0.5)


def test_group_spacing_grows_figsize_by_the_reserved_amount():
    """The figure's own size grows by exactly the pixels group_spacing()
    reserves -- once per boundary that actually needs it, not once per
    interior gap in the grid."""
    fig, axes = plotpress.subplots(3, 1, figsize=(4, 9))
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    # One group spanning rows 0-1: only the row1/row2 boundary borders it,
    # so exactly one boundary (not two) needs the reservation.
    fig.group("Pair", [axes[0], axes[1]], title_position="top")
    fig.group_spacing(hspace=55.0)
    fig.tight_layout()

    assert fig.figsize[1] == pytest.approx(9.0 + 55.0 / fig.style.dpi, abs=1e-6)
    assert fig.figsize[0] == pytest.approx(4.0, abs=1e-9)

    # A second tight_layout() call (e.g. from _settle_layout re-fitting
    # after a later title change) must not compound the growth.
    fig.tight_layout()
    assert fig.figsize[1] == pytest.approx(9.0 + 55.0 / fig.style.dpi, abs=1e-6)


def test_group_spacing_resolves_a_real_interior_boundary_collision():
    """The motivating case: two groups facing each other across an interior
    row boundary, neither title touching it, collide with plain
    tight_layout() -- group_spacing(hspace=...) must be able to fix that
    without falling back to subplots_adjust (which would also discard the
    automatic title/tick-label margins)."""
    def build(hspace):
        fig, axes = plotpress.subplots(2, 2, figsize=(9, 7))
        for ax in axes.ravel():
            ax.plot([0, 1], [0, 1])
            ax.set_title("panel")
        fig.group("Group A", list(axes[0, :]), title_position="top")
        fig.group("Group B", list(axes[1, :]), title_position="top")
        if hspace:
            fig.group_spacing(hspace=hspace)
        fig.tight_layout()
        return fig

    def box_gap(fig):
        root = _parse(fig.to_svg())
        boxes = sorted(
            (float(r.get("y")), float(r.get("y")) + float(r.get("height")))
            for r in root.findall(f".//{NS}rect") if r.get("fill") == "none"
        )
        return boxes[1][0] - boxes[0][1]

    assert box_gap(build(None)) < 0, (
        "the fixture must actually collide without group_spacing, or this "
        "test proves nothing")
    assert box_gap(build(40.0)) > 0


def test_group_spacing_defaults_leave_layout_unchanged():
    """No group_spacing() call must be a complete no-op -- existing figures
    that never touch it see byte-for-byte the same layout as before it
    existed."""
    fig1, axes1 = plotpress.subplots(2, 2)
    for ax in axes1.ravel():
        ax.plot([0, 1], [0, 1])
    fig1.group("A", list(axes1[0, :]))
    fig1.tight_layout()

    fig2, axes2 = plotpress.subplots(2, 2)
    for ax in axes2.ravel():
        ax.plot([0, 1], [0, 1])
    fig2.group("A", list(axes2[0, :]))
    fig2.group_spacing()   # no args: must change nothing
    fig2.tight_layout()

    assert fig1.to_svg() == fig2.to_svg()


def test_sup_labels_do_not_widen_interior_grid_gaps():
    """Regression: suptitle()/supxlabel()/supylabel() added straight into
    top_px/bottom_px/left_px -- the same accumulators that also seed the
    *interior* row/col gap (gap_h/gap_w) -- so a figure-level label, drawn
    once outside the whole grid, ended up widening every gap between every
    row or column in the grid too, not just the true outer margin."""
    fig1, axes1 = plotpress.subplots(3, 3, figsize=(9, 9))
    for ax in axes1.ravel():
        ax.plot([0, 1], [0, 1])
    fig1.tight_layout()
    col_gap_before = axes1[0, 1]._rect[0] - (axes1[0, 0]._rect[0] + axes1[0, 0]._rect[2])
    row_gap_before = axes1[1, 0]._rect[1] - (axes1[0, 0]._rect[1] + axes1[0, 0]._rect[3])

    fig2, axes2 = plotpress.subplots(3, 3, figsize=(9, 9))
    for ax in axes2.ravel():
        ax.plot([0, 1], [0, 1])
    fig2.suptitle("Overall title")
    fig2.supxlabel("shared x label")
    fig2.supylabel("shared y label")
    fig2.tight_layout()
    col_gap_after = axes2[0, 1]._rect[0] - (axes2[0, 0]._rect[0] + axes2[0, 0]._rect[2])
    row_gap_after = axes2[1, 0]._rect[1] - (axes2[0, 0]._rect[1] + axes2[0, 0]._rect[3])

    assert col_gap_after == pytest.approx(col_gap_before, abs=0.5), (
        "supylabel()'s own left-margin reservation leaked into the interior "
        "column gap: %r vs %r" % (col_gap_after, col_gap_before))
    assert row_gap_after == pytest.approx(row_gap_before, abs=0.5), (
        "suptitle()/supxlabel()'s own margin reservation leaked into the "
        "interior row gap: %r vs %r" % (row_gap_after, row_gap_before))


def test_group_titles_do_not_collide_with_suptitle_or_a_reserving_legend():
    """A group's title reservation has to stack correctly with the *other*
    figure-level bands, not just its own axes -- a suptitle above a
    top-facing group title, and a space-reserving figure legend below a
    bottom-facing one, each independently carve space out of
    tight_layout()'s top_px/bottom_px accumulators, and none of the three
    should ever end up drawn on top of another.

    4 rows, not 2: rows 1-2 are plain, ungrouped axes separating "Top row"
    and "Bottom row" -- neither group's title faces the interior boundary
    it would otherwise share with the other (a documented, separately
    tested limitation: an interior boundary gets no automatic reservation
    unless a title actually faces it), so two rows immediately adjacent
    would collide with each other regardless of the figure-level bands this
    test is actually about.
    """
    fig, axes = plotpress.subplots(4, 3, figsize=(10, 8))
    x = np.array([0.0, 1.0])
    for ax in axes.ravel():
        ax.plot(x, x, label="line")
    fig.suptitle("Suite-wide QA sweep")
    fig.legend(loc="lower center")   # a *reserving* placement, unlike an overlay
    fig.group("Top row", list(axes[0]), title_position="top", color="#2ca02c")
    fig.group("Bottom row", list(axes[3]), title_position="bottom", color="#9467bd")
    fig.tight_layout()
    root = _parse(fig.to_svg())

    texts = {t.text: float(t.get("y")) for t in root.findall(f".//{NS}text")
             if t.text in ("Suite-wide QA sweep", "Top row", "Bottom row")}
    boxes = sorted(
        (float(r.get("y")), float(r.get("y")) + float(r.get("height")))
        for r in root.findall(f".//{NS}rect") if r.get("fill") == "none"
    )
    legend_rect = root.find(f'.//{NS}g[@class="plotpress-legend"]//{NS}rect')
    legend_top = float(legend_rect.get("y"))

    # Top to bottom: suptitle, "Top row"'s title, its box, "Bottom row"'s
    # box, its title, then the legend -- each strictly below the last.
    assert texts["Suite-wide QA sweep"] < texts["Top row"] < boxes[0][0]
    assert boxes[0][1] < boxes[1][0]
    assert boxes[1][1] < texts["Bottom row"] < legend_top


def test_group_renders_in_both_backends():
    from plotpress import raster

    fig, axes = _grid_2x2()
    fig.group("A", [axes[0, 0], axes[0, 1]])
    assert "A" in fig.to_svg()
    assert raster.figure_to_image(fig, scale=1) is not None


def test_group_box_wraps_a_colorbar_belonging_entirely_to_its_axes():
    """Regression: a colorbar steals its space from right next to the axes
    it's attached to, but the group's box was computed from g["axes"] alone
    -- a per-axes colorbar sat entirely outside the box meant to enclose it.
    A colorbar shared with an axes *outside* the group must NOT pull the box
    out to wrap it, since that would misrepresent what the group actually is.
    """
    import numpy as np

    fig, axes = plotpress.subplots(1, 3, figsize=(9, 3))
    meshes = [ax.pcolormesh(np.arange(4).reshape(2, 2).astype(float)) for ax in axes]
    fig.colorbar(meshes[0], ax=axes[0])
    shared = fig.colorbar(meshes[1], ax=[axes[1], axes[2]])   # shared with an outside axes
    fig.group("Group", [axes[0], axes[1]])
    fig.tight_layout()

    root = _parse(fig.to_svg())
    box = [b for b in root.findall(f".//{NS}rect") if b.get("fill") == "none"][0]
    bx0, by0 = float(box.get("x")), float(box.get("y"))
    bx1 = bx0 + float(box.get("width"))
    by1 = by0 + float(box.get("height"))

    images = root.findall(f".//{NS}image")
    own_cbar_img = images[0]   # axes[0]'s own colorbar -- the first mesh/colorbar drawn
    ix0, iy0 = float(own_cbar_img.get("x")), float(own_cbar_img.get("y"))
    ix1 = ix0 + float(own_cbar_img.get("width"))
    iy1 = iy0 + float(own_cbar_img.get("height"))
    assert bx0 <= ix0 and by0 <= iy0 and ix1 <= bx1 and iy1 <= by1, (
        "axes[0]'s own colorbar must be fully contained in the group's box")

    shared_cbar_img = images[-1]   # the colorbar shared with axes[2], outside the group
    sx1 = float(shared_cbar_img.get("x")) + float(shared_cbar_img.get("width"))
    assert sx1 > bx1, (
        "a colorbar shared with an axes outside the group must not pull the "
        "box out to wrap it")


def test_colorbar_title_renders_in_both_backends():
    """Regression: a colorbar axes returned early out of _render_axes/
    _raster_axes before ever reaching the title-drawing code, so
    fig.colorbar(mesh, ax=ax).set_title("units") -- documented as this
    library's own convention for labeling a colorbar's scale -- never
    actually appeared in either backend's output."""
    import numpy as np
    from plotpress import raster

    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.arange(4).reshape(2, 2).astype(float))
    fig.colorbar(mesh, ax=ax).set_title("units")
    assert "units" in fig.to_svg()
    assert raster.figure_to_image(fig, scale=1) is not None


def test_group_rejects_empty_or_foreign_axes_and_bad_title_position():
    fig, axes = _grid_2x2()
    with pytest.raises(ValueError, match="at least one axes"):
        fig.group("bad", [])

    other_fig, other_ax = plotpress.subplots()
    with pytest.raises(ValueError, match="must belong to this figure"):
        fig.group("bad", [other_ax])

    with pytest.raises(ValueError, match="title_position"):
        fig.group("bad", [axes[0, 0]], title_position="center")


def test_group_absent_without_the_call():
    fig, _ = _grid_2x2()
    svg = fig.to_svg()
    assert _parse(svg) is not None   # still well-formed
    assert "stroke-dasharray" not in svg


# -- mesh orientation and inverted axes -------------------------------------

def _mesh_image_box(draw):
    """The x/y/width/height of the <image> a mesh emits."""
    fig, ax = plotpress.subplots(figsize=(4.0, 3.0))
    draw(ax)
    el = _parse(fig.to_svg()).find(".//" + NS + "image")
    assert el is not None, "no <image> emitted"
    return [float(el.attrib[a]) for a in ("x", "y", "width", "height")]


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
