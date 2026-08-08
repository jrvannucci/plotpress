"""
Animated meshes across a subplot grid
=========================================

``ax.pcolormesh_frames(x, y, C)`` is the mesh counterpart of
:doc:`plot_37_plot_frames`: ``C`` carries a leading frame axis, ``x``/``y``
stay shared across every frame, and the whole animation exports with
``fig.save(path, fps=...)`` exactly the same way. This example puts four
animated panels on one figure to exercise the same slider-scope rules
:meth:`~plotpress.axes.Axes.plot_frames` documents:

* **Top row** -- ``shared=True`` (the default): both panels drive off the
  one global slider, so scrubbing either scrubs both in lock-step.
* **Bottom row** -- ``shared=False`` with a matching ``slider_group``: each
  panel gets its own slider docked beneath it, with a link checkbox to scrub
  the two together on demand instead of independently.
"""
import os
import tempfile

import numpy as np
import plotpress

g = np.linspace(-3.0, 3.0, 90)
X, Y = np.meshgrid(g, g)
R = np.hypot(X, Y)
THETA = np.arctan2(Y, X)

fig, axes = plotpress.subplots(2, 2, figsize=(9.6, 9.0))

# Top row: shared global slider -- a rotating blob and a traveling wave,
# both stepping through the same 24 frames together.
N_MAIN = 24
angle = np.linspace(0.0, 2.0 * np.pi, N_MAIN, endpoint=False)
blob = np.stack([np.exp(-((X - 1.6 * np.cos(a)) ** 2
                         + (Y - 1.6 * np.sin(a)) ** 2) / 1.2) for a in angle])
wave = np.stack([np.sin(X * 1.6 - a) * np.exp(-R ** 2 / 10.0) for a in angle])

axes[0, 0].pcolormesh_frames(g, g, blob, slider_values=angle, slider_label="angle",
                             cmap="magma")
axes[0, 0].set_aspect("equal")
axes[0, 0].set_title("shared: orbiting blob")

axes[0, 1].pcolormesh_frames(g, g, wave, slider_values=angle, slider_label="angle",
                             cmap="coolwarm")
axes[0, 1].set_aspect("equal")
axes[0, 1].set_title("shared: traveling wave")

# Bottom row: each panel docked with its own slider, linked by a shared
# connection index ("detail") so they can be scrubbed together on demand
# without being forced onto the same global slider as the top row.
N_DETAIL = 16
grow = np.linspace(0.3, 2.6, N_DETAIL)
ring = np.stack([np.exp(-((R - r) ** 2) / 0.06) for r in grow])
petals = np.stack([np.cos(THETA * 5.0) * np.exp(-((R - r) ** 2) / 0.5)
                   for r in grow])

axes[1, 0].pcolormesh_frames(g, g, ring, slider_values=grow, slider_label="radius",
                             shared=False, slider_group="detail", cmap="viridis")
axes[1, 0].set_aspect("equal")
axes[1, 0].set_title("docked: growing ring")

axes[1, 1].pcolormesh_frames(g, g, petals, slider_values=grow, slider_label="radius",
                             shared=False, slider_group="detail", cmap="viridis")
axes[1, 1].set_aspect("equal")
axes[1, 1].set_title("docked: growing petals (linkable)")

fig.tight_layout()

gif_path = os.path.join(tempfile.gettempdir(), "plotpress_pcolormesh_frames_grid.gif")
fig.save(gif_path, fps=10)          # animates the top row's shared "main" slider
