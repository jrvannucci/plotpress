"""
Room acoustic modal pressure
============================

The sound pressure field of a rectangular room driven at one of its axial modal
frequencies. Below the Schroeder frequency a room does not behave diffusely: it
rings at discrete modes, and the standing-wave pattern decides where a listener
hears a boom and where a null.

Acoustic pressure is **signed** -- it is a deviation about static atmospheric
pressure, and the sign is the phase of the standing wave. Two points half a
wavelength apart move in antiphase, which is the whole reason nulls exist. A
diverging map with limits symmetric about zero shows that directly: red and
blue lobes are the antiphase regions, and the white lines between them are the
nodal surfaces where a microphone measures nothing.

Plotting the magnitude instead would merge each antiphase pair and lose the
structure the mode is.
"""
import numpy as np
import plotpress

LX, LY = 6.4, 4.6                      # room dimensions (m)
C_SOUND = 343.0                        # m/s

x = np.linspace(0.0, LX, 360)
y = np.linspace(0.0, LY, 300)
X, Y = np.meshgrid(x, y)

# Superpose a few low-order modes near the drive frequency, each with the
# rigid-wall cosine shape and its own modal damping.
MODES = [(3, 2, 1.00), (2, 3, 0.55), (4, 1, 0.35), (1, 1, 0.22)]
pressure = np.zeros_like(X)
for nx, ny, weight in MODES:
    f_mode = 0.5 * C_SOUND * np.hypot(nx / LX, ny / LY)
    phase = 1.0 / (1.0 + ((f_mode - 92.0) / 14.0) ** 2)    # driven near 92 Hz
    pressure += weight * phase * (np.cos(nx * np.pi * X / LX)
                                  * np.cos(ny * np.pi * Y / LY))

lim = float(np.abs(pressure).max())
fig, ax = plotpress.subplots(figsize=(8.0, 5.4))
mesh = ax.pcolormesh(x, y, pressure, cmap="coolwarm", vmin=-lim, vmax=lim)
ax.contour(X, Y, pressure, levels=[0.0], colors="#222222")
fig.colorbar(mesh, ax=ax).set_title("Pa\n(rel.)")
ax.set_aspect("equal")
ax.set_xlabel("x (m)")
ax.set_ylabel("y (m)")
ax.set_title("Modal pressure at 92 Hz, nodal lines contoured")
fig.tight_layout()
