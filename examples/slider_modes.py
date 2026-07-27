"""Shared vs independent (connectable) sliders.

Every panel here uses ``shared=False``, so each gets its OWN slider docked under
its axes. Panels 0 and 1 share the connection index ``t`` -- each shows a "t"
badge and a checkbox; tick both to link them so they scrub together. Panel 2 has
its own dimension ``z`` (no one to connect to, so no checkbox). Docked sliders
follow their axes when you Span/Zoom.

Run: python examples/slider_modes.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    x = np.linspace(0, 4 * np.pi, 300)
    t = np.linspace(0, 2 * np.pi, 60)   # shared dimension
    z = np.linspace(0, 5, 40)           # independent dimension

    wave = np.sin(x[None, :] - t[:, None])
    bump = np.exp(-((x[None, :] - (2 * np.pi + 3 * np.sin(t[:, None]))) ** 2) / 1.5)
    decay = np.exp(-z[:, None] / 3) * np.sin(x[None, :])   # 40 frames over z

    fig, axes = plotpress.subplots(1, 3, figsize=(18, 4.5))

    # Panels 0 and 1: own docked sliders, sharing connection index "t"
    # (badge + checkbox to link them).
    axes[0].plot_frames(x, wave, slider_values=t, slider_label="t", shared=False,
                        slider_group="t", label="sin(x - t)")
    axes[0].set_title("index t (connectable)")
    axes[0].set_xlabel("x"); axes[0].set_ylabel("y"); axes[0].legend()

    axes[1].plot_frames(x, bump, slider_values=t, slider_label="t", shared=False,
                        slider_group="t", color="#2ca02c", label="bump")
    axes[1].set_title("index t (connectable)")
    axes[1].set_xlabel("x"); axes[1].set_ylabel("y"); axes[1].legend()

    # Panel 2: its own dimension z (nothing to connect to).
    axes[2].plot_frames(x, decay, slider_values=z, slider_label="z", shared=False,
                        color="#d62728", label="e^(-z/3) sin(x)")
    axes[2].set_title("index z (independent)")
    axes[2].set_xlabel("x"); axes[2].set_ylabel("y"); axes[2].legend()

    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "slider_modes.html")
    build().save(out, interactive=True)
    print("wrote", out)
