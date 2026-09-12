"""GroupLayout / subplots_from_groups() / Figure.get_groups()/get_group()/
get_ax() / Axes.set_id()/get_id().

Assumption under test throughout: a GroupLayout-built figure is completely
ordinary once built -- every axes has one flat SubplotSpec in one shared
grid, so tight_layout()/align_xlabels()/subplots_adjust()/to_vega()/
to_vega_lite() all keep working unmodified. Several tests below exist
specifically to pin that claim down, not just exercise the new API.
"""
import io
import warnings

import numpy as np
import pytest

import plotpress
from plotpress.figure import GroupLayout, SubplotSpec


def test_equal_shaped_groups_tile_a_clean_super_grid():
    """Four 2x2 groups over a 2x2 outer arrangement -- the running example
    from the design -- resolve onto one flat 4x4 grid with no remainder."""
    layout = GroupLayout(2, 2)
    layout.add_group(0, 0, 2, 2, title="A")
    layout.add_group(0, 1, 2, 2, title="B")
    layout.add_group(1, 0, 2, 2, title="C")
    layout.add_group(1, 1, 2, 2, title="D")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(10, 8))

    assert axes.shape == (2, 2)
    assert axes[0, 0].shape == (2, 2)
    all_axes = [ax for cell in axes.ravel() for ax in cell.ravel()]
    assert len(all_axes) == 16
    assert len(set(id(ax) for ax in all_axes)) == 16   # every axes distinct

    specs = [ax._subplotspec for ax in all_axes]
    assert all(s.nrows == 4 and s.ncols == 4 for s in specs)
    # No two axes overlap: every (row0,col0) pair is unique.
    origins = [(s.row0, s.col0) for s in specs]
    assert len(set(origins)) == 16


def test_uneven_inner_shapes_span_the_shared_lcm_grid():
    """A 2x1 group and a 1x3 group sharing the same outer row: the taller,
    narrower one's cells must each span 3 super-rows (LCM(2,1)*... ) to
    physically cover the same height as the other's single row -- spans,
    not a rebuilt-per-group height."""
    layout = GroupLayout(1, 2)
    layout.add_group(0, 0, 2, 1)
    layout.add_group(0, 1, 1, 3)
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(10, 4))

    assert axes[0].shape == (2,)
    assert axes[1].shape == (3,)
    left_specs = [ax._subplotspec for ax in axes[0]]
    right_specs = [ax._subplotspec for ax in axes[1]]
    nrows = left_specs[0].nrows
    assert nrows == 2   # LCM(2, 1) = 2 super-rows
    assert all(s.nrows == nrows for s in left_specs + right_specs)
    # The left group's two cells are each one super-row tall, stacked.
    assert sorted((s.row0, s.row1) for s in left_specs) == [(0, 0), (1, 1)]
    # The right group's three cells each span *both* super-rows, to
    # physically cover the same total height as the left group's two
    # stacked cells.
    assert all((s.row0, s.row1) == (0, 1) for s in right_specs)


def test_mask_leaves_a_hole_with_no_axes():
    """A 3x3 mask with the center cell False -- a ring with a hole --
    creates 8 real axes, and the masked-out cell is None, not an axes."""
    layout = GroupLayout(1, 1)
    mask = [[True, True, True], [True, False, True], [True, True, True]]
    layout.add_group(0, 0, mask=mask, title="Ring")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(8, 8))

    inner = axes  # 1x1 outer -> squeezed straight to the one group's array
    assert inner.shape == (3, 3)
    assert inner[1, 1] is None
    present = [ax for ax in inner.ravel() if ax is not None]
    assert len(present) == 8
    for ax in present:
        ax.plot([0, 1], [0, 1])   # every real cell is a usable Axes
    fig.tight_layout()
    fig.to_svg()   # must render without error


def test_mask_shape_inferred_when_nrows_ncols_omitted():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, mask=[[True, False], [True, True]])
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 6))
    assert axes.shape == (2, 2)
    assert axes[0, 1] is None


def test_mask_matching_explicit_nrows_ncols_is_accepted():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, 2, 2, mask=[[True, True], [True, False]])
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 6))
    assert axes.shape == (2, 2)
    assert axes[1, 1] is None


