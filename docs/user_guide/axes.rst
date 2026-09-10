Configuring axes
================

Limits
------

``set_xlim(left, right=None)`` / ``set_ylim(bottom, top=None)``
    Set data limits explicitly (either two args or a ``(lo, hi)`` tuple).
    ``get_xlim()`` / ``get_ylim()`` return the resolved limits (autoscaled from
    the data when unset). A bound may also be datetime-like or a string,
    resolved the same way plotting data is -- see `Datetime and categorical
    axes`_ below -- so ``set_xlim("2024-01-01", "2024-06-01")`` works once the
    axis has seen date data, and ``set_xlim("Q1", "Q3")`` works once it has
    seen those categories. A string bound the axis has no mapping for raises,
    rather than silently starting a new category.

Datetime and categorical axes
------------------------------

Every plotting method (``plot``, ``scatter``, ``bar``/``barh``, ``step``,
``fill_between``/``fill_betweenx``, ``hlines``/``vlines``,
``axhline``/``axvline``, ``errorbar``, ``stem``, ``broken_barh``) accepts two
kinds of non-numeric ``x``/``y`` data directly, with no conversion step:

**Datetime-like** -- a ``numpy.datetime64`` array, a ``datetime.date``/
``datetime.datetime`` (or a sequence of either), or an ISO date string once
the axis is already date-flavored. Values convert to real floating-point days
since the 1970-01-01 epoch (the same epoch modern matplotlib uses), so points
space **proportionally to real elapsed time** -- a gap of 100 days plots ten
times wider than a gap of 10 days, unlike a categorical axis, which would
space every point evenly regardless of what it represents. Ticks land on
calendar-aware boundaries (year/month/day/hour/minute/second, whichever tier
best fits the visible span):

.. code-block:: python

   dates = np.array(["2024-01-05", "2024-01-20", "2024-06-15"], dtype="datetime64[D]")
   ax.plot(dates, [4.2, 5.1, 18.3])
   ax.set_xlim("2024-01-01", "2024-07-01")

**Categorical (string)** -- a plain list of strings plots as a categorical
axis: each distinct value gets an integer position (0, 1, 2, ...) in the
order it is first seen *on that axis*, shared across every plotting call on
it, so a second series naming overlapping categories lands on the same
positions instead of appending duplicates:

.. code-block:: python

   ax.bar(["Q1", "Q2", "Q3"], [10, 20, 15])
   ax.plot(["Q1", "Q3"], [12, 18])   # shares Q1/Q3's positions with the bars above

