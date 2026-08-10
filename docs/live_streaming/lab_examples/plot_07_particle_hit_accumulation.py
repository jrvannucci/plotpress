"""
Particle-hit accumulation map
================================

A photon-counting detector or a beam-profile monitor doesn't fill in a grid
of already-known values -- every bin starts at zero and *increments* each
time a new hit lands in it, the same bin often getting hit many times over
the course of a run. That's a different update rule from every other mesh
example in this gallery (which reveal or replace a value once). Counts only
ever go up, but there's no telling in advance how high they'll climb, so
the colour scale autoscales to the running total the same way
:doc:`../patterns/plot_02_systematic_fill` does.

Structured the way a real acquisition script would be: a callback that
receives whatever new hits the detector reported since the last tick and
pushes the updated histogram to the plot, fed here by a loop simulating the
detector's own readout. Swap ``read_next_hits()`` for a real instrument
call and ``_GalleryLiveArtist`` for ``plotpress.qt.LiveArtist`` and the
rest is unchanged.
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
    itself. ``last_artist`` (the ``Line2D``/``QuadMesh`` the most recent
    update drew) isn't part of the real API -- it's only here so a script
    that also needs a per-frame colorbar refresh has something to hand
    ``fig.colorbar()``.
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
# Live plotting -- this half doesn't change when you swap in a real detector.
# ---------------------------------------------------------------------------
NY, NX = 32, 32
gx = np.linspace(-8, 8, NX + 1)
gy = np.linspace(-8, 8, NY + 1)

fig, ax = plotpress.subplots(figsize=(6.5, 5.5))
counts = np.zeros((NY, NX))
mesh = _GalleryLiveArtist(ax, cmap="inferno")   # no vmin/vmax -- autoscales every call
_gallery_gif_frames = []
_cbar_ax = None


def on_new_hits(hx, hy):
    """Called once per acquisition tick with the (x, y) positions of
    whatever new hits landed since the last one -- bin them into the
    running histogram and redraw, autoscaling to the highest count so far.
    """
    global _cbar_ax
    hist, _, _ = np.histogram2d(hy, hx, bins=[gy, gx])
    counts[:] += hist

    mesh.update(gx, gy, counts)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm)")
    ax.set_title(f"Accumulated particle hits -- {int(counts.sum())} total")
    if _cbar_ax is not None:
        fig.delaxes(_cbar_ax)
    _cbar_ax = fig.colorbar(mesh.last_artist, ax=ax)
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))   # gallery-only


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own detector readout. Every-
# thing above only needs the (x, y) positions of new hits handed to
# on_new_hits() as they arrive.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(12)
# A beam profile (2-D Gaussian) plus flat background -- the same shape a
# real detector's hit distribution takes.
N_HITS_TOTAL = 6000
HITS_PER_TICK = 150
BEAM_FRAC = 0.85


def read_next_hits():
    """Stand-in for the detector reporting whichever hits landed this
    tick.
    """
    n_beam = int(HITS_PER_TICK * BEAM_FRAC)
    n_bg = HITS_PER_TICK - n_beam
    hx = np.concatenate([rng.normal(0.0, 1.6, n_beam), rng.uniform(-8, 8, n_bg)])
    hy = np.concatenate([rng.normal(0.5, 1.3, n_beam), rng.uniform(-8, 8, n_bg)])
    return hx, hy


for _ in range(N_HITS_TOTAL // HITS_PER_TICK):
    on_new_hits(*read_next_hits())

# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
