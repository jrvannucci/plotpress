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
    fills = [f for _, f in _label_fills(page)]           # pin, pin, mirror, mirror
    assert fills[0] == fills[2] and fills[1] == fills[3]  # each pair shares a color...
    assert fills[0] != fills[1]                           # ...and the pairs differ
    assert "#111" not in fills
    _set_snap(page, False)
    assert {f for _, f in _label_fills(page)} == {"#111"}  # back to ordinary labels


@pytest.mark.browser
def test_a_pins_link_color_survives_another_pin_being_deleted(page, tmp_path):
    fig, _ = _pick_fig()
    _load(page, tmp_path, fig, options={"slice": {"enabled": True, "snap_pins": True}})
    _enter_pick_mode(page)
    _click_heatmap(page, 0.3, 0.5)
    _click_heatmap(page, 0.8, 0.7)
    second = _label_fills(page)[1][1]
    page.evaluate("""() => document.querySelector('.plotpress-pin:not([data-snapped])')
        .dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true}))""")
    assert [f for s_, f in _label_fills(page) if not s_] == [second]


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
    assert over["red"] == "#ff6b6b"                    # the value is red
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
