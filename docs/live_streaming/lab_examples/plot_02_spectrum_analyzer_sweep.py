"""
Spectrum analyzer sweep, with max-hold
=========================================

A spectrum analyzer's trace isn't cumulative -- each sweep *replaces* the
previous one outright, since it's measuring the spectrum right now, not
accumulating history. The "max hold" trace most analyzers offer alongside it
is the exception: a second, independent line that only ever moves up,
tracking the highest magnitude seen at each frequency across every sweep so
far. Two ``LiveArtist``\\ s on the same axes -- one replaced every frame, one
only ever grown -- reproduce both at once.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(4)
freq = np.linspace(0, 500, 400)             # MHz
PEAKS = [(120.0, 28.0, 3.0), (310.0, 22.0, 6.0)]   # (freq, height_dB, width_MHz)
NOISE_FLOOR_DB = -20.0
N_SWEEPS = 30

max_hold = np.full_like(freq, NOISE_FLOOR_DB)

_gallery_gif_frames = []
for sweep in range(N_SWEEPS):
    trace = np.full_like(freq, NOISE_FLOOR_DB) + 2.0 * rng.standard_normal(freq.shape)
    for f0, height, width in PEAKS:
        trace += height * np.exp(-((freq - f0) ** 2) / (2 * width ** 2))
        trace += 0.4 * rng.standard_normal(freq.shape) * np.exp(-((freq - f0) ** 2) / (2 * width ** 2))
    max_hold = np.maximum(max_hold, trace)

    fig, ax = plotpress.subplots(figsize=(7, 4.5))
    ax.plot(freq, trace, color="#1f77b4", linewidth=1.0, label="live sweep")
    ax.plot(freq, max_hold, color="#d62728", linewidth=1.4, linestyle="--", label="max hold")
    ax.set_ylim(NOISE_FLOOR_DB - 5, 35)
    ax.set_xlabel("frequency (MHz)"); ax.set_ylabel("magnitude (dB)")
    ax.set_title(f"Sweep {sweep + 1}/{N_SWEEPS}")
    ax.legend(loc="upper left")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax
