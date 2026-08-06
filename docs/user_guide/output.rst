Saving and showing
==================

A figure knows how to serialize itself -- no backend selection, no globals.

``fig.save(path, interactive=False, scale=2)``
    Save by file extension:

    ==========  =========================================================
    Extension   Output
    ==========  =========================================================
    ``.svg``    static vector SVG
    ``.html``   interactive HTML (pass ``interactive=True``)
    ``.png``    raster PNG, supersampled by ``scale``
    ``.pdf``    vector PDF (svglib + reportlab)
    ==========  =========================================================

    .. code-block:: python

       fig.save("figure.svg")
       fig.save("figure.png", scale=3)          # higher-res raster
       fig.save("figure.html", interactive=True)

``fig.savefig(path, **kwargs)``
    matplotlib-compatible alias for :meth:`~plotpress.figure.Figure.save`.

Strings and Jupyter
-------------------

``fig.to_svg()``
    Return the SVG document as a string.

``fig.to_html(interactive=True, wait_extract=False, pick_precision=6, pick_max_mesh_cells=60000, pick_max_points=20000)``
    Return a self-contained interactive HTML string. ``pick_precision`` sets
    the decimal places embedded per point-pick value; ``pick_max_mesh_cells``/
    ``pick_max_points`` cap how much of each mesh's/series' own data is
    embedded for picking, *per artist* -- so a figure with many mesh-bearing
    axes does not multiply the default cap by the axes count. A mesh over the
    cap is block-averaged down to it rather than dropped, so a click still
    answers with a real, if coarser, value; a series over the point cap falls
    back to a geometry-only x/y readout. ``fig.save(..., interactive=True)``
    accepts the same three kwargs.

``fig._repr_svg_()``
    Inline SVG rendering in Jupyter (used automatically).

Native window
-------------

``fig.show(interactive=True, wait_for_extract=False)``
    Open the figure in a native pop-up window via pywebview / WebView2 (the
    ``[gui]`` extra: ``pip install plotpress[gui]``). Falls back to the default
    browser if pywebview is not installed.

    With ``wait_for_extract=True`` the call blocks until the user clicks
    **Extract** in the window, which returns the picked markers/annotations to
    the kernel and closes the window:

    .. code-block:: python

       markers = fig.show(wait_for_extract=True)   # list of dicts

See :doc:`interactivity` for the in-window toolbar and extraction format.

Export dependencies
-------------------

PNG/PDF export uses pure-wheel packages (no cairo) that ship with the standard
install: **Pillow** (PNG raster backend) and **svglib + reportlab** (vector PDF).
