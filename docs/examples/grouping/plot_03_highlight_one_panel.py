"""
Highlighting one panel in a grid
===================================

``fig.group()`` works on a single axes too -- useful for calling out one
panel that stands out from its neighbors, without a separate figure or a
caption pointing back to it. This group also demonstrates the *other* half
of the margin-reservation rule from the previous two examples: it sits in
the interior of the grid, touching none of the figure's own outer edges, so
``tight_layout()`` reserves no extra margin for it -- its "Anomaly detected"
label fits in the existing gap between columns on its own.
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
fig.tight_layout()
