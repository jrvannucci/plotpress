"""
Orbital probability density (PowerNorm)
=======================================

``|psi|^2`` for the hydrogen 3d-z^2 orbital in the x-z plane. The torus and the
outer lobes carry orders of magnitude less probability than the core, so a
linear scale spends almost all of its color range on the peak and renders the
rest as background.

``PowerNorm`` with an exponent below 1 compresses the top of the range and
stretches the bottom, which lifts faint structure into view without clipping the
maximum or resorting to a log scale the data's zeros would not survive.
"""
import numpy as np
import plotpress

g = np.linspace(-24.0, 24.0, 340)        # Bohr radii
X, Z = np.meshgrid(g, g)
r = np.hypot(X, Z)
# cos(theta) measured from the z axis; the origin is a removable singularity.
cos_theta = np.divide(Z, r, out=np.zeros_like(r), where=r > 0.0)

# psi_320 proportional to r^2 exp(-r/3) (3 cos^2(theta) - 1)
psi = r ** 2 * np.exp(-r / 3.0) * (3.0 * cos_theta ** 2 - 1.0)
density = psi ** 2
density /= density.max()

fig, axes = plotpress.subplots(1, 2, figsize=(11.0, 4.6))
linear = axes[0].pcolormesh(g, g, density, cmap="magma")
axes[0].set_title("linear norm")
fig.colorbar(linear, ax=axes[0])

gamma = axes[1].pcolormesh(g, g, density, cmap="magma",
                           norm=plotpress.PowerNorm(0.35))
axes[1].set_title("PowerNorm(0.35)")
fig.colorbar(gamma, ax=axes[1])

for ax in axes:
    ax.set_aspect("equal")
    ax.set_xlabel("x (a0)")
    ax.set_ylabel("z (a0)")
fig.suptitle("Hydrogen 3d-z^2 probability density")
fig.tight_layout()
