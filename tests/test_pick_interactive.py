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
