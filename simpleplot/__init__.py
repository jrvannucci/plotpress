"""simpleplot -- a fast, figure-centric, SVG-first plotting library.

Distinct from matplotlib in three ways:

1. **No global state.** There is no ``pyplot``, no "current figure/axes", no
   global ``rcParams``. Everything hangs off a :class:`Figure`, which owns its
   own :class:`Style`. Build a plot, and the figure holds everything it needs to
   render itself.
2. **matplotlib-like API.** ``Figure``/``Axes`` and methods like ``plot``,
   ``scatter``, ``pcolormesh``, ``set_xlabel``, ``legend`` mirror matplotlib so
   existing code is easy to port. ``simpleplot.subplots(...)`` returns
   ``(fig, axes)`` just like ``plt.subplots(...)`` -- minus the globals.
3. **SVG-first + fast.** Output is vector SVG (with embedded raster only for
   mesh/image layers), optionally interactive, and the architecture is built so
   the hot rendering paths can move to a Rust backend (Phase 2).

Example
-------
>>> import simpleplot
>>> fig, ax = simpleplot.subplots()
>>> ax.plot([0, 1, 2], [0, 1, 4], label="quadratic")
>>> ax.legend()
>>> fig.save("out.svg")
"""

from .colors import LogNorm, Normalize, available_colormaps, get_cmap
from .figure import Figure, subplots
from .style import Style

__version__ = "0.0.1"

__all__ = [
    "Figure",
    "subplots",
    "Style",
    "Normalize",
    "LogNorm",
    "get_cmap",
    "available_colormaps",
    "__version__",
]
