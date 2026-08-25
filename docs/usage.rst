Usage
=====

Figures, not globals
--------------------

Everything hangs off a :class:`~plotpress.Figure`. ``plotpress.subplots()``
returns ``(fig, axes)`` just like matplotlib's ``plt.subplots()`` -- but there is
no global "current figure/axes" and no global ``rcParams``.

.. code-block:: python

   import plotpress
   import numpy as np

   fig, axes = plotpress.subplots(1, 2, figsize=(10, 4))
   x = np.linspace(0, 10, 200)
   axes[0].plot(x, np.sin(x)); axes[0].set_title("sin")
   axes[1].scatter(x, np.cos(x), s=8); axes[1].set_title("cos")
   fig.tight_layout()

.. _matplotlib-shaped-api:

How close is the matplotlib API?
--------------------------------

The object-oriented core is deliberately matplotlib-*shaped*: ``Figure`` /
``Axes`` with ``plot``, ``scatter``, ``bar``, ``hist``, ``pcolormesh``,
``set_xlabel`` / ``set_ylabel`` / ``set_title``, ``set_xlim`` / ``set_ylim``,
``grid``, ``legend``, ``colorbar``, ``twinx`` / ``twiny``, log scales and the
``"C0"``..``"CN"`` colour cycle all behave as you would expect. Code written
against ``fig, ax = plt.subplots()`` usually ports by changing the import.

It is a **shaped** API, not a drop-in one. There is no ``pyplot`` state machine
(``plt.plot`` / ``plt.gca`` / ``plt.savefig``), no ``rcParams``, and the long
tail of matplotlib keyword arguments and plot types is not all present. Treat
the :ref:`gallery <gallery>` as the compatibility surface: if a call appears
there, it works the same way; if it doesn't, assume it needs adapting rather
than a straight copy. Known gaps and trade-offs are catalogued under
:ref:`limitations`.

Output surfaces
---------------

One scene, many targets:

============================================  ==================================
Call                                          Result
============================================  ==================================
``fig.save("x.svg")``                         static vector SVG
``fig.save("x.png")`` / ``fig.savefig(...)``  raster PNG
``fig.save("x.pdf")``                          vector PDF
``fig.save("x.gif")``                          looping GIF (plot_frames())
``fig.save("x.html", interactive=True)``       interactive HTML (JS toolbar)
``fig._repr_svg_()``                           inline SVG in Jupyter
``fig.show()``                                 native pop-up window (``[gui]``)
============================================  ==================================

Interactive figures
--------------------

Interactive HTML and pop-up output carry a self-contained JavaScript toolbar
(no external requests -- works under strict CSPs like Jupyter). Nothing is
active until a tool is selected:

* **Span** -- drag to pan a single plot's data window.
* **Zoom** -- wheel or box-drag to zoom *one* axes in data space (ticks recompute).
* **Point Pick** -- click to read the nearest data value; arrow keys step along
  the series; right-click deletes. Reports extra dims (``z``, ``c``, ...).

.. include:: _static/interactive/usage_pan_zoom_pick.rst.inc

* **Annotate Point** -- like Point Pick, but prompts for text and locks a
  user-written note to that datum instead of the auto-generated readout;
  still steppable by arrow key and still tracks pan/zoom.
* **Annotate Free** -- drop a user-written note anywhere on the figure, not
  locked to any datum -- including the margins or the gap between subplots.

.. include:: _static/interactive/usage_annotate.rst.inc

* **Reset** / **Extract** -- restore the view, or copy/download all markers and
  annotations as CSV/JSON (or hand them back to the kernel with
  ``fig.show(wait_for_extract=True)``).
* **Hide Annotations** -- a standalone toggle, not a mode: hides every pin and
  annotation without deleting any of them. Toggling it back to "Show
  Annotations" restores them exactly as they were, text included.

.. include:: _static/interactive/usage_hide_annotations.rst.inc

3-D data via ``ax.plot_frames(...)`` adds a play/pause/step **slider** over the
extra dimension.

.. include:: _static/interactive/usage_frames.rst.inc

Every picked/extracted record carries ``axes`` and ``axes_title`` -- the
axes' own title, or a generated ``"axes N"`` when it has none, so a
multi-panel export always names its source panel.
:meth:`~plotpress.axes.Axes.set_pick_context` attaches further per-axes
key/value context (e.g. a panel's own color) that rides along on every record
picked from it, and :meth:`~plotpress.axes.Axes.set_pickable` excludes an
axes from Point Pick/Annotate Point entirely -- Span, Zoom, and Annotate Free
are unaffected. See :doc:`user_guide/interactivity` for the full picture, and
:doc:`auto_examples/axes_features/plot_11_spine_color_grid` for
``set_pick_context`` used to surface a per-panel spine color.

.. include:: _static/interactive/usage_pick_context.rst.inc

Combining figures into a report
--------------------------------

:class:`~plotpress.Report` combines several figures into one self-contained
HTML file. Each figure keeps its own independent interactivity -- its own
toolbar, pan/zoom, point-picking, annotations -- because it is embedded in its
own ``<iframe>`` rather than spliced directly into the page: an interactive
figure's JS assumes it owns the page (fixed element ids, a document-level
toolbar), so several sharing one page directly would collide. Add figures
with :meth:`~plotpress.Report.add`, in the order they should appear, with an
optional title and details for each:

.. code-block:: python

   report = plotpress.Report(title="Weekly QA sweep",
                             description="Four sensor batches, one figure each.")
   report.add(fig_a, title="Batch A", details="Baseline run, no anomalies.")
   report.add(fig_b, title="Batch B", details="Elevated noise floor after 14:00.")
   report.save("qa_sweep.html")

Below: four figures, each its own 5x10 grid of independent ``pcolormesh``
panels -- every panel keeping its own title, axes, ticks, labels, and
colorbar -- combined into a single scrollable report.

.. include:: _static/interactive/usage_report.rst.inc

Reading data back out of a saved HTML
---------------------------------------

:func:`~plotpress.load_data` reads the plotted data straight back out of an
``interactive=True`` HTML file -- the original Python objects that built it
don't need to still be around. It returns a list of per-figure dicts (one
item for a bare figure's HTML, one per embedded figure for a
:class:`~plotpress.Report`'s), each mapping axes index to that panel's
series/mesh data plus its labels, limits, and scale:

.. code-block:: python

   figures = plotpress.load_data("qa_sweep.html")
   mesh = figures[0]["axes"][0]["meshes"][0]
   mesh["x"], mesh["y"]   # 1-D cell-center coordinates
   mesh["z"]              # 2-D array, shape (ny, nx)

See :doc:`auto_examples/data_roundtrip/plot_01_reload_mesh_grid_as_lines` and
:doc:`auto_examples/data_roundtrip/plot_02_reload_and_fft_mesh_grid` for two
worked examples: reloading a 30-panel ``pcolormesh`` grid and replotting one
x-slice per panel as a line, and reloading the same grid to run a 2-D FFT
over every panel.

Log scales, aspect, layout
--------------------------

.. code-block:: python

   ax.set_xscale("log"); ax.set_yscale("log")   # or ax.loglog(x, y)
   ax.set_aspect("equal")                        # circles look circular
   fig.tight_layout()                            # auto-margins, no overflow
   ax.annotate("peak", xy=(x0, y0), xytext=(x1, y1), arrowprops={})
   fig.suptitle("Overview")
