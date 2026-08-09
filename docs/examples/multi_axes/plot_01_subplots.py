"""
Subplot grid
============

Four fully independent axes on one figure -- no global state.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)
fig, axes = plotpress.subplots(2, 2, figsize=(8, 6))
axes[0, 0].plot(x, np.sin(x)); axes[0, 0].set_title("sin")
axes[0, 1].plot(x, np.sqrt(x), color="#d62728"); axes[0, 1].set_title("sqrt")
axes[1, 0].scatter(x, np.sin(x), s=6); axes[1, 0].set_title("scatter")
axes[1, 1].pcolormesh(np.outer(np.sin(x[:40]), np.cos(x[:40])), cmap="plasma")
axes[1, 1].set_title("mesh")
fig.suptitle("Subplot grid"); fig.tight_layout()