def test_mask_mismatched_with_explicit_nrows_ncols_raises():
    layout = GroupLayout(1, 1)
    with pytest.raises(ValueError, match="nrows=3"):
        layout.add_group(0, 0, 3, 2, mask=[[True, True], [True, False]])


def test_all_false_mask_raises():
    layout = GroupLayout(1, 1)
    with pytest.raises(ValueError, match="no present cells"):
        layout.add_group(0, 0, mask=[[False, False]])


def test_outer_cell_out_of_bounds_raises():
    layout = GroupLayout(2, 2)
    with pytest.raises(ValueError, match=r"\(2, 0\)"):
        layout.add_group(2, 0, 1, 1)


def test_reassigning_an_outer_cell_raises():
    layout = GroupLayout(1, 2)
    layout.add_group(0, 0, 1, 1)
    with pytest.raises(ValueError, match="already has a group"):
        layout.add_group(0, 0, 1, 1)


def test_empty_layout_raises_a_clear_error():
    layout = GroupLayout(2, 2)
    with pytest.raises(ValueError, match="no groups"):
        plotpress.subplots_from_groups(layout)


def test_unset_outer_cells_are_none():
    layout = GroupLayout(2, 2)
    layout.add_group(0, 0, 1, 1)
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 6))
    assert axes[0, 1] is None and axes[1, 0] is None and axes[1, 1] is None


def test_title_none_places_axes_without_registering_a_group():
    layout = GroupLayout(1, 2)
    layout.add_group(0, 0, 1, 1, title="Named")
    layout.add_group(0, 1, 1, 1, title=None)
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 3))
    groups = fig.get_groups()
    assert len(groups) == 1
    assert groups[0].title == "Named"


def test_id_without_title_raises():
    layout = GroupLayout(1, 1)
    with pytest.raises(ValueError, match="id= needs title= too"):
        layout.add_group(0, 0, 1, 1, id="only-an-id")


def test_sharex_sharey_link_within_a_group_and_hide_inner_tick_labels():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, 2, 2)
    fig, axes = plotpress.subplots_from_groups(
        layout, figsize=(6, 6), sharex=True, sharey=True)
    grid = axes  # 1x1 outer squeezes to the one 2x2 inner array
    for ax in grid.ravel():
        ax.plot([0, 1], [0, 1])
    # Bottom row keeps x labels, top row's are hidden; left column keeps y
    # labels, right column's are hidden -- same rule Figure.subplots() uses.
    assert grid[0, 0]._xticklabels == []
    assert grid[1, 0]._xticklabels is None
    assert grid[0, 1]._yticklabels == []
    assert grid[0, 0]._yticklabels is None


def test_sharex_sharey_respect_an_irregular_mask():
    """The "last row"/"first col" that keeps its tick labels is whichever
    present cell is actually last/first for its column/row -- not
    necessarily the mask's own last index, when the true edge cell is
    masked out."""
    layout = GroupLayout(1, 1)
    # Column 0's last present row is 0 (row 1 is masked out) -- that's the
    # one that must keep its x tick labels, not row 1 (which doesn't exist).
    layout.add_group(0, 0, mask=[[True, True], [False, True]])
    fig, axes = plotpress.subplots_from_groups(
        layout, figsize=(6, 6), sharex=True, sharey=True)
    grid = axes
    assert grid[0, 1] is not None and grid[1, 0] is None and grid[1, 1] is not None
    grid[0, 0]._xticklabels = None  # reset before asserting our own axes only
    # Column 0: only row 0 is present -> it must be the one keeping labels.
    assert grid[0, 0]._xticklabels != []
    # Row 0: column 0's present cell (0,0) is left of column 1 -> row 0's
    # y-label-keeper is (0,0), so (0,1) must have its y labels hidden.
    assert grid[0, 1]._yticklabels == []


def test_one_by_one_layout_squeezes_to_a_bare_group_array():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, 2, 2, title="Only")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 6))
    assert isinstance(axes, np.ndarray) and axes.shape == (2, 2)


def test_squeeze_false_keeps_the_full_2d_outer_and_inner_arrays():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, 1, 1, title="Only")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 6), squeeze=False)
    assert axes.shape == (1, 1)
    assert axes[0, 0].shape == (1, 1)


