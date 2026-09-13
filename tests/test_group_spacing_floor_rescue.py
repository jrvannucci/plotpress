"""Regression for audit bug #5: GroupLayout.group_spacing() could be
silently honored for only a fraction of the pixels actually requested.

A GroupLayout's supergrid dimension is the LCM of its groups' own inner
shapes, times the outer grid -- two groups as ordinary-looking as a 1x3
and a 1x4 side by side already reach a 1x24 supergrid. tight_layout()'s
own cell-floor rescue (_fit_cells) kicks in once a grid this dense can't
otherwise fit every column at its 2% floor, and used to shrink *every*
gap in the list proportionally to make room -- including group_spacing()'s
own explicit reservation, which the figure had already grown specifically
to hold. A caller asking for `wspace=42` to keep two group boxes from
touching could end up with well under half of it as real, visible gap --
silently defeating the one knob that exists specifically to prevent that
overlap.
"""

import plotpress


def _two_group_row(inner_a=3, inner_b=4):
    layout = plotpress.GroupLayout(1, 2)
    layout.add_group(0, 0, nrows=1, ncols=inner_a, title="A")
    layout.add_group(0, 1, nrows=1, ncols=inner_b, title="B")
    fig, groups = plotpress.subplots_from_groups(layout)
    for grp in groups:
        for ax in grp:
            ax.plot([0, 1], [0, 1])
    return fig, groups


def test_group_spacing_survives_the_cell_floor_rescue_on_a_dense_supergrid():
    """The reported case: a 1x3 and a 1x4 group (LCM supergrid = 1x24) is
    dense enough to trigger _fit_cells' floor rescue on its own, well
    before either group looks unusually large to a caller."""
    fig, groups = _two_group_row()
    fig.group_spacing(wspace=42.0)
    fig.tight_layout()

    W = fig.figsize[0] * fig.style.dpi
    last_a = groups[0][-1]
    first_b = groups[1][0]
    la, _, wa, _ = last_a._rect
    lb, _, _, _ = first_b._rect
    axes_gap_px = (lb - (la + wa)) * W

    assert axes_gap_px >= 42.0 - 1e-6, (
        "group_spacing()'s own documented contract is 'exactly this many "
        "pixels added on top of the ordinary gap' -- the rescue must never "
        "shrink the explicitly requested portion, only the ordinary "
        "tick-label-driven base gap")


def test_group_spacing_request_is_fully_reflected_in_figure_growth_and_gap():
    """The figure grows by exactly the requested pixels (unaffected by
    this bug either way) -- what broke was the *visible* gap not matching
    that growth once the rescue kicked in. Both must now agree."""
    fig, groups = _two_group_row()
    base_w = fig.figsize[0]
    fig.group_spacing(wspace=42.0)
    fig.tight_layout()

    grown_px = (fig.figsize[0] - base_w) * fig.style.dpi
    assert abs(grown_px - 42.0) < 1.0

    W = fig.figsize[0] * fig.style.dpi
    last_a = groups[0][-1]
    first_b = groups[1][0]
    la, _, wa, _ = last_a._rect
    lb, _, _, _ = first_b._rect
    axes_gap_px = (lb - (la + wa)) * W
    assert axes_gap_px >= 42.0 - 1.0


def test_ordinary_base_gap_still_shrinks_when_the_floor_is_hit():
    """The fix must not turn off the rescue altogether -- an *ordinary*
    (non-group-spacing) boundary on the same dense grid still needs to
    give way so every column keeps at least its floor width."""
    fig, groups = _two_group_row()
    fig.group_spacing(wspace=42.0)
    fig.tight_layout()

    # Two adjacent axes *inside* group A (an ordinary boundary, no
    # group_spacing on it) must still be squeezed close together --
    # nowhere near the 42px reserved only for the group-to-group seam.
    a0, a1 = groups[0][0], groups[0][1]
    W = fig.figsize[0] * fig.style.dpi
    l0, _, w0, _ = a0._rect
    l1, _, _, _ = a1._rect
    inner_gap_px = (l1 - (l0 + w0)) * W
    assert inner_gap_px < 20.0
