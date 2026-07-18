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
:class:`~simpleplot.figure.Figure` owns its axes and its own
:class:`~simpleplot.style.Style`. ``simpleplot.subplots()`` returns a fresh,
fully independent figure.

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
``artists.py``                data-only scene primitives
``style.py``                  per-figure ``Style`` (replaces ``rcParams``)
``transform.py``              vectorized data->pixel transforms (linear + log)
``colors.py``                 ``Normalize``, colormap LUTs
``ticker.py``                 "nice number" + log tick locations
``primitives.py``             backend-agnostic primitives + artist converter
``svg.py``                    SVG emitter over the shared primitives
``png.py``                    stdlib-only PNG encoder for image layers
``raster.py``                 Pillow PNG backend; svglib/reportlab PDF
``fonts/``                    bundled Helvetica metrics (layout only)
``_interactive.py``           inlined vanilla JS: toolbar, zoom, pick, sliders
============================  ==================================================

Performance
-----------

Avoiding matplotlib's per-``Artist`` Python overhead makes simpleplot much
faster for **many-axes** figures, and rasterizing meshes to one image makes
``pcolormesh`` dramatically cheaper. Even a single huge polyline is a win:
coordinate formatting is vectorized with ``numpy.char`` and monotonic lines are
min/max-decimated per pixel column before serialization (visually lossless), so
a 100k-point line is several times faster than matplotlib -- all in pure Python.
See the project ``README`` for benchmark numbers.