def test_get_groups_returns_a_snapshot_not_a_live_view():
    fig, ax = plotpress.subplots()
    fig.group("g", [ax])
    snap = fig.get_groups()
    snap[0].axes.append("not a real axes")
    assert len(fig.get_groups()[0].axes) == 1


def test_get_groups_works_for_a_plain_manual_group_too():
    """get_groups() isn't GroupLayout-specific -- it reads whatever group()
    already recorded, built via subplots_from_groups or a bare group() call."""
    fig, axes = plotpress.subplots(2, 2)
    fig.group("Left", [axes[0, 0], axes[1, 0]])
    groups = fig.get_groups()
    assert len(groups) == 1
    assert groups[0].title == "Left"
    assert groups[0].axes == [axes[0, 0], axes[1, 0]]
    assert groups[0].outer_row is None and groups[0].outer_col is None


def test_group_layout_figure_survives_tight_layout_align_and_subplots_adjust():
    """The core architectural claim: nothing downstream needs to know the
    figure was built this way."""
    layout = GroupLayout(2, 2)
    for r in range(2):
        for c in range(2):
            layout.add_group(r, c, 2, 2, title=f"G{r}{c}")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(10, 8))
    for cell in axes.ravel():
        for ax in cell.ravel():
            ax.plot([0, 1], [0, 1])
            ax.set_xlabel("x")
            ax.set_ylabel("y")

    fig.align_xlabels()
    fig.align_ylabels()
    fig.subplots_adjust(wspace=0.3, hspace=0.3)
    fig.group_spacing(wspace=10, hspace=10)
    fig.tight_layout()
    svg = fig.to_svg()
    assert "<svg" in svg


def test_group_layout_figure_exports_to_vega_and_vega_lite_as_one_grid():
    layout = GroupLayout(2, 2)
    for r in range(2):
        for c in range(2):
            layout.add_group(r, c, 2, 2, title=f"G{r}{c}")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(10, 8))
    for cell in axes.ravel():
        for ax in cell.ravel():
            ax.plot([0, 1], [0, 1])

    vega_spec = fig.to_vega()
    assert vega_spec["marks"]
    vl_spec, caveats = fig.to_vega_lite()
    grid = vl_spec["grid"]
    assert grid is not None and ("hconcat" in grid or "vconcat" in grid)
    assert vl_spec["standalone"] == []
    assert caveats == []


def test_to_vega_group_marks_handle_empty_hidden_and_twin_cases():
    """_groups_to_vega_marks() is a "direct port" of svg.py's own group-box
    rendering (its own docstring), but never got three fixes svg.py already
    has: skipping a visible=False group, falling back to the frozen rect
    for a group with zero real members left (a bare min()/max() over an
    empty list previously crashed outright -- found by exercising this via
    the new tight_layout(collapse=...) gallery example), and auto-including
    a member's own twin/secondary overlay (and any colorbar attached to
    one) the same way svg._group_bbox does."""
    # Empty group (frozen_rect) must not crash and must use the frozen box.
    fig, axes = plotpress.subplots(1, 2)
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    fig.group("G", [axes[0]])
    axes[0].remove()
    fig.tight_layout()   # collapse=None -- group freezes, doesn't disappear
    spec = fig.to_vega()   # must not raise
    [rect] = [m for m in spec["marks"] if m["name"] == "group0"]
    fx0, fy0, fx1, fy1 = fig.get_groups()[0]._raw["frozen_rect"]
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    assert rect["encode"]["enter"]["x"]["value"] == round(fx0 * W, 2)
    assert rect["encode"]["enter"]["y"]["value"] == round(fy0 * H, 2)

    # visible=False must be skipped entirely, same as the SVG backend.
    fig2, ax2 = plotpress.subplots()
    ax2.plot([0, 1], [0, 1])
    fig2.group("Hidden", [ax2], visible=False)
    spec2 = fig2.to_vega()
    assert not any(m["name"].startswith("group") for m in spec2["marks"])

    # A twin's own decoration widens the box, same as svg.py's own fix.
    fig3, ax3 = plotpress.subplots()
    ax3.plot([0, 1], [0, 1])
    twin = ax3.twinx()
    twin.plot([0, 1], [1, 0])
    twin.set_ylabel("twin")
    fig3.group("G3", [ax3])
    fig3.tight_layout()
    fig4, ax4 = plotpress.subplots()
    ax4.plot([0, 1], [0, 1])
    fig4.group("G4", [ax4])
    fig4.tight_layout()
    width_with_twin = [m for m in fig3.to_vega()["marks"]
                       if m["name"] == "group0"][0]["encode"]["enter"]["width"]["value"]
    width_without_twin = [m for m in fig4.to_vega()["marks"]
                          if m["name"] == "group0"][0]["encode"]["enter"]["width"]["value"]
    assert width_with_twin > width_without_twin


