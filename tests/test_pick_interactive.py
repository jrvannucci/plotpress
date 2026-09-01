"""End-to-end point-picking tests: real clicks in a real browser.

The picking logic lives in JavaScript (``plotpress/_interactive.py``), so the
rest of the suite can only check the payloads that feed it. These tests close
that gap: they load an interactive figure in a headless Chromium, click at the
pixel where the renderer drew a known datum, and assert the marker reports that
datum -- the thing a user actually cares about.

Opt-in, because they need a browser::

    pip install -e ".[browser]" && playwright install chromium
    pytest tests/test_pick_interactive.py

They are deselected by default via the ``browser`` marker (see pyproject.toml),
and skip cleanly when Playwright or its Chromium download is missing, so a
standard ``pytest`` run is unaffected.
"""

import json
import pathlib

import pytest

from pick_cases import build_cases

pytestmark = pytest.mark.browser

HARNESS = (pathlib.Path(__file__).parent / "pick_harness.js").read_text()


@pytest.fixture(scope="module")
def page():
    """A headless Chromium page, shared across cases (launching one is slow)."""
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="needs Playwright: pip install -e '.[browser]'")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except sync_api.Error as exc:                     # pragma: no cover
            pytest.skip("Chromium is not installed: run 'playwright install "
                        "chromium' (%s)" % exc)
        p = browser.new_page(viewport={"width": 1100, "height": 850})
        try:
            yield p
        finally:
            browser.close()


def _run(page, tmp_path, case):
    """Load the figure and return the harness's per-target results."""
    # Unmodified to_html() output -- the tests drive exactly what users get.
    path = tmp_path / ("%s.html" % case.name)
    path.write_text(case.fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    out = page.evaluate(HARNESS, case.targets)
    assert not errors, "JavaScript errors on %s: %s" % (case.name, errors)
    assert "error" in out or "results" in out
    if out.get("error"):
        pytest.fail("%s: %s" % (case.name, out["error"]))
    return out["results"]


@pytest.mark.parametrize("case", build_cases(), ids=lambda c: c.name)
def test_click_picks_the_right_point(page, tmp_path, case):
    """Clicking a drawn datum must produce a marker reporting that datum."""
    failures = []
    for r in _run(page, tmp_path, case):
        if r["bad"]:
            failures.append(
                "  target %d at pixel (%.1f, %.1f)\n"
                "    expected: %s\n"
                "    got:      %s\n"
                "    mismatch: %s"
                % (r["target"], r["px"][0], r["px"][1],
                   json.dumps(r["expect"], sort_keys=True),
                   json.dumps(r["got"], sort_keys=True),
                   "; ".join(r["bad"])))
    assert not failures, "%s (%s)\n%s" % (
        case.name, case.note or "picked the wrong point", "\n".join(failures))


def test_click_on_empty_space_makes_no_stray_marker(page, tmp_path):
    """A click outside any axes must not drop a marker."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    path = tmp_path / "empty.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    n = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button')
            .forEach(b => { if (b.textContent === 'Point Pick') b.click(); });
          // (2, 2) in SVG user space is the figure's top-left margin, well
          // outside the axes rectangle.
          const pt = svg.createSVGPoint();
          pt.x = 2; pt.y = 2;
          const c = pt.matrixTransform(svg.getScreenCTM());
          (document.elementFromPoint(c.x, c.y) || svg).dispatchEvent(
            new MouseEvent('click', {bubbles: true, clientX: c.x, clientY: c.y}));
          return window.plotpressGetMarkers().length;
        }""")
    assert n == 0, "a click in the margin created %d marker(s)" % n


def test_marker_radius_scales_with_its_own_axes_size(page, tmp_path):
    """Regression: a marker's dot used a flat 3.5px radius regardless of the
    axes it landed on -- fine on one normal-sized axes, but a boulder on a
    tiny panel in a large grid (100 axes on one figure, say). It must scale
    down with the axes' own pixel size, not just look identical everywhere,
    while still never shrinking below a comfortably clickable minimum."""
    import numpy as np
    import plotpress
    from pick_cases import px

    fig_small, ax = plotpress.subplots(figsize=(6, 4.8))
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path_small = tmp_path / "marker_size_single_axes.html"
    path_small.write_text(fig_small.to_html(interactive=True), encoding="utf-8")

    fig_grid, axes = plotpress.subplots(10, 10, figsize=(6, 4.8))
    for a in np.asarray(axes).ravel():
        a.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path_grid = tmp_path / "marker_size_10x10_grid.html"
    path_grid.write_text(fig_grid.to_html(interactive=True), encoding="utf-8")

    def picked_radius(path, fig, ax_index=0):
        page.goto(path.as_uri())
        ux, uy = px(fig, ax_index, 1.0, 1.0)
        page.evaluate(
            """() => document.querySelectorAll('.plotpress-toolbar button')
                 .forEach(b => { if (b.textContent === 'Point Pick') b.click(); })""")
        page.mouse.click(*page.evaluate(
            """([ux, uy]) => {
              const svg = document.getElementById('plotpress-svg');
              const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
              const c = pt.matrixTransform(svg.getScreenCTM());
              return [c.x, c.y];
            }""", [ux, uy]))
        return page.evaluate(
            "() => +document.querySelector('.plotpress-pin circle').getAttribute('r')")

    r_single = picked_radius(path_small, fig_small)
    r_grid = picked_radius(path_grid, fig_grid)
    assert r_grid < r_single, (
        "a marker on a tiny panel in a 10x10 grid (%.2f) must be smaller than "
        "one on a normal single axes (%.2f)" % (r_grid, r_single))
    assert r_grid >= 2.0 * 1.4, (
        "even shrunk, a freshly-picked (selected) marker must stay "
        "comfortably visible/clickable: got %.2f" % r_grid)


def test_marker_stays_a_constant_screen_size_across_magnify_zoom(page, tmp_path):
    """Regression: a pin's dot/label used absolute cx/cy/x/y baked straight
    into its SVG children, with no compensation for whole-figure zoom --
    Magnify/Zoom grow the *entire* SVG's rendered CSS size uniformly (see
    _interactive.py's applyZoomSize), which carried a pin's fixed radius up
    right along with it: readable as a small dot at rest, but a blob tens of
    pixels across a few zoom ticks later, covering the very mesh cell it was
    meant to point at -- worst on a large many-panel grid, where each panel
    (and so each mesh cell) starts out tiny to begin with. A pin's own
    on-screen size must stay constant at any zoom level."""
    import numpy as np
    import plotpress
    from pick_cases import px

    fig, axes = plotpress.subplots(8, 8, figsize=(16, 12))
    x = np.linspace(0, 10, 11)
    y = np.linspace(0, 5, 6)
    X, Y = np.meshgrid(x, y)
    for i, ax in enumerate(axes.ravel()):
        Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
        ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
        ax.tick_params(labelsize=4)
    fig.tight_layout()
    path = tmp_path / "marker_constant_size_under_magnify.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 18, 3.0, 5.0)
    _click_mode(page, "Point Pick", ux, uy)
    diameter_before = page.evaluate(
        "() => document.querySelector('.plotpress-pin circle')"
        ".getBoundingClientRect().width")

    svg_width_before = page.evaluate(
        "() => document.getElementById('plotpress-svg').getBoundingClientRect().width")
    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Magnify') b.click(); })""")
    page.evaluate(
        """([ux, uy]) => {
          const svg = document.getElementById('plotpress-svg');
          const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
          const c = pt.matrixTransform(svg.getScreenCTM());
          for (let i = 0; i < 8; i++) {
            document.elementFromPoint(c.x, c.y).dispatchEvent(new WheelEvent('wheel', {
              bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, deltaY: -100}));
          }
        }""", [ux, uy])
    svg_width_after = page.evaluate(
        "() => document.getElementById('plotpress-svg').getBoundingClientRect().width")
    diameter_after = page.evaluate(
        "() => document.querySelector('.plotpress-pin circle')"
        ".getBoundingClientRect().width")

    assert svg_width_after > svg_width_before * 3, (
        "the fixture must actually zoom substantially, or this test proves "
        "nothing: %.0f -> %.0f" % (svg_width_before, svg_width_after))
    assert diameter_after == pytest.approx(diameter_before, rel=0.02), (
        "a pin's on-screen size must stay constant across Magnify zoom: "
        "%.2fpx before, %.2fpx after zooming %.1fx" %
        (diameter_before, diameter_after, svg_width_after / svg_width_before))


