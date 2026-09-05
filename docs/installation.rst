Installation
============

.. code-block:: bash

   pip install plotpress            # SVG + interactive HTML + PNG/PDF export
   pip install plotpress[full]      # + every real end-user feature (viewers + xarray)
   pip install plotpress[contrib]   # + everything a contributor needs

The standard install covers **all file output** -- SVG, interactive HTML, PNG
and vector PDF -- with pure-wheel dependencies (NumPy, Pillow, svglib, reportlab)
that install everywhere: servers, CI and notebooks. ``[full]`` is likely what
you want if you're reaching for more than that at all; pick one of the
narrower extras below instead only when the weight of the others (``[qt]``'s
PyQt6 stack in particular) matters.

Individual extras
------------------

Every extra below also stays installable on its own, or combined in one
command (``pip install plotpress[gui,xarray]``), for anyone who wants less
than the full bundle. ``[viewers]`` bundles the first three; ``[full]`` adds
``[xarray]`` on top of that -- every real end-user feature in one command:

==============  ==========================================================
Extra           Adds
==============  ==========================================================
``[gui]``       ``fig.show()`` native window via pywebview / WebView2
``[qt]``        embed an interactive figure in a PyQt/PySide app (``fig.show_qt()``)
``[jupyter]``   ``show_in_jupyter()``: the interactive toolbar embedded inline in a notebook
``[xarray]``    ``load_data_xarray()``: recovered grid data as one labeled ``xarray.Dataset``
==============  ==========================================================

``[contrib]`` similarly bundles the four extras below -- everything needed to
run the full test suite, benchmarks, and build the docs, in one command:

==============  ==========================================================
Extra           Adds
==============  ==========================================================
``[dev]``       pytest (run the test suite)
``[browser]``   point-picking's end-to-end tests (drive the interactive HTML in a real, headless browser)
``[bench]``     matplotlib, seaborn, plotly (the benchmark comparison and cross-library parity tests)
``[docs]``      Sphinx + the gallery-building toolchain (build ``docs/`` locally)
==============  ==========================================================

Only the native ``fig.show()`` window needs the ``[gui]`` extra, because it
pulls a desktop webview stack (pythonnet on Windows, pyobjc on macOS, system
GTK/WebKit on Linux). Without it, ``fig.show()`` falls back to opening the figure
in the default browser. ``[qt]``, ``[xarray]``, and ``[jupyter]`` are each
similarly narrow: only the one named feature needs the extra dependency, and
everything else in plotpress works without it.