def test_incompatible_shapes_warn_and_still_leave_gaps_at_modest_scale():
    """Regression: mixing shapes whose LCM pushes the shared grid past
    tight_layout()'s cell-size floor (~40 rows/cols) used to silently zero
    out every row/column gap, including group_spacing()'s own deliberate
    reservation -- rendering as groups overlapping rather than a warned,
    explainable sizing problem. Groups sharing a small common multiple
    (this test) must not warn and must still get a real, non-zero gap;
    the large-LCM case is covered separately below."""
    layout = GroupLayout(1, 2)
    layout.add_group(0, 0, 2, 2, title="A")
    layout.add_group(0, 1, 4, 4, title="B")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig, axes = plotpress.subplots_from_groups(layout, figsize=(10, 5))
    for cell in axes:
        for ax in np.atleast_1d(cell).ravel():
            ax.plot([0, 1], [0, 1])
    fig.group_spacing(wspace=20.0)
    fig.tight_layout()

    a_axes = fig.get_groups()[0].flat_axes()
    b_axes = fig.get_groups()[1].flat_axes()
    a_right = max(ax._rect[0] + ax._rect[2] for ax in a_axes)
    b_left = min(ax._rect[0] for ax in b_axes)
    assert b_left - a_right > 0.001, (
        "group_spacing() must still produce a real, non-zero gap between "
        "groups at this modest scale: %r vs %r" % (a_right, b_left))


def test_large_lcm_from_mixed_shapes_warns():
    """The actual bug reported: 2/5/3-column groups together need
    lcm(2, 5, 3) = 30 per outer cell; 3 outer columns pushes the shared
    grid to 90 columns, well past the warning threshold -- the exact
    shape of the dashboard example that first surfaced this."""
    layout = GroupLayout(1, 3)
    layout.add_group(0, 0, 2, 2)
    layout.add_group(0, 1, 1, 5)
    layout.add_group(0, 2, 1, 3)
    with pytest.warns(UserWarning, match="shared 2x90 grid"):
        plotpress.subplots_from_groups(layout, figsize=(15, 5))


def test_projection_polar_is_forwarded_to_every_inner_axes():
    from plotpress.polar import PolarAxes

    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, 1, 2)
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(8, 4),
                                               projection="polar")
    assert all(isinstance(ax, PolarAxes) for ax in axes)


# ---------------------------------------------------------------------------
# axes_ids / axes_titles -- mosaic-style presence + identity in one array.
# ---------------------------------------------------------------------------

def test_axes_ids_establish_presence_and_set_each_axes_own_id():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, axes_ids=[["a", None], [None, "b"]], title="Diag")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 6))
    assert axes[0, 1] is None and axes[1, 0] is None
    assert axes[0, 0].get_id() == "a"
    assert axes[1, 1].get_id() == "b"


def test_axes_titles_establish_presence_and_set_each_axes_own_title():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, axes_titles=[["left", "right"]], title="Row")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 3))
    assert axes[0].get_title() == "left"
    assert axes[1].get_title() == "right"


def test_mask_and_axes_ids_agreeing_is_accepted():
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, mask=[[True, False]], axes_ids=[["a", None]], title="G")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 3))
    assert axes[0].get_id() == "a"
    assert axes[1] is None


def test_mask_and_axes_ids_disagreeing_raises():
    layout = GroupLayout(1, 1)
    with pytest.raises(ValueError, match=r"disagree on whether cell \(0, 0\)"):
        layout.add_group(0, 0, mask=[[False, True]], axes_ids=[["a", None]])


