"""
Error-amplification gate calibration: pulse-angle error vs repetitions
==========================================================================

Excited-state population after applying ``N`` repeated pi pulses, each
carrying the same small deliberate rotation-angle error ``epsilon``, swept
over both. A single imperfect pulse leaves an error too small to see above
readout noise; repeating it accumulates the error N-fold, so the population
oscillates as ``sin^2(N epsilon / 2)`` and the fringe spacing in ``epsilon``
shrinks as ``1/N`` -- exactly the effect that makes this sequence, not a
single-shot measurement, the way amplitude errors are actually calibrated in
practice. Reading the map at any fixed large ``N`` and finding the nearest
fringe to ``epsilon = 0`` gives the pulse-amplitude correction directly; a
single pulse could never resolve it this precisely.

Gate infidelity accumulates with repetition too, which is why the fringe
contrast fades toward the top of the map rather than staying crisp forever --
a real amplification sequence has a practical ceiling on how many repeats are
worth applying before decoherence outruns the amplification.
"""
import numpy as np
import plotpress

GATE_INFIDELITY = 0.0018     # per-gate depolarizing-like error
N_MAX = 60
rng = np.random.default_rng(2024)

angle_error = np.linspace(-0.35, 0.35, 320)     # radians, per-pulse rotation error
repetitions = np.arange(1, N_MAX + 1)
EPS, N = np.meshgrid(angle_error, repetitions)

contrast = (1.0 - GATE_INFIDELITY) ** N
p_excited = 0.5 - 0.5 * contrast * np.cos(N * EPS)
p_excited += rng.normal(0.0, 0.012, p_excited.shape)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(angle_error, repetitions, p_excited, cmap="viridis",
                     vmin=0.0, vmax=1.0)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("P(e)")
ax.set_xlabel("per-pulse rotation error (rad)")
ax.set_ylabel("number of repetitions N")
ax.set_title("Error amplification: fringe spacing shrinks as 1/N")
fig.tight_layout()
