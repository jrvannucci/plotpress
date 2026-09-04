"""Spectral estimators for the signal-processing plot methods.

Pure-NumPy Welch-averaged power / cross spectral density, coherence, single-shot
spectra, and lagged correlation. The conventions (segmenting, Hann window,
mean detrend, one-sided scaling) follow matplotlib's ``mlab`` closely enough
that the resulting plots line up -- without pulling in SciPy.
"""

from __future__ import annotations

import numpy as np


def _as_segments(x, NFFT, noverlap):
    """Split ``x`` into overlapping length-``NFFT`` rows, zero-padded if short."""
    x = np.asarray(x, float).ravel()
    if x.size < NFFT:
        x = np.concatenate([x, np.zeros(NFFT - x.size)])
    step = NFFT - noverlap
    if step <= 0:
        raise ValueError("noverlap must be less than NFFT")
    n_seg = 1 + (x.size - NFFT) // step
    idx = np.arange(NFFT)[None, :] + step * np.arange(n_seg)[:, None]
    return x[idx], step  # (n_seg, NFFT)


def _windowed_fft(x, NFFT, Fs, noverlap, window, detrend):
    """Detrended, windowed rFFT of every segment. Returns (Z, freqs, win, step)."""
    segs, step = _as_segments(x, NFFT, noverlap)
    if detrend:
        segs = segs - segs.mean(axis=1, keepdims=True)
    win = window(NFFT) if callable(window) else np.asarray(window, float)
    Z = np.fft.rfft(segs * win, n=NFFT, axis=1)
    freqs = np.fft.rfftfreq(NFFT, d=1.0 / Fs)
    return Z, freqs, win, step


def _onesided_double(P, NFFT):
    """Double the non-DC / non-Nyquist bins for a one-sided spectrum (in place)."""
    if NFFT % 2 == 0:
        P[..., 1:-1] *= 2.0
    else:
        P[..., 1:] *= 2.0
    return P


def psd(x, NFFT, Fs, noverlap, window, detrend):
    """One-sided power spectral density by Welch averaging."""
    Z, freqs, win, _ = _windowed_fft(x, NFFT, Fs, noverlap, window, detrend)
    scale = 1.0 / (Fs * (win ** 2).sum())
    Pxx = _onesided_double(np.abs(Z) ** 2 * scale, NFFT).mean(axis=0)
    return Pxx, freqs


def csd(x, y, NFFT, Fs, noverlap, window, detrend):
    """One-sided cross spectral density ``Pxy`` (complex)."""
    Zx, freqs, win, _ = _windowed_fft(x, NFFT, Fs, noverlap, window, detrend)
    Zy, _, _, _ = _windowed_fft(y, NFFT, Fs, noverlap, window, detrend)
    scale = 1.0 / (Fs * (win ** 2).sum())
    Pxy = _onesided_double(Zx * np.conj(Zy) * scale, NFFT).mean(axis=0)
    return Pxy, freqs


def cohere(x, y, NFFT, Fs, noverlap, window, detrend):
    """Magnitude-squared coherence ``|Pxy|^2 / (Pxx Pyy)`` in ``[0, 1]``.

    Coherence is only meaningful when the estimate averages several segments;
    a single segment makes it identically 1 (as in matplotlib).
    """
    Zx, freqs, win, _ = _windowed_fft(x, NFFT, Fs, noverlap, window, detrend)
    Zy, _, _, _ = _windowed_fft(y, NFFT, Fs, noverlap, window, detrend)
    scale = 1.0 / (Fs * (win ** 2).sum())
    Pxx = _onesided_double(np.abs(Zx) ** 2 * scale, NFFT).mean(axis=0)
    Pyy = _onesided_double(np.abs(Zy) ** 2 * scale, NFFT).mean(axis=0)
    Pxy = _onesided_double(Zx * np.conj(Zy) * scale, NFFT).mean(axis=0)
    # An empty/all-zero x and y (zero-padded by _as_segments rather than
    # rejected -- a real segment length is still needed either way) makes
    # Pxx == Pyy == 0 everywhere: 0/0, mathematically undefined coherence,
    # not a bug -- silence the resulting "invalid value" noise rather than
    # rejecting a case NFFT-segmenting already treats as legitimate.
    with np.errstate(invalid="ignore"):
        Cxy = np.abs(Pxy) ** 2 / (Pxx * Pyy)
    return Cxy, freqs


def specgram(x, NFFT, Fs, noverlap, window, detrend):
    """Spectrogram: one-sided power per segment. Returns (P, freqs, t).

    ``P`` has shape ``(n_freqs, n_segments)`` -- ready for ``imshow``.
    """
    Z, freqs, win, step = _windowed_fft(x, NFFT, Fs, noverlap, window, detrend)
    scale = 1.0 / (Fs * (win ** 2).sum())
    P = _onesided_double(np.abs(Z) ** 2 * scale, NFFT)      # (n_seg, n_freq)
    t = (np.arange(P.shape[0]) * step + NFFT / 2.0) / Fs
    return P.T, freqs, t


def _single_spectrum(x, Fs, window, detrend):
    """Windowed rFFT of the whole signal (no segmenting)."""
    x = np.asarray(x, float).ravel()
    if x.size == 0:
        # x.mean() on an empty array below leaks a raw "Mean of empty
        # slice" RuntimeWarning before np.fft eventually raises its own
        # clear error a few lines further on -- raise that same "nothing
        # to do" error here instead, without the noise in front of it.
        raise ValueError("magnitude_spectrum()/angle_spectrum()/phase_spectrum(): x must not be empty")
    if detrend:
        x = x - x.mean()
    n = x.size
    win = window(n) if callable(window) else np.asarray(window, float)
    Z = np.fft.rfft(x * win)
    freqs = np.fft.rfftfreq(n, d=1.0 / Fs)
    return Z, freqs, win, n


def magnitude_spectrum(x, Fs, window, detrend):
    """One-sided magnitude spectrum ``|X(f)|``."""
    Z, freqs, win, n = _single_spectrum(x, Fs, window, detrend)
    mag = _onesided_double(np.abs(Z) / win.sum(), n)
    return mag, freqs


def angle_spectrum(x, Fs, window, detrend):
    """Wrapped phase spectrum in radians (``-pi..pi``)."""
    Z, freqs, _, _ = _single_spectrum(x, Fs, window, detrend)
    return np.angle(Z), freqs


def phase_spectrum(x, Fs, window, detrend):
    """Unwrapped phase spectrum in radians."""
    Z, freqs, _, _ = _single_spectrum(x, Fs, window, detrend)
    return np.unwrap(np.angle(Z)), freqs


def correlation(x, y, detrend, normed, maxlags):
    """Lagged cross-correlation. Returns ``(lags, c)`` over ``+-maxlags``."""
    x = np.asarray(x, float).ravel()
    y = np.asarray(y, float).ravel()
    n = x.size
    if y.size != n:
        raise ValueError("x and y must be the same length")
    if detrend:
        x = x - x.mean()
        y = y - y.mean()
    c = np.correlate(x, y, mode="full")
    if normed:
        c = c / (np.sqrt(np.dot(x, x) * np.dot(y, y)) or 1.0)
    if maxlags is None:
        maxlags = n - 1
    if not 0 <= maxlags < n:
        raise ValueError("maxlags must be in 0..len(x)-1")
    lags = np.arange(-maxlags, maxlags + 1)
    c = c[n - 1 - maxlags:n + maxlags]
    return lags, c
