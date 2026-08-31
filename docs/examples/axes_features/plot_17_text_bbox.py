"""
Boxed text and callouts (bbox=)
==================================

``ax.text()``/``ax.annotate()`` already had ``outline`` -- a halo traced
around the glyphs themselves, for plain legibility over an unpredictable
background. ``bbox=`` is a different tool: a filled, optionally bordered box
*behind* the label, matplotlib's own ``bbox=`` dict (a subset of its keys --
``facecolor``/``fc``, ``edgecolor``/``ec``, ``alpha``, ``pad``, ``boxstyle``,
``linewidth``). Where ``outline`` keeps a label readable, ``bbox`` reads as a
callout chip sitting on top of the data.

With ``annotate()``, the arrow leader attaches to the box's own padded edge,
not the bare text -- it visibly touches the box instead of stopping short of
it.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(3)
x = np.linspace(0, 10, 300)
y = np.sin(x) * np.exp(-x / 8.0) + rng.normal(scale=0.03, size=x.size)

fig, ax = plotpress.subplots(figsize=(9.0, 5.2))
ax.plot(x, y, color="#1f77b4", linewidth=1.4)

# A plain label with no bbox, for comparison -- floats with no visual anchor.
ax.text(8.5, 0.55, "no bbox", fontsize=9, color="#666666")

# The default bbox: a plain white box, enough to lift a label off the line.
ax.text(1.0, -0.55, "default bbox={}", bbox={})

# A styled callout: rounded corners, a custom fill/edge, semi-transparent so
# the gridline under it still shows through.
ax.grid(True, alpha=0.3)
ax.text(4.2, 0.6, "styled: round + alpha", color="#412402",
       bbox={"facecolor": "#fac775", "edgecolor": "#854f0b", "alpha": 0.75,
             "boxstyle": "round", "pad": 6})

# annotate() with both an arrow and a bbox -- the leader stops at the box's
# own edge, not the bare text underneath it.
peak_i = int(np.argmax(y[:80]))
ax.annotate(f"peak: y={y[peak_i]:.2f}", xy=(x[peak_i], y[peak_i]),
           xytext=(3.0, 0.85), arrowprops={"color": "#993c1d", "alpha": 0.8},
           bbox={"facecolor": "#faece7", "edgecolor": "#993c1d", "boxstyle": "round"})

ax.set_title("bbox= on text() and annotate(): a callout chip, not just a halo")
ax.set_xlim(0, 10)
fig.tight_layout()
