"""
Phase spectrum
==============
"""
import numpy as np
import plotpress

Fs = 1000.0
t = np.arange(0, 1, 1 / Fs)
x = np.sin(2 * np.pi * 50 * t + 0.6) + 0.5 * np.sin(2 * np.pi * 120 * t)

fig, ax = plotpress.subplots()
ax.phase_spectrum(x, Fs=Fs, color="C3")
ax.set_title("phase_spectrum (unwrapped)")
