"""
Stem plot
=========
"""
import numpy as np
import plotpress

x = np.linspace(0, 2 * np.pi, 24)
fig, ax = plotpress.subplots()
ax.stem(x, np.sin(x))
ax.set_title("Stem plot")
fig.tight_layout()
