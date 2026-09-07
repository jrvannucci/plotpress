"""
More categorical axes and declarative tick formats
=====================================================

Rounding out the datetime/categorical/declarative-tick feature set: a
categorical *y*-axis (the earlier example only showed x), declaring
categories up front with ``set_xticks`` before any data is plotted, a
survey with datetime x error bars, and two more formatter specs
(``"percent"`` and a raw ``%``-style string).
"""
import numpy as np
import plotpress

fig, axes = plotpress.subplots(2, 2, figsize=(10.0, 7.5))

# -- Categorical y-axis: barh positions its bars the same way bar() does ----
ax = axes[0, 0]
ax.barh(["Rust", "Go", "Python", "C++"], [18, 22, 41, 19], color="#1f77b4")
ax.set_title("Categorical y-axis (barh)")
ax.set_xlabel("survey share (%)")

# -- Declaring categories before any data is plotted -------------------------
ax = axes[0, 1]
ax.set_xticks(["Cold", "Cool", "Mild", "Warm", "Hot"])   # categories exist now
ax.plot([0, 2, 4], [12, 18, 27], marker="o", color="#2ca02c")
ax.set_xlim("Cold", "Hot")
ax.set_title("set_xticks() declares categories up front")

# -- A survey with datetime x and y error bars -------------------------------
ax = axes[1, 0]
dates = np.array(["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01"],
                 dtype="datetime64[D]")
readings = [21.3, 24.1, 29.8, 23.6]
uncertainty = [1.2, 0.8, 1.5, 1.0]
ax.errorbar(dates, readings, yerr=uncertainty, marker="s", color="#d62728")
ax.set_title("errorbar() with a datetime x axis")
ax.set_ylabel("temperature (C)")

# -- percent / raw %-string formatters ---------------------------------------
ax = axes[1, 1]
ax.plot([0, 1, 2, 3], [0.12, 0.31, 0.58, 0.74], marker="o", color="#9467bd")
ax.set_yformat("percent")          # 12%, 31%, 58%, 74%
ax.set_xformat("Week %.0f")        # a raw %-style string works too
ax.set_title("percent / raw %-string formatters")

fig.suptitle("More categorical axes and declarative tick formats")
fig.tight_layout()
