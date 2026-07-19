"""Tick location and label formatting ("nice numbers" 1-2-5 algorithm)."""

from __future__ import annotations

import math
from typing import List

import numpy as np


def nice_ticks(vmin: float, vmax: float, n: int = 5) -> np.ndarray:
    """Return ~``n`` evenly spaced "nice" tick locations within [vmin, vmax]."""
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
    # Guard against float dust producing points just outside the range.
    ticks = ticks[(ticks >= vmin - step * 1e-6) & (ticks <= vmax + step * 1e-6)]
    return ticks


def log_ticks(vmin: float, vmax: float) -> np.ndarray:
    """Decade tick locations (powers of 10) spanning [vmin, vmax]."""
    if vmin <= 0:
        # Data/limits reached here non-positive; pick a small positive floor
        # (three decades below the top), never zero. Matches the interactive JS.
        vmin = max(vmax / 1000.0, 1e-300) if vmax > 0 else 1e-3
    lo = math.floor(math.log10(vmin))
    hi = math.ceil(math.log10(vmax))
    if hi - lo > 12:  # avoid absurd counts for huge dynamic range
        exps = np.linspace(lo, hi, 12)
    else:
        exps = np.arange(lo, hi + 1)
    return np.power(10.0, exps)


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
