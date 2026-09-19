"""The Slice tool's two views (``options=["slice"]``: profile replaces the
heatmap; ``options=["slice-companion-panel"]``: profile in a strip beside it)
and the startup settings either option accepts.

The Python half needs nothing; the browser half is opt-in (``pytest -m
browser``) like the other Playwright tests.
"""

import io
import json
import re

import numpy as np
import pytest

import plotpress


def _grid_fig(n=(2, 3)):
    fig, axs = plotpress.subplots(*n, figsize=(10, 6))
    x, y = np.linspace(0, 10, 21), np.linspace(0, 8, 17)
    rng = np.random.default_rng(3)
    for ax in np.ravel(axs):
        ax.pcolormesh(x, y, rng.normal(size=(16, 20)), cmap="RdBu_r", vmin=-3, vmax=3)
    fig.tight_layout()
    return fig


def _config(html):
    m = re.search(r"window\.PLOTPRESS_OPTION_CONFIG=(\{.*?\});</script>", html)
    assert m, "no PLOTPRESS_OPTION_CONFIG was emitted"
    return json.loads(m.group(1))


# ---- Python: startup settings ------------------------------------------------

def test_dict_options_emit_their_settings():
    html = _grid_fig().to_html(options={
        "slice-companion-panel": {"enabled": True, "orientation": "y",
                                  "link_all": True, "index": 4, "panel_size": 0.4},
        "slice": True,
    })
    cfg = _config(html)
    assert cfg["slice-companion-panel"]["orientation"] == "y"
    assert cfg["slice-companion-panel"]["panel_size"] == 0.4
    assert cfg["slice"] == {}


def test_list_options_have_empty_settings():
    assert _config(_grid_fig().to_html(options=["slice"])) == {"slice": {}}


@pytest.mark.parametrize("settings, message", [
    ({"orientation": "z"}, "one of 'x', 'y'"),
    ({"enabled": "yes"}, "True or False"),
    ({"range": "wide"}, "one of 'auto'"),
    ({"index": -1}, "non-negative integer"),
    ({"index": 1.5}, "non-negative integer"),
    ({"panel_size": 0.9}, "between 0.1 and 0.6"),
    ({"range": "custom"}, "range_min and"),
    ({"range": "custom", "range_min": 2, "range_max": 1}, "range_min < range_max"),
    ({"show_view": True}, "unknown setting"),   # belongs to "slice", not the panel
    ({"nope": 1}, "unknown setting"),
])
def test_bad_panel_settings_are_rejected(settings, message):
    with pytest.raises(ValueError, match=message):
        _grid_fig().to_html(options={"slice-companion-panel": settings})


def test_view_only_settings_belong_to_slice():
    html = _grid_fig().to_html(options={"slice": {"show_view": True}})
    assert _config(html)["slice"] == {"show_view": True}
    with pytest.raises(ValueError, match="unknown setting"):
        _grid_fig().to_html(options={"slice": {"panel_size": 0.3}})


def test_non_dict_settings_are_rejected():
    with pytest.raises(TypeError, match="dict of settings"):
        _grid_fig().to_html(options={"slice": "on"})


# ---- browser ---------------------------------------------------------------

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
        p = browser.new_page(viewport={"width": 1300, "height": 900})
        try:
            yield p
        finally:
            browser.close()


def _load(page, tmp_path, fig, **kw):
    path = tmp_path / "s.html"
    path.write_text(fig.to_html(interactive=True, **kw), encoding="utf-8")
    page.goto(path.as_uri())
    return page


def _slice_labels(page):
    return page.evaluate(
        "Array.from(document.querySelectorAll('.plotpress-menu-dropdown label'))"
        ".map(l => l.textContent.trim())")


def _axes_rects(page):
    """Each axes' rect in screen pixels, from its original clipPath."""
    return page.evaluate("""() => {
      const svg = document.getElementById('plotpress-svg'), c = svg.getScreenCTM();
      return Array.from(svg.querySelectorAll('clipPath')).filter(
          cp => /^clip\\d+$/.test(cp.id)).map(cp => {
        const r = cp.firstChild, x = +r.getAttribute('x'), y = +r.getAttribute('y');
        const w = +r.getAttribute('width'), h = +r.getAttribute('height');
        return [x * c.a + c.e, y * c.d + c.f, (x + w) * c.a + c.e, (y + h) * c.d + c.f];
      });
    }""")


