simpleplot
==========

A **lightweight, dependency-light** plotting library that renders **SVG and
self-contained interactive HTML** through a **matplotlib-shaped API** -- with
**no global state** and **no compiled extension**, so it installs everywhere
``pip`` runs.

.. code-block:: python

   import simpleplot
   import numpy as np

   fig, ax = simpleplot.subplots()
   x = np.linspace(0, 4 * np.pi, 400)
   ax.plot(x, np.sin(x), label="sin")
   ax.plot(x, np.cos(x), label="cos", linestyle="--")
   ax.set_xlabel("x"); ax.set_ylabel("y"); ax.legend()

   fig.save("out.svg")                    # static vector SVG
   fig.save("out.png")                    # raster PNG
   fig.save("out.html", interactive=True) # interactive toolbar

What it is for
--------------

simpleplot is **not a matplotlib replacement**, and it does not try to match
matplotlib's twenty years of breadth (no polar or 3-D axes, one font-metric
family -- see :ref:`limitations`). It aims at a narrower, underserved spot:
plotting where matplotlib's install footprint or global state gets in the way.

Reach for simpleplot when you want to:

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
"Plot types" reference.

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
   user_guide/limitations

.. toctree::
   :maxdepth: 2
   :caption: Reference

   auto_examples/index
   api
