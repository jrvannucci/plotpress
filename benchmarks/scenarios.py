"""Shared benchmark scenarios comparing plotpress vs matplotlib.

Each scenario provides an ``plotpress`` builder and a matplotlib (``mpl``) builder.
Both do the same work: construct the figure *and serialize it to SVG*, so we
measure the whole "make the plot" cost, not just object creation.

Both sides use the object-oriented API (no pyplot) for a fair comparison.
Timings use ``time.perf_counter`` and report the best of N repeats to reduce
noise from GC and the OS scheduler.
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


def timeit(fn, repeat: int = 5) -> float:
    """Return the best wall-clock time (seconds) over ``repeat`` runs."""
    fn()  # warm up (imports, caches)
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


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


SCENARIOS = {
    "line_100k_points": {"plotpress": _plotpress_line, "mpl": _mpl_line},
    "scatter_5k_points": {"plotpress": _plotpress_scatter, "mpl": _mpl_scatter},
    "pcolormesh_300x300": {"plotpress": _plotpress_mesh, "mpl": _mpl_mesh},
    "many_axes_8x8_grid": {"plotpress": _plotpress_many_axes, "mpl": _mpl_many_axes},
}
