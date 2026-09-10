"""
Orienting yourself in an unfamiliar figure
============================================

:meth:`~plotpress.Figure.print_layout_summary` is the fastest way to
understand a figure you didn't build yourself -- one loaded from a saved
layout, handed to you by a teammate, or reconstructed from someone else's
HTML export. Rather than reading ``fig.axes``/``ax.artists`` by hand, ask
the figure directly: how many panels, how they're arranged, what's on
each one, and whether it would export cleanly to :meth:`~plotpress.Figure.to_vega`/
:meth:`~plotpress.Figure.to_vega_lite`.

This figure deliberately mixes several real structural cases in one place
-- a plain grid, a ``twinx()`` overlay, a legend, and one artist kind
neither Vega exporter maps yet -- so the summary below has something real
to say about each.
"""
import numpy as np
import plotpress

fig, axes = plotpress.subplots(1, 2, figsize=(9, 4))

t = np.linspace(0, 10, 200)
axes[0].plot(t, np.sin(t), label="signal")
axes[0].legend()
axes[0].set_title("primary vs. a secondary scale")
noise_floor = axes[0].twinx()
noise_floor.plot(t, 0.02 * t, color="C3", linestyle="--")
noise_floor.set_ylabel("noise floor")

rng = np.random.default_rng(0)
axes[1].boxplot([rng.normal(m, 1, 80) for m in (0, 1, -0.5)])
axes[1].set_title("per-channel spread")

fig.print_layout_summary()
