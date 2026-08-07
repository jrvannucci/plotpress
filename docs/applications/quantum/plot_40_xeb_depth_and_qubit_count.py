"""
Cross-entropy benchmarking fidelity vs circuit depth and qubit count
==========================================================================

Linear cross-entropy benchmarking (XEB) fidelity from random circuit
sampling, swept over circuit depth (number of cycles) and the number of
qubits in the circuit -- the system-level benchmark used where per-gate RB
no longer scales, once a circuit is too large to decompose into a handful
of independently characterized gates. Each cycle applies one layer of
random single-qubit gates and one layer of two-qubit entangling gates across
the whole register, so a fixed per-cycle error per qubit pair compounds once
per cycle *and* once per pair -- fidelity falls off exponentially in the
product of depth and qubit count, not in either alone, which is what makes
both axes matter simultaneously here rather than one being swept just to
check the other still works.
"""
import numpy as np
import plotpress

ERROR_PER_CYCLE_PAIR = 0.0065      # per-cycle, per-qubit-pair error contribution
rng = np.random.default_rng(1708)

depth = np.arange(1, 41)               # circuit cycles
n_qubits = np.arange(2, 26)             # qubits in the random circuit
D, NQ = np.meshgrid(depth, n_qubits)

pairs_per_cycle = np.floor(NQ / 2.0)
xeb_fidelity = (1.0 - ERROR_PER_CYCLE_PAIR) ** (D * pairs_per_cycle)
xeb_fidelity *= 1.0 + rng.normal(0.0, 0.03, xeb_fidelity.shape)
xeb_fidelity = np.clip(xeb_fidelity, 1e-4, 1.0)
log_fidelity = np.log10(xeb_fidelity)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(depth, n_qubits, log_fidelity, cmap="viridis")
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("log10 F_XEB")
ax.set_xlabel("circuit depth (cycles)")
ax.set_ylabel("number of qubits")
ax.set_title("XEB fidelity falls off in depth times qubit count, not either alone")
fig.tight_layout()
