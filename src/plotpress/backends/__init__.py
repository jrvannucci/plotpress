"""The output backends: what a Figure's scene renders itself *to*.

One entry point per format -- ``svg`` (the core renderer; everything else
either wraps its output or shares its geometry), ``raster`` (PNG via Pillow,
PDF via svglib/reportlab), ``vega``/``vega_lite`` (JSON specs for an external
Vega/Vega-Lite runtime), and ``_interactive`` (the vanilla-JS toolbar,
assembled from ``_js/``). See ``AGENTS.md``'s render-pipeline diagram at the
repo root for how they relate. No re-exports here -- import the submodule you
need directly, e.g. ``from plotpress.backends.svg import figure_to_svg``.
"""
