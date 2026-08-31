Plotting methods
================

Every plot type is a method on :class:`~plotpress.axes.Axes`. Signatures mirror
matplotlib. See the :ref:`gallery <gallery>` for a rendered example of each.

Every one of them also accepts ``zorder=0`` (omitted from the signatures
below to keep them focused on what's specific to each method) -- draw order
within an axes, independent of call order. Ties keep call order, so this is
opt-in: nothing changes unless you pass it. See
:doc:`../auto_examples/axes_features/plot_14_zorder` for a worked example.

Lines and areas
---------------

``plot(*args, color=None, linewidth=None, linestyle="-", label=None, alpha=1.0, marker=None, markersize=None, markerfacecolor=None)``
    Line plot of ``y`` or ``x, y``. ``linestyle`` is ``"-"``, ``"--"``, ``":"``
    or ``"-."``. Colors auto-advance through the per-axes cycle. ``marker``
    draws a dot at each vertex alongside the line (only round shapes are
    drawn, same limitation as :meth:`~plotpress.axes.Axes.scatter`);
    ``markerfacecolor`` defaults to the line's own ``color``.

    .. code-block:: python

       ax.plot(x, np.sin(x), label="sin")
       ax.plot(x, np.cos(x), linestyle="--")
       ax.plot(x, np.tan(x), marker="o", markerfacecolor="red")

``step(x, y, where="pre", color=None, linewidth=None, label=None, alpha=1.0)``
    Staircase line. ``where`` is ``"pre"``, ``"post"`` or ``"mid"``.

``fill_between(x, y1, y2=0.0, color=None, alpha=0.4, label=None, edgecolor=None, linewidth=0.0)``
    Shade the area between ``y1`` and ``y2`` (scalar or array).
    ``fill_betweenx(y, x1, x2=0.0, ...)`` is the horizontal form; both
    accept the same ``edgecolor``/``linewidth`` :meth:`~plotpress.axes.Axes.fill`
    already has.

``stackplot(x, *ys, colors=None, alpha=0.8, labels=None)``
    Stacked filled areas.

``axvline(x, color=None, linewidth=None, linestyle="--", label=None, alpha=1.0)``
    A vertical reference line at data ``x`` (does not affect autoscaling).

Markers
-------

``scatter(x, y, s=None, c=None, color=None, marker="o", label=None, alpha=1.0, cmap="viridis", norm=None, vmin=None, vmax=None, edgecolors=None, linewidths=None)``
    Scattered points. Pass ``c`` (an array) with ``cmap`` to color points by a
    third variable; ``s`` is the marker diameter in points. Markers stay a
    constant on-screen size under interactive zoom -- which is why only **round**
    markers are drawn: they are emitted as round-capped zero-length strokes, and
    a polygonal marker would have to scale with the zoom instead. ``marker`` is
    accepted for matplotlib compatibility and warns for any other shape;
    distinguish series by color, size or a label instead. ``edgecolors``/
    ``linewidths`` outline every marker in the call (one color/width for the
    whole collection, not per-point) -- keeps overlapping same-color points
    distinguishable; giving ``edgecolors`` alone still draws a visible
    outline, at a default width.

    .. code-block:: python

       ax.scatter(x, y, c=x**2 + y**2, cmap="plasma", s=12)
       ax.scatter(x, y, color="gold", edgecolors="black", linewidths=0.5)

Bars and histograms
-------------------

``bar(x, height, width=0.8, bottom=0.0, color=None, edgecolor=None, linewidth=0.8, label=None, alpha=1.0, yerr=None, xerr=None, capsize=3.0, ecolor=None)``
    Vertical bars. ``barh(y, width, height=0.8, left=0.0, ...)`` is the
    horizontal form. ``yerr``/``xerr`` draw error bars (whiskers + caps, no
    connecting line or marker) centered at each bar's own top
    (``barh``: right edge); ``ecolor`` defaults to black, independent of
    the bars' own ``color``.

``hist(data, bins=10, range=None, color=None, edgecolor="#ffffff", label=None, alpha=1.0, density=False, histtype="bar", cumulative=False, weights=None, stacked=False)``
    Histogram. ``data`` may be a single array or a sequence of arrays --
    multiple datasets share one set of bins, overlaid by default or
    ``stacked=True`` bottom-to-top. ``histtype`` is ``"bar"`` (default),
    ``"step"`` (unfilled outline) or ``"stepfilled"``. ``cumulative``
    running-sums left to right; ``weights`` weights each sample instead of
    counting it as 1. Returns ``(counts, edges, bars)`` -- ``counts``/
    ``bars`` are each a list, one per dataset, when ``data`` held more than
    one.

``hist2d(x, y, bins=20, range=None, cmap="viridis", alpha=1.0)``
    2-D histogram rendered as an image. Returns ``(counts, image)`` -- pass the
    image to :meth:`~plotpress.figure.Figure.colorbar`.

Statistical
-----------

``boxplot(data, positions=None, widths=0.5, color=None, orientation="vertical", label=None, alpha=1.0, whis=1.5, showfliers=True)``
    Box-and-whisker plot; ``data`` is a sequence of arrays. Whiskers reach
    ``whis`` IQRs past q1/q3 (matplotlib's own default is ``1.5``); points
    past that are drawn as open circles unless ``showfliers=False`` drops
    them instead.

``violinplot(data, positions=None, widths=0.5, color=None, orientation="vertical", label=None, points=100, alpha=0.55)``
    Kernel-density "violin" silhouettes (Gaussian KDE, Silverman bandwidth).
    ``alpha=0.55`` is the fill both backends already drew before it was
    configurable.

``errorbar(x, y, yerr=None, xerr=None, color=None, marker="o", markersize=None, capsize=3.0, linestyle="-", linewidth=None, label=None, alpha=1.0, ecolor=None, elinewidth=None, capthick=None)``
    Line/markers with x and/or y error bars and caps. ``ecolor``/
    ``elinewidth`` style the whiskers/caps independently of the line and
    marker -- each falls back to ``color``/``linewidth`` if not given.
    ``capthick`` (the caps' own width) falls back to ``elinewidth`` in turn.

``eventplot(positions, lineoffsets=None, linelengths=0.8, color=None, orientation="horizontal", label=None, alpha=1.0)``
    Raster of event ticks, one row per sequence.

``pie(values, labels=None, colors=None, startangle=90.0, radius=1.0, alpha=1.0)``
    Pie chart. Automatically hides the axis and fixes an equal-aspect square.

2-D fields
----------

``pcolormesh(*args, cmap="viridis", norm=None, vmin=None, vmax=None, alpha=1.0, label=None, rasterized=None)``
    Rectilinear pseudocolor mesh: ``pcolormesh(C)`` or ``pcolormesh(X, Y, C)``.
    A uniform grid always rasterizes to a single embedded image, so its grid
    size costs no DOM nodes; a *non-uniform* grid (cell widths that vary) does
    too by default once past ``rasterized=None``'s auto threshold of about
    2000 cells, below which it draws exact vector ``<rect>`` cells instead --
    no resampling, so no cell is ever too thin to draw. ``True``/``False``
    override the automatic choice either way; forcing raster on a non-uniform
    grid (or a vectorized one past the cell-count threshold) can drop a cell
    narrower than one output pixel, which warns naming it. ``alpha``/``label``
    match :meth:`imshow`.

``imshow(A, cmap="viridis", norm=None, vmin=None, vmax=None, extent=None, origin="upper", alpha=1.0, interpolation="nearest")``
    Display a 2-D (colormapped) or RGB(A) array. ``origin`` is ``"upper"`` or
    ``"lower"``; ``extent`` is ``(xmin, xmax, ymin, ymax)``. ``alpha`` blends
    into whatever is drawn underneath -- an artist drawn first, or pinned
    underneath via a lower ``zorder``, shows through rather than being fully
    covered. ``interpolation="nearest"`` (default) draws crisp pixel blocks
    however far the image is scaled; anything else lets the browser smooth
    it -- SVG output only, since raster (PNG/PDF) output already samples at
    its own fixed resolution.

``contour(*args, levels=8, colors=None, cmap="viridis", vmin=None, vmax=None, label=None, alpha=1.0)``
    Contour lines via marching squares: ``contour(Z)`` or ``contour(x, y, Z)``.
    ``levels`` is a count or an explicit sequence. Each level's color comes
    from its own *value*, normalized by ``vmin``/``vmax`` (default: ``Z``'s
    own min/max) -- the same normalization :meth:`pcolormesh`/``contourf``
    use, so non-uniform ``levels`` still get each one's true position on
    the scale, not just its rank among them. ``alpha`` now matches its own
    sibling ``contourf``, which already had it.

Vector fields
-------------

``quiver(X, Y, U, V, scale=None, color=None, label=None, alpha=1.0)``
    A field of arrows. ``scale`` maps ``(U, V)`` to data units (auto if ``None``).

Signal processing
-----------------

Welch-averaged spectral estimators (pure NumPy -- no SciPy). Each computes with
matplotlib's ``mlab`` conventions (Hann window, mean detrend, one-sided scaling)
and draws through an existing artist. ``NFFT``, ``Fs``, ``noverlap`` and
``window`` control the estimate; each also takes ``alpha`` (forwarded to
whichever artist it draws with -- a line for the spectra, an image for
``specgram``, stems/markers for ``xcorr``/``acorr``).

``psd(x, NFFT=256, Fs=2, noverlap=0, ...)`` / ``csd(x, y, ...)`` / ``cohere(x, y, ...)``
    Power / cross spectral density (in dB) and magnitude-squared coherence.
    Each returns ``(values, freqs, line)``.

``magnitude_spectrum(x, Fs=2, scale=None, ...)`` / ``angle_spectrum`` / ``phase_spectrum``
    Single-shot spectra of the whole signal. ``scale="dB"`` plots the magnitude
    in decibels. Return ``(spectrum, freqs, line)``.

``specgram(x, NFFT=256, Fs=2, noverlap=128, cmap="viridis", ...)``
    Spectrogram (power in dB) drawn with :meth:`imshow`. Returns
    ``(spectrum, freqs, t, image)``.

``xcorr(x, y, normed=True, maxlags=10, ...)`` / ``acorr(x, ...)``
    Lagged cross- / auto-correlation over ``+-maxlags``, drawn as stems plus
    markers. Return ``(lags, c, lines, markers)``.

Polar
-----

Create a polar axes with ``projection="polar"``; angles are in **radians**.

.. code-block:: python

   fig, ax = plotpress.subplots(projection="polar")
   theta = np.linspace(0, 2 * np.pi, 400)
   ax.plot(theta, 1 + 0.5 * np.sin(5 * theta))
   ax.set_rmax(1.6)

``plot(theta, r, ...)`` / ``scatter(theta, r, ...)`` / ``fill(theta, r, ...)``
    The polar-aware plot types. Orientation is set with
    ``set_theta_zero_location("N")`` and ``set_theta_direction(-1)`` *before*
    plotting; radial extent with ``set_rmax``/``set_rlim``/``set_rticks`` and the
    spokes with ``set_thetagrids``.

3-D
---

Create a 3-D axes with ``projection="3d"``; set the camera with
``view_init(elev=, azim=)``.

.. code-block:: python

   fig, ax = plotpress.subplots(projection="3d")
   X, Y = np.meshgrid(np.linspace(-3, 3, 60), np.linspace(-3, 3, 60))
   ax.plot_surface(X, Y, np.sin(np.hypot(X, Y)), cmap="viridis")
   ax.set_zlabel("z")

``scatter(xs, ys, zs, ...)`` / ``plot(xs, ys, zs, ...)``
    3-D points and polylines (also ``scatter3D`` / ``plot3D``).

``plot_surface(X, Y, Z, cmap="viridis", edgecolor=None, ...)``
    Depth-sorted colormapped surface. The returned collection works with
    :meth:`~plotpress.figure.Figure.colorbar`.

``plot_wireframe(X, Y, Z, color=None, ...)``
    Grid wireframe.

The camera and per-axis scaling are honest orthographic projection with a
painter's-algorithm surface -- see :ref:`the 3-D caveats <limitation-3d>`.

Text and annotations
--------------------

``text(x, y, s, color=None, fontsize=None, ha="left", va="baseline", rotation=0.0, outline=None, alpha=1.0, bbox=None, fontweight="normal", fontstyle="normal", transform=None)``
    Text anchored at data coordinates. ``ha`` in ``left/center/right``; ``va``
    in ``baseline/center/top/bottom``. ``alpha`` fades the glyphs themselves.
    ``s`` may contain ``\n`` for a multi-line label -- each line is aligned
    independently per ``ha``, the block as a whole placed per ``va``.

    ``outline`` is a halo drawn behind the glyphs so the label survives landing
    on a series, a mesh cell or a filled band -- which is decided long after the
    label is placed. The default picks white behind dark ink and black behind
    light; over a plain background it is invisible. ``outline=False`` switches
    it off, and a colour chooses your own. Titles, axis labels and tick labels
    never get one: they sit outside the data area.

    ``bbox`` is a different tool: a filled/bordered box *behind* the label
    (matplotlib's own ``bbox=`` dict, a subset of its keys --
    ``facecolor``/``fc``, ``edgecolor``/``ec``, ``alpha``, ``pad``,
    ``boxstyle`` of ``"square"``/``"round"``, ``linewidth``). Pass ``{}`` for
    the defaults. Where ``outline`` keeps a label legible, ``bbox`` reads as a
    callout chip; the two can combine, or either can be used alone.

    ``fontweight`` (``"normal"``/``"bold"``, or any matplotlib weight name/
    number -- ``>= 600`` counts as bold) and ``fontstyle`` (``"normal"``/
    ``"italic"``/``"oblique"``) select the glyph face, on both backends
    (raster has no italic font file, so it fakes the slant with a shear).

    ``transform=ax.transAxes`` places ``(x, y)`` as an axes-fraction position
    -- ``(0, 0)`` the axes' bottom-left corner, ``(1, 1)`` its top-right --
    instead of data coordinates, so a label stays put under autoscaling,
    panning, or a data zoom::

        ax.text(0.95, 0.95, "top right", transform=ax.transAxes,
                ha="right", va="top")

``annotate(text, xy, xytext=None, color=None, fontsize=None, ha="left", va="baseline", arrowprops=None, outline=None, alpha=1.0, bbox=None, fontweight="normal", fontstyle="normal", textcoords=None)``
    Text at ``xytext`` optionally pointing an arrow to ``xy`` (pass
    ``arrowprops={"color": ...}`` or ``{}`` to draw the arrow; ``arrowprops``
    also accepts ``alpha``, independent of the text's own). The leader
    leaves the text's bounding box at the point nearest ``xy``, preferring the
    middle of an edge, so it never crosses the label it belongs to -- with
    ``bbox`` set, that edge is the box's own padded edge, so the leader
    visibly touches the box instead of stopping short of it. Multi-line
    ``text``, ``fontweight``, and ``fontstyle`` all match :func:`text`.

    ``textcoords=ax.transAxes`` places ``xytext`` as an axes-fraction position
    while the arrow still points at the data coordinate ``xy`` -- a callout
    pinned to a corner regardless of where its data ends up after a pan or
    zoom. ``xy`` itself always stays data coordinates.

Animated data (sliders)
-----------------------

``plot_frames(x, Y, slider_values=None, slider_label="frame", shared=True, slider_group=None, ...)``
    Plot 3-D data ``Y`` of shape ``(n_frames, n_points)`` as a line with a
    **slider** over the extra dimension (interactive output only). ``shared=True``
    joins the figure's global slider; ``shared=False`` gives this axes its own
    docked slider, and ``slider_group`` lets several be linked. See
    :doc:`interactivity`.
