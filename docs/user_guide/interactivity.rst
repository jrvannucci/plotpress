Interactive figures
====================

Interactive HTML (``fig.save("x.html", interactive=True)`` / ``fig.to_html()``)
and the native window (``fig.show()``) carry a self-contained, vanilla-JS
toolbar. It makes **no external requests**, so it works offline and under strict
CSPs (Jupyter, sandboxed webviews).

Nothing is interactive until a tool is selected.

In a Jupyter notebook
----------------------

Evaluating a figure directly in a cell (``fig`` as the last expression)
renders it inline as static SVG, not this toolbar -- there's deliberately
no ``_repr_html_``, since Jupyter prefers ``text/html`` over ``image/svg+xml``
when a MIME bundle offers both, and a full interactive HTML document
dropped into an output cell that way renders messily and its ``<script>``
doesn't run there regardless (see :doc:`viewing` for the full comparison of
every surface a figure can render on).

``fig.show_in_jupyter()`` (needs ``[jupyter]``: ``pip install
plotpress[jupyter]`` -- any real Jupyter environment already has IPython)
is the one line that gets this toolbar working inline instead: it embeds
``to_html()``'s self-contained output in an ``<iframe>``, which does
isolate and run the inlined JS, so every tool below -- Pan/Zoom,
Point Picking, sliders, all of it -- works exactly as it does in a saved
``.html`` file opened in a browser:

.. code-block:: python

   fig, ax = plotpress.subplots()
   ax.plot(x, y)
   fig.show_in_jupyter()   # last expression in the cell, or wrap in display(...)

``width``/``height`` default to the figure's own pixel size
(``figsize`` x ``style.dpi``) and can be overridden --
``fig.show_in_jupyter(width=900, height=600)``.

The toolbar
-----------

A single row, spanning the full width of the window and pinned to its top
(``position:fixed``, immune to scrolling, panning, or Pan/Zoom's own
whole-figure zoom). Pan/Zoom and Home sit standalone at the
far left -- whole-figure tools reached for often enough to skip a menu's
extra click. Everything else groups into four menus by what the buttons do:
**Axes** (Axis Span/Axis Zoom, then Reset All Axes, the pair it undoes),
**Point Picking** (the tool, Hide Points, Clear Points, and Extract),
**Annotate** (the tool, Hide Annotations, then Clear Annotations), and
**File** (Save, Save As). A caller's own custom tools (``plotpressAddTool``,
see :doc:`../auto_examples/custom_interactivity/plot_01_add_a_measure_tool`)
get a fifth **Custom** menu, created only once one is actually added. A
persistent indicator naming the current tool (or "No tool active") is pinned
to the bar's own far right.

