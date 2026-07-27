Installation
============

.. code-block:: bash

   pip install plotpress            # SVG + interactive HTML + PNG/PDF export
   pip install plotpress[gui]       # + native pop-up window (fig.show())
   pip install plotpress[dev]       # + pytest (contributors)
   pip install plotpress[bench]     # + matplotlib (benchmark comparison)

The standard install covers **all file output** -- SVG, interactive HTML, PNG
and vector PDF -- with pure-wheel dependencies (NumPy, Pillow, svglib, reportlab)
that install everywhere: servers, CI and notebooks.

Optional extras
---------------

======================  ==========================================================
Extra                   Adds
======================  ==========================================================
``[gui]``               ``fig.show()`` native window via pywebview / WebView2
``[dev]``               pytest (run the test suite)
``[bench]``             matplotlib (the benchmark comparison)
======================  ==========================================================

Only the native ``fig.show()`` window needs the ``[gui]`` extra, because it
pulls a desktop webview stack (pythonnet on Windows, pyobjc on macOS, system
GTK/WebKit on Linux). Without it, ``fig.show()`` falls back to opening the figure
in the default browser.
