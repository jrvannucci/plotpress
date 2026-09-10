"""
Figure title and shared axis labels
====================================

``fig.suptitle()`` sets one title spanning the whole figure, above every
subplot -- distinct from ``ax.set_title()``, which titles a single axes.
``fig.supxlabel()``/``fig.supylabel()`` do the same for a shared x/y axis
label, useful when every panel in a grid shares the same units and
repeating the label on each one would be redundant.
"""
import numpy as np
import plotpress

t = np.linspace(0, 4 * np.pi, 300)
fig, axes = plotpress.subplots(1, 3, figsize=(11, 4), sharey=True)

for ax, phase, label in zip(axes, [0.0, np.pi / 3, 2 * np.pi / 3],
                            ["Sensor A", "Sensor B", "Sensor C"]):
    ax.plot(t, np.sin(t + phase))
    ax.set_title(label)

fig.suptitle("Phase-shifted sensor readings")
fig.supxlabel("Time (s)")
fig.supylabel("Amplitude")
fig.tight_layout()