A menu item that selects a tool is checkable, not one-shot: clicking it
selects that tool (deselecting whatever else was active) and leaves the
menu open, so picking a different tool from the same menu doesn't need
reopening it first. Double-click the active tool to deselect it -- or press
Escape, which works from anywhere, not just while that tool's own button
has focus (handy for a keyboard-only user, who has no double-click to
deselect with). One-shot actions -- Save, Home, Clear Points, Extract, and
the like -- fire immediately and close their menu, the same as clicking
outside any menu does; so does Escape, when a menu happens to be open
(otherwise Escape clears every pin/annotation *and* deselects the active
tool in one press, see the Point Picking row below).

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Tool
     - Behavior
   * - **Pan/Zoom**
     - A plain wheel zooms the *whole figure*, centered on the cursor,
       regardless of which axes (if any) is under it -- the useful gesture
       on a figure with many small axes, where the cursor is only ever over
       one tiny panel at a time. It grows the SVG's own rendered size
       (never any axes' data range or ticks), so once it no longer fits the
       window the browser's own scrollbars reach the rest of it, the same
       as scrolling any other oversized page content. Drag pans that same
       whole-figure view (native page scroll under the hood) in any
       direction. Double-click resets that view (there is no per-axes zoom
       to reset here, unlike Axis Span/Zoom below). Sits standalone at the
       toolbar's far left, not behind a menu -- the one whole-figure-level
       navigation tool, reached for often enough to skip a menu's extra
       click. (Text on the figure -- tick labels, titles, pin labels -- is
       left unselectable for as long as *any* mode is active, not just this
       one: every mode's own drag can sweep across it the same way this
       one's pan always could.)
   * - **Home**
     - Restores whole-figure magnification to its natural size; leaves
       every axes' own pan/zoom and every pin/annotation untouched. Sits
       standalone right after Pan/Zoom, the tool it undoes. Neither Reset
       button (this one, or Reset All Axes below) clears pins or
       annotations; that's what Clear Points/Clear Annotations below are
       for.
   * - **Axis Span**
     - Drag to pan a single plot's data window (log-aware).
   * - **Axis Zoom**
     - Two distinct gestures. Drag a rubber-band box to zoom *one axes* in
       **data space** -- its ticks recompute and markers keep a constant
       size. Ctrl+wheel zooms the *whole figure* instead, the same gesture
       Pan/Zoom's plain wheel does.
   * - **Reset All Axes**
     - Restores every axes' own pan/zoom to its original view; leaves
       whole-figure magnification and every pin/annotation untouched.
       Double-click resets just the plot under the cursor.
   * - **Point Picking**
     - Click to pin the nearest data value. Arrow keys step along the series
       (nearest-neighbour for scatter, cell-by-cell for meshes, contours and
       images). Right-click deletes a marker; Escape clears every pin *and*
       annotation at once (and deselects the active tool, back to no tool
       active). A marker's own dot scales down with the axes it
       landed on, so it never dwarfs a tiny panel in a large grid the way a
       fixed size would -- and stays that same on-screen size at any
       whole-figure zoom level (Pan/Zoom or Axis Zoom's Ctrl+wheel), rather
       than growing along with the figure until it covers the very cell it
       is pointing at. Its
       label box (offset from the dot by default, connected to it by a thin
       leader arrow) is itself draggable -- grab the box, not the dot,
       while Point Picking is active -- and a dragged position survives
       pan/zoom/arrow-key steps and a Save/Save As round trip.
   * - **Hide Points**
     - A standalone toggle, not a mode -- available regardless of which
       tool is selected. Hides every Point Picking pin without deleting any
       of them; toggling it back to "Show Points" restores them exactly as
       they were, text included. Independent of Hide Annotations below --
       an Annotation note stays visible either way.
   * - **Clear Points**
     - Removes every Point Picking pin at once, and only those -- an
       Annotation note survives untouched.
   * - **Extract**
     - Copy/download picked points, or return them to Python -- Point
       Picking pins only, not Annotation notes; an Annotation note has
       nothing to "extract" in the same sense a picked data value does.
   * - **Annotation**
     - Drop a user-written note anywhere on the figure, not locked to any
       datum -- including the margins or the gap between subplots. Its own
       box drags the same way a Point Picking pin's does, while Annotation
       is the active mode.
   * - **Hide Annotations**
     - The mirror of Hide Points: hides every Annotation note without
       deleting any of them, *plus* every figure-drawn boxed callout
       (``ax.text()``/``ax.annotate(bbox=...)``) -- a static callout reads
       the same way on screen as a note. Toggling it back to "Show
       Annotations" restores everything exactly as it was.
   * - **Clear Annotations**
     - The mirror of Clear Points: removes every Annotation note at once,
       and only those -- a Point Picking pin survives untouched.
   * - **Save**
     - Tries to overwrite the file this page was opened from -- pan/zoom,
       every pin/annotation, hidden legend series, Hide Points/Hide
       Annotations, all included -- instead of downloading a new one. That
       needs the File System Access API (Chromium, a secure context);
       anywhere it's unavailable this falls back to the same download Save
       As does.
   * - **Save As**
     - The same, but always downloads a new, equally self-contained HTML
       file rather than trying to overwrite the original. Reopening it
       resumes this exact session, not just what was originally plotted.

``window.plotpressGetMarkers()`` (see below) returns every pin and
annotation, unlike Extract -- it's the general programmatic query a custom
tool or an embedding (e.g. :mod:`plotpress.qt`) reads from, not Extract's
own narrower output.

A box-drag zoom and Axis Span's pan both operate on a single axes' data
limits, recomputing that axes' ticks live -- including on log scales.
Ctrl+wheel (or a trackpad pinch) under Axis Zoom, and Pan/Zoom's own
plain wheel, are the one *image*-style zoom of the whole figure: neither ever
changes any axes' data limits or ticks, only what part of the rendered figure
is currently visible. A plain wheel with no tool selected is left to scroll
the page instead -- it never zooms.

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
``zlabel`` for each of them. ``group`` carries the title of any
:meth:`~plotpress.figure.Figure.group` box that axes sits in -- empty when it
belongs to none, joined with ``", "`` on the rare axes added to more than
one. Together these mean a value pulled out of context (a CSV row, a JSON
dict) still says what it means, not just a bare number.

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
from **Point Picking** -- a click there behaves as if it missed every axes.
**Axis Span**, **Axis Zoom**, **Pan/Zoom**, and **Annotation** are
unaffected, so a figure can restrict picking to a single panel while every
other tool still works everywhere:

.. code-block:: python

   for ax in other_axes:
       ax.set_pickable(False)   # only the remaining axes stays pickable

See :doc:`../auto_examples/axes_features/plot_13_pickable` for a worked
example, and the live figure in :doc:`../usage`.

Extracting markers to Python
----------------------------

The **Extract** button (in the Point Picking menu) opens a panel to
copy/download the current Point Picking markers -- not Annotation notes,
which have nothing to "extract" in the same sense a picked data value does
-- as **CSV or JSON**. Each record is a dict, e.g.::

    {"axes": 0, "axes_title": "axes 0", "kind": "mesh", "x": 0.95, "y": 1.05, "z": 0.397}
    {"axes": 0, "axes_title": "axes 0", "kind": "points", "index": 3, "x": 3.5, "y": 0.36}

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

Adding or replacing the interactivity
--------------------------------------

``extra_js`` (on :meth:`~plotpress.figure.Figure.to_html`/:meth:`~plotpress.figure.Figure.save`)
inlines a caller-supplied JS string into the page, run *after* plotpress's
own -- so ``window.plotpressAddTool``/``plotpressGetMarkers``/``plotpressToData``
already exist by the time it runs. Nothing about supplying it fetches
anything external on its own; it is inlined the same as plotpress's own JS,
keeping the "no external requests" guarantee intact regardless of what it
contains.

**Adding to the existing toolbar** (``include_default_js`` left at its
default ``True``):

.. code-block:: python

   extra_js = """
     window.plotpressAddTool({
       label: 'Log Markers',
       onClick: function () { console.log(window.plotpressGetMarkers()); },
     });
   """
   fig.save("figure.html", interactive=True, extra_js=extra_js)

``window.plotpressAddTool(opts)`` registers a real button in its own
**Custom** menu, alongside the four built-in ones (created only once a first
custom tool actually exists) -- not appended into a built-in menu itself,
which would otherwise run longer with every tool added and blur which
buttons are plotpress's own vs the page's. Two shapes mirroring the built-in
tools:

``{label, onClick}``
    An always-available action, firing immediately on click -- like the
    built-in Extract/Save buttons. Never joins the selection group below.

``{label, mode, onClick, onEnter, onExit, cursor}``
    A real *mode*, joining the same single-selection group as Pan/Zoom,
    Axis Span/Zoom, Point Picking, and Annotation -- selecting it
    deselects whatever else was active, and vice versa. A click on the SVG
    that no built-in mode already claims calls
    ``onClick(event, userSpacePoint)``. ``window.plotpressToData(userSpacePoint)``
    converts that further into a real data value (``{axes, x, y}``, or
    ``null`` off any pickable axes) -- the same per-axes, log-scale/
    inverted-axis-aware conversion Point Picking itself uses, so a custom
    tool doesn't have to reimplement it.
    ``onEnter``/``onExit`` fire when the mode is selected/deselected;
    ``cursor`` sets ``svg.style.cursor`` while it's active.

See :doc:`../auto_examples/custom_interactivity/plot_01_add_a_measure_tool`
for a worked example (a custom "Measure" tool joining the selection group,
plus a plain action button).

**Replacing the interactivity entirely** (``include_default_js=False``):
drops plotpress's own toolbar/pan/zoom/pick JS from the page altogether --
``extra_js`` becomes the *only* interactivity this page gets, built from the
raw ``#plotpress-meta``/``#plotpress-pick``/``#plotpress-style``/
``#plotpress-layout`` JSON payloads (still emitted, since
``interactive=True``) and ``#plotpress-svg`` directly, rather than extending
what plotpress already provides. ``#plotpress-layout`` (grid shape/position
and every decoration -- title, labels, limits, scale, ... -- of each
subplot-grid axes, plus any ``Figure.group()`` boxes and the figure's own
sup-title) is read by Python's own ``load_data()``/``subplots_from_layout()``
round trip, not by the bundled client JS -- no toolbar tool reads it back
out of the page.
``binary_pick_data=False`` is worth pairing with this: the default packs
long numeric arrays as base64 float16/32 for size, which needs plotpress's
own decoder -- exactly what dropping the built-in JS is turning off.

.. code-block:: python

   fig.save("figure.html", interactive=True, include_default_js=False,
            binary_pick_data=False, extra_js=my_own_toolbar_js)

See :doc:`../auto_examples/custom_interactivity/plot_02_override_with_your_own_js`
for a worked example: a click handler built entirely from ``#plotpress-meta``,
with none of plotpress's own JS involved at all.

Exposing the payload shapes at all is a real commitment -- ``axes_metadata()``/
``pick_data()``'s own field names become something a from-scratch script can
depend on, so they're no longer free to change without notice the way
purely-internal serialization would be. What is *not* exposed alongside
them is plotpress's own internal coordinate-transform/zoom/pan
implementation as a reusable library -- ``include_default_js=False`` hands
back the raw data and nothing else; reimplementing pan, zoom, or hit-testing
against it is on the caller.
