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

fig, ((ax1, ax2), (ax3, ax4)) = plotpress.subplots(2, 2, figsize=(8, 7))
ax1.plot(x, np.sin(x) * 3, color="#1f77b4")
ax1.set_title("amplitude 3")
ax2.plot(x, np.sin(x), color="#d62728")
ax2.set_title("amplitude 1")

ax1.sharey(ax2)   # after the fact: both panels now span the same y-range

ax3.plot(x, np.sin(x), color="#1f77b4")
ax3.set_xlim(0, 10)
ax3.set_title("full range")
ax4.plot(x * 20, np.sin(x), color="#d62728")
ax4.set_title("scaled x")

ax3.sharex(ax4)   # after the fact: both panels now span the same x-range
fig.tight_layout()
