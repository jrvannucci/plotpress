"""Embed interactive plotpress figures in PyQt / PySide apps.

A plotpress figure already knows how to render itself as a self-contained
interactive HTML document (the same vector SVG plus a vanilla-JS toolbar: span /
pan, data-space zoom, point-picking, annotation, sliders, and marker extract).
This module drops that document into a ``QWebEngineView`` so the *whole* toolbar
works inside a native Qt app -- nothing is reimplemented.

Works with **PyQt6**, **PySide6**, or **PyQt5** (whichever is installed, tried in
that order). Install one with the ``qt`` extra::

    pip install plotpress[qt]        # PyQt6 + PyQt6-WebEngine

Embed it like any other widget
------------------------------

``PlotPressWidget`` is a plain ``QWidget`` subclass -- add it to a layout, give
it a parent, restyle it, swap the figure at runtime::

    from plotpress.qt import PlotPressWidget

    plot = PlotPressWidget(fig)      # or PlotPressWidget() then plot.set_figure(fig)
    my_layout.addWidget(plot)
    ...
    plot.set_figure(other_fig)        # redraw with a new figure
    plot.markers(print)               # async: hand the picked markers to a callback

Quick standalone window
-----------------------

    import plotpress.qt as spqt
    spqt.view(fig)                    # opens a window, blocks until closed

or, equivalently, ``fig.show_qt()``.
"""

from __future__ import annotations

import atexit
import json
import os
import sys
import tempfile
import types

# Temp HTML files backing the views; QWebEngineView.load() is async, so each
# file must outlive the load. Cleaned up per-widget and again at interpreter exit.
#
# A deliberate, narrow exception to "no module-level mutable state" (see
# CLAUDE.md and tests/test_no_global_state.py): this is process-wide *resource
# cleanup bookkeeping*, not figure-rendering state -- it never makes one
# PlotPressWidget's behavior depend on another's, only ensures every widget's
# own temp file still gets removed at interpreter exit even if its widget
# was never cleanly closed. See test_temp_files_registry_entries_are_independent
# in tests/test_qt.py for the property that actually matters here: removing
# one widget's temp file never touches another's.
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
        "plotpress.qt needs a Qt binding with WebEngine. Install one:\n"
        "  pip install plotpress[qt]        # PyQt6 + PyQt6-WebEngine\n"
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


