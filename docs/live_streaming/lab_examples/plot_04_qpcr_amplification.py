"""
qPCR amplification curves, several wells at once
====================================================

A qPCR run reads out one cycle at a time across every well in the plate
simultaneously, not one well to completion before the next -- so unlike the
single-trace examples elsewhere in this gallery, each update here grows
*several* lines together on one axes. The cycle count is fixed by the
protocol (40 cycles), so only the data within that known window grows, not
the window itself; a threshold line marks the fluorescence level used to
read off each well's Ct (cycle threshold) the moment its curve crosses it.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

rng = np.random.default_rng(2)
N_CYCLES = 40
cycles = np.arange(1, N_CYCLES + 1)
THRESHOLD = 0.3

# Six wells with different starting template concentrations -> different Ct.
wells = {
    "well A1 (10^5 copies)": 14.0,
    "well A2 (10^4 copies)": 17.5,
    "well A3 (10^3 copies)": 21.0,
    "well A4 (10^2 copies)": 24.5,
    "well B1 (NTC)": None,          # no-template control -- never amplifies
    "well B2 (10^1 copies)": 28.0,
}
colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#7f7f7f", "#9467bd"]


def fluorescence(cycle_n, ct):
    if ct is None:
        return 0.02 * rng.standard_normal(cycle_n.shape) + 0.02
    return 0.02 + 1.0 / (1.0 + np.exp(-(cycle_n - ct) / 1.6)) + 0.015 * rng.standard_normal(cycle_n.shape)


full_curves = {name: fluorescence(cycles, ct) for name, ct in wells.items()}
ct_called = {}

_gallery_gif_frames = []
for n in range(1, N_CYCLES + 1):
    fig, ax = plotpress.subplots(figsize=(7.5, 5))
    x = cycles[:n]
    for (name, curve), color in zip(full_curves.items(), colors):
        y = curve[:n]
        ax.plot(x, y, color=color, label=name, linewidth=1.3)
        if name not in ct_called and y[-1] >= THRESHOLD:
            ct_called[name] = float(x[-1])

    ax.axhline(THRESHOLD, color="#333333", linestyle=":", linewidth=1.0)
    ax.set_xlim(1, N_CYCLES)
    ax.set_ylim(-0.05, 1.3)
    ax.set_xlabel("cycle"); ax.set_ylabel("normalized fluorescence")
    ax.set_title(f"qPCR run -- cycle {n}/{N_CYCLES}"
                + (f" -- {len(ct_called)} well(s) called" if ct_called else ""))
    ax.legend(loc="upper left", ncol=1)
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax
