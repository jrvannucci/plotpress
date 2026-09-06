plotpress
==========

Scientific plots you can explore, share, and reuse.

A **fast, dependency-light** plotting library for scientific computing, with a
**matplotlib-shaped API** and **no compiled extension** -- so it installs
everywhere Python does, from notebooks and scientific applications to CI
pipelines and offline environments.

.. code-block:: python

   import plotpress
   import numpy as np

   fig, ax = plotpress.subplots()
   x = np.linspace(0, 4 * np.pi, 400)
   ax.plot(x, np.sin(x), label="sin")
   ax.plot(x, np.cos(x), "--", label="cos")
   ax.set_xlabel("x"); ax.set_ylabel("amplitude"); ax.legend()

   fig.save("figure.svg")                    # static vector SVG
   fig.save("figure.png")                    # raster PNG
   fig.save("figure.html", interactive=True) # self-contained interactive toolbar

One figure. Many destinations.
-------------------------------

Build the ``Figure`` once from the matplotlib-shaped API, then choose the
output when you need it -- no separate figure per format, no plugin to
install::

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
render -- a bridge to web-native visualization for handing a figure to an
existing Vega-based dashboard or notebook, without rebuilding the plot from
scratch. See :doc:`user_guide/architecture` for exactly how much of the
rendering pipeline each of these six actually shares, and where a format
gets its own dedicated path instead.

A plot doesn't have to be a dead image.
-----------------------------------------

A PNG tells someone what your data looked like. An interactive plotpress
figure lets them explore what was plotted -- and recover the data behind it.

When you save an interactive HTML figure, plotpress embeds the plotted data
alongside the figure itself. The result is one self-contained file: open it
in a browser, attach it to a paper, or archive it -- no server, no
plotpress, no Python needed to view it. Months later, the same file can
still be read back with Python::

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

The figure becomes more than an image -- it becomes a portable
representation of the data it displays, ready to inspect, transform, or
replot. A freeform :meth:`~plotpress.figure.Figure.add_axes` rect, an
inset, or a colorbar axes has no grid cell to rebuild from -- its index is
listed in ``layout["omitted_axes"]`` instead of silently vanishing. See
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

Built for scientific Python
------------------------------

plotpress gives you a familiar, matplotlib-shaped interface without
requiring matplotlib itself:

- **Familiar API** -- create figures and axes, plot data, configure labels
  and ticks, build legends, arrange subplots, and style figures the way
  scientific Python users already expect.
- **No pyplot, no globals** -- a ``Figure`` owns its own axes and its own
  ``Style``. There is no process-wide "current figure" and no global
  ``rcParams`` to get in the way of applications, libraries, or concurrent
  workflows. :func:`plotpress.subplots` returns ``(fig, axes)`` just like
  ``plt.subplots()`` -- but touches no global state.
- **Dependency-light** -- built around Python and NumPy, with no compiled
  extension. Hot paths are vectorized (coordinate formatting, min/max
  decimation for huge lines), so it installs, and runs, cleanly in
  environments where a large visualization stack isn't practical.

It is shaped, not drop-in: there's no ``pyplot`` state machine and not every
matplotlib keyword is present -- treat the gallery as the compatibility
surface.

Interactive when you need it
--------------------------------

Static figures are great for papers. Interactive figures are great for
everything else. plotpress can turn a figure into a self-contained HTML
document with a toolbar for:

- Pan and zoom, over every axes at once or one at a time
- Point picking, with extraction to CSV/JSON
- Annotations, with a draggable label independent of the point it's pinned to
- Frame and data sliders for 3-D/animated data (:meth:`~plotpress.axes.Axes.plot_frames`)
- Interactive meshes -- picking works cell-by-cell on a ``pcolormesh``, not just a line's ``x``/``y``
- Custom JavaScript tools, added to the same toolbar via ``extra_js``

There is no server to run and no external application required -- the HTML
travels with its data and opens directly in a browser. Send someone a file,
not a service they have to install. See :doc:`user_guide/interactivity` for
the full toolbar reference.

Scientific visualization, end to end
----------------------------------------

plotpress is designed around the way scientific figures actually get used::

   Explore ──► Analyze ──► Visualize ──► Share ──► Publish ──► Archive ──► Reuse
      ▲                                                                       │
      └───────────────────────────────────────────────────────────────────────┘

