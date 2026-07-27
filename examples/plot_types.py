"""plotpress's take on matplotlib's canonical "Plot types" reference grid.

Recreates the core matplotlib plot-type gallery with plotpress: line, scatter, bar,
barh, hist, step, fill_between, stem, errorbar, imshow, pcolormesh, and pie.

Run: python examples/plot_types.py   (writes plot_types.svg + .html)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotpress


def build():
    rng = np.random.default_rng(0)
    fig, axes = plotpress.subplots(4, 3, figsize=(13, 15))

    # 1. plot
    ax = axes[0, 0]
    x = np.linspace(0, 2 * np.pi, 200)
    ax.plot(x, np.sin(x)); ax.plot(x, np.cos(x), linestyle="--")
    ax.set_title("plot")

    # 2. scatter
    ax = axes[0, 1]
    ax.scatter(rng.normal(size=150), rng.normal(size=150),
               c=rng.uniform(size=150), cmap="viridis", s=12, alpha=0.8)
    ax.set_title("scatter")

    # 3. bar
    ax = axes[0, 2]
    ax.bar(np.arange(5), rng.integers(2, 10, 5), color="#4c72b0")
    ax.set_title("bar")

    # 4. barh
    ax = axes[1, 0]
    ax.barh(np.arange(5), rng.integers(2, 10, 5), color="#dd8452")
    ax.set_title("barh")

    # 5. hist
    ax = axes[1, 1]
    ax.hist(rng.normal(size=1000), bins=20, color="#55a868")
    ax.set_title("hist")

    # 6. step
    ax = axes[1, 2]
    ax.step(np.arange(10), rng.integers(0, 6, 10), where="mid")
    ax.set_title("step")

    # 7. fill_between
    ax = axes[2, 0]
    y = np.sin(x)
    ax.fill_between(x, y - 0.3, y + 0.3, color="#4c72b0", alpha=0.4)
    ax.plot(x, y, color="#4c72b0")
    ax.set_title("fill_between")

    # 8. stem
    ax = axes[2, 1]
    xs = np.linspace(0, 2 * np.pi, 20)
    ax.stem(xs, np.sin(xs))
    ax.set_title("stem")

    # 9. errorbar
    ax = axes[2, 2]
    xe = np.arange(8)
    ax.errorbar(xe, np.sin(xe), yerr=0.2 + 0.1 * rng.uniform(size=8), capsize=3)
    ax.set_title("errorbar")

    # 10. imshow
    ax = axes[3, 0]
    grid = np.add.outer(np.linspace(0, 1, 30), np.linspace(0, 1, 30))
    ax.imshow(np.sin(grid * 6), cmap="plasma")
    ax.set_title("imshow")

    # 11. pcolormesh
    ax = axes[3, 1]
    gx = np.linspace(-3, 3, 120)
    X, Y = np.meshgrid(gx, gx)
    ax.pcolormesh(gx, gx, np.cos(X) * np.cos(Y), cmap="viridis")
    ax.set_title("pcolormesh")

    # 12. pie
    ax = axes[3, 2]
    ax.pie([35, 25, 20, 20], labels=["A", "B", "C", "D"])
    ax.set_title("pie")

    return fig


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    fig = build()
    fig.save(os.path.join(here, "plot_types.svg"))
    fig.save(os.path.join(here, "plot_types.html"), interactive=True)
    print("wrote plot_types.svg and plot_types.html")
