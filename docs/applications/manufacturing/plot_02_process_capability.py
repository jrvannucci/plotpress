"""
Process capability against specification limits
===============================================

The distribution of a measured dimension against the tolerance it has to meet.
Capability indices condense this to a number -- Cp for the spread, Cpk for the
spread and the centring together -- but the number alone hides the two failure
modes that look identical in a summary and completely different here.

The left panel is a capable, centred process. The right is the same spread
shifted halfway to the upper limit: Cp is unchanged, because Cp does not know
where the distribution sits, while Cpk collapses and the parts falling outside
the tolerance are visible as the shaded tail. Drawing the two side by side with
a shared x axis is what makes the distinction concrete.

The specification limits are drawn heavily and the process limits lightly,
because confusing the two is the classic error -- the spec comes from the design
and the process spread comes from the machine, and there is no reason for them
to coincide. The normal fit is drawn over the histogram rather than replacing
it, since the index calculation assumes normality and the reader should be able
to check that assumption against the actual counts.

Out-of-tolerance parts are shaded and counted in parts per million, which is the
unit a supplier quality agreement is written in.
"""
import numpy as np
import polars as pl
import plotpress

rng = np.random.default_rng(66)

LSL, USL = 9.80, 10.20                             # specification limits (mm)
TARGET = 10.00
SIGMA = 0.0455
N = 4000

CASES = [("centred", 10.000, "#1f77b4"), ("shifted 1.5 sigma", 10.068, "#d62728")]

fig, axes = plotpress.subplots(1, 2, figsize=(11.6, 5.2), sharex=True, sharey=True)

grid = np.linspace(9.70, 10.32, 600)

for ax, (name, mu, color) in zip(axes, CASES):
    # One row per inspected part -- the shape a CMM's own measurement log is
    # in, before the histogram and capability indices are computed from it.
    inspected = pl.DataFrame({"diameter": rng.normal(mu, SIGMA, N)})
    parts = inspected["diameter"].to_numpy()
    ax.hist(parts, bins=48, range=(9.70, 10.32), density=True, color=color,
            alpha=0.55, edgecolor="#ffffff", label=f"{N} parts")

    density = (np.exp(-0.5 * ((grid - mu) / SIGMA) ** 2)
               / (SIGMA * np.sqrt(2 * np.pi)))
    ax.plot(grid, density, color="#111111", linewidth=1.6, label="normal fit")

    outside = grid > USL
    ax.fill_between(grid[outside], 0.0, density[outside], color="#d62728",
                    alpha=0.75)
    outside = grid < LSL
    ax.fill_between(grid[outside], 0.0, density[outside], color="#d62728",
                    alpha=0.75)

    cp = (USL - LSL) / (6.0 * SIGMA)
    cpk = min(USL - mu, mu - LSL) / (3.0 * SIGMA)
    ppm = 1e6 * float(((parts > USL) | (parts < LSL)).mean())

    for limit, tag in [(LSL, "LSL"), (USL, "USL")]:
        ax.axvline(limit, color="#000000", linewidth=2.0, linestyle="-")
        # Just above the axis, where neither the legend nor the curve reaches.
        ax.text(limit, 0.35, tag, ha="center", fontsize=9)
    for edge in (mu - 3 * SIGMA, mu + 3 * SIGMA):
        ax.axvline(edge, color=color, linestyle=":", linewidth=1.2)
    ax.axvline(TARGET, color="#888888", linestyle="--", linewidth=1.1)

    ax.set_title(f"{name}:  Cp = {cp:.2f},  Cpk = {cpk:.2f},  {ppm:.0f} ppm out")
    ax.set_xlabel("measured diameter (mm)")
    ax.legend(loc="upper left")

axes[0].set_ylabel("probability density")
axes[0].set_xlim(9.70, 10.32)
axes[0].set_ylim(0.0, 10.2)

fig.suptitle("Same spread, same Cp: only Cpk notices the process moved")
fig.tight_layout()
