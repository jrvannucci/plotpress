"""tick_params(labelrotation=...): diagonal tick labels.

Covers the SVG/raster rendering, tight_layout()'s margin reservation for the
rotated footprint, the template round-trip, and two real bugs found while
building this (a twin axes' own tick_params() override was never consulted
by its renderer at all; post-tight_layout() mutations never re-triggered a
relayout)."""

import numpy as np
import pytest

import plotpress
from conftest import SVG_NS as NS, parse_svg as _parse


def _x_texts(fig):
    return [t for t in _parse(fig.to_svg()).findall(".//" + NS + "text")]


def test_tick_params_labelrotation_stores_per_axis_override():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_params(axis="x", labelrotation=45)
    assert ax._tick_overrides["x"]["tick_label_rotation"] == 45
    assert "tick_label_rotation" not in ax._tick_overrides["y"]


def test_tick_params_labelrotation_axis_both_sets_both():
    fig, ax = plotpress.subplots()
    ax.tick_params(labelrotation=30)   # axis="both" is the default
    assert ax._tick_overrides["x"]["tick_label_rotation"] == 30
    assert ax._tick_overrides["y"]["tick_label_rotation"] == 30


def test_svg_rotates_x_tick_labels_and_right_anchors_them():
    fig, ax = plotpress.subplots()
    ax.bar(["Alpha", "Beta"], [1, 2])
    ax.set_xticks([0, 1], labels=["Alpha", "Beta"])
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()

    texts = _x_texts(fig)
    rotated = [t for t in texts if t.text in ("Alpha", "Beta")]
    assert len(rotated) == 2
    for t in rotated:
        assert t.get("text-anchor") == "end"
        assert "rotate(-45" in t.get("transform", "")


def test_svg_x_ticks_unrotated_by_default_carry_no_transform():
    fig, ax = plotpress.subplots()
    ax.bar(["Alpha", "Beta"], [1, 2])
    fig.tight_layout()

    texts = _x_texts(fig)
    plain = [t for t in texts if t.text in ("Alpha", "Beta")]
    assert len(plain) == 2
    for t in plain:
        assert t.get("text-anchor") == "middle"
        assert t.get("transform") is None


def test_y_axis_tick_labels_can_also_rotate():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_yticks([0, 1], labels=["Low", "High"])
    ax.tick_params(axis="y", labelrotation=30)
    fig.tight_layout()

    texts = _x_texts(fig)
    rotated = [t for t in texts if t.text in ("Low", "High")]
    assert len(rotated) == 2
    for t in rotated:
        assert "rotate(-30" in t.get("transform", "")


def test_tight_layout_reserves_more_bottom_margin_for_rotated_long_labels():
    """The whole point: a rotated long label must not overlap the row below
    it -- tight_layout() has to size the bottom margin from the label's
    actual rotated footprint, not a single fixed text row."""
    long_labels = ["Customer Success", "Product Engineering", "Sales & Marketing"]

    f1, a1 = plotpress.subplots(2, 1, figsize=(6, 6))
    a1[0].bar(long_labels, [1, 2, 3])
    a1[1].plot([0, 1], [0, 1])
    f1.tight_layout()
    unrotated_gap = a1[0]._rect[1] - (a1[1]._rect[1] + a1[1]._rect[3])

    f2, a2 = plotpress.subplots(2, 1, figsize=(6, 6))
    a2[0].bar(long_labels, [1, 2, 3])
    a2[0].tick_params(axis="x", labelrotation=45)
    a2[1].plot([0, 1], [0, 1])
    f2.tight_layout()
    rotated_gap = a2[0]._rect[1] - (a2[1]._rect[1] + a2[1]._rect[3])

    assert rotated_gap > unrotated_gap, (
        "a rotated long label's real (measured) footprint must reserve more "
        "vertical margin than an unrotated single text row, or the panel "
        "below it gets drawn on top of the diagonal labels")


def test_tight_layout_grows_left_margin_for_rotated_labels_on_column_zero():
    """A rotated, end-anchored label reaches away from its tick -- for the
    leftmost column that's toward the figure's own left edge, which would
    otherwise clip the label clean off the canvas rather than merely crowd
    a neighboring panel."""
    long_labels = ["Customer Success", "Product Engineering", "Sales & Marketing"]

    f1, a1 = plotpress.subplots()
    a1.bar(long_labels, [1, 2, 3])
    f1.tight_layout()

    f2, a2 = plotpress.subplots()
    a2.bar(long_labels, [1, 2, 3])
    a2.tick_params(axis="x", labelrotation=45)
    f2.tight_layout()

    assert a2._rect[0] > a1._rect[0]


