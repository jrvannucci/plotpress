"""
Morphogen gradient formation, animated
=========================================

How a developing embryo turns one localized source of a signaling protein
into a graded readout of position -- the mechanism behind Bicoid in the
early fly embryo. Protein is produced at one end, diffuses, and degrades
everywhere with a fixed half-life; solving

    dC/dt = D d^2C/dx^2 - k C

forward in time by explicit finite differences (the same scheme
:doc:`../acoustics/plot_06_duct_pulse_propagation` uses for a wave rather
than a diffusion) shows *how* the exponential profile is reached, not just
what it looks like once it is.

The steady-state shape ``C(x) = C0 exp(-x / lambda)`` is a standard result,
but the animation is the point: early on the gradient is a diffusing front
that has not yet felt the far end of the domain, and it only settles into
the clean exponential once diffusion and degradation have had time to
balance, at ``lambda = sqrt(D / k)``. Reading a snapshot taken too early as
though it were the steady-state gradient is a real interpretive error in
this kind of data, and watching the profile visibly still relaxing makes it
concrete.
"""
import os
import tempfile

import numpy as np
import plotpress

D = 5.0                                             # diffusion coefficient (um^2/s)
K = 2.31e-4                                          # degradation rate (1/s), ~50 min half-life
C0 = 1.0                                             # source concentration at x=0
L = 500.0                                            # domain length (um)

N = 251
x = np.linspace(0.0, L, N)
dx = x[1] - x[0]
dt = 0.3                                             # < 0.5*dx^2/D, stable

conc = np.zeros(N)
conc[0] = C0

N_FRAMES = 45
STEPS_PER_FRAME = 530
frames = np.empty((N_FRAMES, N))
frames[0] = conc.copy()
r = D * dt / dx ** 2

for f in range(1, N_FRAMES):
    for _ in range(STEPS_PER_FRAME):
        lap = np.empty(N)
        lap[1:-1] = conc[2:] - 2 * conc[1:-1] + conc[:-2]
        lap[-1] = conc[-2] - conc[-1]                # zero-gradient far boundary
        conc = conc + dt * (D * lap / dx ** 2 - K * conc)
        conc[0] = C0                                 # fixed source at x=0
    frames[f] = conc.copy()

t_min = np.arange(N_FRAMES) * STEPS_PER_FRAME * dt / 60.0
steady = C0 * np.exp(-x / np.sqrt(D / K))

fig, ax = plotpress.subplots(figsize=(8.6, 5.4))
ax.plot(x, steady, color="#888888", linestyle="--", linewidth=1.4,
        label="steady state, lambda = sqrt(D/k)")
ax.plot_frames(x, frames, slider_values=t_min, slider_label="t (min)",
              color="#2ca02c", label="C(x, t)")
ax.set_ylim(0.0, C0 * 1.05)
ax.set_xlim(0.0, L)
ax.set_xlabel("distance from source (um)")
ax.set_ylabel("concentration (normalized)")
ax.set_title("Diffusion + degradation building the gradient, not just its endpoint")
ax.legend(loc="upper right")
ax.grid(True)
fig.tight_layout()

gif_path = os.path.join(tempfile.gettempdir(), "plotpress_morphogen_gradient.gif")
fig.save(gif_path, fps=15)
