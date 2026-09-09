"""
Irregular group shapes (deleted axes)
========================================

``GroupLayout.add()`` takes an optional ``mask`` -- an ``nrows`` x ``ncols``
array-like of truthy/falsy values marking which inner cells actually get an
axes. A falsy cell is simply never created: no blank ``Axes`` sitting there
unused, and each group's box (from :meth:`~plotpress.figure.Figure.group`)
still bounds only its own *real* cells, so it hugs whatever shape the mask
actually describes -- a ring, an L, a diagonal, a plus sign -- instead of
the full rectangle a plain ``nrows`` x ``ncols`` group would draw.

All four groups below sit in one ``GroupLayout(1, 4)`` -- a single outer
row -- each with its own independent 3x3 mask. The combined grid
:func:`~plotpress.figure.subplots_from_groups` builds underneath is
exactly as ordinary as any other: every real axes below is one flat
``SubplotSpec`` span, same as :func:`~plotpress.figure.subplots` itself
would produce.
"""
import numpy as np
import plotpress

RING = [[1, 1, 1],
       [1, 0, 1],
       [1, 1, 1]]
L_SHAPE = [[1, 0, 0],
          [1, 0, 0],
          [1, 1, 1]]
DIAGONAL = [[1, 0, 0],
           [0, 1, 0],
           [0, 0, 1]]
PLUS = [[0, 1, 0],
       [1, 1, 1],
       [0, 1, 0]]

layout = plotpress.GroupLayout(1, 4)
layout.add(0, 0, mask=RING, title="Ring", color="#d62728")
layout.add(0, 1, mask=L_SHAPE, title="L-shape", color="#1f77b4")
layout.add(0, 2, mask=DIAGONAL, title="Diagonal", color="#2ca02c")
layout.add(0, 3, mask=PLUS, title="Plus", color="#9467bd")

fig, axes = plotpress.subplots_from_groups(layout, figsize=(12, 3.4))

rng = np.random.default_rng(3)
x = np.linspace(0, 2 * np.pi, 60)
for group in axes:
    for ax in group.ravel():
        if ax is None:
            continue   # this cell's mask entry was falsy -- nothing to plot
        ax.plot(x, np.sin(x + rng.uniform(0, 6)), color="#333333", linewidth=1.2)
        ax.set_xticks([])
        ax.set_yticks([])

fig.group_spacing(wspace=20.0)
fig.tight_layout()
