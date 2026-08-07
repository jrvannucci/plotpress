"""
CZ conditional-phase calibration
======================================

Control-qubit response to a final analysis phase, swept alongside the
coupler pulse amplitude that sets a CZ gate's conditional phase -- the
calibration that follows locating the ``|1,1>``-``|0,2>`` avoided crossing
itself (:doc:`plot_24_cz_avoided_crossing_chevron`). With the target qubit
prepared in ``|1>``, the control qubit picks up a phase ``phi(A)`` set by the
coupler pulse amplitude ``A``; scanning the final pi/2 pulse's analysis phase
traces out that value directly, as the phase offset of the resulting fringe.
The conditional phase grows smoothly with amplitude, so a tilted fringe
pattern is the raw signature of a calibration that is *working* -- the
operating amplitude is simply wherever that tilt crosses ``phi = pi``, read
straight off the map rather than fitted from a stack of separate 1-D traces.
"""
import numpy as np
import plotpress

A_CZ = 0.62                  # coupler pulse amplitude (a.u.) giving phi = pi
PHASE_SLOPE = 5.4              # radians of conditional phase per unit amplitude
CONTRAST = 0.85
rng = np.random.default_rng(414)

amplitude = np.linspace(0.30, 0.90, 320)      # coupler pulse amplitude, a.u.
phase = np.linspace(0.0, 4.0 * np.pi, 300)     # analysis phase, radians
A, PHI = np.meshgrid(amplitude, phase)

conditional_phase = PHASE_SLOPE * (A - A_CZ) + np.pi
p_excited = 0.5 + 0.5 * CONTRAST * np.cos(PHI - conditional_phase)
p_excited += rng.normal(0.0, 0.015, p_excited.shape)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(amplitude, phase, p_excited, cmap="viridis", vmin=0.0, vmax=1.0)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("P(e)")
ax.axvline(A_CZ, color="white", linestyle=":", linewidth=1.0)
ax.set_xlabel("coupler pulse amplitude (a.u.)")
ax.set_ylabel("analysis phase (rad)")
ax.set_title("Conditional phase reaches pi where the fringe tilt crosses the dotted line")
fig.tight_layout()
