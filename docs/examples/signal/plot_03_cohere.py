"""
Coherence
=========
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(2)
Fs = 1000.0
n = 1 << 14
base = rng.standard_normal(n)
x = base + 0.3 * rng.standard_normal(n)
y = base + 0.3 * rng.standard_normal(n)          # coherent through a shared source

fig, ax = simpleplot.subplots()
ax.cohere(x, y, NFFT=512, Fs=Fs, noverlap=256, color="C2")
ax.set_title("cohere")