def test_axes_ids_and_axes_titles_disagreeing_raises():
    layout = GroupLayout(1, 1)
    with pytest.raises(ValueError, match="axes_titles and axes_ids disagree"):
        layout.add_group(0, 0, axes_ids=[["a", None]], axes_titles=[[None, "b"]])


# ---------------------------------------------------------------------------
# Group/get_group()/get_ax() lookups.
# ---------------------------------------------------------------------------

def _four_quadrants():
    layout = GroupLayout(2, 2)
    layout.add_group(0, 0, 2, 2, title="Group (0,0)", id="g00")
    layout.add_group(0, 1, 2, 2, title="Group (0,1)")
    layout.add_group(1, 0, 2, 2, title="Group (1,0)")
    layout.add_group(1, 1, 2, 2, title="Group (1,1)")
    return plotpress.subplots_from_groups(layout, figsize=(9, 8))


def test_get_group_by_title_id_and_outer_position():
    fig, axes = _four_quadrants()
    by_title = fig.get_group(title="Group (0,0)")
    by_id = fig.get_group(id="g00")
    by_pos = fig.get_group(row=0, col=0)
    assert by_title.title == by_id.title == by_pos.title == "Group (0,0)"
    assert by_title.outer_row == 0 and by_title.outer_col == 0


def test_get_group_not_found_and_ambiguous_raise():
    fig, axes = _four_quadrants()
    with pytest.raises(ValueError, match="no group matches"):
        fig.get_group(title="nope")
    with pytest.raises(ValueError, match="pass exactly one"):
        fig.get_group()
    with pytest.raises(ValueError, match="pass both row= and col="):
        fig.get_group(row=0)


def test_group_get_ax_by_inner_position_title_and_id():
    fig, axes = _four_quadrants()
    g = fig.get_group(title="Group (0,0)")
    ax = g.get_ax(row=1, col=1)
    assert ax is axes[0, 0][1, 1]
    ax.set_id("br")
    ax.set_title("bottom right")
    assert g.get_ax(id="br") is ax
    assert g.get_ax(title="bottom right") is ax
    assert fig.get_ax(id="br") is ax


def test_group_get_ax_rowcol_on_shapeless_manual_group_raises():
    fig, ax = plotpress.subplots()
    fig.group("g", [ax])
    g = fig.get_group(title="g")
    with pytest.raises(ValueError, match="no inner grid shape"):
        g.get_ax(row=0, col=0)


def test_fig_get_ax_many_true_collects_every_match():
    fig, axes = _four_quadrants()
    for cell in axes.ravel():
        cell[0, 0].set_title("corner")
    with pytest.raises(ValueError, match=r"4 axes match title='corner'"):
        fig.get_ax(title="corner")
    found = fig.get_ax(title="corner", many=True)
    assert len(found) == 4


def test_fig_get_ax_rowcol_zero_is_not_treated_as_missing():
    fig, ax = plotpress.subplots(2, 2)
    found = fig.get_ax(row=0, col=0)
    assert found is ax[0, 0]


# ---------------------------------------------------------------------------
# Axes.set_id()/get_id() uniqueness.
# ---------------------------------------------------------------------------

def test_set_id_raises_on_duplicate():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].set_id("x")
    with pytest.raises(ValueError, match="'x' is already used"):
        axes[1].set_id("x")


def test_set_id_none_always_allowed_and_frees_the_id():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].set_id("x")
    axes[0].set_id(None)
    axes[1].set_id("x")   # no longer taken
    assert axes[1].get_id() == "x"


def test_set_id_to_same_value_again_does_not_self_collide():
    fig, ax = plotpress.subplots()
    ax.set_id("x")
    ax.set_id("x")   # must not raise
    assert ax.get_id() == "x"


def test_remove_clears_id_and_group_membership():
    fig, axes = plotpress.subplots(1, 2)
    axes[0].set_id("x")
    fig.group("g", [axes[0], axes[1]])
    axes[0].remove()
    assert "x" not in fig._id_index
    assert axes[0] not in fig.get_group(title="g").flat_axes()
    axes[1].set_id("x")   # freed by the removal above
    assert axes[1].get_id() == "x"


# ---------------------------------------------------------------------------
# remove_group().
# ---------------------------------------------------------------------------

