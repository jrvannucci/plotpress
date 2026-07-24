"""
Angle spectrum
==============
"""
import numpy as np
import simpleplot

Fs = 1000.0
t = np.arange(0, 1, 1 / Fs)
x = np.sin(2 * np.pi * 50 * t + 0.6) + 0.5 * np.sin(2 * np.pi * 120 * t)

fig, ax = simpleplot.subplots()
ax.angle_spectrum(x, Fs=Fs, color="C0")
ax.set_title("angle_spectrum (wrapped)")
