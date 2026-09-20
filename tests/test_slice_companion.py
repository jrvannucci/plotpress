"""The Slice tool's three views -- a strip beside the heatmap (the default),
the profile replacing the heatmap, or just a cursor -- switched by a radio in
its menu, and the startup settings ``options={"slice": {...}}`` accepts.

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
        "slice": {"enabled": True, "orientation": "y", "view": "replace",
                  "link_all": True, "index": 4, "panel_size": 0.4},
    })
    assert _config(html)["slice"] == {
        "enabled": True, "orientation": "y", "view": "replace",
        "link_all": True, "index": 4, "panel_size": 0.4}


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
    ({"view": "sideways"}, "one of 'cursor'"),
    ({"nope": 1}, "unknown setting"),
])
def test_bad_panel_settings_are_rejected(settings, message):
    with pytest.raises(ValueError, match=message):
        _grid_fig().to_html(options={"slice": settings})


def test_old_view_options_no_longer_exist():
    # The companion panel is a view of "slice" now, not an option of its own.
    with pytest.raises(ValueError, match="unknown interactive option"):
        _grid_fig().to_html(options=["slice-companion-panel"])
    with pytest.raises(ValueError, match="unknown setting"):
        _grid_fig().to_html(options={"slice": {"show_view": True}})


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


def _view_radios(page):
    """{label: checked} for the three view radios."""
    return page.evaluate("""() => Object.fromEntries(Array.from(document.querySelectorAll(
        'input[name="plotpress-slice-view"]')).map(r => [r.parentNode.textContent.trim(), r.checked]))""")


def _pick_view(page, label):
    page.evaluate("""(label) => Array.from(document.querySelectorAll(
        'input[name="plotpress-slice-view"]')).find(
        r => r.parentNode.textContent.includes(label)).click()""", label)


@pytest.mark.browser
def test_slice_offers_all_three_views_with_the_companion_panel_by_default(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options=["slice"])
    assert _view_radios(page) == {
        "Heatmap with cursor": False, "Companion panel": True,
        "Profile replaces heatmap": False}


@pytest.mark.browser
def test_the_radio_switches_between_the_views(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options={"slice": {"enabled": True}})

    def counts():
        return page.evaluate("""() => [
          document.querySelectorAll('.plotpress-slice-companion').length,
          document.querySelectorAll('.plotpress-slice-line').length,
          document.querySelectorAll('.plotpress-slice-cursor').length]""")

    assert counts() == [6, 0, 6]          # strip + cursor on the heatmap
    _pick_view(page, "replace")
    assert counts() == [0, 6, 0]          # profile in the heatmap's place, no cursor
    _pick_view(page, "cursor")
    assert counts() == [0, 0, 6]          # heatmap and cursor only
    _pick_view(page, "Companion")
    assert counts() == [6, 0, 6]          # and back


@pytest.mark.browser
def test_view_setting_picks_the_starting_radio(page, tmp_path):
    for view, label in [("cursor", "Heatmap with cursor"),
                        ("replace", "Profile replaces heatmap")]:
        _load(page, tmp_path, _grid_fig(), options={"slice": {"view": view}})
        assert [k for k, v in _view_radios(page).items() if v] == [label]


@pytest.mark.browser
def test_startup_settings_are_applied(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options={"slice": {
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
    _load(page, tmp_path, _grid_fig(), options=["slice"])
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-companion').length") == 0
    assert page.evaluate("document.querySelectorAll('.plotpress-slider').length") == 0


def _clip_height(page):
    return page.evaluate("+document.querySelector('#clip0 rect').getAttribute('height')")


@pytest.mark.browser
def test_panel_splits_the_axes_rect_and_disabling_restores_it(page, tmp_path):
    fig = _grid_fig((1, 1))
    _load(page, tmp_path, fig)
    original = _clip_height(page)

    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
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
          options={"slice": {"enabled": True, "panel_size": 0.5}})
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
    {"slice": {"enabled": True, "range": "custom",
                               "range_min": -0.05, "range_max": 0.05}},
    {"slice": {"enabled": True, "orientation": "y", "range": "custom",
                               "range_min": -0.05, "range_max": 0.05}},
    {"slice": {"enabled": True, "view": "replace", "range": "custom",
               "range_min": -0.05, "range_max": 0.05}},
    {"slice": {"enabled": True, "view": "replace", "orientation": "y", "range": "custom",
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
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    (label,) = _pin_labels(page)
    got = _parse(label)
    col = int(got["x"] - 0.5)                 # cell midpoints are col + 0.5
    assert "y" not in got                     # the slice's own coordinate lives in the corner
    assert got["z"] == z[3, col]              # the same value the heatmap holds there


@pytest.mark.browser
def test_a_strip_pin_follows_the_slider(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 1}})
    _enter_pick_mode(page)
    _click_strip(page, 0.3)
    before = _parse(_pin_labels(page)[0])
    page.evaluate("""() => { const r = document.querySelector('input[type=range]');
        r.value = 6; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
    after = _parse(_pin_labels(page)[0])
    col = int(before["x"] - 0.5)
    assert after["x"] == before["x"]                 # same sample along the axis...
    assert after["z"] == z[6, col]                   # ...reporting the row the slider moved to


@pytest.mark.browser
def test_arrow_keys_step_a_strip_pin_along_the_profile(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
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
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 2}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    (rec,) = page.evaluate("window.plotpressGetMarkers()")
    assert rec["kind"] == "slice"
    assert rec["z"] == z[2, int(rec["x"])]


@pytest.mark.browser
def test_strip_pins_go_when_the_panel_does(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert len(_pin_labels(page)) == 1
    _pick_view(page, "cursor")
    assert _pin_labels(page) == []


# ---- Snap pins to slice (mirrors of heatmap pins on the profile) -----------------

def _set_snap(page, on=True):
    page.evaluate("""(on) => { const cb = Array.from(document.querySelectorAll('label')).find(
        l => l.textContent.includes('Snap pins to slice')).querySelector('input');
        if (cb.checked !== on) cb.click(); }""", on)


def _click_heatmap(page, fx, fy):
    box = page.evaluate("""() => { const r = document.querySelector('.plotpress-mesh')
        .getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }""")
    page.mouse.click(box[0] + box[2] * fx, box[1] + box[3] * fy)


def _pins(page):
    """[(kind, snapped, label)] for every pin, in document order."""
    return page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-pin')).map(
        p => [p.dataset.kind, !!p.dataset.snapped, p.textContent.trim()])""")


@pytest.mark.browser
def test_snap_mirrors_a_heatmap_pin_onto_the_shown_slice_and_keeps_it(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 1}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.55, 0.3)          # a cell well away from the cursor row
    assert [(k, s) for k, s, _ in _pins(page)] == [("mesh", False)]
    original = _pins(page)[0][2]

    _set_snap(page, True)

    (kind0, snap0, label0), (kind1, snap1, label1) = _pins(page)
    assert (kind0, snap0, label0) == ("mesh", False, original)   # the heatmap pin stays, unchanged
    assert (kind1, snap1) == ("slice", True)
    before, mirror = _parse(original), _parse(label1)
    assert mirror["x"] == before["x"]                    # same place along the profile
    assert mirror["z"] == z[1, int(mirror["x"])]         # reading that row's value
    pin_top, mesh_top = page.evaluate("""() => [
        document.querySelector('.plotpress-pin[data-snapped]').getBoundingClientRect().top,
        document.querySelector('.plotpress-mesh').getBoundingClientRect().top]""")
    assert pin_top < mesh_top                            # up in the strip
    # The dots are drawn like any other pin's; the pair is marked by both
    # labels sharing a (non-default) color.
    def style(sel):
        return page.evaluate("""(sel) => { const p = document.querySelector(sel);
            const c = p.querySelector('circle');
            return [c.getAttribute('fill'), c.getAttribute('stroke'),
                    p.querySelector('rect').getAttribute('fill')]; }""", sel)
    src, mir = style(".plotpress-pin:not([data-snapped])"), style(".plotpress-pin[data-snapped]")
    assert src[:2] == mir[:2] == ["#111", "#fff"]
    assert src[2] == mir[2] != "#111"


@pytest.mark.browser
def test_turning_snap_off_removes_only_the_mirrors(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    _set_snap(page, True)
    assert len(_pins(page)) == 2
    _set_snap(page, False)
    assert [(k, s) for k, s, _ in _pins(page)] == [("mesh", False)]


@pytest.mark.browser
def test_pins_placed_while_snap_is_on_are_mirrored_immediately(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.3, 0.5)
    _click_heatmap(page, 0.8, 0.7)
    assert sorted((k, s) for k, s, _ in _pins(page)) == [
        ("mesh", False), ("mesh", False), ("slice", True), ("slice", True)]


@pytest.mark.browser
def test_a_mirror_follows_the_slider(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    x = _parse(_pins(page)[1][2])["x"]
    page.evaluate("""() => { const r = document.querySelector('input[type=range]');
        r.value = 5; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
    now = _parse(_pins(page)[1][2])
    assert now["z"] == z[5, int(x)]
    # the heatmap pin itself did not move with the slider
    assert _parse(_pins(page)[0][2])["y"] != pytest.approx(5.5)


@pytest.mark.browser
def test_mirrors_use_the_column_for_a_y_slice(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {
        "enabled": True, "orientation": "y", "index": 2, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.7, 0.4)
    before, mirror = (_parse(_pins(page)[i][2]) for i in (0, 1))
    assert mirror["y"] == before["y"]
    assert "x" not in mirror                      # a Y slice's coordinate is in the corner
    assert mirror["z"] == z[int(mirror["y"]), 2]


@pytest.mark.browser
def test_mirrors_are_not_extracted_saved_or_deletable(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    assert len(page.evaluate("window.plotpressGetMarkers()")) == 1      # not two
    # right-clicking the mirror does nothing; right-clicking the pin removes both
    page.evaluate("""() => document.querySelector('.plotpress-pin[data-snapped]')
        .dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))""")
    assert len(_pins(page)) == 2
    page.evaluate("""() => document.querySelector('.plotpress-pin:not([data-snapped])')
        .dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))""")
    assert _pins(page) == []


@pytest.mark.browser
def test_snap_needs_the_companion_view_and_leaves_notes_alone(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    page.evaluate("window.prompt = () => 'my note'")
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menubar button'))
        .find(b => b.textContent === 'Annotate Point').click()""")
    _click_heatmap(page, 0.5, 0.5)
    assert [(k, s) for k, s, _ in _pins(page)] == [("mesh", False)]      # a note: no mirror
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.4)
    assert len(_pins(page)) == 3                                          # note, pin, mirror
    _pick_view(page, "cursor")                                            # strip gone -> mirror gone
    assert [s for _, s, _ in _pins(page)] == [False, False]
    _pick_view(page, "Companion")
    assert [s for _, s, _ in _pins(page)] == [False, False, True]


@pytest.mark.browser
def test_view_options_are_their_own_menu_group(page, tmp_path):
    _load(page, tmp_path, _grid_fig(), options=["slice"])
    groups = page.evaluate("""() => {
      const menu = Array.from(document.querySelectorAll('.plotpress-menu-dropdown')).find(
          d => d.textContent.includes('Enable Slice'));
      const out = [[]];
      for (const el of menu.children) {
        if (el.classList.contains('plotpress-menu-divider')) out.push([]);
        else out[out.length - 1].push(el.textContent.trim());
      }
      return out;
    }""")
    view_group = next(g for g in groups if "Slice view" in g)
    for wanted in ("Heatmap with cursor", "Companion panel",
                   "Profile replaces heatmap", "Snap pins to slice"):
        assert any(wanted in t for t in view_group), wanted
    assert not any("Enable Slice" in t or "Slice X" in t or "Auto (per slice)" in t
                   for t in view_group)


def _label_fills(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-pin')).map(
        p => [!!p.dataset.snapped, p.querySelector('rect').getAttribute('fill')])""")


@pytest.mark.browser
def test_each_linked_pair_gets_its_own_label_color_and_snap_off_restores_it(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.3, 0.5)
    _click_heatmap(page, 0.8, 0.7)
    all_fills = _label_fills(page)
    pins = [f for snapped, f in all_fills if not snapped]
    mirrors = [f for snapped, f in all_fills if snapped]
    assert pins == mirrors                                # each pair shares a color...
    assert pins[0] != pins[1]                             # ...and the pairs differ
    assert "#111" not in pins + mirrors
    _set_snap(page, False)
    assert {f for _, f in _label_fills(page)} == {"#111"}  # back to ordinary labels


@pytest.mark.browser
def test_a_pins_link_color_survives_another_pin_being_deleted(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.3, 0.5)
    _click_heatmap(page, 0.8, 0.7)
    second = [f for snapped, f in _label_fills(page) if not snapped][1]
    page.evaluate("""() => document.querySelector('.plotpress-pin:not([data-snapped])')
        .dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))""")
    assert [f for snapped, f in _label_fills(page) if not snapped] == [second]


# ---- a strip pin whose value leaves the strip / disappears / scrolls away ----------

def _ramp_fig(nan_at=None):
    """z[row, col] = 10*row + col, so each slider step moves the whole profile up."""
    fig, ax = plotpress.subplots(figsize=(7, 5))
    z = np.arange(80, dtype=float).reshape(8, 10)
    if nan_at is not None:
        z[nan_at] = np.nan
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9), z)
    fig.tight_layout()
    return fig


def _set_slider(page, row):
    page.evaluate("""(row) => { const r = document.querySelector('input[type=range]');
        r.value = row; r.dispatchEvent(new Event('input', {bubbles: true})); }""", row)


def _strip_pin_state(page):
    """{top, bottom, dot_y, display, red} for the one strip pin, in screen pixels."""
    return page.evaluate("""() => {
      const pin = document.querySelector('.plotpress-pin[data-kind="slice"]');
      const svg = document.getElementById('plotpress-svg'), c = svg.getScreenCTM();
      const r = document.querySelector('#sliceclip0 rect');
      const y = +r.getAttribute('y'), h = +r.getAttribute('height');
      const dot = pin.querySelector('circle').getBoundingClientRect();
      const red = pin.querySelector('tspan');
      return {top: y * c.d + c.f, bottom: (y + h) * c.d + c.f,
              dot_y: dot.top + dot.height / 2, display: pin.style.display,
              red: red ? red.getAttribute('fill') : null,
              label: pin.textContent.trim()};
    }""")


_RANGE = {"enabled": True, "range": "custom", "range_min": 0, "range_max": 20}


@pytest.mark.browser
def test_a_pin_whose_value_leaves_the_range_clamps_to_the_strip_with_a_red_value(page, tmp_path):
    _load(page, tmp_path, _ramp_fig(), options={"slice": dict(_RANGE)})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    inside = _strip_pin_state(page)
    assert inside["top"] <= inside["dot_y"] <= inside["bottom"]
    assert inside["red"] is None                       # in range: an ordinary label

    _set_slider(page, 7)                               # row 7 is 70+, far past range_max=20
    over = _strip_pin_state(page)
    assert over["top"] - 1 <= over["dot_y"] <= over["bottom"] + 1   # stays on the strip
    assert over["dot_y"] < inside["dot_y"]             # pinned at the top edge
    assert over["red"] == "#dc1f1f"                    # the value is red
    assert _parse(over["label"])["z"] >= 70            # and still the true value

    _set_slider(page, 0)                               # back in range
    assert _strip_pin_state(page)["red"] is None


@pytest.mark.browser
def test_a_pin_is_hidden_while_its_sample_has_no_value(page, tmp_path):
    fig = _ramp_fig(nan_at=(3, 5))
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.55)                           # a sample in column 5
    assert _parse(_pin_labels(page)[0])["x"] == pytest.approx(5.5)
    assert _strip_pin_state(page)["display"] == ""
    _set_slider(page, 3)                               # z[3, 5] is NaN
    assert _strip_pin_state(page)["display"] == "none"
    _set_slider(page, 4)
    assert _strip_pin_state(page)["display"] == ""


@pytest.mark.browser
def test_a_pin_is_hidden_once_zoomed_out_of_the_strips_view(page, tmp_path):
    _load(page, tmp_path, _ramp_fig(), options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.1)                            # a sample near the left edge
    assert _strip_pin_state(page)["display"] == ""
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menubar button'))
        .find(b => b.textContent === 'Axis Zoom').click()""")
    box = page.evaluate("""() => { const r = document.querySelector('.plotpress-mesh')
        .getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }""")
    page.mouse.move(box[0] + box[2] * 0.6, box[1] + box[3] * 0.3)   # zoom into the right side
    page.mouse.down()
    page.mouse.move(box[0] + box[2] * 0.95, box[1] + box[3] * 0.7, steps=4)
    page.mouse.up()
    assert _strip_pin_state(page)["display"] == "none"


@pytest.mark.browser
def test_strip_pin_labels_leave_out_the_slices_own_coordinate(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    (label,) = _pin_labels(page)
    assert re.fullmatch(r"x=[\d.]+, z=[\d.]+", label)      # no "y=..." (it's in the corner)
    # ...while Extract still returns the full record.
    (rec,) = page.evaluate("window.plotpressGetMarkers()")
    assert {"x", "y", "z"} <= set(rec)


@pytest.mark.browser
def test_a_pin_dropped_off_scale_is_red_immediately(page, tmp_path):
    # Not only after the next slider step: the very first layout must paint it.
    _load(page, tmp_path, _ramp_fig(), options={"slice": {**_RANGE, "index": 7}})
    _enter_pick_mode(page)
    # The whole profile is off the scale here, so aim at the strip itself
    # rather than at the (clipped-away) line.
    x, y = page.evaluate("""() => { const c = document.getElementById('plotpress-svg').getScreenCTM();
        const r = document.querySelector('#sliceclip0 rect');
        return [(+r.getAttribute('x') + +r.getAttribute('width') / 2) * c.a + c.e,
                (+r.getAttribute('y') + +r.getAttribute('height') / 2) * c.d + c.f]; }""")
    page.mouse.click(x, y)
    assert _strip_pin_state(page)["red"] == "#dc1f1f"


@pytest.mark.browser
def test_a_mirror_of_an_off_scale_pin_is_red_immediately(page, tmp_path):
    _load(page, tmp_path, _ramp_fig(), options={"slice": {**_RANGE, "index": 7, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.5, 0.5)
    assert _strip_pin_state(page)["red"] == "#dc1f1f"


# ---- Snap is two-way: a pin placed on the profile is mirrored on the heatmap ------

@pytest.mark.browser
def test_a_pin_placed_on_the_slice_is_mirrored_onto_the_heatmap(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    pins = _pins(page)
    assert sorted((k, s) for k, s, _ in pins) == [("mesh", True), ("slice", False)]
    strip = _parse(next(l for k, s, l in pins if k == "slice"))
    heat = _parse(next(l for k, s, l in pins if k == "mesh"))
    assert heat["x"] == strip["x"]                       # same column
    assert heat["y"] == pytest.approx(3.5)               # on the row the slice shows
    assert heat["z"] == strip["z"] == z[3, int(heat["x"])]
    # the pair is marked by a shared label color
    fills = page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-pin'))
        .map(p => p.querySelector('rect').getAttribute('fill'))""")
    assert fills[0] == fills[1] != "#111"


