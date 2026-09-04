"""
Axline
======
"""
import numpy as np
import plotpress

rng = np.random.default_rng(3)
x = np.linspace(0, 10, 60)
y = 0.5 * x + 1 + rng.standard_normal(60)

fig, ax = plotpress.subplots()
ax.scatter(x, y, s=10, color="C0")
# an infinite line through a point with a slope -- spans the axes, no autoscale
ax.axline((0, 1), slope=0.5, color="C3", linewidth=1.5)
# two points sharing an x -- an undefined (vertical) slope, still a valid
# infinite line through both
ax.axline((6, 0), (6, 8), color="C4", linewidth=1.5, linestyle="--")
ax.set_title("axline (fit reference + a vertical one)")
