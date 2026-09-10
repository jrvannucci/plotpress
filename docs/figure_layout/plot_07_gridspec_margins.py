"""
GridSpec margins
==================

``add_gridspec`` accepts the same ``left``/``right``/``top``/``bottom``/
``wspace``/``hspace`` margin kwargs as :meth:`~plotpress.figure.Figure.subplots_adjust`,
applied immediately as the figure's own margins -- a shorthand for setting
spacing at grid-creation time instead of a separate ``subplots_adjust`` call.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig = plotpress.Figure(figsize=(6, 5))
gs = fig.add_gridspec(2, 2, wspace=0.4, hspace=0.5, left=0.12, right=0.95)
for i in range(4):
    ax = fig.add_subplot(gs[i // 2, i % 2])
    ax.plot(x, np.sin(x + i))
fig.suptitle("add_gridspec(wspace=0.4, hspace=0.5, left=0.12, right=0.95)")
