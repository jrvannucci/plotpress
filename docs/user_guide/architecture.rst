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
``axes3d.py``                 ``Axes3D``: orthographic 3-D projection + surface
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
============================  ==================================================

Performance
-----------

Avoiding matplotlib's per-``Artist`` Python overhead makes plotpress much
faster for **many-axes** figures, and rasterizing meshes to one image makes
``pcolormesh`` dramatically cheaper. Even a single huge polyline is a win:
coordinate formatting is vectorized with ``numpy.char`` and monotonic lines are
min/max-decimated per pixel column before serialization (visually lossless), so
a 100k-point line is several times faster than matplotlib -- all in pure Python.
See the project ``README`` for benchmark numbers.
