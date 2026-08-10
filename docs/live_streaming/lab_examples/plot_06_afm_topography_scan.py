"""
AFM/STM topography raster scan
=================================

A scanning-probe microscope builds its image the way a CRT does: the tip
sweeps the fast axis (x) pixel by pixel, then steps the slow axis (y) and
sweeps back -- the same fixed-grid, fixed-scale, point-by-point order as the
acquisition-pattern gallery's raster example, just with physical units (nm)
and a surface topography stand-in (a grain boundary with a step edge)
instead of an abstract field.

Structured the way a real acquisition script would be: a callback that
receives whatever new pixels the tip reported since the last tick and
pushes the updated image to the plot, fed here by a loop simulating the
scan controller. Swap ``read_next_pixels()`` for a real instrument call
and ``_GalleryLiveArtist`` for ``plotpress.qt.LiveArtist`` and the rest is
unchanged.
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
# Live plotting -- this half doesn't change when you swap in a real scanner.
# ---------------------------------------------------------------------------
NY, NX = 20, 28                    # slow axis (y), fast axis (x) pixel counts
FIELD_NM = 200.0                   # scan size, nm -- fixed by the scan setup
VMIN, VMAX = -0.3, 3.0             # the instrument's own known height range

gx = np.linspace(0, FIELD_NM, NX + 1)
gy = np.linspace(0, FIELD_NM, NY + 1)

fig, ax = plotpress.subplots(figsize=(7, 5.2))
grid = np.full((NY, NX), np.nan)

# One-time setup: draw the still-empty image so the axes decorations and
# colorbar are in place before any live updates start.
m0 = ax.pcolormesh(gx, gy, grid, cmap="inferno", vmin=VMIN, vmax=VMAX)
ax.set_aspect("equal")
ax.set_xlabel("x (nm, fast axis)"); ax.set_ylabel("y (nm, slow axis)")
ax.set_title("AFM topography scan")
fig.colorbar(m0, ax=ax)
fig.tight_layout()

image = _GalleryLiveArtist(ax, cmap="inferno", vmin=VMIN, vmax=VMAX)
_gallery_gif_frames = []


def on_new_pixels(pixels):
    """Called once per acquisition tick with whatever ``(row, col, height)``
    pixels the tip reported since the last one.
    """
    for r, c, h in pixels:
        grid[r, c] = h
    image.update(gx, gy, grid)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlabel("x (nm, fast axis)"); ax.set_ylabel("y (nm, slow axis)")
    ax.set_title("AFM topography scan")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))   # gallery-only


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own scan controller. Every-
# thing above only needs a list of (row, col, height) pixels handed to
# on_new_pixels() as they're measured.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(8)
cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
x_nm = (cols + 0.5) * FIELD_NM / NX
y_nm = (rows + 0.5) * FIELD_NM / NY

# A step edge (grain boundary) plus a rounded hillock -- both common AFM
# topography features -- and a little scan noise.
STEP_HEIGHT_NM = 1.8
step = STEP_HEIGHT_NM / (1.0 + np.exp(-(x_nm + 0.6 * y_nm - 140.0) / 6.0))
hillock = 1.1 * np.exp(-((x_nm - 60.0) ** 2 + (y_nm - 130.0) ** 2) / (2 * 22.0 ** 2))
height_nm = step + hillock + 0.04 * rng.standard_normal((NY, NX))

# Fast axis first (x, one pixel at a time), then step the slow axis (y).
order = [(r, c) for r in range(NY) for c in range(NX)]
PIXELS_PER_TICK = 12


def read_next_pixels(lo, hi):
    """Stand-in for the tip reporting whichever pixels it measured this
    tick, in raster order.
    """
    return [(r, c, float(height_nm[r, c])) for r, c in order[lo:hi]]


for lo in range(0, len(order), PIXELS_PER_TICK):
    hi = min(lo + PIXELS_PER_TICK, len(order))
    on_new_pixels(read_next_pixels(lo, hi))

# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
