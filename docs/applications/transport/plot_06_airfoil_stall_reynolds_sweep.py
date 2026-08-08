"""
Stall creeping outward as Reynolds number climbs, animated
================================================================

The same three-Reynolds-number lift data as
:doc:`../fluids/plot_11_airfoil_polar`, with every Reynolds number in
between filled in so the stall angle's
dependence on Reynolds number is a moving boundary rather than three
snapshots to compare by eye. Higher Reynolds number delays transition to
turbulence in the boundary layer, and a turbulent boundary layer resists the
adverse pressure gradient near stall far better than a laminar one -- which
is why the curve does not just get taller with Reynolds number, it keeps
climbing linearly to a *later* angle before it gives up.

The animation makes a subtlety of the static comparison concrete: the
pre-stall lift-curve slope barely changes with Reynolds number -- thin-
airfoil theory does not care about viscosity -- so nearly all of the visible
motion is concentrated right at the top of the curve, where each frame's
stall point has moved a little further out than the last.
"""
import os
import tempfile

import numpy as np
import plotpress

CL_SLOPE = 0.105
ALPHA_ZERO_LIFT = -2.2

# Anchor Reynolds numbers and their stall angle / max Cl, from the static
# three-case example, log-interpolated to animate the sweep between them.
RE_ANCHORS = np.array([2.0e5, 5.0e5, 1.0e6])
STALL_ANCHORS = np.array([10.5, 13.0, 15.0])
CLMAX_ANCHORS = np.array([1.05, 1.28, 1.44])

reynolds = np.logspace(np.log10(2.0e5), np.log10(1.0e6), 45)
log_re = np.log10(reynolds)
stall = np.interp(log_re, np.log10(RE_ANCHORS), STALL_ANCHORS)
cl_max = np.interp(log_re, np.log10(RE_ANCHORS), CLMAX_ANCHORS)

alpha = np.linspace(-6.0, 16.0, 300)

cl = np.empty((reynolds.size, alpha.size))
for f in range(reynolds.size):
    raw = CL_SLOPE * (alpha - ALPHA_ZERO_LIFT)
    softened = cl_max[f] * (1.0 - 0.10 * np.clip(
        (alpha - stall[f] + 3.0) / 3.0, 0.0, 1.0) ** 2)
    cl[f] = np.minimum(raw, softened)
    cl[f][alpha > stall[f] + 4.0] = np.nan          # past-stall: not modelled here

fig, ax = plotpress.subplots(figsize=(8.2, 5.6))
ax.plot_frames(alpha, cl, slider_values=reynolds, slider_label="Re",
              color="#1f77b4", label="Cl(alpha)")
ax.set_xlim(-6.0, 16.0)
ax.set_ylim(-0.5, 1.6)
ax.set_xlabel("angle of attack (degrees)")
ax.set_ylabel("lift coefficient Cl")
ax.set_title("Stall angle grows with Reynolds number; the pre-stall slope barely moves")
ax.legend(loc="upper left")
ax.grid(True)
fig.tight_layout()

gif_path = os.path.join(tempfile.gettempdir(), "plotpress_airfoil_re_sweep.gif")
fig.save(gif_path, fps=10)