@pytest.mark.browser
def test_the_heatmap_mirror_follows_the_slider_to_the_new_row(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    col = int(_parse(next(l for k, s, l in _pins(page) if k == "slice"))["x"])
    _set_slider(page, 5)
    heat = _parse(next(l for k, s, l in _pins(page) if k == "mesh"))
    assert heat["y"] == pytest.approx(5.5) and heat["z"] == z[5, col]
    assert len(_pins(page)) == 2                          # no pile-up of mirrors while stepping


@pytest.mark.browser
def test_reverse_snap_uses_the_column_for_a_y_slice(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {
        "enabled": True, "orientation": "y", "index": 2, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    strip = _parse(next(l for k, s, l in _pins(page) if k == "slice"))
    heat = _parse(next(l for k, s, l in _pins(page) if k == "mesh"))
    assert heat["x"] == pytest.approx(2.5)               # the column the slice shows
    assert heat["y"] == strip["y"]
    assert heat["z"] == z[int(heat["y"]), 2]


@pytest.mark.browser
def test_reverse_mirror_is_removed_with_snap_or_its_pin_and_never_extracted(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert len(page.evaluate("window.plotpressGetMarkers()")) == 1   # the pin you placed
    _set_snap(page, False)
    assert [(k, s) for k, s, _ in _pins(page)] == [("slice", False)]
    _set_snap(page, True)
    assert len(_pins(page)) == 2
    page.evaluate("""() => document.querySelector('.plotpress-pin[data-kind="slice"]:not([data-snapped])')
        .dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))""")
    assert _pins(page) == []                              # deleting the pin takes its mirror too


# ---- colorbars shrink with their heatmap ---------------------------------------------

def _cbar_fig():
    fig, ax = plotpress.subplots(figsize=(7, 5))
    m = ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9),
                      np.arange(80, dtype=float).reshape(8, 10))
    fig.colorbar(m, ax=ax)
    fig.tight_layout()
    return fig


def _cbar_geometry(page):
    return page.evaluate("""() => {
      const g = document.querySelector('g.plotpress-colorbar');
      const img = g.querySelector('image').getBoundingClientRect();
      const mesh = document.querySelector('.plotpress-mesh').getBoundingClientRect();
      const label = g.querySelector('text').getBoundingClientRect();
      return {img_top: img.top, img_bottom: img.bottom, mesh_top: mesh.top,
              mesh_bottom: mesh.bottom, label_h: label.height};
    }""")


@pytest.mark.browser
def test_the_colorbar_shrinks_to_the_heatmap_under_a_companion_strip(page, tmp_path):
    fig = _cbar_fig()
    _load(page, tmp_path, fig)
    plain = _cbar_geometry(page)
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    with_strip = _cbar_geometry(page)
    # Top and bottom now line up with the (smaller) heatmap, not the full axes.
    assert with_strip["img_top"] == pytest.approx(with_strip["mesh_top"], abs=1.5)
    assert with_strip["img_bottom"] == pytest.approx(with_strip["mesh_bottom"], abs=1.5)
    assert with_strip["img_top"] > plain["img_top"] + 20
    # ...without squashing the tick labels.
    assert with_strip["label_h"] == pytest.approx(plain["label_h"], rel=0.05)


@pytest.mark.browser
def test_the_colorbar_grows_back_when_the_strip_goes_away(page, tmp_path):
    fig = _cbar_fig()
    _load(page, tmp_path, fig)
    plain = _cbar_geometry(page)
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _pick_view(page, "cursor")
    back = _cbar_geometry(page)
    assert back["img_top"] == pytest.approx(plain["img_top"], abs=1.0)
    assert back["img_bottom"] == pytest.approx(plain["img_bottom"], abs=1.0)


@pytest.mark.browser
def test_a_y_slice_leaves_the_colorbar_alone(page, tmp_path):
    fig = _cbar_fig()
    _load(page, tmp_path, fig)
    plain = _cbar_geometry(page)
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "orientation": "y"}})
    y_strip = _cbar_geometry(page)
    assert y_strip["img_top"] == pytest.approx(plain["img_top"], abs=1.0)   # strip is on the left
    assert y_strip["img_bottom"] == pytest.approx(plain["img_bottom"], abs=1.0)


