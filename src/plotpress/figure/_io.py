"""The data round-trip's load side: `load_data()`/`load_data_xarray()`/
`load_template()`/`select_panel()` recover plotted data and template dicts
from a saved interactive HTML file -- plain arrays/dicts, not a rebuilt
`Figure` (that's `_template.py`'s `figure_from_template()`, which a caller
chains on separately) -- so this needs nothing from `_core`.
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import time
import warnings
from numbers import Integral

import numpy as np

from ..core.artists import normalize_bbox, normalize_linestyle
from ..axes import Axes
from ..polar import PolarAxes
from ..style import Style
from ..backends.svg import figure_to_svg

def _decode_binary_arrays(obj):
    """Reverse :func:`_encode_binary_arrays`: a ``{"__f32__": b64}``/
    ``{"__f16__": b64}`` leaf becomes a real ``numpy`` array; everything else
    is walked unchanged. float16 decodes via ``numpy``'s native dtype (exact,
    unlike the JS side's hand-rolled ``halfToFloat`` -- there is no
    ``Float16Array`` in a browser, but Python has no such gap).
    """
    if isinstance(obj, dict):
        if set(obj) == {"__f32__"}:
            return np.frombuffer(base64.b64decode(obj["__f32__"]), dtype=np.float32)
        if set(obj) == {"__f16__"}:
            return np.frombuffer(base64.b64decode(obj["__f16__"]),
                                 dtype=np.float16).astype(np.float64)
        return {k: _decode_binary_arrays(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_binary_arrays(v) for v in obj]
    return obj


def _expand_columnar_meta(payload):
    """Reverse :func:`_columnarize_meta`: ``{"cols", "index", "keys"}`` (one
    array per field) back to ``{axes_index: {field: value, ...}, ...}``. A
    plain (non-columnarized) meta payload -- ``binary_pick_data=False`` never
    columnarizes -- is returned unchanged.
    """
    if not (isinstance(payload, dict)
            and {"cols", "index", "keys"} <= set(payload)):
        return payload
    cols, index, keys = payload["cols"], payload["index"], payload["keys"]
    return {i: {k: cols[k][pos] for k in keys} for pos, i in enumerate(index)}


def _extract_json_block(text, element_id):
    """The parsed JSON body of ``<script type="application/json" id="...">``,
    or ``None`` if that element isn't in ``text`` at all."""
    m = re.search(
        r'<script type="application/json" id="%s">(.*?)</script>' % re.escape(element_id),
        text, re.DOTALL)
    return json.loads(m.group(1)) if m else None


def _mesh_centers(mesh):
    """1-D cell-center coordinate arrays for a ``pick_data()`` mesh entry, or
    ``(None, None)`` for a curvilinear (warped) mesh, which has no separable
    per-axis coordinates -- only per-cell ``xc``/``yc`` centers.
    """
    if mesh.get("curvilinear"):
        return None, None
    if "xcoord" in mesh:
        # A contour's samples: the exact coordinate, not an edge midpoint --
        # see pick_data()'s own contour branch for why those can differ.
        return (np.asarray(mesh["xcoord"], dtype=float),
                np.asarray(mesh["ycoord"], dtype=float))
    xe = np.asarray(mesh["xedges"], dtype=float)
    ye = np.asarray(mesh["yedges"], dtype=float)
    return (xe[:-1] + xe[1:]) / 2.0, (ye[:-1] + ye[1:]) / 2.0


