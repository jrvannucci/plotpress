"""
Spy
===
"""
import numpy as np
import simpleplot

rng = np.random.default_rng(1)
A = np.zeros((30, 30))
A[rng.random((30, 30)) > 0.9] = 1.0        # ~10% nonzero
np.fill_diagonal(A, 1.0)

fig, ax = simpleplot.subplots()
ax.spy(A)
ax.set_title("spy (sparsity pattern)")
