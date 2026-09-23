"""Optional GUI viewers, gated behind their own extras.

``qt.py`` embeds an interactive figure in a PyQt/PySide app (the ``qt``
extra). The native pop-up window ``Figure.show()`` falls back to (pywebview,
the ``gui`` extra) lives on ``Figure`` itself in ``plotpress/figure/_core.py``,
not here -- there was no second file to pair it with. No re-exports here --
import the submodule you need directly, e.g.
``from plotpress.gui.qt import PlotPressWidget``.
"""