# ---- a dragged label box stays where the user put it -----------------------------------

def _drag_label(page, selector, dx, dy):
    """Drag a pin's label box by (dx, dy) screen pixels; return its box offset dataset."""
    box = page.evaluate("""(sel) => { const r = document.querySelector(sel + ' rect')
        .getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }""", selector)
    page.mouse.move(box[0], box[1])
    page.mouse.down()
    page.mouse.move(box[0] + dx, box[1] + dy, steps=4)
    page.mouse.up()
    return page.evaluate("""(sel) => { const p = document.querySelector(sel);
        return [p.dataset.boxDx, p.dataset.boxDy]; }""", selector)


@pytest.mark.browser
def test_a_dragged_mirror_label_survives_slider_steps(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    moved = _drag_label(page, ".plotpress-pin[data-snapped]", 40, 25)
    assert moved[0] is not None                          # the drag registered
    element_before = page.evaluate("""() => { window.__m = document.querySelector(
        '.plotpress-pin[data-snapped]'); return true; }""")
    for row in (2, 4, 6, 1):
        _set_slider(page, row)
    after = page.evaluate("""() => { const p = document.querySelector('.plotpress-pin[data-snapped]');
        return [p === window.__m, p.dataset.boxDx, p.dataset.boxDy]; }""")
    assert after == [True, moved[0], moved[1]]           # same element, same dragged offset
    assert len(_pins(page)) == 2


@pytest.mark.browser
def test_a_dragged_heatmap_mirror_label_survives_slider_steps(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    moved = _drag_label(page, ".plotpress-pin[data-kind='mesh'][data-snapped]", -30, 20)
    assert moved[0] is not None
    _set_slider(page, 6)
    after = page.evaluate("""() => { const p = document.querySelector(
        '.plotpress-pin[data-kind="mesh"][data-snapped]'); return [p.dataset.boxDx, p.dataset.boxDy]; }""")
    assert after == moved


@pytest.mark.browser
def test_a_dragged_strip_pin_label_survives_slider_steps(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    moved = _drag_label(page, ".plotpress-pin[data-kind='slice']", 30, 30)
    assert moved[0] is not None
    _set_slider(page, 5)
    after = page.evaluate("""() => { const p = document.querySelector('.plotpress-pin[data-kind="slice"]');
        return [p.dataset.boxDx, p.dataset.boxDy]; }""")
    assert after == moved


# ---- audit regressions ---------------------------------------------------------------

@pytest.mark.browser
def test_disabling_slice_removes_the_heatmap_side_mirrors_too(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)       # heatmap pin  -> mirror on the strip
    _click_strip(page, 0.7)              # strip pin    -> mirror on the heatmap
    assert len(_pins(page)) == 4
    page.evaluate("""() => Array.from(document.querySelectorAll('label')).find(
        l => l.textContent.includes('Enable Slice')).querySelector('input').click()""")
    # Only the pin the user placed on the heatmap survives -- no orphaned (and, being
    # non-deletable, permanent) mirror pins.
    assert [(k, s) for k, s, _ in _pins(page)] == [("mesh", False)]


def _twin_fig():
    fig, ax = plotpress.subplots(figsize=(7, 5))
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9), np.arange(80, dtype=float).reshape(8, 10))
    ax.twinx().plot([0, 10], [0, 1], color="k")
    fig.tight_layout()
    return fig


@pytest.mark.browser
def test_a_strip_pin_follows_an_animated_meshs_frame_slider(page, tmp_path):
    fig, ax = plotpress.subplots(figsize=(7, 5))
    x, y = np.linspace(0, 10, 11), np.linspace(0, 8, 9)
    ax.pcolormesh_frames(x, y, [np.full((8, 10), float(f)) for f in range(4)])
    fig.tight_layout()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    box = page.evaluate("""() => { const c = document.getElementById('plotpress-svg').getScreenCTM();
        const r = document.querySelector('#sliceclip0 rect');
        return [(+r.getAttribute('x') + +r.getAttribute('width') / 2) * c.a + c.e,
                (+r.getAttribute('y') + +r.getAttribute('height') / 2) * c.d + c.f]; }""")
    page.mouse.click(*box)
    before = _parse(_pin_labels(page)[0])["z"]
    page.evaluate("""() => { const s = Array.from(document.querySelectorAll('.plotpress-slider')).find(
        s => s.textContent.includes('frame')); const r = s.querySelector('input[type=range]');
        r.value = 3; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
    assert _parse(_pin_labels(page)[0])["z"] == 3.0 and before != 3.0


# ---- choosing which axes to slice ----------------------------------------------------

def _row_fig(n=3):
    fig, axs = plotpress.subplots(1, n, figsize=(4 * n, 4))
    x, y = np.linspace(0, 10, 11), np.linspace(0, 8, 9)
    for i, ax in enumerate(axs):
        ax.pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10) + i)
    fig.tight_layout()
    return fig, list(axs)


def _strips(page):
    return page.evaluate("document.querySelectorAll('.plotpress-slice-companion').length")


def _scope_radio(page, label):
    page.evaluate("""(label) => Array.from(document.querySelectorAll(
        'input[name="plotpress-slice-scope"]')).find(
        r => r.parentNode.textContent.includes(label)).click()""", label)


def test_axes_setting_accepts_axes_objects_and_indices():
    fig, axs = _row_fig()
    cfg = _config(fig.to_html(options={"slice": {"axes": [axs[0], 2]}}))
    assert cfg["slice"]["axes"] == [0, 2]
    assert "axes" not in _config(fig.to_html(options={"slice": {"axes": "all"}}))["slice"]


@pytest.mark.parametrize("bad, message", [
    ("some", 'must be "all"'),
    ([9], "has index 9"),
    ([-1], 'must be "all"'),
    ([1.5], 'must be "all"'),
])
def test_bad_axes_settings_are_rejected(bad, message):
    fig, _ = _row_fig()
    with pytest.raises(ValueError, match=message):
        fig.to_html(options={"slice": {"axes": bad}})


def test_an_axes_from_another_figure_is_rejected():
    fig, _ = _row_fig()
    _, other = _row_fig()
    with pytest.raises(ValueError, match="isn't part of this figure"):
        fig.to_html(options={"slice": {"axes": [other[0]]}})


@pytest.mark.browser
def test_default_scope_is_all_axes(page, tmp_path):
    fig, _ = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    radios = page.evaluate("""() => Object.fromEntries(Array.from(document.querySelectorAll(
        'input[name="plotpress-slice-scope"]')).map(r => [r.parentNode.textContent.trim(), r.checked]))""")
    assert radios == {"All axes": True, "Selected axes": False}
    assert _strips(page) == 3


@pytest.mark.browser
def test_axes_setting_slices_only_the_chosen_axes(page, tmp_path):
    fig, axs = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": [axs[0], axs[2]]}})
    assert _strips(page) == 2
    assert page.evaluate("document.querySelectorAll('.plotpress-slider').length") == 2
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-cursor').length") == 2
    # the unchosen middle axes is a plain heatmap: full-size clip, no strip
    _load(page, tmp_path, fig)
    full = page.evaluate("+document.querySelector('#clip1 rect').getAttribute('height')")
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": [axs[0], axs[2]]}})
    assert page.evaluate("+document.querySelector('#clip1 rect').getAttribute('height')") == pytest.approx(full)
    # no separate marker for the chosen ones: their frame now holds the slice
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-select').length") == 0


@pytest.mark.browser
def test_choosing_axes_by_clicking_them(page, tmp_path):
    fig, axs = _row_fig()
    _load(page, tmp_path, fig)
    rects = _axes_rects(page)
    plain_height = page.evaluate("+document.querySelector('#clip1 rect').getAttribute('height')")
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    assert _strips(page) == 3
    _scope_radio(page, "Selected axes")
    mode_text = page.evaluate("document.querySelector('.plotpress-mode-indicator').textContent")
    assert "Choose slice axes" in mode_text
    assert _strips(page) == 0                              # nothing chosen yet: nothing sliced
    x0, y0, x1, y1 = rects[1]
    page.mouse.click((x0 + x1) / 2, (y0 + y1) / 2)         # choose the middle axes
    assert _strips(page) == 1
    # only the still-choosable axes are outlined (dashed), and only while choosing
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-select rect').length") == 2
    x0, y0, x1, y1 = rects[2]
    page.mouse.click((x0 + x1) / 2, (y0 + y1) / 2)         # and the last
    assert _strips(page) == 2
    x0, y0, x1, y1 = rects[1]
    page.mouse.click((x0 + x1) / 2, (y0 + y1) / 2)         # click the middle again: drop it
    assert _strips(page) == 1
    assert page.evaluate("+document.querySelector('#clip1 rect').getAttribute('height')") == pytest.approx(plain_height)
    _scope_radio(page, "All axes")
    assert _strips(page) == 3
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-select').length") == 0


@pytest.mark.browser
def test_link_all_couples_only_the_chosen_axes(page, tmp_path):
    fig, axs = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {
        "enabled": True, "link_all": True, "axes": [axs[0], axs[1]]}})
    label = page.evaluate("document.querySelector('.plotpress-sliders .val').textContent")
    assert "(2 axes)" in label
    assert page.evaluate("document.querySelectorAll('.plotpress-slider').length") == 1


@pytest.mark.browser
def test_choosing_another_axes_keeps_the_slider_where_it_was(page, tmp_path):
    fig, axs = _row_fig()
    rects = _axes_rects(_load(page, tmp_path, fig))
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 5, "axes": [axs[0]]}})
    # Already in "Selected axes" from the setting, so re-enter choosing with the button.
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menu-dropdown button'))
        .find(b => b.textContent === 'Choose axes on figure').click()""")
    x0, y0, x1, y1 = rects[1]
    page.mouse.click((x0 + x1) / 2, (y0 + y1) / 2)
    assert _strips(page) == 2
    vals = page.evaluate("Array.from(document.querySelectorAll('.plotpress-slider input[type=range]')).map(r => r.value)")
    assert vals == ["5", "5"]


@pytest.mark.browser
def test_chosen_axes_have_no_blue_outline_or_tint(page, tmp_path):
    fig, axs = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": [axs[0]]}})
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-select').length") == 0
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menu-dropdown button'))
        .find(b => b.textContent === 'Choose axes on figure').click()""")
    strokes = page.evaluate("Array.from(document.querySelectorAll('.plotpress-slice-select rect')).map(r => [r.getAttribute('stroke'), r.getAttribute('fill')])")
    assert strokes == [["#9ca3af", "none"], ["#9ca3af", "none"]]     # the two unchosen, faint and dashed


@pytest.mark.browser
def test_choose_mode_uses_a_cursor_that_shows_on_white(page, tmp_path):
    fig, _ = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": []}})
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menu-dropdown button'))
        .find(b => b.textContent === 'Choose axes on figure').click()""")
    cursor = page.evaluate("document.getElementById('plotpress-svg').style.cursor")
    # A two-tone cross (white halo + black stroke), with the plain crosshair only as fallback.
    assert "data:image/svg+xml" in cursor and "crosshair" in cursor


