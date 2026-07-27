"""Standalone native window demo -- no browser involved.

``fig.show()`` opens a native OS window (via pywebview / WebView2 on Windows)
hosting the same interactive SVG: the corner toolbar (Span / Zoom / Point Pick /
Reset) all work here too. Close the window to end the program.

Run: python examples/show_window.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    rng = np.random.default_rng(3)
    fig, axes = plotpress.subplots(2, 2, figsize=(9, 6))
    x = np.linspace(0, 4 * np.pi, 400)

    ax = axes[0, 0]
    ax.plot(x, np.sin(x), label="sin")
    ax.plot(x, np.cos(x), label="cos", linestyle="--")
    ax.set_title("waves"); ax.set_xlabel("x"); ax.set_ylabel("amp")
    ax.grid(True); ax.legend()

    ax = axes[0, 1]
    xs = rng.normal(size=400)
    ys = xs * 0.6 + rng.normal(size=400)
    ax.scatter(xs, ys, c=xs * xs + ys * ys, cmap="plasma", s=9, alpha=0.85)
    ax.set_title("scatter"); ax.set_xlabel("x"); ax.set_ylabel("y")

    ax = axes[1, 0]
    t = np.linspace(0, 1, 200)
    y = np.sin(2 * np.pi * 5 * t) + rng.normal(0, 0.15, t.size)
    k = int(np.argmax(y))
    ax.plot(t, y, label="signal")
    ax.axvline(t[k], linestyle="--", color="#d62728", label=f"max @ {t[k]:.2f}")
    ax.set_title("peak"); ax.set_xlabel("time"); ax.set_ylabel("v"); ax.legend()

    ax = axes[1, 1]
    gx = np.linspace(-3, 3, 200)
    gy = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(gx, gy)
    Z = np.sin(X**2 + Y**2) / (1 + X**2 + Y**2)
    m = ax.pcolormesh(gx, gy, Z, cmap="viridis")
    ax.set_title("pcolormesh"); ax.set_xlabel("x"); ax.set_ylabel("y")
    fig.colorbar(m, ax=ax)

    return fig


if __name__ == "__main__":
    build().show()  # blocks until the native window is closed
