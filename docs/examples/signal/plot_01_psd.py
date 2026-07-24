"""
Power spectral density
======================
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(0)
Fs = 1000.0
t = np.arange(0, 4, 1 / Fs)
x = np.sin(2 * np.pi * 120 * t) + 0.6 * np.sin(2 * np.pi * 250 * t)
x += 0.6 * rng.standard_normal(t.size)

fig, ax = simpleplot.subplots()
ax.psd(x, NFFT=512, Fs=Fs, noverlap=256, color="C0")
ax.set_title("psd")
