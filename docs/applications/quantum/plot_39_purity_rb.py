"""
Purity RB: separating coherent from incoherent gate error
================================================================

Standard RB fidelity and purity RB "unitarity" decay, plotted together
against sequence length -- the pair of curves that separates *how much*
error a gate set has from *what kind* it is. Fidelity decays at a rate set
by the total error, coherent and incoherent alike; purity, measured from the
length of the Bloch vector each sequence leaves behind rather than from a
single population readout, decays only from the incoherent part, since a
purely coherent over-rotation shrinks the average fidelity across random
sequences without ever shrinking any individual sequence's own Bloch vector.
A purity decay visibly slower than the fidelity decay -- exactly the gap
plotted here -- is the standard diagnostic that a gate set's error budget is
dominated by coherent miscalibration (an amplitude or phase left slightly
wrong) rather than genuine decoherence, and is worth chasing with
:doc:`plot_22_drag_calibration`-style recalibration rather than accepted as
a hardware limit.
"""
import numpy as np
import plotpress

ASYMPTOTE = 0.5
P_FIDELITY = 0.9975               # depolarizing parameter from standard RB
P_UNITARITY = 0.9991                # slower decay: most error here is coherent
rng = np.random.default_rng(1607)

lengths = np.unique(np.round(np.logspace(0, 3.3, 24)).astype(int))

fidelity = ASYMPTOTE + (1.0 - ASYMPTOTE) * P_FIDELITY ** lengths
unitarity = ASYMPTOTE + (1.0 - ASYMPTOTE) * P_UNITARITY ** lengths

f_err = 0.01 * np.sqrt(lengths / lengths[0])
u_err = 0.012 * np.sqrt(lengths / lengths[0])
fidelity_meas = np.clip(fidelity + rng.normal(0.0, f_err * 0.15), 0.0, 1.0)
unitarity_meas = np.clip(unitarity + rng.normal(0.0, u_err * 0.15), 0.0, 1.0)

fig, ax = plotpress.subplots(figsize=(8.2, 5.6))
ax.errorbar(lengths, fidelity_meas - ASYMPTOTE, yerr=f_err * 0.15, color="#1f77b4",
            marker="o", markersize=4.5, linestyle="none", capsize=2.5,
            label="RB fidelity")
ax.errorbar(lengths, unitarity_meas - ASYMPTOTE, yerr=u_err * 0.15, color="#d62728",
            marker="o", markersize=4.5, linestyle="none", capsize=2.5,
            label="purity RB (unitarity)")
fine = np.logspace(0, 3.3, 300)
ax.plot(fine, (1.0 - ASYMPTOTE) * P_FIDELITY ** fine, color="#1f77b4", linewidth=1.3)
ax.plot(fine, (1.0 - ASYMPTOTE) * P_UNITARITY ** fine, color="#d62728", linewidth=1.3)

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Clifford sequence length m")
ax.set_ylabel("survival above asymptote")
ax.set_title("Purity decays slower than fidelity: this gate set's error is mostly coherent")
ax.legend(loc="lower left")
ax.grid(True)
fig.tight_layout()
