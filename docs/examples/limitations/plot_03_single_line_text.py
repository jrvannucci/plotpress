"""
Text is single-line, and PNG is a separate renderer
===================================================

Two design choices meet here. simpleplot lays out only **single-line** strings
-- there is no rich text, no math, no multi-line wrapping. And PNG is drawn by a
second backend (Pillow) rather than by rasterizing the SVG, because every SVG
rasterizer in Python needs cairo, a system library rather than a pip wheel.

A newline exposes both at once. The raster backend breaks the line; an SVG
viewer collapses the ``\\n`` to a space. So the *same* figure with a ``\\n`` in a
label looks different depending on the format -- the one place the two backends
visibly disagree.

The figure below is a PNG, so the red label breaks into two lines. In SVG it
would read ``peak 3.2 (2024)`` on a single line. The green label uses two
separate ``text()`` calls and looks identical in every format.
"""
import numpy as np
import simpleplot

x = np.linspace(0, 10, 200)
y = np.sin(x) * np.exp(-x / 8)

fig, ax = simpleplot.subplots(figsize=(8, 4.5))
ax.plot(x, y)

# Not portable: one text() call with a newline. PNG (this image) breaks it into
# two lines; an SVG viewer collapses the newline and draws it on one line.
ax.text(5.6, 0.6, "peak 3.2\n(2024)", color="#d62728", fontsize=12, va="top")

# Portable: two text() calls, one per line. Identical in PNG, SVG and PDF.
ax.text(5.6, 0.0, "peak 3.2", color="#2ca02c", fontsize=12)
ax.text(5.6, -0.1, "(2024)", color="#2ca02c", fontsize=12)

ax.set_title("A newline renders in PNG but collapses in SVG")
ax.set_xlabel("x")
ax.set_ylabel("y")
fig.tight_layout()

# %%
# Reading it
# ----------
#
# * **Red** -- ``ax.text(..., "peak 3.2\\n(2024)")``. Two lines here, one line in
#   SVG. Never rely on a ``\\n`` if the same figure might be exported to more
#   than one format.
# * **Green** -- two ``text()`` calls at stacked ``y`` positions. Portable, and
#   the only supported way to stack lines.
#
# The broader point: SVG (and the PDF built from it) is the reference rendering,
# and PNG re-draws the same primitives through Pillow. They share the layout and
# the metrics, so they match closely, but they are not guaranteed
# pixel-identical -- a newline is simply the case where the gap is obvious rather
# than sub-pixel.