def test_mesh_pick_reads_correct_value_through_float16_encoding(page, tmp_path):
    """binary_pick_data's float16 tier (chosen only at low enough
    pick_precision for a bounded-range mesh -- see figure._fits_float16) has
    no native Float16Array to fall back on if the hand-written JS decode
    (_interactive.py's halfToFloat) is wrong, so this drives a real click
    through it end to end rather than trusting the Python-side round-trip
    check alone. Every case in the main parametrized suite uses the default
    pick_precision=6, which never selects float16 (see the module docstring
    for _encode_binary_arrays), so nothing else in this file exercises this
    path."""
    import numpy as np
    import plotpress
    from pick_cases import px

    ny, nx = 40, 50
    rows, cols = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    Z = np.sin(rows * 0.3) * np.cos(cols * 0.3)   # bounded to [-1, 1]
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(nx + 1, dtype=float), np.arange(ny + 1, dtype=float), Z)

    html = fig.to_html(interactive=True, pick_precision=2)
    assert '"__f16__"' in html   # sanity: this figure actually exercises the tier
    path = tmp_path / "float16_mesh.html"
    path.write_text(html, encoding="utf-8")
    page.goto(path.as_uri())

    # Select the tool once: re-clicking an already-active toolbar button
    # toggles it *off* (single-selection toolbar), which _click_mode's
    # unconditional click would do on every target after the first.
    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Point Pick'
                                  && !b.classList.contains('active')) b.click(); })""")

    for row, col in [(0, 0), (12, 30), (39, 49), (20, 25)]:
        ux, uy = px(fig, 0, col + 0.5, row + 0.5)
        markers = page.evaluate(
            """([ux, uy]) => {
              document.querySelectorAll('.plotpress-pin').forEach(p => p.remove());
              const svg = document.getElementById('plotpress-svg');
              const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
              const c = pt.matrixTransform(svg.getScreenCTM());
              const el = document.elementFromPoint(c.x, c.y) || svg;
              el.dispatchEvent(new MouseEvent('click', {
                bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
              return window.plotpressGetMarkers();
            }""", [ux, uy])
        assert len(markers) == 1, "click at cell (%d, %d) made %d marker(s)" % (
            row, col, len(markers))
        got = markers[0]["z"]
        expected = round(float(Z[row, col]), 2)
        assert got == pytest.approx(expected, abs=0.01), (
            "cell (%d, %d): expected z~=%.2f, got %r" % (row, col, expected, got))


def test_downsampled_mesh_pick_reads_correct_value(page, tmp_path):
    """A rectilinear mesh over pick_max_mesh_cells is block-averaged before
    embedding (see svg._downsample_grid) rather than dropped, so a click
    still answers with a real value -- covered at the payload-shape level by
    test_pick_data_omits_oversized_series_but_downsamples_oversized_meshes
    in test_svg_output.py, but nothing drove a real click through the
    downsampled cell lookup end to end: every mesh case in pick_cases.py
    stays under the default cap, so bucketIndex() bucketing a click into a
    *coarsened* cell (rather than the original grid) was never actually
    exercised by a browser."""
    import numpy as np
    import plotpress
    from pick_cases import px
    from plotpress.svg import pick_data

    ny, nx = 40, 50
    rows, cols = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    Z = (rows * nx + cols).astype(float)   # distinct value per cell
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(nx + 1, dtype=float), np.arange(ny + 1, dtype=float), Z)

    CAP = 200
    pd = pick_data(fig, max_mesh_cells=CAP)[0]["meshes"][0]
    dny, dnx = pd["shape"]
    assert dny * dnx <= CAP < ny * nx   # sanity: this really downsamples

    html = fig.to_html(interactive=True, pick_max_mesh_cells=CAP)
    path = tmp_path / "downsampled_mesh.html"
    path.write_text(html, encoding="utf-8")
    page.goto(path.as_uri())

    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Point Pick'
                                  && !b.classList.contains('active')) b.click(); })""")

    xe, ye = pd["xedges"], pd["yedges"]
    for row, col in [(0, 0), (dny - 1, dnx - 1), (dny // 2, dnx // 2)]:
        cx = (xe[col] + xe[col + 1]) / 2.0
        cy = (ye[row] + ye[row + 1]) / 2.0
        ux, uy = px(fig, 0, cx, cy)
        markers = page.evaluate(
            """([ux, uy]) => {
              document.querySelectorAll('.plotpress-pin').forEach(p => p.remove());
              const svg = document.getElementById('plotpress-svg');
              const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
              const c = pt.matrixTransform(svg.getScreenCTM());
              const el = document.elementFromPoint(c.x, c.y) || svg;
              el.dispatchEvent(new MouseEvent('click', {
                bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
              return window.plotpressGetMarkers();
            }""", [ux, uy])
        assert len(markers) == 1, "downsampled cell (%d, %d): click made %d marker(s)" % (
            row, col, len(markers))
        got = markers[0]["z"]
        expected = pd["z"][row * dnx + col]
        assert got == pytest.approx(expected, abs=1e-3), (
            "downsampled cell (%d, %d): expected z=%r, got %r" % (row, col, expected, got))


def test_downsampled_curvilinear_mesh_pick_reads_correct_value(page, tmp_path):
    """A curvilinear mesh over the cap downsamples both its z grid *and* its
    per-cell centers (see svg.pick_data's curvilinear branch, which block-
    averages xc/yc the same way as z) -- nothing in pick_cases.py builds a
    curvilinear grid anywhere near pick_max_mesh_cells, so this path was
    never driven through a real click either."""
    import math

    import numpy as np
    import plotpress
    from pick_cases import px
    from plotpress.svg import pick_data

    n = 40   # (n-1)*(n-1) = 1521 cells, comfortably over a small cap
    r = np.linspace(0.3, 1, n)
    th = np.linspace(0, 1.5 * math.pi, n)
    R, TH = np.meshgrid(r, th)
    CX, CY = R * np.cos(TH), R * np.sin(TH)
    CZ = np.arange((n - 1) * (n - 1), dtype=float).reshape(n - 1, n - 1)
    fig, ax = plotpress.subplots(figsize=(6, 5))
    m = ax.pcolormesh(CX, CY, CZ, cmap="plasma")
    assert m.curvilinear

    CAP = 200
    pd = pick_data(fig, max_mesh_cells=CAP)[0]["meshes"][0]
    dny, dnx = pd["shape"]
    assert dny * dnx <= CAP < (n - 1) * (n - 1)   # sanity: this really downsamples
    assert "xc" in pd and "yc" in pd

    html = fig.to_html(interactive=True, pick_max_mesh_cells=CAP)
    path = tmp_path / "downsampled_curvilinear_mesh.html"
    path.write_text(html, encoding="utf-8")
    page.goto(path.as_uri())

    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Point Pick'
                                  && !b.classList.contains('active')) b.click(); })""")

    for idx in (0, dny * dnx // 2, dny * dnx - 1):
        ux, uy = px(fig, 0, pd["xc"][idx], pd["yc"][idx])
        markers = page.evaluate(
            """([ux, uy]) => {
              document.querySelectorAll('.plotpress-pin').forEach(p => p.remove());
              const svg = document.getElementById('plotpress-svg');
              const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
              const c = pt.matrixTransform(svg.getScreenCTM());
              const el = document.elementFromPoint(c.x, c.y) || svg;
              el.dispatchEvent(new MouseEvent('click', {
                bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
              return window.plotpressGetMarkers();
            }""", [ux, uy])
        assert len(markers) == 1, "downsampled curvilinear cell %d: click made %d marker(s)" % (
            idx, len(markers))
        got = markers[0]["z"]
        expected = pd["z"][idx]
        assert got == pytest.approx(expected, abs=1e-3), (
            "downsampled curvilinear cell %d: expected z=%r, got %r" % (idx, expected, got))


# -- vector-cell (rasterized=) mesh picking ----------------------------------
#
# Picking is computed from the embedded pick payload's own cell edges, mapped
# through the *current* view transform -- never by reading which DOM element
# the click landed on -- so it should be indifferent to whether a mesh drew as
# one <image> or one <rect> per cell. These tests drive that through a real
# click rather than trust the reasoning: they specifically target the cell a
# raster resample would drop (see plot_04_pcolormesh_vs_imshow.py), confirming
# it is both visible and clickable once rasterized=False (or auto) vectorizes
# it, and that a click still finds it correctly after the axes is zoomed and
# panned -- proving the vector <rect>s ride the same zoom-group affine every
# other artist does, not just that they exist in the SVG.

def _extreme_mesh(rasterized):
    """The gallery example's 4000:1 grid: cell (0, 0) is 1/4000 of the x span."""
    import numpy as np
    import plotpress

    edges = np.array([0.0, 0.01, 2.0, 6.0, 16.0, 40.0])
    y_edges = np.array([0.0, 0.5, 1.0])
    field = np.tile(np.arange(5.0), (2, 1))
    fig, ax = plotpress.subplots(figsize=(6, 5))
    mesh = ax.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=rasterized)
    return fig, ax, mesh, edges, y_edges, field


@pytest.mark.parametrize("rasterized", [None, False], ids=["auto", "forced_vector"])
def test_vector_mesh_thin_cell_is_clickable_and_reads_its_value(page, tmp_path, rasterized):
    """The cell a forced raster would drop must be pickable once it vectorizes."""
    from pick_cases import px

    fig, ax, mesh, edges, y_edges, field = _extreme_mesh(rasterized)
    assert mesh.vectorized   # sanity: this case must actually exercise vector cells

    path = tmp_path / ("vector_mesh_thin_cell_%s.html" % rasterized)
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ccx, ccy = (edges[0] + edges[1]) / 2.0, (y_edges[0] + y_edges[1]) / 2.0  # cell (0, 0)
    markers = _click_mode(page, "Point Pick", *px(fig, 0, ccx, ccy))
    assert len(markers) == 1, "click on the thin cell made %d marker(s)" % len(markers)
    assert markers[0]["z"] == pytest.approx(float(field[0, 0]))


def test_vector_mesh_stays_pickable_after_zoom(page, tmp_path):
    """The thin cell must still resolve correctly once the axes view has
    narrowed -- proving the vector <rect>s sit inside the same per-axes zoom
    group (svg._render_axes' ``<g class="plotpress-zoom">``) every other
    artist's geometry does, remapped by the same affine, not drawn outside it
    at stale positions the way test_point_pick_large_series_stays_accurate_
    after_zoom guards a large line series against."""
    from pick_cases import px

    fig, ax, mesh, edges, y_edges, field = _extreme_mesh(rasterized=None)
    assert mesh.vectorized
    path = tmp_path / "vector_mesh_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    # Zoom into a narrow window around the thin cell.
    zoom_xlim, zoom_ylim = (0.0, 0.5), (0.0, 1.0)
    x0, y0 = px(fig, 0, zoom_xlim[0], zoom_ylim[0])
    x1, y1 = px(fig, 0, zoom_xlim[1], zoom_ylim[1])
    _box_zoom(page, x0, y0, x1, y1)

    ccx, ccy = (edges[0] + edges[1]) / 2.0, (y_edges[0] + y_edges[1]) / 2.0  # cell (0, 0)
    markers = _click_mode(
        page, "Point Pick", *_px_at_limits(fig, 0, ccx, ccy, zoom_xlim, zoom_ylim))
    assert len(markers) == 1, "click after zoom made %d marker(s)" % len(markers)
    assert markers[0]["z"] == pytest.approx(float(field[0, 0]))


def test_forced_raster_mesh_still_picks_its_surviving_cells(page, tmp_path):
    """rasterized=True on the same grid must keep picking the cells that
    *do* survive resampling -- forcing raster shouldn't break picking on
    top of losing the thin cell."""
    from pick_cases import px

    with pytest.warns(UserWarning, match="cell 0"):   # the thin cell being lost -- expected
        fig, ax, mesh, edges, y_edges, field = _extreme_mesh(rasterized=True)
    assert not mesh.vectorized
    path = tmp_path / "forced_raster_mesh_pick.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ccx, ccy = (edges[1] + edges[2]) / 2.0, (y_edges[0] + y_edges[1]) / 2.0  # cell (0, 1) -- survives
    markers = _click_mode(page, "Point Pick", *px(fig, 0, ccx, ccy))
    assert len(markers) == 1
    assert markers[0]["z"] == pytest.approx(float(field[0, 1]))


@pytest.mark.parametrize("rasterized", [True, False], ids=["raster", "vector"])
def test_pcolormesh_legend_entry_actually_hides_the_mesh(page, tmp_path, rasterized):
    """Regression: a raster mesh's <image> carried no class/data-label at all,
    so the legend's click-to-hide toggle (which matches on .plotpress-series +
    data-label) silently found nothing to hide for it while working fine for a
    vectorized mesh with the identical label= call -- same public API, two
    different real-browser outcomes depending on an internal rendering choice.
    Both must now actually hide when their legend entry is clicked."""
    import warnings

    import numpy as np
    import plotpress

    edges = np.array([0.0, 0.01, 2.0, 6.0, 16.0, 40.0])
    y_edges = np.array([0.0, 0.5, 1.0])
    field = np.tile(np.arange(5.0), (2, 1))
    fig, ax = plotpress.subplots(figsize=(6, 5))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # rasterized=True drops cell 0 here -- not the point of this test
        ax.pcolormesh(edges, y_edges, field, cmap="viridis", rasterized=rasterized,
                      label="mesh")
    ax.legend()
    path = tmp_path / ("mesh_legend_toggle_%s.html" % rasterized)
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    display_before = page.evaluate(
        "() => { const el = document.querySelector('.plotpress-series'); "
        "return el ? el.style.display : null; }")
    page.evaluate(
        """() => document.querySelectorAll('.plotpress-legend text').forEach(t => {
             if (t.textContent.includes('mesh')) t.dispatchEvent(
               new MouseEvent('click', {bubbles: true}));
           })""")
    display_after = page.evaluate(
        "() => document.querySelector('.plotpress-series').style.display")
    assert display_before != "none"
    assert display_after == "none", (
        "legend click did not hide the %s mesh" % rasterized)


def test_pick_on_a_late_axes_survives_columnar_meta_with_a_gap(page, tmp_path):
    """binary_pick_data's meta payload embeds column-wise on a many-axes
    figure (see figure._columnarize_meta) and the client rebuilds
    META[axesIndex] from it -- a bug there (an off-by-one from the excluded
    hidden axes, say) would misroute a click to the wrong axes' limits, not
    just report a slightly-off value, so this checks a late axes past a gap
    in the surviving indices reports both its own axes index and the right
    datum, not a neighbor's."""
    import plotpress
    from pick_cases import px

    fig, axes = plotpress.subplots(6, 6)   # 36 axes: crosses the columnar/
    flat = axes.ravel()                    # binary-array thresholds too
    for i, ax in enumerate(flat):
        ax.plot([0.0, 1.0], [0.0, float(i)])
    flat[15].set_visible(False)            # gap in the surviving indices

    html = fig.to_html(interactive=True)
    assert '"cols"' in html   # sanity: this figure actually exercises it
    path = tmp_path / "many_axes_gap.html"
    path.write_text(html, encoding="utf-8")
    page.goto(path.as_uri())

    # Select the tool once: re-clicking an already-active toolbar button
    # toggles it *off* (single-selection toolbar).
    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Point Pick'
                                  && !b.classList.contains('active')) b.click(); })""")

    for target_i in (30, 3):   # well past the gap, and well before it
        ux, uy = px(fig, target_i, 1.0, float(target_i))
        markers = page.evaluate(
            """([ux, uy]) => {
              document.querySelectorAll('.plotpress-pin').forEach(p => p.remove());
              const svg = document.getElementById('plotpress-svg');
              const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
              const c = pt.matrixTransform(svg.getScreenCTM());
              const el = document.elementFromPoint(c.x, c.y) || svg;
              el.dispatchEvent(new MouseEvent('click', {
                bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
              return window.plotpressGetMarkers();
            }""", [ux, uy])
        assert len(markers) == 1, "axes %d: click made %d marker(s)" % (
            target_i, len(markers))
        got = markers[0]
        assert got["axes"] == target_i, (
            "axes %d: marker reports axes %r (wrong axes -> stale/misaligned "
            "meta reconstruction)" % (target_i, got["axes"]))
        assert got["y"] == pytest.approx(float(target_i), abs=1e-3)


def test_extract_csv_escapes_commas_and_quotes(page, tmp_path):
    """Regression: toCSV() joined fields with a bare comma/newline and no
    RFC 4180 quoting -- a value containing one (annotation text, axes_title,
    a set_pick_context() string, ...) shifted every column after it in that
    row out of alignment. Round-tripping through Python's own csv module is
    the authoritative check that the quoting is actually well-formed, not
    just "contains some quote characters somewhere"."""
    import csv as csv_mod
    import io

    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.set_pick_context(note='comma, and "quote"')
    path = tmp_path / "csv_escape.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 1.0, 1.0)
    _click_mode(page, "Point Pick", ux, uy)

    csv_text = page.evaluate(
        """() => {
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Extract') b.click();
          });
          return document.querySelector('.plotpress-extract textarea').value;
        }""")

    parsed = list(csv_mod.reader(io.StringIO(csv_text)))
    assert len(parsed) == 2, "expected a header row and one data row: %r" % parsed
    header, row = parsed
    assert header.count("note") == 1
    assert row[header.index("note")] == 'comma, and "quote"'


def test_extracted_record_carries_group_title(page, tmp_path):
    """A picked point's record reports which fig.group() box its axes sits
    in (empty when it belongs to none), the same way it already reports
    axes_title -- so a marker from a clustered panel says which cluster it
    came from without the caller having to cross-reference axes indices by
    hand."""
    import plotpress
    from pick_cases import px

    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0.0, 1.0], [0.0, 1.0])
    axes[1].plot([0.0, 1.0], [1.0, 0.0])
    fig.group("Cluster A", [axes[0]])
    path = tmp_path / "group_field.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux0, uy0 = px(fig, 0, 1.0, 1.0)
    grouped = _click_mode(page, "Point Pick", ux0, uy0)
    assert grouped[0]["group"] == "Cluster A"

    # Point Pick is already the active tool -- re-clicking its own button
    # would toggle it off (see setMode()), so the second click dispatches
    # straight to the SVG instead of going through _click_mode again.
    ux1, uy1 = px(fig, 1, 1.0, 0.0)
    markers = page.evaluate(
        """([ux, uy]) => {
          const svg = document.getElementById('plotpress-svg');
          const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
          const c = pt.matrixTransform(svg.getScreenCTM());
          const el = document.elementFromPoint(c.x, c.y) || svg;
          el.dispatchEvent(new MouseEvent('click', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
          return window.plotpressGetMarkers();
        }""", [ux1, uy1])
    assert len(markers) == 2
    assert markers[-1]["group"] == ""


def test_pick_values_key_does_not_clobber_structured_fields(page, tmp_path):
    """Regression: a series' values={...} dict was merged onto the exported
    record with no collision guard, so a key sharing a name with a
    structured field (kind, x, y, index, axes) silently overwrote it --
    unlike Axes.set_pick_context, which explicitly protects those fields."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 4.0],
               values={"kind": [99.0, 98.0, 97.0], "index": [-1.0, -2.0, -3.0]})
    path = tmp_path / "values_collision.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 1.0, 1.0)
    markers = _click_mode(page, "Point Pick", ux, uy)
    assert len(markers) == 1
    assert markers[0]["kind"] == "points", (
        "values={'kind': ...} clobbered the structured kind field: %r" % markers[0])
    assert markers[0]["index"] == 1, (
        "values={'index': ...} clobbered the structured index field: %r" % markers[0])


def test_unpickable_axes_makes_no_marker_but_stays_zoomable(page, tmp_path):
    """set_pickable(False) blocks Point Pick on that axes without disabling
    Span/Zoom -- a figure can restrict picking to a single panel while every
    other tool still works everywhere."""
    import plotpress
    from pick_cases import px

    fig, (left, right) = plotpress.subplots(1, 2)
    left.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    right.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    right.set_pickable(False)
    path = tmp_path / "unpickable.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    target_px = px(fig, 1, 1.0, 1.0)   # a real, drawn datum on the right axes
    n = page.evaluate(
        """(p) => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button')
            .forEach(b => { if (b.textContent === 'Point Pick') b.click(); });
          const pt = svg.createSVGPoint();
          pt.x = p[0]; pt.y = p[1];
          const c = pt.matrixTransform(svg.getScreenCTM());
          (document.elementFromPoint(c.x, c.y) || svg).dispatchEvent(
            new MouseEvent('click', {bubbles: true, clientX: c.x, clientY: c.y}));
          return window.plotpressGetMarkers().length;
        }""", target_px)
    assert n == 0, "clicking a datum on a set_pickable(False) axes created a marker"

    zoomed = page.evaluate(
        """(p) => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button')
            .forEach(b => { if (b.textContent === 'Zoom') b.click(); });
          const before = svg.getBoundingClientRect().width;
          const pt = svg.createSVGPoint();
          pt.x = p[0]; pt.y = p[1];
          const c = pt.matrixTransform(svg.getScreenCTM());
          const el = document.elementFromPoint(c.x, c.y) || svg;
          el.dispatchEvent(new WheelEvent('wheel', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, deltaY: -100,
            ctrlKey: true
          }));
          return svg.getBoundingClientRect().width !== before;
        }""", target_px)
    assert zoomed, "Zoom (ctrl+wheel, whole-figure) must still work over a set_pickable(False) axes"


def test_minor_ticks_reposition_on_zoom(page, tmp_path):
    """Regression: rebuildTicks() only recomputed major ticks on pan/zoom;
    minorticks_on()'s marks stayed frozen at their initial positions instead
    of tracking the new, narrower range."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 10.0])
    ax.minorticks_on()
    path = tmp_path / "minor_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    before = page.evaluate(
        "() => document.getElementById('ticks0').querySelectorAll('line').length")

    x0, y0 = px(fig, 0, 2.0, 2.0)
    x1, y1 = px(fig, 0, 8.0, 8.0)
    _box_zoom(page, x0, y0, x1, y1)   # a per-axes data-space zoom (drag), not wheel

    after = page.evaluate(
        "() => document.getElementById('ticks0').querySelectorAll('line').length")
    assert after != before, (
        "tick mark count did not change after zoom -- minor ticks are frozen")


def test_tick_params_style_survives_zoom(page, tmp_path):
    """Regression: rebuildTicks() read only the figure-wide STYLE payload, so
    a per-axis tick_params() override (color, width, labelsize, ...) rendered
    correctly on the initial static SVG but silently reverted to the default
    style the moment the axes was panned or zoomed."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 10.0])
    ax.tick_params(axis="x", color="#d62728", width=3.0)
    ax.tick_params(axis="y", color="#2ca02c")
    path = tmp_path / "tick_style_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    stroke_query = (
        "() => Array.from(document.getElementById('ticks0').querySelectorAll('g[stroke]'))"
        ".map(g => g.getAttribute('stroke'))")

    before = page.evaluate(stroke_query)
    assert "#d62728" in before and "#2ca02c" in before, (
        "initial render did not honor tick_params colors: %r" % before)

    x0, y0 = px(fig, 0, 2.0, 2.0)
    x1, y1 = px(fig, 0, 8.0, 8.0)
    _box_zoom(page, x0, y0, x1, y1)   # a per-axes data-space zoom (drag), not wheel

    after = page.evaluate(stroke_query)
    assert "#d62728" in after and "#2ca02c" in after, (
        "tick_params() colors reverted to the default style after zoom: %r" % after)


def test_grid_alpha_override_survives_a_real_zoom(page, tmp_path):
    """Same regression class as test_tick_params_style_survives_zoom, for
    grid(alpha=): the client's grid rebuild on zoom must read the per-axes
    override from the (columnar) metadata payload, not just the figure-wide
    Style default the initial static render also happens to satisfy."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 10.0])
    ax.grid(True, alpha=0.05)   # far from the Style default (0.6), so a
                                # silent fallback is unmistakable, not a coincidence
    path = tmp_path / "grid_alpha_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    op_query = (
        "() => { const g = document.getElementById('ticks0')"
        ".querySelector('g[stroke-opacity]'); return g && g.getAttribute('stroke-opacity'); }")

    before = page.evaluate(op_query)
    assert before == "0.05", "initial render did not honor grid(alpha=): %r" % before

    x0, y0 = px(fig, 0, 2.0, 2.0)
    x1, y1 = px(fig, 0, 8.0, 8.0)
    _box_zoom(page, x0, y0, x1, y1)

    after = page.evaluate(op_query)
    assert after == "0.05", (
        "grid(alpha=) reverted to the Style default after zoom: %r" % after)


def test_text_counter_scale_survives_a_real_zoom(page, tmp_path):
    """Regression: a data-anchored ax.text() label sat directly inside the
    per-axes zoom{index} group, so the client's data-zoom matrix(sx,sy,...)
    transform stretched its *glyphs*, not just its position -- readable as
    a normal-size label at rest, a blob many times its own font size after
    zooming into a small region. See the marker-scaling fix for the mirror
    image of this bug (there, a marker wrongly stayed constant size instead
    of scaling with the axis -- here, a label wrongly scales instead of
    staying constant, the same way a title/tick label/pin already does)."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 10.0])
    ax.text(5.0, 5.0, "label", fontsize=14, bbox={"facecolor": "yellow"})
    path = tmp_path / "text_counter_scale_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    size_query = (
        "() => { const el = [...document.querySelectorAll('text')]"
        ".find(t => t.textContent === 'label'); "
        "const r = el.getBoundingClientRect(); return [r.width, r.height]; }")
    before = page.evaluate(size_query)
    assert before[0] > 0 and before[1] > 0

    x0, y0 = px(fig, 0, 4.0, 4.0)
    x1, y1 = px(fig, 0, 6.0, 6.0)
    _box_zoom(page, x0, y0, x1, y1)

    after = page.evaluate(size_query)
    assert after[0] == pytest.approx(before[0], rel=0.03), (
        "label width changed after zoom: %.2f -> %.2f" % (before[0], after[0]))
    assert after[1] == pytest.approx(before[1], rel=0.03), (
        "label height changed after zoom: %.2f -> %.2f" % (before[1], after[1]))


