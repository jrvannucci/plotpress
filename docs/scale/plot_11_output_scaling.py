"""
How output size scales with the data
====================================

The measurement that decides whether a plotting library can be put behind a web
request: how does the *file* grow as the data does?

Three plot types are serialized at sizes spanning four decades and the resulting
SVG measured. On log-log axes a power law is a straight line and its exponent is
the slope, which is the whole reason for these axes -- the question is not how
big any one figure is but which of these curves eventually stops being servable.

The three answers are different, and each follows from a rendering decision made
elsewhere in this gallery:

- **Mesh** grows far more slowly than its cell count. The field becomes one
  embedded PNG, so what the file tracks is how *compressible* the picture is,
  not how many cells went into it. A smooth field -- which is what a sampled
  physical quantity looks like -- costs little to refine. Pure noise is the
  worst case and would grow with a slope near one, because incompressible data
  is incompressible however it is stored, so this curve is the best case for
  meshes and the docstring says so rather than letting the reader assume.
- **Line** is flat above a threshold. Below it every point is written out;
  above it min/max decimation caps the drawn points at roughly two per pixel
  column, and the axes is only so many pixels wide.
- **Scatter** is linear, and honestly so. Every point is an independent mark, so
  every point costs bytes. This is the curve to watch: the batching into one
  path keeps the constant small, but the slope is one and nothing changes that.

A reference slope of one is drawn so the scatter line can be checked against it
rather than eyeballed.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(4)

SIZES = [100, 300, 1_000, 3_000, 10_000, 30_000, 100_000, 300_000]


def svg_kib(build):
    f, a = plotpress.subplots(figsize=(6.4, 4.8))
    build(a)
    return len(f.to_svg().encode("utf-8")) / 1024.0


def line_of(n):
    x = np.linspace(0, 100, n)
    y = np.sin(x) + rng.normal(0, 0.1, n)
    return lambda a: a.plot(x, y)


def scatter_of(n):
    x, y = rng.normal(0, 1, n), rng.normal(0, 1, n)
    return lambda a: a.scatter(x, y, s=3)


def mesh_of(n):
    # A smooth field, not noise: this is what a sampled physical quantity looks
    # like, and it is the case where refining the grid costs the file almost
    # nothing. Noise would sit near slope 1 -- see the docstring.
    side = max(4, int(np.sqrt(n)))
    u = np.linspace(-3.0, 3.0, side)
    xx, yy = np.meshgrid(u, u)
    z = np.sin(xx) * np.cos(yy) + 0.3 * np.exp(-(xx ** 2 + yy ** 2) / 4.0)
    return lambda a: a.pcolormesh(z, cmap="viridis")


SERIES = [("line (decimated)", line_of, "#1f77b4"),
          ("scatter (one path)", scatter_of, "#d62728"),
          ("pcolormesh (one image)", mesh_of, "#2ca02c")]

fig, ax = plotpress.subplots(figsize=(9.2, 6.0))
for name, factory, color in SERIES:
    sizes = [svg_kib(factory(n)) for n in SIZES]
    ax.plot(SIZES, sizes, color=color, linewidth=2.0, label=name)
    ax.scatter(SIZES, sizes, s=6.0, color=color)
    ax.text(SIZES[-1] * 1.15, sizes[-1], f"{sizes[-1]:.0f} KiB", fontsize=8,
            color=color, va="center")

# A slope-1 reference: anything parallel to this grows with the data.
ref_x = np.array([3e3, 3e5], dtype=float)
ref_y = np.array([12.0, 1200.0])
ax.plot(ref_x, ref_y, color="#888888", linestyle="--", linewidth=1.3,
        label="slope 1 (size proportional to N)")

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(80, 1.2e6)
ax.set_xlabel("data points (mesh: cells)")
ax.set_ylabel("SVG size (KiB)")
ax.set_title("Only scatter grows with the data; the others flatten out")
ax.legend(loc="upper left")
ax.grid(True)
fig.tight_layout()
