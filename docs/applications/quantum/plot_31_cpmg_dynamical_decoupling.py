"""
CPMG dynamical decoupling: coherence extension vs number of pulses
=======================================================================

Final-state contrast of a CPMG dynamical-decoupling sequence -- N equally
spaced refocusing pi pulses inserted into an otherwise free-evolution Ramsey
-- swept over the total free-evolution time and N itself, the tune-up that
picks how many refocusing pulses an idling qubit needs against its own noise
environment. Each added pulse narrows the sequence's filter function around
higher frequencies, rejecting more of the slow, ``1/f``-like noise that
limits a bare Ramsey; for that noise spectrum the effective coherence time
grows as a power law in ``N`` rather than saturating,
``T2(N) ~ T2_echo N^p``. The result is a fan, not a single curve: contrast
collapses quickly at low N and survives to far longer times as N increases,
and reading where each row crosses a fixed contrast threshold is how many
pulses a given idle duration actually needs is decided in practice.
"""
import numpy as np
import polars as pl
import plotpress

T2_ECHO = 12.0                 # microseconds, N=1 (Hahn echo) coherence time
POWER = 0.65                    # T2(N) ~ T2_echo * N^POWER, 1/f-noise scaling
STRETCH = 1.4                   # stretched-exponential exponent
N_MAX = 32
rng = np.random.default_rng(919)

time = np.linspace(0.0, 260.0, 320)      # microseconds, total free evolution
pulses = np.arange(1, N_MAX + 1)
T, N = np.meshgrid(time, pulses)

t2_n = T2_ECHO * N ** POWER
contrast = np.exp(-(T / t2_n) ** STRETCH)
contrast += rng.normal(0.0, 0.015, contrast.shape)
contrast = np.clip(contrast, 0.0, 1.0)

# One row per swept (time, pulses) shot -- sorted before the reshape below
# so the pivot back to a grid is correct regardless of row order.
sweep = pl.DataFrame({
    "time_us": T.ravel(),
    "pulses": N.ravel(),
    "contrast": contrast.ravel(),
}).sort(["pulses", "time_us"])

time_axis = sweep["time_us"].unique().sort().to_numpy()
pulses_axis = sweep["pulses"].unique().sort().to_numpy()
contrast = sweep["contrast"].to_numpy().reshape(pulses_axis.size, time_axis.size)

fig, ax = plotpress.subplots(figsize=(7.6, 5.4))
mesh = ax.pcolormesh(time_axis, pulses_axis, contrast, cmap="viridis", vmin=0.0, vmax=1.0)
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("contrast")
ax.set_xlabel("total free-evolution time (us)")
ax.set_ylabel("number of CPMG pulses N")
ax.set_title(f"CPMG coherence extension, T2(N) ~ N^{POWER:.2f}")
fig.tight_layout()