def _px_at_limits(fig, i, dx, dy, xlim, ylim):
    """Like ``pick_cases.px()``, but against an explicit ``(xlim, ylim)``
    instead of the axes' own current limits -- for computing where a datum
    lands on screen *after* a box-zoom has narrowed the browser's view to a
    range the Python ``Axes`` object itself never actually changed to.
    """
    from plotpress.svg import _effective_rect, _pixel_rect
    from plotpress.transform import LinearTransform

    ax = fig.axes[i]
    dpi = fig.style.dpi
    rect = _effective_rect(ax, *_pixel_rect(ax, fig.figsize[0] * dpi,
                                            fig.figsize[1] * dpi), xlim, ylim)
    tr = LinearTransform(xlim, ylim, rect, xscale=ax._xscale, yscale=ax._yscale)
    return [float(tr.x(dx)), float(tr.y(dy))]


def test_point_pick_large_series_stays_accurate_after_zoom(page, tmp_path):
    """Regression: nearestVertex() -- the fallback Point Pick uses for a
    series too large to embed in the pick payload (over to_html()'s default
    pick_max_points=20000) -- compared the click against that series' raw
    SVG geometry, which is fixed in the axes' *original* pre-zoom limits.
    After the axes was zoomed, a click resolved to whatever vertex happened
    to sit at that pixel position in the stale, pre-zoom coordinate space --
    a wrong, sometimes wildly-off datum, not the one under the cursor.

    A rubber-band box zoom sets the axes' new data limits directly, so
    clicking at the *new* on-screen position of a point that was always at
    (target_x, target_y) must still resolve to (roughly) that same datum if
    the fallback is reading the post-zoom coordinate space, not a stale
    pre-zoom one."""
    import numpy as np
    import plotpress
    from pick_cases import px

    x = np.linspace(0.0, 10.0, 25000)   # over the 20000-point embed cap
    y = np.sin(x)
    fig, ax = plotpress.subplots()
    ax.plot(x, y)
    path = tmp_path / "large_series_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    target_x, target_y = 5.0, float(np.sin(5.0))
    zoom_xlim, zoom_ylim = (4.0, 6.0), (-1.2, 1.2)   # a narrow window around it

    x0, y0 = px(fig, 0, zoom_xlim[0], zoom_ylim[0])
    x1, y1 = px(fig, 0, zoom_xlim[1], zoom_ylim[1])
    _box_zoom(page, x0, y0, x1, y1)

    markers = _click_mode(
        page, "Point Pick", *_px_at_limits(fig, 0, target_x, target_y, zoom_xlim, zoom_ylim))
    assert len(markers) == 1
    m = markers[0]
    assert abs(m["x"] - target_x) < 0.5, (
        "picked x is far from the zoomed-in cursor position: %r" % m)
    assert abs(m["y"] - target_y) < 0.5, (
        "picked y is far from the zoomed-in cursor position: %r" % m)


