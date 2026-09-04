plotpress
==========

A **lightweight, dependency-light** plotting library that renders **SVG and
self-contained interactive HTML** through a **matplotlib-shaped API** -- with
**no global state** and **no compiled extension**, so it installs everywhere
``pip`` runs.

.. code-block:: python

   import plotpress
   import numpy as np

   fig, ax = plotpress.subplots()
   x = np.linspace(0, 4 * np.pi, 400)
   ax.plot(x, np.sin(x), label="sin")
   ax.plot(x, np.cos(x), label="cos", linestyle="--")
   ax.set_xlabel("x"); ax.set_ylabel("y"); ax.legend()

   fig.save("out.svg")                    # static vector SVG
   fig.save("out.png")                    # raster PNG
   fig.save("out.html", interactive=True) # interactive toolbar

One figure, several outputs
----------------------------

The same ``Figure`` built once from the matplotlib-shaped API renders to
every format below -- no separate figure per output, no plugin to install::

                                       one Figure object
                                               │
       ┌───────────────┬───────────────┬───────┴───────┬───────────────┬───────────────┐
       ▼               ▼               ▼               ▼               ▼               ▼
     .svg            .png            .pdf            .html           Vega          Vega-Lite
   (vector,        (raster,        (vector,        (SVG + JS       (v5 JSON,      (v5 JSON, a
   the core         Pillow)        svglib +       inlined --      real pixel-   stricter, more
    format)                       reportlab)       no server     space marks)     declarative
                                                  round trip)                      grammar)

``fig.save(path, ...)`` dispatches on the file extension for the first
four; ``fig.to_vega()`` / ``fig.to_vega_lite()`` return a JSON
specification as a plain ``dict`` for a separate Vega/Vega-Lite runtime to
render, rather than a rendered artifact -- useful for handing a figure to
an existing Vega-based dashboard or notebook instead of embedding
plotpress's own SVG/JS. See :doc:`user_guide/architecture` for exactly how
much of the rendering pipeline each of these six actually shares, and where
a format gets its own dedicated path instead.

Reading a figure back out of HTML
------------------------------------

The interactive HTML above isn't a one-way trip: it embeds the plotted data
and the figure's own layout as JSON alongside the SVG, so a later process --
with none of the Python objects that built it still around -- can read a
figure back out and rebuild it::

             a saved .html (Figure.save(path, interactive=True))
                   embeds <script id="plotpress-pick"> and
                      id="plotpress-layout"> per figure
                                      │
                                      ▼
                          plotpress.load_data(path)
                      parses that embedded JSON back out
                                       │
                        ┌──────────────┴──────────────┐
                        ▼                             ▼
                    "layout"                       "axes"
                (grid shape, each            (recovered series/
             axes' own decorations,        mesh/pie data per axes,
               groups, sup-title)              keyed by title)

                        │
                        ▼
                    plotpress.subplots_from_layout(layout)
                    rebuilds the grid and every axes' own
                  decorations -- not the plotted data itself
                                      │
                                      ▼
                  a new, already-labeled Figure -- ready for
                  the caller to replot the recovered "axes"
                                data back into

A freeform :meth:`~plotpress.figure.Figure.add_axes` rect, an inset, or a
colorbar axes has no grid cell to rebuild from -- its index is listed in
``layout["omitted_axes"]`` instead of silently vanishing. See
:ref:`reading-html-data` for the full API and
:doc:`/auto_examples/data_roundtrip/index` for worked examples.

For the common case of a *uniform* grid -- every axes its own single
``pcolormesh`` or line series, all the same shape --
:func:`~plotpress.load_data_xarray` skips the title-keyed dict above
entirely and reads the same file straight into one ``xarray.Dataset``
indexed by row/column instead, with the recovered ``layout`` still
available under ``ds.attrs["layout"]`` for
:func:`~plotpress.subplots_from_layout`. See
:doc:`/auto_examples/data_roundtrip/index` for both paths worked through
end to end.

What it is for
--------------

plotpress is **not a matplotlib replacement**, and it does not try to match
matplotlib's twenty years of breadth (no geographic projections or triangulated
grids, a handful of font-metric families, and its polar / 3-D axes are projected onto the
2-D core rather than a dedicated pipeline -- see :ref:`limitations`). It aims at
a narrower, underserved spot: plotting where matplotlib's install footprint or
global state gets in the way.

Reach for plotpress when you want to:

- **Ship plots from a constrained runtime** -- locked-down servers, minimal
  containers, Pyodide/WASM, or CI -- where a pure-Python + NumPy install with no
  build toolchain and no per-platform wheels matters.
- **Embed in web apps or notebooks** as SVG or self-contained interactive HTML
  whose JS makes no external requests (works under strict CSPs like Jupyter).
- **Write library or server code** that should never touch a global "current
  figure" or a process-wide ``rcParams``.

Reach for **matplotlib** (or seaborn, Plotly) when you need publication-grade
typography across arbitrary fonts, the full plot-type gallery, polar/3-D, or the
deep ecosystem that pandas, seaborn and scikit-learn plot into. The
:ref:`matplotlib-shaped API <matplotlib-shaped-api>` means moving between them is
mostly mechanical.

Highlights
----------

- **No pyplot / no globals** -- a ``Figure`` owns its axes and its own ``Style``.
- **Pure Python + NumPy**, no compiled extension -- installs everywhere ``pip`` does.
- **SVG-first**, with PNG/PDF export and self-contained interactive HTML.
- **matplotlib-shaped API** so moving code either direction is mostly mechanical.

See the :ref:`example gallery <gallery>` for plots recreating matplotlib's
"Plot types" reference, :ref:`large-scale figures <scale_gallery>` for the cases
where build time and file size are the constraint -- including a head-to-head
against matplotlib -- :ref:`live streaming <live_streaming_gallery>` for
watching data update in a Qt window as it's collected, and
:ref:`real applications <applications>` for a hundred-odd figures built from
the data real measurements produce, grouped by field.

.. toctree::
   :maxdepth: 1
   :caption: Getting started

   installation
   usage
   performance

.. toctree::
   :maxdepth: 2
   :caption: User guide

   user_guide/plotting
   user_guide/axes
   user_guide/figures
   user_guide/styling
   user_guide/output
   user_guide/viewing
   user_guide/interactivity
   user_guide/architecture

.. toctree::
   :maxdepth: 2
   :caption: Examples

   auto_examples/index
   auto_scale/index

.. toctree::
   :maxdepth: 2
   :caption: Live plotting

   auto_live_streaming/index

.. toctree::
   :maxdepth: 2
   :caption: Real applications

   auto_applications/index

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api

.. toctree::
   :maxdepth: 2
   :caption: Limitations

   user_guide/limitations
