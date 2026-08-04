"""
Resizing a figure after creation
==================================

``set_size_inches``/``set_dpi`` mutate a figure already built -- the same
axes and data, rendered at a different physical size and resolution.
"""
import numpy as np
import plotpress


def _plot():
    fig, ax = plotpress.subplots(figsize=(4, 3))
    ax.plot(np.linspace(0, 10, 200), np.sin(np.linspace(0, 10, 200)))
    return fig, ax


fig, ax = _plot()
ax.set_title(f"{fig.get_size_inches()} @ {fig.get_dpi():.0f} dpi")

# %%
# The same figure, grown wider and rendered at a higher DPI after the fact:

fig2, ax2 = _plot()
fig2.set_size_inches(9, 3)
fig2.set_dpi(150)
ax2.set_title(f"resized to {fig2.get_size_inches()} @ {fig2.get_dpi():.0f} dpi")
