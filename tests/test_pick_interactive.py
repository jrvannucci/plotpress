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
          const pt = svg.createSVGPoint();
          pt.x = p[0]; pt.y = p[1];
          const c = pt.matrixTransform(svg.getScreenCTM());
          const el = document.elementFromPoint(c.x, c.y) || svg;
          el.dispatchEvent(new WheelEvent('wheel', {
            bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, deltaY: -100
          }));
          return document.getElementById('zoom1').getAttribute('transform') !== null;
        }""", target_px)
    assert zoomed, "Zoom must still work on a set_pickable(False) axes"


def test_minor_ticks_reposition_on_zoom(page, tmp_path):
    """Regression: rebuildTicks() only recomputed major ticks on pan/zoom;
    minorticks_on()'s marks stayed frozen at their initial positions instead
    of tracking the new, narrower range."""
    import plotpress

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 10.0])
    ax.minorticks_on()
    path = tmp_path / "minor_zoom.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    before = page.evaluate(
        "() => document.getElementById('ticks0').querySelectorAll('line').length")

    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Zoom') b.click(); })""")
    box = page.eval_on_selector(
        "#plotpress-svg",
        "el => { const r = el.getBoundingClientRect(); "
        "return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
    page.mouse.move(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    for _ in range(15):
        page.mouse.wheel(0, -100)   # negative deltaY zooms in

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

    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Zoom') b.click(); })""")
    box = page.eval_on_selector(
        "#plotpress-svg",
        "el => { const r = el.getBoundingClientRect(); "
        "return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
    page.mouse.move(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    for _ in range(15):
        page.mouse.wheel(0, -100)   # negative deltaY zooms in

    after = page.evaluate(stroke_query)
    assert "#d62728" in after and "#2ca02c" in after, (
        "tick_params() colors reverted to the default style after zoom: %r" % after)


def test_point_pick_large_series_stays_accurate_after_zoom(page, tmp_path):
    """Regression: nearestVertex() -- the fallback Point Pick uses for a
    series too large to embed in the pick payload (over to_html()'s default
    pick_max_points=20000) -- compared the click against that series' raw
    SVG geometry, which is fixed in the axes' *original* pre-zoom limits.
    After the axes was zoomed, a click resolved to whatever vertex happened
    to sit at that pixel position in the stale, pre-zoom coordinate space --
    a wrong, sometimes wildly-off datum, not the one under the cursor.

    zoomAxesAt() keeps the data value under the cursor fixed while it zooms,
    so wheel-zooming and then clicking at the *same* screen position must
    still resolve to (roughly) the same data point if the fallback is
    reading the right coordinate space."""
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
    cx, cy = page.evaluate(
        """([ux, uy]) => {
          const svg = document.getElementById('plotpress-svg');
          const pt = svg.createSVGPoint(); pt.x = ux; pt.y = uy;
          const c = pt.matrixTransform(svg.getScreenCTM());
          return [c.x, c.y];
        }""",
        px(fig, 0, target_x, target_y))

    page.evaluate(
        """() => document.querySelectorAll('.plotpress-toolbar button')
             .forEach(b => { if (b.textContent === 'Zoom') b.click(); })""")
    page.mouse.move(cx, cy)
    for _ in range(15):
        page.mouse.wheel(0, -100)   # zoom in around (cx, cy), invariant there

    markers = _click_mode(page, "Point Pick",
                           *px(fig, 0, target_x, target_y))
    assert len(markers) == 1
    m = markers[0]
    assert abs(m["x"] - target_x) < 0.5, (
        "picked x is far from the zoomed-in cursor position: %r" % m)
    assert abs(m["y"] - target_y) < 0.5, (
        "picked y is far from the zoomed-in cursor position: %r" % m)


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
