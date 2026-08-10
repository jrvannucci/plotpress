"""
Radio telescope beam map, serpentine scan
=============================================

An on-the-fly sky survey doesn't raster back to the start of each row --
that would waste half the observing time slewing the dish. It scans one row
left to right, steps down, then scans right to left, alternating direction
every row (a "boustrophedon" or serpentine pattern) so the telescope is
always integrating, never just repositioning. The grid and colour scale are
both fixed by the survey plan, exactly like the acquisition-pattern
gallery's raster example -- only the *order* pixels arrive in differs.

Structured the way a real acquisition script would be: a callback that
receives whatever new pixels the dish reported since the last tick and
pushes the updated map to the plot, fed here by a loop simulating the
survey controller. Swap ``read_next_pixels()`` for a real instrument call
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
# Live plotting -- this half doesn't change when you swap in a real dish.
# ---------------------------------------------------------------------------
NY, NX = 22, 34                  # declination steps, right-ascension steps
gx = np.linspace(-1.5, 1.5, NX + 1)   # degrees, RA offset
gy = np.linspace(-1.0, 1.0, NY + 1)   # degrees, Dec offset
VMIN, VMAX = 2.5, 10.2           # the receiver's own known temperature range, K

fig, ax = plotpress.subplots(figsize=(8, 5.2))
grid = np.full((NY, NX), np.nan)

# One-time setup: draw the still-empty map so the axes decorations and
# colorbar are in place before any live updates start.
m0 = ax.pcolormesh(gx, gy, grid, cmap="magma", vmin=VMIN, vmax=VMAX)
ax.set_aspect("equal")
ax.set_xlabel("RA offset (deg)"); ax.set_ylabel("Dec offset (deg)")
ax.set_title("On-the-fly sky survey, serpentine scan")
fig.colorbar(m0, ax=ax)
fig.tight_layout()

sky_map = _GalleryLiveArtist(ax, cmap="magma", vmin=VMIN, vmax=VMAX)
_gallery_gif_frames = []


def on_new_pixels(pixels):
    """Called once per acquisition tick with whatever ``(row, col,
    temperature)`` pixels the dish reported since the last one.
    """
    for r, c, temp in pixels:
        grid[r, c] = temp
    sky_map.update(gx, gy, grid)
    ax.set_aspect("equal")             # cla() inside update() wiped these
    ax.set_xlabel("RA offset (deg)"); ax.set_ylabel("Dec offset (deg)")
    ax.set_title("On-the-fly sky survey, serpentine scan")
    fig.tight_layout()
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))   # gallery-only


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own survey controller. Every-
# thing above only needs a list of (row, col, temperature) pixels handed to
# on_new_pixels() as they're measured.
# ---------------------------------------------------------------------------
rng = np.random.default_rng(19)
cols, rows = np.meshgrid(np.arange(NX), np.arange(NY))
ra = (cols + 0.5) * 3.0 / NX - 1.5
dec = (rows + 0.5) * 2.0 / NY - 1.0

# Background sky temperature plus two point sources of different brightness.
SOURCES = [(-0.5, 0.3, 8.0, 0.06), (0.6, -0.2, 4.5, 0.05)]
temp_k = 2.7 + 0.05 * rng.standard_normal((NY, NX))
for src_ra, src_dec, peak, width in SOURCES:
    temp_k += peak * np.exp(-((ra - src_ra) ** 2 + (dec - src_dec) ** 2) / (2 * width ** 2))

# Serpentine order: row 0 left to right, row 1 right to left, and so on --
# an on-the-fly survey never slews back to the start of a row.
order = []
for r in range(NY):
    cols_this_row = range(NX) if r % 2 == 0 else range(NX - 1, -1, -1)
    order.extend((r, c) for c in cols_this_row)
PIXELS_PER_TICK = 10


def read_next_pixels(lo, hi):
    """Stand-in for the dish reporting whichever pixels it measured this
    tick, in serpentine order.
    """
    return [(r, c, float(temp_k[r, c])) for r, c in order[lo:hi]]


for lo in range(0, len(order), PIXELS_PER_TICK):
    hi = min(lo + PIXELS_PER_TICK, len(order))
    on_new_pixels(read_next_pixels(lo, hi))
for _ in range(2):   # hold on the fully-filled frame for a moment
    _gallery_gif_frames.append(_gallery_gif_frames[-1])

# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