def _load_single_figure(text):
    """Every plotted axes' data out of one figure's own interactive HTML."""
    pick = _extract_json_block(text, "plotpress-pick")
    if pick is None:
        raise ValueError(
            "no embedded plot data found -- load_data() only works on HTML "
            "saved with interactive=True (Figure.to_html()/save(..., "
            "interactive=True) or Report.save()); a static SVG or "
            "interactive=False HTML embeds only drawn shapes, nothing to "
            "read back")
    pick = {int(k): v for k, v in _decode_binary_arrays(pick).items()}
    meta_raw = _extract_json_block(text, "plotpress-meta") or {}
    meta = _expand_columnar_meta(_decode_binary_arrays(meta_raw))
    meta = {int(k): v for k, v in meta.items()}

    axes = {}
    for i in sorted(set(pick) | set(meta)):
        entry = pick.get(i, {"series": [], "meshes": [], "pies": []})
        m = meta.get(i, {})
        series = []
        for s in entry.get("series", []):
            series.append({
                "kind": s.get("kind"),
                "x": np.asarray(s["x"], dtype=float),
                "y": np.asarray(s["y"], dtype=float),
                "vals": {k: np.asarray(v, dtype=float)
                        for k, v in s.get("vals", {}).items()},
                # None for a file saved before these existed, or a series
                # kind (box/violin/quiver/event/contour) that never carried
                # one meaningful color/label to begin with.
                "label": s.get("label"), "color": s.get("color"),
            })
        meshes = []
        for msh in entry.get("meshes", []):
            ny, nx = msh["shape"]
            z = np.asarray(msh["z"], dtype=float).reshape(ny, nx)
            xc, yc = _mesh_centers(msh)
            meshes.append({
                "x": xc, "y": yc, "z": z,
                "extent": tuple(msh["extent"]),
                "curvilinear": bool(msh.get("curvilinear", False)),
            })
        axes[i] = {
            "series": series, "meshes": meshes, "pies": entry.get("pies", []),
            "title": m.get("title"), "xlabel": m.get("xlabel"),
            "ylabel": m.get("ylabel"), "zlabel": m.get("zlabel"),
            "xlim": (m["xmin"], m["xmax"]) if "xmin" in m else None,
            "ylim": (m["ymin"], m["ymax"]) if "ymin" in m else None,
            "xscale": m.get("xscale"), "yscale": m.get("yscale"),
        }
    return axes


def _load_template(text):
    """The ``plotpress-layout`` block (see ``svg.template_metadata`` -- the
    HTML tag keeps this internal id regardless of the Python-facing rename,
    since every already-saved file on disk has its real data under it), or
    the empty template a figure with no grid-placed axes and no groups
    would embed -- older files saved before this block existed, or before
    it carried the full template shape, fall back to (or are padded out
    with) the same empty defaults rather than raising or coming back
    partial, so ``load_data()`` keeps working on them.
    """
    raw = _extract_json_block(text, "plotpress-layout")
    if raw is None:
        return {"figsize": None, "axes": {}, "groups": [], "omitted_axes": [],
                "suptitle": None, "supxlabel": None, "supylabel": None,
                "facecolor": None, "style": None, "overlays": [], "insets": [],
                "colorbars": []}
    return {"style": None, "overlays": [], "insets": [], "colorbars": [],
           **raw, "axes": {int(k): v for k, v in raw["axes"].items()}}


def _split_report_entries(text):
    """One chunk of HTML per :class:`Report` entry, each starting at its
    ``plotpress-report-label`` div (always present, unlike the optional title/
    details) -- avoids needing to balance nested ``<div>`` tags with regex,
    which a proper (non-regular) HTML parse would need otherwise.
    """
    return text.split('<div class="plotpress-report-label">')[1:]


def _dedupe_keyed(pairs, noun, stacklevel):
    """Build a dict from ``[(key, item), ...]`` pairs (already in the order
    they should be tried), disambiguating any collision with a
    ``"<key> (2)"``, ``"<key> (3)"``, ... suffix -- rather than silently
    letting a later item overwrite, and lose, an earlier one that resolves
    to the identical key. Two axes (or two Report entries) sharing an
    explicit title is realistic authoring, not exotic input worth crashing
    or staying silent about -- a grid of identically-labeled panels, a
    report re-using a section name -- the same "accept it, don't crash,
    but don't stay silent" choice :func:`plotpress.artists.normalize_linestyle`
    already makes for an unrecognized linestyle. Warns once, naming every
    collision resolved, rather than the caller discovering a shorter dict
    than they expected with no signal why.

    ``noun`` is ``(singular, plural)`` (e.g. ``("figure", "figures")``),
    so the one-collision case reads naturally instead of always using the
    plural form regardless of count.
    """
    keyed = {}
    collisions = []
    for base, item in pairs:
        key, n = base, 2
        while key in keyed:
            key = f"{base} ({n})"
            n += 1
        if key != base:
            collisions.append((base, key))
        keyed[key] = item
    if collisions:
        singular, plural = noun
        word = singular if len(collisions) == 1 else plural
        detail = ", ".join(f"{b!r} -> {k!r}" for b, k in collisions)
        warnings.warn(
            f"load_data(): {len(collisions)} {word} shared a title with "
            f"another already-keyed one -- disambiguated ({detail}) so every "
            "one stays recoverable instead of a later one silently "
            "overwriting an earlier one with the same key. Pass "
            "by_index=True for a stable, collision-free key instead.",
            UserWarning, stacklevel=stacklevel)
    return keyed


