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
    "github_user": "plotpress",
    "github_repo": "plotpress",
    "github_version": "main",
    "conf_py_path": "/docs/",
}


# -- sphinx-gallery: capture plotpress Figures as example images -------------
# Gallery subsections whose examples also get a *live* interactive figure on
# their page. Every interactive figure inlines the whole JS toolbar and its own
# pick data (~130 KiB each here), so this is opt-in per section rather than
# gallery-wide: switching on all 69 examples would add several megabytes of
# mostly-redundant payload to the site.
INTERACTIVE_SECTIONS = ("mesh",)

_INTERACTIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "_static", "interactive")


def _wants_interactive(src_file):
    """True if this example lives in a section configured for live figures."""
    return os.path.basename(os.path.dirname(src_file)) in INTERACTIVE_SECTIONS


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
    # Example pages are built at auto_examples/<section>/, two levels below the
    # HTML root that _static sits in.
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


sphinx_gallery_conf = {
    "examples_dirs": "examples",
    "gallery_dirs": "auto_examples",
    # Order thumbnails by file name. Every example is numbered (plot_01_...)
    # precisely to fix the reading order, but sphinx-gallery defaults to sorting
    # by *code length*, which buried the line-plot introduction two thirds of
    # the way down the page behind whatever example happened to be shortest.
    "within_subsection_order": FileNameSortKey,
    # Sections run capability-first, with limitations last: a reader browsing
    # the gallery should meet what the library does before what it does not.
    # Alphabetical (the default) put limitations second, right behind the
    # introductory plot types.
    "subsection_order": ExplicitOrder([
        "examples/mesh",
        "examples/scale",
        "examples/polar",
        "examples/threed",
        "examples/signal",
        "examples/seaborn",
        "examples/limitations",
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
