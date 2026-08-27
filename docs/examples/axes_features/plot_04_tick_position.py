"""
Tick position
=============

``tick_top`` / ``tick_right`` move an axes' ticks and labels off their
default edges -- useful for panels stacked directly beneath each other with a
shared "top" x-axis. ``tick_bottom`` / ``tick_left`` move them back; the
default axes already draws there, so the left panel below calls them only to
make the (otherwise invisible) default explicit.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, (ax1, ax2) = plotpress.subplots(1, 2, figsize=(8, 3.5))

ax1.plot(x, np.sin(x), color="#2ca02c")
ax1.tick_bottom()
ax1.tick_left()
ax1.set_title("tick_bottom + tick_left (default)", size=11)

ax2.plot(x, np.sin(x), color="#2ca02c")
ax2.tick_top()
ax2.tick_right()
ax2.set_title("tick_top + tick_right", size=11)
fig.tight_layout()
