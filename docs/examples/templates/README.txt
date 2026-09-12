.. _templates_gallery:

Reusable, data-free figure templates
-------------------------------------

``Figure.to_template()``/``save_template()`` snapshot a figure's own
structure and styling -- grid shape, group boxes, spine colors, tick
overrides, ids, twin/secondary/inset overlays, and its ``Style`` -- with no
plotted data in it at all. ``plotpress.load_template()``/
``figure_from_template()`` rebuild a blank, identically styled figure from
that snapshot. These examples build a template once and reuse it, unmodified,
across unrelated datasets.
