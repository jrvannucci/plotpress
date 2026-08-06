"""
Tick styling
============

``tick_params`` restyles tick marks and labels -- ``labelsize``, ``length``,
``width``, ``color``, ``labelcolor``. ``axis="x"``/``"y"`` (default
``"both"``) scopes the change to one axis, so the x and y ticks can carry
independent styling.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, ax = plotpress.subplots()
ax.plot(x, np.sin(x), color="#1f77b4")
ax.tick_params(axis="x", color="#d62728", labelcolor="#d62728", labelsize=11)
ax.tick_params(axis="y", color="#2ca02c", labelcolor="#2ca02c", length=7, width=1.5)
ax.set_title("tick_params(axis='x' / 'y', ...)", size=11)
fig.tight_layout()
