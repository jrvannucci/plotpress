"""
Restricting point picking to one axes
=======================================

``set_pickable(False)`` excludes an axes from the interactive toolbar's
**Point Picking** tool -- a click there behaves as if it missed every axes.
**Axis Span**, **Axis Zoom**, **Figure Navigator**, and **Annotation** are
unaffected, so a figure can restrict picking to a single panel while every
other tool still works everywhere. The static image below looks like an
ordinary grid -- the effect only shows up in ``interactive=True`` output, so
this is also a live figure in the online docs.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)

fig, (left, right) = plotpress.subplots(1, 2, figsize=(7, 3.2))
left.plot(x, np.sin(x), color="#1f77b4")
left.set_title("pickable (default)")
right.plot(x, np.cos(x), color="#d62728")
right.set_title("set_pickable(False)")
right.set_pickable(False)
fig.tight_layout()
