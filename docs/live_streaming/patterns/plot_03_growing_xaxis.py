"""
An x axis whose extent isn't known up front
==============================================

Sometimes the sweep range itself is the unknown -- a search that keeps
extending until a stopping condition is met, rather than a pre-planned grid.
Here ``x`` grows one column at a time and the axes limits grow with it,
while ``y`` and the colour scale stay fixed throughout.

The code below is exactly what you'd write against the real
``plotpress.qt.LiveArtist``: a callback that receives one finished column at
a time and pushes it to the plot, fed by a loop simulating a sweep
controller that doesn't know its own stopping point yet. Only
``read_next_column()`` is meant to be replaced, with your own instrument
call.
"""
import numpy as np
import plotpress

# sphinx_gallery_start_ignore
# Doc-build-only harness below: there's no Qt binding to drive a real window
# with at doc-build time, so LiveArtist here reproduces plotpress.qt.
# LiveArtist's update() exactly (ax.cla(), replot, the same auto x-limits for
# a line) and renders a frame instead of pushing one to a live window. None
# of this -- including this whole ignored block -- is part of what a real
# script using the actual LiveArtist would need.
from plotpress.raster import figure_to_image


class LiveArtist:
    def __init__(self, ax, **plot_kwargs):
        self.ax = ax
        self.plot_kwargs = plot_kwargs
        self.last_artist = None

    def update(self, *data):
        self.ax.cla()
        if len(data) == 2:
            x, y = data
            self.last_artist = self.ax.plot(x, y, **self.plot_kwargs)
            if len(x):
                self.ax.set_xlim(float(min(x)), float(max(x)))
        elif len(data) == 3:
            x, y, c = data
            self.last_artist = self.ax.pcolormesh(x, y, c, **self.plot_kwargs)
        else:
            raise TypeError("update() takes (x, y) or (x, y, C)")


_gallery_gif_frames = []
# sphinx_gallery_end_ignore

NY = 18
Y = np.arange(NY + 1, dtype=float)
VMIN, VMAX = 0.0, 10.0   # the instrument's own known reading range
N_STEPS_EXPECTED = 26    # only used to size the fixed x window below

fig, ax = plotpress.subplots(figsize=(7, 4.5))
mesh = LiveArtist(ax, cmap="plasma", vmin=VMIN, vmax=VMAX)
cols_collected = []

# One-time colorbar: the scale is fixed, so it never needs a per-frame
# refresh the way plot_02_systematic_fill's autoscaled one does.
m0 = ax.pcolormesh(np.array([0.0, 1.0]), Y, np.zeros((NY, 1)), cmap="plasma",
                   vmin=VMIN, vmax=VMAX)
fig.colorbar(m0, ax=ax)


def on_new_column(x0, values):
    """Called once per column the sweep finishes -- append it and redraw
    with one more column of x extent than before.
    """
    cols_collected.append(values)
    X = np.arange(len(cols_collected) + 1, dtype=float)
    C = np.column_stack(cols_collected)
    mesh.update(X, Y, C)
    ax.set_xlim(0, N_STEPS_EXPECTED)   # cla() wiped this -- fixed frame, shows how far there is to go
    ax.set_xlabel("x (sweep step)"); ax.set_ylabel("y index")
    ax.set_title(f"Growing x axis: {len(cols_collected)}/{N_STEPS_EXPECTED} columns collected")
    fig.tight_layout()
    # sphinx_gallery_start_ignore
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))
    # sphinx_gallery_end_ignore


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own sweep controller. Every-
# thing above only needs an x value and its column of readings handed to
# on_new_column() as each one finishes.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(11)
rows = np.arange(NY)


def read_next_column(x0):
    """Stand-in for the sweep controller reporting a finished column at
    sweep position x0.
    """
    return (np.exp(-((rows - 9) ** 2) / 22.0) * 8.0 * np.cos(x0 / 4.0) ** 2
            + 0.15 * rng.standard_normal(NY))


for step in range(N_STEPS_EXPECTED):
    on_new_column(float(step), read_next_column(float(step)))

# sphinx_gallery_start_ignore
# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
# sphinx_gallery_end_ignore
