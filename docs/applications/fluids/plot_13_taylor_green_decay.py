"""
The decaying Taylor-Green vortex: an exact solution, animated
===================================================================

The steady Taylor-Green vortex array from
:doc:`plot_04_vorticity_vectors` is actually the ``t = 0`` slice of an exact,
time-dependent solution of the incompressible Navier-Stokes equations --
one of the few nontrivial cases where the equations can be solved in closed
form rather than only simulated, which is why it is a standard code-
validation case rather than a demonstration flow:

    omega(x, y, t) = 2 sin(x) sin(y) exp(-2 nu t).

Viscosity does exactly one thing to this flow: it decays the whole pattern
uniformly in time, in place. The vortex array does not drift, merge, or
change shape -- every cell shrinks toward zero at the same exponential rate
``exp(-2 nu t)`` at once, because the spatial structure ``sin(x) sin(y)`` is
itself an eigenfunction of the Laplacian, so diffusion multiplies it by a
scalar rather than reshaping it. That is a special property of this flow, not
of viscous decay generally, and is exactly why it has a closed form at all.

The colour scale is fixed to the ``t = 0`` amplitude across every frame
(:class:`~plotpress.artists.FrameQuadMesh`'s shared-norm behaviour, the same
mechanism :doc:`../acoustics/plot_07_room_mode_oscillation` relies on) so the
decay reads as fading toward the neutral midpoint rather than as a rescaled
colour bar quietly doing the work instead.
"""
import os
import tempfile

import numpy as np
import plotpress

NU = 0.05                                          # kinematic viscosity (normalized)

g = np.linspace(0.0, 2.0 * np.pi, 140)
X, Y = np.meshgrid(g, g)
spatial = 2.0 * np.sin(X) * np.sin(Y)

N_FRAMES = 36
t = np.linspace(0.0, 15.0, N_FRAMES)               # 1.5 decay times (tau = 1/2nu = 10)
vorticity = np.stack([spatial * np.exp(-2.0 * NU * ti) for ti in t])
lim = float(np.abs(vorticity[0]).max())

fig, ax = plotpress.subplots(figsize=(6.6, 6.0))
mesh = ax.pcolormesh_frames(g, g, vorticity, slider_values=t, slider_label="t",
                            cmap="coolwarm", vmin=-lim, vmax=lim)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("omega")
ax.set_aspect("equal")
ax.set_xlabel("x")
ax.set_ylabel("y")
ax.set_title("Exact decay: the pattern fades in place, it does not drift")
fig.tight_layout()

gif_path = os.path.join(tempfile.gettempdir(), "plotpress_taylor_green_decay.gif")
fig.save(gif_path, fps=12)
