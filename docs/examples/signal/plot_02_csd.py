"""
Cross spectral density
======================
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(1)
Fs = 1000.0
t = np.arange(0, 4, 1 / Fs)
common = np.sin(2 * np.pi * 90 * t)
x = common + 0.5 * rng.standard_normal(t.size)
y = np.roll(common, 12) + 0.5 * rng.standard_normal(t.size)   # shared 90 Hz tone

fig, ax = simpleplot.subplots()
ax.csd(x, y, NFFT=512, Fs=Fs, noverlap=256, color="C3")
ax.set_title("csd")
