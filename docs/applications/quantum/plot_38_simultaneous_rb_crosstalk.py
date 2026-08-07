"""
Simultaneous RB: crosstalk-limited fidelity vs spectator activity
========================================================================

Single-qubit RB sequence fidelity, swept over sequence length and how
active a neighboring "spectator" qubit is kept during the same sequence --
idle, or driven with its own random single-qubit Cliffords at the same
time. Simultaneous RB is how crosstalk between control lines is actually
quantified: comparing a qubit's own RB decay run in isolation against the
same sequence run *while* a neighbor is simultaneously being driven isolates
exactly the extra error crosstalk contributes, separate from that qubit's
own intrinsic gate error. The steeper decay at high spectator activity is
not a measurement artefact to calibrate away -- it is the crosstalk budget a
multi-qubit device's own parallel gate scheduling has to live inside.
"""
import numpy as np
import polars as pl
import plotpress

ASYMPTOTE = 0.5
P_ISOLATED = 0.9993               # depolarizing parameter, spectator idle
CROSSTALK_PENALTY = 0.0035         # extra (1-p) at full spectator activity
rng = np.random.default_rng(1506)

lengths = np.unique(np.round(np.logspace(0, 3, 26)).astype(int))
activity = np.linspace(0.0, 1.0, 220)      # 0 = spectator idle, 1 = fully driven
M, ACT = np.meshgrid(lengths, activity)

p = P_ISOLATED - CROSSTALK_PENALTY * ACT
survival = (1.0 - ASYMPTOTE) * p ** M
survival *= 1.0 + rng.normal(0.0, 0.02, survival.shape)
survival = np.clip(survival, 1e-4, 1.0)

# One row per swept (sequence length, spectator activity) point -- sorted
# before the reshape below so the pivot back to a grid is correct
# regardless of row order.
sweep = pl.DataFrame({
    "sequence_length": M.ravel(),
    "activity": ACT.ravel(),
    "log_survival": np.log10(survival).ravel(),
}).sort(["activity", "sequence_length"])

lengths_axis = sweep["sequence_length"].unique().sort().to_numpy()
activity_axis = sweep["activity"].unique().sort().to_numpy()
log_survival = sweep["log_survival"].to_numpy().reshape(activity_axis.size, lengths_axis.size)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(lengths_axis, activity_axis, log_survival, cmap="viridis")
ax.set_xscale("log")
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("log10\n(F - 1/2)")
ax.set_xlabel("Clifford sequence length m")
ax.set_ylabel("spectator qubit activity")
ax.set_title("Simultaneous RB: crosstalk from an active spectator steepens the decay")
fig.tight_layout()
