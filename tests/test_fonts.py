"""Font resolution for the raster backend, and the metrics limitation it works around."""

import numpy as np
import pytest

import plotpress
from plotpress import raster
from plotpress.fonts import text_width

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
    font = raster._font(18, plotpress.Style().font_family)
    # 18px == tick_label_size * the default scale=2 supersample.
    assert _rms_error(font, 18) < 1.0


@needs_metric_font
def test_resolved_face_beats_pillows_builtin_default():
    from PIL import ImageFont

    size = 18
    builtin = ImageFont.load_default(size=size)
    resolved = raster._font(size, plotpress.Style().font_family)
    assert _rms_error(resolved, size) < _rms_error(builtin, size)


def test_font_lookup_falls_back_instead_of_raising(monkeypatch):
    """Headless machines have none of these files; PNG export must still work."""
    monkeypatch.setattr(raster, "_font_files",
                        lambda family, bold=False: ["no-such-font.ttf"])
    raster._font_cache.clear()
    font = raster._font(12, "Whatever, sans-serif")
    assert font is not None
    raster._font_cache.clear()


def test_candidate_list_always_ends_with_metric_compatible_faces():
    files = raster._font_files("NoSuchFamily, sans-serif")
    assert files[-len(raster._HELVETICA_METRIC_FILES):] == \
        list(raster._HELVETICA_METRIC_FILES)


def test_candidate_list_prefers_the_requested_family():
    """The named family's own faces come before the metric-family fallback."""
    from plotpress.fonts import families

    files = raster._font_files("Courier New, monospace")
    first_courier = min(files.index(f) for f in ("Courier New.ttf", "cour.ttf"))
    first_fallback = min(files.index(f) for f in families.HELVETICA_FILES
                         if f in files)
    assert first_courier < first_fallback


def test_no_chain_mixes_metrically_incompatible_faces():
    """The rule that makes falling back safe: a stack's candidate files belong
    either to the metric family that measured it or to the Helvetica last
    resort -- never to some third family that merely looks similar.

    DejaVu Serif is 29% wider than Times and DejaVu Sans 14% wider than
    Helvetica, so a serif or Verdana chain tailing into either would overflow
    every box on a machine with no better face installed.
    """
    from plotpress.fonts import families

    owner = {}
    for metric_family, (regular, bold) in families._METRIC_FILES.items():
        for f in regular + bold:
            owner.setdefault(f, metric_family)

    for name, entry in families._FAMILIES.items():
        for want_bold in (False, True):
            for f in families.font_files(name, bold=want_bold):
                who = owner.get(f)
                if who is None:
                    continue        # the family's own face, e.g. verdana.ttf
                assert who in (entry.metrics, "helvetica"), (
                    f"{name!r} would draw with {f!r} ({who}) but is measured "
                    f"as {entry.metrics}")


@pytest.mark.parametrize("family", [None, "", "Helvetica, Arial, sans-serif",
                                    "Courier New, monospace", "'Quoted Name'"])
def test_font_lookup_accepts_any_family_string(family):
    assert raster._font(12, family) is not None


def test_png_export_still_works_end_to_end(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0], label="a series label")
    ax.legend()
    ax.set_ylabel("y axis label")
    ax.set_title("Title")
    out = tmp_path / "fig.png"
    fig.save(str(out), scale=2)
    assert out.stat().st_size > 0


def _laid_out(family):
    fig, ax = plotpress.subplots(style=plotpress.Style(font_family=family))
    ax.plot([0.0, 1.0], [0.0, 1.0], label="a series label")
    ax.legend()
    ax.set_ylabel("y axis label")
    fig.tight_layout()
    return ax


def test_layout_follows_the_configured_metric_family():
    """Courier is much wider than Helvetica, so it must reserve a wider margin.

    This used to assert the opposite -- that layout ignored font_family -- back
    when there was a single Helvetica table. Kept inverted rather than deleted
    so the docs cannot silently drift from the code again.
    """
    courier = _laid_out("Courier New, monospace")
    helvetica = _laid_out("Helvetica, Arial, sans-serif")
    assert courier._rect[0] > helvetica._rect[0]


def test_metric_compatible_families_lay_out_identically():
    """Arial and Liberation Sans are Helvetica clones by design; measuring them
    as anything else would be wrong."""
    base = _laid_out("Helvetica")._rect
    assert _laid_out("Arial")._rect == base
    assert _laid_out("Liberation Sans")._rect == base


def test_unmeasurable_family_falls_back_to_helvetica():
    """Verdana's metrics are proprietary and match nothing bundled, so it is
    measured as Helvetica -- the documented limitation."""
    assert _laid_out("Verdana, sans-serif")._rect == _laid_out("Helvetica")._rect


