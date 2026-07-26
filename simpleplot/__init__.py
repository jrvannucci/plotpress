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
   mesh/image layers), optionally interactive. The hot paths are vectorized in
   NumPy and huge lines are decimated, so it is fast in **pure Python** -- no
   compiled extension, installs everywhere pip does.

Example
-------
>>> import simpleplot
>>> fig, ax = simpleplot.subplots()
>>> ax.plot([0, 1, 2], [0, 1, 4], label="quadratic")
>>> ax.legend()
>>> fig.save("out.svg")
"""

from .colors import (
    LogNorm, Normalize, PowerNorm, SymLogNorm, available_colormaps, get_cmap,
)
from .figure import Figure, subplots
from .style import Style

def _detect_version() -> str:
    """The installed version, however this copy of simpleplot is being run.

    Three cases, in order of precision. ``_version.py`` is written by
    versioningit at build time and is the exact string the artifact was built
    with. Failing that -- a source checkout that was never built, which is how
    the test suite imports the package -- fall back to the metadata of an
    installed copy. If neither exists, say so rather than inventing a number.
    """
    try:
        from ._version import __version__ as v
        return v
    except ImportError:
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:                       # pragma: no cover - Python < 3.8
        return "0+unknown"
    try:
        return version("simpleplot")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _detect_version()

__all__ = [
    "Figure",
    "subplots",
    "Style",
    "Normalize",
    "LogNorm",
    "PowerNorm",
    "SymLogNorm",
    "get_cmap",
    "available_colormaps",
    "__version__",
]
