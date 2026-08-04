"""
Tick position
=============

``tick_top`` / ``tick_right`` move an axes' ticks and labels off their
default edges (bottom/left) -- useful for panels stacked directly beneath
each other with a shared "top" x-axis.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, ax = plotpress.subplots()
ax.plot(x, np.sin(x), color="#2ca02c")
ax.tick_top()
ax.tick_right()
ax.set_title("tick_top + tick_right", size=11)
