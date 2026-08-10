"""
Oscilloscope rolling trace
============================

A scope shows a fixed-*width* time window, not the whole run: as new
samples arrive the trace shifts left and the oldest samples fall off the
left edge entirely, rather than the x axis growing to hold everything ever
captured (contrast the acquisition-pattern gallery's growing-x-axis
example). A ``collections.deque(maxlen=...)`` is the natural buffer for
this -- append the newest samples, let the oldest ones drop on their own.

The code below is exactly what you'd write against the real
``plotpress.qt.LiveArtist``: a callback that receives whatever new samples
came in since the last tick and pushes them to the plot, fed by a loop
simulating an instrument. Only ``read_from_scope()`` is meant to be
replaced, with your own driver call.
"""
from collections import deque

import numpy as np
import plotpress

# sphinx_gallery_start_ignore
# Doc-build-only harness below: there's no Qt binding to drive a real window
# with at doc-build time, so LiveArtist here reproduces plotpress.qt.
# LiveArtist's update() exactly (ax.cla(), replot, the same auto x-limits for
# a line) and renders a frame instead of pushing one to a live window. None
# of this -- including this whole ignored block -- is part of what a real
# script using the actual LiveArtist would need.
from plotpress.raster import figure_to_image


class LiveArtist:
    def __init__(self, ax, **plot_kwargs):
        self.ax = ax
        self.plot_kwargs = plot_kwargs
        self.last_artist = None

    def update(self, *data):
        self.ax.cla()
        if len(data) == 2:
            x, y = data
            self.last_artist = self.ax.plot(x, y, **self.plot_kwargs)
            if len(x):
                self.ax.set_xlim(float(min(x)), float(max(x)))
        elif len(data) == 3:
            x, y, c = data
            self.last_artist = self.ax.pcolormesh(x, y, c, **self.plot_kwargs)
        else:
            raise TypeError("update() takes (x, y) or (x, y, C)")


_gallery_gif_frames = []
# sphinx_gallery_end_ignore

WINDOW = 200   # samples visible at once

fig, ax = plotpress.subplots(figsize=(7, 4))
scope = LiveArtist(ax, color="#39d353", linewidth=1.2)
t_buf, v_buf = deque(maxlen=WINDOW), deque(maxlen=WINDOW)


def on_new_samples(ts, vs):
    """Called once per acquisition tick with whatever new samples came in
    since the last one -- how most scope drivers actually hand off data (a
    buffer read), not literally one sample at a time.
    """
    t_buf.extend(ts)
    v_buf.extend(vs)
    scope.update(np.array(t_buf), np.array(v_buf))
    ax.set_facecolor("#0b1a0b")
    ax.set_ylim(-1.5, 1.5)
    ax.set_xlabel("time (s)"); ax.set_ylabel("voltage (V)")
    ax.set_title("60 Hz line pickup + 900 Hz ringing")
    fig.tight_layout()
    # sphinx_gallery_start_ignore
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))
    # sphinx_gallery_end_ignore


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own instrument driver. Every-
# thing above only needs (ts, vs) handed to on_new_samples() as they arrive.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(1)
DT = 0.0005              # s between samples -- 2 kS/s
N_TICKS = 40
SAMPLES_PER_TICK = 12


def read_from_scope(t0):
    """Stand-in for a real scope's buffer read: SAMPLES_PER_TICK new
    (t, v) samples starting at t0.
    """
    ts = t0 + DT * np.arange(SAMPLES_PER_TICK)
    vs = (1.0 * np.sin(2 * np.pi * 60.0 * ts)
          + 0.15 * np.sin(2 * np.pi * 900.0 * ts)
          + 0.05 * rng.standard_normal(SAMPLES_PER_TICK))
    return ts, vs


t = 0.0
for _ in range(N_TICKS):
    ts, vs = read_from_scope(t)
    on_new_samples(ts, vs)
    t = ts[-1] + DT

# sphinx_gallery_start_ignore
# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
# sphinx_gallery_end_ignore
