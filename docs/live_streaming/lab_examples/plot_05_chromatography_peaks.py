"""
Chromatography trace with live peak detection
=================================================

An HPLC or GC run is read out continuously as the sample elutes, so the
trace grows one retention-time step at a time -- the detector's y range is
fixed by its hardware, but there's no telling in advance how long the run
needs to be, so x keeps growing until the run is stopped. Once a peak's
apex has clearly passed (the signal has risen, then fallen back by a
margin), it gets labeled right where it was found, rather than waiting for
the whole run to finish and post-processing it.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(6)
PEAKS = [(3.2, 1.0, 0.15), (7.8, 2.6, 0.22), (8.6, 1.1, 0.12), (14.0, 0.6, 0.30)]
t_full = np.linspace(0, 18, 220)


def baseline_signal(t):
    s = 0.05 + 0.01 * t
    for center, height, width in PEAKS:
        s = s + height * np.exp(-((t - center) ** 2) / (2 * width ** 2))
    return s


true_signal = baseline_signal(t_full) + 0.015 * rng.standard_normal(t_full.shape)

STRIDE = 5
n_frames = int(np.ceil(len(t_full) / STRIDE))
labeled = []   # retention times already annotated

_gallery_gif_frames = []
for k in range(1, n_frames + 1):
    n = min(k * STRIDE, len(t_full))
    t, y = t_full[:n], true_signal[:n]

    fig, ax = plotpress.subplots(figsize=(7.5, 4.5))
    ax.plot(t, y, color="#8c564b", linewidth=1.2)
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 3.2)
    ax.set_xlabel("retention time (min)"); ax.set_ylabel("detector signal (AU)")
    ax.set_title(f"Chromatogram -- {t[-1]:.1f} / 18.0 min")

    # A peak has "passed" once the signal has climbed at least 0.3 AU above
    # a nearby earlier point and then dropped back down by the same margin
    # -- simple enough to run every frame, exactly like an online integrator
    # would flag it during the run rather than after.
    if n > 10:
        for center, height, width in PEAKS:
            if center in labeled or center > t[-1]:
                continue
            past_apex_idx = np.searchsorted(t, center + 1.5 * width)
            if past_apex_idx < len(y) and t[past_apex_idx - 1] > center:
                apex_i = np.argmax(y[:past_apex_idx])
                if y[apex_i] - y[past_apex_idx - 1] > 0.2 * height:
                    labeled.append(center)
                    ax.annotate(f"{center:.1f} min", (t[apex_i], y[apex_i]),
                                xytext=(t[apex_i] + 0.3, y[apex_i] + 0.25),
                                color="#d62728")

    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax
