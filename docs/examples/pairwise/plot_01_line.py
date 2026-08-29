"""
Line plot
=========

Multiple lines with a legend -- the ``plot`` reference example. The third
line adds ``marker=`` -- a dot at each vertex alongside the line itself,
sparse data over the same 200-point grid so the individual markers stay
distinguishable rather than merging into a solid row of dots.
"""
import numpy as np
import plotpress

x = np.linspace(0, 2 * np.pi, 200)
xm = np.linspace(0, 2 * np.pi, 15)
fig, ax = plotpress.subplots()
ax.plot(x, np.sin(x), label="sin")
ax.plot(x, np.cos(x), linestyle="--", label="cos")
ax.plot(xm, np.sin(xm) * np.cos(xm), marker="o", markerfacecolor="#d62728",
       label="sin*cos, marker='o'")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("Line plot"); ax.legend()
fig.tight_layout()