def test_legend_title_box_fits_its_bold_title():
    """The legend title is drawn bold but used to be measured with regular
    metrics, so a long title overhung the box it was centered in."""
    from plotpress.svg import _legend_layout

    title = "Measurement conditions"
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0], label="s")
    ax.legend(title=title)
    lay = _legend_layout(ax, ax.style)

    fam = ax.style.font_family
    as_bold = text_width(title, lay["fs"], fam, bold=True)
    as_regular = text_width(title, lay["fs"], fam)
    assert lay["box_w"] >= as_bold + lay["pad"] * 2
    # Guards the guard: if bold and regular measured the same, the assert above
    # would pass no matter what the code did.
    assert as_bold > as_regular


def test_bold_is_wider_than_regular():
    for s in ("legend title", "Series A", "y axis label"):
        assert text_width(s, 10, bold=True) > text_width(s, 10)


def test_courier_is_measured_monospaced():
    wide = text_width("iiii", 10, "Courier New, monospace")
    assert wide == pytest.approx(text_width("WWWW", 10, "Courier New, monospace"))
    # ...and genuinely wider than the Helvetica it used to be measured as.
    assert wide > text_width("iiii", 10)


@pytest.mark.parametrize("stack, expected", [
    ("Helvetica, Arial, sans-serif", "helvetica"),
    ("Arial", "helvetica"),
    ("'Liberation Sans'", "helvetica"),
    ("Courier New, monospace", "courier"),
    ("Times New Roman, serif", "times"),
    ("DejaVu Sans", "dejavu sans"),
    ("Verdana, sans-serif", "helvetica"),      # unmeasurable -> documented fallback
    ("NoSuchFace, Courier New", "courier"),    # skips past the unknown name
    ("", "helvetica"),
    (None, "helvetica"),
])
def test_family_resolution(stack, expected):
    from plotpress.fonts import resolve_family

    assert resolve_family(stack) == expected


def test_bundled_tables_match_their_afm_sources():
    """The width tables are generated; this catches them drifting from source.

    Reads the same URW base-14 AFMs the generator reads, by glyph name, and
    compares every ASCII advance.
    """
    matplotlib = pytest.importorskip("matplotlib", reason="AFM sources ship with matplotlib")
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    try:
        import gen_font_metrics as gen
    finally:
        sys.path.pop(0)

    from plotpress.fonts import metrics

    afm_dir = os.path.join(os.path.dirname(matplotlib.__file__),
                           "mpl-data", "fonts", "afm")
    for key, fn in gen._AFM_SOURCES.items():
        path = os.path.join(afm_dir, fn)
        if not os.path.exists(path):
            pytest.skip(f"{fn} not bundled with this matplotlib")
        expected = gen._afm_widths(path)
        if key[0] == "courier":
            assert set(expected.values()) == {metrics._COURIER_ADVANCE}
        else:
            assert metrics._TABLES[key] == expected, f"{key} drifted from {fn}"


def test_raster_resolves_a_real_bold_face_for_the_legend_title():
    """SVG draws the legend title and suptitle bold; PNG must not draw them
    regular, or the two backends disagree on weight."""
    bold = raster._font(18, plotpress.Style().font_family, bold=True)
    regular = raster._font(18, plotpress.Style().font_family)
    if bold.getname() == regular.getname():
        pytest.skip("no bold face installed on this machine")
    assert bold.getlength("legend title") > regular.getlength("legend title")


def test_bold_lookup_falls_back_to_regular_before_pillows_default():
    """Right glyphs at the wrong weight beat Pillow's metric-incompatible
    built-in, so the bold candidate list ends with the regular faces."""
    files = raster._font_files("Helvetica, Arial, sans-serif", bold=True)
    for regular in raster._HELVETICA_METRIC_FILES:
        assert regular in files


def test_installed_measurement_is_off_by_default():
    """Determinism is the default: nothing consults the machine unless asked."""
    assert plotpress.Style().measure_installed_fonts is False


def test_installed_measurement_matches_bundled_for_metric_compatible_faces():
    """Arial is metric-compatible with Helvetica, so measuring the real file
    must reproduce the bundled table. Cross-validates the generated data
    against a font that actually exists on this machine."""
    from plotpress.fonts.installed import installed_table

    table = installed_table("Arial")
    if table is None:
        pytest.skip("no Arial-metric face installed")
    for ch in ("n", "W", "0", "i", " "):
        assert table[ch] == pytest.approx(text_width(ch, 1000), abs=1.0)


