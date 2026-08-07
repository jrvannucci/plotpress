"""
Pulsar dynamic spectrum
=======================

A dynamic spectrum from a pulsar search: received power against radio frequency
and time. A pulse leaving the star arrives later at low frequencies because
free electrons along the line of sight slow them, by

    dt = 4.15 ms * DM * (f_lo^-2 - f_hi^-2),  f in GHz

so a single broadband pulse smears into the characteristic dispersion sweep.
Measuring its curvature gives the dispersion measure, and hence the distance.

The band is not clean: terrestrial transmitters sit in fixed frequency channels
and swamp everything. Those channels are flagged and set to ``nan`` rather than
zeroed -- zeroing would drag the colour scale and leave a black stripe that
looks like real absorption, whereas an unpainted channel is unmistakably
missing data.
"""
import numpy as np
import polars as pl
import plotpress

rng = np.random.default_rng(19)
freq = np.linspace(1.20, 1.60, 320)        # GHz
time = np.linspace(0.0, 0.42, 380)         # seconds
F, T = np.meshgrid(freq, time)

DM = 68.0                                   # pc/cm3
PERIOD = 0.128                              # s
F_REF = freq.max()

delay = 4.15e-3 * DM * (F ** -2 - F_REF ** -2)
phase = ((T - delay) % PERIOD) / PERIOD
power = 1.0 + 5.5 * np.exp(-((phase - 0.25) ** 2) / 2.0e-4)
power *= (F / F_REF) ** -1.6                # steep pulsar spectrum
power += rng.normal(0.0, 0.35, power.shape) + 1.0

# Radio-frequency interference: whole channels are unusable and get flagged.
for f0, width in [(1.381, 0.006), (1.452, 0.010), (1.269, 0.004)]:
    power[np.abs(F - f0) < width] = np.nan

# One row per (time, frequency) channel sample -- the shape a backend's own
# filterbank export is in, before it is gridded for the mesh.
filterbank = pl.DataFrame({"freq": F.ravel(), "time": T.ravel(), "power": power.ravel()}) \
    .sort(["time", "freq"])
freq = filterbank["freq"].unique().sort().to_numpy()
time = filterbank["time"].unique().sort().to_numpy()
power = filterbank["power"].to_numpy().reshape(time.size, freq.size)

fig, ax = plotpress.subplots(figsize=(7.8, 5.2))
mesh = ax.pcolormesh(freq, time, power, cmap="cividis")
fig.colorbar(mesh, ax=ax).set_title("power\n(a.u.)")
ax.set_xlabel("frequency (GHz)")
ax.set_ylabel("time (s)")
ax.set_title(f"Dispersion sweep at DM = {DM:.0f} pc/cm3, RFI channels flagged")
fig.tight_layout()