def _mode_text(page):
    return page.evaluate("document.querySelector('.plotpress-mode-indicator').textContent.trim()")


def _menu_button(page, label):
    return page.evaluate("""(label) => { const b = Array.from(document.querySelectorAll(
        '.plotpress-menu-dropdown button')).find(b => b.textContent === label);
        if (!b) return false; b.click(); return true; }""", label)


@pytest.mark.browser
def test_escape_leaves_choose_mode_and_keeps_pins(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    assert len(_pins(page)) == 1
    _scope_radio(page, "Selected axes")                       # now choosing
    assert _mode_text(page).startswith("Choose slice axes")
    page.keyboard.press("Escape")
    assert _mode_text(page) == "No tool active"
    assert len(_pins(page)) == 1                              # not cleared by leaving choose mode


@pytest.mark.browser
def test_choose_mode_label_says_escape_finishes_it(page, tmp_path):
    fig, _ = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": []}})
    _menu_button(page, "Choose axes on figure")
    assert "Esc" in _mode_text(page)                          # the hint is in the label itself
    page.keyboard.press("Escape")
    assert _mode_text(page) == "No tool active"


@pytest.mark.browser
def test_the_status_line_tracks_the_selection(page, tmp_path):
    fig, _ = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": []}})
    status = lambda: page.evaluate("document.querySelector('.plotpress-menu-note').textContent")
    assert status().startswith("None selected")
    _menu_button(page, "Choose axes on figure")
    box = page.evaluate("""() => { const r = document.querySelector('.plotpress-mesh').getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2]; }""")
    page.mouse.click(*box)
    assert status().startswith("1 selected")                  # updates after the first click too


@pytest.mark.browser
def test_choose_axes_button_is_highlighted_while_choosing(page, tmp_path):
    fig, _ = _row_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": []}})
    is_active = lambda: page.evaluate("""() => Array.from(document.querySelectorAll(
        '.plotpress-menu-dropdown button')).find(b => b.textContent === 'Choose axes on figure')
        .classList.contains('active')""")
    assert not is_active()
    _menu_button(page, "Choose axes on figure")
    assert is_active()                                        # same highlight as Point Picking/Annotate
    page.keyboard.press("Escape")
    assert not is_active()


def test_axes_setting_accepts_numpy_integers():
    fig, _ = _row_fig()
    cfg = _config(fig.to_html(options={"slice": {"axes": [np.int64(1), np.int32(2)]}}))
    assert cfg["slice"]["axes"] == [1, 2]        # plain ints in the emitted JSON


# ---- Extract ignores slice pins (the heatmap carries the data) --------------------------

def _extract(page):
    """Run the Extract button and return the records it hands to the host."""
    page.evaluate("""() => { window.__extracted = null;
        window.pywebview = {api: {extract: (recs) => { window.__extracted = recs; }}}; }""")
    assert _menu_button(page, "Extract")
    return page.evaluate("window.__extracted")


@pytest.mark.browser
@pytest.mark.parametrize("snap", [True, False])
def test_extract_of_a_heatmap_pin_is_one_record_with_or_without_snap(page, tmp_path, snap):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3, "snap_pins": snap}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.55, 0.3)
    recs = _extract(page)
    assert [r["kind"] for r in recs] == ["mesh"]            # the mirror on the profile is not a 2nd record


