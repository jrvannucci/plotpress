"""Regression for audit bug #3: post-tight_layout() tick/label mutations
left ``Figure._layout_dirty`` false, so ``_settle_layout()`` (the mechanism
``set_title()``/``set_xlabel()`` already relied on) never re-fit the grid --
a tick/label change made after ``tight_layout()`` rendered with a margin
still sized for whatever was true when ``tight_layout()`` ran, sometimes
placing a long new label mostly off the canvas.

Each of these setters can change how much margin ``tight_layout()`` needs
to reserve (a different tick count/width, a relabeled axis, moved to the
opposite edge, or a resized tick/label), so each must mark the layout dirty
the same way ``set_title()`` does.
"""

import plotpress


def _fresh_dirty_fig():
    """A figure that has already been laid out once (so ``_tight_pad`` is
    set and ``_settle_layout()`` would actually act on the dirty flag),
    with the flag itself freshly cleared."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    fig.tight_layout()
    assert fig._layout_dirty is False
    return fig, ax


def test_set_xticks_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_xticks([0, 0.5, 1])
    assert fig._layout_dirty is True


def test_set_yticks_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_yticks([0, 0.5, 1])
    assert fig._layout_dirty is True


def test_set_xticks_minor_does_not_mark_layout_dirty():
    """Minor ticks are unlabeled and never widen tight_layout()'s reserved
    margin (see figure.py's own ldec/bdec, which only ever read the major
    tick style) -- forcing a relayout for them would just be wasted work."""
    fig, ax = _fresh_dirty_fig()
    ax.set_xticks([0.25, 0.75], minor=True)
    assert fig._layout_dirty is False


def test_set_xticklabels_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_xticks([0, 1])
    fig.tight_layout()
    ax.set_xticklabels(["Long Category Name", "Another One"])
    assert fig._layout_dirty is True


def test_set_yticklabels_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_yticks([0, 1])
    fig.tight_layout()
    ax.set_yticklabels(["Long Category Name", "Another One"])
    assert fig._layout_dirty is True


def test_set_xlocator_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_xlocator({"kind": "multiple", "base": 0.25})
    assert fig._layout_dirty is True


def test_set_ylocator_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_ylocator({"kind": "multiple", "base": 0.25})
    assert fig._layout_dirty is True


def test_set_xformat_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_xformat("percent")
    assert fig._layout_dirty is True


def test_set_yformat_marks_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.set_yformat("percent")
    assert fig._layout_dirty is True


def test_tick_top_and_bottom_mark_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.tick_top()
    assert fig._layout_dirty is True

    fig2, ax2 = _fresh_dirty_fig()
    ax2.tick_bottom()
    assert fig2._layout_dirty is True


def test_tick_left_and_right_mark_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.tick_right()
    assert fig._layout_dirty is True

    fig2, ax2 = _fresh_dirty_fig()
    ax2.tick_left()
    assert fig2._layout_dirty is True


def test_tick_params_labelsize_and_length_mark_layout_dirty():
    fig, ax = _fresh_dirty_fig()
    ax.tick_params(labelsize=14)
    assert fig._layout_dirty is True

    fig2, ax2 = _fresh_dirty_fig()
    ax2.tick_params(length=10)
    assert fig2._layout_dirty is True


def test_tick_params_color_alone_does_not_mark_layout_dirty():
    """Color has no geometric effect on tight_layout()'s reserved margin --
    only labelsize/length/labelrotation do -- so it must not force a
    relayout of every panel in a grid just to recolor its ticks."""
    fig, ax = _fresh_dirty_fig()
    ax.tick_params(color="red", labelcolor="red")
    assert fig._layout_dirty is False


def test_set_axis_off_and_on_mark_layout_dirty():
    """tight_layout() skips an axis-off axes' ticks/labels entirely when
    sizing margins -- toggling it after a fit leaves stale, no-longer-
    needed (or missing) reserved space."""
    fig, ax = _fresh_dirty_fig()
    ax.set_axis_off()
    assert fig._layout_dirty is True

    fig2, ax2 = _fresh_dirty_fig()
    ax2.set_axis_off()
    fig2.tight_layout()
    ax2.set_axis_on()
    assert fig2._layout_dirty is True


def test_a_long_yticklabel_set_after_tight_layout_actually_refits():
    """End-to-end: not just the flag, but that a real render after the
    mutation reflows the margin instead of clipping the new label."""
    fig, ax = plotpress.subplots(figsize=(4, 4))
    ax.plot([0, 1], [0, 1])
    fig.tight_layout()
    narrow_left = ax._rect[0]

    ax.set_yticks([0, 1], labels=["short", "a very long category name here"])
    fig.to_svg()   # render triggers _settle_layout()
    wide_left = ax._rect[0]

    assert wide_left > narrow_left, (
        "a much wider y tick label set after tight_layout() must grow the "
        "left margin on the next render, not keep the stale, narrower fit")
