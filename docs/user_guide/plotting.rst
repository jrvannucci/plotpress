Plotting methods
================

Every plot type is a method on :class:`~plotpress.axes.Axes`. Signatures mirror
matplotlib. See the :ref:`gallery <gallery>` for a rendered example of each.

Lines and areas
---------------

``plot(*args, color=None, linewidth=None, linestyle="-", label=None, alpha=1.0)``
    Line plot of ``y`` or ``x, y``. ``linestyle`` is ``"-"``, ``"--"``, ``":"``
    or ``"-."``. Colors auto-advance through the per-axes cycle.

    .. code-block:: python

       ax.plot(x, np.sin(x), label="sin")
       ax.plot(x, np.cos(x), linestyle="--")

``step(x, y, where="pre", color=None, linewidth=None, label=None, alpha=1.0)``
    Staircase line. ``where`` is ``"pre"``, ``"post"`` or ``"mid"``.

``fill_between(x, y1, y2=0.0, color=None, alpha=0.4, label=None)``
    Shade the area between ``y1`` and ``y2`` (scalar or array).

``stackplot(x, *ys, colors=None, alpha=0.8, labels=None)``
    Stacked filled areas.

``axvline(x, color=None, linewidth=None, linestyle="--", label=None, alpha=1.0)``
    A vertical reference line at data ``x`` (does not affect autoscaling).

Markers
-------

``scatter(x, y, s=None, c=None, color=None, marker="o", label=None, alpha=1.0, cmap="viridis", norm=None, vmin=None, vmax=None)``
    Scattered points. Pass ``c`` (an array) with ``cmap`` to color points by a
    third variable; ``s`` is the marker diameter in points. Markers stay a
    constant on-screen size under interactive zoom -- which is why only **round**
    markers are drawn: they are emitted as round-capped zero-length strokes, and
    a polygonal marker would have to scale with the zoom instead. ``marker`` is
    accepted for matplotlib compatibility and warns for any other shape;
    distinguish series by color, size or a label instead.

    .. code-block:: python

       ax.scatter(x, y, c=x**2 + y**2, cmap="plasma", s=12)

Bars and histograms
-------------------

``bar(x, height, width=0.8, bottom=0.0, color=None, edgecolor=None, linewidth=0.8, label=None, alpha=1.0)``
    Vertical bars. ``barh(y, width, height=0.8, left=0.0, ...)`` is the
    horizontal form.

``hist(data, bins=10, range=None, color=None, edgecolor="#ffffff", label=None, alpha=1.0, density=False)``
    Histogram. Returns ``(counts, edges, bars)``.

``hist2d(x, y, bins=20, range=None, cmap="viridis")``
    2-D histogram rendered as an image. Returns ``(counts, image)`` -- pass the
    image to :meth:`~plotpress.figure.Figure.colorbar`.

Statistical
-----------

``boxplot(data, positions=None, widths=0.5, color=None, orientation="vertical", label=None)``
    Box-and-whisker plot; ``data`` is a sequence of arrays. Whiskers use the
    1.5x IQR rule and outliers are drawn as open circles.

``violinplot(data, positions=None, widths=0.5, color=None, orientation="vertical", label=None, points=100)``
    Kernel-density "violin" silhouettes (Gaussian KDE, Silverman bandwidth).

``errorbar(x, y, yerr=None, xerr=None, color=None, marker="o", markersize=None, capsize=3.0, linestyle="-", linewidth=None, label=None, alpha=1.0)``
    Line/markers with x and/or y error bars and caps.

``eventplot(positions, lineoffsets=None, linelengths=0.8, color=None, orientation="horizontal", label=None)``
    Raster of event ticks, one row per sequence.

``pie(values, labels=None, colors=None, startangle=90.0, radius=1.0)``
    Pie chart. Automatically hides the axis and fixes an equal-aspect square.

2-D fields
----------

``pcolormesh(*args, cmap="viridis", norm=None, vmin=None, vmax=None)``
    Rectilinear pseudocolor mesh: ``pcolormesh(C)`` or ``pcolormesh(X, Y, C)``.
    Rasterized to a single embedded image, so grid size costs no DOM nodes.

``imshow(A, cmap="viridis", norm=None, vmin=None, vmax=None, extent=None, origin="upper", alpha=1.0)``
    Display a 2-D (colormapped) or RGB(A) array. ``origin`` is ``"upper"`` or
    ``"lower"``; ``extent`` is ``(xmin, xmax, ymin, ymax)``.

``contour(*args, levels=8, colors=None, cmap="viridis", label=None)``
    Contour lines via marching squares: ``contour(Z)`` or ``contour(x, y, Z)``.
    ``levels`` is a count or an explicit sequence.

Vector fields
-------------

``quiver(X, Y, U, V, scale=None, color=None, label=None)``
    A field of arrows. ``scale`` maps ``(U, V)`` to data units (auto if ``None``).

Signal processing
-----------------

Welch-averaged spectral estimators (pure NumPy -- no SciPy). Each computes with
matplotlib's ``mlab`` conventions (Hann window, mean detrend, one-sided scaling)
and draws through an existing artist. ``NFFT``, ``Fs``, ``noverlap`` and
``window`` control the estimate.

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

``text(x, y, s, color=None, fontsize=None, ha="left", va="baseline", rotation=0.0)``
    Text anchored at data coordinates. ``ha`` in ``left/center/right``; ``va``
    in ``baseline/center/top/bottom``.

``annotate(text, xy, xytext=None, color=None, fontsize=None, ha="left", va="baseline", arrowprops=None)``
    Text at ``xytext`` optionally pointing an arrow to ``xy`` (pass
    ``arrowprops={"color": ...}`` or ``{}`` to draw the arrow).

Animated data (sliders)
-----------------------

``plot_frames(x, Y, slider_values=None, slider_label="frame", shared=True, slider_group=None, ...)``
    Plot 3-D data ``Y`` of shape ``(n_frames, n_points)`` as a line with a
    **slider** over the extra dimension (interactive output only). ``shared=True``
    joins the figure's global slider; ``shared=False`` gives this axes its own
    docked slider, and ``slider_group`` lets several be linked. See
    :doc:`interactivity`.
