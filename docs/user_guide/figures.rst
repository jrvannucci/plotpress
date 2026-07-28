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
