"""
Unequal padding on each side of a group
==========================================

``pad`` is a single number on every other example in this gallery -- the
same clearance on all four sides. It also accepts a ``(left, right, top,
bottom)`` sequence for unequal padding, useful exactly when a group's own
edges don't all mean the same thing: the two groups below sit right next to
each other, sharing one boundary in the middle of the figure and each
carrying a title on their own *outer* top edge.

A single scalar ``pad`` big enough for the title clearance both groups need
would also push their shared inner boundary apart by the same amount, even
though nothing is there to clear -- wasted canvas, and the two groups read
as farther apart than they should. Tightening just that one side (``left``
for "After", ``right`` for "Before") while keeping the title-facing top
generous does what a single number can't: the two boxes visibly touch in
the middle, without either title crowding its own plots.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(3)
x = np.linspace(0, 6, 17)
y = np.linspace(0, 4, 13)
X, Y = np.meshgrid(x, y)

fig, axes = plotpress.subplots(2, 4, figsize=(12, 6))
for r in range(2):
    for c in range(4):
        phase = c * 0.5
        Z = np.sin(X + phase - r) * np.cos(Y - phase) + 0.05 * rng.standard_normal(X.shape)
        axes[r, c].pcolormesh(x, y, Z, cmap="viridis", vmin=-1.2, vmax=1.2)
        axes[r, c].tick_params(labelsize=6)

# (left, right, top, bottom) -- tight on the side facing the other group,
# generous everywhere else, including the top each title needs.
fig.group("Before", list(axes[:, 0:2].ravel()), title_position="top",
         color="#1f77b4", pad=(20.0, 4.0, 24.0, 8.0))
fig.group("After", list(axes[:, 2:4].ravel()), title_position="top",
         color="#d62728", pad=(4.0, 20.0, 24.0, 8.0))

# The shared boundary is interior to the grid and neither title faces it,
# so tight_layout() won't widen it on its own -- group_spacing() reserves
# just enough room for the two tightened (4px) inner edges to clear each
# other without colliding.
fig.group_spacing(wspace=10.0)
fig.tight_layout()
