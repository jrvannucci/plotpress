"""
Twin axes (twinx)
=================

Two independent y-scales sharing one x-axis, with the second y-axis on the right.
"""
import numpy as np
import simpleplot

t = np.linspace(0, 10, 300)

fig, ax = simpleplot.subplots()
ax.plot(t, np.sin(t), color="#1f77b4")
ax.set_xlabel("t")
ax.set_ylabel("sin(t)")

ax2 = ax.twinx()
ax2.plot(t, np.exp(t / 3), color="#d62728")
ax2.set_ylabel("exp(t/3)")

ax.set_title("twinx")
