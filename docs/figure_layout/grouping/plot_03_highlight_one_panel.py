"""
Highlighting one panel in a grid
===================================

``fig.group()`` works on a single axes too -- useful for calling out one
panel that stands out from its neighbors, without a separate figure or a
caption pointing back to it. This group also demonstrates the *other* half
of the margin-reservation rule from the previous two examples: it sits in
the interior of the grid, touching none of the figure's own outer edges,
so ``tight_layout()`` widens only the one column boundary its "Anomaly
detected" label actually faces -- not the whole grid -- growing the figure
just enough to clear it automatically. ``pad``'s own right side is still
worth widening a little further here: text width is an estimate, not a
measurement (see :ref:`limitations`), and a title this long relative to
its own column leaves the automatic minimum little room to spare.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(3)
t = np.linspace(0, 10, 200)
anomaly_idx = 5   # row 1, col 1 of a 2x4 grid -- an interior cell

fig, axes = plotpress.subplots(2, 4, figsize=(11, 5))
flat = axes.ravel()
for i, ax in enumerate(flat):
    if i == anomaly_idx:
        y = np.sin(t) + 0.6 * np.exp(-((t - 6) ** 2) / 0.05)
    else:
        y = np.sin(t) + 0.05 * rng.standard_normal(t.size)
    ax.plot(t, y, color="#1f77b4")
    ax.set_title(f"Channel {i}", fontsize=9)

fig.group("Anomaly detected", [flat[anomaly_idx]], color="#d62728",
         linestyle="-", title_position="right", linewidth=2.0)
# The automatic minimum (see tight_layout()'s own interior-title handling)
# clears the neighboring axes' border by only a handful of pixels -- text
# width is an estimate, not a measurement (see :ref:`limitations`), and a
# title this long relative to its own column leaves that estimate little
# room for real font rendering to vary from it. group_spacing() reserves
# real, visible breathing room on top of the automatic minimum, the same
# way it would for any other interior boundary.
fig.group_spacing(wspace=40.0)
fig.tight_layout()
