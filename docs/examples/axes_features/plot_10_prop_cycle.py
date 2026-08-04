"""
Per-axes color cycle
======================

``set_prop_cycle`` overrides one axes' color cycle without touching the
figure's shared ``Style`` -- the other axes on the same figure keeps the
default cycle.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 100)

fig, (ax1, ax2) = plotpress.subplots(1, 2, figsize=(8, 3.5))
ax1.set_prop_cycle(["#e41a1c", "#377eb8", "#4daf4a"])
for i in range(3):
    ax1.plot(x, np.sin(x + i))
ax1.set_title("custom cycle")

for i in range(3):
    ax2.plot(x, np.sin(x + i))
ax2.set_title("default cycle")
fig.tight_layout()
