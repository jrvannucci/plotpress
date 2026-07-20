simpleplot
==========

A fast, **figure-centric**, **SVG-first** plotting library with a
matplotlib-like API and **no global state**.

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

Highlights
----------

- **No pyplot / no globals** -- a ``Figure`` owns its axes and its own ``Style``.
- **matplotlib-like API** for an easy port.
- **SVG-first**, with PNG/PDF export and self-contained interactive HTML.

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
