"""
Oscilloscope rolling trace
============================

A scope shows a fixed-*width* time window, not the whole run: as new
samples arrive the trace shifts left and the oldest samples fall off the
left edge entirely, rather than the x axis growing to hold everything ever
captured (contrast the acquisition-pattern gallery's growing-x-axis
example). A ``collections.deque(maxlen=...)`` is the natural buffer for
this -- append the newest sample, let the oldest one drop on its own -- and
that buffer's current contents are exactly what a ``LiveArtist.update(t, v)``
call would get fed on a real scope, once per acquisition.
"""
from collections import deque

import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(1)
WINDOW = 200            # samples visible at once
DT = 0.0005              # s between samples -- 2 kS/s
N_STEPS = 40
SAMPLES_PER_STEP = 12

t_buf = deque(maxlen=WINDOW)
v_buf = deque(maxlen=WINDOW)

t = 0.0
_gallery_gif_frames = []
for step in range(N_STEPS):
    for _ in range(SAMPLES_PER_STEP):
        v = (1.0 * np.sin(2 * np.pi * 60.0 * t)
             + 0.15 * np.sin(2 * np.pi * 900.0 * t)
             + 0.05 * rng.standard_normal())
        t_buf.append(t)
        v_buf.append(v)
        t += DT

    fig, ax = plotpress.subplots(figsize=(7, 4))
    ax.plot(np.array(t_buf), np.array(v_buf), color="#39d353", linewidth=1.2)
    ax.set_facecolor("#0b1a0b")
    if len(t_buf) == WINDOW:
        ax.set_xlim(t_buf[0], t_buf[-1])
    ax.set_ylim(-1.5, 1.5)
    ax.set_xlabel("time (s)"); ax.set_ylabel("voltage (V)")
    ax.set_title("60 Hz line pickup + 900 Hz ringing")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax
