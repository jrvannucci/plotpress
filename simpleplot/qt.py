"""Embed interactive simpleplot figures in PyQt / PySide apps.

A simpleplot figure already knows how to render itself as a self-contained
interactive HTML document (the same vector SVG plus a vanilla-JS toolbar: span /
pan, data-space zoom, point-picking, annotation, sliders, and marker extract).
This module drops that document into a ``QWebEngineView`` so the *whole* toolbar
works inside a native Qt app -- nothing is reimplemented.

Works with **PyQt6**, **PySide6**, or **PyQt5** (whichever is installed, tried in
that order). Install one with the ``qt`` extra::

    pip install simpleplot[qt]        # PyQt6 + PyQt6-WebEngine

Embed it like any other widget
------------------------------

``SimplePlotWidget`` is a plain ``QWidget`` subclass -- add it to a layout, give
it a parent, restyle it, swap the figure at runtime::

    from simpleplot.qt import SimplePlotWidget

    plot = SimplePlotWidget(fig)      # or SimplePlotWidget() then plot.set_figure(fig)
    my_layout.addWidget(plot)
    ...
    plot.set_figure(other_fig)        # redraw with a new figure
    plot.markers(print)               # async: hand the picked markers to a callback

Quick standalone window
-----------------------

    import simpleplot.qt as spqt
    spqt.view(fig)                    # opens a window, blocks until closed

or, equivalently, ``fig.show_qt()``.
"""

from __future__ import annotations

import atexit
import os
import tempfile
import types

# Temp HTML files backing the views; QWebEngineView.load() is async, so each
# file must outlive the load. Cleaned up per-widget and again at interpreter exit.
_TEMP_FILES: set[str] = set()


def _load_binding():
    """Import a Qt binding + its WebEngine widget; return them in a namespace.

    Tries PyQt6, then PySide6, then PyQt5. Raises a friendly ImportError naming
    the ``qt`` extra if none is importable.
    """
    tried = []
    for name in ("PyQt6", "PySide6", "PyQt5"):
        try:
            widgets = __import__(name + ".QtWidgets", fromlist=["*"])
            webengine = __import__(name + ".QtWebEngineWidgets", fromlist=["*"])
            core = __import__(name + ".QtCore", fromlist=["*"])
            return types.SimpleNamespace(
                name=name,
                QApplication=widgets.QApplication,
                QWidget=widgets.QWidget,
                QVBoxLayout=widgets.QVBoxLayout,
                QWebEngineView=webengine.QWebEngineView,
                QUrl=core.QUrl,
                Qt=core.Qt,
            )
        except ImportError as exc:   # binding (or its WebEngine module) missing
            tried.append(f"{name}: {exc}")
    raise ImportError(
        "simpleplot.qt needs a Qt binding with WebEngine. Install one:\n"
        "  pip install simpleplot[qt]        # PyQt6 + PyQt6-WebEngine\n"
        "  # or PySide6, or PyQt5 + PyQtWebEngine\n"
        "tried:\n  " + "\n  ".join(tried)
    )


_QT = _load_binding()


def _remove_temp(path):
    try:
        os.remove(path)
    except OSError:
        pass
    _TEMP_FILES.discard(path)


@atexit.register
def _cleanup_all_temps():
    for path in list(_TEMP_FILES):
        _remove_temp(path)