@pytest.mark.browser
def test_extract_reports_the_heatmap_cell_for_a_pin_placed_on_the_slice(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    recs = _extract(page)
    assert [r["kind"] for r in recs] == ["mesh"]            # never "slice"
    r = recs[0]
    assert r["y"] == pytest.approx(3.5)                     # the row the slice was showing
    assert r["z"] == z[3, int(r["x"])]                      # and that cell's value


@pytest.mark.browser
def test_extract_does_not_report_the_same_cell_twice(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)                                 # heatmap cell (row 3, col c) via its mirror
    heat = _parse(next(l for k, s, l in _pins(page) if k == "mesh"))
    # ...now pick that very cell on the heatmap directly
    box = page.evaluate("""() => { const r = document.querySelector('.plotpress-mesh').getBoundingClientRect();
        return [r.left, r.top, r.width, r.height]; }""")
    page.mouse.click(box[0] + box[2] * (heat["x"] / 10), box[1] + box[3] * (1 - heat["y"] / 8))
    recs = _extract(page)
    keys = [(r["axes"], r["kind"], r["index"]) for r in recs]
    assert len(keys) == len(set(keys)) == 1                 # one cell, one record


@pytest.mark.browser
def test_extract_leaves_out_slice_pins_when_snap_is_off(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)                                 # a profile pin with no heatmap mirror
    _click_heatmap(page, 0.4, 0.6)
    assert [r["kind"] for r in _extract(page)] == ["mesh"]  # only the heatmap pin


# ---- Extract tells the user when slice pins were left out ------------------------------

def _notice(page):
    return page.evaluate("""() => { const n = document.querySelector('.plotpress-extract-notice');
        return n ? n.textContent : null; }""")


@pytest.mark.browser
def test_extract_warns_when_slice_pins_were_left_out_because_snap_is_off(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert _extract(page) == []
    msg = _notice(page)
    assert msg and "1 pin placed on the slice was not extracted" in msg
    assert "Snap pins to slice" in msg                       # says how to get them extracted


@pytest.mark.browser
def test_extract_warns_with_the_right_count(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.2)
    _click_strip(page, 0.8)
    _extract(page)
    assert "2 pins placed on the slice were not extracted" in _notice(page)


@pytest.mark.browser
def test_extract_has_no_warning_once_snap_is_on(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert len(_extract(page)) == 1                          # extracted via its heatmap mirror
    assert _notice(page) is None


@pytest.mark.browser
def test_extract_has_no_warning_without_slice_pins(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    assert len(_extract(page)) == 1
    assert _notice(page) is None


@pytest.mark.browser
def test_turning_snap_on_after_the_warning_extracts_the_pins(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert _extract(page) == [] and _notice(page)
    _set_snap(page, True)
    recs = _extract(page)
    assert [r["kind"] for r in recs] == ["mesh"] and _notice(page) is None


# ---- the Extract panel: JSON by default, radios to switch, one Copy button --------------

def _panel(page):
    return page.evaluate("""() => { const p = document.querySelector('.plotpress-extract');
        return {text: p.querySelector('textarea').value,
                formats: Array.from(p.querySelectorAll('input[name="plotpress-extract-format"]'))
                    .map(r => [r.parentNode.textContent, r.checked]),
                buttons: Array.from(p.querySelectorAll('button')).map(b => b.textContent)}; }""")


@pytest.mark.browser
def test_extract_panel_defaults_to_json_with_radios_and_a_plain_copy_button(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig)
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    _menu_button(page, "Extract")
    panel = _panel(page)
    assert panel["formats"] == [["JSON", True], ["CSV", False]]
    assert json.loads(panel["text"])[0]["kind"] == "mesh"          # JSON showing by default
    assert "Copy" in panel["buttons"] and "Copy CSV" not in panel["buttons"]


@pytest.mark.browser
def test_extract_panel_radios_switch_the_text_and_back(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig)
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    _menu_button(page, "Extract")
    click = lambda label: page.evaluate("""(label) => Array.from(document.querySelectorAll(
        'input[name="plotpress-extract-format"]')).find(r => r.parentNode.textContent === label).click()""", label)
    click("CSV")
    assert _panel(page)["text"].splitlines()[0].startswith("axes,")      # a CSV header row
    click("JSON")
    assert json.loads(_panel(page)["text"])[0]["kind"] == "mesh"


@pytest.mark.browser
def test_extract_panel_with_no_markers_is_an_empty_json_list(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig)
    _menu_button(page, "Extract")
    assert json.loads(_panel(page)["text"]) == []


# ---- gap fixes: zoom cursor, arrow keys on mirrors, wait-for-extract notice ----------------

@pytest.mark.browser
def test_axis_zoom_uses_the_two_tone_cursor_too(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig)
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menubar button'))
        .find(b => b.textContent === 'Axis Zoom').click()""")
    cursor = page.evaluate("document.getElementById('plotpress-svg').style.cursor")
    assert "data:image/svg+xml" in cursor and "crosshair" in cursor


@pytest.mark.browser
def test_arrow_keys_on_a_mirror_step_the_pin_it_mirrors(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    source_before = _parse(next(l for k, s, l in _pins(page) if k == "mesh"))
    # select the mirror (on the strip) and press an arrow
    page.evaluate("""() => document.querySelector('.plotpress-pin[data-snapped]')
        .dispatchEvent(new MouseEvent('click', {bubbles: true}))""")
    page.keyboard.press("ArrowRight")
    pins = _pins(page)
    source = _parse(next(l for k, s, l in pins if k == "mesh"))
    mirror = _parse(next(l for k, s, l in pins if k == "slice"))
    assert source["x"] == pytest.approx(source_before["x"] + 1)   # the heatmap pin moved...
    assert mirror["x"] == source["x"]                              # ...and its mirror followed


def _wait_page(page, tmp_path, options):
    fig, _ = _pick_fig()
    path = tmp_path / "w.html"
    path.write_text(fig.to_html(interactive=True, wait_extract=True, options=options), encoding="utf-8")
    page.goto(path.as_uri())
    page.evaluate("""() => { window.__extracted = 'unsent';
        window.pywebview = {api: {extract: (recs) => { window.__extracted = recs; }}}; }""")


@pytest.mark.browser
def test_wait_for_extract_holds_the_send_back_when_slice_pins_are_left_out(page, tmp_path):
    _wait_page(page, tmp_path, {"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    assert _menu_button(page, "Extract")
    assert page.evaluate("window.__extracted") == "unsent"           # the window would have closed
    assert "not extracted" in _notice(page)
    assert "Extract without them" in _panel(page)["buttons"]
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-extract button'))
        .find(b => b.textContent === 'Extract without them').click()""")
    assert page.evaluate("window.__extracted") == []


@pytest.mark.browser
def test_wait_for_extract_sends_immediately_when_nothing_was_left_out(page, tmp_path):
    _wait_page(page, tmp_path, {"slice": {"enabled": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.4, 0.6)
    assert _menu_button(page, "Extract")
    recs = page.evaluate("window.__extracted")
    assert [r["kind"] for r in recs] == ["mesh"]


# ---- axes that used to get only a cursor: axis off, fixed ticks, twin/secondary ---------

def _fixed_tick_fig():
    fig, ax = plotpress.subplots(figsize=(7, 5))
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9), np.arange(80, dtype=float).reshape(8, 10))
    ax.set_xticks([0, 5, 10]); ax.set_yticks([0, 4, 8])
    ax.grid(True)
    fig.tight_layout()
    return fig


def _tick_label_centers(page):
    """[(text, cx, cy)] in screen pixels for the static tick labels of axes 0 (x and y
    labels can share text, e.g. both "0", so this is a list, not a dict)."""
    return [tuple(v) for v in page.evaluate("""() => Array.from(document.querySelectorAll('#ticks0 text')).map(
        t => { const r = t.getBoundingClientRect(); return [t.textContent, r.left + r.width / 2, r.top + r.height / 2]; })""")]


def _mesh_box(page):
    return page.evaluate("""() => { const r = document.querySelector('.plotpress-mesh').getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom}; }""")


@pytest.mark.browser
def test_axis_off_axes_gets_a_strip(page, tmp_path):
    fig, ax = plotpress.subplots(figsize=(7, 5))
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9), np.arange(80, dtype=float).reshape(8, 10))
    ax.axis("off")
    fig.tight_layout()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    assert _strips(page) == 1


@pytest.mark.browser
def test_fixed_y_ticks_follow_the_shrunken_heatmap_under_an_x_strip(page, tmp_path):
    fig = _fixed_tick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    assert _strips(page) == 1                                # fixed ticks no longer block the strip
    mesh, labels = _mesh_box(page), _tick_label_centers(page)
    left_side = {t: cy for t, cx, cy in labels if cx < mesh["left"]}   # the y-axis labels
    assert left_side["8"] == pytest.approx(mesh["top"], abs=6)         # y=8 at the heatmap's top
    assert left_side["0"] == pytest.approx(mesh["bottom"], abs=6)      # y=0 at its bottom
    assert left_side["4"] == pytest.approx((left_side["0"] + left_side["8"]) / 2, abs=4)


@pytest.mark.browser
def test_fixed_x_ticks_follow_the_shrunken_heatmap_under_a_y_strip(page, tmp_path):
    fig = _fixed_tick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "orientation": "y"}})
    mesh, labels = _mesh_box(page), _tick_label_centers(page)
    below = {t: cx for t, cx, cy in labels if cy > mesh["bottom"] + 4}    # the x-axis labels
    assert below["0"] == pytest.approx(mesh["left"], abs=8)               # x=0 at the heatmap's left edge
    assert below["10"] == pytest.approx(mesh["right"], abs=10)            # x=10 at its right edge
    assert below["5"] == pytest.approx((below["0"] + below["10"]) / 2, abs=4)


@pytest.mark.browser
def test_fixed_ticks_go_back_when_the_strip_does(page, tmp_path):
    fig = _fixed_tick_fig()
    _load(page, tmp_path, fig)
    plain = _tick_label_centers(page)
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    _pick_view(page, "cursor")
    back = _tick_label_centers(page)
    assert len(back) == len(plain)
    for (t0, x0, y0), (t1, x1, y1) in zip(plain, back):
        assert t0 == t1 and x1 == pytest.approx(x0, abs=0.6) and y1 == pytest.approx(y0, abs=0.6)


@pytest.mark.browser
def test_a_twin_axes_shares_the_strip_layout(page, tmp_path):
    _load(page, tmp_path, _twin_fig(), options={"slice": {"enabled": True}})
    assert _strips(page) == 1                                # a twin no longer blocks the strip
    h = page.evaluate("Array.from(document.querySelectorAll('clipPath')).filter(c => /^clip\\d+$/.test(c.id)).map(c => +c.firstChild.getAttribute('height'))")
    assert len(h) == 2 and h[0] == pytest.approx(h[1])       # mesh axes and twin shrank together
    _pick_view(page, "cursor")
    h2 = page.evaluate("Array.from(document.querySelectorAll('clipPath')).filter(c => /^clip\\d+$/.test(c.id)).map(c => +c.firstChild.getAttribute('height'))")
    assert h2[0] > h[0] and h2[0] == pytest.approx(h2[1])    # and grew back together


def test_a_twins_tick_side_is_in_the_metadata():
    # The client redraws a twin's ticks on pan/zoom from this; it used to say "left"
    # for a twinx (drawn on the right), so zooming moved the twin's labels across the plot.
    from plotpress.svg import axes_metadata

    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    twx, twy = ax.twinx(), ax.twiny()
    meta = axes_metadata(fig, idx_of={id(a): i for i, a in enumerate(fig.axes)})
    assert meta[0]["yside"] == "left" and meta[0]["xside"] == "bottom"
    assert meta[fig.axes.index(twx)]["yside"] == "right"
    assert meta[fig.axes.index(twy)]["xside"] == "top"


@pytest.mark.browser
def test_a_twins_labels_stay_on_the_right_under_a_strip(page, tmp_path):
    _load(page, tmp_path, _twin_fig(), options={"slice": {"enabled": True}})
    mesh = _mesh_box(page)
    twin_labels = page.evaluate("""() => Array.from(document.querySelectorAll('#ticks1 text')).map(
        t => t.getBoundingClientRect().left)""")
    assert twin_labels and all(x > mesh["right"] for x in twin_labels)   # only its own (right) y-axis


# ---- pins on the "Profile replaces heatmap" view ---------------------------------------

def _click_axes_middle(page, frac_x=0.5, frac_y=0.5):
    b = page.evaluate("""() => { const c = document.getElementById('plotpress-svg').getScreenCTM();
        const r = document.querySelector('#clip0 rect');
        return [(+r.getAttribute('x') + +r.getAttribute('width') * %f) * c.a + c.e,
                (+r.getAttribute('y') + +r.getAttribute('height') * %f) * c.d + c.f]; }""" % (frac_x, frac_y))
    page.mouse.click(*b)


@pytest.mark.browser
def test_clicking_the_replace_view_picks_a_profile_sample_not_a_hidden_cell(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "view": "replace", "index": 3}})
    _enter_pick_mode(page)
    _click_axes_middle(page)
    pins = _pins(page)
    assert [(k, s) for k, s, _ in pins] == [("slice", False)]        # never a "mesh" pin on the hidden heatmap
    got = _parse(pins[0][2])
    assert got["z"] == z[3, int(got["x"])]                            # the profile's own value


