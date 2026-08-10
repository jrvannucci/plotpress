"""
Both axes growing: a search window expanding outward
========================================================

Combine :doc:`plot_03_growing_xaxis` with the same growth in ``y``: a search
that starts small and widens its window in both directions each time the
edge of what's been measured still looks interesting -- outward from a seed
region rather than sweeping the same fixed range. Both axes limits *and*
the mesh shape change every frame.

Structured the way a real acquisition script would be: a callback that
receives a freshly re-measured (and now larger) window and pushes it to the
plot, fed here by a loop simulating a search controller that keeps widening
until it decides it's seen enough. Swap ``read_window()`` for a real
instrument call and ``_GalleryLiveArtist`` for ``plotpress.qt.LiveArtist``
and the rest is unchanged.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image


class _GalleryLiveArtist:
    """Doc-build-only stand-in for ``plotpress.qt.LiveArtist`` -- there's no
    Qt binding to drive a real window with at doc-build time, so this only
    reproduces ``update()``'s redraw behavior (``ax.cla()``, replot, and for
    a line the same auto x-limits from the data) and nothing else. Swap it
    for ``from plotpress.qt import PlotPressWidget, LiveArtist`` and
    ``LiveArtist(widget, fig, ax, **plot_kwargs)`` -- every
    ``artist.update(...)`` call below needs no other change; just drop each
    callback's trailing ``_gallery_gif_frames.append(...)`` line, since a
    real ``LiveArtist`` already pushes every frame to the live window
    itself.
    """

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


# ---------------------------------------------------------------------------
# Live plotting -- this half doesn't change when you swap in a real search.
# ---------------------------------------------------------------------------
VMIN, VMAX = 0.0, 10.0   # the instrument's own known reading range
CX, CY = 20.0, 20.0      # the window's fixed center; only its extent grows
MAX_HALF = 20            # widest the window is ever allowed to grow

fig, ax = plotpress.subplots(figsize=(6, 5.5))
mesh = _GalleryLiveArtist(ax, cmap="viridis", vmin=VMIN, vmax=VMAX)
_gallery_gif_frames = []

# One-time colorbar: the scale is fixed, so it never needs a per-frame
# refresh the way plot_02_systematic_fill's autoscaled one does.
m0 = ax.pcolormesh(np.array([CX - 1, CX + 1]), np.array([CY - 1, CY + 1]),
                   np.zeros((1, 1)), cmap="viridis", vmin=VMIN, vmax=VMAX)
fig.colorbar(m0, ax=ax)


def on_new_scan(half, gx, gy, C):
    """Called each time the search widens its window and re-measures it."""
    mesh.update(gx, gy, C)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlim(CX - MAX_HALF - 1, CX + MAX_HALF + 1)   # fixed frame
    ax.set_ylim(CY - MAX_HALF - 1, CY + MAX_HALF + 1)
    ax.set_xlabel("x"); ax.set_ylabel("y")
    ax.set_title(f"Search window: +-{half}")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))   # gallery-only


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own search controller. Every-
# thing above only needs a re-measured (gx, gy, C) window handed to
# on_new_scan() each time it widens.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(23)


def read_window(half):
    """Stand-in for the instrument re-scanning a window of half-width
    ``half`` centered on (CX, CY).
    """
    n = 2 * half + 1
    gx = np.linspace(CX - half, CX + half, n)
    gy = np.linspace(CY - half, CY + half, n)
    xs, ys = np.meshgrid(gx, gy)
    C = (np.exp(-((xs - CX) ** 2 + (ys - CY) ** 2) / 60.0) * 10.0
         + 0.15 * rng.standard_normal(xs.shape))
    return gx, gy, C


for half in range(2, MAX_HALF + 1, 2):
    gx, gy, C = read_window(half)
    on_new_scan(half, gx, gy, C)

# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
