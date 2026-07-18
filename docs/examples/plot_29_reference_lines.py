"""
Reference lines, spans & fills
==============================

``axhline`` / ``axvspan`` / ``axhspan`` / ``fill_between`` / ``axline``.
"""
import numpy as np
import simpleplot

x = np.linspace(0, 10, 300)
y = np.sin(x)

fig, ax = simpleplot.subplots()
ax.plot(x, y, label="sin")
ax.fill_between(x, y, 0, color="#1f77b4", alpha=0.2)
ax.axhline(0, color="k", linestyle=":")
ax.axvspan(3, 4, color="orange", alpha=0.3)
ax.axhspan(-0.5, 0.5, color="green", alpha=0.15)
ax.axline((0, -1), slope=0.2, color="purple")
ax.legend(loc="upper right")
ax.set_title("reference marks")