@pytest.mark.browser
def test_a_replace_view_pin_follows_the_slider(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "view": "replace", "index": 1}})
    _enter_pick_mode(page)
    _click_axes_middle(page, 0.3)
    col = int(_parse(_pins(page)[0][2])["x"])
    _set_slider(page, 6)
    assert _parse(_pins(page)[0][2])["z"] == z[6, col]


@pytest.mark.browser
def test_pins_carry_across_the_two_profile_views_but_not_to_cursor_only(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 2}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)                                            # a pin on the companion strip
    x = _parse(_pins(page)[0][2])["x"]
    _pick_view(page, "replace")
    assert len(_pins(page)) == 1
    assert _parse(_pins(page)[0][2])["x"] == x                         # same sample, now on the replace profile
    assert page.evaluate("document.querySelector('.plotpress-pin').style.display") == ""
    _pick_view(page, "Companion")
    assert len(_pins(page)) == 1 and _parse(_pins(page)[0][2])["z"] == z[2, int(x)]
    _pick_view(page, "cursor")
    assert _pins(page) == []                                           # no profile left to point at


@pytest.mark.browser
def test_a_replace_view_pin_clamps_and_goes_red_when_off_range(page, tmp_path):
    _load(page, tmp_path, _ramp_fig(), options={"slice": {**_RANGE, "view": "replace", "index": 0}})
    _enter_pick_mode(page)
    _click_axes_middle(page, 0.5, 0.5)
    _set_slider(page, 7)                                              # values 70+, far past range_max=20
    state = page.evaluate("""() => { const pin = document.querySelector('.plotpress-pin[data-kind="slice"]');
        const c = document.getElementById('plotpress-svg').getScreenCTM();
        const r = document.querySelector('#clip0 rect');
        const top = +r.getAttribute('y') * c.d + c.f, bottom = (+r.getAttribute('y') + +r.getAttribute('height')) * c.d + c.f;
        const dot = pin.querySelector('circle').getBoundingClientRect();
        return {inside: dot.top + dot.height / 2 >= top - 1 && dot.top + dot.height / 2 <= bottom + 1,
                red: !!pin.querySelector('tspan')}; }""")
    assert state == {"inside": True, "red": True}


# ---- Save / Save As keeps the Slice state ---------------------------------------------------

def _save_and_reopen(page, tmp_path):
    page.evaluate("window.showSaveFilePicker = undefined")        # take the download path
    with page.expect_download() as info:
        assert _menu_button(page, "Save As")
    saved = tmp_path / "saved.html"
    info.value.save_as(str(saved))
    page.goto(saved.as_uri())


def _slice_state(page):
    return page.evaluate("""() => ({
      enabled: Array.from(document.querySelectorAll('label')).find(l => l.textContent.includes('Enable Slice')).querySelector('input').checked,
      view: (Array.from(document.querySelectorAll('input[name="plotpress-slice-view"]')).find(r => r.checked) || {parentNode: {textContent: ''}}).parentNode.textContent.trim(),
      orient: (Array.from(document.querySelectorAll('input[name="plotpress-slice-orient"]')).find(r => r.checked) || {parentNode: {textContent: ''}}).parentNode.textContent.trim(),
      scope: (Array.from(document.querySelectorAll('input[name="plotpress-slice-scope"]')).find(r => r.checked) || {parentNode: {textContent: ''}}).parentNode.textContent.trim(),
      strips: document.querySelectorAll('.plotpress-slice-companion').length,
      lines: document.querySelectorAll('.plotpress-slice-line').length,
      sliders: document.querySelectorAll('.plotpress-slider').length,
      values: Array.from(document.querySelectorAll('.plotpress-slider input[type=range]')).map(r => r.value),
      snap: Array.from(document.querySelectorAll('label')).find(l => l.textContent.includes('Snap pins')).querySelector('input').checked,
      linkAll: Array.from(document.querySelectorAll('label')).find(l => l.textContent.includes('Link all')).querySelector('input').checked,
    })""")


@pytest.mark.browser
def test_save_as_reopens_with_the_slice_state_it_was_left_in(page, tmp_path):
    fig, axs = _row_fig()
    _load(page, tmp_path, fig, options=["slice"])                        # nothing enabled at load
    page.evaluate("""() => { const L = t => Array.from(document.querySelectorAll('label')).find(l => l.textContent.includes(t)).querySelector('input');
        L('Enable Slice').click(); L('Link all matching axes').click(); L('Snap pins to slice').click(); }""")
    _pick_view(page, "replace")
    page.evaluate("""() => Array.from(document.querySelectorAll('input[name="plotpress-slice-orient"]')).find(
        r => r.parentNode.textContent.includes('Slice Y')).click()""")
    _scope_radio(page, "Selected axes")
    page.evaluate("""() => Array.from(document.querySelectorAll('.plotpress-menu-dropdown button')).find(
        b => b.textContent === 'Choose axes on figure').click()""")
    plain = _axes_rects(page)
    for i in (0, 2):
        x0, y0, x1, y1 = plain[i]
        page.mouse.click((x0 + x1) / 2, (y0 + y1) / 2)
    page.keyboard.press("Escape")
    _set_slider(page, 4)
    before = _slice_state(page)
    assert before["enabled"] and before["scope"] == "Selected axes" and before["values"] == ["4"]

    _save_and_reopen(page, tmp_path)
    after = _slice_state(page)
    assert after == before                                             # everything as it was left


@pytest.mark.browser
def test_save_as_keeps_a_disabled_slice_disabled_and_the_options(page, tmp_path):
    fig, _ = _row_fig()
    _load(page, tmp_path, fig, options=["slice"])
    _save_and_reopen(page, tmp_path)
    state = _slice_state(page)
    assert not state["enabled"] and state["sliders"] == 0
    assert page.evaluate("Array.from(document.querySelectorAll('.plotpress-menubar button')).some(b => b.textContent.startsWith('Slice'))")


@pytest.mark.browser
def test_a_profile_pin_survives_save_as(page, tmp_path):
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "index": 3}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    label = _pins(page)[0][2]
    _save_and_reopen(page, tmp_path)
    pins = _pins(page)
    assert [(k, s) for k, s, _ in pins] == [("slice", False)]
    assert pins[0][2] == label                                          # same sample, same value


# ---- a colorbar shared by several axes ---------------------------------------------------

def _shared_cbar_fig():
    fig, axs = plotpress.subplots(1, 2, figsize=(11, 4.5))
    x, y = np.linspace(0, 10, 11), np.linspace(0, 8, 9)
    m = axs[0].pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10))
    axs[1].pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10) + 5)
    fig.colorbar(m, ax=list(axs))
    fig.tight_layout()
    return fig, list(axs)


def _shared_cbar_geometry(page):
    return page.evaluate("""() => { const g = document.querySelector('g.plotpress-colorbar');
        const i = g.querySelector('image').getBoundingClientRect();
        const tops = Array.from(document.querySelectorAll('.plotpress-mesh')).map(m => m.getBoundingClientRect().top);
        return {parents: g.dataset.parents, top: i.top, bottom: i.bottom, meshTops: tops}; }""")


@pytest.mark.browser
def test_a_shared_colorbar_shrinks_when_all_its_axes_have_strips(page, tmp_path):
    fig, _ = _shared_cbar_fig()
    _load(page, tmp_path, fig)
    plain = _shared_cbar_geometry(page)
    assert plain["parents"] == "0,1"
    _load(page, tmp_path, fig, options={"slice": {"enabled": True}})
    g = _shared_cbar_geometry(page)
    assert g["top"] == pytest.approx(g["meshTops"][0], abs=1.5)      # lines up with both heatmaps' tops
    assert g["top"] > plain["top"] + 20


@pytest.mark.browser
def test_a_shared_colorbar_stays_put_unless_all_its_axes_change_alike(page, tmp_path):
    fig, axs = _shared_cbar_fig()
    _load(page, tmp_path, fig)
    plain = _shared_cbar_geometry(page)
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "axes": [axs[0]]}})   # only one of the two
    g = _shared_cbar_geometry(page)
    assert g["top"] == pytest.approx(plain["top"], abs=1.0) and g["bottom"] == pytest.approx(plain["bottom"], abs=1.0)


# ---- scale: eligibility and pin relayout survive the perf rewrites -------------

def _mesh_fig_with_inset():
    fig, axs = plotpress.subplots(1, 2, figsize=(10, 4))
    x, y = np.linspace(0, 1, 11), np.linspace(0, 1, 9)
    for ax in axs:
        ax.pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10))
    axs[0].inset_axes([0.6, 0.6, 0.3, 0.3]).plot([0, 1], [0, 1])
    fig.tight_layout()
    return fig


@pytest.mark.browser
def test_an_inset_still_blocks_a_strip_but_only_on_its_own_axes(page, tmp_path):
    # Eligibility is computed in one bucketed pass now; the nested-axes rule
    # must still hold, and must not spill onto the neighbouring axes.
    _load(page, tmp_path, _mesh_fig_with_inset(), options={"slice": {"enabled": True}})
    assert _strips(page) == 1


