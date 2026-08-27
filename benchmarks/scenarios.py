"""Shared benchmark scenarios comparing plotpress, matplotlib, xy and plotly.

``SCENARIOS`` compares static-SVG output: a ``plotpress`` builder, a
matplotlib (``mpl``) builder, and, where the API allows an equivalent, an
``xy`` builder. Each builder does the same work -- construct the figure *and
serialize it to SVG* -- so the whole "make the plot" cost is measured, not
just object creation.

``HTML_SCENARIOS`` compares self-contained interactive HTML instead:
plotly has no native static-image path of its own (``fig.to_image()`` always
shells out to a real browser via ``kaleido``), so it is compared on the
output it *does* produce natively -- ``fig.to_html()`` -- against
``fig.to_html(interactive=True)`` on the plotpress side.

All builders use each library's own object-oriented API (no pyplot-style
globals) for a fair comparison. Timings use ``time.perf_counter`` and report
the best of N repeats to reduce noise from GC and the OS scheduler.
"""

from __future__ import annotations

import io
import time

import numpy as np

import plotpress

_RNG = np.random.default_rng(1234)


def has_matplotlib() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except Exception:
        return False


def has_xy() -> bool:
    """xy ships per-platform wheels, so it is simply absent on some machines."""
    try:
        import xy  # noqa: F401
        return True
    except Exception:
        return False


def has_plotly() -> bool:
    try:
        import plotly  # noqa: F401
        return True
    except Exception:
        return False


def timeit(fn, repeat: int = 5) -> float:
    """Return the best wall-clock time (seconds) over ``repeat`` runs."""
    fn()  # warm up (imports, caches)
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def _size_kib(result) -> float:
    """KiB of a builder's return value -- str or bytes, whichever it serialized to."""
    data = result.encode("utf-8") if isinstance(result, str) else result
    return len(data) / 1024.0


def timeit_and_size(fn, repeat: int = 5) -> tuple[float, float]:
    """Like :func:`timeit`, plus the output size (KiB) of the builder's own
    return value -- every builder here returns the serialized SVG/HTML it
    just built, so this is a free byproduct of a call already being made, not
    an extra render. Deterministic input data (see the module-level arrays
    above) means the size does not vary run to run, so one call suffices."""
    result = fn()  # warm up (imports, caches); also this run's size sample
    size = _size_kib(result)
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best, size


# --------------------------------------------------------------------------
# Data (generated once; shared by both backends so we time rendering only).
# --------------------------------------------------------------------------
_X_100K = np.linspace(0, 100, 100_000)
_Y_100K = np.sin(_X_100K) + 0.01 * _X_100K
_SCAT_X = _RNG.normal(size=5_000)
_SCAT_Y = _RNG.normal(size=5_000)
_MESH = np.sin(np.outer(np.linspace(0, 6, 300), np.linspace(0, 6, 300)))
_GRID_X = np.linspace(0, 10, 200)
_GRID_Y = np.sin(_GRID_X)


# --------------------------------------------------------------------------
# plotpress builders
# --------------------------------------------------------------------------
def _plotpress_line():
    fig, ax = plotpress.subplots()
    ax.plot(_X_100K, _Y_100K)
    return fig.to_svg()


def _plotpress_scatter():
    fig, ax = plotpress.subplots()
    ax.scatter(_SCAT_X, _SCAT_Y, s=4)
    return fig.to_svg()


def _plotpress_mesh():
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(_MESH)
    fig.colorbar(m, ax=ax)
    return fig.to_svg()


def _plotpress_many_axes():
    fig, axes = plotpress.subplots(8, 8, figsize=(16, 16))
    for ax in axes.ravel():
        ax.plot(_GRID_X, _GRID_Y)
    return fig.to_svg()


# --------------------------------------------------------------------------
# matplotlib builders (object-oriented, SVG canvas -- no pyplot globals)
# --------------------------------------------------------------------------
def _mpl_figure(figsize=(6.4, 4.8)):
    from matplotlib.backends.backend_svg import FigureCanvasSVG
    from matplotlib.figure import Figure as MFigure

    fig = MFigure(figsize=figsize)
    FigureCanvasSVG(fig)
    return fig


def _mpl_savefig(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="svg")
    return buf.getvalue()


def _mpl_line():
    fig = _mpl_figure()
    fig.add_subplot(111).plot(_X_100K, _Y_100K)
    return _mpl_savefig(fig)


def _mpl_scatter():
    fig = _mpl_figure()
    fig.add_subplot(111).scatter(_SCAT_X, _SCAT_Y, s=4)
    return _mpl_savefig(fig)


def _mpl_mesh():
    fig = _mpl_figure()
    ax = fig.add_subplot(111)
    m = ax.pcolormesh(_MESH)
    fig.colorbar(m, ax=ax)
    return _mpl_savefig(fig)


