"""
Particle-hit accumulation map
================================

A photon-counting detector or a beam-profile monitor doesn't fill in a grid
of already-known values -- every bin starts at zero and *increments* each
time a new hit lands in it, the same bin often getting hit many times over
the course of a run. That's a different update rule from every other mesh
example in this gallery (which reveal or replace a value once), but it
still fits ``pcolormesh_frames`` directly: counts only ever go up, so the
shared colour scale autoscaled across every frame lands exactly on the
final frame's range.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(12)
NY, NX = 32, 32
gx = np.linspace(-8, 8, NX + 1)
gy = np.linspace(-8, 8, NY + 1)

# A beam profile (2-D Gaussian) plus flat background -- the same shape a
# real detector's hit distribution takes.
N_HITS_TOTAL = 6000
HITS_PER_FRAME = 150
n_frames = N_HITS_TOTAL // HITS_PER_FRAME

beam_frac = 0.85
counts = np.zeros((NY, NX))
C = np.empty((n_frames, NY, NX))
for k in range(n_frames):
    n_beam = int(HITS_PER_FRAME * beam_frac)
    n_bg = HITS_PER_FRAME - n_beam
    hx = np.concatenate([rng.normal(0.0, 1.6, n_beam), rng.uniform(-8, 8, n_bg)])
    hy = np.concatenate([rng.normal(0.5, 1.3, n_beam), rng.uniform(-8, 8, n_bg)])
    hist, _, _ = np.histogram2d(hy, hx, bins=[gy, gx])
    counts += hist
    C[k] = counts

fig, ax = plotpress.subplots(figsize=(6.5, 5.5))
m = ax.pcolormesh_frames(gx, gy, C, cmap="inferno")
fig.colorbar(m, ax=ax)
ax.set_aspect("equal")
ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm)")
ax.set_title("Accumulated particle hits")
fig.tight_layout()
