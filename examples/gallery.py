"""plotpress gallery: line, scatter, and pcolormesh -- no global state anywhere.

Run: python examples/gallery.py   (writes .svg files next to this script)
"""

import numpy as np

import plotpress


def line_example():
    fig, ax = plotpress.subplots(figsize=(6.4, 4.0))
    x = np.linspace(0, 4 * np.pi, 400)
    ax.plot(x, np.sin(x), label="sin")
    ax.plot(x, np.cos(x), label="cos", linestyle="--")
    ax.plot(x, np.sin(x) * np.exp(-x / 10), label="damped")
    ax.set_title("Line plot")
    ax.set_xlabel("x")
    ax.set_ylabel("amplitude")
    ax.grid(True)
    ax.legend()
    return fig


def scatter_example():
    rng = np.random.default_rng(0)
    fig, ax = plotpress.subplots(figsize=(6.4, 4.0))
    x = rng.normal(size=300)
    y = x * 0.5 + rng.normal(size=300)
    ax.scatter(x, y, c=x * x + y * y, cmap="plasma", s=8, alpha=0.8)
    ax.set_title("Scatter (color-mapped)")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    return fig


def pcolormesh_example():
    fig, ax = plotpress.subplots(figsize=(6.0, 4.5))
    x = np.linspace(-3, 3, 200)
    y = np.linspace(-3, 3, 200)
    X, Y = np.meshgrid(x, y)
    Z = np.sin(X**2 + Y**2) / (1 + X**2 + Y**2)
    mesh = ax.pcolormesh(x, y, Z, cmap="viridis")
    ax.set_title("pcolormesh")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    fig.colorbar(mesh, ax=ax)
    return fig


def subplots_example():
    fig, axes = plotpress.subplots(2, 2, figsize=(8, 6))
    x = np.linspace(0, 10, 200)
    axes[0, 0].plot(x, np.sin(x))
    axes[0, 0].set_title("sin")
    axes[0, 1].plot(x, np.sqrt(x), color="#d62728")
    axes[0, 1].set_title("sqrt")
    axes[1, 0].scatter(x, np.sin(x) + 0.1 * x, s=5)
    axes[1, 0].set_title("scatter")
    Z = np.outer(np.sin(x), np.cos(x))
    axes[1, 1].pcolormesh(Z, cmap="plasma")
    axes[1, 1].set_title("mesh")
    return fig


if __name__ == "__main__":
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    outputs = {
        "line.svg": line_example(),
        "scatter.svg": scatter_example(),
        "pcolormesh.svg": pcolormesh_example(),
        "subplots.svg": subplots_example(),
    }
    for name, fig in outputs.items():
        fig.save(os.path.join(here, name))
        print("wrote", name)
    # Interactive HTML (pan/zoom + legend toggle) from the line example.
    line_example().save(os.path.join(here, "line_interactive.html"), interactive=True)
    print("wrote line_interactive.html")
