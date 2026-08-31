"""
A 4x4 grid, each panel labeled in its own corner
===================================================

Sixteen small multiples need a label identifying *which* panel is which --
here, the two parameters a 2-D field was generated from. A data-coordinate
label would need its own ``(x, y)`` worked out per panel, and would drift out
of a sensible spot the moment a panel's own data range differed from its
neighbors'. ``transform=ax.transAxes`` sidesteps both: ``(0.95, 0.95)`` is
always "the top-right corner", identically, on every one of the sixteen axes,
regardless of what each one's ``pcolormesh`` happens to span.
"""
import numpy as np
import plotpress

g = np.linspace(-3.0, 3.0, 60)
X, Y = np.meshgrid(g, g)

fig, axes = plotpress.subplots(4, 4, figsize=(11.0, 11.0))

freqs = np.linspace(0.6, 2.4, 4)
phases = np.linspace(0.0, np.pi, 4)
for i, ax in enumerate(axes.flat):
    freq, phase = freqs[i // 4], phases[i % 4]
    Z = np.exp(-(X ** 2 + Y ** 2) / 6.0) * np.cos(freq * X + phase)
    ax.pcolormesh(g, g, Z, cmap="RdBu_r", vmin=-1, vmax=1)
    # Each panel's box carries *its own* parameters -- the whole point of a
    # corner label here, not just a shared title the figure could carry once.
    ax.text(0.95, 0.95, f"f={freq:.1f}\nphase={phase:.2f}",
           transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
           bbox={"facecolor": "#ffffff", "edgecolor": "#888888",
                 "alpha": 0.85, "pad": 3.0})
    ax.set_xticks([]); ax.set_yticks([])

fig.suptitle("16 pcolormesh panels, each self-labeled via transform=ax.transAxes")
fig.tight_layout()
