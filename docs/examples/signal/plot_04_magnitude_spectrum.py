"""
Magnitude spectrum
==================
"""
import numpy as np
import plotpress

Fs = 1000.0
t = np.arange(0, 2, 1 / Fs)
x = np.sin(2 * np.pi * 60 * t) + 0.5 * np.sin(2 * np.pi * 180 * t)

fig, ax = plotpress.subplots()
ax.magnitude_spectrum(x, Fs=Fs, scale="dB", color="C4")
ax.set_title("magnitude_spectrum (dB)")
