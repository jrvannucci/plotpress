"""Signal-processing plot methods: psd/csd/cohere, spectra, specgram, xcorr.

These check the estimators are numerically right (the tone lands in the correct
frequency bin, coherence is bounded, autocorrelation peaks at lag 0), not just
that the calls render -- correctness the delegation to plot/imshow can't fake.
"""
import numpy as np
import pytest

import plotpress


def _tone(freq, Fs, n, seed=0):
    """A sinusoid at ``freq`` Hz plus a little noise, sampled at ``Fs``."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / Fs
    return np.sin(2 * np.pi * freq * t) + 0.01 * rng.standard_normal(n)


def test_psd_peaks_at_the_tone_frequency():
    Fs, f0 = 1000.0, 100.0
    x = _tone(f0, Fs, 8192)
    fig, ax = plotpress.subplots()
    Pxx, freqs, line = ax.psd(x, NFFT=1024, Fs=Fs, noverlap=512)
    assert Pxx.shape == freqs.shape
    assert abs(freqs[np.argmax(Pxx)] - f0) <= Fs / 1024      # within one bin
    # method delegates to a real line artist and labels the axes
    assert line in ax.artists
    assert ax._ylabel.startswith("Power Spectral Density")


def test_specgram_shape_and_extent():
    Fs = 1000.0
    x = _tone(120.0, Fs, 4096)
    fig, ax = plotpress.subplots()
    P, freqs, t, im = ax.specgram(x, NFFT=256, Fs=Fs, noverlap=128)
    assert P.shape == (freqs.size, t.size)
    assert im in ax.artists
    assert freqs[np.argmax(P.mean(axis=1))] == pytest.approx(120.0, abs=Fs / 256)


def test_cohere_is_bounded_and_high_for_related_signals():
    Fs = 1000.0
    rng = np.random.default_rng(1)
    n = 16384
    base = rng.standard_normal(n)
    x = base + 0.1 * rng.standard_normal(n)
    y = base + 0.1 * rng.standard_normal(n)              # shares the same source
    fig, ax = plotpress.subplots()
    Cxy, freqs, _ = ax.cohere(x, y, NFFT=512, Fs=Fs, noverlap=256)
    assert np.all(Cxy >= -1e-9) and np.all(Cxy <= 1 + 1e-9)
    assert Cxy.mean() > 0.5                               # strongly coherent


def test_magnitude_and_phase_spectrum_agree_on_length():
    x = _tone(50.0, 1000.0, 2000)
    fig, ax = plotpress.subplots()
    mag, f1, _ = ax.magnitude_spectrum(x, Fs=1000.0)
    ph, f2, _ = ax.phase_spectrum(x, Fs=1000.0)
    ang, f3, _ = ax.angle_spectrum(x, Fs=1000.0)
    assert mag.shape == ph.shape == ang.shape == f1.shape
    np.testing.assert_array_equal(f1, f2)
    assert np.all(np.abs(ang) <= np.pi + 1e-9)           # wrapped
    assert mag[np.argmax(mag)] == mag.max()


def test_magnitude_spectrum_db_scale_is_log():
    # The returned spectrum is linear either way (as in matplotlib); scale="dB"
    # only changes what is *plotted*, so assert on the line's y-data.
    x = _tone(50.0, 1000.0, 2000)
    fig, ax = plotpress.subplots()
    lin, _, line_lin = ax.magnitude_spectrum(x, Fs=1000.0)
    fig2, ax2 = plotpress.subplots()
    db, _, line_db = ax2.magnitude_spectrum(x, Fs=1000.0, scale="dB")
    np.testing.assert_allclose(db, lin, rtol=1e-6)                 # both linear
    np.testing.assert_allclose(line_lin.y, lin, rtol=1e-6)
    np.testing.assert_allclose(line_db.y, 20.0 * np.log10(lin), rtol=1e-6)


def test_acorr_peaks_at_zero_lag_and_is_normed():
    rng = np.random.default_rng(2)
    x = rng.standard_normal(500)
    fig, ax = plotpress.subplots()
    lags, c, lines, markers = ax.acorr(x, maxlags=20)
    assert np.array_equal(lags, np.arange(-20, 21))
    assert lags[np.argmax(c)] == 0
    assert c[np.argmax(c)] == pytest.approx(1.0)          # normed autocorr
    assert markers in ax.artists


def test_xcorr_symmetry_of_lag_axis():
    rng = np.random.default_rng(3)
    x = rng.standard_normal(300)
    y = rng.standard_normal(300)
    fig, ax = plotpress.subplots()
    lags, c, _, _ = ax.xcorr(x, y, maxlags=15)
    assert lags[0] == -15 and lags[-1] == 15
    assert c.size == 31


def test_spectral_methods_render_in_both_backends():
    pytest.importorskip("PIL")
    from plotpress.raster import figure_to_image

    x = _tone(80.0, 1000.0, 4096)
    fig, axes = plotpress.subplots(2, 2)
    axes[0, 0].psd(x, Fs=1000.0)
    axes[0, 1].specgram(x, Fs=1000.0)
    axes[1, 0].magnitude_spectrum(x, Fs=1000.0)
    axes[1, 1].acorr(x, maxlags=25)
    assert fig.to_svg().startswith("<?xml") or "<svg" in fig.to_svg()
    figure_to_image(fig, scale=1)                         # raster must not raise
