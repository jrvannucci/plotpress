"""The Figure: the root object that owns everything needed to render itself.

There is no global "current figure" or "current axes". A figure holds its own
axes, its own :class:`~plotpress.style.Style`, and knows how to serialize itself to
SVG/HTML or show itself in a native pop-up window. Two figures never share
mutable state.

Split into a package once the single-file version passed 5000 lines. ``Figure``
itself, and the grid/group machinery it's genuinely mutually coupled to
(``Group``/``GroupLayout``/``subplots()``/``subplots_from_groups()`` -- see
``_core.py``'s own docstring for why those stay together), make up the bulk;
``_layout.py`` and ``_html_options.py`` are the two leaf modules ``_core``
depends on, and ``_template.py``/``_report.py``/``_io.py`` are the three
independent things built *from* a ``Figure`` (a rebuilt one, a multi-figure
aggregator, and recovered plotted data, respectively) rather than needed *by*
it. This module re-exports every one of them -- public and private -- so
``from plotpress.figure import X`` keeps resolving exactly as it did when this
was one file; see ``plotpress/fonts/__init__.py`` for the same pattern applied
to a smaller subpackage.
"""

from ._layout import (
    _MIN_TICK_LABEL_SIZE, _MIN_TITLE_SIZE, _TEXT_FIT_MARGIN, _auto_scale_overlapping_labels,
    _ax_ident, _axes_position_desc, _axes_summary_lines, _cbar_label_width,
    _collapse_empty_grid_rows_and_cols, _iter_text_overflows, _layout_colorbar, _layout_figure_legend,
    _layout_inset, _place_spec_rects, _require_one_grid_shape, _vega_compat_report,
    _warn_about_text_overflow,
)
from ._html_options import (
    _BINARY_ARRAY_MIN_LEN, _INTERACTIVE_OPTIONS, _OPTION_KEYS, _check_option_value,
    _columnarize_meta, _encode_binary_arrays, _fits_float16, _json_payload,
    _resolve_options, _sanitize_nan, _toolbar_clearance,
)
from ._core import (
    Figure, GridSpec, Group, GroupLayout,
    SubplotSpec, _ALIGN_UNSET, _MarkerApi, _TEMP_MAX_AGE,
    _TEMP_PREFIX, _apply_axes_decorations, _axes_class, _cell_subplotspec,
    _finish_lookup, _fit_cells, _flatten_axes, _group_by,
    _normalize_pad, _resolve_lookup_key, _slice_span, _squeeze_grid,
    _subplot_rect, _sweep_stale_tempfiles, subplots, subplots_from_groups,
)
from ._template import (
    _rebuild_from_template, _squeeze_template_axes, figure_from_template,
)
from ._report import (
    Report, _REPORT_MAX_WIDTH, _REPORT_SCRIPT, _REPORT_STYLE,
)
from ._io import (
    _decode_binary_arrays, _dedupe_keyed, _expand_columnar_meta, _extract_json_block,
    _load_single_figure, _load_template, _mesh_centers, _split_report_entries,
    _title_keyed_axes, load_data, load_data_xarray, load_template,
    select_panel,
)

__all__ = [
    "Figure", "GridSpec", "Group", "GroupLayout",
    "Report", "SubplotSpec", "_ALIGN_UNSET", "_BINARY_ARRAY_MIN_LEN",
    "_INTERACTIVE_OPTIONS", "_MIN_TICK_LABEL_SIZE", "_MIN_TITLE_SIZE", "_MarkerApi",
    "_OPTION_KEYS", "_REPORT_MAX_WIDTH", "_REPORT_SCRIPT", "_REPORT_STYLE",
    "_TEMP_MAX_AGE", "_TEMP_PREFIX", "_TEXT_FIT_MARGIN", "_apply_axes_decorations",
    "_auto_scale_overlapping_labels", "_ax_ident", "_axes_class", "_axes_position_desc",
    "_axes_summary_lines", "_cbar_label_width", "_cell_subplotspec", "_check_option_value",
    "_collapse_empty_grid_rows_and_cols", "_columnarize_meta", "_decode_binary_arrays", "_dedupe_keyed",
    "_encode_binary_arrays", "_expand_columnar_meta", "_extract_json_block", "_finish_lookup",
    "_fit_cells", "_fits_float16", "_flatten_axes", "_group_by",
    "_iter_text_overflows", "_json_payload", "_layout_colorbar", "_layout_figure_legend",
    "_layout_inset", "_load_single_figure", "_load_template", "_mesh_centers",
    "_normalize_pad", "_place_spec_rects", "_rebuild_from_template", "_require_one_grid_shape",
    "_resolve_lookup_key", "_resolve_options", "_sanitize_nan", "_slice_span",
    "_split_report_entries", "_squeeze_grid", "_squeeze_template_axes", "_subplot_rect",
    "_sweep_stale_tempfiles", "_title_keyed_axes", "_toolbar_clearance", "_vega_compat_report",
    "_warn_about_text_overflow", "figure_from_template", "load_data", "load_data_xarray",
    "load_template", "select_panel", "subplots", "subplots_from_groups",
]
