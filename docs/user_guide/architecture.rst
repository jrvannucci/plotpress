How it works
============

Design in one sentence
----------------------

Artists are data holders; their geometry is computed once into backend-agnostic
primitives (``primitives.py``) that ``svg.py`` and ``raster.py`` emit. There is
no global state, and no compiled extension -- it is pure Python + NumPy.

No global state
---------------

Unlike matplotlib, there is no ``pyplot`` layer and no global ``rcParams``. A
:class:`~plotpress.figure.Figure` owns its axes and its own
:class:`~plotpress.style.Style`. ``plotpress.subplots()`` returns a fresh,
fully independent figure.

This is what makes building axes **threadable and parallelizable**: with
nothing shared across figures, several threads each building their own
independent ``Figure`` have no mutable global state to race over. Across
*processes* the same property means a ``Figure``/``Axes`` pickles cleanly --
no global registry to somehow reconcile on the other side -- which is why a
``joblib``/``multiprocessing`` worker can build a real, complete axes
(fit + plot in one call) in its own process and hand it back rather than
returning only plain arrays for the parent to replot. What a process
boundary does *not* preserve is object identity: the axes that comes back
is a copy, never the original, so :meth:`~plotpress.figure.Figure.adopt_axes`
merges it into the real figure in place of whichever of its own axes shares
that grid position. See :doc:`figures` ("Building a figure across
processes") for the full API, and
:doc:`../auto_examples/parallel_building/plot_01_joblib_lazy_parquet_fit`
for a worked example -- a lazy parquet scan and curve fit inside a joblib
worker, merged back with ``adopt_axes()``.

SVG-first, selectively raster
-----------------------------

Lines, bars, scatter, contours and text are vector ``<path>``/``<text>``. Only
2-D fields (``pcolormesh``, ``imshow``, ``hist2d``, curvilinear contour fill)
are rasterized -- each to a *single* embedded ``<image>``, so a 500x500 grid
costs one DOM node instead of 250,000 rectangles. Scatter markers are
zero-length round-capped strokes, so ``vector-effect: non-scaling-stroke`` keeps
them a constant size under interactive zoom.

Module layout
-------------

============================  ==================================================
Module                        Responsibility
============================  ==================================================
``figure.py``                 ``Figure``, ``subplots()``, layout, save/show
``axes.py``                   ``Axes``: plotting methods, limits, autoscale
``polar.py``                  ``PolarAxes``: (theta, r) projection + polar frame
``_spectral.py``              pure-NumPy Welch spectral estimators
``artists.py``                data-only scene primitives
``style.py``                  per-figure ``Style`` (replaces ``rcParams``)
``transform.py``              vectorized data->pixel transforms (linear + log)
``colors.py``                 ``Normalize``, colormap LUTs
``ticker.py``                 "nice number" + log tick locations
``primitives.py``             backend-agnostic primitives + artist converter
``svg.py``                    SVG emitter over the shared primitives
``png.py``                    stdlib-only PNG encoder for image layers
``raster.py``                 Pillow PNG backend; svglib/reportlab PDF
``fonts/``                    bundled width tables + the family registry (layout only)
``_interactive.py``           inlined vanilla JS: toolbar, zoom, pick, sliders
``vega.py``                   ``Figure.to_vega()``: a real Vega v5 JSON spec
``vega_lite.py``              ``Figure.to_vega_lite()``: a Vega-Lite v5 spec
============================  ==================================================

Compiling to other renderers
-----------------------------

plotpress already has one real, shared intermediate representation --
:func:`~plotpress.primitives.artist_to_prims`, converting an ``artists.py``
scene object into backend-agnostic pixel-space prims (``Path``, ``Markers``,
``Rect``, ``Segments``, ``PolygonBatch``, ``ImagePrim``). ``svg.py``,
``raster.py``, and *most* of ``vega.py`` all compile from that one shared
representation, not from three independent reimplementations of the same
geometry::

     Axes.artists (artists.py: Line2D, Bars, Pie, Text, ...)
                          │
              transform.py│  data space -> pixel space
                          v
              artist_to_prims()  (primitives.py)
              the one shared, backend-agnostic
              pixel-space representation
        ┌───────────────────┼───────────────────┐
        v                   v                   v
    svg.py              raster.py            vega.py
  (SVG string)       (PNG via Pillow,     (Vega v5 JSON,
                       PDF via svglib)      most mark kinds)

That diagram is honest only as far as it goes -- two real exceptions:

- **``_interactive.py`` is not a fourth compiler off the shared prims.** It is
  vanilla JS layered onto ``svg.py``'s own *output* -- pan/zoom/point-pick
  read and mutate the rendered SVG DOM in the browser, not a shared IR. There
  is no interactive-JS "compiler"; there is one hand-written JS payload bolted
  onto one specific SVG shape.
- **``vega.py`` has a second, un-shared path.** ``Line2D`` (unmarked),
  ``ScatterCollection``, ``Bars``, ``ErrorBar``, ``Stem``, ``Pie``, and
  ``Text``/``Annotation`` get their own dedicated builders in ``vega.py``,
  written directly against ``artists.py``'s fields rather than through
  ``artist_to_prims()`` -- real duplication with ``svg.py``'s renderers for
  the same artist kinds, not IR reuse. This isn't an oversight left
  unfixed: a Vega ``field``/``scale``-encoded mark (reactive to a runtime
  domain change) and a frozen pixel path are different *shapes* of output,
  not different syntax for the same one -- reusing the prims layer for those
  kinds would mean giving up that reactivity. See :mod:`plotpress.vega`'s own
  module docstring for the full trade-off.
- **``vega_lite.py`` barely touches the shared prims layer at all.**
  Vega-Lite's mark vocabulary is closed -- no raw path-per-datum mark the
  way Vega has -- so ``artist_to_prims()``'s pixel-space prims have
  nowhere to plug in for most artist kinds; almost every mark builder in
  ``vega_lite.py`` is hand-written directly against ``artists.py``'s own
  fields instead, a third independent translation of the same handful of
  artist kinds (the one partial exception is its mesh/image mark, which
  does reuse the same ``rgba()``/``extent()`` pair ``artist_to_prims()``'s
  own ``(QuadMesh, Image)`` branch reads). See :mod:`plotpress.vega_lite`'s
  own module docstring for its three fidelity tiers and the
  figure-composition algorithm Vega-Lite's grid-only layout model forces
  that neither ``vega.py`` nor any pixel-space backend needs.

How a page actually loads
^^^^^^^^^^^^^^^^^^^^^^^^^^

Two real paths exist today, and they load very differently::

    Figure.to_html(interactive=True)
      Figure.to_svg() + _interactive.py's JS
        --> one self-contained .html file (SVG and JS both inlined)
      Browser opens the file
        --> renders immediately; no other request, no separate render step

    Figure.to_vega() + a Vega-embed page (e.g. docs/conf.py's own
    generated Vega-export pages, or any Vega-runtime host)
      Figure.to_vega() --> a JSON spec (no picture, just data)
        --> embedded in a page next to <script src=".../vega-embed...">
      Browser opens the page
        --> downloads vega-embed's JS --> vegaEmbed() parses the JSON and
            draws the chart at LOAD TIME, in the browser -- nothing about
            the figure is pre-rendered by plotpress at all

Performance
-----------

Avoiding matplotlib's per-``Artist`` Python overhead makes plotpress much
faster for **many-axes** figures, and rasterizing meshes to one image makes
``pcolormesh`` dramatically cheaper. Even a single huge polyline is a win:
coordinate formatting is vectorized with ``numpy.char`` and monotonic lines are
min/max-decimated per pixel column before serialization (visually lossless), so
a 100k-point line is several times faster than matplotlib -- all in pure Python.
See the project ``README`` for benchmark numbers.
