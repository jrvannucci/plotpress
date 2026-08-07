"""
Bouguer gravity anomaly
=======================

A Bouguer anomaly map: the residual gravitational acceleration once latitude,
elevation and terrain have been removed, so what remains reflects density
contrasts in the subsurface. Positive lobes sit over dense intrusions, negative
ones over sedimentary basins and salt.

Anomalies are quoted in milligal -- roughly a millionth of surface gravity --
and they straddle zero, where zero means "nothing anomalous down there". A
diverging map with symmetric limits keeps that reading honest: an autoscaled
range would tint barren ground the colour of a weak anomaly.

Contours over the mesh give the interpreter something to trace and measure
gradients against, which is how basin edges are picked.
"""
import numpy as np
import polars as pl
import plotpress

east = np.linspace(0.0, 120.0, 340)      # km
north = np.linspace(0.0, 90.0, 300)
E, N = np.meshgrid(east, north)


def body(e0, n0, radius, peak_mgal):
    """Anomaly of a buried sphere: the classic textbook forward model.

    Normalized so ``peak_mgal`` is the amplitude directly over the body, which
    keeps the map in the tens of milligal a real Bouguer survey produces.
    """
    r2 = (E - e0) ** 2 + (N - n0) ** 2
    return peak_mgal * radius ** 3 / (r2 + radius ** 2) ** 1.5


anomaly = (body(34.0, 58.0, 14.0, 55.0)          # dense mafic intrusion
           + body(78.0, 34.0, 18.0, -42.0)       # sedimentary basin
           + body(96.0, 68.0, 10.0, 26.0)
           + body(20.0, 22.0, 12.0, -20.0))      # salt structure
anomaly += 0.02 * (E - 60.0)                      # broad regional gradient

# One row per surveyed (easting, northing) station -- sorted before the
# reshape below so the pivot back to a grid is correct regardless of order.
survey = pl.DataFrame({
    "east_km": E.ravel(), "north_km": N.ravel(), "anomaly_mgal": anomaly.ravel(),
}).sort(["north_km", "east_km"])

east_axis = survey["east_km"].unique().sort().to_numpy()
north_axis = survey["north_km"].unique().sort().to_numpy()
anomaly = survey["anomaly_mgal"].to_numpy().reshape(north_axis.size, east_axis.size)
lim = float(survey["anomaly_mgal"].abs().max())

fig, ax = plotpress.subplots(figsize=(8.0, 5.6))
mesh = ax.pcolormesh(east_axis, north_axis, anomaly, cmap="coolwarm", vmin=-lim, vmax=lim)
ax.contour(east_axis, north_axis, anomaly, levels=9, colors="#333333")
bar = fig.colorbar(mesh, ax=ax)
bar.set_title("mGal")
ax.set_aspect("equal")
ax.set_xlabel("easting (km)")
ax.set_ylabel("northing (km)")
ax.set_title("Bouguer anomaly with contours at 9 levels")
fig.tight_layout()