def test_wheel_zoom_scales_the_whole_figure_view_centered_on_cursor(page, tmp_path):
    """Ctrl+wheel zooms the whole figure by growing the SVG's own rendered
    size, not a single axes' data range -- the useful gesture on a figure
    with many small axes, where zooming whatever tiny panel the cursor
    happens to be over isn't. It must work regardless of which axes (if
    any) sits under the cursor, must keep the data/user-space point under
    the cursor fixed (the same point maps to the same screen pixel before
    and after, via the compensating scroll), and must leave every
    individual axes' own zoom transform untouched -- that is still driven
    only by a rubber-band box drag, not the wheel."""
    import numpy as np
    import plotpress

    fig, axes = plotpress.subplots(2, 2)
    for ax in np.asarray(axes).ravel():
        ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "wheel_whole_figure.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Zoom') b.click();
          });
          const r0 = svg.getBoundingClientRect();
          const cx = r0.x + r0.width * 0.3, cy = r0.y + r0.height * 0.7;
          // Zoom in several ticks first so the figure genuinely overflows the
          // viewport -- the "point under the cursor stays put" guarantee is
          // kept via a compensating scroll (see zoomTo()), which has nothing
          // to correct with, and so cannot hold, for as long as the whole
          // figure still fits on screen with room to spare.
          for (let i = 0; i < 6; i++) {
            svg.dispatchEvent(new WheelEvent('wheel', {
              bubbles: true, cancelable: true, clientX: cx, clientY: cy, deltaY: -300,
              ctrlKey: true
            }));
          }
          const before = svg.getBoundingClientRect().width;
          const pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy;
          const u0 = pt.matrixTransform(svg.getScreenCTM().inverse());
          svg.dispatchEvent(new WheelEvent('wheel', {
            bubbles: true, cancelable: true, clientX: cx, clientY: cy, deltaY: -300,
            ctrlKey: true
          }));
          const after = svg.getBoundingClientRect().width;
          // Fresh getScreenCTM(): the SVG's rendered size (and, via the
          // compensating scroll, its on-screen position) just changed, so
          // its inverse must be re-derived to read what user-space point is
          // now under the same screen pixel.
          const u1 = pt.matrixTransform(svg.getScreenCTM().inverse());
          const zoomTransforms = [0, 1, 2, 3].map(i => {
            const el = document.getElementById('zoom' + i);
            return el && el.getAttribute('transform');
          });
          return { before, after, u0: {x: u0.x, y: u0.y}, u1: {x: u1.x, y: u1.y},
                   zoomTransforms };
        }""")
    assert out["before"] != out["after"], (
        "ctrl+wheel over an axes must still zoom the whole figure, not do nothing")
    assert out["u0"]["x"] == pytest.approx(out["u1"]["x"], abs=0.5)
    assert out["u0"]["y"] == pytest.approx(out["u1"]["y"], abs=0.5)
    assert all(t is None for t in out["zoomTransforms"]), (
        "wheel must not touch any individual axes' own zoom transform -- "
        "only a rubber-band box drag should: %r" % out["zoomTransforms"])


def test_plain_wheel_without_ctrl_does_not_zoom_and_is_not_captured(page, tmp_path):
    """A plain scroll (no Ctrl) must leave the figure's own view untouched
    and must not be preventDefault()'d -- the page should scroll normally
    underneath the figure, exactly as it would over any other content, even
    while Zoom is the active tool."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "wheel_no_ctrl.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Zoom') b.click();
          });
          const before = svg.getAttribute('viewBox');
          const r = svg.getBoundingClientRect();
          const ev = new WheelEvent('wheel', {
            bubbles: true, cancelable: true,
            clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, deltaY: -300
          });
          const notCancelled = svg.dispatchEvent(ev);   // false if preventDefault() ran
          return { before, after: svg.getAttribute('viewBox'), notCancelled };
        }""")
    assert out["before"] == out["after"], (
        "a plain wheel (no Ctrl) must not zoom the figure")
    assert out["notCancelled"], (
        "a plain wheel must not be preventDefault()'d -- the page must "
        "still be free to scroll under the figure")


def test_magnify_mode_zooms_on_a_plain_wheel_no_ctrl_needed(page, tmp_path):
    """Magnify is the explicit opt-in past Zoom's Ctrl+wheel requirement --
    selecting it means a plain wheel (no Ctrl) should zoom the whole figure
    and capture the scroll, for wherever holding Ctrl is awkward or already
    claimed by the browser/OS. Regression: must not require ctrlKey the way
    Zoom's own wheel handling does."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "magnify_plain_wheel.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Magnify') b.click();
          });
          const before = svg.getBoundingClientRect().width;
          const r = svg.getBoundingClientRect();
          const ev = new WheelEvent('wheel', {
            bubbles: true, cancelable: true,
            clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, deltaY: -300
          });
          const notCancelled = svg.dispatchEvent(ev);
          return { before, after: svg.getBoundingClientRect().width, notCancelled };
        }""")
    assert out["before"] != out["after"], (
        "Magnify mode must zoom on a plain wheel, without needing Ctrl")
    assert not out["notCancelled"], (
        "a wheel that zooms the figure must be preventDefault()'d, or the "
        "page would also scroll underneath it")


def test_magnify_mode_drag_pans_the_zoomed_in_whole_figure_view(page, tmp_path):
    """Once Magnify has zoomed in, a zoomed-in figure needs a way back to
    parts that scrolled out of view -- drag pans the same whole-figure view
    (real page scroll, so the browser's own scrollbars work too) in any
    direction, without switching to Span. It must move the scroll position
    in both x and y, and -- staying isolated from per-axes zoom/pan the same
    way the wheel does -- must never touch any individual axes' own zoom
    transform or the SVG's own zoomed-in size, even when the drag starts on
    top of a real axes."""
    import numpy as np
    import plotpress

    fig, axes = plotpress.subplots(2, 2)
    for ax in np.asarray(axes).ravel():
        ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "magnify_drag_pan.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Magnify') b.click();
          });
          const r = svg.getBoundingClientRect();
          const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
          // Zoom in enough ticks (plain wheel, no Ctrl -- Magnify's own
          // gesture) that the figure genuinely overflows the viewport --
          // otherwise there is nowhere for a pan to actually scroll to.
          for (let i = 0; i < 8; i++) {
            svg.dispatchEvent(new WheelEvent('wheel', {
              bubbles: true, cancelable: true, clientX: cx, clientY: cy, deltaY: -300
            }));
          }
          const widthAfterZoom = svg.getBoundingClientRect().width;
          const scrollBefore = { x: window.scrollX, y: window.scrollY };

          svg.dispatchEvent(new MouseEvent('mousedown', {
            bubbles: true, clientX: cx, clientY: cy, button: 0}));
          window.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true, clientX: cx - 80, clientY: cy - 60}));
          window.dispatchEvent(new MouseEvent('mouseup', {
            bubbles: true, clientX: cx - 80, clientY: cy - 60}));
          const scrollAfter = { x: window.scrollX, y: window.scrollY };
          const widthAfterDrag = svg.getBoundingClientRect().width;

          const zoomTransforms = [0, 1, 2, 3].map(i => {
            const el = document.getElementById('zoom' + i);
            return el && el.getAttribute('transform');
          });
          return { scrollBefore, scrollAfter, widthAfterZoom, widthAfterDrag, zoomTransforms };
        }""")
    assert out["scrollBefore"] != out["scrollAfter"], (
        "drag must pan (scroll) the page after Magnify zoomed in: %r" % out)
    assert out["scrollBefore"]["x"] != out["scrollAfter"]["x"], (
        "drag must move the scroll position in x, not just y: %r" % out)
    assert out["scrollBefore"]["y"] != out["scrollAfter"]["y"], (
        "drag must move the scroll position in y, not just x: %r" % out)
    assert out["widthAfterDrag"] == out["widthAfterZoom"], (
        "a pan drag must not also change the zoom level")
    assert all(t is None for t in out["zoomTransforms"]), (
        "Magnify's drag-pan must not touch any individual axes' own zoom "
        "transform -- only the whole-figure view: %r" % out["zoomTransforms"])


def test_magnify_mode_double_click_resets_the_whole_figure_view(page, tmp_path):
    """Span/Zoom's double-click resets one axes' own data zoom -- meaningless
    under Magnify, which never touches per-axes data. Its double-click must
    reset the whole-figure view instead, back to exactly the figure's own
    natural (unzoomed) rendered size, the same thing the wheel and drag-pan
    both operate on."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "magnify_dblclick_reset.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Magnify') b.click();
          });
          const home = svg.getBoundingClientRect().width;
          const r = svg.getBoundingClientRect();
          const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
          svg.dispatchEvent(new WheelEvent('wheel', {
            bubbles: true, cancelable: true, clientX: cx, clientY: cy, deltaY: -300
          }));
          const zoomedIn = svg.getBoundingClientRect().width;
          svg.dispatchEvent(new MouseEvent('dblclick', {
            bubbles: true, cancelable: true, clientX: cx, clientY: cy
          }));
          return { home, zoomedIn, after: svg.getBoundingClientRect().width };
        }""")
    assert out["zoomedIn"] != out["home"], (
        "the fixture must actually zoom in first, or this test proves nothing")
    assert out["after"] == out["home"], (
        "double-click under Magnify must reset the whole-figure view: %r" % out)


