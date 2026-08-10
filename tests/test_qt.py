"""Tests for the optional PyQt/PySide viewer (``plotpress.qt``).

The Qt code path needs a binding + WebEngine, which CI does not install, so the
GUI test skips there. The contract tests below run everywhere: they guard the
JS hook the widget depends on and the friendly no-binding error.
"""
import importlib
import json
import os
import pathlib
import sys
import time

import numpy as np
import pytest

import plotpress


def _has_qt_binding():
    for name in ("PyQt6", "PySide6", "PyQt5"):
        try:
            importlib.import_module(name)
            importlib.import_module(name + ".QtWebEngineWidgets")
            return True
        except ImportError:
            continue
    return False


def _wait_for_load(view, app, timeout_ms=5000):
    # QWebEngineView.load() is async; closing a view (or the app moving on
    # to another test) while a load is still in flight leaves a dangling
    # continuation in the WebEngine process that can crash a *later*, wholly
    # unrelated event-loop spin. Every test that touches a view must let its
    # load actually finish before moving on -- this pumps the event loop
    # until `loadFinished` fires (or `timeout_ms` elapses, so a genuine
    # failure to load still ends the test instead of hanging it).
    done = []
    view.loadFinished.connect(lambda ok: done.append(ok))
    elapsed = 0
    step = 20
    while not done and elapsed < timeout_ms:
        app.processEvents()
        time.sleep(step / 1000)
        elapsed += step
    return bool(done and done[0])


def test_qt_widget_targets_a_real_marker_hook():
    # PlotPressWidget.markers() pulls picked markers via
    # window.plotpressGetMarkers(); that hook must exist in the interactive JS,
    # and qt.py must reference it (both checked without importing Qt).
    from plotpress._interactive import INTERACTIVE_JS

    assert "window.plotpressGetMarkers" in INTERACTIVE_JS
    src = (pathlib.Path(plotpress.__file__).parent / "qt.py").read_text(encoding="utf-8")
    assert "plotpressGetMarkers" in src


def test_qt_import_error_is_friendly_when_no_binding():
    if _has_qt_binding():
        pytest.skip("a Qt binding is installed; the no-binding path can't be exercised")
    with pytest.raises(ImportError, match=r"plotpress\[qt\]"):
        importlib.import_module("plotpress.qt")


def test_show_qt_is_lazy():
    # Importing plotpress must not require Qt; the method only pulls it in when
    # called. Presence of the attribute is enough to assert the wiring.
    assert hasattr(plotpress.Figure, "show_qt")


def test_live_artist_targets_the_pick_update_hook():
    # LiveArtist patches an already-loaded page's pick payload via
    # window.plotpressUpdatePick; that hook must exist in the interactive JS,
    # and qt.py must reference it (both checked without importing Qt).
    from plotpress._interactive import INTERACTIVE_JS

    assert "window.plotpressUpdatePick" in INTERACTIVE_JS
    src = (pathlib.Path(plotpress.__file__).parent / "qt.py").read_text(encoding="utf-8")
    assert "plotpressUpdatePick" in src


@pytest.fixture(scope="module")
def shared_qt_widget():
    # Every test in this file that needs a real QWebEngineView shares this
    # one widget/view rather than each constructing its own: creating a
    # second QWebEngineView after a prior one has been closed, within the
    # same process, is fragile on this platform (offscreen WebEngine +
    # PyQt6) and can crash a later, unrelated event-loop spin even when
    # each view's own load/close is individually well-behaved. One process,
    # one view.
    if not _has_qt_binding():
        pytest.skip("no Qt binding with WebEngine installed")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import plotpress.qt as spqt

    app = spqt._QT.QApplication.instance() or spqt._QT.QApplication(sys.argv)
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(16, dtype=float).reshape(4, 4))
    w = spqt.PlotPressWidget(fig)
    _wait_for_load(w.view, app)
    yield spqt, app, w
    w.close()


def test_plotpress_widget_smoke(shared_qt_widget):
    spqt, app, w = shared_qt_widget

    assert isinstance(w, spqt._QT.QWidget)
    assert isinstance(w.view, spqt._QT.QWebEngineView)
    # A backing temp file was created for the (async) load.
    assert w._temp and os.path.exists(w._temp)
    # Swapping the figure replaces the temp file without error.
    old = w._temp
    fig, ax = plotpress.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    w.set_figure(fig)
    assert w._temp and w._temp != old
    _wait_for_load(w.view, app)


