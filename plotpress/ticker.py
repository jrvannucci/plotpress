"""Tick location and label formatting ("nice numbers" 1-2-5 algorithm),
plus the declarative locator/formatter specs :meth:`~plotpress.axes.Axes.
set_xlocator`/``set_xformat`` accept.

A *locator* spec is a small dict naming a scheme (``{"kind": "multiple",
"base": ...}``) rather than a matplotlib-style ``Locator`` object -- it has
to be plain, JSON-serializable data so the exact same tick-placement rule
can be replayed client-side when an interactive figure is zoomed/panned (see
``_interactive.py``'s own mirror of every function here). A *formatter*
spec is the same idea for labels: a name, a ``%``-style string, or (Python-
only, see :func:`apply_tick_format`) a callable.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import List

import numpy as np


def log_floor(vmax: float) -> float:
    """A sensible positive floor for a log-scale bound that reached zero or
    negative -- three decades below ``vmax`` (or ``1e-3`` if ``vmax`` itself
    isn't positive either), never exactly zero.

    Shared by :func:`log_ticks`/:func:`minor_ticks` here and by
    :class:`~plotpress.colors.LogNorm`, which used to independently floor at
    a fixed ``1e-300`` instead -- for a ``LogNorm(vmin=0, vmax=...)``
    colorbar, that meant the tick positions (via this function) and the
    actual color mapping (via the old fixed floor) disagreed on where the
    scale's usable bottom sits, visually compressing almost the entire real
    data range into one end of the colormap.
    """
    return max(vmax / 1000.0, 1e-300) if vmax > 0 else 1e-3


def nice_ticks(vmin: float, vmax: float, n: int = 5) -> np.ndarray:
    """Return ~``n`` evenly spaced "nice" tick locations within [vmin, vmax].

    Order-independent: ``set_xlim(hi, lo)`` reverses the axis (like matplotlib),
    so the caller may pass ``vmin > vmax``. The tick *locations* are the same
    either way -- the reversal is handled by the transform -- so normalize here.
    """
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    if vmin == vmax:
        vmin, vmax = vmin - 0.5, vmax + 0.5
    if not (math.isfinite(vmin) and math.isfinite(vmax)):
        return np.array([vmin, vmax])

    span = vmax - vmin
    raw_step = span / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw_step))
    norm = raw_step / mag
    # Snap to a nice multiple of the magnitude.
    if norm < 1.5:
        step = 1 * mag
    elif norm < 3:
        step = 2 * mag
    elif norm < 7:
        step = 5 * mag
    else:
        step = 10 * mag

    start = math.ceil(vmin / step) * step
    ticks = np.arange(start, vmax + step * 0.5, step)
    # Snap the near-zero tick to exactly zero. For an unlucky step (0.02, say)
    # np.arange lands it at ~1e-17 instead of 0, which then formats as "1.4e-17".
    # A real tick is a multiple of step, so only the zero tick can be this close.
    ticks[np.abs(ticks) < step * 1e-6] = 0.0
    # Guard against float dust producing points just outside the range.
    ticks = ticks[(ticks >= vmin - step * 1e-6) & (ticks <= vmax + step * 1e-6)]
    return ticks


def log_ticks(vmin: float, vmax: float) -> np.ndarray:
    """Tick locations for a log axis, all lying **within** [vmin, vmax].

    Decades where the range spans them. The containment matters: a tick outside
    the limits transforms to a pixel outside the axes box, and nothing clips
    tick labels -- so an out-of-range decade is drawn into whatever sits next to
    the axes, typically the neighboring subplot. Autoscale margins alone are
    enough to trigger it: data from 0.01 upward gets a limit just under 0.01,
    which used to pull in a 0.001 tick a whole panel away.

    Ranges narrower than a decade have no decade inside them, so they fall back
    to 1-2-5 subdivisions and then to plain :func:`nice_ticks` -- an axis with
    no labels at all is worse than one whose labels are not powers of ten.

    Order-independent (see :func:`nice_ticks`): a reversed log limit still gets
    its ticks rather than silently rendering none.
    """
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    if vmin <= 0:
        # Data/limits reached here non-positive; pick a small positive floor
        # (three decades below the top), never zero. Matches the interactive JS.
        vmin = log_floor(vmax)
    lo = math.floor(math.log10(vmin))
    hi = math.ceil(math.log10(vmax))
    # Huge dynamic range (a bit-error-rate axis spans seventeen decades): thin
    # the decades out rather than interpolating between them. Every k-th decade
    # keeps every label a round power of ten; a linear interpolation over the
    # exponents produced ticks at 4.3e-17 and 1.9e-15, which is unreadable and
    # not what a log axis is for.
    step = max(1, int(math.ceil((hi - lo) / 12.0)))
    exps = np.arange(lo, hi + 1, step)

    def _inside(values):
        # Relative tolerance: a decade that the limit sits on should survive the
        # float dust of 10 ** floor(log10(v)).
        return values[(values >= vmin * (1 - 1e-9)) & (values <= vmax * (1 + 1e-9))]

    # Three decades is the point where powers of ten alone label an axis well.
    # Two -- a range like 2 um to 120 um -- leaves a wide axis carrying "10" and
    # "100" and nothing else, so subdivide instead.
    ticks = _inside(np.power(10.0, exps))
    if ticks.size >= 3:
        return ticks

    # Sub-decade range: 1-2-5 within each decade the range touches.
    fine = np.concatenate([np.array([1.0, 2.0, 5.0]) * 10.0 ** e
                           for e in np.arange(lo, hi + 1)])
    fine = _inside(np.sort(fine))
    if fine.size >= 2:
        return fine
    return nice_ticks(vmin, vmax)


def minor_ticks(major: np.ndarray, vmin: float, vmax: float,
                scale: str = "linear") -> np.ndarray:
    """Unlabeled minor tick locations between/around ``major``, within [vmin, vmax].

    Linear: subdivides the major step by a count keyed off its leading digit
    (1->5, 2->4, 5->5), matching :func:`nice_ticks`'s 1-2-5 convention, so
    minor ticks land on round subdivisions of whatever step ``nice_ticks``
    chose. Log: the 2..9 sub-decade marks within each decade the range spans.
    """
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    if scale == "log":
        if vmin <= 0:
            vmin = log_floor(vmax)
        lo = math.floor(math.log10(vmin))
        hi = math.ceil(math.log10(vmax))
        fine = np.concatenate([np.arange(2, 10) * 10.0 ** e
                               for e in np.arange(lo, hi + 1)])
        fine = fine[(fine >= vmin) & (fine <= vmax)]
        return np.sort(fine)

    major = np.asarray(major, dtype=float)
    if major.size < 2:
        return np.empty(0, dtype=float)
    step = float(major[1] - major[0])
    if step == 0:
        return np.empty(0, dtype=float)
    mag = 10 ** math.floor(math.log10(abs(step)))
    lead = round(abs(step) / mag)
    n = {1: 5, 2: 4, 5: 5}.get(lead, 5)
    substep = step / n
    # Walk outward from the first major tick, in both directions, so minor
    # ticks land exactly on subdivisions of the major grid rather than an
    # independent grid that may not line up with it.
    ticks = []
    k = math.floor((vmin - major[0]) / substep) - 1
    kmax = math.ceil((vmax - major[0]) / substep) + 1
    for i in range(int(k), int(kmax) + 1):
        v = major[0] + i * substep
        if vmin - substep * 1e-6 <= v <= vmax + substep * 1e-6:
            # Skip points coincident with a major tick.
            if not np.any(np.abs(major - v) < abs(substep) * 1e-6):
                ticks.append(v)
    return np.array(sorted(ticks), dtype=float)


def format_tick(v: float) -> str:
    """Format a tick value compactly (fixed or scientific as appropriate)."""
    if v == 0:
        return "0"
    av = abs(v)
    if av >= 1e5 or av < 1e-3:
        s = f"{v:.1e}"
        # Tidy "1.0e+03" -> "1e3".
        mant, exp = s.split("e")
        mant = mant.rstrip("0").rstrip(".")
        exp = int(exp)
        return f"{mant}e{exp}"
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s


def _sci_tick(v: float, exp: int, decimals: int) -> str:
    """Format ``v`` against a *shared* exponent, e.g. ``1.002e5`` for exp=5."""
    mant = f"{v / 10.0 ** exp:.{decimals}f}"
    if "." in mant:
        mant = mant.rstrip("0").rstrip(".")
    return f"{mant}e{exp}"


def format_ticks(values) -> List[str]:
    """Format a *set* of ticks so no two labels collide.

    ``format_tick`` alone rounds each value to one mantissa digit, which turns a
    narrow band at high magnitude into six identical labels (ticks across
    [100000, 101000] all read "1e5"). For an evenly spaced set, pick a single
    shared exponent and carry enough mantissa digits to resolve the tick *step*,
    so the labels stay distinct and comparable.

    Unevenly spaced sets -- log decades, mainly -- keep the per-value form,
    where each label already carries its own exponent.
    """
    vals = [float(v) for v in values]
    labels = [format_tick(v) for v in vals]
    if len(set(labels)) == len(labels):
        return labels                      # already distinct -- nothing to repair
    if len(vals) < 2 or not all(math.isfinite(v) for v in vals):
        return labels

    diffs = np.diff(vals)
    step = abs(float(diffs[0]))
    # Uneven spacing means no single exponent describes the set; a zero step
    # means the ticks are float-identical, so no formatting can separate them.
    if step == 0 or not np.allclose(diffs, diffs[0], rtol=1e-6):
        return labels

    peak = max(abs(v) for v in vals)
    if peak == 0:
        return labels

    exp = math.floor(math.log10(peak))
    # Enough decimals that one step is visible in the mantissa: the step spans
    # 10**-d of the shared decade when d = exp - log10(step). The 1e-9 absorbs
    # float dust so an exact power-of-ten step doesn't round a digit up.
    decimals = max(0, min(12, math.ceil(exp - math.log10(step) - 1e-9)))
    shared = [_sci_tick(v, exp, decimals) for v in vals]
    # Only adopt the rewrite if it actually separated them (a range so narrow
    # that 12 decimals cannot resolve it keeps the shorter per-value labels).
    return shared if len(set(shared)) == len(shared) else labels


def multiple_ticks(vmin: float, vmax: float, base: float, offset: float = 0.0) -> np.ndarray:
    """Tick locations at every multiple of ``base`` (plus ``offset``) within
    ``[vmin, vmax]`` -- matplotlib's ``MultipleLocator``. The standard way to
    force ticks at, say, every ``pi/2`` on a trig plot's axis, regardless of
    what :func:`nice_ticks`'s own 1-2-5 scheme would have chosen.
    """
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    if not (base > 0):
        raise ValueError(f"multiple locator: base must be > 0, got {base!r}")
    start = math.ceil((vmin - offset) / base) * base + offset
    ticks = np.arange(start, vmax + base * 1e-9, base)
    return ticks[(ticks >= vmin - base * 1e-6) & (ticks <= vmax + base * 1e-6)]


def resolve_tick_locations(vmin: float, vmax: float, scale: str = "linear",
                           locator=None, is_date: bool = False) -> np.ndarray:
    """The location half of tick resolution, in the priority every renderer
    (SVG, raster, the interactive JS rebuild) applies identically: an
    explicit ``locator`` spec first, then a date axis, then a log scale,
    then the default "nice number" scheme. An explicit, literal tick array
    (``Axes.set_xticks``) is resolved by the caller before this is ever
    reached -- it wins over all of these.
    """
    if locator is not None:
        return apply_locator(locator, vmin, vmax)
    if is_date:
        from .dates import date_ticks
        return date_ticks(vmin, vmax)
    if scale == "log":
        return log_ticks(vmin, vmax)
    return nice_ticks(vmin, vmax)


def apply_locator(spec, vmin: float, vmax: float) -> np.ndarray:
    """Resolve a locator spec (see :meth:`~plotpress.axes.Axes.set_xlocator`)
    into tick locations for the current ``[vmin, vmax]``."""
    kind = spec.get("kind") if isinstance(spec, dict) else spec
    if kind == "multiple":
        return multiple_ticks(vmin, vmax, spec["base"], spec.get("offset", 0.0))
    raise ValueError(f"unknown locator kind {kind!r}")


def resolve_tick_format(values, fmt=None, is_date: bool = False) -> List[str]:
    """The label half of tick resolution, mirroring
    :func:`resolve_tick_locations`'s priority: an explicit ``fmt`` spec
    first, then a date axis, then the default numeric formatting. Explicit,
    literal tick *labels* (``Axes.set_xticklabels``) are resolved by the
    caller before this is ever reached.
    """
    if fmt is not None:
        return apply_tick_format(fmt, values)
    if is_date:
        from .dates import format_date_ticks
        return format_date_ticks(values)
    return format_ticks(values)


#: SI/engineering suffixes by power-of-1000 exponent.
_SI_PREFIXES = {
    -8: "y", -7: "z", -6: "a", -5: "f", -4: "p", -3: "n", -2: "u", -1: "m",
    0: "", 1: "k", 2: "M", 3: "G", 4: "T", 5: "P", 6: "E", 7: "Z", 8: "Y",
}


def _engineering_tick(v: float, decimals: int) -> str:
    if v == 0:
        return "0"
    exp3 = max(-8, min(8, math.floor(math.log10(abs(v)) / 3)))
    mant = f"{v / 10.0 ** (exp3 * 3):.{decimals}f}"
    if "." in mant:
        mant = mant.rstrip("0").rstrip(".")
    return f"{mant}{_SI_PREFIXES[exp3]}"


def _pi_tick(v: float, max_denominator: int) -> str:
    if abs(v) < 1e-12:
        return "0"
    frac = Fraction(v / math.pi).limit_denominator(max_denominator)
    num, den = frac.numerator, frac.denominator
    if num == 0:
        return "0"
    sign = "-" if num < 0 else ""
    num = abs(num)
    num_str = "" if num == 1 else str(num)
    return f"{sign}{num_str}π" if den == 1 else f"{sign}{num_str}π/{den}"


def resolve_axis_ticks(vmin: float, vmax: float, explicit=None,
                       categorical: bool = False, categories=None,
                       scale: str = "linear", locator=None,
                       is_date: bool = False) -> np.ndarray:
    """Tick *locations* for one axis dimension, at the full priority every
    renderer (SVG, raster, the interactive JS rebuild) must apply
    identically: an explicit literal array (``Axes.set_xticks``) first,
    then one tick per category on a categorical axis, then an explicit
    :func:`apply_locator` spec, then a date axis, then a log scale, then
    the default "nice number" scheme.
    """
    if explicit is not None:
        return np.asarray(explicit, dtype=float)
    if categorical:
        cats = np.arange(len(categories or []), dtype=float)
        kept = cats[(cats >= vmin - 1e-9) & (cats <= vmax + 1e-9)]
        # An empty result (every category panned out of view) would render
        # no ticks at all -- fall back to the full set, same as
        # date_ticks()/multiple_ticks() do for their own edge cases.
        return kept if kept.size else cats
    return resolve_tick_locations(vmin, vmax, scale, locator, is_date)


def resolve_axis_tick_labels(values, explicit=None, categorical: bool = False,
                             categories=None, fmt=None,
                             is_date: bool = False) -> List[str]:
    """Tick *labels* for one axis dimension, mirroring
    :func:`resolve_axis_ticks`'s priority: explicit literal labels
    (``Axes.set_xticklabels``) first, then this axis' own category names,
    then an explicit :func:`apply_tick_format` spec, then a date axis,
    then plain numeric formatting.
    """
    if explicit is not None:
        labs = list(explicit)[:len(values)]
        return labs + [""] * (len(values) - len(labs))
    if categorical and categories:
        return [categories[i] if 0 <= (i := int(round(v))) < len(categories) else ""
                for v in values]
    return resolve_tick_format(values, fmt, is_date)


def apply_tick_format(spec, values) -> List[str]:
    """Apply a formatter spec (see :meth:`~plotpress.axes.Axes.set_xformat`)
    to tick ``values``.

    ``spec`` is one of:

    - a callable ``value -> str`` (Python-only -- see ``set_xformat``'s own
      docstring for why this can't survive an interactive zoom);
    - ``"percent"``/``"comma"``/``"eng"``/``"pi"`` (or the same as a dict
      with ``"kind"`` plus options, e.g. ``{"kind": "percent", "decimals": 1}``);
    - any other string containing ``"%"``, applied as a plain ``%``-style
      format applied to each value (``"%.2f"``, ``"$%.0f"``).
    """
    if callable(spec):
        return [spec(v) for v in values]
    if isinstance(spec, dict):
        kind = spec.get("kind")
        opts = {k: v for k, v in spec.items() if k != "kind"}
    else:
        kind, opts = spec, {}
    vals = [float(v) for v in values]
    if kind == "percent":
        decimals = opts.get("decimals", 0)
        return [f"{v * 100:.{decimals}f}%" for v in vals]
    if kind in ("comma", "thousands"):
        decimals = opts.get("decimals", 0)
        return [f"{v:,.{decimals}f}" for v in vals]
    if kind in ("eng", "engineering"):
        decimals = opts.get("decimals", 1)
        return [_engineering_tick(v, decimals) for v in vals]
    if kind in ("pi", "multiple_of_pi"):
        max_den = opts.get("max_denominator", 12)
        return [_pi_tick(v, max_den) for v in vals]
    if isinstance(kind, str) and "%" in kind:
        return [kind % v for v in vals]
    raise ValueError(
        f"unknown tick format {spec!r} -- expected a callable, one of "
        "'percent'/'comma'/'eng'/'pi', or a '%'-style format string"
    )