@pytest.mark.browser
def test_a_wide_grid_gets_a_strip_for_every_axes_quickly(page, tmp_path):
    # 200 coupled meshes: a per-axes document scan (the old shape) made enabling
    # take many seconds; this guards against the quadratic version coming back.
    fig, axs = plotpress.subplots(8, 25, figsize=(25, 8))
    x, y = np.linspace(0, 1, 6), np.linspace(0, 1, 5)
    for ax in np.ravel(axs):
        ax.pcolormesh(x, y, np.arange(20, dtype=float).reshape(4, 5))
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "link_all": True}})
    assert _strips(page) == 200
    import time
    t0 = time.time()
    page.evaluate("""() => { const r = document.querySelector('.plotpress-slider input[type=range]');
        r.value = 3; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
    assert time.time() - t0 < 2.0


# ---- gridlines on the profile ----------------------------------------------------

def _grid_checkbox(page, checked=None):
    return page.evaluate("""(want) => {
      const cb = Array.from(document.querySelectorAll('.plotpress-menu-dropdown label')).find(
          l => l.textContent.includes('Gridlines on profile')).querySelector('input');
      if (want !== null && cb.checked !== want) cb.click();
      return cb.checked;
    }""", checked)


def _strip_line_count(page):
    return page.evaluate("document.querySelector('.plotpress-slice-companion g[stroke=\"#e3e3e3\"]')"
                         " ? document.querySelectorAll('.plotpress-slice-companion g[stroke=\"#e3e3e3\"] line').length : 0")


def test_grid_must_be_a_bool():
    with pytest.raises(ValueError):
        _grid_fig().to_html(options={"slice": {"grid": "yes"}})
    assert _config(_grid_fig().to_html(options={"slice": {"grid": False}}))["slice"] == {"grid": False}


@pytest.mark.browser
def test_the_grid_checkbox_toggles_the_strip_gridlines(page, tmp_path):
    _load(page, tmp_path, _grid_fig((1, 2)), options={"slice": {"enabled": True}})
    assert _grid_checkbox(page) is True
    on = _strip_line_count(page)
    assert on > 0
    _grid_checkbox(page, False)
    assert _strip_line_count(page) == 0
    _grid_checkbox(page, True)
    assert _strip_line_count(page) == on


@pytest.mark.browser
def test_the_strip_grid_has_lines_along_both_directions(page, tmp_path):
    # Value guides alone would all share one orientation; the spatial ones cross them.
    _load(page, tmp_path, _grid_fig((1, 1)), options={"slice": {"enabled": True, "orientation": "x"}})
    horiz, vert = page.evaluate("""() => {
      const ls = Array.from(document.querySelectorAll('.plotpress-slice-companion g[stroke="#e3e3e3"] line'));
      return [ls.filter(l => l.getAttribute('y1') === l.getAttribute('y2')).length,
              ls.filter(l => l.getAttribute('x1') === l.getAttribute('x2')).length];
    }""")
    assert horiz > 0 and vert > 0


@pytest.mark.browser
def test_the_replace_view_draws_its_grid_under_the_profile(page, tmp_path):
    _load(page, tmp_path, _grid_fig((1, 1)), options={"slice": {"enabled": True, "view": "replace"}})
    order = page.evaluate("""() => { const svg = document.getElementById('plotpress-svg');
      const kids = Array.from(svg.children);
      const g = kids.findIndex(k => k.classList.contains('plotpress-slice-ticks'));
      const l = kids.findIndex(k => k.classList.contains('plotpress-slice-line'));
      return [g, l, document.querySelectorAll('.plotpress-slice-grid').length]; }""")
    assert order[0] != -1 and order[0] < order[1] and order[2] == 1
    _grid_checkbox(page, False)
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-grid').length") == 0


@pytest.mark.browser
def test_grid_off_at_startup_and_kept_by_save(page, tmp_path):
    _load(page, tmp_path, _grid_fig((1, 1)), options={"slice": {"enabled": True, "grid": False}})
    assert _grid_checkbox(page) is False
    assert _strip_line_count(page) == 0
    _save_and_reopen(page, tmp_path)
    assert _grid_checkbox(page) is False
    assert _strip_line_count(page) == 0


# ---- inset axes are left out of Slice ---------------------------------------------

def _fig_with_meshed_inset():
    fig, axs = plotpress.subplots(1, 2, figsize=(10, 4))
    x, y = np.linspace(0, 1, 11), np.linspace(0, 1, 9)
    for ax in axs:
        ax.pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10))
    axs[0].inset_axes([0.6, 0.6, 0.3, 0.3]).pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10)[::-1])
    fig.tight_layout()
    return fig


def test_an_inset_names_its_parent_in_the_metadata():
    html = _fig_with_meshed_inset().to_html(interactive=True)
    meta = json.loads(re.search(r'id="plotpress-meta"[^>]*>(.*?)</script>', html, re.S).group(1))
    assert "inset_of" in json.dumps(meta)


@pytest.mark.browser
def test_an_inset_mesh_gets_no_slider_or_cursor(page, tmp_path):
    # Two ordinary meshes plus a mesh drawn in an inset of the first: only the two
    # ordinary ones are sliced.
    _load(page, tmp_path, _fig_with_meshed_inset(), options={"slice": {"enabled": True}})
    assert page.evaluate("document.querySelectorAll('.plotpress-slider').length") == 2
    assert page.evaluate("document.querySelectorAll('.plotpress-slice-cursor, [class*=slice-cursor]').length") == 2


# ---- a menu change that moves the profile has to bring the pins along ----------------

def _pick_range(page, label):
    page.evaluate("""(label) => Array.from(document.querySelectorAll(
        'input[name="plotpress-slice-range-mode"]')).find(
        r => r.parentNode.textContent.includes(label)).click()""", label)


def _profile_y_at(page, x):
    """The profile path's own y at user-space x -- where a pin there belongs."""
    return page.evaluate("""(x) => {
      const d = document.querySelector(
          '.plotpress-slice-companion path').getAttribute('d');
      let best = null, bd = Infinity;
      d.slice(1).split(/[ML]/).forEach(s => {
        const [px, py] = s.split(',').map(Number);
        if (Math.abs(px - x) < bd) { bd = Math.abs(px - x); best = py; }
      });
      return best; }""", x)


@pytest.mark.browser
def test_changing_the_value_range_keeps_strip_pins_on_the_profile(page, tmp_path):
    # The value range rescales the profile, so a pin on it has to be re-resolved
    # -- it used to stay at the pixel the *old* range put it at.
    _load(page, tmp_path, _ramp_fig(), options={"slice": {"enabled": True, "index": 3}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    pin_x = page.evaluate(
        "+document.querySelector('.plotpress-pin[data-kind=\"slice\"]').dataset.anchorX")
    pin_y = page.evaluate(
        "+document.querySelector('.plotpress-pin[data-kind=\"slice\"]').dataset.anchorY")
    assert pin_y == pytest.approx(_profile_y_at(page, pin_x), abs=1)

    page.evaluate("""() => { const ins = document.querySelectorAll(
        '.plotpress-slice-custom-range input');
        ins[0].value = -200; ins[1].value = 200;
        ins.forEach(i => i.dispatchEvent(new Event('change', {bubbles: true}))); }""")
    _pick_range(page, "Custom")
    moved_y = _profile_y_at(page, pin_x)
    pin_y2 = page.evaluate(
        "+document.querySelector('.plotpress-pin[data-kind=\"slice\"]').dataset.anchorY")
    assert moved_y != pytest.approx(pin_y, abs=2), "the profile should have rescaled"
    assert pin_y2 == pytest.approx(moved_y, abs=1)


@pytest.mark.browser
def test_link_all_keeps_the_slice_where_it_was(page, tmp_path):
    # Collapsing a group's sliders into one changes how a row is driven, not
    # which row is showing -- it used to snap every slice back to row 0.
    _load(page, tmp_path, _grid_fig(), options={"slice": {"enabled": True, "index": 5}})
    values = lambda: page.evaluate(  # noqa: E731
        """() => Array.from(document.querySelectorAll(
            '.plotpress-slider input[type=range]')).map(r => +r.value)""")
    assert values() and all(v == 5 for v in values())
    page.evaluate("""() => Array.from(document.querySelectorAll(
        '.plotpress-menu-dropdown label')).find(
        l => l.textContent.includes('Link all matching axes')
        ).querySelector('input').click()""")
    assert values() and all(v == 5 for v in values())


@pytest.mark.browser
def test_resetting_the_axes_keeps_a_twin_split_with_its_parent(page, tmp_path):
    # Reset All Axes (and a double-click reset) puts one axes back in its full,
    # original rect -- but under a companion strip the parent's heatmap only
    # owns part of that rect, so the twin used to come back spread over the
    # whole of it, its ticks running up into the strip.
    _load(page, tmp_path, _twin_fig(), options={"slice": {"enabled": True}})
    twin_ticks = lambda: page.evaluate(  # noqa: E731
        """() => Array.from(document.querySelectorAll('#ticks1 text')).map(
            t => Math.round(t.getBoundingClientRect().top))""")
    before = twin_ticks()
    assert before
    page.evaluate("""() => Array.from(document.querySelectorAll('button')).find(
        b => b.textContent.trim() === 'Reset All Axes').click()""")
    assert twin_ticks() == before


# ---- an axes too small to hold the strip's own legibility floor -------------

@pytest.mark.browser
@pytest.mark.parametrize("orient", ["x", "y"])
def test_a_strip_never_takes_more_than_its_own_axes(page, tmp_path, orient):
    # The strip's 28px floor is a minimum for a normal panel, not a claim on a
    # tiny one: a stack of ~23px panels used to give the strip more than the
    # whole axes, leaving the heatmap with a negative rect and drawing nothing
    # -- silently, since a negative width/height throws no error.
    if orient == "x":
        fig, axs = plotpress.subplots(14, 1, figsize=(6, 5))
    else:
        fig, axs = plotpress.subplots(1, 14, figsize=(6, 5))
    x, y = np.linspace(0, 10, 11), np.linspace(0, 8, 9)
    for ax in np.ravel(axs):
        ax.pcolormesh(x, y, np.arange(80, dtype=float).reshape(8, 10))
        ax.axis("off")
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    _load(page, tmp_path, fig,
          options={"slice": {"enabled": True, "orientation": orient}})
    rects = page.evaluate(r"""() => Array.from(document.querySelectorAll('clipPath'))
        .filter(c => /^clip\d+$/.test(c.id))
        .map(c => [+c.firstChild.getAttribute('width'),
                   +c.firstChild.getAttribute('height')])""")
    assert errs == [], errs
    assert rects and all(w > 0 and h > 0 for w, h in rects), rects


# ---- a slice with no finite values at all ----------------------------------

def _nan_row_fig(row=4):
    z = np.arange(80, dtype=float).reshape(8, 10)
    z[row] = np.nan
    fig, ax = plotpress.subplots(figsize=(7, 5))
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9), z)
    fig.tight_layout()
    return fig


@pytest.mark.browser
def test_an_all_nan_row_blanks_the_replace_profile(page, tmp_path):
    # Stepping onto a row with no values used to leave the *previous* row's
    # line on screen: the slider said row 4 while the profile plotted row 3.
    _load(page, tmp_path, _nan_row_fig(),
          options={"slice": {"enabled": True, "view": "replace", "index": 3}})
    line_d = lambda: page.evaluate(  # noqa: E731
        """() => { const l = document.querySelector('.plotpress-slice-line');
           return l ? l.getAttribute('d') : null; }""")
    row3 = line_d()
    assert row3
    _set_slider(page, 4)
    assert line_d() == ""                       # nothing to draw, and nothing stale
    _set_slider(page, 3)
    assert line_d() == row3                     # and it comes back


@pytest.mark.browser
def test_a_strip_pin_hides_over_an_all_nan_slice_and_returns(page, tmp_path):
    # slicePinPoint() returns null when the whole slice is NaN (no value range
    # to place against); that used to leave the pin visible, still showing the
    # value it read on the last row that had one.
    _load(page, tmp_path, _nan_row_fig(),
          options={"slice": {"enabled": True, "index": 3}})
    _enter_pick_mode(page)
    _click_strip(page, 0.5)
    state = lambda: page.evaluate(  # noqa: E731
        """() => { const p = document.querySelector('.plotpress-pin[data-kind="slice"]');
           return p && {display: p.style.display, label: p.textContent.trim()}; }""")
    on_row_3 = state()
    assert on_row_3["display"] == ""
    _set_slider(page, 4)
    assert state()["display"] == "none"
    _set_slider(page, 3)
    assert state() == on_row_3


# ---- the unsliced axis keeps its own ticks ---------------------------------

def _locator_mesh_fig():
    """A mesh whose x axis ticks every 2.5 by locator, not by "nice numbers"."""
    fig, ax = plotpress.subplots(figsize=(8, 5))
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9),
                  np.arange(80, dtype=float).reshape(8, 10))
    ax.set_xlocator({"kind": "multiple", "base": 2.5})
    fig.tight_layout()
    return fig