@pytest.mark.browser
def test_panel_option_alone_offers_the_panel_not_the_replace_view(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options=["slice-companion-panel"])
    labels = _slice_labels(page)
    assert "Show companion panel" in labels
    assert "Show slice view" not in labels


@pytest.mark.browser
def test_slice_option_alone_offers_the_replace_view_not_the_panel(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options=["slice"])
    labels = _slice_labels(page)
    assert "Show slice view" in labels
    assert "Show companion panel" not in labels


@pytest.mark.browser
def test_both_options_are_mutually_exclusive_views(page, tmp_path):
    _load(page, tmp_path, _grid_fig(),
          options={"slice": {"enabled": True}, "slice-companion-panel": {}})
    # Panel is the default view; asking for the replace view swaps to it.
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-companion').length") == 6
    page.evaluate("""() => { Array.from(document.querySelectorAll('label')).find(
        l => l.textContent.includes('Show slice view')).querySelector('input').click(); }""")
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-companion').length") == 0
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-line').length") == 6
    panel_cb = page.evaluate("""() => Array.from(document.querySelectorAll('label')).find(
        l => l.textContent.includes('Show companion panel')).querySelector('input').checked""")
    assert panel_cb is False


@pytest.mark.browser
def test_startup_settings_are_applied(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options={"slice-companion-panel": {
        "enabled": True, "orientation": "y", "link_all": True, "index": 5}})
    state = page.evaluate("""() => ({
      panels: document.querySelectorAll('.plotpress-slice-companion').length,
      bars: document.querySelectorAll('.plotpress-sliders .plotpress-slider').length,
      label: (document.querySelector('.plotpress-sliders .val') || {}).textContent,
      value: (document.querySelector('.plotpress-sliders input[type=range]') || {}).value,
    })""")
    assert state["panels"] == 6          # enabled at load, no click needed
    assert state["bars"] == 1            # link_all: one global slider for all six
    assert state["label"].startswith("x (6 axes)")   # orientation "y" slices columns
    assert state["value"] == "5"         # index


@pytest.mark.browser
def test_slice_stays_off_until_asked(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options=["slice-companion-panel"])
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-companion').length") == 0
    assert page.evaluate("document.querySelectorAll('.plotpress-slider').length") == 0


def _clip_height(page):
    return page.evaluate("+document.querySelector('#clip0 rect').getAttribute('height')")


@pytest.mark.browser
def test_panel_splits_the_axes_rect_and_disabling_restores_it(page, tmp_path):
    fig = _grid_fig((1, 1))
    _load(page, tmp_path, fig)
    original = _clip_height(page)

    _load(page, tmp_path, fig, options={"slice-companion-panel": {"enabled": True}})
    assert page.evaluate(
        "document.querySelector('.plotpress-slice-companion').childNodes.length") > 0
    # The heatmap gave up ~30% of the rect to the strip.
    assert _clip_height(page) == pytest.approx(original * 0.7, rel=0.05)

    page.evaluate("""() => { Array.from(document.querySelectorAll('label')).find(
        l => l.textContent.includes('Enable Slice')).querySelector('input').click(); }""")
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-companion').length") == 0
    assert _clip_height(page) == pytest.approx(original)


@pytest.mark.browser
def test_panel_size_setting_changes_the_split(page, tmp_path):
    fig = _grid_fig((1, 1))
    _load(page, tmp_path, fig)
    original = _clip_height(page)
    _load(page, tmp_path, fig,
          options={"slice-companion-panel": {"enabled": True, "panel_size": 0.5}})
    assert _clip_height(page) == pytest.approx(original * 0.5, rel=0.05)


