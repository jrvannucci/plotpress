"""
CZ gate calibration: the 11-02 avoided crossing chevron
============================================================

Population transferred from ``|1,1>`` into the leakage level ``|0,2>``,
swept over the detuning of a tunable coupler and the interaction time -- the
calibration map for a controlled-phase gate built on this avoided crossing
between two-*qubit* levels, rather than a single qubit's own drive detuning
(compare :doc:`plot_06_qubit_chevron`). Bringing ``|1,1>`` and ``|0,2>`` into
resonance and back once around this crossing accumulates the conditional
phase a CZ gate needs; the coupler detuning and gate time that do that with
the *least* residual population left behind in ``|0,2>`` -- reading as the
first chevron fringe closing back down to zero exactly at ``delta = 0`` --
are the two numbers this measurement exists to extract.

The math is the same driven-two-level form as every other chevron in this
gallery, because it genuinely is the same physics -- a two-level system
brought through an avoided crossing -- applied to a different pair of levels
for a different purpose.
"""
import numpy as np
import plotpress

G_MHZ = 10.0                 # 11-02 coupling strength
T2_NS = 400.0                  # leakage-level-limited coherence time
rng = np.random.default_rng(303)

detuning = np.linspace(-60.0, 60.0, 320)      # MHz, coupler detuning to |02>
duration = np.linspace(0.0, 60.0, 280)         # ns
D, T = np.meshgrid(detuning, duration)

g = 2.0 * np.pi * G_MHZ * 1e-3               # rad/ns
delta = 2.0 * np.pi * D * 1e-3                # rad/ns
omega_eff = np.hypot(2 * g, delta)

contrast = np.exp(-T / T2_NS)
p_02 = contrast * (4 * g ** 2 / omega_eff ** 2) * np.sin(omega_eff * T / 2.0) ** 2
p_02 += rng.normal(0.0, 0.012, p_02.shape)

fig, ax = plotpress.subplots(figsize=(7.6, 5.2))
mesh = ax.pcolormesh(detuning, duration, p_02, cmap="viridis", vmin=0.0, vmax=1.0)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("P(02)")
ax.set_xlabel("coupler detuning to |02> (MHz)")
ax.set_ylabel("interaction time (ns)")
ax.set_title(f"CZ 11-02 avoided crossing, coupling g = {G_MHZ:.0f} MHz")
fig.tight_layout()
