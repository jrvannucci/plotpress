"""Regression for audit bug #2: an axis label's own render offset used the
figure-wide default tick style, not tick_params()'s resolved per-axis
override -- so a labelsize (or, once rotation shipped, labelrotation)
override could put the axis label on top of a tick label sized (or tilted)
differently from what the offset assumed.

svg._render_labels/raster._raster_labels now resolve the same per-axis
override tight_layout() already measures from, exactly like
svg._render_ticks's own caller already did for the tick marks/labels
themselves.
"""

import math

import plotpress
from conftest import SVG_NS as NS, parse_svg as _parse


def _label_texts(fig):
    return {t.text: t for t in _parse(fig.to_svg()).findall(".//" + NS + "text")}


def _x_offset_past_axes_bottom(fig, ax, label_text):
    """How far *past* the axes' own bottom edge the xlabel is drawn --
    the quantity that has to track the tick style, not the label's
    absolute canvas position (tight_layout() sizes the reserved margin
    from the exact same tick style the render offset now also uses, so
    the two move together and the label's *absolute* position ends up
    unchanged regardless of tick size -- only the gap it leaves for the
    tick labels in between actually reveals a mismatch).

    ``ax._rect`` stores ``bottom`` matplotlib-style, as a fraction *up
    from the bottom of the figure* -- ``svg._pixel_rect`` converts that to
    the pixel-space (top-left-origin, y-down) top of the box via
    ``(1 - (bottom + h)) * H``, so the box's own pixel-space bottom edge
    is ``(1 - bottom) * H``, not ``(bottom + h) * H``.
    """
    _, bottom, _, _ = ax._rect
    H = fig.figsize[1] * fig.style.dpi
    axes_bottom_px = (1.0 - bottom) * H
    return float(_label_texts(fig)[label_text].get("y")) - axes_bottom_px


def _y_offset_past_axes_left(fig, ax, label_text):
    left, _, _, _ = ax._rect
    W = fig.figsize[0] * fig.style.dpi
    axes_left_px = left * W
    return axes_left_px - float(_label_texts(fig)[label_text].get("x"))


def test_larger_x_labelsize_widens_the_xlabels_own_clearance():
    f1, a1 = plotpress.subplots()
    a1.plot([0, 1], [0, 1])
    a1.set_xlabel("time")
    f1.tight_layout()
    default_offset = _x_offset_past_axes_bottom(f1, a1, "time")

    f2, a2 = plotpress.subplots()
    a2.plot([0, 1], [0, 1])
    a2.set_xlabel("time")
    a2.tick_params(axis="x", labelsize=24)
    f2.tight_layout()
    larger_offset = _x_offset_past_axes_bottom(f2, a2, "time")

    assert larger_offset > default_offset, (
        "a bigger x tick label needs more clearance between the axes' own "
        "bottom edge and the xlabel, or the xlabel draws on top of the "
        "(now larger) tick labels")


def test_larger_y_labelsize_widens_the_ylabels_own_clearance():
    f1, a1 = plotpress.subplots()
    a1.plot([0, 1], [0, 1])
    a1.set_ylabel("value")
    f1.tight_layout()
    default_offset = _y_offset_past_axes_left(f1, a1, "value")

    f2, a2 = plotpress.subplots()
    a2.plot([0, 1], [0, 1])
    a2.set_ylabel("value")
    a2.tick_params(axis="y", labelsize=24)
    f2.tight_layout()
    larger_offset = _y_offset_past_axes_left(f2, a2, "value")

    assert larger_offset > default_offset, (
        "a bigger y tick label needs more clearance to its left before "
        "the (left-side) ylabel starts")


def test_rotated_xlabel_offset_clears_the_rotated_footprint_not_one_text_row():
    labels = ["Customer Success", "Product Engineering", "Sales & Marketing"]

    fig, ax = plotpress.subplots()
    ax.bar(labels, [1, 2, 3])
    ax.set_xlabel("Department")
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    rotated_offset = _x_offset_past_axes_bottom(fig, ax, "Department")

    fig2, ax2 = plotpress.subplots()
    ax2.bar(labels, [1, 2, 3])
    ax2.set_xlabel("Department")
    fig2.tight_layout()
    unrotated_offset = _x_offset_past_axes_bottom(fig2, ax2, "Department")

    assert rotated_offset > unrotated_offset, (
        "the xlabel's own offset must clear the rotated tick labels' real "
        "(measured) footprint, not the flat single-text-row offset an "
        "unrotated label would need")


def test_png_render_with_labelsize_override_does_not_crash(tmp_path):
    import pytest

    pytest.importorskip("PIL")
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.tick_params(labelsize=20)
    fig.tight_layout()
    p = tmp_path / "labelsize.png"
    fig.savefig(str(p))
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_title_still_renders_alongside_axis_labels():
    """Regression for the exact mistake made while fixing this: rewriting
    _render_labels' body must not drop the title block it also owns."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.set_title("hello")
    texts = {t.text for t in _parse(fig.to_svg()).findall(".//" + NS + "text")}
    assert {"time", "value", "hello"} <= texts
