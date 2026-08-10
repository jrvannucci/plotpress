"""
Titration curve, marking the equivalence point live
=======================================================

A pH titration is added drop by drop, so the x axis (volume of titrant
added) only ever grows -- the same shape as the acquisition-pattern
gallery's growing-x-axis example, but with two lab-specific details: ``y``
is bounded to the pH scale regardless of how far ``x`` grows, and once
enough of the curve is in, the steepest point (the equivalence point) can be
found and annotated live rather than only after the run finishes.
"""
import numpy as np
import plotpress
from plotpress.raster import figure_to_image

TRUE_EQUIV_ML = 24.6
rng = np.random.default_rng(9)


def ph_at(volume_ml):
    # A sigmoid stand-in for a strong-acid/strong-base titration curve.
    return 7.0 + 6.0 * np.tanh((volume_ml - TRUE_EQUIV_ML) / 1.3)


n_drops = 62
volumes = np.linspace(0.2, 40.0, n_drops)

vs, phs = [], []
equiv_found_at = None
_gallery_gif_frames = []
for i, v in enumerate(volumes):
    vs.append(v)
    phs.append(ph_at(v) + 0.05 * rng.standard_normal())

    fig, ax = plotpress.subplots(figsize=(6.5, 5))
    ax.plot(vs, phs, color="#2ca02c", linewidth=1.0)
    ax.scatter(vs, phs, color="#2ca02c", s=14)
    ax.set_xlim(0, 40)
    ax.set_ylim(0, 14)
    ax.axhline(7.0, color="#888888", linestyle=":", linewidth=1.0)
    ax.set_xlabel("titrant added (mL)"); ax.set_ylabel("pH")
    ax.set_title(f"Titration in progress -- drop {i + 1}/{n_drops}")

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
    _gallery_gif_frames.append(figure_to_image(fig, scale=2))

del fig, ax
