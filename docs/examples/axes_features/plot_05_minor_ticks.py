"""
Minor ticks
===========

``minorticks_on`` adds unlabeled subdivisions between the major ticks --
linear subdivisions on the left, sub-decade marks on a log axis on the right.
"""
import numpy as np
import plotpress

x = np.linspace(1, 100, 200)

fig, axes = plotpress.subplots(1, 2, figsize=(8, 3.5))
axes[0].plot(x, np.sin(x / 5))
axes[0].minorticks_on()
axes[0].set_title("linear")

axes[1].loglog(x, x ** 1.5)
axes[1].minorticks_on()
axes[1].set_title("log-log")
fig.tight_layout()
