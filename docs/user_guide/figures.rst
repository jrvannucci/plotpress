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

Grouping axes
-------------

``fig.group(title, axes, id=None, linestyle="--", color="black", linewidth=1.5, title_position="top", pad=8.0, fontsize=None)``
    Draw a labeled box around a set of axes -- e.g. a cluster of related
    panels in a larger grid. The box is the tight bounding rectangle of
    their individual positions, expanded to also clear each axes' own
    tick labels, axis labels, and title. ``title_position`` is one of
    ``"top"``/``"bottom"``/``"left"``/``"right"``, placing ``title`` just
    outside that edge of the box. ``id`` is a second, exact-match way to
    find the group again besides its title -- unlike an axes' own id (see
    below), a group's id isn't required to be unique. Several groups may
    be added to one figure; call before ``tight_layout()`` so it can
    reserve outer margin for a title facing the figure's own edge.

``fig.group_spacing(wspace=None, hspace=None)``
    Reserve extra pixels between subplots for ``group()`` boxes, on top of
    whatever ``tight_layout()`` already sizes from tick labels alone --
    only at the interior row/column boundaries that actually border a
    group's own bounding box, not every gap alike.

``fig.get_groups()`` / ``fig.get_group(row=None, col=None, title=None, id=None)``
    ``get_groups()`` is every registered group as a
    :class:`~plotpress.figure.Group` (``.title``, ``.id``, ``.axes``,
    ``.outer_row``/``.outer_col``, the same styling ``group()`` took) --
    a snapshot, not a live view. ``get_group()`` finds the *one* matching
    exactly one of: ``(row, col)`` together (a group's own position in its
    :class:`~plotpress.figure.GroupLayout` outer grid -- see below;
    ``None`` for a plain manual ``group()`` call), ``title``, or ``id`` --
    raising if none or more than one matches. Read either to find which
    axes already belong to a named group before combining it with
    another, or to inspect a figure you didn't build yourself.

    .. code-block:: python

       fig, axes = plotpress.subplots(2, 2)
       fig.group("Left pair", [axes[0, 0], axes[1, 0]])
       fig.group("Right pair", [axes[0, 1], axes[1, 1]])
       for g in fig.get_groups():
           print(g.title, len(g.axes))
       left = fig.get_group(title="Left pair")

``fig.get_ax(row=None, col=None, title=None, id=None, many=False)`` / ``group.get_ax(row=None, col=None, title=None, id=None, many=False)``
    Find one axes by exactly one of ``(row, col)``, ``title``, or ``id``
    -- ``fig.get_ax()``'s row/col is a *plain, ungrouped* axes' own grid
    position (use ``group.get_ax()`` for an axes inside a group instead);
    ``group.get_ax()``'s row/col is that group's own *inner* position
    (raises if the group has no grid shape, i.e. it wasn't built from a
    ``GroupLayout``). Either raises if nothing matches, or -- unless
    ``many=True`` -- if more than one does (impossible for ``id``, unique
    per figure by construction; titles may legitimately repeat).
    ``many=True`` returns every match as a list instead.

``ax.set_id(id)`` / ``ax.get_id()``
    A plain, undrawn identifier for later retrieval via ``get_ax()`` --
    distinct from ``set_title()`` (drawn on the plot, and may repeat
    across axes). Unlike a title, an id must be unique across the whole
    figure: raises if another axes already has it. ``None`` (the default)
    always clears it.

``fig.remove_group(group=None, title=None, id=None)``
    Remove a group entirely: every one of its axes (via ``ax.remove()``,
    which also frees its id and drops it from ``sharex``/``sharey``
    groups) and the group's own box/title registration -- leaves a blank
    rectangle rather than reflowing the rest of the grid to fill it.

``plotpress.GroupLayout(nrows, ncols)`` / ``plotpress.subplots_from_groups(layout, figsize=(6.4, 4.8), ...)``
    Build a figure as an outer grid of *groups*, each its own inner grid
    of axes -- for a layout like "four quadrants, each its own 2x2
    cluster of plots" without hand-deriving which cells of one big flat
    grid each quadrant's axes actually occupy.
    ``layout.add_group(row, col, nrows, ncols, mask=None, axes_ids=None, axes_titles=None, title=None, id=None, **group_kwargs)``
    places one group at outer cell ``(row, col)``; every group may have a
    *different* inner shape, inferred from whichever of these is given:

    - ``mask`` (an ``nrows`` x ``ncols`` array-like of truthy/falsy
      values) marks which inner cells actually get an axes -- an
      irregular group (an L-shape, a ring with a hole) instead of a
      plain rectangle, with no axes created for a falsy cell.
    - ``axes_ids``/``axes_titles`` (the same shape, ``str | None``) do the
      same, mosaic-style: a non-``None`` entry both marks presence *and*
      sets that axes' id/title in one step. Giving more than one of
      these is fine as long as they agree on which cells are present.

    ``layout.remove_group(row, col)`` drops a *planned* group before
    building (see ``fig.remove_group()`` above for removing one from an
    already-built figure instead).

    .. code-block:: python

       layout = plotpress.GroupLayout(2, 2)
       layout.add_group(0, 0, 2, 2, title="Group (0,0)")
       layout.add_group(0, 1, 2, 2, title="Group (0,1)")
       layout.add_group(1, 0, 2, 2, title="Group (1,0)")
       layout.add_group(1, 1, 2, 2, title="Group (1,1)")
       fig, axes = plotpress.subplots_from_groups(layout, figsize=(12, 10))
       axes[0, 0][1, 1].plot(x, y)   # group (0,0)'s own bottom-right axes

    Internally this resolves onto one plain, flat grid -- the least
    common multiple of every group's own row/column count, times the
    outer shape -- with each group's axes as ordinary ``SubplotSpec``
    spans within it. The figure is completely ordinary once built:
    ``tight_layout()``, ``align_xlabels``/``align_ylabels``,
    ``to_vega``/``to_vega_lite``, and twin/secondary axes all work
    unmodified. Keep every group's row count sharing a small common
    multiple with its neighbors' (and likewise for columns) -- mixing
    incompatible shapes (5 rows alongside 2 and 3) can need a far finer
    shared grid than any one of them suggests, which past about 40 rows
    or columns can make ``tight_layout()`` drop every gap, including
    ``group_spacing()``'s own reservation, to keep cells from shrinking
    to nothing -- :func:`~plotpress.figure.subplots_from_groups` warns
    when this happens. See :doc:`/auto_figure_layout/grouping/plot_14_irregular_group_shapes`
    and :doc:`/auto_figure_layout/grouping/plot_15_dashboard_mixed_shapes_and_masks`
    for worked examples, and
    :doc:`/auto_figure_layout/grouping/plot_18_two_ways_to_build_the_same_grouped_figure`
    for the same figure built both with ``GroupLayout`` and by hand with
    ``subplots()`` + ``Axes.remove()`` + ``fig.group()``.

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

``fig.legend(ax=None, loc="lower center", ncol=1, title=None, pad=0.01, fontsize=None)``
    One legend for the whole figure, drawn from every labelled artist. Labels
    are **de-duplicated**, so a grid whose panels all plot the same series gets
    one entry per series rather than one per panel. ``fontsize`` overrides
    the entry/title text size, matching ``Axes.legend``.

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
