"""Datetime axis support: converting date/time values to and from the plain
float days-since-epoch every other axis already works in, plus date-aware
tick locating and formatting.

The epoch is 1970-01-01 (Unix epoch), the same one modern matplotlib uses
(``matplotlib.dates`` switched to it in 3.3) -- not because the exact epoch
matters for anything plotpress does internally (any fixed origin round-trips
identically), but because it means a value already converted for matplotlib
(``matplotlib.dates.date2num(...)``) is also a valid plotpress date value,
and vice versa.

A date axis is otherwise a perfectly ordinary linear axis: the data is
converted to float days once, at plot time (see ``Axes._as_axis_data``), and
everything downstream (autoscale, the transform, panning/zooming) works on
that float exactly like it would for any other linear quantity. Only tick
*locations* (:func:`date_ticks`) and tick *labels* (:func:`format_date_ticks`)
need to know the axis is date-flavored.

See :doc:`/auto_examples/axes_features/plot_22_datetime_categorical_and_tick_specs`
and :doc:`/auto_examples/axes_features/plot_23_datetime_gantt_and_milestones`
for worked examples.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import List

import numpy as np

_EPOCH = np.datetime64("1970-01-01T00:00:00", "us")
_US_PER_DAY = 86_400_000_000.0


def is_datetime_like(value) -> bool:
    """True for anything :func:`to_days` can convert: a ``numpy.datetime64``
    scalar/array, a ``datetime.date``/``datetime.datetime``, or a sequence of
    those (what a plain Python list of dates, or a ``pandas`` ``Series``/
    ``DatetimeIndex`` converted through ``numpy.asarray``, already is).
    """
    if isinstance(value, (np.datetime64, _dt.date)):
        return True
    arr = np.asarray(value)
    if arr.dtype.kind == "M":  # numpy datetime64
        return True
    if arr.dtype == object and arr.size:
        # A plain Python list of dates/datetimes -- np.asarray on those
        # doesn't infer datetime64 the way it does for a real array-like of
        # them, so check the actual elements. Only the first is checked
        # (matching this codebase's existing "check the first" convention
        # for cheap type-sniffing, e.g. hist()'s multi-dataset detection) --
        # a mixed list still fails loudly inside to_days() instead of here.
        first = arr.flat[0]
        return isinstance(first, (np.datetime64, _dt.date))
    return False


def to_days(value) -> np.ndarray:
    """Convert date/time data to a plain ``float64`` array of days since the
    1970-01-01 epoch -- the representation every other plotpress axis
    already uses, so nothing downstream needs to know the data was ever a
    date.

    A missing timestamp (``numpy.datetime64("NaT")``, the datetime analogue
    of ``NaN``) maps to ``NaN``, not a huge-but-finite float -- ``NaT``'s own
    ``int64`` encoding is the minimum representable ``int64``, which without
    this would silently become "roughly 300,000 years before 1970" instead
    of being excluded the way a real missing value should be.
    """
    arr = np.asarray(value)
    if arr.dtype.kind != "M":
        # Object array of datetime.date/datetime.datetime, or a bare scalar
        # -- let numpy's own datetime64 constructor do the parsing/promotion
        # (it already accepts both types) rather than hand-rolling it.
        arr = np.asarray(value, dtype="datetime64[us]")
    arr = arr.astype("datetime64[us]")
    days = (arr.astype("int64") - _EPOCH.astype("int64")) / _US_PER_DAY
    nat = np.isnat(arr)
    return np.where(nat, np.nan, days) if np.any(nat) else days


def days_to_datetime64(days) -> np.ndarray:
    """Inverse of :func:`to_days`: float days since epoch -> ``datetime64[us]``."""
    days = np.asarray(days, dtype=float)
    us = np.round(days * _US_PER_DAY).astype("int64")
    return (_EPOCH.astype("int64") + us).astype("datetime64[us]").astype("datetime64[us]")


# Candidate tick spacings, coarsest first, in days -- each paired with the
# datetime64 unit to *round* candidate tick positions to (so a "1 day" tick
# lands on midnight, not on whatever fractional day the view happens to
# start at) and a default label format for that tier. Chosen to mirror
# matplotlib's AutoDateLocator's own tiers (year/month/day/hour/minute/
# second), simplified to one nice step per tier rather than its full
# multi-candidate search.
_YEAR = 365.25
_MONTH = 30.44
_TIERS = [
    # (step_days, round_unit, fmt)
    (10 * _YEAR, "Y", "%Y"), (5 * _YEAR, "Y", "%Y"), (2 * _YEAR, "Y", "%Y"),
    (1 * _YEAR, "Y", "%Y"),
    (6 * _MONTH, "M", "%Y-%m"), (3 * _MONTH, "M", "%Y-%m"),
    (1 * _MONTH, "M", "%Y-%m"),
    (14.0, "D", "%m-%d"), (7.0, "D", "%m-%d"), (2.0, "D", "%m-%d"),
    (1.0, "D", "%m-%d"),
    (0.5, "h", "%m-%d %H:%M"), (0.25, "h", "%H:%M"),
    (1 / 24, "h", "%H:%M"), (1 / 48, "m", "%H:%M"),
    (10 / 1440, "m", "%H:%M:%S"), (1 / 1440, "m", "%H:%M:%S"),
    (10 / 86400, "s", "%H:%M:%S"), (1 / 86400, "s", "%H:%M:%S"),
]


def _pick_tier(span_days: float):
    if not math.isfinite(span_days) or span_days <= 0:
        return _TIERS[-1]
    # ~5 ticks across the span -- matching nice_ticks' own target density.
    target_step = span_days / 5.0
    for step, unit, fmt in reversed(_TIERS):
        if step >= target_step:
            return step, unit, fmt
    return _TIERS[0]


def date_ticks(vmin: float, vmax: float, n: int = 5) -> np.ndarray:
    """Tick locations (float days since epoch) for a date axis, chosen at a
    sensible calendar tier -- years, months, days, hours, minutes or
    seconds -- for the given span, and landing on round boundaries within
    that tier (the first of the month, midnight, the top of the hour) rather
    than at arbitrary offsets from wherever the view happens to start.
    """
    if vmin > vmax:
        vmin, vmax = vmax, vmin
    if vmin == vmax:
        vmin, vmax = vmin - 1.0, vmax + 1.0
    if not (math.isfinite(vmin) and math.isfinite(vmax)):
        return np.array([vmin, vmax])

    step, unit, _fmt = _pick_tier(vmax - vmin)
    lo_dt = days_to_datetime64(vmin).astype(f"datetime64[{unit}]")
    hi_dt = days_to_datetime64(vmax).astype(f"datetime64[{unit}]")
    # Step size in the rounding unit's own ticks (years/months rounds to
    # calendar boundaries via the datetime64 unit cast above; sub-day tiers
    # step in real time units, which np.arange over the unit handles too).
    unit_days = {"Y": _YEAR, "M": _MONTH, "D": 1.0, "h": 1 / 24,
                "m": 1 / 1440, "s": 1 / 86400}[unit]
    step_units = max(1, round(step / unit_days))
    # Walk from one tier-step before lo to one after hi so the first/last
    # in-range tick is never missed to float/calendar rounding.
    start = lo_dt - np.timedelta64(step_units, unit)
    count = int((hi_dt - start) / np.timedelta64(step_units, unit)) + 3
    cand = start + np.arange(count) * np.timedelta64(step_units, unit)
    cand_days = to_days(cand.astype("datetime64[us]"))
    keep = (cand_days >= vmin - 1e-9) & (cand_days <= vmax + 1e-9)
    ticks = cand_days[keep]
    return ticks if ticks.size else np.array([vmin, vmax])


def format_date_ticks(values) -> List[str]:
    """Format a *set* of date tick values (float days since epoch), all at
    one calendar tier chosen from the set's own span -- so a year's worth of
    monthly ticks reads ``2024-01``, ``2024-02``, ... while a day's worth of
    hourly ticks reads ``14:00``, ``15:00``, ... instead of every label
    repeating a full, unchanging date.
    """
    vals = np.asarray([float(v) for v in values], dtype=float)
    if vals.size == 0:
        return []
    span = float(vals.max() - vals.min()) if vals.size > 1 else 1.0
    _step, _unit, fmt = _pick_tier(span if span > 0 else 1.0)
    dts = days_to_datetime64(vals).astype("datetime64[us]").astype(object)
    return [dt.strftime(fmt) for dt in dts]
