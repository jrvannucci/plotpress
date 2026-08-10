"""
Titration curve, marking the equivalence point live
=======================================================

A pH titration is added drop by drop, so the x axis (volume of titrant
added) only ever grows -- the same shape as the acquisition-pattern
gallery's growing-x-axis example, but with two lab-specific details: ``y``
is bounded to the pH scale regardless of how far ``x`` grows, and once
enough of the curve is in, the steepest point (the equivalence point) can be
found and annotated live rather than only after the run finishes.

The code below is exactly what you'd write against the real
``plotpress.qt.LiveArtist``: a callback that receives one drop at a time
and pushes it to the plot, fed by a loop simulating a titrator. Only
``read_next_drop()`` is meant to be replaced, with your own instrument
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

fig, ax = plotpress.subplots(figsize=(6.5, 5))
curve = LiveArtist(ax, color="#2ca02c", linewidth=1.0)
vs, phs = [], []
equiv_found_at = None


def on_new_drop(v, ph):
    """Called once per drop added -- push the new (volume, pH) reading and
    redraw, checking whether enough of the curve is in yet to locate and
    mark the equivalence point.
    """
    global equiv_found_at
    vs.append(v)
    phs.append(ph)

    curve.update(np.array(vs), np.array(phs))
    ax.scatter(vs, phs, color="#2ca02c", s=14)   # cla() inside update() wiped this
    ax.set_xlim(0, 40); ax.set_ylim(0, 14)
    ax.axhline(7.0, color="#888888", linestyle=":", linewidth=1.0)
    ax.set_xlabel("titrant added (mL)"); ax.set_ylabel("pH")
    ax.set_title(f"Titration in progress -- drop {len(vs)}")

    # Once there's enough curve to have crossed the steepest section, find
    # and mark it -- exactly the kind of "annotate as it's discovered"
    # detail a live plot can do that a pre-rendered static curve can't.
    if len(vs) >= 6:
        d_ph = np.gradient(np.array(phs), np.array(vs))
        peak = int(np.argmax(np.abs(d_ph)))
        if np.abs(d_ph[peak]) > 1.5 and vs[peak] not in (vs[0], vs[-1]):
            equiv_found_at = vs[peak]
    if equiv_found_at is not None:
        ax.axvline(equiv_found_at, color="#d62728", linestyle="--", linewidth=1.2)
        ax.annotate(f"equivalence ~ {equiv_found_at:.1f} mL", (equiv_found_at, 11.0),
                    xytext=(equiv_found_at + 2.0, 12.5), color="#d62728")

    fig.tight_layout()
    # sphinx_gallery_start_ignore
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))
    # sphinx_gallery_end_ignore


# ---------------------------------------------------------------------------
# Data acquisition -- replace this with your own titrator/pH meter driver.
# Everything above only needs a (volume, pH) reading handed to
# on_new_drop() as each drop is added.
# ---------------------------------------------------------------------------
TRUE_EQUIV_ML = 24.6
rng = np.random.default_rng(9)
N_DROPS = 62
drop_volumes = np.linspace(0.2, 40.0, N_DROPS)


def read_next_drop(volume_ml):
    """Stand-in for the pH meter reporting a reading after this drop --
    a sigmoid curve for a strong-acid/strong-base titration, plus noise.
    """
    ph = 7.0 + 6.0 * np.tanh((volume_ml - TRUE_EQUIV_ML) / 1.3)
    return ph + 0.05 * rng.standard_normal()


for volume_ml in drop_volumes:
    on_new_drop(volume_ml, read_next_drop(volume_ml))

# sphinx_gallery_start_ignore
# fig (and its axes) is a single, module-level object updated in place
# across every tick above -- not a fresh one per frame -- so it's still a
# bare global here and needs an explicit del, or the gallery scraper would
# also capture it as a redundant static PNG alongside the GIF.
del fig, ax
# sphinx_gallery_end_ignore
