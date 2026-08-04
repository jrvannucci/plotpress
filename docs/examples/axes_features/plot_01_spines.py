"""
Spines
======

``ax.spines`` is a dict of the four box sides, each independently
visible/colored -- hide the top and right spines for a "despined" look, and
color the remaining two differently so it's clear each side is its own
independent ``Spine``, not one shared box color.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, ax = plotpress.subplots()
ax.plot(x, np.sin(x), color="#1f77b4")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("green")
ax.spines["bottom"].set_color("red")
ax.spines["bottom"].set_linewidth(1.5)
ax.set_title("despined, with distinct per-side colors")
