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

Log scales, aspect, layout
--------------------------

.. code-block:: python

   ax.set_xscale("log"); ax.set_yscale("log")   # or ax.loglog(x, y)
   ax.set_aspect("equal")                        # circles look circular
   fig.tight_layout()                            # auto-margins, no overflow
   ax.annotate("peak", xy=(x0, y0), xytext=(x1, y1), arrowprops={})
   fig.suptitle("Overview")
