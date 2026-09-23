"""``figure_to_svg`` -- the module's single public entry point, which is why it
sits above (imports from) everything else here rather than the reverse.
"""

from __future__ import annotations

import dataclasses
import math
import warnings

import numpy as np

from ...core.artists import (
    Annotation, Barbs, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Image, Line2D, LineCollection, Pie, Polygon,
    PolyCollection, QuadMesh, Quiver, ScatterCollection, Span, Stem, Table, Text,
    Violin, _edges_from,
)
from ...style.colors import apply_colormap, resolve_colorbar_ticks, to_hex
from ..png import png_data_uri
from ...core.primitives import artist_to_prims
from ...core.primitives import pie_center_radius, pie_label_positions, tick_axis_edge
from ...core.primitives import (
    marker_polygon, marker_shape_kind, marker_strokes, normalize_marker_shape,
)
from ...core.primitives import ImagePrim as PImage
from ...core.primitives import Line as PLine
from ...core.primitives import Markers as PMarkers
from ...core.primitives import Path as PPath
from ...core.primitives import PolygonBatch as PPolyBatch
from ...core.primitives import Rect as PRect
from ...core.primitives import Segments as PSegments
from ...style.ticker import minor_ticks
from ...core.transform import LinearTransform

from ._format import _esc, _fmt
from ._legend import _render_figure_legend
from ._render import _render_axes
from ._group_layout import _render_figtexts, _render_groups

def figure_to_svg(fig, interactive: bool = False) -> str:
    fig._settle_layout()
    dpi = fig.style.dpi
    if not (dpi > 0):
        # figsize itself is validated at Figure() construction, but dpi is
        # a plain, freely-mutable Style attribute -- fig.style.dpi = 0 (or
        # negative) reaches this same width/height product and produces the
        # identical invalid, unrenderable SVG (width="0"/negative) that
        # fix was written to prevent, just through a different door.
        raise ValueError(f"Figure.style.dpi must be > 0, got {dpi!r}")
    W = fig.figsize[0] * dpi
    H = fig.figsize[1] * dpi

    defs: list[str] = []
    body: list[str] = []

    for i, ax in enumerate(fig.axes):
        _render_axes(ax, fig, W, H, i, defs, body)

    _render_figtexts(fig, W, H, body)
    _render_figure_legend(fig, fig.style, W, H, body)
    _render_groups(fig, W, H, body)

    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{_fmt(W)}" height="{_fmt(H)}" '
        f'viewBox="0 0 {_fmt(W)} {_fmt(H)}" '
        f'font-family="{fig.style.font_family}">'
    )
    # A document <title> is both an accessibility hook (screen readers,
    # browser-tab title if the SVG is opened standalone) and free metadata
    # for anything that lists SVG files by name -- only emitted when there
    # is a real title to give it, rather than a generic filler on every plot.
    title_block = f"<title>{_esc(fig._suptitle['text'])}</title>" if fig._suptitle else ""
    bg = f'<rect x="0" y="0" width="{_fmt(W)}" height="{_fmt(H)}" fill="{fig.style.facecolor}"/>'
    defs_block = f"<defs>{''.join(defs)}</defs>" if defs else ""
    return header + title_block + defs_block + bg + "".join(body) + "</svg>"
