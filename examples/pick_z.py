"""Point picking with values beyond x/y (z and extra dimensions).

Generates an interactive HTML where Point Pick reports:
  * a pcolormesh cell's z value,
  * a scatter point's c (color) value plus an extra 'temp' dimension,
  * a plain line -- only x and y, since extra dimensions are opt-in.

Open pick_z.html, click the "Point Pick" toolbar button, then click points.

Run: python examples/pick_z.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    rng = np.random.default_rng(11)
    fig, axes = plotpress.subplots(1, 3, figsize=(16, 4.5))

    # 1) pcolormesh -> pick reports z (the field value at the clicked cell).
    ax = axes[0]
    gx = np.linspace(-3, 3, 120)
    gy = np.linspace(-3, 3, 120)
    X, Y = np.meshgrid(gx, gy)
    Z = np.exp(-(X**2 + Y**2) / 4) * np.cos(3 * X)
    m = ax.pcolormesh(gx, gy, Z, cmap="viridis")
    ax.set_title("pcolormesh (pick z)")
    ax.set_xlabel("x"); ax.set_ylabel("y")
    fig.colorbar(m, ax=ax)

    # 2) scatter with a color dimension c and an extra 'temp' dimension.
    ax = axes[1]
    n = 250
    x = rng.uniform(0, 10, n)
    y = rng.uniform(0, 10, n)
    z = np.sin(x) + np.cos(y)          # color dimension
    temp = 20 + 5 * rng.normal(size=n)  # a 4th value per point
    ax.scatter(x, y, c=z, cmap="plasma", s=14, values={"temp": temp})
    ax.set_title("scatter (pick c + temp)")
    ax.set_xlabel("x"); ax.set_ylabel("y")

    # 3) plain line: no extra dimensions, so picking reports only x and y.
    ax = axes[2]
    t = np.linspace(0, 2 * np.pi, 60)
    ax.plot(t, np.sin(t), label="wave")
    ax.set_title("line (x, y only)")
    ax.set_xlabel("t"); ax.set_ylabel("y"); ax.legend()

    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "pick_z.html")
    build().save(out, interactive=True)
    print("wrote", out)
