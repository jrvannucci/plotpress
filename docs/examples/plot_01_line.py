"""
Line plot
=========

Multiple lines with a legend -- the ``plot`` reference example.
"""
import numpy as np
import plotpress

x = np.linspace(0, 2 * np.pi, 200)
fig, ax = plotpress.subplots()
ax.plot(x, np.sin(x), label="sin")
ax.plot(x, np.cos(x), linestyle="--", label="cos")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("Line plot"); ax.legend()
fig.tight_layout()
