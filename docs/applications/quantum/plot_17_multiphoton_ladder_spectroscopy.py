"""
Multi-photon transmon ladder spectroscopy
=============================================

Two-tone spectroscopy at fixed frequency range but swept drive power, strong
enough to drive multi-photon transitions up the transmon's anharmonic ladder.
An n-photon process reaching level n appears at the n-photon-averaged
frequency

    f_n = f01 - (n - 1) alpha / 2,

since climbing the ladder against a negative anharmonicity ``alpha`` costs
progressively less energy per photon. Each higher branch also needs
correspondingly higher drive power to appear at all -- an n-photon transition
rate scales as the n-th power of the drive amplitude -- so the ladder switches
on rung by rung as power rises rather than all at once, and each rung
power-broadens once driven hard enough to saturate.
"""
import numpy as np
import plotpress

F01 = 5.050                  # 0-1 transition, GHz
ANHARMONICITY = -0.220        # GHz (negative: transmon)
N_LEVELS = 4

frequency = np.linspace(F01 - 0.36, F01 + 0.01, 380)
power_dbm = np.linspace(-20.0, 15.0, 300)
F, P = np.meshgrid(frequency, power_dbm)

amplitude = 10.0 ** (P / 20.0)          # linear drive amplitude from dBm

response = np.zeros_like(F)
for n in range(1, N_LEVELS + 1):
    center = F01 + (n - 1) * ANHARMONICITY / 2.0
    threshold = 0.55 + 0.65 * (n - 1)    # higher rungs need more drive
    turn_on = 1.0 / (1.0 + np.exp(-(np.log10(amplitude) - np.log10(threshold)) / 0.12))
    width = 0.006 + 0.010 * amplitude / n
    response += turn_on * width ** 2 / ((F - center) ** 2 + width ** 2)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(frequency, power_dbm, response, cmap="plasma")
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("response\n(a.u.)")
ax.set_xlabel("probe frequency (GHz)")
ax.set_ylabel("drive power (dBm)")
ax.set_title(f"Multi-photon ladder, anharmonicity = {ANHARMONICITY * 1e3:.0f} MHz")
fig.tight_layout()
