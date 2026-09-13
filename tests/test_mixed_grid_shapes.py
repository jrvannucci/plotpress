"""Regression for audit bug #6: Figure.add_subplot()/subplots() can be
called more than once on one figure, each call producing its own
independently-shaped grid -- a case the module's own docstrings already
described as supported (see figure.py's adopt_axes()). tight_layout() and
subplots_adjust() both assumed one shared (nrows, ncols) grid for the whole
figure, though, so mixing shapes used to reach _place_spec_rects' own
col_left/row_bottom arrays -- sized for just the first grid -- and crash
with a bare, uninformative IndexError instead of explaining what happened.
"""

import pytest

import plotpress


def _mixed_shape_figure():
    fig = plotpress.Figure()
    a = fig.add_subplot(1, 1, 1)
    a.plot([0, 1], [0, 1])
    b = fig.add_subplot(1, 2, 1)
    b.plot([0, 1], [1, 0])
    c = fig.add_subplot(1, 2, 2)
    c.plot([0, 1], [0, 0])
    return fig


def test_tight_layout_raises_a_clear_error_for_mixed_grid_shapes():
    fig = _mixed_shape_figure()
    with pytest.raises(ValueError, match="more than one independently-shaped grid"):
        fig.tight_layout()


def test_subplots_adjust_raises_a_clear_error_for_mixed_grid_shapes():
    fig = _mixed_shape_figure()
    with pytest.raises(ValueError, match="more than one independently-shaped grid"):
        fig.subplots_adjust(left=0.2)


def test_the_error_names_every_distinct_shape_present():
    fig = _mixed_shape_figure()
    with pytest.raises(ValueError, match=r"1x1, 1x2"):
        fig.tight_layout()


def test_a_single_grid_is_unaffected_regardless_of_call_count():
    """add_subplot() called multiple times for pieces of the *same* shape
    (nothing mismatched) must still work -- this only rejects a genuine
    shape mismatch, not multiple add_subplot() calls in general."""
    fig = plotpress.Figure()
    a = fig.add_subplot(1, 2, 1)
    a.plot([0, 1], [0, 1])
    b = fig.add_subplot(1, 2, 2)
    b.plot([0, 1], [1, 0])
    fig.tight_layout()   # must not raise
    fig.subplots_adjust(left=0.15)   # must not raise


def test_plain_subplots_grid_is_unaffected():
    fig, axes = plotpress.subplots(2, 3)
    for ax in axes.ravel():
        ax.plot([0, 1], [0, 1])
    fig.tight_layout()   # must not raise
