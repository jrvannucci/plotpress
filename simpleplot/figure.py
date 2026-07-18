"""The Figure: the root object that owns everything needed to render itself.

There is no global "current figure" or "current axes". A figure holds its own
axes, its own :class:`~simpleplot.style.Style`, and knows how to serialize itself to
SVG/HTML or show itself in a native pop-up window. Two figures never share
mutable state.
"""

from __future__ import annotations

import numpy as np

from .axes import Axes
from .style import Style
from .svg import figure_to_svg


class Figure:
    def __init__(self, figsize=(6.4, 4.8), style: Style = None, facecolor=None):
        self.figsize = tuple(figsize)
        self.style = (style or Style()).copy()
        if facecolor is not None:
            self.style.facecolor = facecolor
        self.axes: list[Axes] = []
        # Slider "units" -- each is one control bar. The global unit "main" is a
        # single bar driving all shared series; a docked unit ("ax<i>") sits
        # under one axes. Docked units may share a connection *index* so the UI
        # can offer a checkbox to link them.
        self._sliders = {}          # unit_id -> spec
        self._slider_index_n = {}   # connection index -> n_frames (validation)

        # Figure-level (global) text spanning all subplots.
        self._suptitle = None
        self._supxlabel = None
        self._supylabel = None

    def suptitle(self, text, size=None):
        """Set a global title centered across the whole figure."""
        self._suptitle = {"text": text, "size": size}

    def supxlabel(self, text, size=None):
        """Set a global x label centered along the bottom of the figure."""
        self._supxlabel = {"text": text, "size": size}

    def supylabel(self, text, size=None):
        """Set a global y label centered along the left of the figure."""
        self._supylabel = {"text": text, "size": size}

    def _register_slider(self, unit, index, n, values, label, is_global, axes_key):
        """Register (or validate) a slider unit and its connection index."""
        if unit in self._sliders:
            if self._sliders[unit]["n"] != n:
                raise ValueError(
                    f"plot_frames() series in slider unit {unit!r} must share "
                    f"n_frames (have {self._sliders[unit]['n']}, got {n})"
                )
            return
        if index is not None:
            if index in self._slider_index_n and self._slider_index_n[index] != n:
                raise ValueError(
                    f"plot_frames() series sharing slider index {index!r} must "
                    f"have the same n_frames (have {self._slider_index_n[index]}, "
                    f"got {n})"
                )
            self._slider_index_n[index] = n
        vals = ([float(v) for v in values] if values is not None
                else list(range(n)))
        if len(vals) != n:
            raise ValueError("slider_values length must equal n_frames")
        self._sliders[unit] = {
            "n": int(n), "values": vals, "label": label,
            "index": index, "global": bool(is_global), "axes": axes_key,
        }

    # -- axes construction --------------------------------------------------
    def add_axes(self, rect) -> Axes:
        """Add an axes at ``rect = (left, bottom, width, height)`` (fractions)."""
        ax = Axes(self, rect)
        self.axes.append(ax)
        return ax

    def add_subplot(self, nrows=1, ncols=1, index=1) -> Axes:
        ax = self.add_axes(_subplot_rect(nrows, ncols, index))
        ax._subplotspec = (nrows, ncols, index)
        return ax

    def subplots(self, nrows=1, ncols=1, squeeze=True, sharex=False, sharey=False):
        """Create a grid of axes; return a single Axes or a NumPy array of them.

        ``sharex``/``sharey`` link the grid so autoscaling spans every subplot
        (shared limits) and inner tick labels are hidden, like matplotlib.
        """
        grid = np.empty((nrows, ncols), dtype=object)
        for r in range(nrows):
            for c in range(ncols):
                index = r * ncols + c + 1
                ax = self.add_axes(_subplot_rect(nrows, ncols, index))
                ax._subplotspec = (nrows, ncols, index)
                grid[r, c] = ax

        axlist = grid.ravel().tolist()
        if sharex:
            for r in range(nrows):
                for c in range(ncols):
                    grid[r, c]._sharex_group = axlist
                    if r != nrows - 1:            # hide labels off the bottom row
                        grid[r, c].set_xticklabels([])
        if sharey:
            for r in range(nrows):
                for c in range(ncols):
                    grid[r, c]._sharey_group = axlist
                    if c != 0:                    # hide labels off the left column
                        grid[r, c].set_yticklabels([])

        if not squeeze:
            return grid
        if nrows == 1 and ncols == 1:
            return grid[0, 0]
        if nrows == 1 or ncols == 1:
            return grid.ravel()
        return grid

    def tight_layout(self, pad=0.02):
        """Auto-fit subplot margins so ticks/labels/titles never overflow.

        Measures each axes' decorations with the bundled font metrics and
        re-lays-out the subplot grid. Call it *before* ``colorbar`` (colorbars
        are positioned relative to their parent's rect).
        """
        from .fonts import text_width
        from .ticker import format_ticks, log_ticks, nice_ticks

        st = self.style
        Wpx = self.figsize[0] * st.dpi
        Hpx = self.figsize[1] * st.dpi
        specs = [ax for ax in self.axes
                 if ax._subplotspec is not None and not ax._is_colorbar]
        if not specs:
            return self
        nrows, ncols = specs[0]._subplotspec[0], specs[0]._subplotspec[1]

        left_px = bottom_px = top_px = right_px = 0.0
        for ax in specs:
            if ax._title:
                top_px = max(top_px, st.title_size + 8)
            if ax._axis_off:
                continue
            (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
            yt = (ax._yticks if ax._yticks is not None else
                  (log_ticks(ymin, ymax) if ax._yscale == "log" else nice_ticks(ymin, ymax)))
            ytw = max((text_width(l, st.tick_label_size) for l in format_ticks(yt)),
                      default=0.0)
            ldec = st.tick_size + ytw + 4
            if ax._ylabel:
                ldec += st.label_size + 6
            left_px = max(left_px, ldec)
            bdec = st.tick_size + st.tick_label_size + 4
            if ax._xlabel:
                bdec += st.label_size + 6
            bottom_px = max(bottom_px, bdec)
            right_px = max(right_px, st.tick_label_size * 0.6)  # last x label overhang

        # Figure-level titles/labels add their own bands.
        if self._suptitle:
            top_px += (self._suptitle.get("size") or st.title_size * 1.5) + 6
        if self._supxlabel:
            bottom_px += (self._supxlabel.get("size") or st.label_size * 1.2) + 6
        if self._supylabel:
            left_px += (self._supylabel.get("size") or st.label_size * 1.2) + 6

        edge = pad * min(Wpx, Hpx) + 4
        left = (left_px + edge) / Wpx
        right = 1 - (right_px + edge) / Wpx
        bottom = (bottom_px + edge) / Hpx
        top = 1 - (top_px + edge) / Hpx
        gap_w = left_px / Wpx                       # interior column gap
        gap_h = (bottom_px + top_px) / Hpx          # interior row gap
        axw = (right - left - (ncols - 1) * gap_w) / max(ncols, 1)
        axh = (top - bottom - (nrows - 1) * gap_h) / max(nrows, 1)
        axw = max(axw, 0.02)
        axh = max(axh, 0.02)

        for ax in specs:
            idx = ax._subplotspec[2] - 1
            row, col = idx // ncols, idx % ncols
            ax._rect = (left + col * (axw + gap_w),
                        bottom + (nrows - 1 - row) * (axh + gap_h), axw, axh)
        return self

    # -- colorbar -----------------------------------------------------------
    def colorbar(self, mappable, ax, fraction=0.05, pad=0.02) -> Axes:
        """Add a colorbar for ``mappable``.

        ``ax`` may be a single :class:`~simpleplot.axes.Axes` (the colorbar
        steals space from it) or a list / array of axes (one **shared** colorbar
        spanning them all, placed on their right -- the grid is squeezed to make
        room). All the axes should share the mappable's ``vmin``/``vmax`` for the
        shared bar to describe them accurately.
        """
        axlist = _flatten_axes(ax)
        if len(axlist) == 1:
            left, bottom, w, h = axlist[0]._rect
            cbar_w = w * fraction
            axlist[0]._rect = (left, bottom, w * (1 - fraction - pad), h)
            cax = self.add_axes((left + w * (1 - fraction), bottom, cbar_w, h))
        else:
            rects = np.array([a._rect for a in axlist])
            gl, gb = rects[:, 0].min(), rects[:, 1].min()
            gr = (rects[:, 0] + rects[:, 2]).max()
            gt = (rects[:, 1] + rects[:, 3]).max()
            span_w = gr - gl
            cbar_w = span_w * fraction
            scale = (span_w - span_w * (fraction + pad)) / span_w
            for a in axlist:                       # squeeze the group leftward
                left, bottom, w, h = a._rect
                a._rect = (gl + (left - gl) * scale, bottom, w * scale, h)
            cax = self.add_axes((gr - cbar_w, gb, cbar_w, gt - gb))
        cax._is_colorbar = True
        cax._cbar_source = mappable
        return cax

    # -- serialization ------------------------------------------------------
    def to_svg(self) -> str:
        return figure_to_svg(self)

    def _repr_svg_(self) -> str:
        # Static inline SVG is the Jupyter default; use to_html for interactive.
        return figure_to_svg(self)

    def to_html(self, interactive: bool = True, wait_extract: bool = False,
                pick_precision: int = 6) -> str:
        """Serialize to a self-contained HTML document.

        ``pick_precision`` sets the decimal places of the embedded point-pick
        arrays (the mesh z grids dominate the file size for mesh-heavy figures);
        lower it to shrink the HTML at the cost of readout precision.
        """
        svg = figure_to_svg(self)
        # Tag the root <svg> so the JS can grab it.
        svg = svg.replace("<svg ", '<svg id="simpleplot-svg" ', 1)
        script = ""
        if interactive:
            import json

            from ._interactive import INTERACTIVE_JS
            from .svg import axes_metadata, frame_data, pick_data, style_payload

            meta = json.dumps(axes_metadata(self))
            pick = json.dumps(pick_data(self, precision=pick_precision))
            styl = json.dumps(style_payload(self))
            payloads = (
                f'<script type="application/json" id="simpleplot-meta">{meta}</script>'
                f'<script type="application/json" id="simpleplot-pick">{pick}</script>'
                f'<script type="application/json" id="simpleplot-style">{styl}</script>'
            )
            if self._sliders:
                frames = json.dumps(frame_data(self))
                sliders = json.dumps(self._sliders)
                payloads += (
                    f'<script type="application/json" id="simpleplot-frames">{frames}</script>'
                    f'<script type="application/json" id="simpleplot-sliders">{sliders}</script>'
                )
            config = ("<script>window.SIMPLEPLOT_WAIT_EXTRACT=true;</script>"
                      if wait_extract else "")
            script = config + payloads + f"<script>{INTERACTIVE_JS}</script>"
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>body{margin:0;background:#f5f5f5;display:flex;"
            "justify-content:center;align-items:center;min-height:100vh}"
            "#simpleplot-svg{cursor:default;box-shadow:0 1px 6px rgba(0,0,0,.2)}"
            "</style></head><body>"
            f"{svg}{script}</body></html>"
        )

    # NB: intentionally *no* _repr_html_. Jupyter prefers text/html over
    # image/svg+xml, and returning a full interactive HTML document renders
    # messily in an output cell (and its scripts don't run there). Notebooks
    # therefore fall back to the clean static SVG above; for an interactive
    # figure in a notebook, embed to_html() in an <iframe> (see the docs).

    def save(self, path: str, interactive: bool = False, scale: int = 2,
             pick_precision: int = 6):
        """Save by extension: ``.svg``, ``.html``, ``.png``, or ``.pdf``.

        All formats work with the standard install (PNG is a supersampled
        raster; PDF is vector). ``pick_precision`` applies only to interactive
        HTML (see :meth:`to_html`).
        """
        lower = path.lower()
        if lower.endswith(".html") or lower.endswith(".htm"):
            content = self.to_html(interactive=interactive,
                                   pick_precision=pick_precision)
        elif lower.endswith(".svg"):
            content = self.to_svg()
        elif lower.endswith(".png"):
            from .raster import save_png
            return save_png(self, path, scale=scale)
        elif lower.endswith(".pdf"):
            from .raster import save_pdf
            return save_pdf(self, path)
        else:
            raise ValueError("save() supports .svg/.html/.png/.pdf (got %r)" % path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def savefig(self, path, **kwargs):
        """Alias for :meth:`save` (matplotlib-compatible name)."""
        return self.save(path, **kwargs)

    # -- display ------------------------------------------------------------
    def show(self, interactive: bool = True, wait_for_extract: bool = False):
        """Display in a native pop-up window (via pywebview if installed).

        Returns the list of markers the user extracted in the window (each a
        dict of values: ``x``, ``y``, any extra dims, ``axes``, ``kind``), or
        an empty list if none were extracted.

        With ``wait_for_extract=True`` the call becomes an interactive point-
        picking session: the kernel blocks, the user drops markers and clicks
        **Extract**, and *that* returns the markers to the kernel and closes the
        window (no manual close needed).

        The native window needs the ``[gui]`` extra
        (``pip install simpleplot[gui]``). Without it, this falls back to opening
        the figure in the default browser and returns ``None`` (use the in-page
        Extract panel to copy/download).
        """
        html = self.to_html(interactive=interactive, wait_extract=wait_for_extract)
        w = int(self.figsize[0] * self.style.dpi) + 40
        h = int(self.figsize[1] * self.style.dpi) + 60
        try:
            import webview  # provided by the [gui] extra (pywebview)
        except ImportError:
            if wait_for_extract:
                raise RuntimeError(
                    "wait_for_extract=True needs the native window; install it "
                    "with: pip install simpleplot[gui]"
                )
            import os
            import tempfile
            import webbrowser

            fd, name = tempfile.mkstemp(suffix=".html")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(html)
            webbrowser.open("file://" + os.path.abspath(name))
            return None

        api = _MarkerApi()
        window = webview.create_window("simpleplot", html=html, js_api=api,
                                       width=w, height=h)
        if wait_for_extract:
            api._window = window   # Extract closes the window -> unblocks below
        webview.start()
        return api.markers

    def show_qt(self, title="simpleplot", block=True, interactive=True,
                pick_precision=6):
        """Display in a native Qt window (PyQt/PySide), for Qt-based apps.

        Thin wrapper around ``simpleplot.qt.view``. Needs a Qt binding with
        WebEngine (``pip install simpleplot[qt]``). To embed the figure inside
        your own Qt layout instead of a standalone window, use
        ``simpleplot.qt.SimplePlotWidget`` directly.
        """
        from .qt import view
        return view(self, title=title, block=block, interactive=interactive,
                    pick_precision=pick_precision)


class _MarkerApi:
    """pywebview bridge: the in-window Extract button pushes markers to Python."""

    def __init__(self):
        self.markers = []
        self._window = None   # set when Extract should also close the window

    def extract(self, records):
        # Called from JS as window.pywebview.api.extract(records).
        self.markers = list(records) if records else []
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
        return True


def _flatten_axes(ax):
    """Normalize a single Axes / list / ndarray of axes to a flat list."""
    if isinstance(ax, Axes):
        return [ax]
    return [a for a in np.asarray(ax, dtype=object).ravel()]


def subplots(nrows=1, ncols=1, figsize=(6.4, 4.8), style: Style = None,
             facecolor=None, squeeze=True, sharex=False, sharey=False):
    """Convenience constructor mirroring ``matplotlib.pyplot.subplots``.

    Unlike matplotlib, this creates and returns a fresh, fully independent
    figure -- there is no global state touched. ``sharex``/``sharey`` link the
    grid's limits and hide inner tick labels.
    """
    fig = Figure(figsize=figsize, style=style, facecolor=facecolor)
    axes = fig.subplots(nrows, ncols, squeeze=squeeze, sharex=sharex, sharey=sharey)
    return fig, axes


def _subplot_rect(nrows, ncols, index):
    """Compute an axes rect for a 1-based subplot ``index`` in an NxM grid."""
    left, right, bottom, top = 0.125, 0.9, 0.11, 0.88
    wspace, hspace = 0.2, 0.2
    avail_w = right - left
    avail_h = top - bottom
    axw = avail_w / (ncols + wspace * (ncols - 1))
    axh = avail_h / (nrows + hspace * (nrows - 1))

    idx = index - 1
    row = idx // ncols
    col = idx % ncols
    ax_left = left + col * axw * (1 + wspace)
    ax_bottom = bottom + (nrows - 1 - row) * axh * (1 + hspace)
    return (ax_left, ax_bottom, axw, axh)