def test_live_artist_line_and_sparse_mesh(shared_qt_widget):
    # LiveArtist's first update() is a normal full-page load; every update
    # after that patches the already-loaded page via runJavaScript instead
    # (both the visible SVG and the point-pick payload). This exercises both
    # paths for a line and for a mostly-NaN mesh (the realistic case for a
    # progressively-collected 2-D sweep) -- critically, the mesh gets a
    # *second* update (still NaN-heavy) so the click below verifies the
    # JS-patch path itself, not just the first load: a bare NaN in the
    # live-refreshed pick payload is valid Python but not valid JSON, so an
    # unsanitized one would make `JSON.parse` throw inside
    # `window.plotpressUpdatePick` and silently leave picking on stale,
    # first-load data -- which a test that only ever called `mesh.update()`
    # once (the full-reload path, no JS patch involved at all) would never
    # catch.
    spqt, app, widget = shared_qt_widget
    from plotpress.svg import _effective_rect, _pixel_rect
    from plotpress.transform import LinearTransform

    qtcore = __import__(spqt._QT.name + ".QtCore", fromlist=["QTimer"])
    QTimer = qtcore.QTimer

    # Re-target the shared widget at a fresh figure with two axes; the first
    # LiveArtist.update() call below does the actual (re)load.
    fig, (ax, mesh_ax) = plotpress.subplots(1, 2, figsize=(8, 4))
    line = spqt.LiveArtist(widget, fig, ax)
    mesh = spqt.LiveArtist(widget, fig, mesh_ax, cmap="viridis", vmin=0, vmax=10)

    grid = np.full((4, 4), np.nan)
    grid[1, 2] = 7.0   # filled on the first (full-reload) mesh update
    gx = np.arange(5, dtype=float)
    gy = np.arange(5, dtype=float)

    state = {"errors": []}
    results = {}

    def click_px(target_ax, target_fig, dx, dy):
        dpi = target_fig.style.dpi
        (xmin, xmax), (ymin, ymax) = target_ax._resolved_limits()
        rect = _effective_rect(
            target_ax, *_pixel_rect(target_ax, target_fig.figsize[0] * dpi,
                                     target_fig.figsize[1] * dpi),
            (xmin, xmax), (ymin, ymax))
        tr = LinearTransform((xmax, xmin) if target_ax._xinverted else (xmin, xmax),
                              (ymax, ymin) if target_ax._yinverted else (ymin, ymax),
                              rect, xscale=target_ax._xscale, yscale=target_ax._yscale)
        return float(tr.x(dx)), float(tr.y(dy))

    def click_js(ux, uy):
        return """
        (function() {
          var svg = document.getElementById('plotpress-svg');
          document.querySelectorAll('.plotpress-toolbar button').forEach(function(b) {
            if (b.textContent === 'Point Pick' && !b.classList.contains('active')) b.click();
          });
          var pt = svg.createSVGPoint(); pt.x = %f; pt.y = %f;
          var c = pt.matrixTransform(svg.getScreenCTM());
          var el = document.elementFromPoint(c.x, c.y) || svg;
          el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true,
            clientX: c.x, clientY: c.y, button: 0}));
          return JSON.stringify(window.plotpressGetMarkers());
        })();
        """ % (ux, uy)

    def do_line_update(n):
        x = np.arange(n + 2, dtype=float)
        y = x * 2.0
        try:
            line.update(x, y)
        except Exception as exc:   # noqa: BLE001 -- surfaced via state["errors"]
            state["errors"].append(("line", exc))
            app.quit()

    def on_line_injected(ok):
        # Fires only for the injected (2nd+) calls -- runJavaScript's own
        # callback, so this really means "the DOM patch landed", not a guess.
        n = state["line_n"] + 1
        state["line_n"] = n
        if n == 1:
            do_line_update(2)
        else:
            do_mesh_update(0)

    def do_mesh_update(n):
        if n == 1:
            grid[2, 3] = 3.5   # a second cell revealed on the injected update,
                                # rest of the grid (including [1, 2]'s neighbors) still NaN
        try:
            mesh.update(gx, gy, grid)
        except Exception as exc:   # noqa: BLE001
            state["errors"].append(("mesh", exc))
            app.quit()

    def on_mesh_injected(ok):
        # Fires once the second mesh update's JS patch round-trips -- the
        # path a bare NaN elsewhere in the grid would otherwise break
        # (JSON.parse throwing inside window.plotpressUpdatePick, leaving
        # PICK stale) without ever raising on the Python side.
        check_mesh_click()

    def on_load_finished(ok):
        # Real QWebEngineView.loadFinished -- fires once per full-page
        # navigation, i.e. once for `line`'s first update() and once for
        # `mesh`'s (each LiveArtist tracks its own loaded state, so touching
        # a second axes on the same widget triggers its own first load).
        state["loads"] += 1
        if state["loads"] == 1:
            line.on_complete = on_line_injected
            do_line_update(1)
        else:
            mesh.on_complete = on_mesh_injected
            do_mesh_update(1)

    def check_mesh_click():
        # Cell (row=2, col=3) -- only revealed by the second, JS-patched
        # update, with the rest of the grid still NaN around it.
        ux, uy = click_px(mesh_ax, fig, 3.5, 2.5)
        widget.view.page().runJavaScript(click_js(ux, uy), got_mesh_click)

    def got_mesh_click(result):
        results["mesh_click"] = result
        app.quit()

    state["line_n"] = 0
    state["loads"] = 0
    widget.view.loadFinished.connect(on_load_finished)
    QTimer.singleShot(0, lambda: do_line_update(0))
    QTimer.singleShot(15000, app.quit)   # safety timeout
    app.exec()

    assert state["errors"] == []
    markers = json.loads(results.get("mesh_click") or "[]")
    assert markers, (
        "click on the cell revealed by the JS-patched (2nd) mesh update produced "
        "no marker -- if PICK silently failed to refresh (e.g. a NaN elsewhere in "
        "the still-mostly-empty grid broke JSON.parse), this cell would report "
        "nothing rather than the stale first-load data, since it didn't exist yet"
    )
    assert markers[0]["z"] == pytest.approx(3.5)