def test_grouplayout_remove_group_before_build():
    layout = GroupLayout(1, 2)
    layout.add_group(0, 0, 1, 1, title="keep")
    layout.add_group(0, 1, 1, 1, title="drop")
    layout.remove_group(0, 1)
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(4, 2))
    assert [g.title for g in fig.get_groups()] == ["keep"]
    assert axes[1] is None


def test_grouplayout_remove_group_missing_raises():
    layout = GroupLayout(1, 1)
    with pytest.raises(ValueError, match="no group at"):
        layout.remove_group(0, 0)


def test_figure_remove_group_removes_axes_and_registration():
    fig, axes = _four_quadrants()
    n_before = len(fig.axes)
    fig.remove_group(title="Group (1,1)")
    assert len(fig.axes) == n_before - 4
    assert [g.title for g in fig.get_groups()] == [
        "Group (0,0)", "Group (0,1)", "Group (1,0)"]
    with pytest.raises(ValueError, match="no group matches"):
        fig.get_group(title="Group (1,1)")


def test_figure_remove_group_also_removes_a_members_own_twin():
    """remove_group() removes every axes in group.flat_axes() -- the
    group's own *listed* members -- via Axes.remove(), which (see its own
    docstring) now also removes any twin/secondary built from the axes
    being removed. A twin is never itself a listed group member (see
    Figure.group()'s own docstring on why it's auto-included instead), so
    without that cascading cleanup it would survive its own group's
    removal as an orphan: still in fig.axes, still rendered, with no
    parent axes -- or group -- left to explain it."""
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [0, 1])
    twin = axes[1].twinx()
    twin.plot([0, 1], [1, 0])
    fig.group("G", [axes[0], axes[1]], id="g1")

    fig.remove_group(id="g1")
    assert fig.axes == []
    assert twin not in fig.axes


def test_figure_remove_group_needs_exactly_one_selector():
    fig, axes = _four_quadrants()
    g = fig.get_group(title="Group (0,0)")
    with pytest.raises(ValueError, match="pass exactly one"):
        fig.remove_group()
    with pytest.raises(ValueError, match="pass exactly one"):
        fig.remove_group(group=g, title="Group (0,0)")


# ---------------------------------------------------------------------------
# Regressions found auditing this feature after it shipped.
# ---------------------------------------------------------------------------

def test_cla_releases_the_axes_own_id_not_just_resets_it():
    """cla()/clear() re-runs __init__, which resets _id to None the same as
    every other attribute -- but the *figure's* own _id_index doesn't know
    that on its own. Without releasing it explicitly, another axes trying
    to claim the freed id was incorrectly blocked by a stale entry
    pointing at an axes that no longer has that id at all."""
    fig, axes = plotpress.subplots(1, 2)
    axes[0].set_id("x")
    axes[0].cla()
    assert axes[0].get_id() is None
    assert "x" not in fig._id_index
    axes[1].set_id("x")   # must not raise
    assert axes[1].get_id() == "x"


def test_removing_every_axes_in_a_group_freezes_its_box_instead_of_crashing():
    """A group's box is ordinarily the bounding rectangle of its own axes --
    with zero axes left (each removed individually via Axes.remove(), not
    through Figure.remove_group()), rendering has nothing left to measure
    and used to raise ValueError: min() iterable argument is empty (an
    earlier version instead dropped the group entirely at that point, the
    same outcome Figure.remove_group() produces deliberately -- but that
    silently discarded a box a caller may still want visible, e.g. a
    labeled placeholder region while its axes are rebuilt elsewhere).
    Axes.remove() now freezes the group's current box (figure-fraction, see
    svg._group_bbox) the moment its last axes leaves, and rendering falls
    back to that frozen rect instead of measuring nonexistent members."""
    layout = GroupLayout(1, 1)
    layout.add_group(0, 0, 1, 2, title="G")
    fig, axes = plotpress.subplots_from_groups(layout, figsize=(6, 3))
    for ax in list(axes):
        ax.remove()
    groups = fig.get_groups()
    assert [g.title for g in groups] == ["G"]
    assert groups[0].flat_axes() == []
    fig.tight_layout()
    fig.to_svg()   # must not raise
    fig.save(io.BytesIO(), format="png")   # the raster backend too