class SimplePlotWidget(_QT.QWidget):
    """A ``QWidget`` that renders a simpleplot :class:`~simpleplot.Figure`
    as an interactive figure.

    Parameters
    ----------
    figure : simpleplot.Figure, optional
        Figure to display now. Omit and call :meth:`set_figure` later.
    parent : QWidget, optional
        Standard Qt parent.
    interactive : bool, default True
        Include the JS toolbar. ``False`` embeds a static (but still crisp,
        zoomable-by-Qt) SVG document.
    pick_precision : int, default 6
        Decimal places for the embedded point-pick data (see
        :meth:`simpleplot.Figure.to_html`). Lower it to shrink mesh-heavy
        figures.
    """

    def __init__(self, figure=None, parent=None, interactive=True,
                 pick_precision=6):
        super().__init__(parent)
        self._interactive = interactive
        self._pick_precision = pick_precision
        self._temp = None

        self._view = _QT.QWebEngineView(self)
        layout = _QT.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        if figure is not None:
            self.set_figure(figure)

    # -- public API ---------------------------------------------------------
    def set_figure(self, figure, interactive=None, pick_precision=None):
        """Render ``figure`` into the view, replacing any current one."""
        if interactive is not None:
            self._interactive = interactive
        if pick_precision is not None:
            self._pick_precision = pick_precision
        html = figure.to_html(interactive=self._interactive,
                              pick_precision=self._pick_precision)
        self._load_html(html)
        # A sensible default size from the figure's pixel dimensions.
        w = int(figure.figsize[0] * figure.style.dpi)
        h = int(figure.figsize[1] * figure.style.dpi)
        self._view.setMinimumSize(200, 150)
        self.resize(w, h)

    @property
    def view(self):
        """The underlying ``QWebEngineView`` (for advanced customization)."""
        return self._view

    def markers(self, callback):
        """Asynchronously fetch the picked markers, then call ``callback(list)``.

        Each marker is a dict of values (``x``, ``y``, any extra dims like ``z``
        / ``c``, plus ``axes`` and ``kind``) -- the same records the in-figure
        **Extract** button produces. Async because Qt runs page JS off-thread.
        """
        import json

        js = ("JSON.stringify(window.simpleplotGetMarkers ? "
              "window.simpleplotGetMarkers() : [])")

        def _done(result):
            try:
                callback(json.loads(result) if result else [])
            except (ValueError, TypeError):
                callback([])

        self._view.page().runJavaScript(js, _done)

    # -- internals ----------------------------------------------------------
    def _load_html(self, html):
        # QWebEngineView.setHtml() silently truncates content over ~2 MB, which
        # the mesh-heavy figures blow past. Writing to a temp file and loading by
        # URL has no size limit; the document is self-contained (data: URIs), so
        # a file:// base URL resolves everything.
        self._drop_temp()
        fd, path = tempfile.mkstemp(suffix=".html", prefix="simpleplot_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html)
        self._temp = path
        _TEMP_FILES.add(path)
        self._view.load(_QT.QUrl.fromLocalFile(path))

    def _drop_temp(self):
        if self._temp:
            _remove_temp(self._temp)
            self._temp = None

    def closeEvent(self, event):   # noqa: N802 (Qt naming)
        self._drop_temp()
        super().closeEvent(event)


def view(figure, title="simpleplot", block=True, interactive=True,
         pick_precision=6):
    """Open ``figure`` in a standalone Qt window.

    Reuses the running ``QApplication`` if there is one (e.g. inside an existing
    app or an IPython Qt event loop); otherwise creates one. With ``block=True``
    (the default outside an existing app) the call blocks until the window
    closes. Returns the :class:`SimplePlotWidget`.
    """
    app = _QT.QApplication.instance()
    owns_app = app is None
    if owns_app:
        _enable_webengine_gl()
        app = _QT.QApplication([])

    widget = SimplePlotWidget(figure, interactive=interactive,
                              pick_precision=pick_precision)
    widget.setWindowTitle(title)
    widget.show()

    if block and owns_app:
        # exec() on PyQt6/PySide6; exec_() on PyQt5.
        (getattr(app, "exec", None) or app.exec_)()
    return widget


def _enable_webengine_gl():
    """Best-effort: some platforms need shared GL contexts for WebEngine."""
    attr = getattr(getattr(_QT.Qt, "ApplicationAttribute", _QT.Qt),
                   "AA_ShareOpenGLContexts", None)
    if attr is not None:
        try:
            _QT.QApplication.setAttribute(attr, True)
        except (TypeError, RuntimeError):
            pass
