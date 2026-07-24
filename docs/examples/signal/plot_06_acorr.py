"""
Autocorrelation
===============
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(3)
# AR(1) process: neighbouring samples correlate, so acorr decays with lag
x = np.zeros(600)
for i in range(1, x.size):
    x[i] = 0.8 * x[i - 1] + rng.standard_normal()

fig, ax = simpleplot.subplots()
ax.acorr(x, maxlags=40, color="C0")
ax.set_title("acorr"); ax.set_xlabel("lag")