Mixing plain numbers into an axis that is already date- or category-flavored
(on the same dimension) is not a supported idiom. See
:doc:`../auto_examples/axes_features/plot_22_datetime_categorical_and_tick_specs`,
:doc:`../auto_examples/axes_features/plot_23_datetime_gantt_and_milestones`
(``broken_barh`` with real dates, the other common datetime idiom -- compare
:doc:`../auto_examples/pairwise/plot_11_broken_barh`'s plain day-offsets),
and :doc:`../auto_examples/axes_features/plot_24_more_categorical_axes_and_tick_formats`
for worked examples.

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

``set_xticks(ticks, labels=None, minor=False)`` / ``set_yticks(ticks, labels=None, minor=False)``
    Fix tick locations. Pass ``[]`` to hide ticks; pass ``None`` to restore
    automatic "nice number" ticks. ``ticks`` may also be datetime-like or a
    list of strings -- resolved the same way as plotting data (see `Datetime
    and categorical axes`_ above), so ``set_xticks(["Q1", "Q2", "Q3"])``
    both declares those as this axis' categories *and* pins the tick
    positions, even before any data has been plotted.

``set_xlocator(spec)`` / ``set_ylocator(spec)``
    A declarative tick-*location* rule, in place of the default "nice
    number" scheme -- currently just
    ``{"kind": "multiple", "base": ...}`` (matplotlib's ``MultipleLocator``:
    a tick at every multiple of ``base``, e.g. every ``np.pi / 2`` on a trig
    plot). Ranks below an explicit literal ``set_xticks`` array and this
    axis' own categories, and above date/log/default ticking.

``set_xformat(spec)`` / ``set_yformat(spec)``
    A declarative tick-*label* rule: ``"percent"``, ``"comma"``/
    ``"thousands"``, ``"eng"``/``"engineering"`` (SI suffixes -- ``1.5k``,
    ``2.3M``), ``"pi"``/``"multiple_of_pi"`` (``pi/2``, ``3pi/4``), any of
    those as a dict with options (``{"kind": "percent", "decimals": 1}``), a
    raw ``%``-style format string (``"$%.0f"``), or a plain callable
    ``value -> str``.

    Every form except a callable is plain, JSON-serializable data --
    deliberately not a matplotlib-style ``Locator``/``Formatter`` object --
    so the exact same rule replays correctly when an interactive figure is
    panned or zoomed in the browser. A callable formatter still works for
    static SVG/PNG/PDF output, but can't cross into the page's JavaScript:
    a zoomed interactive figure using one falls back to default formatting
    for that axis instead.

``set_xlabel(label, visible=True)`` / ``set_ylabel(label, visible=True)`` / ``set_title(title)``
    Axis labels and the per-axes title. ``visible=False`` stores the
    label without drawing it and without reserving any margin for it --
    ``get_xlabel()`` still returns the text, ``print_summary()`` still
    lists it (marked ``(hidden)``), the ``load_data()`` layout round-trip
    still carries it, and a picked point's **Extract** record still
    reports it. For a dense grid that names every panel's axes for later
    data export but draws only one shared ``fig.supxlabel``/
    ``fig.supylabel`` -- see
    :doc:`/auto_examples/axes_features/plot_25_hidden_axis_labels`.

``set_xlabel_visible(visible=True)`` / ``set_ylabel_visible(visible=True)`` / ``get_xlabel_visible()`` / ``get_ylabel_visible()``
    Show or hide an axis label without changing its text -- the toggle
    form of the ``visible=`` argument above. (matplotlib spells this
    ``ax.xaxis.label.set_visible(...)``; plotpress has no per-artist
    handle, so the toggle is a direct method.)

``set_id(id)`` / ``get_id()``
    A plain, undrawn identifier for this axes -- distinct from
    ``set_title()``, which is drawn on the plot and may legitimately
    repeat across several axes. Unlike a title, ``id`` must be unique
    across this axes' whole figure: raises if another axes already has
    it. Pass ``None`` to clear it. Exists for later retrieval via
    ``fig.get_ax(id=...)`` or (inside a group) ``group.get_ax(id=...)``
    -- see :doc:`figures` for both, and
    :doc:`/auto_figure_layout/grouping/plot_14_irregular_group_shapes` for a
    worked example.

Grid, legend, visibility
------------------------

``grid(visible=True)``
    Toggle grid lines at the tick locations.

``legend(loc="upper right", ncol=1, title=None, handles=None, labels=None, fontsize=None)``
    Draw a legend from artists that were given a ``label=``, placed inside this
    axes. A ``twinx``/``twiny`` twin's artists are included too, so one call
    covers both y axes. ``fontsize`` overrides the entry/title text size.
    ``handles`` overrides which artists appear -- any plotpress artist, in
    the order given, from this axes, another, or never added to one at all
    -- pair with ``labels`` to also override the text shown for each,
    positionally. For a single legend spanning a whole grid, see
    ``fig.legend`` in :doc:`figures`.

``set_axis_off()``
    Hide the spines, ticks, grid, and axis labels (the title is kept). Used
    automatically by :meth:`~plotpress.axes.Axes.pie`.

.. note::

   In interactive HTML, per-axes **data** zoom/pan recomputes ticks live and
   redraws the artists of the axes under the cursor. A date axis, a
   categorical axis, and a ``set_xlocator``/``set_xformat`` spec all replay
   correctly on that live rebuild -- except a *callable* ``set_xformat``,
   which falls back to default formatting there (see above). See
   :doc:`interactivity`.
