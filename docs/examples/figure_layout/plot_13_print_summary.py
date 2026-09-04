"""
Drilling into one panel with ax.print_summary()
==================================================

:meth:`~plotpress.axes.Axes.print_summary` is the per-axes half of
:meth:`~plotpress.Figure.print_layout_summary` -- useful once
``print_layout_summary()`` has told you *which* panel needs a closer
look, or any time you already have one ``Axes`` in hand (inside a loop
over ``fig.axes``, say) and want its own position, scale, and export
compatibility without re-printing the whole figure.

Three real relationships in one figure -- a plain grid cell, an
:meth:`~plotpress.axes.Axes.inset_axes` zoom, and a colorbar -- each
describes itself differently.
"""
import numpy as np
import plotpress

fig, ax = plotpress.subplots(figsize=(6, 4.5))
t = np.linspace(0, 20, 400)
ax.plot(t, np.sin(t) * np.exp(-t / 15))
ax.set_title("damped oscillation")

zoom = ax.inset_axes((0.55, 0.55, 0.4, 0.4))
zoom.plot(t[:40], np.sin(t[:40]) * np.exp(-t[:40] / 15), color="C3")
zoom.set_title("zoom: t < 2", fontsize=8)

mesh = ax.pcolormesh(np.linspace(0, 20, 6), np.linspace(-1, 1, 6),
                     np.random.default_rng(0).random((5, 5)), alpha=0)
cbar = fig.colorbar(mesh, ax=ax)

for panel in fig.axes:
    panel.print_summary()
    print()
