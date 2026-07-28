"""Sphinx configuration for the plotpress documentation (Read the Docs)."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

import plotpress  # noqa: E402
from sphinx_gallery.sorting import FileNameSortKey  # noqa: E402

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
def _plotpress_scraper(block, block_vars, gallery_conf):
    """Save any new ``plotpress.Figure`` created by an example to a PNG.

    Mirrors sphinx-gallery's matplotlib scraper, but scans the example's globals
    (plotpress has no global figure registry) and rasterizes via the built-in
    Pillow backend.
    """
    from sphinx_gallery.scrapers import figure_rst

    it = block_vars["image_path_iterator"]
    seen = block_vars.setdefault("_plotpress_seen", set())
    paths = []
    for value in list(block_vars["example_globals"].values()):
        if isinstance(value, plotpress.Figure) and id(value) not in seen:
            seen.add(id(value))
            path = next(it)
            value.save(path, scale=2)      # PNG via plotpress.raster
            paths.append(path)
    return figure_rst(paths, gallery_conf["src_dir"])


sphinx_gallery_conf = {
    "examples_dirs": "examples",
    "gallery_dirs": "auto_examples",
    # Order thumbnails by file name. Every example is numbered (plot_01_...)
    # precisely to fix the reading order, but sphinx-gallery defaults to sorting
    # by *code length*, which buried the line-plot introduction two thirds of
    # the way down the page behind whatever example happened to be shortest.
    "within_subsection_order": FileNameSortKey,
    # Separator-agnostic so examples execute on Windows and POSIX alike.
    "filename_pattern": r"plot_",
    "image_scrapers": (_plotpress_scraper,),
    "reset_modules": (),
    "thumbnail_size": (400, 280),
    "remove_config_comments": True,
    "download_all_examples": False,
    "line_numbers": False,
}
