"""
Linking axes after creation
=============================

``sharex``/``sharey`` link two *already-existing* axes -- unlike
``plotpress.subplots(sharex=True)``, which only wires up a grid at creation
time. Handy when the panels come from separate ``add_axes``/``add_subplot``
calls.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, (ax1, ax2) = plotpress.subplots(1, 2, figsize=(8, 3.5))
ax1.plot(x, np.sin(x) * 3, color="#1f77b4")
ax1.set_title("amplitude 3")
ax2.plot(x, np.sin(x), color="#d62728")
ax2.set_title("amplitude 1")

ax1.sharey(ax2)   # after the fact: both panels now span the same y-range
fig.tight_layout()
