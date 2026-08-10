"""
Cyclic voltammetry, cycle over cycle
=======================================

A cyclic voltammogram sweeps voltage forward then back across a fixed
window, tracing out a loop -- both axes are bounded and known before the
run starts, unlike every growing-axis example elsewhere in this gallery.
What makes it worth its own example is what happens *between* cycles: each
new sweep retraces the same loop, drawn over the earlier ones rather than
replacing them, so cycle-to-cycle drift (here, a fouling electrode losing
peak current) shows up directly as the loops shrink inward over the run.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(14)
V_MIN, V_MAX = -0.2, 0.8
POINTS_PER_HALF = 45
N_CYCLES = 5

forward = np.linspace(V_MIN, V_MAX, POINTS_PER_HALF)
reverse = np.linspace(V_MAX, V_MIN, POINTS_PER_HALF)[1:]
voltage_cycle = np.concatenate([forward, reverse])


def current_for_cycle(v, cycle_index):
    # Redox peaks (oxidation on the forward sweep, reduction on the
    # reverse) that shrink each cycle as the electrode fouls, plus a
    # capacitive background and measurement noise.
    decay = 0.82 ** cycle_index
    is_forward = np.arange(len(v)) < POINTS_PER_HALF
    i = 0.15 * v
    i = i + np.where(is_forward, 1.0, 0.0) * decay * 2.6 * np.exp(-((v - 0.42) ** 2) / (2 * 0.05 ** 2))
    i = i - np.where(is_forward, 0.0, 1.0) * decay * 2.1 * np.exp(-((v - 0.28) ** 2) / (2 * 0.05 ** 2))
    return i + 0.03 * rng.standard_normal(v.shape)


completed_cycles = []   # each: (voltage_full, current_full)
STRIDE = 4

_gallery_gif_frames = []
for c in range(N_CYCLES):
    current_cycle_v, current_cycle_i = [], []
    for n in range(STRIDE, len(voltage_cycle) + STRIDE, STRIDE):
        n = min(n, len(voltage_cycle))
        current_cycle_v = voltage_cycle[:n]
        current_cycle_i = current_for_cycle(voltage_cycle[:n], c)

        fig, ax = plotpress.subplots(figsize=(6.5, 5.5))
        for j, (v_old, i_old) in enumerate(completed_cycles):
            fade = 0.15 + 0.5 * (j + 1) / max(1, len(completed_cycles))
            ax.plot(v_old, i_old, color="#555555", alpha=fade, linewidth=1.0)
        ax.plot(current_cycle_v, current_cycle_i, color="#d62728", linewidth=1.6)
        ax.set_xlim(V_MIN - 0.05, V_MAX + 0.05)
        ax.set_ylim(-1.4, 2.9)
        ax.set_xlabel("potential (V)"); ax.set_ylabel("current (uA)")
        ax.set_title(f"Cyclic voltammetry -- cycle {c + 1}/{N_CYCLES}")
        fig.tight_layout()
        _gallery_gif_frames.append(figure_to_image(fig, scale=2))

    completed_cycles.append((current_cycle_v, current_cycle_i))

del fig, ax