def test_installed_measurement_changes_layout_for_an_unmeasurable_family():
    """The whole point of the opt-in: Verdana is ~14% wider than the Helvetica
    it otherwise gets measured as, so turning this on must widen its margin."""
    from plotpress.fonts.installed import installed_table

    if installed_table("Verdana") is None:
        pytest.skip("Verdana not installed")

    def margin(measure_installed):
        style = plotpress.Style(font_family="Verdana, sans-serif",
                                 measure_installed_fonts=measure_installed)
        fig, ax = plotpress.subplots(style=style)
        ax.barh(np.arange(3), [1.0, 2.0, 3.0])
        ax.set_yticks(np.arange(3))
        ax.set_yticklabels(["a wide category name"] * 3)
        fig.tight_layout()
        return ax._rect[0]

    assert margin(True) > margin(False)


def test_installed_measurement_falls_back_when_nothing_resolves(monkeypatch):
    """A machine with none of the candidate files must still lay out, using the
    bundled tables rather than raising."""
    from plotpress.fonts import installed

    # _measure imports font_files from .families at call time, so patch it there.
    monkeypatch.setattr("plotpress.fonts.families.font_files",
                        lambda family, bold=False: ["no-such-font.ttf"])
    installed.clear_cache()
    try:
        assert installed.installed_table("Whatever") is None
        # ...and text_width still returns the bundled estimate.
        assert text_width("abc", 10, "Whatever", measure_installed=True) == \
            text_width("abc", 10, "Whatever")
    finally:
        installed.clear_cache()


def test_tight_layout_measures_custom_tick_labels():
    """Category names set via set_yticklabels are usually far wider than the
    numbers they replace; sizing the margin from the tick *values* clipped them."""
    labels = ["a very long category name"] * 3
    fig, ax = plotpress.subplots()
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
    from plotpress.svg import _max_ytick_width

    fig, ax = plotpress.subplots()
    ax.barh(np.arange(3), [1.0, 2.0, 3.0])
    ax.set_yticks(np.arange(3))
    ax.set_yticklabels(["short"] * 3)
    narrow = _max_ytick_width(ax, ax.style)
    ax.set_yticklabels(["a very long category name"] * 3)
    wide = _max_ytick_width(ax, ax.style)
    assert wide > narrow * 2


def test_tight_layout_still_measures_numeric_ticks():
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1e7])
    fig.tight_layout()
    labels = _tick_labels(ax)
    needed = max(text_width(l, ax.style.tick_label_size) for l in labels)
    reserved = ax._rect[0] * fig.figsize[0] * ax.style.dpi
    assert reserved >= needed


def _tick_labels(ax):
    from plotpress.svg import _resolve_tick_labels
    from plotpress.ticker import nice_ticks

    (_, _), (lo, hi) = ax._resolved_limits()
    return _resolve_tick_labels(ax._yticklabels, nice_ticks(lo, hi))


@pytest.mark.parametrize("data_scale", [1.0, 1e7, 1e-7],
                         ids=["narrow-ticks", "wide-ticks", "sci-ticks"])
def test_raster_places_the_ylabel_where_svg_does(data_scale, monkeypatch):
    """raster used the tick-label font *size* plus a constant as a stand-in for
    their measured width, drifting up to ~9px from the SVG position and jamming
    the label against the figure edge when tick labels were narrow.

    Drives the real raster path and captures the x it hands _vtext, rather than
    recomputing the formula here -- which would pass no matter what raster does.
    """
    import re

    from plotpress import raster

    fig, ax = plotpress.subplots(figsize=(7.0, 3.6))
    ax.bar([0, 1, 2], np.array([1.0, 2.0, 3.0]) * data_scale)
    ax.set_ylabel("YYYY")
    fig.tight_layout()

    svg_x = float(re.search(
        r'<text x="([-\d.]+)"[^>]*rotate\(-90[^)]*\)">YYYY</text>',
        fig.to_svg()).group(1))

    seen = []
    real_vtext = raster._vtext
    monkeypatch.setattr(raster, "_vtext",
                        lambda draw, text, x, y, fill, font:
                        (seen.append((text, x)), real_vtext(draw, text, x, y, fill, font))[1])
    scale = 2
    raster.figure_to_image(fig, scale=scale)

    drawn = [x for text, x in seen if text == "YYYY"]
    assert drawn, "the y label was never drawn"
    assert drawn[0] / scale == pytest.approx(svg_x, abs=0.01)


def test_twin_axes_png_still_renders(tmp_path):
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.set_ylabel("left")
    tw = ax.twinx()
    tw.plot([0.0, 1.0], [0.0, 100.0])
    tw.set_ylabel("right")
    fig.tight_layout()
    out = tmp_path / "twin.png"
    fig.save(str(out), scale=2)
    assert out.stat().st_size > 0
