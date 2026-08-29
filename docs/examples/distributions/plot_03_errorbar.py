"""
Error bars
==========

``ecolor``/``elinewidth``/``capthick`` style the whiskers/caps independently
of the line and marker -- each falls back to ``color``/``linewidth`` if not
given, so a plain :meth:`errorbar` call looks exactly as it did before these
existed.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(7)
x = np.arange(10)
fig, ax = plotpress.subplots()
ax.errorbar(x, np.sin(x), yerr=rng.uniform(0.1, 0.4, 10), capsize=3,
           ecolor="#999999", elinewidth=1.0, capthick=2.0)
ax.set_title("errorbar")
fig.tight_layout()
