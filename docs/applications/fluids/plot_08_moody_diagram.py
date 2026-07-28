"""
Moody diagram
=============

The chart every pipe in every plant has been sized from: friction factor against
Reynolds number, one curve per relative roughness. It is log-log because both
axes span orders of magnitude and because the laminar branch is a power law,
``f = 64/Re``, which only reads as a straight line there.

The diagram's real content is the *transition* between regimes, and drawing it
honestly requires admitting where the data stops. Between roughly Re = 2300 and
4000 the flow is neither reliably laminar nor reliably turbulent, no correlation
applies, and the curves are simply not drawn -- the shaded band with no lines in
it is the correct representation of a region where the answer is unknown.
Interpolating across it, which is easy to do accidentally by plotting one
continuous array, would invent a friction factor precisely where an engineer
most needs to be warned off.

At high Reynolds number each rough-pipe curve flattens: friction stops depending
on Reynolds number and depends only on roughness. That "fully rough" asymptote
is why the curves are labelled at their right-hand ends with the roughness
rather than in a legend -- the label sits on the part of the curve it describes,
and a nine-entry legend would be read by colour-matching instead.
"""
import numpy as np
import plotpress

LAMINAR = (500.0, 2300.0)
TRANSITION = (2300.0, 4000.0)
ROUGHNESS = [5e-2, 2e-2, 1e-2, 4e-3, 1e-3, 2e-4, 5e-5, 1e-5, 0.0]


def colebrook(Re, rel_rough, iterations=40):
    """Solve the implicit Colebrook-White equation by fixed-point iteration."""
    f = 0.02 * np.ones_like(Re)
    for _ in range(iterations):
        rhs = -2.0 * np.log10(rel_rough / 3.7 + 2.51 / (Re * np.sqrt(f)))
        f = 1.0 / rhs ** 2
    return f


re_lam = np.logspace(np.log10(LAMINAR[0]), np.log10(LAMINAR[1]), 60)
re_turb = np.logspace(np.log10(TRANSITION[1]), 8.0, 400)

lut = plotpress.get_cmap("viridis")
colors = ["#%02x%02x%02x" % tuple(lut[i])
          for i in np.linspace(15, 230, len(ROUGHNESS)).astype(int)]

fig, ax = plotpress.subplots(figsize=(9.6, 6.2))

ax.plot(re_lam, 64.0 / re_lam, color="#111111", linewidth=2.0, label="laminar, 64/Re")
ax.axvspan(*TRANSITION, color="#bbbbbb", alpha=0.55)
ax.text(2950.0, 0.058, "critical\nzone", ha="center", fontsize=9, color="#444444")

Y_LO, Y_HI = 0.007, 0.14
for eps, color in zip(ROUGHNESS, colors):
    f = colebrook(re_turb, eps)
    ax.plot(re_turb, f, color=color, linewidth=1.4)
    # Label each curve on itself, at the last Reynolds number where it is still
    # inside the axes. The smooth-pipe curve keeps falling off the bottom, and
    # a label pinned to the right-hand edge would be drawn below the axis.
    visible = np.nonzero((f > Y_LO) & (re_turb < 1.2e8))[0]
    label = "smooth" if eps == 0.0 else f"{eps:g}"
    ax.text(re_turb[visible[-1]] * 1.1, f[visible[-1]], label, fontsize=8,
            color=color, va="baseline")

ax.text(2.2e7, 0.0115, "relative roughness e/D", fontsize=9, color="#333333",
        ha="center")

ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(500.0, 4e8)
ax.set_ylim(Y_LO, Y_HI)
ax.set_xlabel("Reynolds number  Re = rho V D / mu")
ax.set_ylabel("Darcy friction factor f")
ax.set_title("Moody diagram: the critical zone is left blank because it is unknown")
ax.legend(loc="upper right")
ax.grid(True)
fig.tight_layout()
