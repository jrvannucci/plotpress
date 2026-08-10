"""Tests for the optional PyQt/PySide viewer (``plotpress.qt``).

The Qt code path needs a binding + WebEngine, which CI does not install, so the
GUI test skips there. The contract tests below run everywhere: they guard the
JS hook the widget depends on and the friendly no-binding error.
"""
import importlib
import os
import pathlib
import sys

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


@pytest.mark.skipif(not _has_qt_binding(), reason="no Qt binding with WebEngine installed")
def test_plotpress_widget_smoke():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import plotpress.qt as spqt

    app = spqt._QT.QApplication.instance() or spqt._QT.QApplication(sys.argv)
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(16, dtype=float).reshape(4, 4))

    w = spqt.PlotPressWidget(fig)
    try:
        assert isinstance(w, spqt._QT.QWidget)
        assert isinstance(w.view, spqt._QT.QWebEngineView)
        # A backing temp file was created for the (async) load.
        assert w._temp and os.path.exists(w._temp)
        # Swapping the figure replaces the temp file without error.
        old = w._temp
        w.set_figure(fig)
        assert w._temp and w._temp != old
    finally:
        w.close()
        assert not w._temp or not os.path.exists(w._temp)
    app.processEvents()
