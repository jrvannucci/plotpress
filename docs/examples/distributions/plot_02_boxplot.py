"""
Box plot
========

``whis`` sets how many IQRs past q1/q3 the whiskers reach before a point
counts as a flier (matplotlib's own default is ``1.5``; wider here so fewer
of this dataset's points are flagged).
"""
import numpy as np
import plotpress

rng = np.random.default_rng(5)
data = [rng.normal(loc, 1.0, 200) for loc in (0, 1, 2, 1.5)]
fig, ax = plotpress.subplots()
ax.boxplot(data, whis=2.5)
ax.set_title("Box plot")
fig.tight_layout()
