"""3-D data shown as a 2-D line plot plus a slider over the extra dimension.

The data is y(x, t): a family of curves indexed by t. ``plot_frames`` draws one
2-D slice; the slider scrubs t and redraws. A single figure-wide slider drives
both panels, so they scrub together (linked).

Open slider_3d.html and drag the slider at the bottom.

Run: python examples/slider_3d.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    x = np.linspace(0, 4 * np.pi, 300)
    t = np.linspace(0, 2 * np.pi, 60)          # the extra (slider) dimension

    # Traveling wave y(x, t) = sin(x - t): shape (n_frames, n_points).
    wave = np.sin(x[None, :] - t[:, None])
    # A gaussian bump whose center sweeps with t.
    centers = 2 * np.pi + 3 * np.sin(t)
    bumps = np.exp(-((x[None, :] - centers[:, None]) ** 2) / 1.5)

    fig, axes = plotpress.subplots(1, 2, figsize=(13, 4.5))

    ax = axes[0]
    ax.plot_frames(x, wave, slider_values=t, slider_label="t", label="sin(x - t)")
    ax.set_title("traveling wave")
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.legend()

    ax = axes[1]
    ax.plot_frames(x, bumps, slider_values=t, slider_label="t",
                   color="#2ca02c", label="bump")
    ax.set_title("moving gaussian (linked)")
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.legend()

    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "slider_3d.html")
    build().save(out, interactive=True)
    print("wrote", out)
