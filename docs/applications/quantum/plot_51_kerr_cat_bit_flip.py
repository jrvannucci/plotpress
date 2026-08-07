"""
Kerr-cat qubit: exponential bit-flip protection, linear phase-flip cost
============================================================================

A Kerr-nonlinear oscillator under two-photon driving stabilizes two coherent
states, ``|alpha>`` and ``|-alpha>``, as a pair of quasi-degenerate pointer
states separated by an energy barrier that grows with the mean photon number
``n = alpha^2`` -- the "cat size". Single-photon loss, the dominant error
channel, can only nudge the oscillator's phase-space location a little at a
time, so tunneling all the way from one pointer state to the other -- a
logical bit flip -- takes exponentially many such nudges as the barrier
grows:

    Gamma_x ~ kappa_1 n exp(-2n).

The same single-photon loss dephases the cat directly, at a rate that only
grows with the number of photons there are to lose,

    Gamma_z ~ kappa_1 n,

so phase-flip errors get *more* frequent exactly as bit flips are being
suppressed. This is the defining trade-off of bias-preserving cat qubits: the
noise is not reduced, it is reshaped, traded from the error type a repetition
code cannot fix cheaply into the error type it can.
"""
import numpy as np
import polars as pl
import plotpress

KAPPA1 = 1.0 / 40.0                                 # single-photon loss rate (1/us)

alpha2 = np.linspace(0.5, 9.0, 400)                 # mean photon number |alpha|^2

# One row per cat size -- the shape a noise-budget sweep is actually
# tabulated in, before bit-flip and phase-flip times are read off it.
budget = pl.DataFrame({
    "alpha2": alpha2,
    "gamma_x": KAPPA1 * alpha2 * np.exp(-2.0 * alpha2),
    "gamma_z": KAPPA1 * alpha2,
})
budget = budget.with_columns(
    (1.0 / pl.col("gamma_x")).alias("t_x"),
    (1.0 / pl.col("gamma_z")).alias("t_z"),
)
alpha2_axis = budget["alpha2"].to_numpy()
t_x = budget["t_x"].to_numpy()
t_z = budget["t_z"].to_numpy()
bias = t_x / t_z

# The bias ratio is the number a bias-preserving outer code is chosen
# around; report where it first crosses two practically motivated
# thresholds rather than just the raw curves.
crossing_1e3 = float(np.interp(1.0e3, bias, alpha2_axis))
crossing_1e6 = float(np.interp(1.0e6, bias, alpha2_axis))

fig, ax = plotpress.subplots(figsize=(8.4, 5.8))
ax.plot(alpha2_axis, t_x * 1e3, color="#1f77b4", linewidth=2.0,
        label="bit-flip time T_x (exponential)")
ax.plot(alpha2_axis, t_z * 1e3, color="#d62728", linewidth=2.0,
        label="phase-flip time T_z (linear in 1/|alpha|^2)")

for target, label in [(crossing_1e3, "bias 10^3"), (crossing_1e6, "bias 10^6")]:
    if alpha2_axis.min() <= target <= alpha2_axis.max():
        t_here = float(np.interp(target, alpha2_axis, t_x)) * 1e3
        ax.axvline(target, color="#888888", linestyle=":", linewidth=1.0)
        ax.text(target + 0.08, t_here, label, fontsize=8, color="#666666",
                rotation=90, va="top")

ax.set_yscale("log")
ax.set_xlabel("cat size |alpha|^2 (mean photon number)")
ax.set_ylabel("error timescale (ms)")
ax.set_title("Bit flips are suppressed exponentially; phase flips grow to pay for it")
ax.legend(loc="center right")
ax.grid(True)
fig.tight_layout()
