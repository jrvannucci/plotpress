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
_GIF_DIR = os.path.join(_DOCS_DIR, "_static", "gifs")


def _wheel_zoom_frames(fig, cursor_frac, n_steps=16, zoom_factor=0.85,
                       hold_frames=5, supersample=6, out_size=None):
    """Reproduce the wheel-zoom-toward-cursor gesture as a sequence of raster
    frames, for a demo GIF -- there's no browser at doc-build time to drive
    the real interactive gesture, so this applies ``_interactive.py``'s
    ``zoomViewAt()`` -- ``view[0] = px - (px - view[0]) * factor`` -- to a
    shrinking pixel crop of a supersampled render of the same static figure,
    in place of an SVG viewBox change. Supersampling (well past the crop's
    final display size) keeps the tightest crop from looking pixelated,
    standing in for a real SVG viewer's resolution-independent zoom.
    """
    from PIL import Image
    from plotpress.raster import figure_to_image

    base = figure_to_image(fig, scale=supersample)
    W, H = base.size
    out_size = out_size or (W // supersample, H // supersample)
    cx, cy = cursor_frac[0] * W, cursor_frac[1] * H
    view_x, view_y, view_w, view_h = 0.0, 0.0, float(W), float(H)

    def crop_frame():
        box = (round(view_x), round(view_y),
              round(view_x + view_w), round(view_y + view_h))
        return base.crop(box).resize(out_size, Image.LANCZOS)

    zoom_in = [crop_frame()]
    for _ in range(n_steps):
        view_x = cx - (cx - view_x) * zoom_factor
        view_y = cy - (cy - view_y) * zoom_factor
        view_w *= zoom_factor
        view_h *= zoom_factor
        zoom_in.append(crop_frame())
    # Hold on the fully zoomed-in frame, then mirror the sequence back out --
    # a single loop demonstrates both directions of the gesture.
    return zoom_in + [zoom_in[-1]] * hold_frames + list(reversed(zoom_in))


def _write_wheel_zoom_gif(fig, name, cursor_frac, **kwargs):
    """Write a wheel-zoom-toward-cursor demo GIF into ``_static/gifs/``."""
    os.makedirs(_GIF_DIR, exist_ok=True)
    frames = _wheel_zoom_frames(fig, cursor_frac, **kwargs)
    path = os.path.join(_GIF_DIR, name + ".gif")
    frames[0].save(path, format="GIF", save_all=True,
                   append_images=frames[1:], duration=90, loop=0)


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


def _write_usage_report_demo(report, name, caption, height=760):
    """Write ``report`` (a :class:`plotpress.Report`) as a live interactive
    demo for the usage guide; return nothing -- writes both the combined
    report HTML and an RST snippet ``usage.rst`` pulls in with ``.. include::``.

    Mirrors :func:`_write_usage_demo`, but for a :class:`~plotpress.Report`
    rather than a single :class:`~plotpress.Figure`: ``Report.save()`` already
    writes the combined, self-contained HTML file directly, so this only has
    to point an outer iframe at it. ``height`` is a fixed viewport rather than
    the figure-size-derived height :func:`_write_usage_demo` computes -- a
    report stacks several figures, so it scrolls internally instead of trying
    to show the whole thing at once.
    """
    os.makedirs(_INTERACTIVE_DIR, exist_ok=True)
    report.save(os.path.join(_INTERACTIVE_DIR, name + ".html"))
    rst = "\n".join([
        ".. raw:: html",
        "",
        '   <div class="plotpress-interactive">',
        f"     <p><em>{caption}</em></p>",
        f'     <iframe src="_static/interactive/{name}.html" width="100%" height="{height}"',
        '             loading="lazy" style="max-width:100%; border:1px solid #ddd;"',
        '             title="Interactive report"></iframe>',
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

    fig5, ax5 = plotpress.subplots(figsize=(6, 4))
    x5 = np.linspace(0, 10, 200)
    ax5.plot(x5, np.sin(x5) + 0.15 * np.cos(3 * x5))
    ax5.set_xlabel("x"); ax5.set_ylabel("y")
    _write_usage_demo(
        fig5, "usage_hide_annotations",
        "Point Pick a few values along the curve, then click Hide "
        "Annotations -- every pin disappears without being deleted; click "
        "it again (now labeled Show Annotations) to bring them all back "
        "exactly as they were.")

    _build_usage_report_demo()
    _build_wheel_zoom_gifs()


def _build_wheel_zoom_gifs():
    """The two GIFs embedded in usage.rst's Zoom bullet, demonstrating the
    wheel-zoom-toward-cursor gesture (see _wheel_zoom_frames): one on a
    many-axes grid -- the case a per-axes zoom wouldn't help with, since the
    cursor is only ever over one tiny panel at a time -- and one on a plain
    single-axes figure, showing the same gesture works just as directly
    there.
    """
    import numpy as np

    rng = np.random.default_rng(1)
    fig_grid, axes = plotpress.subplots(5, 6, figsize=(16, 9))
    x = np.linspace(0, 10, 21)
    y = np.linspace(0, 5, 11)
    X, Y = np.meshgrid(x, y)
    for i, ax in enumerate(np.asarray(axes).ravel()):
        Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
        ax.pcolormesh(x, y, Z, cmap="viridis", vmin=-1, vmax=1)
        ax.set_title(f"panel {i}", fontsize=7)
        ax.tick_params(labelsize=5)
    fig_grid.tight_layout()
    _write_wheel_zoom_gif(fig_grid, "wheel_zoom_many_axes", cursor_frac=(0.32, 0.62))

    fig_one, ax_one = plotpress.subplots(figsize=(6, 4))
    x1 = np.linspace(0, 10, 300)
    ax_one.plot(x1, np.sin(x1) * np.exp(-x1 / 12))
    ax_one.set_xlabel("x"); ax_one.set_ylabel("y")
    _write_wheel_zoom_gif(fig_one, "wheel_zoom_single_axes", cursor_frac=(0.35, 0.3))


def _build_usage_report_demo():
    """The Report demo embedded in usage.rst's "Combining figures into a
    report" section: four independent figures, each a 5x10 grid of its own
    pcolormesh panels (own title, axes, ticks, labels, colorbar), combined
    into one file via plotpress.Report -- exercising both "many axes in one
    figure" and "many figures in one HTML" at once.
    """
    import numpy as np

    rng = np.random.default_rng(0)
    cmaps = ["viridis", "plasma", "magma", "inferno"]
    report = plotpress.Report(
        title="Sensor bank sweep",
        description="Four batches of a 5x10 sensor grid, one figure each.")
    for i, cmap in enumerate(cmaps):
        fig, axes = plotpress.subplots(5, 10, figsize=(24, 13))
        for j, ax in enumerate(np.asarray(axes).ravel()):
            z = rng.uniform(0, 1, (4, 4)) + 0.5 * np.sin(j)
            m = ax.pcolormesh(z, cmap=cmap)
            ax.set_title(f"panel {j}", fontsize=7)
            ax.set_xlabel("x")
            ax.set_ylabel("y")
            ax.tick_params(labelsize=5)
            fig.colorbar(m, ax=ax)
        fig.tight_layout()
        report.add(fig, title=f"Batch {chr(65 + i)}",
                   details=f"50 independent sensor panels, cmap={cmap!r}. "
                           "Each keeps its own title, ticks, labels, and "
                           "colorbar -- pan/zoom/pick works panel by panel.")
    _write_usage_report_demo(
        report, "usage_report",
        "Four figures, each a 5x10 grid of independent pcolormesh panels, "
        "combined into one file with plotpress.Report -- every panel in "
        "every figure keeps its own toolbar-driven interactivity.")


_build_usage_demos()


def _plotpress_scraper(block, block_vars, gallery_conf):
    """Save any new ``plotpress.Figure`` created by an example to an image.

    Mirrors sphinx-gallery's matplotlib scraper, but scans the example's globals
    (plotpress has no global figure registry) and rasterizes via the built-in
    Pillow backend. A figure with a ``plot_frames()`` series saves as an
    animated GIF instead of a static PNG -- sphinx-gallery's own thumbnailer
    (``sphinx_gallery.gen_rst.save_thumbnail``) copies a ``.gif`` byte for byte
    rather than re-encoding it, so both the gallery page's image and its
    thumbnail play the animation rather than freezing on frame 0. Examples in
    :data:`INTERACTIVE_SECTIONS` additionally get a live interactive copy
    embedded below the image.
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
            if value._sliders:
                # image_path_iterator only ever hands out a .png path; swap
                # the extension so _find_image_ext (and save_thumbnail's
                # copyfile-for-gif branch) pick up the animation instead.
                path = os.path.splitext(path)[0] + ".gif"
                from plotpress.raster import save_gif
                save_gif(value, path, fps=10, scale=2)
            else:
                value.save(path, scale=2)      # PNG via plotpress.raster
            paths.append(path)
            if interactive:
                embeds.append(_interactive_embed(value, path))

    # A handful of examples (progressive/live-acquisition demos, one
    # independent Figure per frame) need a colour scale or axis extent that
    # changes frame to frame -- plot_frames()/pcolormesh_frames()'s shared,
    # fixed Normalize can't express that, so there's no single animated
    # plotpress.Figure to scan globals for above. Those scripts render their
    # own frames (plotpress.raster.figure_to_image) into this list instead;
    # stitch it into a GIF through the same path iterator so it lands in the
    # gallery -- and gets thumbnailed -- exactly like any other animation.
    frames = block_vars["example_globals"].get("_gallery_gif_frames")
    if frames:
        path = os.path.splitext(next(it))[0] + ".gif"
        frames[0].save(path, format="GIF", save_all=True,
                       append_images=frames[1:], duration=80, loop=0)
        paths.append(path)

    rst = figure_rst(paths, gallery_conf["src_dir"])
    if embeds:
        rst += "\n\n" + "\n".join(embeds)
    return rst


# Four galleries, from four source trees. ``examples`` is the plot-type
# reference -- one figure per method, deliberately minimal. ``scale`` is the
# large-figure gallery, where build time and file size are the subject rather
# than a footnote, so its examples are slow by design and belong off the
# reference page. ``live_streaming`` is a feature deep-dive -- every example
# animates an acquisition sequence a real ``plotpress.qt.LiveArtist`` would
# show updating live, first as abstract patterns, then as specific lab
# instruments -- and gets its own gallery rather than a subsection of
# ``examples`` because both halves would otherwise crowd out the plot-type
# reference they'd sit alongside. ``applications`` is the real-application
# gallery, grouped by field, where the point is the reasoning that leads to
# the figure rather than the call that draws it.
sphinx_gallery_conf = {
    "examples_dirs": ["examples", "scale", "live_streaming", "applications"],
    "gallery_dirs": ["auto_examples", "auto_scale", "auto_live_streaming", "auto_applications"],
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
        "examples/pairwise",
        "examples/distributions",
        "examples/gridded_data",
        "examples/multi_axes",
        "examples/animation",
        "examples/axes_features",
        "examples/figure_layout",
        "examples/advanced_axes",
        "examples/polar",
        "examples/threed",
        "examples/signal",
        "examples/seaborn",
        "examples/data_roundtrip",
        "examples/limitations",
        "live_streaming/patterns",
        "live_streaming/lab_examples",
        "applications/earth",
        "applications/space",
        "applications/medical",
        "applications/biology",
        "applications/chemistry",
        "applications/materials",
        "applications/quantum_spectroscopy",
        "applications/quantum_readout_maps",
        "applications/quantum_coherence_noise",
        "applications/quantum_gate_calibration",
        "applications/quantum_benchmarking",
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
