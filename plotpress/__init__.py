"""plotpress -- a fast, figure-centric, SVG-first plotting library.

Distinct from matplotlib in three ways:

1. **No global state.** There is no ``pyplot``, no "current figure/axes", no
   global ``rcParams``. Everything hangs off a :class:`Figure`, which owns its
   own :class:`Style`. Build a plot, and the figure holds everything it needs to
   render itself.
2. **matplotlib-like API.** ``Figure``/``Axes`` and methods like ``plot``,
   ``scatter``, ``pcolormesh``, ``set_xlabel``, ``legend`` mirror matplotlib so
   existing code is easy to port. ``plotpress.subplots(...)`` returns
   ``(fig, axes)`` just like ``plt.subplots(...)`` -- minus the globals.
3. **SVG-first + fast.** Output is vector SVG (with embedded raster only for
   mesh/image layers), optionally interactive. The hot paths are vectorized in
   NumPy and huge lines are decimated, so it is fast in **pure Python** -- no
   compiled extension, installs everywhere pip does.

Example
-------
>>> import plotpress
>>> fig, ax = plotpress.subplots()
>>> ax.plot([0, 1, 2], [0, 1, 4], label="quadratic")
>>> ax.legend()
>>> fig.save("out.svg")
"""

import importlib

# name -> (submodule, attribute). Every one of these pulls in NumPy
# transitively (through .colors or .figure), which is most of what
# `import plotpress` costs. Resolving them lazily on first access -- rather
# than importing eagerly here -- keeps a bare `import plotpress` cheap for
# callers who only need __version__ or are introspecting the package.
_LAZY_ATTRS = {
    "Figure": (".figure", "Figure"),
    "subplots": (".figure", "subplots"),
    "subplots_from_layout": (".figure", "subplots_from_layout"),
    "Report": (".figure", "Report"),
    "load_data": (".figure", "load_data"),
    "load_data_xarray": (".figure", "load_data_xarray"),
    "Style": (".style", "Style"),
    "Normalize": (".colors", "Normalize"),
    "LogNorm": (".colors", "LogNorm"),
    "PowerNorm": (".colors", "PowerNorm"),
    "SymLogNorm": (".colors", "SymLogNorm"),
    "get_cmap": (".colors", "get_cmap"),
    "available_colormaps": (".colors", "available_colormaps"),
}


def __getattr__(name):
    try:
        module_name, attr_name = _LAZY_ATTRS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(importlib.import_module(module_name, __name__), attr_name)
    globals()[name] = value  # cache: __getattr__ only runs once per name
    return value


def __dir__():
    return sorted(__all__)


def _detect_version() -> str:
    """The installed version, however this copy of plotpress is being run.

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
        return version("plotpress")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _detect_version()

__all__ = [
    "Figure",
    "subplots",
    "subplots_from_layout",
    "Report",
    "load_data",
    "load_data_xarray",
    "Style",
    "Normalize",
    "LogNorm",
    "PowerNorm",
    "SymLogNorm",
    "get_cmap",
    "available_colormaps",
    "__version__",
]