def _mpl_many_axes():
    fig = _mpl_figure(figsize=(16, 16))
    axes = fig.subplots(8, 8)
    for ax in axes.ravel():
        ax.plot(_GRID_X, _GRID_Y)
    return _mpl_savefig(fig)


# --------------------------------------------------------------------------
# xy builders (Rust core + WebGL client; to_svg() renders headlessly)
# --------------------------------------------------------------------------
# xy facets by a data column rather than by an arbitrary grid of axes, so the
# 8x8 case is expressed as 64 groups of one long-form table. That is the
# idiomatic equivalent, not a handicap.
_FACET = {
    "x": np.tile(_GRID_X, 64),
    "y": np.tile(_GRID_Y, 64),
    "panel": np.repeat(np.arange(64), _GRID_X.size),
}


def _xy_line():
    import xy
    return xy.chart(xy.line(_X_100K, _Y_100K)).to_svg()


def _xy_scatter():
    import xy
    return xy.chart(xy.scatter(_SCAT_X, _SCAT_Y, size=4)).to_svg()


def _xy_mesh():
    import xy
    return xy.chart(xy.heatmap(_MESH), xy.colorbar()).to_svg()


def _xy_many_axes():
    import xy
    return xy.facet_chart(xy.line("x", "y"), data=_FACET, by="panel", cols=8).to_svg()


SCENARIOS = {
    "line_100k_points": {"plotpress": _plotpress_line, "mpl": _mpl_line,
                         "xy": _xy_line},
    "scatter_5k_points": {"plotpress": _plotpress_scatter, "mpl": _mpl_scatter,
                          "xy": _xy_scatter},
    "pcolormesh_300x300": {"plotpress": _plotpress_mesh, "mpl": _mpl_mesh,
                           "xy": _xy_mesh},
    "many_axes_8x8_grid": {"plotpress": _plotpress_many_axes, "mpl": _mpl_many_axes,
                           "xy": _xy_many_axes},
}


# --------------------------------------------------------------------------
# plotly: compared on *interactive HTML*, not static SVG.
# --------------------------------------------------------------------------
# plotly has no native static-image serializer of its own -- ``fig.to_image()``
# always round-trips through a real, headless-browser layout/paint pipeline
# (the ``kaleido`` package), on *every call*, which measures a browser's
# cold-start cost (~3.5-5s here) far more than it measures rendering. Its
# native, in-process output is self-contained interactive HTML
# (``fig.to_html()``, plotly.js embedded), which is exactly what
# ``fig.to_html(interactive=True)`` is on the plotpress side -- so that is
# the fair like-for-like comparison, not the SVG one above.
def _plotpress_line_html():
    fig, ax = plotpress.subplots()
    ax.plot(_X_100K, _Y_100K)
    return fig.to_html(interactive=True)


def _plotpress_scatter_html():
    fig, ax = plotpress.subplots()
    ax.scatter(_SCAT_X, _SCAT_Y, s=4)
    return fig.to_html(interactive=True)


def _plotpress_mesh_html():
    fig, ax = plotpress.subplots()
    m = ax.pcolormesh(_MESH)
    fig.colorbar(m, ax=ax)
    return fig.to_html(interactive=True)


def _plotpress_many_axes_html():
    fig, axes = plotpress.subplots(8, 8, figsize=(16, 16))
    for ax in axes.ravel():
        ax.plot(_GRID_X, _GRID_Y)
    return fig.to_html(interactive=True)


def _plotly_line_html():
    import plotly.graph_objects as go
    fig = go.Figure(data=go.Scattergl(x=_X_100K, y=_Y_100K, mode="lines"))
    return fig.to_html()


def _plotly_scatter_html():
    import plotly.graph_objects as go
    fig = go.Figure(data=go.Scattergl(x=_SCAT_X, y=_SCAT_Y, mode="markers",
                                      marker=dict(size=4)))
    return fig.to_html()


def _plotly_mesh_html():
    import plotly.graph_objects as go
    fig = go.Figure(data=go.Heatmap(z=_MESH))
    return fig.to_html()


def _plotly_many_axes_html():
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=8, cols=8)
    for i in range(64):
        fig.add_trace(go.Scattergl(x=_GRID_X, y=_GRID_Y, mode="lines"),
                      row=i // 8 + 1, col=i % 8 + 1)
    return fig.to_html()


HTML_SCENARIOS = {
    "line_100k_points": {"plotpress": _plotpress_line_html, "plotly": _plotly_line_html},
    "scatter_5k_points": {"plotpress": _plotpress_scatter_html, "plotly": _plotly_scatter_html},
    "pcolormesh_300x300": {"plotpress": _plotpress_mesh_html, "plotly": _plotly_mesh_html},
    "many_axes_8x8_grid": {"plotpress": _plotpress_many_axes_html, "plotly": _plotly_many_axes_html},
}
