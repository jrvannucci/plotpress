"""
Bacterial growth curves under antibiotic stress
===============================================

Optical density of a bacterial culture over eighteen hours, at four antibiotic
concentrations. Growth is exponential while nutrients last, which means the
quantity with constant slope is ``log(OD)``, not ``OD`` -- so the y axis is
logarithmic and the exponential phase becomes the straight segment whose slope
*is* the growth rate.

That is not a presentational choice. Doubling time is read directly off the
slope, and the three phases the biology defines -- lag, exponential, stationary
-- are only separable as three straight-line segments. On a linear axis the lag
phase and the low-concentration cultures are all pinned to the axis and
indistinguishable.

Each condition is three biological replicates, drawn as a mean with a shaded
band spanning the replicate range rather than as three overlaid traces. Nine
lines would obscure the separation between conditions, which is the comparison
the experiment exists to make; a band shows the replicate spread without adding
lines to track.

The highest concentration shows regrowth after eight hours -- resistant mutants
taking over the culture -- which on a log axis is unmistakable as a second
straight segment, and on a linear axis would be a barely visible upturn.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(2718)

t = np.linspace(0.0, 18.0, 400)                   # hours

CONDITIONS = [
    # label,          lag (h), rate (1/h), carrying OD, regrowth, colour
    ("no drug",           1.1, 0.92, 1.35, None,        "#1f77b4"),
    ("0.5x MIC",          1.8, 0.61, 1.10, None,        "#2ca02c"),
    ("1x MIC",            3.2, 0.28, 0.55, None,        "#ff7f0e"),
    ("4x MIC",            0.0, 0.00, 0.02, (8.4, 0.74), "#d62728"),
]
OD_BLANK = 0.008                                   # sterile-medium reading
N_REPLICATES = 3

fig, ax = plotpress.subplots(figsize=(8.6, 5.6))

for label, lag, rate, carrying, regrowth, color in CONDITIONS:
    curves = []
    for _ in range(N_REPLICATES):
        # Logistic growth after a lag: exponential early, saturating late.
        r = rate * rng.normal(1.0, 0.06)
        onset = lag * rng.normal(1.0, 0.10)
        od = carrying / (1.0 + (carrying / 0.02 - 1.0)
                         * np.exp(-r * np.clip(t - onset, 0.0, None)))
        od = np.where(t < onset, 0.02, od)
        if regrowth is not None:
            # Resistant subpopulation: a second exponential from a small base.
            r2_onset, r2 = regrowth
            resistant = 0.004 * np.exp(r2 * np.clip(t - r2_onset, 0.0, None))
            od = od + np.minimum(resistant, 1.2)
        # Plate-reader noise is additive on OD, so it dominates at low density.
        curves.append(od + OD_BLANK + rng.normal(0.0, 0.004, t.size))
    curves = np.array(curves)

    ax.fill_between(t, curves.min(axis=0), curves.max(axis=0), color=color,
                    alpha=0.2)
    ax.plot(t, curves.mean(axis=0), color=color, linewidth=1.7, label=label)

ax.axhline(OD_BLANK, color="#888888", linestyle=":", linewidth=1.2)
ax.text(0.2, OD_BLANK * 1.15, "blank", fontsize=9, color="#666666")

ax.set_yscale("log")
ax.set_xlim(0.0, 18.0)
ax.set_ylim(5e-3, 3.0)
ax.set_xlabel("time (h)")
ax.set_ylabel("OD600")
ax.set_title("Growth curves: exponential phase is the straight part of a log axis")
ax.legend(loc="lower right", title="antibiotic")
ax.grid(True)
fig.tight_layout()
