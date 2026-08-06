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
     - Wheel, or drag a rubber-band box, to zoom *one* axes in **data space** --
       its ticks recompute and markers keep a constant size.
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

Per-axes zoom and pan operate on a single axes' data limits (not an image
zoom of the whole figure), recomputing that axes' ticks live -- including on log
scales.

Point picking reports extra dimensions
--------------------------------------

Picked values carry any extra per-point dimensions. A ``pcolormesh``/``imshow``/
``contour`` cell reports its ``z`` value; a scatter reports its ``c`` value;
and arbitrary named dimensions attach via ``values=`` on the plotting call.

Extracting markers to Python
----------------------------

The **Extract** button opens a panel to copy/download the current markers and
annotations as **CSV or JSON**. Each record is a dict, e.g.::

    {"axes": 0, "kind": "mesh", "x": 0.95, "y": 1.05, "z": 0.397}
    {"axes": 0, "kind": "annotation", "x": 3.5, "y": 0.36, "text": "peak"}

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
