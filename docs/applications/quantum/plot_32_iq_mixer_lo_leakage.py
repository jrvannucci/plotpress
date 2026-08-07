"""
IQ mixer calibration: nulling LO leakage
============================================

Local-oscillator leakage power at an IQ upconverting mixer's output, swept
over the DC offset voltages fed into its I and Q ports -- the first
calibration run on every microwave line before any pulse shape or gate
timing is even meaningful. An unbalanced mixer leaks a copy of the bare LO
tone straight through regardless of what baseband signal is applied; adding
a small DC offset to each port cancels it, and the correct pair of offsets
is the single point where the leakage drops to the spectrum analyzer's own
noise floor. That floor is why the map is not a clean, unbounded funnel:
past a certain depth there is nothing left to null against, so the minimum
reads as a flat dark patch rather than a single point, and re-running the
calibration lands anywhere inside it.
"""
import numpy as np
import polars as pl
import plotpress

I0, Q0 = 0.024, -0.041         # correct offsets, volts
SLOPE_DB = 46.0                  # dB of leakage suppressed per unit of offset^2
NOISE_FLOOR_DBM = -85.0
rng = np.random.default_rng(1001)

i_offset = np.linspace(-0.15, 0.15, 320)
q_offset = np.linspace(-0.15, 0.15, 300)
I, Q = np.meshgrid(i_offset, q_offset)

residual = (I - I0) ** 2 + (Q - Q0) ** 2
leakage_dbm = NOISE_FLOOR_DBM + SLOPE_DB * np.log10(1.0 + residual / 2e-4)
leakage_dbm += rng.normal(0.0, 0.5, leakage_dbm.shape)

# One row per swept (I offset, Q offset) point -- sorted before the reshape
# below so the pivot back to a grid is correct regardless of row order.
sweep = pl.DataFrame({
    "i_offset_v": I.ravel(),
    "q_offset_v": Q.ravel(),
    "leakage_dbm": leakage_dbm.ravel(),
}).sort(["q_offset_v", "i_offset_v"])

i_axis = sweep["i_offset_v"].unique().sort().to_numpy()
q_axis = sweep["q_offset_v"].unique().sort().to_numpy()
leakage_dbm = sweep["leakage_dbm"].to_numpy().reshape(q_axis.size, i_axis.size)

fig, ax = plotpress.subplots(figsize=(7.0, 5.8))
mesh = ax.pcolormesh(i_axis, q_axis, leakage_dbm, cmap="viridis")
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("LO leak\n(dBm)")
ax.set_aspect("equal")
ax.set_xlabel("I DC offset (V)")
ax.set_ylabel("Q DC offset (V)")
ax.set_title(f"LO leakage null at (I, Q) = ({I0:.3f}, {Q0:.3f}) V")
fig.tight_layout()
