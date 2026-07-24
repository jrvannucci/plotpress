"""
Cross-correlation
=================
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(0)
n = 400
x = rng.standard_normal(n)
y = np.roll(x, 15) + 0.4 * rng.standard_normal(n)   # y lags x by 15 samples

fig, ax = simpleplot.subplots()
ax.xcorr(x, y, maxlags=40, color="C2")
ax.set_title("xcorr (peak at the lag)"); ax.set_xlabel("lag")
