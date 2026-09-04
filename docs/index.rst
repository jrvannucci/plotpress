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

                       plotpress API
              (Figure, Axes -- matplotlib-shaped,
               no globals, no compiled extension)
                            |
                            v
                      one Figure object
                            |
     +----------+----------+----------+----------+----------+
     v          v          v          v          v          v
   .svg       .png       .pdf       .html        Vega       Vega-Lite
  (vector,  (raster,   (vector,   (self-        v5 JSON     v5 JSON
   the core   Pillow)   svglib +   contained,   spec        spec, a
   format)              reportlab) SVG + JS,    (real       stricter,
                                    no server    pixel-      more
                                    round trip)  space       declarative
                                                  marks)      grammar

``fig.save(path, ...)`` dispatches on the file extension for the first
four; ``fig.to_vega()`` / ``fig.to_vega_lite()`` return a JSON
specification as a plain ``dict`` for a separate Vega/Vega-Lite runtime to
render, rather than a rendered artifact -- useful for handing a figure to
an existing Vega-based dashboard or notebook instead of embedding
plotpress's own SVG/JS. See :doc:`user_guide/architecture` for exactly how
much of the rendering pipeline each of these six actually shares, and where
a format gets its own dedicated path instead.

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
