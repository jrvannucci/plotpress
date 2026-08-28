Figures and layout
===================

Everything hangs off a :class:`~plotpress.figure.Figure`. There is **no global
state** -- no ``pyplot``, no "current figure/axes", no global ``rcParams``. Two
figures never share mutable state.

Creating figures and axes
-------------------------

``plotpress.subplots(nrows=1, ncols=1, figsize=(6.4, 4.8), style=None, facecolor=None, squeeze=True)``
    Create a figure and a grid of axes; returns ``(fig, axes)`` just like
    ``matplotlib.pyplot.subplots`` -- but touches no globals. ``axes`` is a
    single :class:`~plotpress.axes.Axes`, a 1-D array, or a 2-D array.

    .. code-block:: python

       fig, ax = plotpress.subplots()
       fig, axes = plotpress.subplots(2, 3, figsize=(12, 7))

Methods on the figure:

``fig.add_subplot(nrows=1, ncols=1, index=1)``
    Add one axes at a grid position.

``fig.add_axes(rect)``
    Add an axes at ``rect = (left, bottom, width, height)`` in figure fractions.

``fig.subplots(nrows=1, ncols=1, squeeze=True)``
    Fill the figure with a grid of axes.

Colorbars
---------

``fig.colorbar(mappable, ax, fraction=0.05, pad=0.02)``
    Add a colorbar for a mappable (a ``pcolormesh`` / ``imshow`` / ``hist2d``
    result), stealing space from ``ax``.

    .. code-block:: python

       m = ax.pcolormesh(x, y, Z)
       fig.colorbar(m, ax=ax)

Figure-level legend
-------------------

``fig.legend(ax=None, loc="lower center", ncol=1, title=None, pad=0.01)``
    One legend for the whole figure, drawn from every labelled artist. Labels
    are **de-duplicated**, so a grid whose panels all plot the same series gets
    one entry per series rather than one per panel.

    .. code-block:: python

       fig, axes = plotpress.subplots(2, 3)
       for i, ax in enumerate(axes.ravel()):
           ax.plot(x, signal[i], label="signal")
           ax.plot(x, reference[i], label="reference")
       fig.tight_layout()
       fig.legend(loc="lower center", ncol=2)

    ``loc`` is in **figure** coordinates. The outside placements --
    ``"lower center"``, ``"upper center"``, ``"right"``/``"center right"`` and
    ``"center left"`` -- reserve a band at that edge and shrink the subplot grid
    to fit, so the legend never lands on a plot. Any other placement overlays
    without reserving, the way an axes legend sits inside its own rect.

    ``ax`` restricts which axes contribute entries; by default they all do.
    Order relative to ``tight_layout`` does not matter -- the reservation is
    re-applied whenever the grid is reflowed.

Automatic layout
----------------

``fig.tight_layout(pad=0.02)``
    Measure each axes' decorations (tick labels, axis labels, titles) with the
    bundled font metrics and re-lay-out the subplot grid so nothing overflows or
    overlaps. Call it **before** ``colorbar`` (colorbars are positioned relative
    to their parent's rect).

Figure-level text
-----------------

``fig.suptitle(text, size=None)``
    A global title centered across the whole figure.

``fig.supxlabel(text, size=None)`` / ``fig.supylabel(text, size=None)``
    Shared x / y labels centered along the bottom / left of the figure. These
    span all subplots and coexist with each axes' own ``set_title`` /
    ``set_xlabel``.

Building a figure across processes
-----------------------------------

``fig.adopt_axes(ax)``
    Merge an axes built standalone -- most often a copy that just crossed a
    process boundary (a ``joblib``/``multiprocessing`` worker's return value)
    -- into this figure, in place of whichever of this figure's own axes
    shares its grid position.

    A ``Figure`` isn't something a worker process can share with the one
    that owns it: pickling an axes to hand it to a worker (or back) always
    produces a copy, never a live reference, however identical it looks --
    mutating that copy inside the worker never touches the original.
    ``adopt_axes`` is the fix, not a workaround for avoiding it: give a
    worker function a real axes to plot on, let it plot on a pickled copy
    of that axes in its own process, and merge the finished copy back with
    ``adopt_axes`` once it returns.

    .. code-block:: python

       from joblib import Parallel, delayed

       def analyze_panel(ax, x, y, title):
           # fit + plot -- identical whether ax came from this process
           # or a pickled copy of one; adopt_axes() is never called here
           coeffs = np.polyfit(x, y, deg=2)
           ax.scatter(x, y)
           ax.plot(x, np.polyval(coeffs, x), color="red")
           ax.set_title(title)
           return ax

       fig, axes = plotpress.subplots(2, 2)
       panels = {"a": {"ax": axes[0, 0], "x": xa, "y": ya, "title": "a"}, ...}

       built = Parallel(n_jobs=4)(delayed(analyze_panel)(**kw) for kw in panels.values())
       for built_ax in built:
           fig.adopt_axes(built_ax)
       fig.tight_layout()

       # debugging one panel later, live: the SAME function, called
       # directly -- no joblib, no adopt_axes() needed at all
       analyze_panel(axes[0, 0], xa, ya, "a")

    A colorbar axes has no grid position to match, since :meth:`~plotpress.figure.Figure.colorbar`
    always creates one that never existed in this figure to begin with --
    it is appended instead of replacing a slot. Adopt it and the axes it
    belongs to from the *same* worker result (e.g. both elements of a
    returned ``(ax, cax)`` tuple): pickling preserves the object graph
    *within* one call, so the colorbar's own reference to its parent axes
    survives the round trip already correct.

    Anything that compares axes by identity across more than one of them
    -- :meth:`~plotpress.figure.Figure.group`, a colorbar shared over
    several axes, ``align_xlabels``/``align_ylabels`` -- has to run
    *after* every worker's result has been adopted, against the real,
    merged objects. Never before dispatch, and never inside the worker
    itself: identity never survives a process boundary, so there is no
    way to express "these two axes belong to the same group" from inside
    two different workers that each only ever see their own copy.

    See :doc:`../auto_examples/parallel_building/plot_01_joblib_lazy_parquet_fit`
    for a full worked example.