class PlotPressWidget(_QT.QWidget):
    """A ``QWidget`` that renders a plotpress :class:`~plotpress.Figure`
    as an interactive figure.

    Parameters
    ----------
    figure : plotpress.Figure, optional
        Figure to display now. Omit and call :meth:`set_figure` later.
    parent : QWidget, optional
        Standard Qt parent.
    interactive : bool, default True
        Include the JS toolbar. ``False`` embeds a static (but still crisp,
        zoomable-by-Qt) SVG document.
    pick_precision : int, default 6
        Decimal places for the embedded point-pick data (see
        :meth:`plotpress.Figure.to_html`). Lower it to shrink mesh-heavy
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
        js = ("JSON.stringify(window.plotpressGetMarkers ? "
              "window.plotpressGetMarkers() : [])")

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
        fd, path = tempfile.mkstemp(suffix=".html", prefix="plotpress_")
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


class LiveArtist:
    """A line or mesh that redraws in place, without reloading the page.

    ``PlotPressWidget.set_figure()`` is a full ``QWebEngineView`` navigation
    -- a fresh temp file, page teardown/setup, the toolbar JS re-running from
    scratch -- which tops out around 4-5 Hz regardless of data size, since
    that cost is dominated by the navigation itself rather than by rendering.
    ``LiveArtist`` loads the figure once (a normal, full ``set_figure()``
    call, needed to get the toolbar/JS/pick-data in place) and every update
    after that patches the already-loaded page instead: the visible SVG's
    content is swapped for a fresh render, and the point-pick payload for
    this artist's axes is refreshed to match, both in one round trip.
    Measured (offscreen ``QWebEngineView``, PyQt6) at roughly 55 Hz sustained
    for a 50,000-point line and 140 Hz for a 100x100 mesh, against a
    full-reload ceiling around 4-5 Hz regardless of data size -- since that
    ceiling comes from the page navigation itself, not from rendering, it
    doesn't move no matter how much data is on the figure.

    A NaN-heavy or sparsely/progressively collected mesh -- the common case
    for a real 2-D instrument sweep, most of the grid unmeasured at first --
    needs no special handling: NaN already renders as "no data" and reports
    as such on pick, the same as a static figure's masked region.

    Parameters
    ----------
    widget : PlotPressWidget
        Must already be showing ``fig`` (or about to -- the first
        :meth:`update` call does that itself).
    fig : plotpress.Figure
    ax : plotpress.Axes
        Must belong to ``fig``.
    on_complete : callable, optional
        Called after each :meth:`update` finishes, with a single argument
        that means different things depending on which path that call took:
        for the very first call (a full page load) it is ``True``, fired
        *synchronously* right after the (async) navigation is started, not
        when the page actually finishes loading -- there is no callback for
        that from a fire-and-forget ``set_figure()``. For every call after
        that (the patched-page path), it fires *asynchronously*, once the
        ``page().runJavaScript()`` round trip genuinely completes, with the
        JS return value (truthy on success).
    **plot_kwargs
        Forwarded to ``ax.plot()`` (a 2-argument :meth:`update`) or
        ``ax.pcolormesh()`` (a 3-argument one) on every call -- ``color``,
        ``cmap``, ``vmin``/``vmax``, etc.

    Attributes
    ----------
    last_artist : Line2D or QuadMesh or None
        Whatever the most recent :meth:`update` drew -- ``None`` before the
        first call. Since ``update()`` clears the whole axes on every call,
        a colorbar for an autoscaled mesh (no fixed ``vmin``/``vmax``) has
        to be dropped and redrawn from the new mappable each time too; this
        is what to hand ``fig.colorbar()`` for that::

            mesh = LiveArtist(widget, fig, ax, cmap="viridis")
            cbar_ax = None

            def on_new_frame(x, y, c):
                global cbar_ax
                mesh.update(x, y, c)
                if cbar_ax is not None:
                    fig.delaxes(cbar_ax)
                cbar_ax = fig.colorbar(mesh.last_artist, ax=ax)

    Examples
    --------
    A rolling line, one new sample per call::

        from collections import deque
        from plotpress.qt import PlotPressWidget, LiveArtist

        fig, ax = plotpress.subplots()
        widget = PlotPressWidget(fig)
        line = LiveArtist(widget, fig, ax)
        xs, ys = deque(maxlen=500), deque(maxlen=500)

        def on_new_sample(x, y):
            xs.append(x); ys.append(y)
            line.update(np.fromiter(xs, float), np.fromiter(ys, float))

    A mesh filled in as a 2-D sweep collects, starting all-NaN::

        mesh = LiveArtist(widget, fig, ax, cmap="viridis", vmin=0, vmax=1)
        grid = np.full((ny, nx), np.nan)

        def on_new_point(row, col, value):
            grid[row, col] = value
            mesh.update(x_edges, y_edges, grid)   # 3 args -> pcolormesh
    """

    def __init__(self, widget, fig, ax, on_complete=None, **plot_kwargs):
        self.widget = widget
        self.fig = fig
        self.ax = ax
        self.plot_kwargs = plot_kwargs
        self.on_complete = on_complete or (lambda _result: None)
        self.last_artist = None
        self._loaded = False

    def update(self, *data):
        """Redraw with new data: ``update(x, y)`` for a line, ``update(x, y,
        C)`` for a mesh -- same argument shape as ``ax.plot()``/
        ``ax.pcolormesh()``, which is exactly what this calls after clearing
        the axes. The very first call goes through a full page load (needed
        once to get the toolbar/JS in place); every call after that patches
        the already-loaded page instead.
        """
        if len(data) == 2:
            x, y = data
            self.ax.cla()
            self.last_artist = self.ax.plot(x, y, **self.plot_kwargs)
            if len(x):
                self.ax.set_xlim(float(min(x)), float(max(x)))
        elif len(data) == 3:
            x, y, c = data
            self.ax.cla()
            self.last_artist = self.ax.pcolormesh(x, y, c, **self.plot_kwargs)
        else:
            raise TypeError(
                "update() takes (x, y) for a line or (x, y, C) for a mesh, "
                f"got {len(data)} arguments")

        if not self._loaded:
            self.widget.set_figure(self.fig)
            self._loaded = True
            self.on_complete(True)
        else:
            from .figure import _sanitize_nan
            from .svg import pick_data
            svg = self.fig.to_svg()
            axes_index = self.fig.axes.index(self.ax)
            entry = pick_data(self.fig).get(
                axes_index, {"series": [], "meshes": [], "pies": []})
            self.widget.view.page().runJavaScript(
                _live_update_js(svg, axes_index, _sanitize_nan(entry)), self.on_complete)


def _live_update_js(svg_text, axes_index, pick_entry):
    """Swap #plotpress-svg's *children* for a fresh render and refresh that
    axes' embedded pick-data entry, in one round trip.

    Keeps the same outer <svg> node object alive rather than replacing it:
    the toolbar JS captures ``document.getElementById('plotpress-svg')``
    once into a closure at load time, so replacing the node itself would
    silently detach pan/zoom/pick from what's actually on screen after the
    first update. Two attributes on that node are deliberately left as they
    are rather than copied from the fresh render: ``id`` (obviously), and
    ``viewBox`` -- the toolbar's pan/zoom state lives in a JS closure variable
    captured once at load, not re-read from the DOM, so overwriting the
    live attribute out from under it would visually snap a panned/zoomed
    view back to home while leaving that JS state stale and now out of sync
    with what's on screen. User-placed pins (Point Picking markers, Annotation
    notes -- all rendered as direct <svg> children tagged
    ``plotpress-pin``, never part of the server-rendered SVG) are lifted out
    before the swap and reattached after, so a live update doesn't silently
    wipe them the way a full page reload already would. A pin's position is
    an SVG-user-space point, the same space pan/zoom moves it through, so it
    stays correct across pan/zoom; it is *not* re-anchored to its data
    coordinate if this update also changed that axes' limits (a growing-axis
    figure), the one case where a preserved pin can end up pointing at the
    wrong pixel for what it labeled.

    ``pick_entry`` must already be finite -- run it through
    :func:`plotpress.figure._sanitize_nan` first. A bare NaN/Infinity is a
    valid Python float but not valid JSON; ``json.dumps`` emits it as an
    unquoted token the browser's strict ``JSON.parse`` throws on, which would
    otherwise silently break *only* live-updated picking (the initial static
    payload already goes through this same sanitizing step).
    """
    return """
    (function() {
      var old = document.getElementById('plotpress-svg');
      if (!old) return false;
      var pins = [];
      for (var p = 0; p < old.children.length; p++) {
        if (old.children[p].classList.contains('plotpress-pin')) pins.push(old.children[p]);
      }
      var doc = new DOMParser().parseFromString(%s, 'image/svg+xml');
      var fresh = doc.documentElement;
      while (old.firstChild) old.removeChild(old.firstChild);
      while (fresh.firstChild) old.appendChild(fresh.firstChild);
      pins.forEach(function(pin) { old.appendChild(pin); });
      for (var i = 0; i < fresh.attributes.length; i++) {
        var a = fresh.attributes[i];
        if (a.name !== 'id' && a.name !== 'viewBox') old.setAttribute(a.name, a.value);
      }
      if (window.plotpressUpdatePick) window.plotpressUpdatePick(%d, %s);
      return true;
    })();
    """ % (json.dumps(svg_text), axes_index, json.dumps(json.dumps(pick_entry)))


def view(figure, title="plotpress", block=True, interactive=True,
         pick_precision=6):
    """Open ``figure`` in a standalone Qt window.

    Reuses the running ``QApplication`` if there is one (e.g. inside an existing
    app or an IPython Qt event loop); otherwise creates one. With ``block=True``
    (the default outside an existing app) the call blocks until the window
    closes. Returns the :class:`PlotPressWidget`.
    """
    app = _QT.QApplication.instance()
    owns_app = app is None
    if owns_app:
        _enable_webengine_gl()
        # sys.argv, not [] -- an empty argv leaves QtWebEngine's internal
        # base::CommandLine uninitialized ("the program name is not passed
        # to QCoreApplication"), which breaks every QWebEngineView this
        # QApplication ever creates, not just this one.
        app = _QT.QApplication(sys.argv)

    widget = PlotPressWidget(figure, interactive=interactive,
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
