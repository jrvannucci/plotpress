"""
Bioreactor dashboard, four channels at once
==============================================

A bioreactor's control system logs several channels together -- temperature,
pH, dissolved oxygen, agitation speed -- each with its own physically
meaningful range and its own control behavior (a tight setpoint band for
temperature, a sawtooth for pH as base is dosed in to correct drift, a dip
and recovery for DO as the culture's oxygen demand peaks then eases). A real
dashboard drives one ``LiveArtist`` per panel, all four updating together
from the same sweep loop, on a single ``PlotPressWidget``/figure -- the
Qt-side shape the test suite's own multi-axes check exercises.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(15)
N_HOURS = 48
STEPS_PER_HOUR = 4
t_full = np.linspace(0, N_HOURS, N_HOURS * STEPS_PER_HOUR + 1)

# Temperature: held near a 37 C setpoint by the control loop.
temp = 37.0 + 0.15 * np.sin(t_full / 3.0) + 0.06 * rng.standard_normal(t_full.shape)

# pH: drifts down as the culture produces acid, corrected back up in steps
# whenever base is dosed in -- a sawtooth, not a smooth curve.
ph = 7.2 - 0.35 * (t_full % 6.0) / 6.0
ph = ph + 0.02 * rng.standard_normal(t_full.shape)

# Dissolved oxygen: drops as growth accelerates through mid-run, then
# recovers as the cascade control raises agitation to compensate.
growth_rate = np.exp(-((t_full - 22.0) ** 2) / (2 * 9.0 ** 2))
do_pct = 80.0 - 55.0 * growth_rate + 1.5 * rng.standard_normal(t_full.shape)
do_pct = np.clip(do_pct, 5.0, 95.0)

# Agitation: the cascade control's response to the DO dip above.
agitation_rpm = 250.0 + 350.0 * growth_rate + 4.0 * rng.standard_normal(t_full.shape)

channels = [
    ("Temperature", temp, "#d62728", (36.0, 38.0), "deg C"),
    ("pH", ph, "#1f77b4", (6.6, 7.4), ""),
    ("Dissolved O2", do_pct, "#2ca02c", (0, 100), "%"),
    ("Agitation", agitation_rpm, "#9467bd", (200, 650), "RPM"),
]

STRIDE = 6
n_frames = int(np.ceil(len(t_full) / STRIDE))

_gallery_gif_frames = []
for k in range(1, n_frames + 1):
    n = min(k * STRIDE, len(t_full))
    t = t_full[:n]

    fig, axes = plotpress.subplots(2, 2, figsize=(9, 6.5))
    for (name, series, color, ylim, unit), ax in zip(channels, axes.flat):
        ax.plot(t, series[:n], color=color, linewidth=1.2)
        ax.set_xlim(0, N_HOURS)
        ax.set_ylim(*ylim)
        ax.set_title(f"{name}{f' ({unit})' if unit else ''}")
        ax.set_xlabel("time (h)")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, axes
