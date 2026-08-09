"""
DRAG coefficient calibration from amplified leakage
========================================================

Leakage out of the computational subspace, into the transmon's second excited
state, after ``N`` repeated single-qubit gates -- swept over both ``N`` and
the DRAG (Derivative Removal by Adiabatic Gate) correction coefficient
``beta`` applied to each pulse. DRAG cancels leakage caused by driving a gate
fast relative to the anharmonicity by adding a scaled derivative of the pulse
envelope to the quadrature that couples to the 1-2 transition; away from the
correct ``beta`` a small per-gate leakage remains, and, just like a
rotation-angle error, that small leakage compounds with repetition,
``P_leak(N) ~ 1 - (1 - p(beta))^N``. Repeating the gate is what turns a
per-shot leakage too small to resolve into a visible, N-dependent valley
whose minimum locates the correct ``beta`` far more precisely than a single
application ever could.
"""
import numpy as np
import polars as pl
import plotpress

BETA_OPT = 0.42                 # correct DRAG coefficient
LEAK_MIN = 0.0006                # residual per-gate leakage even at beta_opt
CURVATURE = 0.006                # sets how sharply leakage grows away from beta_opt
N_MAX = 40
rng = np.random.default_rng(99)

beta = np.linspace(0.0, 0.9, 320)
repetitions = np.arange(1, N_MAX + 1)
BETA, N = np.meshgrid(beta, repetitions)

leak_per_gate = LEAK_MIN + CURVATURE * (BETA - BETA_OPT) ** 2
p_leak = 1.0 - (1.0 - leak_per_gate) ** N
p_leak = np.clip(p_leak + rng.normal(0.0, 0.0015, p_leak.shape), 0.0, 1.0)

# One row per swept (beta, repetitions) shot -- sorted before the reshape
# below so the pivot back to a grid is correct regardless of row order.
sweep = pl.DataFrame({
    "beta": BETA.ravel(),
    "repetitions": N.ravel(),
    "p_leak": p_leak.ravel(),
}).sort(["repetitions", "beta"])

beta_axis = sweep["beta"].unique().sort().to_numpy()
repetitions_axis = sweep["repetitions"].unique().sort().to_numpy()
p_leak = sweep["p_leak"].to_numpy().reshape(repetitions_axis.size, beta_axis.size)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(beta_axis, repetitions_axis, p_leak, cmap="inferno")
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("P(leak)")
ax.set_xlabel("DRAG coefficient beta")
ax.set_ylabel("number of repetitions N")
ax.set_title(f"DRAG calibration: leakage valley narrows at beta = {BETA_OPT:.2f}")
fig.tight_layout()
