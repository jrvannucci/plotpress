"""
Load duration curve and the generation stack
============================================

A year of hourly electricity demand, shown twice. On the left it is a time
series; on the right the same 8760 numbers are sorted from highest to lowest.
That sort throws away *when* demand occurred and keeps only *how often* each
level was reached -- which is exactly the question a generation plan asks, and
the reason the load duration curve is the standard planning figure.

The payoff is that horizontal slices of the sorted curve become plant
capacities and the areas under them become energy. Baseload plant sits at the
bottom and runs almost all year; peaking plant occupies the thin spike on the
left and runs a few dozen hours. Reading that off the time series is impossible;
reading it off the sorted curve is a ruler.

So the right panel is filled by band with ``fill_between`` rather than merely
drawn, with each band labelled by its capacity factor -- the fraction of the year
that plant runs, which is what determines whether an expensive-to-build,
cheap-to-run technology beats the reverse.

The peak hour is annotated on both panels. On the left it is one point in a
January cold snap; on the right it is the leftmost point of the curve. Being the
same event in two representations is the point of showing both.
"""
import numpy as np
import polars as pl
import plotpress

rng = np.random.default_rng(2007)

HOURS = 8760
hour = np.arange(HOURS)
day_of_year = hour / 24.0

# Seasonal swing (winter heating peak), daily double peak, weekday/weekend.
seasonal = 1.0 + 0.26 * np.cos(2 * np.pi * (day_of_year - 8.0) / 365.0)
daily = (1.0 + 0.16 * np.sin(2 * np.pi * (hour % 24 - 8.0) / 24.0)
         + 0.09 * np.sin(4 * np.pi * (hour % 24 - 6.0) / 24.0))
weekly = np.where((day_of_year.astype(int) % 7) < 5, 1.0, 0.90)

load = 31_000.0 * seasonal * daily * weekly
load *= np.exp(rng.normal(0.0, 0.035, HOURS))
# A cold snap: a few days of exceptional demand that set the annual peak.
snap = np.exp(-((day_of_year - 12.0) ** 2) / (2 * 1.6 ** 2))
load *= 1.0 + 0.20 * snap

# One row per hour of the year -- the shape a grid operator's own demand log
# is in, before it is sorted into a duration curve.
demand = pl.DataFrame({"hour": hour, "day_of_year": day_of_year, "load": load})
peak = demand.sort("load", descending=True).row(0, named=True)

# The same 8760 readings, sorted highest to lowest -- a different table, not
# a reordering of the one above, since the duration curve deliberately
# discards which hour each reading came from.
duration = pl.DataFrame({
    "rank": np.arange(HOURS),
    "load": demand["load"].sort(descending=True).to_numpy(),
})

PLANT = [
    ("nuclear + hydro", 17_000.0, "#1f77b4"),
    ("combined cycle gas", 12_000.0, "#2ca02c"),
    ("open cycle gas", 8_000.0, "#ff7f0e"),
    ("demand response", 12_000.0, "#d62728"),
]

fig, axes = plotpress.subplots(1, 2, figsize=(12.0, 5.2))
ax_time, ax_ldc = axes

ax_time.plot(demand["day_of_year"].to_numpy(), demand["load"].to_numpy() / 1e3,
             color="#555555", linewidth=0.4)
ax_time.scatter([peak["day_of_year"]], [peak["load"] / 1e3], s=8.0, color="#d62728")
ax_time.annotate("annual peak", xy=(peak["day_of_year"], peak["load"] / 1e3),
                 xytext=(80.0, 48.0), arrowprops={"color": "#d62728"},
                 color="#d62728", fontsize=9)
ax_time.set_xlim(0.0, 365.0)
ax_time.set_xlabel("day of year")
ax_time.set_ylabel("demand (GW)")
ax_time.set_title("Chronological: when demand happened")
ax_time.grid(True)

rank = duration["rank"].to_numpy()
sorted_load = duration["load"].to_numpy()
base = 0.0
for name, capacity, color in PLANT:
    top = base + capacity
    lower = np.clip(sorted_load, base, top)
    ax_ldc.fill_between(rank, base / 1e3, lower / 1e3, color=color, alpha=0.85,
                        label=name)
    running = float((sorted_load > base).sum()) / HOURS
    ax_ldc.text(HOURS * 0.55, (base + min(capacity, 9000.0) * 0.42) / 1e3,
                f"{name}\ncapacity factor {running * 100:.0f}%", fontsize=8,
                color="#111111")
    base = top

ax_ldc.plot(rank, sorted_load / 1e3, color="#111111", linewidth=1.4,
            label="load duration curve")
ax_ldc.scatter([0], [sorted_load[0] / 1e3], s=8.0, color="#d62728")
ax_ldc.annotate("annual peak\n(same hour)", xy=(0.0, sorted_load[0] / 1e3),
                xytext=(900.0, 52.0), arrowprops={"color": "#d62728"},
                color="#d62728", fontsize=9)

ax_ldc.set_xlim(0.0, HOURS)
ax_ldc.set_ylim(0.0, 58.0)
ax_ldc.set_xlabel("hours per year at or above this demand")
ax_ldc.set_title("Sorted: how often each level was reached")

fig.suptitle("The same 8760 numbers: one ordering plans operations, the other plans plant")
fig.tight_layout()
