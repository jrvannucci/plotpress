"""
Frame slider
============

``ax.plot_frames(x, Y)`` plots 3-D data ``Y`` of shape ``(n_frames, n_points)``
as a line with a play/pause/step slider over the extra dimension -- the static
gallery image below captures frame 0; open the figure as interactive HTML to
scrub it.
"""
import numpy as np
import plotpress

x = np.linspace(0, 2 * np.pi, 200)
t = np.linspace(0, 2 * np.pi, 30, endpoint=False)
wave = np.sin(x[None, :] - t[:, None])          # (n_frames, n_points)

fig, ax = plotpress.subplots()
ax.plot_frames(x, wave, slider_values=t, slider_label="t", label="wave")
ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_title("Frame slider")
ax.set_ylim(-1.2, 1.2)
ax.legend()
fig.tight_layout()