- **Explore** -- interact with a measurement, simulation, image, or spectrum
  while building an experiment or analysis (pan/zoom, point-picking).
- **Analyze** -- the same figure workflow for signal processing, statistics,
  and multidimensional data.
- **Visualize** -- build and style the figure: plot, arrange subplots, apply
  colormaps and normalization.
- **Share** -- hand an interactive HTML figure to a collaborator -- no
  server, nothing to install on their end.
- **Publish** -- export a publication figure as SVG/PNG/PDF, or publish a
  self-contained HTML figure that carries its own data.
- **Archive** -- keep the figure and its plotted data together in one
  portable file.
- **Reuse** -- load the figure back with ``plotpress.load_data()``, recover
  the data, and analyze or replot it -- the cycle starts again from Explore.

Made for real scientific workloads
--------------------------------------

plotpress isn't just a handful of basic plotting primitives -- it covers the
kinds of figures scientists actually build:

- **Signal processing** -- power spectral density, cross-spectral density,
  coherence, spectrograms, autocorrelation, cross-correlation, and
  magnitude/angle/phase spectra (pure-NumPy Welch estimators).
- **2-D and gridded data** -- images, meshes (including curvilinear grids),
  contours, vector fields, and logarithmic/power/symlog normalization for
  large scientific fields.
- **Statistical visualization** -- histograms, 2-D histograms, box plots,
  violin plots, ECDFs, KDEs, event rasters, error bars, and hexbins.
- **Complex figures** -- subplot grids, shared axes, colorbars (including
  one shared across several axes), secondary axes, inset axes, grouped
  panels, figure-level titles/labels, and mixed layouts.
- **Animation** -- animated lines and meshes with frame sliders, exportable
  as self-contained looping GIFs.
- **Large figures** -- built to keep object and output-node counts under
  control, so a very large multi-panel figure stays practical; see the
  :doc:`/auto_examples/grouping/plot_13_full_scale_demo` example (500
  ``pcolormesh`` panels across 250 grouped, individually colorbar'd pairs).

See the :ref:`example gallery <gallery>` for a figure per plot type,
:ref:`large-scale figures <scale_gallery>` for build-time and file-size
comparisons against matplotlib, :ref:`live streaming <live_streaming_gallery>`
for watching data update in a Qt window as it's collected, and
:ref:`real applications <applications>` for a hundred-odd figures built from
the data real measurements produce, grouped by field.

Designed for constrained environments
-----------------------------------------

Scientific software doesn't always run on a developer laptop. plotpress
targets environments where a conventional plotting stack can be hard to
deploy: locked-down networks, offline systems, minimal containers, CI,
scientific and web applications, Pyodide/WASM, library and server code, and
shared computing environments. No GUI is required to create a figure, no
global plotting state is required, and interactive HTML needs no running
server.

plotpress is **not a matplotlib replacement**, and it does not try to match
matplotlib's twenty years of breadth (no geographic projections or
triangulated grids, a handful of font-metric families, and its polar / 3-D
axes are projected onto the 2-D core rather than a dedicated pipeline --
see :ref:`limitations`). It aims at a narrower, underserved spot: plotting
where matplotlib's install footprint or global state gets in the way.

Reach for **matplotlib** (or seaborn, Plotly) when you need publication-grade
typography across arbitrary fonts, the full plot-type gallery, polar/3-D, or
the deep ecosystem that pandas, seaborn and scikit-learn plot into. The
:ref:`matplotlib-shaped API <matplotlib-shaped-api>` means moving between
them is mostly mechanical.

One API. One figure. Many representations.
-----------------------------------------------

The figure should be independent of where you eventually use it::

                            ┌─────────── SVG
                            │
                            ├─────────── PNG
                            │
   Scientific Python ──► Figure ─────── PDF
                            │
                            ├─────────── HTML ──► explore
                            │                     share
                            │                     recover data
                            │
                            ├─────────── Vega
                            │
                            └─────────── Vega-Lite

Create the visualization once, choose how to render it later, and keep the
data available for whenever you need it again.

Start plotting
------------------

.. code-block:: bash

   pip install plotpress

.. code-block:: python

   import plotpress
   fig, ax = plotpress.subplots()
   ax.plot(x, y)
   fig.save("figure.html", interactive=True)

Explore it in a browser. Share the file. Archive it. Load it again.

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
