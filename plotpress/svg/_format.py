"""Small formatting/geometry primitives every other submodule leans on:
number/text escaping for SVG attribute values, and an axes' own pixel rect
before any aspect-ratio shrinkage is applied.
"""

from __future__ import annotations

import dataclasses
import math
import warnings

import numpy as np

from ..artists import (
    Annotation, Barbs, Bars, BoxPlot, Contour, ErrorBar, EventPlot, FillBetween,
    FrameLine2D, FrameQuadMesh, Image, Line2D, LineCollection, Pie, Polygon,
    PolyCollection, QuadMesh, Quiver, ScatterCollection, Span, Stem, Table, Text,
    Violin, _edges_from,
)
from ..colors import apply_colormap, resolve_colorbar_ticks, to_hex
from ..png import png_data_uri
from ..primitives import artist_to_prims
from ..primitives import pie_center_radius, pie_label_positions, tick_axis_edge
from ..primitives import (
    marker_polygon, marker_shape_kind, marker_strokes, normalize_marker_shape,
)
from ..primitives import ImagePrim as PImage
from ..primitives import Line as PLine
from ..primitives import Markers as PMarkers
from ..primitives import Path as PPath
from ..primitives import PolygonBatch as PPolyBatch
from ..primitives import Rect as PRect
from ..primitives import Segments as PSegments
from ..ticker import minor_ticks
from ..transform import LinearTransform

_DASH = {"-": None, "--": "6,4", ":": "1,3", "-.": "6,3,1,3"}


def _fmt(v: float) -> str:
    """Compact fixed-precision coordinate (2 dp), trimming trailing zeros."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _esc(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _pixel_rect(ax, W, H):
    left, bottom, w, h = ax._rect
    return (left * W, (1.0 - (bottom + h)) * H, w * W, h * H)
