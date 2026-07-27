Configuring axes
================

Limits
------

``set_xlim(left, right=None)`` / ``set_ylim(bottom, top=None)``
    Set data limits explicitly (either two args or a ``(lo, hi)`` tuple).
    ``get_xlim()`` / ``get_ylim()`` return the resolved limits (autoscaled from
    the data when unset).

Scales
------

``set_xscale(scale)`` / ``set_yscale(scale)``
    ``"linear"`` (default) or ``"log"``. Log axes use decade ticks and map
    non-positive values to gaps.

``semilogx(*args, **kwargs)`` / ``semilogy(...)`` / ``loglog(...)``
    Convenience: set the scale(s) to log and ``plot`` in one call.

    .. code-block:: python

       ax.loglog(x, x**2)
       ax.set_yscale("log")

Aspect ratio
------------

``set_aspect(aspect)``
    ``"equal"`` makes one data unit equal in x and y (circles look circular);
    ``"auto"`` fills the box; a number sets the y/x unit ratio. Implemented
    box-adjust: the drawn box shrinks, centered, to honor the ratio.

Ticks and labels
----------------

``set_xticks(ticks)`` / ``set_yticks(ticks)``
    Fix tick locations. Pass ``[]`` to hide ticks; pass ``None`` to restore
    automatic "nice number" ticks.

``set_xlabel(label)`` / ``set_ylabel(label)`` / ``set_title(title)``
    Axis labels and the per-axes title.

Grid, legend, visibility
------------------------

``grid(visible=True)``
    Toggle grid lines at the tick locations.

``legend()``
    Draw a legend from artists that were given a ``label=``. Placed in the
    upper-right of the axes.

``set_axis_off()``
    Hide the spines, ticks, grid, and axis labels (the title is kept). Used
    automatically by :meth:`~plotpress.axes.Axes.pie`.

.. note::

   In interactive HTML, per-axes **data** zoom/pan recomputes ticks live and
   redraws the artists of the axes under the cursor. See :doc:`interactivity`.