def test_magnify_mode_disables_text_selection_on_the_svg(page, tmp_path):
    """A drag-to-pan under Magnify sweeps across the figure's own tick
    labels/titles just like a text-selection drag would; without disabling
    it, panning highlights that text instead of just moving the view. Other
    modes leave it alone -- selection is a Magnify-specific problem, not a
    general one."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "magnify_no_text_select.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    def user_select_under(label):
        return page.evaluate(
            """(label) => {
              document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
                if (b.textContent === label) b.click();
              });
              return getComputedStyle(document.getElementById('plotpress-svg')).userSelect;
            }""", label)

    assert user_select_under("Span") != "none"
    assert user_select_under("Magnify") == "none"
    # Switching back off Magnify must restore normal selection behavior.
    assert user_select_under("Magnify") != "none"   # clicking the active tool turns it off


def test_zoomed_in_figure_makes_the_page_natively_scrollable(page, tmp_path):
    """Regression: whole-figure zoom used to crop the SVG's own viewBox --
    its rendered size on the page never changed, so there was nothing for
    the browser's own scrollbars to reach, and dragging was the only way to
    see the rest of a zoomed-in figure. It must instead grow the SVG's
    actual on-page size, so the page genuinely overflows and the browser's
    native scroll (real scrollbars, trackpad, keyboard) works -- checked
    here as real document overflow and a real, non-zero scroll offset after
    zooming toward a corner, not just an internal state flag. Resetting must
    shrink it back down to nothing left to scroll."""
    import numpy as np
    import plotpress

    fig, axes = plotpress.subplots(4, 4, figsize=(9, 9))
    for ax in np.asarray(axes).ravel():
        ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    path = tmp_path / "magnify_native_scroll.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Magnify') b.click();
          });
          const before = {
            scrollWidth: document.documentElement.scrollWidth,
            scrollHeight: document.documentElement.scrollHeight,
            zoomedClass: document.body.classList.contains('plotpress-zoomed'),
          };
          // Zoom in several ticks near a corner, not the center, so the
          // resulting scroll offset is unambiguously non-zero in both axes.
          const r = svg.getBoundingClientRect();
          const cx = r.x + r.width * 0.1, cy = r.y + r.height * 0.1;
          for (let i = 0; i < 8; i++) {
            svg.dispatchEvent(new WheelEvent('wheel', {
              bubbles: true, cancelable: true, clientX: cx, clientY: cy, deltaY: -300
            }));
          }
          const zoomed = {
            scrollWidth: document.documentElement.scrollWidth,
            scrollHeight: document.documentElement.scrollHeight,
            overflow: getComputedStyle(document.body).overflow,
            zoomedClass: document.body.classList.contains('plotpress-zoomed'),
            scrollX: window.scrollX, scrollY: window.scrollY,
          };
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === 'Reset') b.click();
          });
          const reset = {
            width: svg.getBoundingClientRect().width,
            zoomedClass: document.body.classList.contains('plotpress-zoomed'),
          };
          return { before, zoomed, reset };
        }""")
    assert out["zoomed"]["scrollWidth"] > out["before"]["scrollWidth"], (
        "zooming in must make the page's own content genuinely wider than "
        "before, not just internally cropped: %r" % out)
    assert out["zoomed"]["scrollHeight"] > out["before"]["scrollHeight"]
    assert out["zoomed"]["overflow"] == "auto", (
        "the page must actually be scrollable while zoomed: %r" % out)
    assert out["zoomed"]["scrollX"] > 0 and out["zoomed"]["scrollY"] > 0, (
        "zooming toward a corner must leave the page genuinely scrolled, "
        "not still sitting at the origin: %r" % out)
    assert not out["before"]["zoomedClass"] and out["zoomed"]["zoomedClass"], (
        "the zoomed marker class must appear only once actually zoomed in: %r" % out)
    assert not out["reset"]["zoomedClass"], (
        "Reset must clear the zoomed state along with the size: %r" % out)


def _box_zoom(page, x0, y0, x1, y1):
    """Simulate a real "Zoom"-mode rubber-band drag between two SVG
    user-space pixel points -- the mechanism that now drives per-axes,
    data-space zoom (the wheel zooms the whole figure instead; see
    test_wheel_zoom_scales_the_whole_figure_view_centered_on_cursor)."""
    page.evaluate(
        """([x0, y0, x1, y1]) => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button')
            .forEach(b => { if (b.textContent === 'Zoom') b.click(); });
          function toClient(ux, uy) {
            const pt = svg.createSVGPoint();
            pt.x = ux; pt.y = uy;
            return pt.matrixTransform(svg.getScreenCTM());
          }
          const a = toClient(x0, y0), b = toClient(x1, y1);
          svg.dispatchEvent(new MouseEvent('mousedown', {
            bubbles: true, clientX: a.x, clientY: a.y, button: 0}));
          window.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true, clientX: b.x, clientY: b.y}));
          window.dispatchEvent(new MouseEvent('mouseup', {
            bubbles: true, clientX: b.x, clientY: b.y}));
        }""",
        [x0, y0, x1, y1])


def _drag_pan(page, x0, y0, x1, y1):
    """Simulate a real "Span"-mode drag between two SVG user-space points."""
    return page.evaluate(
        """([x0, y0, x1, y1]) => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button')
            .forEach(b => { if (b.textContent === 'Span') b.click(); });
          function toClient(ux, uy) {
            const pt = svg.createSVGPoint();
            pt.x = ux; pt.y = uy;
            return pt.matrixTransform(svg.getScreenCTM());
          }
          const a = toClient(x0, y0), b = toClient(x1, y1);
          svg.dispatchEvent(new MouseEvent('mousedown', {
            bubbles: true, clientX: a.x, clientY: a.y, button: 0}));
          window.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true, clientX: b.x, clientY: b.y}));
          window.dispatchEvent(new MouseEvent('mouseup', {
            bubbles: true, clientX: b.x, clientY: b.y}));
          function matrixOf(id) {
            const el = document.getElementById(id);
            const t = el && el.getAttribute('transform');
            if (!t) return null;
            const nums = t.match(/-?[\\d.]+(?:e-?\\d+)?/g).map(Number);
            return { sx: nums[0], sy: nums[3], tx: nums[4], ty: nums[5] };
          }
          return { zoom0: matrixOf('zoom0'), zoom1: matrixOf('zoom1') };
        }""",
        [x0, y0, x1, y1])


def test_twin_axes_stays_in_sync_when_the_parent_is_panned(page, tmp_path):
    """Regression: a twinx overlay occupies the exact same pixel rect as its
    parent, so a drag over the shared area can only ever resolve to one of
    them (axesAt() picks a single axes). Before the fix, panning always hit
    the parent and the twin's ``zoom1`` group was never touched -- the twin's
    line stayed frozen while the parent's data moved underneath it. Now the
    hit axes propagates its shared dimension onto the other, so both groups
    end up with matching x-shift components.
    """
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 1.0])
    ax2 = ax.twinx()
    ax2.plot([0.0, 10.0], [0.0, 1000.0])
    path = tmp_path / "twin_pan.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = _drag_pan(page, 200, 200, 260, 220)   # drag well inside the shared box
    assert out["zoom0"] is not None, "parent's zoom group was never transformed"
    assert out["zoom1"] is not None, (
        "twin's zoom group was never transformed -- it desynced from its parent")
    assert out["zoom0"]["sx"] == pytest.approx(out["zoom1"]["sx"], abs=1e-6)
    assert out["zoom0"]["tx"] == pytest.approx(out["zoom1"]["tx"], abs=1e-6)


