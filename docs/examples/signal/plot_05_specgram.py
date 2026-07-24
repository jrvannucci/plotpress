"""
Spectrogram
===========
"""
import numpy as np
import simpleplot

Fs = 2000.0
t = np.arange(0, 3, 1 / Fs)
# a linear chirp sweeping 50 -> 500 Hz, so the band rises across the spectrogram
x = np.sin(2 * np.pi * (50 * t + (450 / (2 * 3)) * t ** 2))

fig, ax = simpleplot.subplots()
m, freqs, times, im = ax.specgram(x, NFFT=256, Fs=Fs, noverlap=200, cmap="magma")
ax.set_title("specgram"); fig.colorbar(im, ax=ax)