def test_tick_label_rotation_round_trips_through_template():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_params(axis="x", labelrotation=45)

    fig2, ax2 = plotpress.figure_from_template(fig.to_template())
    assert ax2._tick_overrides["x"]["tick_label_rotation"] == 45


def test_twin_tick_params_labelrotation_actually_renders_on_the_twin():
    """Regression: _render_twin_ticks never consulted the twin's own
    tick_params() override at all (any of it -- labelsize, color, and now
    rotation), always drawing with the figure-wide default no matter what
    was set on the twin itself."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    twin = ax.twiny()
    twin.plot([0, 1], [1, 0])
    twin.set_xticks([0, 1], labels=["Left", "Right"])
    twin.tick_params(axis="x", labelrotation=30, labelsize=13.0)
    fig.tight_layout()

    texts = _x_texts(fig)
    rotated = [t for t in texts if t.text in ("Left", "Right")]
    assert len(rotated) == 2
    for t in rotated:
        assert "rotate(-30" in t.get("transform", "")
        assert t.get("font-size") == "13.0"


def test_setting_labelrotation_after_tight_layout_triggers_relayout():
    """tick_params(labelrotation=...) changes how much margin tight_layout()
    needs to reserve, so -- like set_title()/set_xlabel() already do -- it
    must mark the figure's layout dirty for _settle_layout() to re-fit
    before the next render, or a rotation applied after tight_layout() would
    render with a margin sized for the old, unrotated label."""
    long_labels = ["Customer Success", "Product Engineering", "Sales & Marketing"]
    fig, axes = plotpress.subplots(2, 1, figsize=(6, 6))
    axes[0].bar(long_labels, [1, 2, 3])
    axes[1].plot([0, 1], [0, 1])
    fig.tight_layout()
    before = axes[0]._rect[1] - (axes[1]._rect[1] + axes[1]._rect[3])

    axes[0].tick_params(axis="x", labelrotation=45)
    fig.to_svg()   # render triggers _settle_layout()
    after = axes[0]._rect[1] - (axes[1]._rect[1] + axes[1]._rect[3])

    assert after > before


def test_save_png_with_rotated_tick_labels(tmp_path):
    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.bar(["Customer Success", "Product Engineering"], [1, 2])
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    p = tmp_path / "rotated.png"
    fig.savefig(str(p))
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_rotated_x_labels_do_not_paint_above_the_axes_bottom_edge(tmp_path):
    """Regression: a rotated tick label's own renderer used to *center* the
    rotated glyph box on its anchor point instead of honoring the same
    right-anchor svg.py uses (see _rotated_anchored_text's own docstring),
    so roughly half of each label swung up past the axis and into the plot
    area instead of hanging below it. Checked by pixel: nothing but the
    plain green bar fill may appear in a thin strip just *inside* the axes'
    own bottom edge once labels are rotated."""
    pytest.importorskip("PIL")
    import numpy as np
    from PIL import Image

    fig, ax = plotpress.subplots(figsize=(6, 4))
    ax.bar(["Customer Success", "Product Engineering", "Sales & Marketing"],
          [1, 2, 3], color="#2ca02c")
    ax.set_ylim(0, 3)
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    p = tmp_path / "rotated_bounds.png"
    fig.savefig(str(p))

    img = np.asarray(Image.open(str(p)).convert("RGB"))
    left, bottom, w, h = ax._rect
    W, H = fig.figsize[0] * fig.style.dpi, fig.figsize[1] * fig.style.dpi
    axis_bottom_row = int(round(H * (1 - bottom)))
    # A couple of pixels above the axis line, over the empty (unbarred) gap
    # near x=0 -- background white or bar green only, never dark tick-label
    # glyph pixels bleeding up past the axis from a mis-anchored rotation.
    strip = img[max(0, axis_bottom_row - 4):axis_bottom_row - 1,
               int(W * left):int(W * (left + w))]
    is_background_or_bar = (
        np.all(strip > 230, axis=-1)                                     # white
        | ((strip[..., 1].astype(int) - strip[..., 0].astype(int)) > 30)  # greener than red: the bar fill
    )
    assert is_background_or_bar.mean() > 0.98, (
        "dark (label-colored) pixels found just inside the axes' own "
        "bottom edge -- a rotated tick label is painting into the plot")
