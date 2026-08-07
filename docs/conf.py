"""Sphinx configuration for the plotpress documentation (Read the Docs)."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

import plotpress  # noqa: E402
from sphinx_gallery.sorting import ExplicitOrder, FileNameSortKey  # noqa: E402

# -- Project information ------------------------------------------------------
project = "plotpress"
copyright = "2026, plotpress contributors"
author = "plotpress contributors"
release = plotpress.__version__
version = release

# -- General configuration ----------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_gallery.gen_gallery",
]

autosummary_generate = True
autodoc_member_order = "bysource"
napoleon_numpy_docstring = True
napoleon_google_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
}

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_static_path = ["_static"]
# Widens the content column and lets table cells wrap; see the file for why the
# RTD theme's defaults put a scrollbar under every wide table.
html_css_files = ["custom.css"]

# The sphinx-gallery scraper is a function, so the config can't be pickle-cached
# -- that warning is benign; suppress it so CI can build with -W (warnings as
# errors) and still catch real documentation problems.
suppress_warnings = ["config.cache"]

# -- HTML output (Read the Docs theme) ----------------------------------------
html_theme = "sphinx_rtd_theme"
html_title = f"plotpress {version}"
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 3,
    "prev_next_buttons_location": "bottom",
    "style_external_links": True,
}
# "Edit on GitHub" / source links in the RTD theme header.
html_context = {
    "display_github": True,
    "github_user": "jrvannucci",
    "github_repo": "plotpress",
    "github_version": "main",
    "conf_py_path": "/docs/",
}


# -- sphinx-gallery: capture plotpress Figures as example images -------------
# Examples that also get a *live* interactive figure on their page. Every
# interactive figure inlines the whole JS toolbar and its own pick data (a few
# hundred KiB each for a dense mesh), so this is opt-in rather than
# gallery-wide: switching it on for the plot-type reference too would add
# megabytes of mostly-redundant payload for figures that have nothing to
# explore. The real-application gallery is the one worth exploring, so it gets
# live figures throughout.
_DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
_INTERACTIVE_ROOT = os.path.join(_DOCS_DIR, "applications")

_INTERACTIVE_DIR = os.path.join(_DOCS_DIR, "_static", "interactive")


def _wants_interactive(src_file):
    """True if this example lives under a gallery configured for live figures."""
    return os.path.abspath(src_file).startswith(_INTERACTIVE_ROOT + os.sep)


def _interactive_embed(fig, image_path):
    """Write ``fig`` as self-contained interactive HTML; return an RST raw block.

    The figure goes in an ``<iframe>`` rather than being spliced into the page.
    Each interactive figure carries its own copy of the toolbar script and its
    own element ids, so several on one page -- or one alongside the theme's own
    JavaScript -- would otherwise collide. An iframe gives each its own document
    and costs nothing, since the HTML is already self-contained and makes no
    external requests.
    """
    os.makedirs(_INTERACTIVE_DIR, exist_ok=True)
    name = os.path.splitext(os.path.basename(image_path))[0] + ".html"
    with open(os.path.join(_INTERACTIVE_DIR, name), "w", encoding="utf-8") as fh:
        fh.write(fig.to_html(interactive=True))

    dpi = fig.style.dpi
    width = int(round(fig.figsize[0] * dpi))
    # Room for the toolbar and any slider strip below the figure itself.
    height = int(round(fig.figsize[1] * dpi)) + 96
    # Example pages are built at auto_applications/<section>/, two levels below
    # the HTML root that _static sits in.
    src = "../../_static/interactive/" + name
    return "\n".join([
        ".. raw:: html",
        "",
        '   <div class="plotpress-interactive">',
        "     <p><em>Live figure &mdash; pick a tool, then zoom, pan, "
        "point-pick or annotate. Nothing is active until a tool is selected."
        "</em></p>",
        f'     <iframe src="{src}" width="{width}" height="{height}"',
        '             loading="lazy" style="max-width:100%; border:1px solid #ddd;"',
        '             title="Interactive figure"></iframe>',
        "   </div>",
        "",
    ])


def _write_usage_demo(fig, name, caption):
    """Write ``fig`` as a live interactive demo for the hand-written usage
    guide; return nothing -- writes both the demo HTML and an RST snippet
    ``usage.rst`` pulls in with ``.. include::``.

    ``usage.rst`` has no sphinx-gallery scraper pass to hook into (that only
    runs over ``examples_dirs``), so its demos are generated directly here,
    once, when Sphinx loads this config -- before any page is read. The
    embed markup itself mirrors :func:`_interactive_embed`, just with a
    caption and a shallower relative path (``usage.html`` sits one directory
    up from a gallery page, not two).
    """
    os.makedirs(_INTERACTIVE_DIR, exist_ok=True)
    with open(os.path.join(_INTERACTIVE_DIR, name + ".html"), "w", encoding="utf-8") as fh:
        fh.write(fig.to_html(interactive=True))
    dpi = fig.style.dpi
    width = int(round(fig.figsize[0] * dpi))
    height = int(round(fig.figsize[1] * dpi)) + 96
    rst = "\n".join([
        ".. raw:: html",
        "",
        '   <div class="plotpress-interactive">',
        f"     <p><em>{caption}</em></p>",
        f'     <iframe src="_static/interactive/{name}.html" width="{width}" height="{height}"',
        '             loading="lazy" style="max-width:100%; border:1px solid #ddd;"',
        '             title="Interactive figure"></iframe>',
        "   </div>",
        "",
    ])
    with open(os.path.join(_INTERACTIVE_DIR, name + ".rst.inc"), "w", encoding="utf-8") as fh:
        fh.write(rst)


def _build_usage_demos():
    """The three live figures embedded in docs/usage.rst's interactivity
    section -- one per toolbar capability the prose there describes."""
    import numpy as np

    fig1, ax1 = plotpress.subplots(figsize=(6, 4))
    x = np.linspace(0, 10, 200)
    ax1.plot(x, np.sin(x), label="sin")
    sx = np.linspace(0, 10, 25)
    ax1.scatter(sx, np.cos(sx), s=20, label="cos",
               values={"phase": sx % (2 * np.pi)})
    ax1.set_xlabel("x"); ax1.set_ylabel("y"); ax1.legend()
    _write_usage_demo(
        fig1, "usage_pan_zoom_pick",
        "Span to pan, Zoom to zoom (wheel or box-drag), Point Pick to read a "
        "value -- the scatter series also carries a phase value, surfaced "
        "when a marker is picked.")

    fig2, ax2 = plotpress.subplots(figsize=(6, 4))
    x2 = np.linspace(0, 10, 300)
    ax2.plot(x2, np.sin(x2) * np.exp(-x2 / 12))
    ax2.set_xlabel("x"); ax2.set_ylabel("y")
    _write_usage_demo(
        fig2, "usage_annotate",
        "Annotate Point locks a note to the nearest datum -- try the peak; "
        "Annotate Free drops one anywhere on the figure, including outside "
        "the axes.")

    fig3, ax3 = plotpress.subplots(figsize=(6, 4))
    xf = np.linspace(0, 2 * np.pi, 100)
    frames = np.array([np.sin(xf + phase)
                       for phase in np.linspace(0, 2 * np.pi, 24, endpoint=False)])
    ax3.plot_frames(xf, frames, slider_label="phase")
    ax3.set_xlabel("x"); ax3.set_ylabel("y")
    _write_usage_demo(
        fig3, "usage_frames",
        "plot_frames adds a play/pause/step slider over an extra dimension.")

    fig4, (ax4l, ax4r) = plotpress.subplots(1, 2, figsize=(6, 4))
    x4 = np.linspace(0, 10, 200)
    ax4l.plot(x4, np.sin(x4), color="#d62728")
    ax4l.set_title("Sensor A")
    ax4l.set_pick_context(edge_color="red", unit="V")
    ax4r.plot(x4, np.cos(x4), color="#1f77b4")   # no title -- axes_title falls back
    ax4r.set_pickable(False)
    _write_usage_demo(
        fig4, "usage_pick_context",
        "Point Pick the left panel: its axes_title (\"Sensor A\") and "
        "set_pick_context() keys (edge_color, unit) ride along on the marker. "
        "The right panel has set_pickable(False), so clicking it does "
        "nothing -- and were it pickable, its axes_title would fall back to "
        "a generated \"axes 1\" since it has no title of its own.")


_build_usage_demos()


def _plotpress_scraper(block, block_vars, gallery_conf):
    """Save any new ``plotpress.Figure`` created by an example to a PNG.

    Mirrors sphinx-gallery's matplotlib scraper, but scans the example's globals
    (plotpress has no global figure registry) and rasterizes via the built-in
    Pillow backend. Examples in :data:`INTERACTIVE_SECTIONS` additionally get a
    live interactive copy embedded below the static image -- the PNG stays,
    because sphinx-gallery builds its thumbnails from it.
    """
    from sphinx_gallery.scrapers import figure_rst

    it = block_vars["image_path_iterator"]
    seen = block_vars.setdefault("_plotpress_seen", set())
    interactive = _wants_interactive(block_vars["src_file"])
    paths, embeds = [], []
    for value in list(block_vars["example_globals"].values()):
        if isinstance(value, plotpress.Figure) and id(value) not in seen:
            seen.add(id(value))
            path = next(it)
            value.save(path, scale=2)      # PNG via plotpress.raster
            paths.append(path)
            if interactive:
                embeds.append(_interactive_embed(value, path))
    rst = figure_rst(paths, gallery_conf["src_dir"])
    if embeds:
        rst += "\n\n" + "\n".join(embeds)
    return rst


# Three galleries, from three source trees. ``examples`` is the plot-type
# reference -- one figure per method, deliberately minimal. ``scale`` is the
# large-figure gallery, where build time and file size are the subject rather
# than a footnote, so its examples are slow by design and belong off the
# reference page. ``applications`` is the real-application gallery, grouped by
# field, where the point is the reasoning that leads to the figure rather than
# the call that draws it.
sphinx_gallery_conf = {
    "examples_dirs": ["examples", "scale", "applications"],
    "gallery_dirs": ["auto_examples", "auto_scale", "auto_applications"],
    # Order thumbnails by file name. Every example is numbered (plot_01_...)
    # precisely to fix the reading order, but sphinx-gallery defaults to sorting
    # by *code length*, which buried the line-plot introduction two thirds of
    # the way down the page behind whatever example happened to be shortest.
    "within_subsection_order": FileNameSortKey,
    # Sections run capability-first, with limitations last: a reader browsing
    # the gallery should meet what the library does before what it does not.
    # Alphabetical (the default) put limitations second, right behind the
    # introductory plot types. The application sections then run outward from
    # the planet to the lab bench to the ledger, which is arbitrary but stable
    # -- alphabetical would open on acoustics and scatter related fields apart.
    "subsection_order": ExplicitOrder([
        "scale/limitations",
        "examples/axes_features",
        "examples/figure_layout",
        "examples/advanced_axes",
        "examples/polar",
        "examples/threed",
        "examples/signal",
        "examples/seaborn",
        "examples/limitations",
        "applications/earth",
        "applications/space",
        "applications/medical",
        "applications/biology",
        "applications/chemistry",
        "applications/materials",
        "applications/quantum",
        "applications/semiconductor",
        "applications/fluids",
        "applications/acoustics",
        "applications/energy",
        "applications/transport",
        "applications/manufacturing",
        "applications/computing",
        "applications/finance",
    ]),
    # Separator-agnostic so examples execute on Windows and POSIX alike.
    "filename_pattern": r"plot_",
    "image_scrapers": (_plotpress_scraper,),
    "reset_modules": (),
    "thumbnail_size": (400, 280),
    "remove_config_comments": True,
    "download_all_examples": False,
    "line_numbers": False,
}