def _line_pixels_outside_axes(page, rects):
    from PIL import Image

    img = np.array(Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")).astype(int)
    mask = np.abs(img - np.array([31, 119, 180])).sum(axis=2) < 12   # the profile's #1f77b4
    inside = np.zeros(mask.shape, bool)
    for x0, y0, x1, y1 in rects:
        inside[int(y0) - 2:int(y1) + 3, int(x0) - 2:int(x1) + 3] = True
    return int((mask & ~inside).sum()), int((mask & inside).sum())


@pytest.mark.browser
@pytest.mark.parametrize("options", [
    # A value range far narrower than the data, so the line has to leave the
    # plot box unless it is clipped -- in each view and orientation.
    {"slice-companion-panel": {"enabled": True, "range": "custom",
                               "range_min": -0.05, "range_max": 0.05}},
    {"slice-companion-panel": {"enabled": True, "orientation": "y", "range": "custom",
                               "range_min": -0.05, "range_max": 0.05}},
    {"slice": {"enabled": True, "show_view": True, "range": "custom",
               "range_min": -0.05, "range_max": 0.05}},
    {"slice": {"enabled": True, "show_view": True, "orientation": "y", "range": "custom",
               "range_min": -0.05, "range_max": 0.05}},
])
def test_profile_never_leaves_the_axes(page, tmp_path, options):
    fig = _grid_fig()
    rects = _axes_rects(_load(page, tmp_path, fig))
    _load(page, tmp_path, fig, options=options)
    outside, inside = _line_pixels_outside_axes(page, rects)
    assert inside > 0, "the profile drew nothing, so this test proved nothing"
    assert outside == 0


# ---- Point Picking on the companion strip -----------------------------------

def _pick_fig():
    fig, ax = plotpress.subplots(figsize=(7, 5))
    x, y = np.linspace(0, 10, 11), np.linspace(0, 8, 9)
    z = np.arange(80, dtype=float).reshape(8, 10)   # z[row, col] = 10*row + col
    ax.pcolormesh(x, y, z)
    fig.tight_layout()
    return fig, z


def _enter_pick_mode(page):
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menubar button'))
        .find(b => b.textContent === 'Point Picking').click()""")


def _click_strip(page, frac=0.5):
    """Click ``frac`` of the way across the profile line, at its height."""
    box = page.evaluate("""() => { const r = document.querySelector(
        '.plotpress-slice-companion path').getBoundingClientRect();
        return [r.left, r.top, r.width, r.height]; }""")
    page.mouse.click(box[0] + box[2] * frac, box[1] + box[3] / 2)


def _pin_labels(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll(
        '.plotpress-pin[data-kind="slice"]')).map(p => p.textContent.trim())""")


def _parse(label):
    return {k: float(v) for k, v in re.findall(r"(\w+)=(-?[\d.e+-]+)", label)}


@pytest.mark.browser
def test_clicking_the_strip_picks_the_profile_sample_under_it(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice-companion-panel": {"enabled": True, "index": 3}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    (label,) = _pin_labels(page)
    got = _parse(label)
    col = int(got["x"] - 0.5)                 # cell midpoints are col + 0.5
    assert got["y"] == pytest.approx(3.5)     # the cursor row's own midpoint (index 3)
    assert got["z"] == z[3, col]              # the same value the heatmap holds there


@pytest.mark.browser
def test_a_strip_pin_follows_the_slider(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice-companion-panel": {"enabled": True, "index": 1}})
    _enter_pick_mode(page)
    _click_strip(page, 0.3)
    before = _parse(_pin_labels(page)[0])
    page.evaluate("""() => { const r = document.querySelector('input[type=range]');
        r.value = 6; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
    after = _parse(_pin_labels(page)[0])
    col = int(before["x"] - 0.5)
    assert after["x"] == before["x"]                 # same sample along the axis...
    assert after["y"] == pytest.approx(6.5)          # ...on the row the slider moved to
    assert after["z"] == z[6, col]                   # ...reporting that row's value


@pytest.mark.browser
def test_arrow_keys_step_a_strip_pin_along_the_profile(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice-companion-panel": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    x0 = _parse(_pin_labels(page)[0])["x"]
    page.keyboard.press("ArrowRight")
    assert _parse(_pin_labels(page)[0])["x"] == pytest.approx(x0 + 1)
    page.keyboard.press("ArrowUp")               # not along an X profile: no-op
    assert _parse(_pin_labels(page)[0])["x"] == pytest.approx(x0 + 1)


@pytest.mark.browser
def test_strip_pins_extract_as_slice_records(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice-companion-panel": {"enabled": True, "index": 2}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    (rec,) = page.evaluate("window.plotpressGetMarkers()")
    assert rec["kind"] == "slice"
    assert rec["z"] == z[2, int(rec["x"])]


@pytest.mark.browser
def test_strip_pins_go_when_the_panel_does(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice-companion-panel": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert len(_pin_labels(page)) == 1
    page.evaluate("""() => Array.from(document.querySelectorAll('label')).find(
        l => l.textContent.includes('Show companion panel')).querySelector('input').click()""")
    assert _pin_labels(page) == []
