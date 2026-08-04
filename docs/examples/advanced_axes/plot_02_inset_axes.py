"""
Inset axes
==========

``inset_axes`` places a small axes inside this one, positioned as a fraction
of the *parent's own box* -- handy for a zoomed-in detail view. It tracks the
parent through a later ``tight_layout``/``subplots_adjust`` rather than
freezing its position at creation time.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 1000)
y = np.sin(x) * np.exp(-x / 10)

fig, ax = plotpress.subplots()
ax.plot(x, y)
ax.set_title("damped oscillation")
ax.set_xlabel("t")
ax.set_ylabel("amplitude")

inset = ax.inset_axes([0.55, 0.55, 0.4, 0.4])
early = x <= 2
inset.plot(x[early], y[early], color="#d62728")
inset.set_title("zoom: t < 2", size=9)
fig.tight_layout()
