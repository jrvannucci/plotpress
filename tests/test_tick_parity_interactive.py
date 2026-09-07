"""Regression test: the interactive HTML's client-side tick-formatting JS
(``plotpress/_interactive.py``'s ``resolveAxisTicks``/``jsPiTick``/
``jsPrintfTick``/``jsDateTicks``) must produce the same tick labels
``plotpress.ticker``/``plotpress.dates`` compute in Python, for the *same*
resolved view range, after a real zoom in a real browser -- not just on
first render.

An earlier audit found two real, silent divergences here (``jsPiTick`` used
the wrong fraction algorithm; the raw ``%``-format mirror diverged from
Python's real ``%`` operator in five ways), both caught only by hand
comparing Node output to Python output -- nothing exercised the actual
post-zoom JS path. This closes that gap: each case drags a real "Axis Zoom"
rubber-band on the real toolbar, reads back the resolved view range via the
same public ``window.plotpressToData()`` a custom tool would use, and checks
the tick labels actually rendered against what Python's own resolver
computes for that exact range.

Opt-in, because it needs a browser (see ``test_pick_interactive.py``, whose
fixture/skip pattern this mirrors)::

    pip install -e ".[browser]" && playwright install chromium
    pytest tests/test_tick_parity_interactive.py
"""
import pathlib

import numpy as np
import pytest

import plotpress
from plotpress.svg import axes_metadata
from plotpress.ticker import resolve_axis_tick_labels, resolve_axis_ticks

pytestmark = pytest.mark.browser

HARNESS = (pathlib.Path(__file__).parent / "tick_parity_harness.js").read_text()


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
        p = browser.new_page(viewport={"width": 900, "height": 700})
        try:
            yield p
        finally:
            browser.close()


def _zoom_and_read(page, tmp_path, fig, name):
    """Drag a real Axis-Zoom rubber-band across ~70% of axes 0's own box,
    then return {"xrange", "yrange", "labels"} for the range it resolved to.
    """
    box = axes_metadata(fig)[0]
    args = {
        "x0": box["x"] + 0.15 * box["w"], "y0": box["y"] + 0.15 * box["h"],
        "x1": box["x"] + 0.85 * box["w"], "y1": box["y"] + 0.85 * box["h"],
        "axesIndex": 0, "box": box,
    }
    path = tmp_path / ("%s.html" % name)
    path.write_text(fig.to_html(interactive=True), encoding="utf-8")
    page.goto(path.as_uri())

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    out = page.evaluate(HARNESS, args)
    assert not errors, "JavaScript errors on %s: %s" % (name, errors)
    if out.get("error"):
        pytest.fail("%s: %s" % (name, out["error"]))
    return out


def _assert_labels_match(out, expected_labels, name):
    for lab in expected_labels:
        assert lab in out["labels"], (
            "%s: expected tick label %r (zoomed x-range %r) not found among "
            "rendered labels %r" % (name, lab, out["xrange"], out["labels"]))


def test_pi_formatted_locator_matches_after_a_real_zoom(page, tmp_path):
    """Regresses jsPiTick's wrong-fraction bug (it used to round onto a fixed
    1/12 grid instead of a real continued-fraction search, so e.g. a tick at
    0.2*pi rendered "pi/6" post-zoom instead of the correct "pi/5"). The
    locator base is deliberately pi/5, not pi/2 or pi/3 -- either of those
    already lands exactly on the 1/12 grid (6/12, 4/12) and would pass even
    with the old, wrong algorithm; pi/5 doesn't (its multiples need a
    denominator the fixed grid can't represent), which is what actually
    exercises the bug."""
    fig, ax = plotpress.subplots()
    x = np.linspace(0, 6 * np.pi, 400)
    ax.plot(x, np.sin(x))
    ax.set_xlim(0, 6 * np.pi)
    ax.set_xlocator({"kind": "multiple", "base": np.pi / 5})
    ax.set_xformat("pi")

    out = _zoom_and_read(page, tmp_path, fig, "pi_zoom")
    xmin, xmax = out["xrange"]
    ticks = resolve_axis_ticks(xmin, xmax, locator={"kind": "multiple", "base": np.pi / 5})
    _assert_labels_match(out, resolve_axis_tick_labels(ticks, fmt="pi"), "pi-format")


def test_raw_percent_format_string_matches_after_a_real_zoom(page, tmp_path):
    """Regresses jsPrintfTick's "%.0f%%" escaping bug (a literal %% next to
    a real conversion rendered as a doubled %% instead of collapsing to one
    "%") and its %d-truncates-not-rounds bug."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2, 3, 4], [3.4, 27.6, 58.1, 71.9, 94.5])
    ax.set_xlim(0, 4)
    ax.set_yformat("%.0f%%")

    out = _zoom_and_read(page, tmp_path, fig, "printf_zoom")
    ymin, ymax = out["yrange"]
    ticks = resolve_axis_ticks(ymin, ymax)
    _assert_labels_match(out, resolve_axis_tick_labels(ticks, fmt="%.0f%%"), "%-format")


def test_date_axis_ticks_match_after_a_real_zoom(page, tmp_path):
    """Regresses any jsDateTicks/jsFormatDateTicks divergence from
    dates.date_ticks()/format_date_ticks() for an arbitrary post-zoom range."""
    fig, ax = plotpress.subplots()
    dates = np.array(["2022-01-01", "2022-09-01", "2023-06-01", "2024-02-01",
                      "2025-01-01"], dtype="datetime64[D]")
    ax.plot(dates, [1, 2, 1.5, 2.5, 2])

    out = _zoom_and_read(page, tmp_path, fig, "date_zoom")
    xmin, xmax = out["xrange"]
    ticks = resolve_axis_ticks(xmin, xmax, is_date=True)
    _assert_labels_match(out, resolve_axis_tick_labels(ticks, is_date=True), "date")
