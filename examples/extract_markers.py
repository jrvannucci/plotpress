"""Extract marker values from the figure UI back into Python.

Blocking point-picking session:
  1. Build plots.
  2. fig.show(wait_for_extract=True) opens the window and BLOCKS the kernel.
  3. Click "Point Pick", click points to drop markers (arrow keys to fine-tune,
     right-click to delete).
  4. Click "Extract" -- the markers are sent to the kernel AND the window closes,
     so the call returns the list of marker dicts for you to use.

Run: python examples/extract_markers.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    rng = np.random.default_rng(4)
    fig, axes = plotpress.subplots(1, 2, figsize=(11, 4.5))

    t = np.linspace(0, 4 * np.pi, 400)
    axes[0].plot(t, np.sin(t), label="sin")
    axes[0].set_title("line"); axes[0].set_xlabel("t"); axes[0].set_ylabel("y")
    axes[0].legend()

    x = rng.uniform(0, 10, 200)
    y = rng.uniform(0, 10, 200)
    axes[1].scatter(x, y, c=np.hypot(x - 5, y - 5), cmap="plasma", s=14,
                    values={"dist": np.hypot(x - 5, y - 5)})
    axes[1].set_title("scatter"); axes[1].set_xlabel("x"); axes[1].set_ylabel("y")
    return fig


if __name__ == "__main__":
    fig = build()
    # Kernel blocks here until the user clicks "Extract" in the window.
    markers = fig.show(wait_for_extract=True)
    print(f"\nExtracted {len(markers or [])} marker(s):")
    for m in (markers or []):
        print("  ", m)
    # `markers` is now a normal Python list you can use for the rest of the run.
