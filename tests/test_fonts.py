"""Font resolution for the raster backend, and the metrics limitation it works around."""

import numpy as np
import pytest

import simpleplot
from simpleplot import raster
from simpleplot.fonts import text_width

SAMPLES = ["1.002e5", "y axis label", "a series label", "Wwwiii", "-0.5"]


def _rms_error(font, size):
    """RMS % disagreement between drawn glyph widths and the layout metrics."""
    errs = [(font.getlength(s) - text_width(s, size)) / text_width(s, size) * 100
            for s in SAMPLES]
    return (sum(e * e for e in errs) / len(errs)) ** 0.5


def _has_metric_compatible_font():
    from PIL import ImageFont

    for name in raster._HELVETICA_METRIC_FILES:
        try:
            ImageFont.truetype(name, 12)
            return True
        except OSError:
            continue
    return False


# Bare CI images may ship none of these; the fidelity claims only hold when one
# is installed. Everything below this guard must pass with or without fonts.
needs_metric_font = pytest.mark.skipif(
    not _has_metric_compatible_font(),
    reason="no Helvetica-metric font installed on this machine",
)


@needs_metric_font
def test_default_stack_resolves_to_a_helvetica_metric_face():
    """PNG glyphs must come from a face the layout metrics actually describe."""
    font = raster._font(18, simpleplot.Style().font_family)
    # 18px == tick_label_size * the default scale=2 supersample.
    assert _rms_error(font, 18) < 1.0


@needs_metric_font
def test_resolved_face_beats_pillows_builtin_default():
    from PIL import ImageFont

    size = 18
    builtin = ImageFont.load_default(size=size)
    resolved = raster._font(size, simpleplot.Style().font_family)
    assert _rms_error(resolved, size) < _rms_error(builtin, size)


def test_font_lookup_falls_back_instead_of_raising(monkeypatch):
    """Headless machines have none of these files; PNG export must still work."""
    monkeypatch.setattr(raster, "_font_files", lambda family: ["no-such-font.ttf"])
    raster._font_cache.clear()
    font = raster._font(12, "Whatever, sans-serif")
    assert font is not None
    raster._font_cache.clear()


def test_candidate_list_always_ends_with_metric_compatible_faces():
    files = raster._font_files("NoSuchFamily, sans-serif")
    assert files[-len(raster._HELVETICA_METRIC_FILES):] == \
        list(raster._HELVETICA_METRIC_FILES)


def test_candidate_list_prefers_the_requested_family():
    files = raster._font_files("Courier New, monospace")
    assert files[0] == "cour.ttf"
    assert "arial.ttf" in files          # ...but still falls back to compatible


@pytest.mark.parametrize("family", [None, "", "Helvetica, Arial, sans-serif",
                                    "Courier New, monospace", "'Quoted Name'"])
def test_font_lookup_accepts_any_family_string(family):
    assert raster._font(12, family) is not None


def test_png_export_still_works_end_to_end(tmp_path):
    fig, ax = simpleplot.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0], label="a series label")
    ax.legend()
    ax.set_ylabel("y axis label")
    ax.set_title("Title")
    out = tmp_path / "fig.png"
    fig.save(str(out), scale=2)
    assert out.stat().st_size > 0


def test_metrics_are_font_family_independent():
    """The documented limitation: text_width measures Helvetica, whatever the
    configured family. Guards the docs against silently drifting from the code."""
    wide = simpleplot.Style(font_family="Courier New, monospace")
    narrow = simpleplot.Style(font_family="Helvetica, Arial, sans-serif")
    fig_w, ax_w = simpleplot.subplots(style=wide)
    fig_n, ax_n = simpleplot.subplots(style=narrow)
    for ax in (ax_w, ax_n):
        ax.plot([0.0, 1.0], [0.0, 1.0], label="a series label")
        ax.legend()
        ax.set_ylabel("y axis label")
    fig_w.tight_layout()
    fig_n.tight_layout()
    assert ax_w._rect == ax_n._rect      # identical layout despite different fonts


def test_tight_layout_measures_custom_tick_labels():
    """Category names set via set_yticklabels are usually far wider than the
    numbers they replace; sizing the margin from the tick *values* clipped them."""
    labels = ["a very long category name"] * 3
    fig, ax = simpleplot.subplots()
    ax.barh(np.arange(3), [1.0, 2.0, 3.0])
    ax.set_yticks(np.arange(3))
    ax.set_yticklabels(labels)
    fig.tight_layout()

    needed = max(text_width(l, ax.style.tick_label_size) for l in labels)
    reserved = ax._rect[0] * fig.figsize[0] * ax.style.dpi
    assert reserved >= needed


def test_ylabel_clears_custom_tick_labels():
    """The y label is placed past the widest tick label, so it must measure the
    custom strings too."""
    from simpleplot.svg import _max_ytick_width

    fig, ax = simpleplot.subplots()
    ax.barh(np.arange(3), [1.0, 2.0, 3.0])
    ax.set_yticks(np.arange(3))
    ax.set_yticklabels(["short"] * 3)
    narrow = _max_ytick_width(ax, ax.style)
    ax.set_yticklabels(["a very long category name"] * 3)
    wide = _max_ytick_width(ax, ax.style)
    assert wide > narrow * 2


def test_tight_layout_still_measures_numeric_ticks():
    fig, ax = simpleplot.subplots()
    ax.plot([0.0, 1.0], [0.0, 1e7])
    fig.tight_layout()
    labels = _tick_labels(ax)
    needed = max(text_width(l, ax.style.tick_label_size) for l in labels)
    reserved = ax._rect[0] * fig.figsize[0] * ax.style.dpi
    assert reserved >= needed


def _tick_labels(ax):
    from simpleplot.svg import _resolve_tick_labels
    from simpleplot.ticker import nice_ticks

    (_, _), (lo, hi) = ax._resolved_limits()
    return _resolve_tick_labels(ax._yticklabels, nice_ticks(lo, hi))