def _title_keyed_axes(axes):
    """Re-key an int-indexed axes dict by each axes' own title, falling back
    to ``"axes {i}"`` when it has none -- the same fallback a picked record's
    ``axes_title`` already uses (see ``_interactive.py``'s
    ``resolvePickTarget``), so both surfaces name an untitled axes the same
    way. Two axes sharing an explicit title is disambiguated, not silently
    collapsed to one -- see :func:`_dedupe_keyed`.
    """
    pairs = [(axes[i].get("title") or f"axes {i}", axes[i]) for i in sorted(axes)]
    return _dedupe_keyed(pairs, ("axes", "axes"), stacklevel=4)


def load_template(path: str) -> dict:
    """Read back a :meth:`Figure.save_template` file: plain JSON, no HTML
    parsing involved, unlike :func:`load_data`. Pass the result to
    :func:`figure_from_template` to rebuild the figure it describes.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(path: str, by_index: bool = False):
    """Read back the plotted data embedded in a self-contained interactive
    HTML file written by :meth:`Figure.to_html`/:meth:`Figure.save` or
    :meth:`Report.save`.

    By default, returns a dict keyed by each figure's own title (a
    :class:`Report` entry's :meth:`Report.add` title; a generated
    ``"Figure N"`` -- 1-based, matching the label a :class:`Report` page
    itself shows -- for an entry with none, or for a bare :class:`Figure`'s
    HTML, which has no report-level title at all). Each figure's own value
    has ``"details"`` (a `Report` entry's longer description, or ``None``)
    ``"axes"`` (itself a dict keyed by each axes' own title, falling back to
    ``"axes {index}"`` -- matching a picked record's ``axes_title`` fallback
    -- for an untitled one), and ``"template"``::

        {"series": [{"kind": "line", "x": array, "y": array,
                    "vals": {name: array, ...},
                    "label": str | None, "color": str | None}, ...],
         "meshes": [{"x": array,          # 1-D cell centers (None if curvilinear)
                     "y": array,          # 1-D cell centers (None if curvilinear)
                     "z": array,          # 2-D, shape (ny, nx), row 0 = ymin
                     "extent": (xmin, xmax, ymin, ymax),
                     "curvilinear": bool}, ...],
         "pies": [...],
         "title": str | None, "xlabel": str | None, "ylabel": str | None,
         "zlabel": str | None, "xlim": (float, float) | None,
         "ylim": (float, float) | None, "xscale": str, "yscale": str}

    A series' ``"label"``/``"color"`` are the artist's own ``label=``/
    (single, resolved) ``color=`` at save time -- ``None`` for a file saved
    before these existed, an unlabeled/uncolored series, a
    colormap-mapped ``scatter(c=...)`` (no one color to report), or a kind
    with no single meaningful color/label at all (box/violin/quiver/event/
    contour). Real for ``"line"``/``"scatter"``/``"stem"``/``"errorbar"``/
    ``"bar"``, which is enough to rebuild a labeled, colored legend after
    replotting recovered data -- see
    :func:`~plotpress.figure_from_template`.

    ``"template"`` is the figure-level structure and styling -- grid
    shape/position, every decoration (title, labels, limits, scale, ...),
    spine colors, tick overrides, and id of each subplot-grid axes, any
    :meth:`Figure.group` boxes, twin/secondary/inset overlays, colorbar
    styling, this figure's own :class:`~plotpress.style.Style`, and its
    sup-title/label -- needed to rebuild an equivalent, already-styled
    figure, independent of the per-axes data above. This is the exact same
    dict :meth:`Figure.to_template` produces (see
    :func:`plotpress.svg.template_metadata` for the full field-by-field
    breakdown) -- pass it straight to :func:`plotpress.figure_from_template`
    to recreate the source figure's grid, every axes' own decorations and
    styling, its groups, and its overlays, before replotting recovered
    data into it -- see :doc:`/auto_examples/data_roundtrip/index`. A file
    saved before 3-D support was removed can still report the literal
    ``"3d"`` here (this function only reads back whatever string was
    stored, it doesn't validate it) -- :func:`figure_from_template` raises
    a clear "unknown projection" for that one, since it cannot rebuild an
    axes kind that no longer exists.

    Axes placed with a freeform :meth:`Figure.add_axes` rect (no grid
    cell) and colorbar axes are absent from ``"axes"`` -- their indices
    are listed in ``"omitted_axes"`` instead -- and a group's own
    ``"n_members"`` is its *original* member count, before any
    unrecoverable member was filtered out of its ``"axes"`` list, so a
    caller can tell a group that lost one apart from one that didn't.
    ``"legend"`` is recorded but not auto-applied by
    ``figure_from_template`` -- see that function's own docstring for why.
    A file saved before this block existed loads as
    ``{"figsize": None, "axes": {}, "groups": [], "omitted_axes": [],
    "suptitle": None, "supxlabel": None, "supylabel": None, "facecolor": None,
    "style": None, "overlays": [], "insets": [], "colorbars": []}``, and one
    saved by an in-between version (before some of these fields existed)
    has the same empty defaults padded in for whichever it predates.

    Title keys are convenient but not guaranteed unique -- two figures (or
    two axes within one figure) sharing the same title no longer collide
    silently: the later one is disambiguated with a ``" (2)"``, ``" (3)"``,
    ... suffix rather than overwriting (and losing) the earlier one, and a
    ``UserWarning`` names every collision resolved this way. Pass
    ``by_index=True`` when even that renaming matters, or when a stable,
    order-based key is simply more useful than a name: this returns a list
    of per-figure dicts instead (one per figure embedded in the file, in
    the order they appear -- a bare figure's HTML still comes back as a
    one-item list), each with the same ``"title"``/``"details"``/``"axes"``/
    ``"template"`` shape as above except ``"axes"`` is keyed by plain integer
    index rather than title -- and never renamed, since there is no title
    collision to resolve when the key is a position instead of a name.

    Only works on HTML saved with ``interactive=True``: a static SVG or an
    ``interactive=False`` HTML embeds no data to read back, only drawn
    shapes, and raises ``ValueError``. Recovered arrays reflect whatever
    precision/caps were in effect at save time (``pick_precision``,
    ``pick_max_points``, ``pick_max_mesh_cells``) -- they are not guaranteed
    bit-exact copies of the original data for a series/mesh that was rounded
    or capped on the way out. A mesh that crossed ``pick_max_mesh_cells`` at
    save time comes back at that coarser, block-averaged resolution, not the
    original grid's -- see :meth:`Figure.to_html`'s own docstring for
    exactly what that averaging costs.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # A Report entry saved with collapsed=True carries its document in
    # data-lazy-doc="..." instead of a live srcdoc="..." (see _REPORT_SCRIPT's
    # own comment on why) -- checked as a real second case by attribute name,
    # not left to the substring coincidence of a name that simply happens to
    # still contain "srcdoc=".
    if 'srcdoc="' not in text and 'data-lazy-doc="' not in text:
        figures = [{"title": None, "details": None, "axes": _load_single_figure(text),
                    "template": _load_template(text)}]
    else:
        figures = []
        for chunk in _split_report_entries(text):
            doc_m = (re.search(r'srcdoc="(.*?)"', chunk, re.DOTALL)
                    or re.search(r'data-lazy-doc="(.*?)"', chunk, re.DOTALL))
            if not doc_m:
                continue
            title_m = re.search(r"<h2>(.*?)</h2>", chunk, re.DOTALL)
            details_m = re.search(
                r'<p class="plotpress-report-details">(.*?)</p>', chunk, re.DOTALL)
            doc = html.unescape(doc_m.group(1))
            figures.append({
                "title": html.unescape(title_m.group(1)) if title_m else None,
                "details": html.unescape(details_m.group(1)) if details_m else None,
                "axes": _load_single_figure(doc),
                "template": _load_template(doc),
            })

    if by_index:
        return figures

    pairs = [(entry["title"] or f"Figure {n}", entry)
            for n, entry in enumerate(figures, start=1)]
    keyed = _dedupe_keyed(pairs, ("figure", "figures"), stacklevel=3)
    return {key: {**entry, "axes": _title_keyed_axes(entry["axes"])}
           for key, entry in keyed.items()}


def load_data_xarray(path: str, figure=None):
    """Read one figure's plotted data back as a single ``xarray.Dataset``,
    dimensioned by the figure's own axes grid (``row``/``col``, from the
    same layout :func:`load_data` already returns) instead of
    :func:`load_data`'s title-keyed dict of dicts.

    Needs the optional ``xarray`` dependency: ``pip install
    plotpress[xarray]``.

    Built for the case :doc:`/auto_examples/data_roundtrip/index` already
    showcases -- a uniform grid of same-shaped scientific measurements
    (every panel its own ``pcolormesh``, or its own single line series) --
    where a title-keyed dict of dicts is the wrong tool entirely: a caller
    wanting "the z value at row 2, column 3" has to already know that
    panel's title (or fall back to :func:`load_data`'s own
    ``by_index=True``, still just a flat list with no row/column
    structure of its own), loop over every panel by hand to stack them
    into one array, and hope no two panels happened to share a title --
    see :func:`load_data`'s own now-fixed collision handling, which this
    sidesteps structurally rather than by disambiguating: xarray indexes
    by integer row/column position, never by a string title, so there is
    no title to collide on in the first place.

    Only supports a *uniform* rectangular grid -- every axes a single,
    non-spanning cell (as :func:`plotpress.subplots`/:meth:`Figure.add_subplot`
    place them, never a row/column span from ``add_gridspec``) -- where
    every axes with data carries **exactly one** mesh (all the same shape,
    non-curvilinear) or **exactly one** line series (all the same length),
    never a mix of the two kinds, and never more than one series/mesh on a
    single axes. A cell with no axes at all, or an axes nothing was ever
    plotted on, is fine -- it comes back NaN (its ``x``/``y`` too, in the
    per-panel-coordinate case), distinguished from a panel whose real data
    legitimately happened to be all-NaN by the ``has_data`` coordinate
    below. Raises ``ValueError``, naming exactly what about the figure
    didn't fit, for anything else -- a mixed grid, a span, multiple series
    per axes, differing mesh shapes -- pointing at :func:`load_data`
    (``by_index=True`` for the title-collision-proof form) as the fallback
    for a figure this doesn't cover.

    The returned ``Dataset`` has ``row``/``col`` coordinates plus each
    panel's own ``title``/``xlabel``/``ylabel`` (``""`` for a missing
    panel) and ``has_data`` (``True`` for a grid cell an axes with plotted
    data actually occupies, ``False`` for one with no axes or nothing
    plotted) as ``(row, col)`` coordinates; a mesh grid's ``x``/``y`` are
    shared 1-D coordinates when every panel used the identical grid, else
    per-panel ``(row, col, x)``/``(row, col, y)`` arrays -- and its data
    variable is ``z``, dimensioned ``(row, col, y, x)``. A line grid's data
    variable is ``y``, dimensioned ``(row, col, point)``, with ``x`` the
    same shared-or-per-panel choice. ``.attrs`` carries the recovered
    figure's own ``figsize`` and title, plus ``"template"`` -- the exact
    same dict :func:`load_data` returns under that key, ready to pass
    straight to :func:`figure_from_template` without a second, separate
    :func:`load_data` call just to get it -- ``ds.attrs["template"]``, not
    a duplicate parse of the file.

    ``figure`` selects which figure to load from a multi-figure
    :class:`Report` file -- an int index (0-based, save order) or the
    exact string title a :class:`Report` entry was given. Left as
    ``None`` (the default), the file must have exactly one figure, or
    this raises naming how many it actually found.
    """
    try:
        import xarray as xr
    except ImportError as e:
        raise ImportError(
            "load_data_xarray() needs the optional xarray dependency -- "
            "install it with: pip install plotpress[xarray]"
        ) from e

    figures = load_data(path, by_index=True)
    if figure is None:
        if len(figures) != 1:
            raise ValueError(
                f"load_data_xarray(): this file has {len(figures)} figures, "
                "not 1 -- pass figure=<int index> or figure=<exact title "
                "str> to pick one (plotpress.load_data(path, by_index=True) "
                "lists every figure this file has, each with its own "
                "\"title\")."
            )
        entry = figures[0]
    elif isinstance(figure, int):
        try:
            entry = figures[figure]
        except IndexError:
            raise ValueError(
                f"load_data_xarray(): figure index {figure} out of range -- "
                f"this file has {len(figures)} figure(s)."
            ) from None
    else:
        matches = [f for f in figures if f["title"] == figure]
        if not matches:
            raise ValueError(
                f"load_data_xarray(): no figure titled {figure!r} in this "
                f"file -- available titles: {[f['title'] for f in figures]!r}"
            )
        entry = matches[0]

    axes = entry["axes"]   # int-indexed (this came from by_index=True above)
    template_axes = entry["template"].get("axes") or {}
    order = sorted(axes)
    if not order:
        raise ValueError("load_data_xarray(): this figure has no plotted axes.")
    missing_template = [i for i in order if i not in template_axes]
    if missing_template:
        raise ValueError(
            f"load_data_xarray(): axes {missing_template} have plotted data "
            "but no recorded grid cell (a freeform Figure.add_axes() rect, "
            "not a subplot grid cell) -- a uniform subplot grid is required; "
            "use plotpress.load_data() instead for this figure."
        )

    specs = [template_axes[i] for i in order]
    if len({(s["nrows"], s["ncols"]) for s in specs}) != 1:
        raise ValueError(
            "load_data_xarray(): this figure's axes don't share one "
            "nrows x ncols grid shape -- not a uniform grid; use "
            "plotpress.load_data() instead."
        )
    if not all(s["row0"] == s["row1"] and s["col0"] == s["col1"] for s in specs):
        raise ValueError(
            "load_data_xarray(): a row/column span (from add_gridspec) is "
            "not a single grid cell -- not supported; use "
            "plotpress.load_data() instead."
        )
    nrows, ncols = specs[0]["nrows"], specs[0]["ncols"]

    # `order` is every axes the grid actually has, whether or not anything
    # was ever plotted on it (an empty axes still reports "" series/meshes/
    # pies, not an absent entry) -- `filled` narrows that to the ones with
    # real data, which is what the kind/shape checks and every data array
    # below care about. title/xlabel/ylabel below still read from `order`,
    # not `filled` -- an otherwise-empty panel can carry a real title.
    kinds = set()
    filled = []
    for i in order:
        a = axes[i]
        n_series, n_meshes, n_pies = len(a["series"]), len(a["meshes"]), len(a["pies"])
        if n_meshes == 0 and n_series == 0 and n_pies == 0:
            continue   # nothing plotted here -- a missing panel, not an error
        elif n_meshes == 1 and n_series == 0 and n_pies == 0:
            kinds.add("mesh"); filled.append(i)
        elif n_series == 1 and n_meshes == 0 and n_pies == 0:
            kinds.add("line"); filled.append(i)
        else:
            raise ValueError(
                f"load_data_xarray(): axes {i} ({a['title']!r}) has "
                f"{n_series} series, {n_meshes} mesh(es), {n_pies} pie(s) -- "
                "only a grid where every axes with data has exactly one "
                "mesh, or exactly one line series (never a mix, never more "
                "than one), is supported; use plotpress.load_data() instead."
            )
    if not filled:
        raise ValueError(
            "load_data_xarray(): this figure's grid has no plotted axes."
        )
    if len(kinds) != 1:
        raise ValueError(
            "load_data_xarray(): a mix of mesh axes and line-series axes "
            "in the same grid isn't supported; use plotpress.load_data() "
            "instead."
        )
    kind = kinds.pop()

    def grid_of(items, default="", dtype=object):
        # A cell no `items` entry ever touches (an axes with nothing
        # plotted, or no axes at all) keeps `default` rather than whatever
        # an object array happens to default-initialize to (None) --
        # title/xlabel/ylabel stay uniformly str either way, empty or not,
        # never a mix of "" and None.
        g = np.full((nrows, ncols), default, dtype=dtype)
        for i, v in items:
            s = template_axes[i]
            g[s["row0"], s["col0"]] = v
        return g

    # True for every grid cell an axes with plotted data actually occupies,
    # False for one with no axes at all or an axes nothing was ever plotted
    # on. Missing cells stay NaN in every numeric array below too (they're
    # pre-filled with NaN, and only cells in `filled` are ever written into)
    # -- has_data is what lets a caller tell "this panel is genuinely empty"
    # apart from "this panel's own data legitimately happened to be
    # all-NaN".
    has_data = grid_of([(i, True) for i in filled], default=False, dtype=bool)

    coords = {
        "title": (("row", "col"), grid_of([(i, axes[i]["title"] or "") for i in order])),
        "xlabel": (("row", "col"), grid_of([(i, axes[i]["xlabel"] or "") for i in order])),
        "ylabel": (("row", "col"), grid_of([(i, axes[i]["ylabel"] or "") for i in order])),
        "has_data": (("row", "col"), has_data),
    }
    attrs = {"figsize": entry["template"].get("figsize"), "title": entry["title"],
             "template": entry["template"]}

    if kind == "mesh":
        meshes = [axes[i]["meshes"][0] for i in filled]
        if any(m["curvilinear"] for m in meshes):
            raise ValueError(
                "load_data_xarray(): a curvilinear mesh (irregular per-cell "
                "x/y coordinates, no separable 1-D axes) isn't supported; "
                "use plotpress.load_data() instead."
            )
        shapes = {m["z"].shape for m in meshes}
        if len(shapes) != 1:
            raise ValueError(
                f"load_data_xarray(): meshes differ in shape across the "
                f"grid ({sorted(shapes)}) -- every panel must match; use "
                "plotpress.load_data() instead."
            )
        ny, nx = shapes.pop()
        # grid_of()'s own object-array shell doesn't fit here -- each cell
        # holds a whole 2-D mesh, not one scalar the way title/xlabel above
        # do -- so this one (nrows, ncols, ny, nx) float array is built
        # directly instead of routing through it.
        z = np.full((nrows, ncols, ny, nx), np.nan)
        for i, m in zip(filled, meshes):
            s = template_axes[i]
            z[s["row0"], s["col0"], :, :] = m["z"]

        x0, y0 = meshes[0]["x"], meshes[0]["y"]
        shared = all(np.array_equal(m["x"], x0) and np.array_equal(m["y"], y0)
                    for m in meshes)
        if shared:
            coords["x"] = ("x", x0)
            coords["y"] = ("y", y0)
            data_vars = {"z": (("row", "col", "y", "x"), z)}
        else:
            # NaN-filled, not np.empty()'s uninitialized garbage -- a
            # missing cell's own x/y has no data to report either.
            X = np.full((nrows, ncols, nx), np.nan)
            Y = np.full((nrows, ncols, ny), np.nan)
            for i, m in zip(filled, meshes):
                s = template_axes[i]
                X[s["row0"], s["col0"], :] = m["x"]
                Y[s["row0"], s["col0"], :] = m["y"]
            coords["x"] = (("row", "col", "x"), X)
            coords["y"] = (("row", "col", "y"), Y)
            data_vars = {"z": (("row", "col", "y", "x"), z)}
    else:
        series = [axes[i]["series"][0] for i in filled]
        lengths = {s["x"].size for s in series}
        if len(lengths) != 1:
            raise ValueError(
                f"load_data_xarray(): series differ in length across the "
                f"grid ({sorted(lengths)}) -- every panel must match; use "
                "plotpress.load_data() instead."
            )
        n = lengths.pop()
        y = np.full((nrows, ncols, n), np.nan)
        for i, s in zip(filled, series):
            spec = template_axes[i]
            y[spec["row0"], spec["col0"], :] = s["y"]

        x0 = series[0]["x"]
        shared = all(np.array_equal(s["x"], x0) for s in series)
        if shared:
            coords["point"] = ("point", x0)
            data_vars = {"y": (("row", "col", "point"), y)}
        else:
            # NaN-filled, not np.empty()'s uninitialized garbage -- see the
            # matching comment in the mesh branch above.
            X = np.full((nrows, ncols, n), np.nan)
            for i, s in zip(filled, series):
                spec = template_axes[i]
                X[spec["row0"], spec["col0"], :] = s["x"]
            coords["x"] = (("row", "col", "point"), X)
            data_vars = {"y": (("row", "col", "point"), y)}

    return xr.Dataset(data_vars, coords=coords, attrs=attrs)


def select_panel(ds, title=None, row=None, col=None, multiple=False):
    """Pull one panel out of a :func:`load_data_xarray` grid, dropping
    ``row``/``col`` entirely instead of leaving them behind as length-1
    dimensions -- ``ds.isel(row=r, col=c)`` already does exactly that for a
    scalar ``r``/``c``, which is all this is: that call, plus resolving
    ``title`` to the one ``(row, col)`` position it names.

    Pass **either** ``title`` (matched against ``ds["title"]``, the same
    string :func:`load_data`/a panel's own ``ax.set_title()`` used) **or**
    both ``row``/``col`` (plain 0-based grid position) -- not a mix of the
    two, and not neither. Raises ``ValueError`` when ``title`` matches no
    panel at all. When ``title`` matches more than one panel (two panels
    sharing a title, so there is no name left to disambiguate by), this
    raises too *unless* ``multiple=True``, which returns every match as a
    list instead of picking one.

    ``multiple=True`` always returns a ``list`` of ``Dataset``\\ s -- one
    item for a unique ``title`` or an explicit ``row=``/``col=``, or one
    per match for a duplicated ``title`` -- rather than a list only
    *sometimes* and a bare ``Dataset`` otherwise, so a caller that always
    wants to loop over the result doesn't have to branch on how many
    panels actually matched.

    Each returned ``Dataset`` keeps every data variable/coordinate
    :func:`load_data_xarray` built, just without ``row``/``col`` -- a mesh
    panel's ``z`` is ``(y, x)`` instead of ``(row, col, y, x)``, a line
    panel's ``y`` is ``(point,)`` instead of ``(row, col, point)``, and
    ``title``/``xlabel``/``ylabel``/``has_data`` come back as plain scalar
    attributes of that one panel rather than ``(row, col)`` arrays.

    ::

        ds = plotpress.load_data_xarray(path)
        panel = plotpress.select_panel(ds, title="panel 4")
        panel["z"].plot()   # a plain (y, x) DataArray, xarray's own .plot()

        # Two panels both titled "control" -- get both instead of raising.
        controls = plotpress.select_panel(ds, title="control", multiple=True)
        for p in controls:
            p["z"].plot()
    """
    if title is not None:
        if row is not None or col is not None:
            raise ValueError(
                "select_panel(): pass title=, or row=/col=, not both.")
        matches = np.argwhere(ds["title"].values == title)
        if len(matches) == 0:
            raise ValueError(
                f"select_panel(): no panel titled {title!r} -- available: "
                f"{sorted(set(ds['title'].values.ravel()))!r}"
            )
        positions = [(int(r), int(c)) for r, c in matches]
    elif row is None or col is None:
        raise ValueError("select_panel(): pass title=, or both row= and col=.")
    else:
        positions = [(row, col)]

    if len(positions) > 1 and not multiple:
        raise ValueError(
            f"select_panel(): {len(positions)} panels are titled {title!r} "
            "-- not unique, so title alone can't pick one; pass row=/col= "
            "for a specific one, or multiple=True for every match as a list."
        )
    panels = [ds.isel(row=r, col=c) for r, c in positions]
    return panels if multiple else panels[0]
