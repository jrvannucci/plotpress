"""
Line styles
===========

The four dash patterns ``plot()`` (and every other line-drawing method --
``hlines``/``vlines``/``axhline``/``axvline``/``axline``/``errorbar``/
``Figure.group()``) understands, each in both the short form matplotlib
users already know and its equally valid long-form alias -- ``"dashed"``
draws the exact same pattern as ``"--"``, not a second, different style.
Solid needs no ``linestyle=`` at all; it is every method's own default.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)
fig, ax = plotpress.subplots(figsize=(8, 5))

ax.plot(x, np.sin(x) + 3.0, linestyle="-", label="'-' (solid, the default)")
ax.plot(x, np.sin(x) + 2.0, linestyle="--", label="'--'")
ax.plot(x, np.sin(x) + 2.0 - 0.15, linestyle="dashed", label="'dashed' (same pattern)")
ax.plot(x, np.sin(x) + 1.0, linestyle=":", label="':'")
ax.plot(x, np.sin(x) + 1.0 - 0.15, linestyle="dotted", label="'dotted' (same pattern)")
ax.plot(x, np.sin(x) + 0.0, linestyle="-.", label="'-.'")
ax.plot(x, np.sin(x) + 0.0 - 0.15, linestyle="dashdot", label="'dashdot' (same pattern)")

ax.set_title("Line styles -- short form and long-form alias draw identically")
ax.set_xlabel("x"); ax.set_ylabel("y")
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
