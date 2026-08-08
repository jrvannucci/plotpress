"""
Stokes' first problem: viscous diffusion from an impulsively started plate
==============================================================================

An infinite plate at rest is set moving at speed ``U`` at ``t = 0``; viscosity
is the only thing that ever tells the fluid above it to move at all, and it
does so by pure diffusion of momentum -- there is no pressure gradient, no
convection, just

    u(y, t) / U = erfc(y / (2 sqrt(nu t))),

the exact solution of ``u_t = nu u_yy`` for this boundary condition. It is
the viscous twin of the diffusing morphogen front in
:doc:`../biology/plot_06_morphogen_gradient_formation`: same equation, same
error-function profile, momentum in place of concentration.

The boundary-layer thickness where the fluid has picked up most of the
plate's speed grows as ``sqrt(nu t)`` rather than linearly in time, which is
the signature of a diffusive process and the reason viscous effects spread
so slowly compared to a wave: doubling the distance reached takes four times
as long, not twice. ``erfc`` has no NumPy builtin, so it is built here from
the same accurate rational-polynomial normal-tail approximation
:doc:`../materials/plot_07_sn_fatigue` uses, rather than adding a SciPy
dependency for one function.
"""
import os
import tempfile

import numpy as np
import plotpress


def gaussian_tail(z):
    """Q(z) = 1 - Phi(z) via an accurate erfc approximation -- no SciPy."""
    t = 1.0 / (1.0 + 0.2316419 * np.abs(z))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
                + t * (-1.821255978 + t * 1.330274429))))
    tail = 0.3989422804014327 * np.exp(-0.5 * z ** 2) * poly
    return np.where(z >= 0, tail, 1.0 - tail)


def erfc(x):
    return 2.0 * gaussian_tail(x * np.sqrt(2.0))


U = 1.0                                             # plate speed (m/s)
NU = 1.0e-6                                          # kinematic viscosity, water (m^2/s)

y = np.linspace(0.0, 8.0e-3, 260)                    # distance from plate (m)
t = np.linspace(0.15, 5.0, 40)                       # time since start (s)

Y, T = np.meshgrid(y, t)                             # both shape (t.size, y.size)
velocity = U * erfc(Y / (2.0 * np.sqrt(NU * T)))
y_mm = y * 1e3

fig, ax = plotpress.subplots(figsize=(7.4, 5.8))
ax.plot_frames(y_mm, velocity, slider_values=t, slider_label="t (s)",
              color="#1f77b4", label="u(y, t)")
ax.set_xlim(0.0, 8.0)
ax.set_ylim(0.0, U * 1.05)
ax.set_xlabel("distance from plate (mm)")
ax.set_ylabel("velocity u / U")
ax.set_title("Momentum diffusing from the wall: boundary layer grows as sqrt(t)")
ax.legend(loc="upper right")
ax.grid(True)
fig.tight_layout()

gif_path = os.path.join(tempfile.gettempdir(), "plotpress_stokes_first_problem.gif")
fig.save(gif_path, fps=10)
