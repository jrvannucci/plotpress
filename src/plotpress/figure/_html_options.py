"""Startup-option validation and the JSON/binary encoding used to build an
interactive HTML export's embedded payloads. A leaf module -- nothing here
calls back into `_core`.
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import time
import warnings
from numbers import Integral

import numpy as np

from ..artists import normalize_bbox, normalize_linestyle
from ..axes import Axes
from ..polar import PolarAxes
from ..style import Style
from ..svg import figure_to_svg

_INTERACTIVE_OPTIONS = ("slice",)


_OPTION_KEYS = {
    "slice": {
        "enabled": bool,
        "orientation": ("x", "y"),
        "view": ("cursor", "companion", "replace"),
        "panel_size": "fraction",
        "link_all": bool,
        "snap_pins": bool,
        "grid": bool,
        "axes": "axes",
        "range": ("auto", "colorbar", "custom"),
        "range_min": "number",
        "range_max": "number",
        "index": "index",
    },
}


def _check_option_value(option, key, spec, value):
    def bad(expected):
        return ValueError(
            f"options[{option!r}][{key!r}] must be {expected}, got {value!r}")

    if spec is bool:
        if not isinstance(value, bool):
            raise bad("True or False")
    elif isinstance(spec, tuple):
        if value not in spec:
            raise bad("one of " + ", ".join(repr(v) for v in spec))
    elif spec == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float))                 or not math.isfinite(value):
            raise bad("a finite number")
    elif spec == "index":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise bad("a non-negative integer")
    elif spec == "axes":
        listed = isinstance(value, (list, tuple))
        if not (value == "all" or (listed and all(
                isinstance(v, Axes) or (isinstance(v, Integral) and not isinstance(v, bool) and v >= 0)
                for v in value))):
            raise bad('"all", or a list of axes (or axes indices)')
    elif spec == "fraction":
        if isinstance(value, bool) or not isinstance(value, (int, float))                 or not 0.1 <= value <= 0.6:
            raise bad("a number between 0.1 and 0.6")


def _resolve_options(options):
    """Validate ``options=``; return ``(names, config)``.

    ``options`` is a list of option names, or a dict mapping a name to its
    startup settings (``True``/``None``/``{}`` for the defaults). ``config``
    is ``{name: settings}`` for every named option -- what the JS reads to
    start the tool in the caller's chosen state.
    """
    if options is None:
        given = {}
    elif isinstance(options, str):
        raise TypeError(
            f"options= takes a list of names, not the bare string {options!r} "
            f"-- did you mean options=[{options!r}]?"
        )
    elif isinstance(options, dict):
        given = dict(options)
    else:
        given = {name: None for name in options}
    unknown = [o for o in given if o not in _INTERACTIVE_OPTIONS]
    if unknown:
        raise ValueError(
            f"unknown interactive option(s) {unknown!r}; valid options are "
            f"{list(_INTERACTIVE_OPTIONS)!r}"
        )
    config = {}
    for name, settings in given.items():
        if settings is None or settings is True:
            settings = {}
        if not isinstance(settings, dict):
            raise TypeError(
                f"options[{name!r}] must be a dict of settings (or True/None "
                f"for the defaults), got {settings!r}")
        keys = _OPTION_KEYS[name]
        bad_keys = [k for k in settings if k not in keys]
        if bad_keys:
            raise ValueError(
                f"unknown setting(s) {bad_keys!r} for option {name!r}; valid "
                f"settings are {sorted(keys)!r}")
        for k, v in settings.items():
            _check_option_value(name, k, keys[k], v)
        if settings.get("range") == "custom" and not (
                "range_min" in settings and "range_max" in settings
                and settings["range_min"] < settings["range_max"]):
            raise ValueError(
                f"options[{name!r}]: range='custom' needs range_min and "
                f"range_max, with range_min < range_max")
        config[name] = dict(settings)
    return list(config), config


def _sanitize_nan(obj):
    """Replace non-finite floats (NaN/Infinity/-Infinity) with ``None``.

    ``json.dumps``'s default ``allow_nan=True`` emits those as bare, unquoted
    tokens -- valid Python literals but not valid JSON -- so the browser's
    strict ``JSON.parse`` throws on the very first one and the whole payload
    (meta, pick data, style, everything in one script element) fails to load,
    silently disabling the entire interactive toolbar. A masked or missing
    measurement is an ordinary case for real data (a heatmap's saturated
    pixels, a masked land/ocean field, a scatter's dropped-out channel), not a
    rare one, so this has to hold for every payload, not just the common one.
    """
    if isinstance(obj, np.generic):
        # A numpy scalar (np.int64, np.float64, ...) reaching here -- e.g.
        # from a set_xlocator()/set_xformat() spec built with a value pulled
        # out of a numpy array -- isn't JSON-serializable even though most
        # numpy float types happen to subclass the builtin float. .item()
        # unwraps it to the equivalent native Python type; recursing lets
        # the float branch below still catch a numpy NaN/Infinity.
        return _sanitize_nan(obj.item())
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _columnarize_meta(meta):
    """``{axes_index: {field: value, ...}, ...}`` -> one array per field.

    ``axes_metadata()`` has no long arrays of its own -- every field is a
    single scalar per axes -- so on a figure with hundreds of axes its cost
    is ~25 JSON key names (``"tick_style"``, ``"secondary_dim"``, ...)
    repeated in full for every one of them, not a big number array
    :func:`_encode_binary_arrays` could shrink. Restructuring to one array
    per field states each key name once total; the client rebuilds the exact
    original per-axes shape from it (see ``_interactive.py``'s
    ``expandColumnarMeta``), so nothing downstream that reads
    ``META[axesIndex].field`` has to change. The axes index itself isn't
    contiguous (colorbar/3-D/hidden axes are excluded upstream), so it rides
    along as its own array rather than being assumed to be ``range(n)``.
    """
    index = list(meta.keys())
    if not index:
        return {"keys": [], "index": [], "cols": {}}
    keys = list(next(iter(meta.values())).keys())
    cols = {k: [meta[i][k] for i in index] for k in keys}
    return {"keys": keys, "index": index, "cols": cols}


_BINARY_ARRAY_MIN_LEN = 32  # below this, base64+wrapper overhead loses to plain JSON


def _fits_float16(arr, precision):
    """Whether ``arr`` (float64) survives a float16 round trip losing nothing
    beyond what rounding to ``precision`` decimals already gave up.

    float16 has ~3 significant decimal digits and overflows past +-65504, so
    this can't be decided from ``precision`` alone -- a value in the
    thousands loses digits precision=6 promised to keep, and one past 65504
    overflows to Infinity outright. Casting down and back and comparing
    catches both: NaN/+Inf/-Inf must map to themselves exactly (an
    overflowing finite value shows up as a spurious Infinity here), and every
    finite value must still match to within half the last decimal place
    ``precision`` rounded to.
    """
    if arr.size == 0:
        return True
    nan, posinf, neginf = np.isnan(arr), np.isposinf(arr), np.isneginf(arr)
    finite = ~(nan | posinf | neginf)
    # A value past float16's range overflowing to Infinity here is expected
    # and handled below (it fails the mask comparison, so float32 is used
    # instead) -- not a bug to warn about on every large-magnitude figure,
    # which binary_pick_data's default-on status would otherwise do.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        f16_as_f64 = arr.astype(np.float16).astype(np.float64)
    if not (np.array_equal(np.isnan(f16_as_f64), nan)
            and np.array_equal(np.isposinf(f16_as_f64), posinf)
            and np.array_equal(np.isneginf(f16_as_f64), neginf)):
        return False
    if not finite.any():
        return True
    tol = 0.5 * 10.0 ** -precision
    return np.allclose(f16_as_f64[finite], arr[finite], atol=tol, rtol=0)


def _toolbar_clearance(interactive, n_sliders):
    """(top, bottom) pixels of vertical space the toolbar and any docked
    slider strip need -- both are real reserved space for the same reason:
    the menu bar (``.plotpress-menubar``) and a docked slider strip
    (``.plotpress-sliders``) are both ``position:fixed`` overlays (the bar
    pinned to the top of the viewport so Pan/Zoom's own whole-figure zoom
    can never scroll it out of reach -- see the CSS comment on
    ``.plotpress-menubar`` in ``_interactive.py``), so nothing else stops
    either from drawing over the figure unless this reserves the room for
    them. Used for a ``standalone=False`` document's own body padding
    (:meth:`Figure.to_html`) and for sizing an ``<iframe>`` around one
    (:meth:`Report.save`, and the docs build's own gallery/usage embeds in
    ``docs/conf.py``), so a figure looks the same either way it ends up on
    a page. A standalone page needs neither: a full viewport tall of
    flex-centering slack already keeps both from overlapping the centered
    figure.

    41px is the bar's own single row, measured live in a browser -- padding
    top/bottom, its 1px border-bottom, plus its button/label content's own
    line height, no separate group labels or stacked rows the old two-row
    toolbar needed. Does not budget for a caller's own ``plotpressAddTool()``
    menu (``extra_js=`` on :meth:`Figure.to_html`) -- it lands in the *same*
    row (a sixth menu, not an extra one), so it never changes the bar's own
    height regardless of how many custom tools it adds.

    60px per slider matches each docked strip's own footprint
    (``.plotpress-slider``).
    """
    if not interactive:
        return 0, 0
    return 41, 60 * n_sliders


def _encode_binary_arrays(obj, precision=6):
    """Replace long flat number lists with a base64 float16/float32 buffer.

    A mesh z grid or a long line series embeds as JSON number *text*
    (``"0.707107,0.6,..."``) by default -- verbose, and every value has to be
    re-parsed digit by digit on the JS side. Swapping those arrays for
    ``{"__f32__": "<base64>"}`` (or ``{"__f16__": ...}`` where that loses
    nothing -- see :func:`_fits_float16`) and reinterpreting the bytes
    client-side benchmarked at roughly half the embedded size and stayed
    close to ``JSON.parse``-level decode speed, where matching that size with
    gzip instead cost 5-7x the decode time -- ``DecompressionStream``'s
    per-call overhead dominates at these payload sizes. See the benchmark
    this was validated against for the numbers.

    At the library's default ``precision=6``, float16's ~3 significant
    digits essentially never clears the round-trip check, so this only
    starts choosing float16 once a caller lowers ``pick_precision`` enough
    for it to matter -- consistent with what that parameter has always
    promised: lower precision, smaller file.

    Float32/float16 both natively represent NaN/Infinity, so a masked mesh
    cell or dropped-out channel survives the round trip without the ``None``
    substitution :func:`_sanitize_nan` has to do for plain JSON numbers --
    this only ever touches arrays that go through this encoder, not
    everything else in the payload, so short arrays keep exact ``_sanitize_nan``
    behavior.
    """
    if isinstance(obj, dict):
        return {k: _encode_binary_arrays(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        if (len(obj) >= _BINARY_ARRAY_MIN_LEN
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in obj)):
            arr = np.asarray(obj, dtype=np.float64)
            if _fits_float16(arr, precision):
                return {"__f16__": base64.b64encode(
                    arr.astype(np.float16).tobytes()).decode("ascii")}
            arr32 = arr.astype(np.float32)
            return {"__f32__": base64.b64encode(arr32.tobytes()).decode("ascii")}
        return [_encode_binary_arrays(v, precision) for v in obj]
    return obj


def _json_payload(obj) -> str:
    """JSON for embedding in an inline ``<script>`` block.

    An HTML parser ends a script element at the first ``</script`` in its text,
    wherever it appears -- so a label or dimension name carrying that substring
    would close the payload early and turn whatever followed into live markup.
    ``json.dumps`` does not escape ``<``, so escape it (plus ``>`` and ``&``) as
    ``\\uXXXX``. These are valid JSON string escapes, so ``JSON.parse`` still
    yields the original characters.
    """
    return (
        json.dumps(_sanitize_nan(obj))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
