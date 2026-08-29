.. _custom_interactivity_gallery:

Custom interactive JS
=========================

``fig.save(..., extra_js=...)``/``fig.to_html(..., extra_js=...)`` inline a
caller-supplied JS string into the page -- to *add* to plotpress's own
toolbar (``include_default_js`` left at its default ``True``:
``window.plotpressAddTool(...)`` registers a real button in the same row,
joining the same single-selection group as Span/Zoom/Point Pick if given a
``mode``), or to *replace* it entirely (``include_default_js=False`` drops
plotpress's own JS -- ``extra_js`` becomes the only interactivity this page
gets, built from the raw ``#plotpress-meta``/``#plotpress-pick`` JSON
payloads and ``#plotpress-svg`` directly). Nothing about either fetches
anything external on its own -- ``extra_js`` is inlined the same as
plotpress's own JS, same as every other interactive HTML plotpress writes.
