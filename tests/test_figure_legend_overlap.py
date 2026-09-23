"""Regression for audit bug #4: a large edge figure legend could overlap
the plot it was meant to sit beside.

``_layout_figure_legend`` reserved at most 60% of the figure for the
legend's edge band, but ``_render_figure_legend`` always draws the legend
at its own real, unshrunk size (``legend_box()``'s own computed
``box_h``/``box_w``) -- when a legend's actual footprint needed more than
that 60%, the axes only gave up 60% while the legend still drew its full
size, overlapping the axes by the difference. ``Figure.legend()``'s own
docstring promises the four named edges "reserve a band ... so the legend
never lands on a plot" -- the cap broke that promise for a large-enough
legend.
"""

import warnings

import numpy as np
import pytest

import plotpress
from plotpress.backends.svg import figure_legend_layout


def _figure_with_many_labeled_lines(n, figsize=(6.0, 6.0)):
    fig, ax = plotpress.subplots(figsize=figsize)
    x = np.linspace(0, 1, 5)
    for i in range(n):
        ax.plot(x, x + i, label=f"series {i}")
    return fig, ax


def test_a_large_bottom_legend_no_longer_overlaps_the_axes():
    fig, ax = _figure_with_many_labeled_lines(24)
    fig.legend(loc="lower center", ncol=1)
    fig.tight_layout()

    lay = figure_legend_layout(fig)
    W = fig.figsize[0] * fig.style.dpi
    H = fig.figsize[1] * fig.style.dpi
    pad_px = fig._figure_legend["pad"] * min(W, H) + 4
    needed_band = (lay["box_h"] + 2 * pad_px) / H

    left, bottom, w, h = ax._rect
    reserved_band = bottom   # fraction of H given to the legend below the axes
    assert reserved_band >= needed_band - 1e-9, (
        "the axes must give up at least as much room as the legend's own "
        "real (unshrunk) height actually needs, or the legend draws over "
        "the bottom of the axes")


def test_a_large_right_legend_no_longer_overlaps_the_axes():
    fig, ax = _figure_with_many_labeled_lines(24)
    fig.legend(loc="right", ncol=1)
    fig.tight_layout()

    lay = figure_legend_layout(fig)
    W = fig.figsize[0] * fig.style.dpi
    H = fig.figsize[1] * fig.style.dpi
    pad_px = fig._figure_legend["pad"] * min(W, H) + 4
    needed_band = (lay["box_w"] + 2 * pad_px) / W

    left, bottom, w, h = ax._rect
    reserved_band = 1.0 - (left + w)
    assert reserved_band >= needed_band - 1e-9


def test_a_small_legend_is_unaffected():
    """The ordinary case must not regress: a legend that easily fits still
    reserves the same band across a reflow as it always did (mirrors the
    project's own test_figure_legend_reservation_survives_a_reflow)."""
    fig, axes = plotpress.subplots(2, 2, figsize=(8.0, 5.0))
    for i, ax in enumerate(axes.ravel()):
        ax.plot([0, 1], [0, 1], label="sin")
        ax.plot([0, 1], [1, 0], label="cos")
    fig.tight_layout()
    fig.legend(loc="lower center")
    before = [tuple(a._rect) for a in axes.ravel()]
    fig.tight_layout()
    after = [tuple(a._rect) for a in axes.ravel()]
    assert after == before   # reservation survives a reflow, unchanged


def test_an_extreme_legend_warns_instead_of_silently_overflowing():
    """A legend so large it would need almost the entire figure is a real,
    if rare, degenerate case -- clamped to a safety ceiling with a clear
    warning, rather than either silently overlapping (the bug) or letting
    the axes shrink to nothing with no explanation."""
    fig, ax = _figure_with_many_labeled_lines(200)
    fig.legend(loc="lower center", ncol=1)
    with pytest.warns(UserWarning, match="needs about"):
        fig.tight_layout()

    # Clamped to the safety ceiling (plus whatever ordinary tick-label
    # margin already existed at that edge before the legend band stacked
    # on top of it) rather than left to consume the entire figure height.
    left, bottom, w, h = ax._rect
    assert h > 0.01


def test_a_legend_within_the_safety_ceiling_does_not_warn():
    fig, ax = _figure_with_many_labeled_lines(24)
    fig.legend(loc="lower center", ncol=1)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig.tight_layout()   # must not raise/warn
