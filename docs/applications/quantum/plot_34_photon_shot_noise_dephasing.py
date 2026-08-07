"""
Photon-shot-noise dephasing of a Hahn echo
================================================

Echo contrast (a single refocusing pulse at the sequence's midpoint) swept
over free-evolution delay and the residual photon population left in the
dispersively coupled readout resonator between measurements -- the tune-up
that sets how much residual heating or imperfect resonator reset an idling
qubit can tolerate. Each stray photon randomly dephases the qubit through
the dispersive shift ``chi``, at a rate that grows linearly with photon
number to leading order; a Hahn echo cancels *static* detuning but not this
fluctuating, photon-number-dependent dephasing, so ``T2_echo`` itself
shortens as the residual population rises rather than staying fixed. Reading
the delay at which contrast crosses a fixed threshold, as a function of
photon number, is exactly how a resonator reset or filtering scheme is
validated -- if T2_echo does not recover to its low-photon value between
shots, photons are lingering longer than intended.
"""
import numpy as np
import polars as pl
import plotpress

GAMMA0_PER_US = 1.0 / 25.0       # 1/T2_echo at n_th = 0
CHI_MHZ = 1.5                      # dispersive shift
KAPPA_MHZ = 3.0                    # resonator linewidth
DEPHASING_SCALE = 0.05             # tunes the per-photon dephasing rate to microseconds
rng = np.random.default_rng(1203)

delay = np.linspace(0.0, 60.0, 320)          # microseconds
n_photons = np.linspace(0.0, 3.0, 280)        # residual thermal/stray photons
TAU, N = np.meshgrid(delay, n_photons)

chi = 2.0 * np.pi * CHI_MHZ
kappa = 2.0 * np.pi * KAPPA_MHZ
gamma_photon = chi ** 2 * kappa / (kappa ** 2 + chi ** 2)   # per photon
gamma_phi = GAMMA0_PER_US + gamma_photon * N * DEPHASING_SCALE

contrast = np.exp(-TAU * gamma_phi)
contrast += rng.normal(0.0, 0.015, contrast.shape)
contrast = np.clip(contrast, 0.0, 1.0)

# One row per swept (delay, photon number) shot -- sorted before the reshape
# below so the pivot back to a grid is correct regardless of row order.
sweep = pl.DataFrame({
    "delay_us": TAU.ravel(),
    "n_photons": N.ravel(),
    "contrast": contrast.ravel(),
}).sort(["n_photons", "delay_us"])

delay_axis = sweep["delay_us"].unique().sort().to_numpy()
n_photons_axis = sweep["n_photons"].unique().sort().to_numpy()
contrast = sweep["contrast"].to_numpy().reshape(n_photons_axis.size, delay_axis.size)

fig, ax = plotpress.subplots(figsize=(7.6, 5.2))
mesh = ax.pcolormesh(delay_axis, n_photons_axis, contrast, cmap="viridis", vmin=0.0, vmax=1.0)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("contrast")
ax.set_xlabel("echo delay (us)")
ax.set_ylabel("residual photons n_th")
ax.set_title("T2 echo shortens with residual resonator photons")
fig.tight_layout()
