"""
Text and annotations
====================

``ax.text`` and ``ax.annotate`` with an arrow.
"""
import numpy as np
import plotpress

x = np.linspace(0, 10, 200)
y = np.sin(x) * np.exp(-x / 8)
fig, ax = plotpress.subplots()
ax.plot(x, y)
i = int(np.argmax(y))
ax.annotate("peak", xy=(x[i], y[i]), xytext=(x[i] + 2, y[i] + 0.15),
            arrowprops={"color": "#d62728"})
ax.text(6, -0.3, "damped sine", color="#555")
ax.set_title("Annotations")
fig.tight_layout()