def test_secondary_axis_stays_in_sync_when_the_parent_is_panned(page, tmp_path):
    """Same regression as the twin case, but for secondary_xaxis/yaxis, which
    mirror *both* dimensions of their parent unconditionally."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 1.0])
    ax.secondary_xaxis("top")
    path = tmp_path / "secondary_pan.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    out = _drag_pan(page, 200, 200, 260, 220)
    assert out["zoom0"] is not None
    assert out["zoom1"] is not None, (
        "secondary axis's zoom group was never transformed -- it desynced "
        "from its parent")
    assert out["zoom0"]["sx"] == pytest.approx(out["zoom1"]["sx"], abs=1e-6)
    assert out["zoom0"]["tx"] == pytest.approx(out["zoom1"]["tx"], abs=1e-6)
    assert out["zoom0"]["sy"] == pytest.approx(out["zoom1"]["sy"], abs=1e-6)
    assert out["zoom0"]["ty"] == pytest.approx(out["zoom1"]["ty"], abs=1e-6)


def test_double_click_reset_also_resets_a_linked_twin(page, tmp_path):
    """Regression: resetAxesOne() only reset the double-clicked axes' own
    state, without propagating to its twin -- so after a pan, double-clicking
    the parent snapped it back but left the twin stranded at whatever view it
    had drifted to."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 1.0])
    ax2 = ax.twinx()
    ax2.plot([0.0, 10.0], [0.0, 1000.0])
    path = tmp_path / "twin_reset.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    _drag_pan(page, 200, 200, 260, 220)   # both now panned away from their default view

    out = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          const pt = svg.createSVGPoint(); pt.x = 200; pt.y = 200;
          const c = pt.matrixTransform(svg.getScreenCTM());
          svg.dispatchEvent(new MouseEvent('dblclick', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y}));
          function has(id) {
            return !!document.getElementById(id).getAttribute('transform');
          }
          return { zoom0: has('zoom0'), zoom1: has('zoom1') };
        }""")
    assert not out["zoom0"], "parent should be back at its original (untransformed) view"
    assert not out["zoom1"], "twin must reset along with its parent"


def _click_mode(page, mode_label, ux, uy, prompt_text=None):
    """Select a toolbar tool by its label and click at an SVG user-space point.

    ``prompt_text``, when given, auto-accepts the ``window.prompt()`` an
    Annotate mode raises -- Playwright otherwise auto-dismisses dialogs,
    which would make every annotate click a no-op.

    Fires a real ``mousedown``/``mouseup`` immediately before the ``click``,
    not just the click itself -- the click handler bails out early if
    ``moved`` is still set from an *earlier*, unrelated drag (a box-zoom
    before a click in the same test, say), and only a fresh ``mousedown``
    resets that flag, exactly as it would for a genuine user click.
    """
    if prompt_text is not None:
        page.once("dialog", lambda d: d.accept(prompt_text))
    return page.evaluate(
        """([label, ux, uy]) => {
          const svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
            if (b.textContent === label) b.click();
          });
          const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
          const c = pt.matrixTransform(svg.getScreenCTM());
          const el = document.elementFromPoint(c.x, c.y) || svg;
          el.dispatchEvent(new MouseEvent('mousedown', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
          el.dispatchEvent(new MouseEvent('mouseup', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
          el.dispatchEvent(new MouseEvent('click', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0}));
          return window.plotpressGetMarkers();
        }""",
        [mode_label, ux, uy])


def test_annotate_point_locks_a_note_to_the_nearest_datum(page, tmp_path):
    """"Annotate Point" must resolve to the same target Point Pick would, but
    carry the user's own text instead of the auto-generated "x=.., y=.."
    readout -- and keep it after arrow-key stepping."""
    import plotpress
    from pick_cases import px

    x = [0.0, 1.0, 2.0, 3.0]
    y = [0.0, 1.0, 4.0, 9.0]
    fig, ax = plotpress.subplots()
    ax.plot(x, y)
    path = tmp_path / "annotate_point.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, x[2], y[2])
    markers = _click_mode(page, "Annotate Point", ux, uy, prompt_text="peak here")
    assert len(markers) == 1
    m = markers[0]
    assert m["kind"] == "points" and m["index"] == 2
    assert m["x"] == pytest.approx(x[2]) and m["y"] == pytest.approx(y[2])
    assert m["text"] == "peak here"

    # Step to the next point (arrow key) -- the text must survive the move.
    page.evaluate(
        """() => document.querySelector('.plotpress-pin')
             .dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, key: 'ArrowRight'}))""")
    stepped = page.evaluate("() => window.plotpressGetMarkers()")
    assert len(stepped) == 1
    assert stepped[0]["index"] == 3
    assert stepped[0]["text"] == "peak here", "custom text must not be lost on step"


def test_annotate_point_note_survives_frame_slider_scrub(page, tmp_path):
    """Regression: updateFramePins() (fired whenever a plot_frames slider
    moves) called layoutPin() directly instead of through the pinLabel()
    helper every other re-layout path uses -- pan/zoom (relayoutPins) and
    arrow-key stepping (stepPin) both already went through pinLabel(), so
    only the frame-slider path silently stomped a user's Annotate Point note
    back to the auto-generated "x=.., y=.." readout on every scrub."""
    import numpy as np
    import plotpress
    from pick_cases import px

    x = np.array([0.0, 1.0, 2.0, 3.0])
    Y = np.array([x * (f + 1) for f in range(4)])   # frame f: y = x * (f + 1)
    fig, ax = plotpress.subplots()
    ax.plot_frames(x, Y, slider_label="t")
    path = tmp_path / "frame_annotate.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, x[2], Y[0][2])   # frame 0's vertex at x[2]
    markers = _click_mode(page, "Annotate Point", ux, uy, prompt_text="watch me")
    assert len(markers) == 1 and markers[0]["text"] == "watch me"

    page.evaluate(
        """() => {
          const input = document.querySelector('.plotpress-slider input[type=range]');
          input.value = 2;
          input.dispatchEvent(new Event('input', {bubbles: true}));
        }""")

    label = page.evaluate(
        "() => document.querySelector('.plotpress-pin text').textContent")
    assert label == "watch me", (
        "custom annotation text was stomped back to the auto-readout on "
        "frame change: %r" % label)

    after = page.evaluate("() => window.plotpressGetMarkers()")
    assert len(after) == 1 and after[0]["text"] == "watch me"


def test_pcolormesh_frames_pick_reads_the_current_frames_value(page, tmp_path):
    """Regression: frame_data()'s FrameQuadMesh branch only ever embedded
    each frame's rendered PNG (for redraw) -- never its raw z grid -- and
    pick_data() only ever handles a plain (non-frame) QuadMesh, so a
    pcolormesh_frames() axes had no pick data anywhere, at any frame. Point
    Pick and Annotate Point silently produced no marker at all on one,
    however precisely a click landed on a cell."""
    import numpy as np
    import plotpress
    from pick_cases import px

    Z = np.arange(20.0).reshape(4, 5)
    frames = np.stack([Z, Z + 100.0, Z + 200.0])   # 3 frames, same grid
    fig, ax = plotpress.subplots()
    ax.pcolormesh_frames(frames, cmap="viridis")
    path = tmp_path / "meshframe_pick.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 2.5, 1.5)   # center of cell (row=1, col=2)
    markers = _click_mode(page, "Point Pick", ux, uy)
    assert len(markers) == 1
    m = markers[0]
    assert m["kind"] == "meshframe"
    assert m["z"] == float(Z[1, 2])   # frame 0's value

    # Scrub to frame 2 -- the same pin must keep its position (the grid is
    # shared across frames; only C animates) but report the new frame's value.
    page.evaluate(
        """() => {
          const input = document.querySelector('.plotpress-slider input[type=range]');
          input.value = 2;
          input.dispatchEvent(new Event('input', {bubbles: true}));
        }""")
    after = page.evaluate("() => window.plotpressGetMarkers()")
    assert len(after) == 1
    assert after[0]["x"] == m["x"] and after[0]["y"] == m["y"]
    assert after[0]["z"] == float(Z[1, 2] + 200.0)


def test_pcolormesh_frames_pick_arrow_key_steps_to_neighboring_cell(page, tmp_path):
    import numpy as np
    import plotpress
    from pick_cases import px

    Z = np.arange(20.0).reshape(4, 5)
    fig, ax = plotpress.subplots()
    ax.pcolormesh_frames(np.stack([Z, Z + 100.0]), cmap="viridis")
    path = tmp_path / "meshframe_step.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 2.5, 1.5)   # cell (row=1, col=2)
    _click_mode(page, "Point Pick", ux, uy)
    page.evaluate("() => document.querySelector('.plotpress-pin').dispatchEvent("
                  "new MouseEvent('click', {bubbles: true}))")
    page.keyboard.press("ArrowRight")
    after = page.evaluate("() => window.plotpressGetMarkers()")
    assert len(after) == 1
    assert after[0]["z"] == float(Z[1, 3]), (
        "arrow-key stepping did not move to the neighboring cell: %r" % after)


def test_mesh_pick_arrow_key_up_honors_an_inverted_axis(page, tmp_path):
    """Regression: neighbor()'s mesh branch used to treat "up" as always
    meaning "increase the row index," regardless of which way the axis was
    actually drawn -- so on an axis flipped with invert_yaxis() (e.g. depth
    plots, which draw larger values toward the bottom), pressing the Up
    arrow moved the pin further *down* the screen instead of up. Same bug,
    mirrored, for invert_xaxis() and the Left/Right keys."""
    import numpy as np
    import plotpress
    from pick_cases import px

    Z = np.arange(20.0).reshape(4, 5)   # row = y index, col = x index

    fig, ax = plotpress.subplots()
    ax.pcolormesh(Z, cmap="viridis")
    ax.invert_yaxis()
    ax.invert_xaxis()
    path = tmp_path / "mesh_inverted_step.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 2.5, 1.5)   # cell (row=1, col=2)
    _click_mode(page, "Point Pick", ux, uy)
    page.evaluate("() => document.querySelector('.plotpress-pin').dispatchEvent("
                  "new MouseEvent('click', {bubbles: true}))")

    page.keyboard.press("ArrowUp")
    after_up = page.evaluate("() => window.plotpressGetMarkers()")
    assert after_up[0]["z"] == float(Z[0, 2]), (
        "on an inverted y-axis, Up must step to the smaller row index (drawn "
        "higher on screen), not the larger one: %r" % after_up)

    page.keyboard.press("ArrowRight")
    after_right = page.evaluate("() => window.plotpressGetMarkers()")
    assert after_right[0]["z"] == float(Z[0, 1]), (
        "on an inverted x-axis, Right must step to the smaller column index "
        "(drawn further right on screen), not the larger one: %r" % after_right)


def test_pcolormesh_frames_curvilinear_pick_uses_nearest_cell_center(page, tmp_path):
    """A warped (curvilinear) pcolormesh_frames() grid must pick via nearest
    cell center just like a plain curvilinear pcolormesh does -- not crash
    for lack of xedges/yedges, which only a rectilinear mesh has."""
    import math
    import numpy as np
    import plotpress
    from pick_cases import px

    n = 8
    r = np.linspace(0.3, 1.0, n)
    th = np.linspace(0, 1.5 * math.pi, n)
    R, TH = np.meshgrid(r, th)
    X, Y = R * np.cos(TH), R * np.sin(TH)
    Z0 = np.arange((n - 1) * (n - 1), dtype=float).reshape(n - 1, n - 1)
    fig, ax = plotpress.subplots(figsize=(6, 5))
    ax.pcolormesh_frames(X, Y, np.stack([Z0, Z0 + 50.0]), cmap="plasma")
    path = tmp_path / "meshframe_curvi.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    i, j = 3, 3
    ccx = float((X[i, j] + X[i, j + 1] + X[i + 1, j] + X[i + 1, j + 1]) / 4.0)
    ccy = float((Y[i, j] + Y[i, j + 1] + Y[i + 1, j] + Y[i + 1, j + 1]) / 4.0)
    ux, uy = px(fig, 0, ccx, ccy)
    markers = _click_mode(page, "Point Pick", ux, uy)
    assert len(markers) == 1
    assert markers[0]["z"] == float(Z0[i, j])


def test_annotate_point_on_a_pie_miss_makes_no_marker(page, tmp_path):
    """A pie axes only has its wedges to pick -- "Annotate Point" missing all
    of them must make no marker, same as Point Pick, not fall back to a
    free-floating note."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.pie([1, 1, 1])
    path = tmp_path / "annotate_point_pie_miss.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    # Center of the axes box: inside the pie's hole, outside every wedge. No
    # prompt_text: a miss must bail out *before* window.prompt(), and a
    # page.once('dialog', ...) that's never consumed here would otherwise
    # leak forward and hijack the next test's prompt on this shared page.
    markers = _click_mode(page, "Annotate Point", 0.0, 0.0)
    assert markers == []


def test_annotate_free_tracks_data_coordinate_inside_an_axes(page, tmp_path):
    """Inside an axes, "Annotate Free" isn't locked to any datum, but it
    should still report a data coordinate (and pan/zoom with that axes),
    matching the pre-existing single "Annotate" tool's behavior."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 5.0])
    path = tmp_path / "annotate_free_inside.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 3.0, 2.0)
    markers = _click_mode(page, "Annotate Free", ux, uy, prompt_text="mid-plot note")
    assert len(markers) == 1
    m = markers[0]
    assert m["kind"] == "annotation" and m["text"] == "mid-plot note"
    assert m["axes"] == 0
    # A free note reports the exact clicked spot, not a snapped value -- allow
    # the same sub-pixel click-rounding slack as the mesh-picking tests.
    assert m["x"] == pytest.approx(3.0, abs=0.05)
    assert m["y"] == pytest.approx(2.0, abs=0.05)


def test_annotate_free_works_outside_any_axes(page, tmp_path):
    """Regression: the original single "Annotate" tool required being inside
    an axes (``if (!a) return``), so a figure-margin caption or a note
    between subplots was impossible. "Annotate Free" must work there too,
    reporting a figure pixel position since no data coordinate exists."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    path = tmp_path / "annotate_free_outside.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    # (2, 2) in SVG user space is the figure's top-left margin (see
    # test_click_on_empty_space_makes_no_stray_marker), well outside any axes.
    markers = _click_mode(page, "Annotate Free", 2, 2, prompt_text="figure caption")
    assert len(markers) == 1
    m = markers[0]
    assert m["kind"] == "annotation" and m["text"] == "figure caption"
    assert "axes" not in m, "a margin note has no data coordinate to report"
    assert m["px"] == pytest.approx(2, abs=1) and m["py"] == pytest.approx(2, abs=1)


def test_hide_annotations_toggle_hides_without_deleting(page, tmp_path):
    """"Hide Annotations" is a standalone toggle, not a mode -- it must hide
    every pin (Point Pick markers and Annotate notes alike) without deleting
    any of them, and bringing it back must restore them exactly, including
    their text."""
    import plotpress
    from pick_cases import px

    x, y = [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 4.0, 9.0]
    fig, ax = plotpress.subplots()
    ax.plot(x, y)
    path = tmp_path / "hide_annotations.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux0, uy0 = px(fig, 0, x[1], y[1])
    _click_mode(page, "Point Pick", ux0, uy0)
    ux1, uy1 = px(fig, 0, x[2], y[2])
    _click_mode(page, "Annotate Point", ux1, uy1, prompt_text="second point")
    assert len(page.evaluate("() => window.plotpressGetMarkers()")) == 2

    def toggle_and_read():
        return page.evaluate(
            """() => {
              let btn = null;
              document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
                if (b.textContent === 'Hide Annotations' ||
                    b.textContent === 'Show Annotations') btn = b;
              });
              btn.click();
              const pins = document.querySelectorAll('.plotpress-pin');
              const hiddenCount = Array.from(pins).filter(
                p => getComputedStyle(p).display === 'none').length;
              return {
                label: btn.textContent,
                pinCount: pins.length,
                hiddenCount: hiddenCount,
                markers: window.plotpressGetMarkers(),
              };
            }""")

    hidden = toggle_and_read()
    assert hidden["label"] == "Show Annotations"
    assert hidden["pinCount"] == 2, "toggling must not delete any pin"
    assert hidden["hiddenCount"] == 2, "every pin must be visually hidden"
    assert len(hidden["markers"]) == 2, "marker data must survive while hidden"

    shown = toggle_and_read()
    assert shown["label"] == "Hide Annotations"
    assert shown["hiddenCount"] == 0, "toggling back must restore visibility"
    assert shown["markers"] == hidden["markers"], (
        "restored markers must carry the exact same data, including text")


def test_hide_annotations_toggle_also_hides_static_boxed_text(page, tmp_path):
    """Hide Annotations must take a figure-drawn ax.text(bbox=...)/
    ax.annotate(bbox=...) callout too, not just interactive pins -- it reads
    as the same kind of "annotation" on screen. A plain unboxed label is not
    a callout and must stay visible throughout."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2, 3], [0, 1, 4, 9])
    ax.text(0.95, 0.95, "boxed", transform=ax.transAxes, ha="right", va="top",
            bbox={"facecolor": "yellow"})
    ax.text(0.05, 0.05, "plain", transform=ax.transAxes)
    ax.annotate("callout", xy=(1, 1), xytext=(2, 6),
               arrowprops={"color": "red"}, bbox={})
    path = tmp_path / "hide_annotations_textbox.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    def read():
        return page.evaluate(
            """() => {
              const boxes = document.querySelectorAll('.plotpress-textbox');
              const hidden = Array.from(boxes).filter(
                b => getComputedStyle(b).display === 'none').length;
              const plain = Array.from(document.querySelectorAll('text'))
                .find(t => t.textContent === 'plain');
              return {
                boxCount: boxes.length,
                hiddenCount: hidden,
                plainVisible: getComputedStyle(plain).display !== 'none',
              };
            }""")

    before = read()
    assert before["boxCount"] == 2   # the boxed text() and the boxed annotate()
    assert before["hiddenCount"] == 0
    assert before["plainVisible"]

    _click_toolbar(page, "Hide Annotations")
    hidden = read()
    assert hidden["hiddenCount"] == 2, "both boxed callouts must hide"
    assert hidden["plainVisible"], "an unboxed label is not a callout -- stays visible"

    _click_toolbar(page, "Show Annotations")
    shown = read()
    assert shown["hiddenCount"] == 0, "toggling back must restore both"


def test_standalone_false_scales_a_slider_figures_svg_to_its_container(page, tmp_path):
    """Regression: a plot_frames()/pcolormesh_frames() figure wraps the SVG in
    a div (so docked sliders can be positioned over it) that was hardcoded to
    display:inline-block -- shrink-wrapping it to the SVG's own fixed
    width/height attributes regardless of any CSS on the SVG itself. Combined
    with standalone=False's #plotpress-svg{width:100%} (see Report, which
    embeds every figure this way), that circular sizing left the SVG's
    percentage width unresolvable, so it silently fell back to its native
    pixel size -- exactly the bug this figure type has, and a plain (no
    slider) figure does not."""
    import numpy as np
    import plotpress

    x = np.linspace(0, 1, 50)
    Y = np.array([np.sin(2 * np.pi * x + t) for t in np.linspace(0, 2, 4)])
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.plot_frames(x, Y)
    path = tmp_path / "slider_scale.html"
    path.write_text(fig.to_html(standalone=False), encoding="utf-8")
    page.goto(path.as_uri())

    result = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          return {svgWidth: svg.getBoundingClientRect().width,
                  bodyWidth: document.body.getBoundingClientRect().width};
        }""")
    assert result["svgWidth"] == pytest.approx(result["bodyWidth"], abs=1), (
        "the SVG did not scale to fill its container: %r" % result)


