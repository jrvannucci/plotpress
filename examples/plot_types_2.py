"""More of matplotlib's "Plot types": statistical, gridded, and vector fields.

Adds boxplot, violinplot, eventplot, quiver, contour, hist2d, and stackplot to
the plotpress gallery. Writes a static .svg and an interactive .html.

Run: python examples/plot_types_2.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    rng = np.random.default_rng(1)
    fig, axes = plotpress.subplots(2, 4, figsize=(17, 8))
    ax = axes.ravel()

    groups = [rng.normal(m, s, 200) for m, s in [(0, 1), (1, 1.5), (-1, 0.8)]]
    ax[0].boxplot(groups); ax[0].set_title("boxplot")

    ax[1].violinplot(groups); ax[1].set_title("violinplot")

    events = [np.sort(rng.uniform(0, 10, n)) for n in (18, 25, 12, 30)]
    ax[2].eventplot(events); ax[2].set_title("eventplot")

    gx = np.linspace(-2, 2, 12)
    X, Y = np.meshgrid(gx, gx)
    U, V = -Y, X
    ax[3].quiver(X, Y, U, V); ax[3].set_title("quiver")

    cx = np.linspace(-3, 3, 60)
    CX, CY = np.meshgrid(cx, cx)
    Z = np.sin(CX) * np.cos(CY)
    ax[4].contour(cx, cx, Z, levels=9); ax[4].set_title("contour")

    ax[5].hist2d(rng.normal(size=4000), rng.normal(size=4000), bins=30)
    ax[5].set_title("hist2d")

    t = np.linspace(0, 10, 60)
    ax[6].stackplot(t, np.abs(np.sin(t)) + 0.3, np.abs(np.cos(t)) + 0.2,
                    0.4 + 0.2 * np.sin(t / 2), labels=["a", "b", "c"])
    ax[6].set_title("stackplot"); ax[6].legend()

    ax[7].set_axis_off()  # spare panel

    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    fig = build()
    fig.save(os.path.join(here, "plot_types_2.svg"))
    fig.save(os.path.join(here, "plot_types_2.html"), interactive=True)
    print("wrote plot_types_2.svg and plot_types_2.html")