def test_adopt_axes_updates_group_membership_not_just_id_index():
    """adopt_axes() already re-registered a replaced axes' id (see
    above) but left every group referencing the pre-adoption object
    untouched -- a group built (unusually) before dispatching an axes to
    a worker kept pointing at the orphaned original after the merge."""
    import pickle
    fig, axes = plotpress.subplots(1, 2)
    fig.group("mygroup", list(axes), id="gid1")
    worker_copy = pickle.loads(pickle.dumps(axes[1]))
    worker_copy.set_title("worker-title")
    fig.adopt_axes(worker_copy)

    g = fig.get_group(id="gid1")
    assert axes[1] not in g.flat_axes()
    assert worker_copy in g.flat_axes()
    assert g.get_ax(title="worker-title") is worker_copy


def test_removing_one_axes_from_a_two_group_shared_axes_can_empty_the_other():
    """Axes.remove() drops the axes from every group it belongs to, not
    just one -- an axes shared between two groups (unusual, but not
    prevented) leaving the figure empties both."""
    fig, axes = plotpress.subplots(2, 2)
    fig.group("A", [axes[0, 0], axes[0, 1]])
    fig.group("B", [axes[0, 1], axes[1, 1]])
    axes[0, 1].remove()
    assert [g.title for g in fig.get_groups()] == ["A", "B"]
    assert fig.get_group(title="B").flat_axes() == [axes[1, 1]]


# ---------------------------------------------------------------------------
# tight_layout(collapse="grid"/"tight"): reclaiming whitespace from removed
# axes/groups.
# ---------------------------------------------------------------------------

def _specs(axes):
    return [(s.nrows, s.ncols, s.row0, s.row1, s.col0, s.col1)
           for s in (ax._subplotspec for ax in axes)]


def test_collapse_grid_is_a_noop_for_a_single_gap_inside_a_full_row():
    """A single removed cell inside an otherwise-populated row/column is
    not a fully-empty row/column -- collapse="grid" must never move a
    surviving axes relative to its siblings for this case."""
    fig, axes = plotpress.subplots(2, 2)
    axes[0, 0].remove()
    before = _specs([axes[0, 1], axes[1, 0], axes[1, 1]])
    fig.tight_layout(collapse="grid")
    after = _specs([axes[0, 1], axes[1, 0], axes[1, 1]])
    assert before == after == [(2, 2, 0, 0, 1, 1), (2, 2, 1, 1, 0, 0), (2, 2, 1, 1, 1, 1)]


def test_collapse_grid_shrinks_a_fully_emptied_row():
    fig, axes = plotpress.subplots(3, 3)
    for ax in list(axes[1, :]):
        ax.remove()
    fig.tight_layout(collapse="grid")
    remaining = [ax for ax in fig.axes if ax._subplotspec is not None]
    assert len(remaining) == 6
    specs = sorted(_specs(remaining))
    assert specs == [
        (2, 3, 0, 0, 0, 0), (2, 3, 0, 0, 1, 1), (2, 3, 0, 0, 2, 2),
        (2, 3, 1, 1, 0, 0), (2, 3, 1, 1, 1, 1), (2, 3, 1, 1, 2, 2),
    ]
    # The two surviving rows keep their original relative order (the row
    # that was originally last is still last after the middle one is gone).
    assert axes[0, 0]._subplotspec.row0 == 0
    assert axes[2, 0]._subplotspec.row0 == 1


def test_collapse_grid_shrinks_a_fully_emptied_column():
    fig, axes = plotpress.subplots(2, 3)
    for ax in list(axes[:, 1]):
        ax.remove()
    fig.tight_layout(collapse="grid")
    remaining = [ax for ax in fig.axes if ax._subplotspec is not None]
    specs = sorted(_specs(remaining))
    assert specs == [
        (2, 2, 0, 0, 0, 0), (2, 2, 0, 0, 1, 1),
        (2, 2, 1, 1, 0, 0), (2, 2, 1, 1, 1, 1),
    ]


