"""tight_layout()'s advisory text-overflow warnings and auto_label_scale=:
completing the last piece of audit bug #1 (long labels/titles overlap or
clip under tight_layout()) -- the cases outside what tight_layout()'s own
margin math was ever going to catch on its own (an *unrotated* x tick
label too long for its own tick spacing, or a title/group title wider
than the box it's centered over), where the right fix (smaller font,
rotation, shorter text, wider figure) is a judgment call. Default behavior
is to warn, naming a concrete fix; ``auto_label_scale=True`` picks one of
those fixes itself wherever there's a per-instance font size to shrink.
"""

import warnings

import plotpress

LONG_LABELS = ["Customer Success", "Product Engineering", "Sales & Marketing",
              "Finance & Legal", "Human Resources", "Information Technology"]


def _warnings_from(fn):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn()
    return [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


def test_overlapping_x_tick_labels_warn_with_a_concrete_fix():
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.bar(LONG_LABELS, range(len(LONG_LABELS)))
    msgs = _warnings_from(fig.tight_layout)
    assert any("x tick labels are wider" in m and "labelrotation" in m
              and "auto_label_scale" in m for m in msgs)


def test_an_ordinary_figure_produces_no_overflow_warnings():
    fig, axes = plotpress.subplots(2, 3, figsize=(10, 6))
    for i, ax in enumerate(axes.ravel()):
        ax.plot([0, 1], [0, 1])
        ax.set_title(f"Panel {i}")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    assert _warnings_from(fig.tight_layout) == []


def test_rotated_x_tick_labels_are_exempt_from_the_overlap_check():
    """A rotated label's own footprint is handled by the vertical-margin
    fix (0.38.0/0.38.3), not this horizontal-spacing heuristic -- it
    would otherwise flag the very fix the warning itself recommends."""
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.bar(LONG_LABELS, range(len(LONG_LABELS)))
    ax.tick_params(axis="x", labelrotation=45)
    msgs = _warnings_from(fig.tight_layout)
    assert not any("x tick labels are wider" in m for m in msgs)


def test_a_title_wider_than_its_axes_warns():
    fig, ax = plotpress.subplots(figsize=(2.5, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_title("An Extremely Long Title That Will Not Fit")
    msgs = _warnings_from(fig.tight_layout)
    assert any("title" in m and "wider than its own axes" in m for m in msgs)


def test_an_xlabel_wider_than_its_axes_warns_and_names_the_limitation():
    fig, ax = plotpress.subplots(figsize=(2.0, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("An Extremely Long X Axis Label Right Here")
    msgs = _warnings_from(fig.tight_layout)
    assert any("xlabel" in m and "no per-axes xlabel size" in m for m in msgs)


def test_a_group_title_wider_than_its_box_warns():
    fig, axes = plotpress.subplots(1, 2, figsize=(3, 3))
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    fig.group("An Extremely Long Group Title Right Here", list(axes),
             title_position="top")
    msgs = _warnings_from(fig.tight_layout)
    assert any("group's title" in m and "wider than its own box" in m for m in msgs)


def test_auto_label_scale_fixes_overlapping_x_tick_labels_with_no_warning():
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.bar(LONG_LABELS, range(len(LONG_LABELS)))
    default_size = ax.style.tick_label_size
    msgs = _warnings_from(lambda: fig.tight_layout(auto_label_scale=True))
    assert msgs == []
    assert ax._tick_overrides["x"]["tick_label_size"] < default_size


def test_auto_label_scale_fixes_an_oversized_title_with_no_warning():
    fig, ax = plotpress.subplots(figsize=(2.5, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_title("An Extremely Long Title That Will Not Fit")
    default_size = fig.style.title_size
    msgs = _warnings_from(lambda: fig.tight_layout(auto_label_scale=True))
    assert msgs == []
    assert ax._title_size < default_size


def test_auto_label_scale_fixes_an_oversized_group_title_with_no_warning():
    fig, axes = plotpress.subplots(1, 2, figsize=(3, 3))
    for ax in axes:
        ax.plot([0, 1], [0, 1])
    fig.group("An Extremely Long Group Title Right Here", list(axes),
             title_position="top")
    default_size = fig.style.title_size
    msgs = _warnings_from(lambda: fig.tight_layout(auto_label_scale=True))
    assert msgs == []
    [g] = fig.get_groups()
    assert g._raw["fontsize"] < default_size


def test_auto_label_scale_never_fixes_a_plain_xlabel_and_still_warns():
    """There's no per-axes font size to shrink for a plain set_xlabel() --
    auto_label_scale must not pretend it fixed this."""
    fig, ax = plotpress.subplots(figsize=(2.0, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("An Extremely Long X Axis Label Right Here")
    msgs = _warnings_from(lambda: fig.tight_layout(auto_label_scale=True))
    assert any("xlabel" in m for m in msgs)


def test_auto_label_scale_stops_at_the_legibility_floor_and_still_warns():
    """An extreme enough case can't be fully fixed by shrinking alone --
    the floor is a legibility limit, not a promise everything now fits,
    so this must still tell the caller it needs a different remedy."""
    labels = [f"Extremely Long Category Name Number {i}" for i in range(10)]
    fig, ax = plotpress.subplots(figsize=(4, 3))
    ax.bar(labels, range(10))
    msgs = _warnings_from(lambda: fig.tight_layout(auto_label_scale=True))
    assert any("x tick labels are wider" in m for m in msgs)
    assert ax._tick_overrides["x"]["tick_label_size"] == 6.0   # the floor


def test_auto_label_scale_reflows_the_margin_for_the_smaller_font():
    """Shrinking the tick label needs less vertical margin below the axes
    -- auto_label_scale must re-run tight_layout() fully, not just patch
    the font size and leave the old (now oversized) margin reserved."""
    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.bar(LONG_LABELS, range(len(LONG_LABELS)))
    fig.tight_layout()   # default labelsize, whatever margin that reserves
    bottom_before = ax._rect[1]

    fig2, ax2 = plotpress.subplots(figsize=(6, 4))
    ax2.bar(LONG_LABELS, range(len(LONG_LABELS)))
    fig2.tight_layout(auto_label_scale=True)
    bottom_after = ax2._rect[1]

    assert bottom_after < bottom_before, (
        "a smaller tick label needs a smaller bottom margin -- "
        "auto_label_scale's corrective pass must actually apply")