def test_standalone_true_still_shrink_wraps_a_slider_figure(page, tmp_path):
    """The other side of the regression above: fixing standalone=False's
    wrap-div sizing (moved from a hardcoded inline style to a standalone-aware
    CSS class, see Figure.to_html) must not change standalone=True's own
    behavior -- a slider figure opened directly in its own tab should still
    render at its natural pixel size, shrink-wrapped and centered, not
    suddenly stretched to fill the browser window."""
    import numpy as np
    import plotpress

    x = np.linspace(0, 1, 50)
    Y = np.array([np.sin(2 * np.pi * x + t) for t in np.linspace(0, 2, 4)])
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.plot_frames(x, Y)
    path = tmp_path / "slider_standalone.html"
    path.write_text(fig.to_html(standalone=True), encoding="utf-8")
    page.goto(path.as_uri())

    result = page.evaluate(
        """() => {
          const svg = document.getElementById('plotpress-svg');
          const wrap = svg.parentElement;
          return {svgWidth: svg.getBoundingClientRect().width,
                  svgHeight: svg.getBoundingClientRect().height,
                  wrapWidth: wrap.getBoundingClientRect().width,
                  wrapClass: wrap.className};
        }""")
    assert result["wrapClass"] == "plotpress-svg-wrap"
    assert result["svgWidth"] == pytest.approx(600, abs=1)    # figsize(6,4) @ 100 dpi
    assert result["svgHeight"] == pytest.approx(400, abs=1)
    assert result["wrapWidth"] == pytest.approx(600, abs=1), (
        "the wrap div did not shrink-wrap to the SVG's natural size: %r" % result)


def test_report_stretches_a_slider_figure_to_the_iframes_width(page, tmp_path):
    """The same regression as above, exercised through the real Report path
    (rather than Figure.to_html directly) -- the iframe's own resize script
    must also settle on the true, scaled height, not a tiny one measured
    before the fix would have made the SVG collapse to its native size."""
    import numpy as np
    import plotpress

    x = np.linspace(0, 1, 50)
    Y = np.array([np.sin(2 * np.pi * x + t) for t in np.linspace(0, 2, 4)])
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.plot_frames(x, Y)
    report = plotpress.Report()
    report.add(fig)
    path = tmp_path / "slider_report.html"
    report.save(str(path))
    page.goto(path.as_uri())
    page.wait_for_timeout(200)

    result = page.evaluate(
        """() => {
          const f = document.querySelector('.plotpress-report-entry iframe');
          const svg = f.contentDocument.getElementById('plotpress-svg');
          return {svgWidth: svg.getBoundingClientRect().width,
                  iframeWidth: f.getBoundingClientRect().width,
                  iframeHeight: f.getBoundingClientRect().height};
        }""")
    # svgWidth is the iframe's *content* box; iframeWidth (its border box, per
    # _REPORT_STYLE's 1px iframe border) runs 2px wider -- both within a
    # couple px is "scaled to fill it", not coincidentally close.
    assert result["svgWidth"] == pytest.approx(result["iframeWidth"], abs=3)
    # height = width * (4/6), plus the toolbar's fixed 80px clearance (two
    # stacked button rows -- see _toolbar_clearance) and the one docked
    # slider's 60px allowance -- both are real body padding inside the
    # embedded document now (Figure.to_html, standalone=False), so
    # scrollHeight (what the resize script measures) already includes them.
    expected_h = result["svgWidth"] * 4 / 6 + 80 + 60
    assert result["iframeHeight"] == pytest.approx(expected_h, abs=3)


def test_standalone_false_toolbar_does_not_overlap_the_svg(page, tmp_path):
    """Regression: the toolbar is position:fixed, so it takes no layout
    space of its own -- something else has to reserve room for it, or it
    draws directly over whatever's in the figure's own top-right corner (a
    legend, here). standalone=False's SVG sits flush against the body's
    edges rather than getting centering slack to absorb this, so the body
    padding Figure.to_html now adds for exactly this case has to actually be
    there, not just present in the CSS text but overridden or miscomputed."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4], label="x")
    ax.legend(loc="upper right")
    path = tmp_path / "toolbar_clearance.html"
    path.write_text(fig.to_html(standalone=False), encoding="utf-8")
    page.goto(path.as_uri())

    result = page.evaluate(
        """() => {
          // .plotpress-toolbar-wrap, not .plotpress-toolbar -- the toolbar
          // is two stacked rows now (nav then mark), and only the wrap's
          // own box covers both; the first row alone would under-measure
          // the real bottom edge and miss overlap the second row causes.
          const toolbar = document.querySelector('.plotpress-toolbar-wrap');
          const svg = document.getElementById('plotpress-svg');
          const t = toolbar.getBoundingClientRect(), s = svg.getBoundingClientRect();
          return {toolbarBottom: t.bottom, svgTop: s.top};
        }""")
    assert result["toolbarBottom"] <= result["svgTop"], (
        "the toolbar overlaps the top of the figure: %r" % result)


def test_report_resize_does_not_collapse_a_not_yet_loaded_lazy_entry(page, tmp_path):
    """Regression: the resize-fit script used to measure and resize every
    report iframe unconditionally, including one that is loading="lazy" and
    hasn't fired its own `load` event yet (still far below the fold) -- its
    placeholder document's near-zero scrollHeight collapsed that entry's
    still-showing initial height guess to almost nothing the moment any
    resize event fired, well before the reader ever scrolled near it."""
    import numpy as np
    import plotpress

    fig1, ax1 = plotpress.subplots()
    ax1.plot([0, 1], [0, 1])
    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 1], [1, 0])

    report = plotpress.Report()
    report.add(fig1)
    report.add(fig2)
    path = tmp_path / "lazy_report.html"
    report.save(str(path))
    page.goto(path.as_uri())

    result = page.evaluate(
        """() => {
          const iframes = Array.from(document.querySelectorAll('.plotpress-report-entry iframe'));
          const second = iframes[1];
          const before = {loaded: !!second.dataset.loaded, height: second.getAttribute('height')};
          window.dispatchEvent(new Event('resize'));
          return {before: before, secondHeightAfter: second.style.height};
        }""")
    if result["before"]["loaded"]:
        pytest.skip("second iframe already loaded before the page settled -- "
                    "nothing to regress-test here in this environment")
    # Unloaded means fit() must have no-op'd: no inline style height was ever
    # set, so the browser still shows the initial `height` attribute's guess.
    assert result["secondHeightAfter"] == "", (
        "resize touched an iframe that had not loaded yet: %r" % result)


# -- Save / Save As --------------------------------------------------------

def _click_toolbar(page, label):
    page.evaluate(
        """(label) => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === label) b.click(); })""", label)


def test_save_as_downloads_a_page_that_restores_pins_view_and_toggles(page, tmp_path):
    """The core round trip: pan/zoom, a Point Pick, an Annotate Point note, a
    free annotation, a hidden legend series, and Hide Annotations all have to
    come back exactly as they were when the downloaded copy is reopened --
    not just the data plot_data()/load_data() already covers, the live
    session's own state."""
    import plotpress
    from pick_cases import px

    x = [0.0, 1.0, 2.0, 3.0]
    fig, ax = plotpress.subplots()
    ax.plot(x, [0.0, 1.0, 4.0, 9.0], label="sq")
    ax.plot(x, [0.0, 1.0, 2.0, 3.0], label="lin")
    ax.legend()
    path = tmp_path / "save_roundtrip.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())
    # The File System Access API's picker needs a real OS dialog Playwright
    # can't drive headlessly; deleting it forces the same plain-download
    # fallback real users hit in Firefox/Safari, so the round trip below can
    # actually run to completion instead of hanging on an unanswered picker.
    page.evaluate("() => { delete window.showSaveFilePicker; }")

    ux, uy = px(fig, 0, x[2], 4.0)   # a real point on the "sq" line
    markers = _click_mode(page, "Point Pick", ux, uy)
    assert len(markers) == 1

    markers = _click_mode(page, "Annotate Point", *px(fig, 0, x[1], 1.0),
                          prompt_text="watch me")
    assert len(markers) == 2

    # Annotate Free in the margin, above the axes -- not locked to any datum.
    page.once("dialog", lambda d: d.accept("free note"))
    _click_toolbar(page, "Annotate Free")
    box = page.eval_on_selector(
        "#plotpress-svg", "el => { const r = el.getBoundingClientRect(); "
        "return {x: r.x, y: r.y}; }")
    page.mouse.click(box["x"] + 5, box["y"] + 3)
    assert len(page.evaluate("() => window.plotpressGetMarkers()")) == 3

    # Hide the "sq" legend series.
    page.evaluate(
        """() => document.querySelectorAll('.plotpress-legend text').forEach(t => {
             if (t.textContent === 'sq') t.dispatchEvent(new MouseEvent('click', {bubbles: true}));
           })""")

    # Ctrl+wheel-zoom the whole figure.
    _click_toolbar(page, "Zoom")
    svg_box = page.eval_on_selector(
        "#plotpress-svg", "el => { const r = el.getBoundingClientRect(); "
        "return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
    page.mouse.move(svg_box["x"] + svg_box["w"] * 0.3, svg_box["y"] + svg_box["h"] * 0.3)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -300)
    page.keyboard.up("Control")
    zoomed_width_before = page.eval_on_selector(
        "#plotpress-svg", "el => el.getBoundingClientRect().width")
    scroll_before = page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")

    # Hide Annotations.
    _click_toolbar(page, "Hide Annotations")

    with page.expect_download() as dl_info:
        _click_toolbar(page, "Save As")
    saved = tmp_path / "save_roundtrip_saved.html"
    dl_info.value.save_as(str(saved))

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(saved.as_uri())
    assert not errors, "JS error loading the saved page: %s" % errors

    zoomed_width_after = page.eval_on_selector(
        "#plotpress-svg", "el => el.getBoundingClientRect().width")
    scroll_after = page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")
    assert zoomed_width_after == pytest.approx(zoomed_width_before, abs=1.0)
    assert scroll_after == scroll_before

    restored = page.evaluate("() => window.plotpressGetMarkers()")
    assert len(restored) == 3
    texts = sorted(m.get("text", "") for m in restored)
    assert texts == ["", "free note", "watch me"]

    assert page.eval_on_selector(
        "#plotpress-svg", "el => el.classList.contains('plotpress-hide-annotations')")

    sq_display = page.evaluate(
        """() => { const s = [...document.querySelectorAll('.plotpress-series')]
                     .find(el => el.getAttribute('data-label') === 'sq');
                   return s ? s.style.display : null; }""")
    assert sq_display == "none"

    toggle_label = page.evaluate(
        """() => { const b = [...document.querySelectorAll('.plotpress-toolbar button')]
                     .find(b => b.textContent.includes('Annotations'));
                   return b ? b.textContent : null; }""")
    assert toggle_label == "Show Annotations"