def _heatmap_xticks(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('#ticks0 text'))
        .filter(t => t.getAttribute('text-anchor') === 'middle')
        .map(t => [t.textContent, Math.round(+t.getAttribute('x'))])""")


@pytest.mark.browser
def test_strip_gridlines_sit_on_the_heatmaps_own_ticks(page, tmp_path):
    # The shared-axis guides are there to line up with the heatmap's ticks;
    # they used to be re-derived as plain "nice numbers", losing this axis'
    # locator (and equally its categories, date handling or format).
    _load(page, tmp_path, _locator_mesh_fig(), options={"slice": {"enabled": True}})
    tick_x = sorted(x for _, x in _heatmap_xticks(page))
    grid_x = page.evaluate("""() => Array.from(document.querySelectorAll(
        '.plotpress-slice-companion g[clip-path] line'))
        .filter(l => l.getAttribute('x1') === l.getAttribute('x2'))
        .map(l => Math.round(+l.getAttribute('x1'))).sort((a, b) => a - b)""")
    assert grid_x == tick_x, (grid_x, tick_x)


@pytest.mark.browser
def test_the_replace_view_keeps_the_unsliced_axis_ticks_as_they_were(page, tmp_path):
    _load(page, tmp_path, _locator_mesh_fig(),
          options={"slice": {"enabled": True, "view": "cursor"}})
    before = _heatmap_xticks(page)
    assert [lab for lab, _ in before] == ["0", "2.5", "5", "7.5", "10"], before
    _pick_view(page, "replaces")
    after = page.evaluate("""() => Array.from(document.querySelectorAll(
        '.plotpress-slice-ticks text'))
        .filter(t => t.getAttribute('text-anchor') === 'middle')
        .map(t => [t.textContent, Math.round(+t.getAttribute('x'))])""")
    assert after == before, (after, before)


# ---- Slice's mesh hiding must not collide with the legend's ----------------

@pytest.mark.browser
def test_a_slider_step_leaves_a_legend_hidden_mesh_hidden(page, tmp_path):
    # Slice and the legend's click-to-hide toggle both used to write the
    # element's own style.display, so whichever ran last undid the other: a
    # slider step brought back a mesh the reader had just hidden.
    fig, ax = plotpress.subplots(figsize=(7, 5))
    ax.pcolormesh(np.linspace(0, 10, 11), np.linspace(0, 8, 9),
                  np.arange(80, dtype=float).reshape(8, 10), label="grid")
    ax.plot([0, 10], [0, 8], label="line")
    ax.legend()
    fig.tight_layout()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "view": "cursor"}})
    shown = lambda: page.evaluate(  # noqa: E731
        "() => getComputedStyle(document.querySelector('.plotpress-mesh')).display")
    assert shown() != "none"
    page.evaluate("""() => { const t = Array.from(document.querySelectorAll(
        '.plotpress-legend text')).find(t => t.textContent === 'grid');
        t.dispatchEvent(new MouseEvent('click', {bubbles: true})); }""")
    assert shown() == "none"
    _set_slider(page, 5)
    assert shown() == "none", "a slider step un-hid a legend-hidden mesh"


@pytest.mark.browser
def test_the_replace_view_still_hides_the_mesh_it_stands_in_for(page, tmp_path):
    # The other half of the same split: Slice's own hiding still has to work.
    fig, z = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "view": "replace"}})
    shown = lambda: page.evaluate(  # noqa: E731
        "() => getComputedStyle(document.querySelector('.plotpress-mesh')).display")
    assert shown() == "none"
    _pick_view(page, "cursor")
    assert shown() != "none"


# ---- the menu has to stay inside a short embed ------------------------------

def _open_menu(page, label):
    page.evaluate("""(l) => Array.from(document.querySelectorAll(
        '.plotpress-menu-label')).find(
        b => b.textContent.trim().startsWith(l)).click()""", label)


def _open_dropdown_fit(page):
    return page.evaluate("""() => {
      const d = document.querySelector(
        '.plotpress-menu.open .plotpress-menu-dropdown');
      if (!d) return null;
      const r = d.getBoundingClientRect();
      const items = d.querySelectorAll('label, button, input');
      d.scrollTop = d.scrollHeight;                 // scroll to the end
      const last = items[items.length - 1].getBoundingClientRect();
      return {overflowBottom: Math.round(r.bottom - document.documentElement.clientHeight),
              overflowRight: Math.round(r.right - document.documentElement.clientWidth),
              scrolls: d.scrollHeight > d.clientHeight + 1,
              lastReachable: last.bottom <= r.bottom + 1 && last.top >= r.top - 1}; }""")


@pytest.mark.browser
@pytest.mark.parametrize("height", [560, 420, 320])
def test_the_slice_menu_stays_inside_a_short_embedded_figure(page, tmp_path, height):
    # A figure embedded in a page (a Report panel, a docs gallery iframe) gets
    # whatever height the host gave it. The Slice menu is the tallest one, and
    # with nothing bounding it the bottom of the list fell outside the document
    # -- clipped away rather than scrolled off, since an iframe has no viewport
    # of its own to scroll, so those options could not be reached at all.
    original = dict(page.viewport_size)
    try:
        page.set_viewport_size({"width": 1064, "height": height})
        _load(page, tmp_path, _grid_fig(), options={"slice": {}})
        _open_menu(page, "Slice")
        fit = _open_dropdown_fit(page)
        assert fit is not None, "the Slice menu did not open"
        assert fit["overflowBottom"] <= 0, fit
        assert fit["overflowRight"] <= 0, fit
        assert fit["lastReachable"], fit
    finally:
        page.set_viewport_size(original)


@pytest.mark.browser
def test_a_tall_viewport_leaves_the_menu_unclamped(page, tmp_path):
    # The clamp is only for the cramped case; with room to spare the menu must
    # still render at its natural height, with no internal scrollbar.
    original = dict(page.viewport_size)
    try:
        page.set_viewport_size({"width": 1280, "height": 1000})
        _load(page, tmp_path, _grid_fig(), options={"slice": {}})
        _open_menu(page, "Slice")
        fit = _open_dropdown_fit(page)
        assert fit["scrolls"] is False, fit
        assert fit["overflowBottom"] <= 0, fit
    finally:
        page.set_viewport_size(original)


# ---- the global slider bar at scale ----------------------------------------

def _mixed_shape_fig(nrows, ncols, shapes):
    """A grid whose meshes come in `shapes` distinct grid shapes, so Slice's
    link grouping produces that many compatible groups."""
    fig, arr = plotpress.subplots(nrows, ncols, subplot_size=(0.9, 0.7),
                                  squeeze=False)
    rng = np.random.default_rng(0)
    for i, ax in enumerate(ax for row in arr for ax in row):
        n = 6 + (i % shapes)
        ax.pcolormesh(np.linspace(0, 1, 13), np.linspace(0, 1, n + 1),
                      rng.normal(size=(n, 12)))
        ax.tick_params(labelsize=4)
    fig.tight_layout()
    return fig


@pytest.mark.browser
@pytest.mark.parametrize("shapes, height", [(16, 504), (24, 900)])
def test_the_global_slider_bar_stays_reachable_at_scale(page, tmp_path,
                                                        shapes, height):
    # "Link all matching axes" makes one global slider per compatible group, so
    # a figure whose meshes come in many grid shapes stacks many of them in the
    # bar fixed to the bottom of the window. With nothing bounding that column
    # it grew off the *top* of the window -- 24 groups made a 1319px bar in a
    # 900px viewport -- and a position:fixed element does not scroll with the
    # page, so those sliders could not be reached at all.
    original = dict(page.viewport_size)
    try:
        page.set_viewport_size({"width": 1000, "height": height})
        _load(page, tmp_path, _mixed_shape_fig(6, 8, shapes),
              options={"slice": {"enabled": True, "link_all": True}})
        state = page.evaluate(r"""() => {
          const bar = document.querySelector('.plotpress-sliders');
          const sliders = Array.from(
            document.querySelectorAll('.plotpress-slider'));
          const vh = document.documentElement.clientHeight;
          const br = bar.getBoundingClientRect();
          let unreachable = 0;
          for (const s of sliders) {           // scroll each into the bar
            bar.scrollTop = s.offsetTop;
            const r = s.getBoundingClientRect();
            if (r.top < br.top - 1 || r.bottom > br.bottom + 1) unreachable++;
          }
          bar.scrollTop = 0;
          return {sliders: sliders.length, unreachable,
                  barOffscreen: br.top < -1 || br.bottom > vh + 1}; }""")
        assert state["sliders"] == shapes, state
        assert not state["barOffscreen"], state
        assert state["unreachable"] == 0, state
    finally:
        page.set_viewport_size(original)
