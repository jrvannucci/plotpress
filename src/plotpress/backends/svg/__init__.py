"""SVG serialization: turn a Figure's scene into an SVG document string.

This is the whole rendering pipeline, in pure Python + NumPy: transforms are
vectorized, each series becomes a single ``<path>`` (not one node per point),
huge lines are min/max-decimated before serialization, and each ``pcolormesh``
becomes one embedded ``<image>``. Coordinate formatting is vectorized with
``numpy.char``. Pure Python and NumPy are the whole story -- no compiled
extension; the library installs everywhere pip does.

Split into a package once the single-file version passed ~3300 lines with 90
top-level functions and no classes to naturally group them -- a pure function
library like this splits along its own dependency graph with no shared-state
concerns, so each submodule below is exactly one concern: ``_format`` (leaf
string/geometry helpers), ``_ticks_and_frame``, ``_text_and_annotations``,
``_legend``, ``_render`` (one ``_render_*`` per artist kind), ``_group_layout``
(``Figure.group()``'s boxes), ``_core`` (the public entry point, which is why
it sits above everything else here rather than the reverse), and ``_metadata``
(the interactive-HTML JSON payloads, called by figure.py, calling back into
nothing else here). This module re-exports every one of them -- public and
private -- so every name that was importable from the original single-file
``svg.py`` (public and private) resolves unchanged from here, just under
``plotpress.backends.svg`` now that the whole package lives under
``backends/``; see ``plotpress/fonts/__init__.py`` for the same re-export
pattern applied to a smaller subpackage.
"""

from ._format import (
    _DASH, _esc, _fmt, _pixel_rect,
)
from ._ticks_and_frame import (
    _max_ytick_width, _render_grid, _render_labels, _render_minor_ticks,
    _render_spines, _render_ticks, _render_twin_ticks, _xtick_label_extent,
    twiny_headroom,
)
from ._text_and_annotations import (
    _HA, _HA_FRAC, _LINE_HEIGHT_FRAC, _VA,
    _VA_FRAC, _axes_fraction_xy, _bbox_pad, _bbox_svg,
    _cscale_open, _multiline_shift, _render_annotation, _render_table,
    _render_text, _text_svg, leader_anchor, text_box,
)
from ._legend import (
    FIGURE_LEGEND_EDGE, _LEGEND_ANCHORS, _legend_layout, _legend_origin,
    _render_colorbar, _render_figure_legend, _render_legend, draw_legend,
    figure_legend_layout, figure_legend_origin, legend_box, legend_entries,
)
from ._render import (
    _HATCH_ANGLES, _HATCH_NAMES, _HATCH_SIZE, _barb_angles,
    _barb_geometry, _defs_has_id, _effective_rect, _emit_markers,
    _emit_prim, _emit_round_markers, _emit_shaped_markers, _hatch_pattern_def,
    _hatch_pattern_id, _line_path_d, _path_d, _prim_color,
    _render_axes, _render_barbs, _render_bars, _render_boxplot,
    _render_contour, _render_errorbar, _render_eventplot, _render_frameline,
    _render_framequadmesh, _render_mesh_vector, _render_pie, _render_quiver,
    _render_stem, _render_violin, _seg_to_path,
)
from ._group_layout import (
    _HA_ANCHOR, _VA_DY, _colorbar_label, _combine_group_rects,
    _ghost_group_rect, _ghost_group_rects, _group_axes_extra, _group_bbox,
    _group_colorbar_extra, _group_colorbars, _group_members, _group_top_clearance,
    _group_twins_and_secondaries, _render_fig_text, _render_figtexts, _render_groups,
)
from ._core import (
    figure_to_svg,
)
from ._metadata import (
    _axes_decoration_fields, _axes_layout_fields, _curvilinear_centers, _downsample_grid,
    _quadmesh_pick_entry, _rl, _round_list, _template_axes_extra,
    _warn_downsampled, axes_metadata, frame_data, pick_data,
    style_payload, template_metadata,
)

__all__ = [
    "FIGURE_LEGEND_EDGE", "_DASH", "_HA", "_HATCH_ANGLES",
    "_HATCH_NAMES", "_HATCH_SIZE", "_HA_ANCHOR", "_HA_FRAC",
    "_LEGEND_ANCHORS", "_LINE_HEIGHT_FRAC", "_VA", "_VA_DY",
    "_VA_FRAC", "_axes_decoration_fields", "_axes_fraction_xy", "_axes_layout_fields",
    "_barb_angles", "_barb_geometry", "_bbox_pad", "_bbox_svg",
    "_colorbar_label", "_combine_group_rects", "_cscale_open", "_curvilinear_centers",
    "_defs_has_id", "_downsample_grid", "_effective_rect", "_emit_markers",
    "_emit_prim", "_emit_round_markers", "_emit_shaped_markers", "_esc",
    "_fmt", "_ghost_group_rect", "_ghost_group_rects", "_group_axes_extra",
    "_group_bbox", "_group_colorbar_extra", "_group_colorbars", "_group_members",
    "_group_top_clearance", "_group_twins_and_secondaries", "_hatch_pattern_def", "_hatch_pattern_id",
    "_legend_layout", "_legend_origin", "_line_path_d", "_max_ytick_width",
    "_multiline_shift", "_path_d", "_pixel_rect", "_prim_color",
    "_quadmesh_pick_entry", "_render_annotation", "_render_axes", "_render_barbs",
    "_render_bars", "_render_boxplot", "_render_colorbar", "_render_contour",
    "_render_errorbar", "_render_eventplot", "_render_fig_text", "_render_figtexts",
    "_render_figure_legend", "_render_frameline", "_render_framequadmesh", "_render_grid",
    "_render_groups", "_render_labels", "_render_legend", "_render_mesh_vector",
    "_render_minor_ticks", "_render_pie", "_render_quiver", "_render_spines",
    "_render_stem", "_render_table", "_render_text", "_render_ticks",
    "_render_twin_ticks", "_render_violin", "_rl", "_round_list",
    "_seg_to_path", "_template_axes_extra", "_text_svg", "_warn_downsampled",
    "_xtick_label_extent", "axes_metadata", "draw_legend", "figure_legend_layout",
    "figure_legend_origin", "figure_to_svg", "frame_data", "leader_anchor",
    "legend_box", "legend_entries", "pick_data", "style_payload",
    "template_metadata", "text_box", "twiny_headroom",
]
