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
3. **SVG-first, fast, and multi-format.** Output is vector SVG (with embedded
   raster only for mesh/image layers) -- and from that same figure, also PNG,
   PDF, self-contained interactive HTML (a full pan/zoom/pick/annotate
   toolbar), or a Vega/Vega-Lite JSON spec. The hot paths are vectorized in
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
from typing import TYPE_CHECKING

# Re-exports are resolved lazily at runtime through ``__getattr__`` below (see
# ``_LAZY_ATTRS``), which a static type checker can't follow. Spelling them out
# again here -- only ever seen by the checker, never executed -- gives Pylance/
# mypy the real classes and signatures for ``plotpress.subplots``,
# ``plotpress.Figure``, and the rest, with autocomplete and go-to-definition
# intact. Keep this list and ``_LAZY_ATTRS``/``__all__`` in step.
if TYPE_CHECKING:
    from .colors import (
        BoundaryNorm,
        LogNorm,
        Normalize,
        PowerNorm,
        SymLogNorm,
        TwoSlopeNorm,
        available_colormaps,
        get_cmap,
        make_cmap,
        make_listed_cmap,
        register_cmap,
        to_hex,
    )
    from .figure import (
        Figure,
        Group,
        GroupLayout,
        Report,
        figure_from_template,
        load_data,
        load_data_xarray,
        load_template,
        select_panel,
        subplots,
        subplots_from_groups,
    )
    from .style import Style, named_cycle

# name -> (submodule, attribute). Every one of these pulls in NumPy
# transitively (through .colors or .figure), which is most of what
# `import plotpress` costs. Resolving them lazily on first access -- rather
# than importing eagerly here -- keeps a bare `import plotpress` cheap for
# callers who only need __version__ or are introspecting the package.
_LAZY_ATTRS = {
    "Figure": (".figure", "Figure"),
    "subplots": (".figure", "subplots"),
    "subplots_from_groups": (".figure", "subplots_from_groups"),
    "GroupLayout": (".figure", "GroupLayout"),
    "Group": (".figure", "Group"),
    "Report": (".figure", "Report"),
    "load_data": (".figure", "load_data"),
    "load_data_xarray": (".figure", "load_data_xarray"),
    "load_template": (".figure", "load_template"),
    "figure_from_template": (".figure", "figure_from_template"),
    "select_panel": (".figure", "select_panel"),
    "Style": (".style", "Style"),
    "Normalize": (".colors", "Normalize"),
    "LogNorm": (".colors", "LogNorm"),
    "PowerNorm": (".colors", "PowerNorm"),
    "SymLogNorm": (".colors", "SymLogNorm"),
    "TwoSlopeNorm": (".colors", "TwoSlopeNorm"),
    "BoundaryNorm": (".colors", "BoundaryNorm"),
    "get_cmap": (".colors", "get_cmap"),
    "available_colormaps": (".colors", "available_colormaps"),
    "make_cmap": (".colors", "make_cmap"),
    "make_listed_cmap": (".colors", "make_listed_cmap"),
    "register_cmap": (".colors", "register_cmap"),
    "to_hex": (".colors", "to_hex"),
    "named_cycle": (".style", "named_cycle"),
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
    "subplots_from_groups",
    "GroupLayout",
    "Group",
    "Report",
    "load_data",
    "load_data_xarray",
    "load_template",
    "figure_from_template",
    "select_panel",
    "Style",
    "Normalize",
    "LogNorm",
    "PowerNorm",
    "SymLogNorm",
    "TwoSlopeNorm",
    "BoundaryNorm",
    "get_cmap",
    "available_colormaps",
    "make_cmap",
    "make_listed_cmap",
    "register_cmap",
    "to_hex",
    "named_cycle",
    "__version__",
]
