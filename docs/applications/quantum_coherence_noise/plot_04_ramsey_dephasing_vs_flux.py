"""
Ramsey dephasing across the flux-tuning range
================================================

A fixed-frequency Ramsey sequence run at every point along a flux-tunable
transmon's tuning curve, rather than at one flux bias with detuning swept in
software (compare :doc:`plot_03_ramsey_chevron`). The qubit is driven at a
constant frequency set exactly on resonance at the flux sweet spot; moving
away from it detunes the qubit from that fixed drive at the same time as flux
noise starts dephasing it, since both effects are driven by the same
first-order flux sensitivity ``df/dPhi``, which vanishes at the sweet spot and
grows away from it. The two compound into an hourglass: fringes appear and
speed up away from ``Phi = 0``, and the envelope narrows at the same rate --
one figure showing why operating at the sweet spot is not just convenient but
is the whole reason flux-tunable qubits are usable at all.
"""
import numpy as np
import polars as pl
import plotpress

F_SWEET = 5.0                 # GHz, qubit frequency at the sweet spot
CURVATURE = 0.55               # GHz per Phi0^2, local curvature near the sweet spot
T2_SWEET = 20.0                # microseconds, sweet-spot-limited T2*
DEPHASING_K = 55.0             # sets how fast T2 collapses with flux sensitivity
rng = np.random.default_rng(63)

# A narrow window around the sweet spot -- a wider excursion would detune the
# qubit by hundreds of MHz, far too fast for a fixed-frequency drive and a
# microsecond-scale delay axis to resolve at all.
flux = np.linspace(-0.06, 0.06, 320)        # Phi / Phi0
delay = np.linspace(0.0, 10.0, 260)         # microseconds
PHI, TAU = np.meshgrid(flux, delay)

detuning = -CURVATURE * PHI ** 2                       # GHz, relative to F_SWEET
slope = 2.0 * CURVATURE * np.abs(PHI)                   # |df/dPhi|, GHz per Phi0
dephasing_rate = 1.0 / T2_SWEET + DEPHASING_K * slope ** 2
t2 = 1.0 / dephasing_rate

signal = 0.5 + 0.5 * np.exp(-TAU / t2) * np.cos(2 * np.pi * detuning * 1e3 * TAU)
signal += rng.normal(0.0, 0.015, signal.shape)

# One row per swept (flux, delay) shot -- sorted before the reshape below so
# the pivot back to a grid is correct regardless of row order.
sweep = pl.DataFrame({
    "flux_phi0": PHI.ravel(),
    "delay_us": TAU.ravel(),
    "signal": signal.ravel(),
}).sort(["delay_us", "flux_phi0"])

flux_axis = sweep["flux_phi0"].unique().sort().to_numpy()
delay_axis = sweep["delay_us"].unique().sort().to_numpy()
signal = sweep["signal"].to_numpy().reshape(delay_axis.size, flux_axis.size)

fig, ax = plotpress.subplots(figsize=(7.6, 5.2))
mesh = ax.pcolormesh(flux_axis, delay_axis, signal, cmap="viridis", vmin=0.0, vmax=1.0)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("P(e)")
ax.set_xlabel("flux bias (Phi / Phi0)")
ax.set_ylabel("free-evolution delay (us)")
ax.set_title(f"Ramsey envelope collapses away from the flux sweet spot (f = {F_SWEET:.1f} GHz)")
fig.tight_layout()
