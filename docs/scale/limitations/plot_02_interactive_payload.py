"""
Interactivity costs more than the figure does
=============================================

An interactive figure is self-contained: the toolbar's JavaScript is inlined and
so is the data it needs to answer a point-pick, because the file must work from
``file://`` and under a strict CSP with no outside requests. That is a deliberate
constraint and it has a price, which this figure measures: for a mesh the
inlined ``z`` grid dwarfs the drawing, and the interactive file is several times
the static one at every setting.

There is no way to have the first property without the second. Fetching the pick
data on demand would make the file small and would also make it stop working
from a filesystem, inside a notebook, or behind a CSP -- which are the cases the
format exists for.

Full precision is almost never wanted. A readout of ``-0.4271639823974515`` is
seventeen significant figures of a quantity measured to three, and every one of
those digits is bytes in the file. ``pick_precision`` rounds the inlined values,
and the saving is close to linear in the digits dropped.

The figure measures it: the same mesh serialized at a range of precisions,
against the static SVG as the floor. Two things are worth reading off it. The
curve is close to linear rather than proportional -- the toolbar script and the
SVG itself are a fixed cost that no precision setting touches -- so the saving
from dropping two digits is real but bounded, and the annotation quotes the
measured figure rather than a hopeful one. And the gap to the floor is large:
most of an interactive file is pick data, which is worth knowing before
switching interactivity on across a whole gallery.
"""
import time

import numpy as np
import plotpress

rng = np.random.default_rng(5)

N = 220
g = np.linspace(-3.0, 3.0, N)
X, Y = np.meshgrid(g, g)
Z = np.sin(X * 1.7) * np.cos(Y * 1.3) + 0.3 * rng.random((N, N))


def payload(precision):
    """KiB of self-contained interactive HTML at this pick precision."""
    f, a = plotpress.subplots(figsize=(6.0, 5.0))
    a.pcolormesh(g, g, Z, cmap="viridis")
    html = f.to_html(interactive=True, pick_precision=precision)
    return len(html.encode("utf-8")) / 1024.0


precisions = [2, 3, 4, 5, 6, 8, 10]
sizes = [payload(p) for p in precisions]

def static_floor():
    """KiB of plain SVG -- everything above this is the price of interaction.

    Built inside a function so its Figure stays local: the gallery scraper
    collects every Figure left in an example's globals, and a scratch one would
    be published as a second, meaningless image on the page.
    """
    f, a = plotpress.subplots(figsize=(6.0, 5.0))
    a.pcolormesh(g, g, Z, cmap="viridis")
    return len(f.to_svg().encode("utf-8")) / 1024.0


static_kib = static_floor()

fig, ax = plotpress.subplots(figsize=(9.0, 5.4))
ax.plot(precisions, sizes, color="#1f77b4", linewidth=2.0,
        label="interactive HTML")
ax.scatter(precisions, sizes, s=7.0, color="#1f77b4")
ax.axhline(static_kib, color="#2ca02c", linestyle="--", linewidth=1.6,
           label=f"static SVG floor ({static_kib:.0f} KiB)")

DEFAULT = 6
default_kib = sizes[precisions.index(DEFAULT)]
ax.annotate(f"default: {default_kib:.0f} KiB",
            xy=(DEFAULT, default_kib), xytext=(7.0, default_kib * 1.12),
            arrowprops={"color": "#333333"}, fontsize=9)
four_kib = sizes[precisions.index(4)]
ax.annotate(f"precision 4: {four_kib:.0f} KiB\n"
            f"({100 * (1 - four_kib / default_kib):.0f}% smaller)",
            xy=(4, four_kib), xytext=(2.2, four_kib * 0.72),
            arrowprops={"color": "#d62728"}, color="#d62728", fontsize=9)

ax.set_xlabel("pick_precision (significant digits inlined per value)")
ax.set_ylabel("file size (KiB)")
ax.set_ylim(0.0, None)
ax.set_title(f"{N}x{N} mesh: what the point-pick readout costs to carry")
ax.legend(loc="upper left")
ax.grid(True)
fig.tight_layout()
