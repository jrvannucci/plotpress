"""End-to-end point-picking tests: real clicks in a real browser.

The picking logic lives in JavaScript (``simpleplot/_interactive.py``), so the
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
    import simpleplot

    fig, ax = simpleplot.subplots()
    ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 4.0])
    path = tmp_path / "empty.html"
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    n = page.evaluate(
        """() => {
          const svg = document.getElementById('simpleplot-svg');
          document.querySelectorAll('.simpleplot-toolbar button')
            .forEach(b => { if (b.textContent === 'Point Pick') b.click(); });
          // (2, 2) in SVG user space is the figure's top-left margin, well
          // outside the axes rectangle.
          const pt = svg.createSVGPoint();
          pt.x = 2; pt.y = 2;
          const c = pt.matrixTransform(svg.getScreenCTM());
          (document.elementFromPoint(c.x, c.y) || svg).dispatchEvent(
            new MouseEvent('click', {bubbles: true, clientX: c.x, clientY: c.y}));
          return window.simpleplotGetMarkers().length;
        }""")
    assert n == 0, "a click in the margin created %d marker(s)" % n
