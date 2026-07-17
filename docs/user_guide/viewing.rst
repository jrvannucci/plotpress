Viewing figures
===============

A figure can be *viewed* in several ways, from a static image to a fully
interactive window. Nothing is global -- you always view a specific ``Figure``.

At a glance
-----------

.. list-table::
   :header-rows: 1
   :widths: 26 40 16 18

   * - Surface
     - How
     - Interactive?
     - Needs
   * - Browser (static)
     - ``fig.save("f.svg")`` / ``"f.png"`` then open the file
     - no
     - --
   * - Browser (interactive)
     - ``fig.save("f.html", interactive=True)`` then open the file
     - **yes**
     - --
   * - Jupyter (inline)
     - evaluate ``fig`` in a cell
     - static
     - --
   * - Jupyter (interactive)
     - embed ``fig.to_html()`` in an ``<iframe>`` (below)
     - **yes**
     - --
   * - Native window
     - ``fig.show()``
     - **yes**
     - ``[gui]``
   * - Qt window / widget
     - ``fig.show_qt()`` or ``simpleplot.qt.SimplePlotWidget``
     - **yes**
     - ``[qt]``
   * - Embedded
     - drop ``fig.to_svg()`` / ``fig.to_html()`` into your own page
     - optional
     - --

In a browser
------------

The most portable options are files you double-click:

.. code-block:: python

   fig.save("figure.svg")                       # vector, static
   fig.save("figure.html", interactive=True)    # full toolbar, self-contained

.. figure:: /_static/view_static.png
   :alt: A static simpleplot figure rendered in a browser
   :width: 100%

   A saved SVG (or PNG) opened in a browser -- vector, portable, no toolbar.

The interactive HTML is a single self-contained file (inlined SVG + JS, no
external requests), so it opens offline and is easy to share. See
:doc:`interactivity` for the toolbar.

In Jupyter
----------

Evaluating a figure in a notebook cell displays it **inline as static SVG**
(via ``Figure._repr_svg_``) -- crisp, vector, no toolbar:

.. code-block:: python

   fig, ax = simpleplot.subplots()
   ax.plot(x, y)
   fig                     # renders inline

.. figure:: /_static/view_jupyter.png
   :alt: A simpleplot figure rendered inline in a Jupyter notebook cell
   :width: 100%

   Evaluating ``fig`` in a notebook cell renders it inline as static SVG
   (``Figure._repr_svg_``).

For the **interactive** toolbar *inside* a notebook, embed the self-contained
HTML in an ``<iframe>`` (which isolates and runs the inlined JS):

.. code-block:: python

   from IPython.display import HTML

   html = fig.to_html(interactive=True).replace('"', "&quot;")
   HTML(f'<iframe srcdoc="{html}" width="720" height="520" '
        f'style="border:0"></iframe>')

Alternatively, write an ``.html`` file and open it, or pop the figure out into a
native window with ``fig.show()``.

Native window
-------------

``fig.show()`` opens the figure in a native OS window (pywebview / WebView2 on
Windows, WebKit on macOS, GTK/WebKit on Linux) with the full toolbar. It needs
the ``[gui]`` extra and blocks until the window is closed; without it,
``fig.show()`` falls back to opening the default browser.

.. code-block:: python

   fig.show()                               # native window (or browser fallback)
   markers = fig.show(wait_for_extract=True) # block, return picked data to Python

.. figure:: /_static/view_window.png
   :alt: The native simpleplot window with its interactive toolbar
   :width: 100%

   ``fig.show()`` -- a native OS window hosting the same interactive figure,
   with the Span / Zoom / Point Pick / Annotate / Reset / Extract toolbar. The
   interactive ``.html`` file looks the same in a browser.

See :doc:`output` for ``wait_for_extract`` and the extraction format.

In a PyQt / PySide app
----------------------

For Qt-based desktop apps, ``simpleplot.qt`` renders the interactive figure
in a ``QWebEngineView`` -- the *same* toolbar (span / zoom / point-pick /
annotate / sliders / extract), reusing the HTML renderer rather than
reimplementing it. It works with **PyQt6**, **PySide6**, or **PyQt5** and needs
the ``[qt]`` extra (``pip install simpleplot[qt]``).

Quick standalone window:

.. code-block:: python

   fig.show_qt()                 # or: import simpleplot.qt as spqt; spqt.view(fig)

``SimplePlotWidget`` is a plain ``QWidget``, so it embeds into any layout of your
own application like any other widget:

.. code-block:: python

   from simpleplot.qt import SimplePlotWidget

   plot = SimplePlotWidget(fig)          # a QWidget
   my_layout.addWidget(plot)             # drop it anywhere

   plot.set_figure(other_fig)            # redraw with a different figure
   plot.markers(lambda recs: print(recs))  # async: hand picked markers to Python

The widget owns a ``QWebEngineView`` (exposed as ``plot.view`` for further
customization) and loads the document from a temporary file, so even large,
mesh-heavy figures render (``QWebEngineView.setHtml`` alone caps at ~2 MB). Pass
``pick_precision=`` to shrink the embedded point-pick data for big figures, just
as with :meth:`~simpleplot.Figure.to_html`.

Embedded in your own page or app
--------------------------------

``fig.to_svg()`` and ``fig.to_html()`` return strings, so a figure drops
straight into a template, dashboard, report, or web response -- no files and no
server round-trip:

.. code-block:: python

   svg = fig.to_svg()               # inline vector, for reports / emails
   page = f"<article>{svg}</article>"

   interactive = fig.to_html()      # standalone interactive document