def test_collapse_grid_keeps_a_twin_aligned_with_its_surviving_parent():
    """A twin/secondary shares its parent's exact SubplotSpec object (see
    twinx()'s own assignment) -- collapse="grid" mutates that object in
    place rather than replacing it, so the twin must stay correctly
    aligned with its parent even when a *different* row's removal is what
    triggers the collapse."""
    fig, axes = plotpress.subplots(3, 1)
    twin = axes[2].twinx()
    axes[1].remove()
    fig.tight_layout(collapse="grid")
    assert twin._subplotspec is axes[2]._subplotspec
    assert axes[2]._subplotspec.nrows == 2
    assert axes[2]._subplotspec.row0 == 1


def test_collapse_grid_never_corrupts_an_unrelated_independently_shaped_grid():
    """Regression, found auditing this feature: Figure.add_subplot()/
    subplots() can be called more than once on one figure, each call
    producing its own independently-shaped grid. Collapsing one grid's
    empty row used to take nrows/ncols from *whichever* spec happened to
    be first in fig.axes and apply the resulting new shape to every
    grid axes on the figure indiscriminately -- silently overwriting a
    completely unrelated, untouched grid's own SubplotSpec.nrows/ncols
    with the wrong values. Specs must be grouped by their own (nrows,
    ncols) first, and collapsing must stay within one group at a time."""
    fig = plotpress.Figure()
    col = [fig.add_subplot(3, 1, i) for i in (1, 2, 3)]
    for ax in col:
        ax.plot([0, 1], [0, 1])
    col[1].remove()   # empty the middle row of the 3x1 grid

    solo = fig.add_subplot(1, 1, 1)   # a second, unrelated 1x1 "grid"
    solo.plot([0, 1], [1, 0])

    fig.tight_layout(collapse="grid")

    # The unrelated 1x1 axes must be completely untouched.
    assert (solo._subplotspec.nrows, solo._subplotspec.ncols,
           solo._subplotspec.row0, solo._subplotspec.col0) == (1, 1, 0, 0)
    # The 3x1 column must still have collapsed correctly on its own.
    remaining = [ax for ax in col if ax._subplotspec is not None and ax in fig.axes]
    assert len(remaining) == 2
    assert all(ax._subplotspec.nrows == 2 for ax in remaining)
    assert sorted(ax._subplotspec.row0 for ax in remaining) == [0, 1]
    fig.to_svg()   # must not raise


def test_collapse_grid_discards_a_group_emptied_by_direct_axes_removal():
    """Removing a group's only axes directly (not via remove_group())
    freezes its box in place rather than deleting the group (documented,
    deliberate -- see Axes.remove()'s own docstring). collapse="grid"
    is what actually reclaims that space by dropping the now-empty group
    entirely."""
    fig, axes = plotpress.subplots(1, 2)
    fig.group("G", [axes[0]])
    axes[0].remove()
    assert [g.title for g in fig.get_groups()] == ["G"]   # frozen, not gone

    fig.tight_layout(collapse="grid")
    assert fig.get_groups() == []


def test_collapse_none_default_leaves_frozen_groups_and_gaps_alone():
    """The default collapse=None must reproduce exactly today's behavior --
    a regression guard so grid/group collapsing stays strictly opt-in."""
    fig, axes = plotpress.subplots(2, 2)
    fig.group("G", [axes[0, 0]])
    axes[0, 0].remove()
    fig.tight_layout()   # collapse=None
    assert [g.title for g in fig.get_groups()] == ["G"]
    remaining = [ax for ax in fig.axes if ax._subplotspec is not None]
    assert all(ax._subplotspec.nrows == 2 and ax._subplotspec.ncols == 2
              for ax in remaining)


def test_collapse_invalid_value_raises_value_error():
    fig, ax = plotpress.subplots()
    with pytest.raises(ValueError, match="collapse must be None, 'grid', or 'tight'"):
        fig.tight_layout(collapse="bogus")


def test_collapse_tight_raises_not_implemented_for_now():
    fig, ax = plotpress.subplots()
    with pytest.raises(NotImplementedError, match="collapse='grid'"):
        fig.tight_layout(collapse="tight")


def test_tight_layout_pad_still_works_alongside_collapse():
    fig, axes = plotpress.subplots(2, 2)
    axes[0, 0].remove()
    fig.tight_layout(pad=0.05, collapse="grid")
    fig.to_svg()   # must not raise
