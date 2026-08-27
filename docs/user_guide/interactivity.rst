Interactive figures
====================

Interactive HTML (``fig.save("x.html", interactive=True)`` / ``fig.to_html()``)
and the native window (``fig.show()``) carry a self-contained, vanilla-JS
toolbar. It makes **no external requests**, so it works offline and under strict
CSPs (Jupyter, sandboxed webviews).

Nothing is interactive until a tool is selected.

The toolbar
-----------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Tool
     - Behavior
   * - **Span**
     - Drag to pan a single plot's data window (log-aware).
   * - **Zoom**
     - Two distinct gestures. Drag a rubber-band box to zoom *one axes* in
       **data space** -- its ticks recompute and markers keep a constant
       size. Ctrl+wheel zooms the *whole figure* instead, centered on the
       cursor, regardless of which axes (if any) is under it -- the useful
       gesture on a figure with many small axes, where the cursor is only
       ever over one tiny panel at a time. It only rescales the SVG's own
       viewBox, so it never touches any axes' data range or ticks.
   * - **Point Pick**
     - Click to pin the nearest data value. Arrow keys step along the series
       (nearest-neighbour for scatter, cell-by-cell for meshes, contours and
       images). Right-click deletes a marker; Escape clears all.
   * - **Annotate Point**
     - Like Point Pick, but prompts for text and locks a user-written note to
       that datum instead of the auto-generated readout; still steppable by
       arrow key and still tracks pan/zoom.
   * - **Annotate Free**
     - Drop a user-written note anywhere on the figure, not locked to any
       datum -- including the margins or the gap between subplots.
   * - **Reset**
     - Restore the view; double-click resets just the plot under the cursor.
   * - **Extract**
     - Copy/download all markers + annotations, or return them to Python.
   * - **Hide Annotations**
     - A standalone toggle, not a mode -- available regardless of which tool
       is selected. Hides every pin and annotation without deleting any of
       them; toggling it back to "Show Annotations" restores them exactly as
       they were, text included.
   * - **Save As**
     - Download the current page -- pan/zoom, every pin/annotation, hidden
       legend series, Hide Annotations -- as a new, equally self-contained
       HTML file. Reopening it resumes this exact session, not just what was
       originally plotted.
   * - **Save**
     - The same, but tries to overwrite the file this page was opened from
       instead of downloading a new one. That needs the File System Access
       API (Chromium, a secure context); anywhere it's unavailable this
       falls back to the same download Save As does.
   * - **▸** / **◂**
     - Collapses the whole button row (a screenshot, an unobstructed view)
       without hiding this one handle, which stays put so the row can always
       be brought back -- no reload needed. Not remembered across a
       reload/Save; it always starts expanded.

A box-drag zoom and Span's pan both operate on a single axes' data limits,
recomputing that axes' ticks live -- including on log scales. Ctrl+wheel (or
a trackpad pinch) is the one *image*-style zoom of the whole figure: it never
changes any axes' data limits or ticks, only what part of the rendered figure
is currently visible. A plain wheel, without Ctrl, is left to scroll the page
instead -- it never zooms.

Point picking reports extra dimensions
--------------------------------------

Picked values carry any extra per-point dimensions. A ``pcolormesh``/``imshow``/
``contour`` cell reports its ``z`` value; a scatter reports its ``c`` value;
and arbitrary named dimensions attach via ``values=`` on the plotting call.

Every picked record also carries ``axes`` (the source axes' index) and
``axes_title`` -- the axes' own title, or a generated ``"axes N"`` when it has
none, so a multi-panel export always identifies its source panel by name, not
just a bare index. ``xlabel``/``ylabel`` carry that axes' own axis labels, and
``zlabel`` carries the title of any colorbar attached to it (this library's
own convention for labeling what a colorbar's scale means is
``fig.colorbar(mesh, ax=ax).set_title("units")``) -- a colorbar shared across
several axes via ``fig.colorbar(mesh, ax=[a, b])`` reports the same
``zlabel`` for each of them. Together these mean a value pulled out of
context (a CSV row, a JSON dict) still says what it means, not just a bare
number.

:meth:`~plotpress.axes.Axes.set_pick_context` attaches further, axes-level
key/value context that rides along on every record picked from that axes --
useful for identifying a panel by more than its title, e.g. surfacing a
per-panel spine color:

.. code-block:: python

   ax.set_pick_context(edge_color="red")
   # a click on this axes now reports {..., "edge_color": "red", ...}

A context key that collides with a structured field the record already sets
(``x``, ``y``, ``kind``, ...) is ignored for that record -- the picked data
always wins. See :doc:`../auto_examples/axes_features/plot_11_spine_color_grid`
for a worked example, and the live figure in :doc:`../usage`.

:meth:`~plotpress.axes.Axes.set_pickable` (default ``True``) excludes an axes
from **Point Pick** and **Annotate Point** -- a click there behaves as if it
missed every axes. **Span**, **Zoom**, and **Annotate Free** are unaffected,
so a figure can restrict picking to a single panel while every other tool
still works everywhere:

.. code-block:: python

   for ax in other_axes:
       ax.set_pickable(False)   # only the remaining axes stays pickable

See :doc:`../auto_examples/axes_features/plot_13_pickable` for a worked
example, and the live figure in :doc:`../usage`.

Extracting markers to Python
----------------------------

The **Extract** button opens a panel to copy/download the current markers and
annotations as **CSV or JSON**. Each record is a dict, e.g.::

    {"axes": 0, "axes_title": "axes 0", "kind": "mesh", "x": 0.95, "y": 1.05, "z": 0.397}
    {"axes": 0, "axes_title": "axes 0", "kind": "annotation", "x": 3.5, "y": 0.36, "text": "peak"}

For a blocking "pick session" that hands the markers straight back to the
kernel, use the native window:

.. code-block:: python

   markers = fig.show(wait_for_extract=True)
   # kernel blocks; user picks points / annotates, clicks Extract; window closes
   for m in markers:
       print(m)

Sliders for N-dimensional data
------------------------------

:meth:`~plotpress.axes.Axes.plot_frames` renders 3-D data ``Y`` of shape
``(n_frames, n_points)`` and adds a **slider** (play / pause / step) over the
extra dimension. ``slider_values`` labels it.

.. code-block:: python

   wave = np.sin(x[None, :] - t[:, None])       # (n_frames, n_points)
   ax.plot_frames(x, wave, slider_values=t, slider_label="t")

* ``shared=True`` (default) -- all ``plot_frames`` panels share one global slider.
* ``shared=False`` -- each axes gets its own slider docked beneath it. Give
  several the same ``slider_group`` to show a link checkbox so they can scrub
  together on demand.

The same frames export to a self-contained looping GIF, for anywhere an
interactive HTML slider does not fit -- a README, a slide, a chat message:

.. code-block:: python

   fig.save("wave.gif", fps=10)

This animates whichever slider ``slider_unit`` names (``"main"``, the shared
global slider, by default). A figure with more than one -- some
``plot_frames`` panels shared, others docked with ``shared=False`` -- picks
one slider per GIF; the others hold their frame 0 for that render. Export
each unit separately (``slider_unit="ax1"``, matching the axes it is docked
to) for more than one animated GIF from the same figure.
