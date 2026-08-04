"""
subplots_adjust
================

``subplots_adjust`` sets the grid's margins and gutters directly, as
fractions of the figure -- an alternative to :meth:`~plotpress.figure.Figure.tight_layout`'s
automatic fit when the exact numbers matter.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)


def _grid():
    fig, axes = plotpress.subplots(2, 2, figsize=(6, 5))
    for i, ax in enumerate(axes.ravel()):
        ax.plot(x, np.sin(x + i))
    return fig, axes


fig, axes = _grid()
fig.suptitle("default spacing")

# %%
# Widening the gutters and edges:

fig2, axes2 = _grid()
fig2.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.1,
                     wspace=0.4, hspace=0.4)
fig2.suptitle("subplots_adjust(wspace=0.4, hspace=0.4, ...)")