def test_save_twice_does_not_duplicate_the_saved_state_payload(page, tmp_path):
    """A second Save As, starting from an already-saved copy, must replace
    the previous payload rather than append a second one -- getElementById
    would otherwise return whichever the parser adds first, silently
    ignoring every save after the first."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    path = tmp_path / "save_twice.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())
    # See test_save_as_downloads_a_page_that_restores_pins_view_and_toggles:
    # the picker needs a real OS dialog Playwright can't drive headlessly.
    page.evaluate("() => { delete window.showSaveFilePicker; }")

    with page.expect_download() as dl_info:
        _click_toolbar(page, "Save As")
    once = tmp_path / "save_twice_1.html"
    dl_info.value.save_as(str(once))

    page.goto(once.as_uri())
    page.evaluate("() => { delete window.showSaveFilePicker; }")
    _click_toolbar(page, "Point Pick")
    page.mouse.click(
        *page.eval_on_selector(
            "#plotpress-svg", "el => { const r = el.getBoundingClientRect(); "
            "return [r.x + r.width / 2, r.y + r.height / 2]; }"))
    with page.expect_download() as dl_info2:
        _click_toolbar(page, "Save As")
    twice = tmp_path / "save_twice_2.html"
    dl_info2.value.save_as(str(twice))

    text = twice.read_text(encoding="utf-8")
    assert text.count('id="plotpress-saved-state"') == 1

    page.goto(twice.as_uri())
    assert len(page.evaluate("() => window.plotpressGetMarkers()")) == 1


def test_save_falls_back_to_download_without_file_system_access_api(page, tmp_path):
    """True in-place overwrite needs the File System Access API; anywhere
    it's unavailable (Firefox/Safari, or simulated here), Save must still
    produce something -- a plain download -- rather than silently doing
    nothing."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    path = tmp_path / "save_fallback.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())
    page.evaluate("() => { delete window.showSaveFilePicker; }")

    with page.expect_download() as dl_info:
        _click_toolbar(page, "Save")
    assert dl_info.value.suggested_filename.endswith(".html")


def test_toolbar_hides_and_recovers(page, tmp_path):
    """The toolbar's two button rows (nav/mark -- see the grouping test
    below) can both be collapsed together to declutter the view (a
    screenshot, say) -- but the toggle that collapses them must itself
    never be part of what gets hidden, or there would be no way back
    without reloading the page."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    path = tmp_path / "toolbar_toggle.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    nav_bar = page.locator(".plotpress-toolbar-nav")
    mark_bar = page.locator(".plotpress-toolbar-mark")
    toggle = page.locator(".plotpress-toolbar-toggle")
    assert nav_bar.is_visible()
    assert mark_bar.is_visible()
    assert toggle.is_visible()
    n_buttons = nav_bar.locator("button").count() + mark_bar.locator("button").count()
    assert n_buttons > 1   # Span/Zoom/.../Extract, not just the toggle itself

    toggle.click()
    assert not nav_bar.is_visible()
    assert not mark_bar.is_visible()
    assert toggle.is_visible(), "the toggle must survive hiding the rows it controls"

    toggle.click()
    assert nav_bar.is_visible()
    assert mark_bar.is_visible()
    assert (nav_bar.locator("button").count()
           + mark_bar.locator("button").count()) == n_buttons


def test_builtin_toolbar_is_grouped_into_a_nav_row_and_a_mark_row(page, tmp_path):
    """The built-in toolbar is two coherent groups, not one long row:
    navigate the view and persist it (Span/Zoom/Magnify/Reset/Save/Save As)
    above, mark data and get it out (Point Pick/Annotate Point/Annotate
    Free/Hide Annotations/Extract) below."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    path = tmp_path / "toolbar_grouping.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    nav_labels = page.locator(".plotpress-toolbar-nav button").all_inner_texts()
    mark_labels = page.locator(".plotpress-toolbar-mark button").all_inner_texts()
    assert nav_labels == ["Span", "Zoom", "Magnify", "Reset", "Save", "Save As"]
    assert mark_labels == ["Point Pick", "Annotate Point", "Annotate Free",
                           "Hide Annotations", "Extract"]

    nav_top = page.locator(".plotpress-toolbar-nav").bounding_box()["y"]
    mark_top = page.locator(".plotpress-toolbar-mark").bounding_box()["y"]
    assert mark_top > nav_top, "the mark row must render below the nav row"


def test_extra_js_add_tool_registers_a_button_in_the_real_toolbar(page, tmp_path):
    """plotpressAddTool({label, onClick}) -- the plain-action-button shape,
    like the built-in Extract/Save: fires immediately, never joins the
    single-selection group."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    extra_js = """
      window.plotpressAddTool({
        label: 'Custom Action',
        onClick: function () { window.__customActionFired = true; },
      });
    """
    path = tmp_path / "add_tool_action.html"
    path.write_text(fig.to_html(interactive=True, extra_js=extra_js), encoding="utf-8")
    page.goto(path.as_uri())

    labels = page.evaluate(
        "() => Array.from(document.querySelectorAll('.plotpress-toolbar button'))"
        ".map(b => b.textContent)")
    assert "Custom Action" in labels

    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
             if (b.textContent === 'Custom Action') b.click();
           })""")
    assert page.evaluate("() => window.__customActionFired") is True
    active = page.evaluate(
        "() => Array.from(document.querySelectorAll('.plotpress-toolbar button.active'))"
        ".map(b => b.textContent)")
    assert active == [], "an action button (no mode) must never become 'active'"


def test_extra_js_add_tool_mode_joins_single_selection_group(page, tmp_path):
    """plotpressAddTool({label, mode, onClick, onEnter, onExit, cursor}) --
    a real mode: selecting it deselects whatever built-in tool was active
    and vice versa, its own onClick fires with a real user-space point via
    the same click pipeline Point Pick uses, and onEnter/onExit fire on
    entry/exit."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    extra_js = """
      window.plotpressAddTool({
        label: 'Custom Mode', mode: 'custom-mode', cursor: 'help',
        onClick: function (ev, p) { window.__customClickPoint = {x: p.x, y: p.y}; },
        onEnter: function () { window.__enterCount = (window.__enterCount || 0) + 1; },
        onExit: function () { window.__exitCount = (window.__exitCount || 0) + 1; },
      });
    """
    path = tmp_path / "add_tool_mode.html"
    path.write_text(fig.to_html(interactive=True, extra_js=extra_js), encoding="utf-8")
    page.goto(path.as_uri())

    _click_mode(page, "Span", *px(fig, 0, 0.5, 0.5))
    assert page.evaluate(
        "() => document.querySelector('.plotpress-toolbar button[data-mode=\"span\"]')"
        ".classList.contains('active')")

    ux, uy = px(fig, 0, 0.5, 0.5)
    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button').forEach(b => {
             if (b.textContent === 'Custom Mode') b.click();
           })""")
    assert page.evaluate("() => window.__enterCount") == 1
    assert not page.evaluate(
        "() => document.querySelector('.plotpress-toolbar button[data-mode=\"span\"]')"
        ".classList.contains('active')"), "selecting the custom mode must deselect Span"
    assert page.evaluate(
        "() => document.querySelector('.plotpress-toolbar button[data-mode=\"custom-mode\"]')"
        ".classList.contains('active')")
    assert page.evaluate("() => getComputedStyle(document.getElementById('plotpress-svg')).cursor") == "help"

    page.evaluate(
        """([ux, uy]) => {
          const svg = document.getElementById('plotpress-svg');
          const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
          const c = pt.matrixTransform(svg.getScreenCTM());
          const el = document.elementFromPoint(c.x, c.y) || svg;
          el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, clientX:c.x, clientY:c.y, button:0}));
          el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, clientX:c.x, clientY:c.y, button:0}));
          el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, clientX:c.x, clientY:c.y, button:0}));
        }""", [ux, uy])
    clicked = page.evaluate("() => window.__customClickPoint")
    assert clicked is not None
    assert clicked["x"] == pytest.approx(ux, abs=1.0)
    assert clicked["y"] == pytest.approx(uy, abs=1.0)

    _click_mode(page, "Span", *px(fig, 0, 0.2, 0.2))
    assert page.evaluate("() => window.__exitCount") == 1


def test_plotpress_to_data_matches_point_pick_readout(page, tmp_path):
    """window.plotpressToData(p) must resolve to the same data value Point
    Pick itself would report for the same pixel -- it's documented as
    reusing that exact conversion, not an approximation of it."""
    import plotpress
    from pick_cases import px

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    path = tmp_path / "to_data_check.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    ux, uy = px(fig, 0, 0.5, 0.5)
    result = page.evaluate(
        """([ux, uy]) => {
          const svg = document.getElementById('plotpress-svg');
          const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
          const c = pt.matrixTransform(svg.getScreenCTM());
          const p = {x: ux, y: uy};
          return window.plotpressToData(p);
        }""", [ux, uy])
    assert str(result["axes"]) == "0"   # axes keys come through JS as strings
    assert result["x"] == pytest.approx(0.5, abs=0.01)
    assert result["y"] == pytest.approx(0.5, abs=0.01)


def test_plotpress_to_data_returns_null_off_any_axes(page, tmp_path):
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    path = tmp_path / "to_data_null.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    result = page.evaluate("() => window.plotpressToData({x: -1000, y: -1000})")
    assert result is None


def test_include_default_js_false_drops_the_toolbar_and_add_tool(page, tmp_path):
    """The 'override' case, end to end: no toolbar, no plotpressAddTool --
    extra_js is the only thing driving the page, working off the raw
    #plotpress-meta payload directly."""
    import plotpress

    fig, ax = plotpress.subplots()
    x = [0.0, 1.0]
    ax.plot(x, [0.0, 1.0])
    extra_js = """
      var meta = JSON.parse(document.getElementById('plotpress-meta').textContent);
      window.__axesCountFromMeta = Object.keys(meta).length;
      window.__addToolExists = typeof window.plotpressAddTool;
    """
    path = tmp_path / "override_mode.html"
    path.write_text(
        fig.to_html(interactive=True, include_default_js=False,
                    binary_pick_data=False, extra_js=extra_js),
        encoding="utf-8")
    page.goto(path.as_uri())

    assert page.evaluate("() => !!document.querySelector('.plotpress-toolbar')") is False
    assert page.evaluate("() => window.__addToolExists") == "undefined"
    assert page.evaluate("() => window.__axesCountFromMeta") == 1


def test_extra_js_add_tool_lands_in_its_own_row_not_the_builtin_toolbar(page, tmp_path):
    """Custom tools must not be appended into plotpress's own .plotpress-toolbar
    row -- a caller adding several tools would otherwise keep lengthening
    the built-in row and blur which buttons are plotpress's own vs the
    page's. They get their own .plotpress-toolbar-custom row instead,
    stacked below, and the collapse toggle hides both together."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    extra_js = "window.plotpressAddTool({label: 'Custom', onClick: function () {}});"
    path = tmp_path / "custom_row.html"
    path.write_text(fig.to_html(interactive=True, extra_js=extra_js), encoding="utf-8")
    page.goto(path.as_uri())

    nav_bar = page.locator(".plotpress-toolbar-nav")
    mark_bar = page.locator(".plotpress-toolbar-mark")
    custom_bar = page.locator(".plotpress-toolbar-custom")
    assert custom_bar.count() == 1
    assert "Custom" not in nav_bar.inner_text()
    assert "Custom" not in mark_bar.inner_text()
    assert "Custom" in custom_bar.inner_text()

    page.locator(".plotpress-toolbar-toggle").click()
    assert not nav_bar.is_visible()
    assert not mark_bar.is_visible()
    assert not custom_bar.is_visible(), "the toggle must hide the custom row too"

    page.locator(".plotpress-toolbar-toggle").click()
    assert nav_bar.is_visible()
    assert mark_bar.is_visible()
    assert custom_bar.is_visible()


def test_no_custom_row_created_when_no_custom_tools_are_added(page, tmp_path):
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    path = tmp_path / "no_custom_row.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())
    assert page.locator(".plotpress-toolbar-custom").count() == 0
