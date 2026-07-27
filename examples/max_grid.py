"""Grid of signals: title each plot, find its maximum, mark it with a vline.

Every subplot:
  * plots a curve (a mixture of Gaussian bumps plus mild noise),
  * finds the global maximum of the data,
  * marks that point with a marker and a vertical line (``axvline``),
  * has a title, visible x/y ticks with values, and a legend giving the peak.

Run: python examples/max_grid.py
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress

NROWS, NCOLS = 5, 5          # 25 plots; raise for a larger grid
N_SAMPLES = 300


def make_signal(rng, t):
    """A smooth multi-bump curve with a well-defined global maximum."""
    y = np.zeros_like(t)
    for _ in range(int(rng.integers(1, 4))):
        mu = rng.uniform(0.1, 0.9)
        sigma = rng.uniform(0.03, 0.12)
        amp = rng.uniform(0.5, 1.5)
        y += amp * np.exp(-((t - mu) ** 2) / (2 * sigma ** 2))
    y += rng.normal(0, 0.02, t.size)
    return y


def build():
    rng = np.random.default_rng(11)
    t = np.linspace(0.0, 1.0, N_SAMPLES)

    fig, axes = plotpress.subplots(NROWS, NCOLS, figsize=(4.6 * NCOLS, 3.6 * NROWS))
    for k, ax in enumerate(axes.ravel()):
        y = make_signal(rng, t)

        i_max = int(np.argmax(y))
        x_max, y_max = t[i_max], y[i_max]

        ax.plot(t, y, color="#4c72b0", linewidth=1.5)
        ax.axvline(x_max, color="#c44e52", linewidth=1.5, linestyle="--",
                   label=f"max: y={y_max:.2f} @ x={x_max:.2f}")
        ax.scatter([x_max], [y_max], s=9, color="#c44e52")

        ax.set_title(f"channel {k:02d}")
        ax.set_xlabel("time (s)")
        ax.set_ylabel("amplitude")
        ax.legend()
    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "max_grid.svg")

    t0 = time.perf_counter()
    fig = build()
    svg = fig.to_svg()
    dt = time.perf_counter() - t0

    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)

    # Interactive HTML: wheel-zoom, drag-pan, and click a legend entry to
    # toggle that plot's max line.
    html_out = os.path.join(here, "max_grid.html")
    fig.save(html_out, interactive=True)

    print(f"plots:     {NROWS * NCOLS}")
    print(f"build+svg: {dt * 1e3:.1f} ms")
    print(f"svg size:  {os.path.getsize(out) / 1024:.1f} KiB")
    print(f"wrote {out}")
    print(f"wrote {html_out}")
