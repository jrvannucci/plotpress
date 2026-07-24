"""
Matshow
=======
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(0)
M = rng.standard_normal((12, 12))
M += np.eye(12) * 3                        # a bright diagonal to read the layout

fig, ax = simpleplot.subplots()
im = ax.matshow(M, cmap="RdBu")
ax.set_title("matshow"); fig.colorbar(im, ax=ax)
