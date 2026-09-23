"""The shared scene/geometry layer every backend renders from.

``artists.py`` holds data, not geometry (``Line2D``, ``Bars``, ``QuadMesh``,
...); ``primitives.py``'s ``artist_to_prims()`` converts an artist plus a
``transform.py`` ``LinearTransform`` into backend-agnostic pixel-space prims
(``Path``, ``Markers``, ...) that ``svg.py``/``raster.py``/``vega.py`` then
each emit in their own format. No re-exports here -- import the submodule you
need directly, e.g. ``from plotpress.core.artists import Line2D``.
"""
