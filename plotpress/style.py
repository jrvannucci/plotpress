"""Per-figure styling. Replaces matplotlib's global ``rcParams``.

Every :class:`~plotpress.figure.Figure` owns its own :class:`Style` instance, so
nothing here is global. Mutating one figure's style never affects another.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List

# Default categorical color cycle (matplotlib's "tab10").
DEFAULT_COLOR_CYCLE: List[str] = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


@dataclass
class Style:
    """Visual configuration for a single figure.

    Create a variant without mutating the original via :meth:`copy`.
    """

    # Figure
    facecolor: str = "#ffffff"
    dpi: float = 100.0

    # Axes
    axes_facecolor: str = "#ffffff"
    spine_color: str = "#000000"
    spine_width: float = 0.8

    # Text
    #
    # Layout reserves space for text using bundled advance widths (see
    # plotpress.fonts), because an SVG figure is laid out before anything draws
    # the glyphs. Helvetica, Times, Courier and DejaVu Sans are bundled, along
    # with their metric-compatible clones, so those families are accurate. A
    # family outside them -- Verdana, Tahoma, Arial Black, Arial Narrow -- still
    # renders, but is measured as Helvetica, so its legend boxes and axis
    # margins will not fit it. Set measure_installed_fonts for those.
    font_family: str = "Helvetica, Arial, sans-serif"
    font_size: float = 10.0
    title_size: float = 12.0
    label_size: float = 11.0
    text_color: str = "#000000"

    # Measure the font files installed on this machine instead of the bundled
    # tables. More faithful for families plotpress cannot measure, at the cost
    # of the guarantee that the same script lays out identically everywhere --
    # which is why it is off. See plotpress.fonts.installed.
    measure_installed_fonts: bool = False

    # Ticks
    tick_size: float = 3.5
    tick_width: float = 0.8
    tick_label_size: float = 9.0

    # Grid
    grid_color: str = "#b0b0b0"
    grid_width: float = 0.6
    grid_alpha: float = 0.6

    # Lines / markers
    line_width: float = 1.5
    marker_size: float = 6.0  # diameter in points

    color_cycle: List[str] = field(default_factory=lambda: list(DEFAULT_COLOR_CYCLE))

    def text_width(self, text: str, size: float, bold: bool = False,
                   italic: bool = False) -> float:
        """Predicted width of ``text`` in pixels, per this style's font settings.

        The measuring entry point layout should use: it carries ``font_family``
        and ``measure_installed_fonts`` with it, so no caller has to remember to
        pass either.
        """
        from .fonts import text_width

        return text_width(text, size, self.font_family, bold, italic,
                          measure_installed=self.measure_installed_fonts)

    def copy(self, **overrides) -> "Style":
        """Return a modified copy, leaving this instance untouched.

        Mutable fields are duplicated so two figures never share a list.
        """
        overrides.setdefault("color_cycle", list(self.color_cycle))
        return replace(self, **overrides)
