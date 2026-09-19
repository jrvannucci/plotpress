"""The interactive toolbar is modular: a baseline every page gets, plus
add-ons a caller opts into by name via ``options=``.

The Python half (validation, what gets emitted) runs everywhere; the browser
half checks which menus the JS actually builds, and is opt-in like the other
Playwright tests (``pytest -m browser``).
"""

import json
import re

import numpy as np
import pytest

import plotpress

CORE = ["Pan/Zoom", "Home", "Fit Width", "Axes", "Point Picking", "Annotate",
        "Extract", "File"]


def _line_fig():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 4])
    return fig


def _mesh_fig():
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(20.0).reshape(4, 5))
    return fig


def _emitted_options(html):
    m = re.search(r"window\.PLOTPRESS_OPTIONS=(\[.*?\]);", html)
    assert m, "no PLOTPRESS_OPTIONS config was emitted"
    return json.loads(m.group(1))


def test_default_has_no_optional_add_ons():
    assert _emitted_options(_line_fig().to_html()) == []


def test_options_are_emitted_without_duplicates():
    assert _emitted_options(
        _line_fig().to_html(options=["slice", "slice"])) == ["slice"]


def test_unknown_option_names_the_valid_ones():
    with pytest.raises(ValueError, match="slice"):
        _line_fig().to_html(options=["sliec"])


def test_point_picking_is_not_an_option():
    # It's part of every page's core toolbar, so asking for it by name is a
    # mistake worth surfacing rather than silently accepting.
    with pytest.raises(ValueError, match="annotation-pointpicking"):
        _line_fig().to_html(options=["annotation-pointpicking"])


def test_bare_string_is_rejected_rather_than_split_into_letters():
    with pytest.raises(TypeError, match=r"options=\['slice'\]"):
        _line_fig().to_html(options="slice")


def test_save_forwards_options(tmp_path):
    path = tmp_path / "f.html"
    _line_fig().save(str(path), interactive=True, options=["slice"])
    assert _emitted_options(path.read_text(encoding="utf-8")) == ["slice"]


def test_report_forwards_options(tmp_path):
    report = plotpress.Report()
    report.add(_line_fig())
    path = tmp_path / "r.html"
    report.save(str(path), options=["slice"])
    # Each figure is an escaped srcdoc, so look for the escaped form.
    assert "PLOTPRESS_OPTIONS=[&quot;slice&quot;]" in \
        path.read_text(encoding="utf-8")


def test_data_payloads_do_not_depend_on_options(tmp_path):
    # load_data() reads the embedded pick payload back out of a saved page, so
    # a page saved without options has to carry the same data as one with them.
    fig = _line_fig()
    baseline, full = tmp_path / "b.html", tmp_path / "f.html"
    fig.save(str(baseline), interactive=True)
    fig.save(str(full), interactive=True, options=["slice"])
    for p in (baseline, full):
        assert 'id="plotpress-pick"' in p.read_text(encoding="utf-8")
    a, b = (plotpress.load_data(str(p)) for p in (baseline, full))
    assert repr(a) == repr(b)


# ---- browser: which menus the JS actually builds --------------------------

@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="needs Playwright: pip install -e '.[browser]'")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except sync_api.Error as exc:                     # pragma: no cover
            pytest.skip("Chromium is not installed: %s" % exc)
        p = browser.new_page(viewport={"width": 1100, "height": 850})
        try:
            yield p
        finally:
            browser.close()


def _all_button_text(page, tmp_path, fig, **kw):
    path = tmp_path / "t.html"
    path.write_text(fig.to_html(interactive=True, **kw), encoding="utf-8")
    page.goto(path.as_uri())
    return page.evaluate(
        "Array.from(document.querySelectorAll('.plotpress-menubar button'))"
        ".map(b => b.textContent.replace('\u25be', '').trim())")


@pytest.mark.browser
def test_default_is_the_core_toolbar_without_slice(page, tmp_path):
    labels = _all_button_text(page, tmp_path, _mesh_fig())
    for name in CORE:
        assert name in labels
    assert "Slice" not in labels


@pytest.mark.browser
def test_slice_option_adds_slice_and_keeps_the_core(page, tmp_path):
    labels = _all_button_text(page, tmp_path, _mesh_fig(), options=["slice"])
    for name in CORE + ["Slice"]:
        assert name in labels


@pytest.mark.browser
def test_slice_option_still_needs_a_mesh(page, tmp_path):
    labels = _all_button_text(page, tmp_path, _line_fig(), options=["slice"])
    assert "Slice" not in labels
