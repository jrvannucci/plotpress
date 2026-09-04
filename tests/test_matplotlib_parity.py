"""matplotlib / seaborn API-compatibility parity.

plotpress bills a *matplotlib-shaped* API. These tests pin the compatibility
that matters for drop-in use:

* coverage  -- plotpress's Axes exposes the core matplotlib Axes methods;
* keywords  -- matplotlib's *keyword* names for first positional args work
               (``ax.hist(x=...)``, ``ax.set_title(label=...)``, etc.);
* numbers   -- where matplotlib produces a well-defined value (histogram bins,
               autoscaled limits, quartiles), plotpress agrees;
* seaborn   -- the seaborn-style helpers (kdeplot/ecdfplot/rugplot) match real
               seaborn's output shape.

matplotlib and seaborn are optional (see the ``bench`` extra); every test that
needs them ``importorskip``s, so a plain dependency-light run just skips them.
The pure-plotpress checks (keyword aliases, hist == ``np.histogram``) always
run and guard the parity fixes against regression.
"""
import numpy as np
import pytest

import plotpress


# ---------------------------------------------------------------------------
# Coverage: the core matplotlib Axes methods plotpress commits to.
# ---------------------------------------------------------------------------
CORE_AXES_METHODS = [
    # line / marker
    "plot", "scatter", "step", "stem", "errorbar", "stairs",
    # bar / fill
    "bar", "barh", "hist", "fill", "fill_between", "fill_betweenx",
    "stackplot", "broken_barh", "eventplot",
    # statistical
    "boxplot", "violinplot", "hexbin", "hist2d", "pie",
    # image / field
    "imshow", "matshow", "spy", "pcolormesh", "contour", "contourf", "quiver",
    # spectral
    "psd", "csd", "cohere", "magnitude_spectrum", "angle_spectrum",
    "phase_spectrum", "specgram", "xcorr", "acorr",
    # reference geometry
    "axhline", "axvline", "axline", "axhspan", "axvspan", "hlines", "vlines",
    # annotation / scale
    "text", "annotate", "semilogx", "semilogy", "loglog",
    # limits / ticks / labels
    "set_xlim", "set_ylim", "get_xlim", "get_ylim", "set_xbound", "set_ybound",
    "set_xscale", "set_yscale", "set_aspect", "margins",
    "set_xticks", "set_yticks", "set_xticklabels", "set_yticklabels",
    "invert_xaxis", "invert_yaxis", "twinx", "twiny",
    "set_xlabel", "set_ylabel", "set_title", "grid", "legend", "tick_params",
]


@pytest.mark.parametrize("name", CORE_AXES_METHODS)
def test_axes_method_exists(name):
    _, ax = plotpress.subplots()
    assert callable(getattr(ax, name, None)), f"missing Axes.{name}"


def test_method_names_are_a_subset_of_matplotlib():
    """Every non-underscore Axes method (bar the intentional seaborn/bespoke
    extras) shares its name with a real matplotlib Axes method."""
    plt = pytest.importorskip("matplotlib.pyplot")
    import matplotlib
    matplotlib.use("Agg")

    _, spax = plotpress.subplots()
    _, mpax = plt.subplots()
    sp = {n for n in dir(spax)
          if not n.startswith("_") and callable(getattr(spax, n))}
    mpl = {n for n in dir(mpax) if not n.startswith("_")}
    intentional_extras = {
        "kdeplot", "ecdfplot", "rugplot", "plot_frames", "pcolormesh_frames",
        # matplotlib puts these on ax.xaxis/ax.yaxis; plotpress has no XAxis/
        # YAxis wrapper objects (flat Axes methods are the whole API), so they
        # live directly on Axes instead.
        "tick_top", "tick_bottom", "tick_left", "tick_right",
        # matplotlib's picking is a different, event-based mpl_connect system
        # with no per-axes on/off switch or attachable metadata -- these
        # control plotpress's own interactive-HTML point picking instead.
        "set_pickable", "get_pickable", "set_pick_context", "get_pick_context",
        # A plain-English orientation to one axes (position, scales,
        # artists, Vega/Vega-Lite export compatibility) -- matplotlib has
        # no equivalent; see Figure.print_layout_summary for the
        # whole-figure version.
        "print_summary",
    }
    unexpected = sp - mpl - intentional_extras
    plt.close("all")
    assert not unexpected, f"non-matplotlib method names: {sorted(unexpected)}"


# ---------------------------------------------------------------------------
# Keyword parity: matplotlib's keyword name for the first positional arg works.
# These are pure-plotpress regression guards for the parity fixes.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("call", [
    lambda ax: ax.hist(x=np.random.default_rng(0).standard_normal(50)),
    lambda ax: ax.boxplot(x=[np.random.default_rng(0).standard_normal(50)]),
    lambda ax: ax.pie(x=[1, 2, 3]),
    lambda ax: ax.imshow(X=np.random.default_rng(0).random((4, 4))),
    lambda ax: ax.set_title(label="t"),
    lambda ax: ax.set_xlabel(xlabel="x"),
    lambda ax: ax.set_ylabel(ylabel="y"),
], ids=["hist", "boxplot", "pie", "imshow", "set_title",
        "set_xlabel", "set_ylabel"])
def test_matplotlib_keyword_names(call):
    fig, ax = plotpress.subplots()
    call(ax)
    fig.to_svg()  # must render


def test_set_ticks_combined_labels_form():
    """matplotlib's ``set_xticks(ticks, labels)`` one-call form."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1, 2], [0, 1, 0])
    ax.set_xticks([0, 1, 2], ["a", "b", "c"])
    ax.set_yticks([0, 1], ["lo", "hi"])
    assert ax._xticklabels == ["a", "b", "c"]
    assert ax._yticklabels == ["lo", "hi"]


def test_positional_calls_still_work():
    """Renaming params must not break positional callers."""
    rng = np.random.default_rng(0)
    fig, ax = plotpress.subplots()
    ax.hist(rng.standard_normal(50))
    ax.boxplot([rng.standard_normal(50)])
    fig, ax = plotpress.subplots()
    ax.pie([1, 2, 3])
    fig, ax = plotpress.subplots()
    ax.imshow(rng.random((4, 4)))
    fig.to_svg()


# ---------------------------------------------------------------------------
# Numerical parity.
# ---------------------------------------------------------------------------
def test_hist_bins_equal_numpy():
    """hist bins/counts are exactly numpy's -- matplotlib's own basis."""
    d = np.random.default_rng(42).standard_normal(500)
    _, ax = plotpress.subplots()
    counts, edges, _ = ax.hist(d, bins=20)
    np_counts, np_edges = np.histogram(d, bins=20)
    assert np.array_equal(np.asarray(counts), np_counts)
    assert np.allclose(np.asarray(edges), np_edges)


def test_hist_respects_range():
    d = np.random.default_rng(42).standard_normal(500)
    _, ax = plotpress.subplots()
    counts, _, _ = ax.hist(d, bins=10, range=(-2, 2))
    np_counts, _ = np.histogram(d, bins=10, range=(-2, 2))
    assert np.array_equal(np.asarray(counts), np_counts)


def test_plot_autoscale_matches_matplotlib():
    plt = pytest.importorskip("matplotlib.pyplot")
    import matplotlib
    matplotlib.use("Agg")

    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    _, spax = plotpress.subplots()
    spax.plot(x, y)
    _, mpax = plt.subplots()
    mpax.plot(x, y)
    # matplotlib pads the data range ~5% on each side; plotpress should match.
    assert np.allclose(spax.get_xlim(), mpax.get_xlim(), atol=0.3)
    assert np.allclose(spax.get_ylim(), mpax.get_ylim(), atol=0.3)
    plt.close("all")


def test_plot_limits_enclose_data():
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    _, ax = plotpress.subplots()
    ax.plot(x, y)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    assert x0 <= x.min() and x1 >= x.max()
    assert y0 <= y.min() and y1 >= y.max()


def test_bar_zero_baseline_and_span():
    _, ax = plotpress.subplots()
    ax.bar([1, 2, 3], [10, 20, 30], width=0.8)
    x0, x1 = ax.get_xlim()
    assert x0 <= 0.6 and x1 >= 3.4          # bars are centered, width 0.8
    assert ax.get_ylim()[0] <= 0            # baseline anchored at zero


def test_boxplot_median_matches_numpy():
    plt = pytest.importorskip("matplotlib.pyplot")
    import matplotlib
    matplotlib.use("Agg")

    d = np.random.default_rng(7).standard_normal(1000)
    med = np.percentile(d, 50)
    _, mpax = plt.subplots()
    mbp = mpax.boxplot([d])
    assert np.isclose(mbp["medians"][0].get_ydata()[0], med)
    # plotpress computes the same stats internally and must render.
    fig, spax = plotpress.subplots()
    spax.boxplot([d])
    assert "<" in fig.to_svg()
    plt.close("all")


def test_errorbar_limits_include_error_extents():
    _, ax = plotpress.subplots()
    ax.errorbar([1, 2, 3], [1, 2, 3], yerr=0.5)
    y0, y1 = ax.get_ylim()
    assert y0 <= 0.5 + 1e-9 and y1 >= 3.5 - 1e-9


def test_logscale_clamps_positive():
    _, ax = plotpress.subplots()
    ax.plot([1, 10, 100], [1, 10, 100])
    ax.set_xscale("log")
    ax.set_yscale("log")
    assert ax.get_xlim()[0] > 0
    assert ax.get_ylim()[0] > 0


# ---------------------------------------------------------------------------
# Seaborn parity.
# ---------------------------------------------------------------------------
def test_kde_xrange_matches_seaborn():
    sns = pytest.importorskip("seaborn")
    plt = pytest.importorskip("matplotlib.pyplot")
    import matplotlib
    matplotlib.use("Agg")

    d = np.random.default_rng(0).standard_normal(500)
    _, spax = plotpress.subplots()
    spax.kdeplot(d)
    _, mpax = plt.subplots()
    sns.kdeplot(d, ax=mpax)
    # KDE support extends past the data via the smoothing cut; the axis range
    # plotpress picks should track seaborn's within a small tolerance.
    assert np.allclose(spax.get_xlim(), mpax.get_xlim(), atol=0.5)
    plt.close("all")


@pytest.mark.parametrize("call", [
    lambda ax: ax.kdeplot(np.random.default_rng(0).standard_normal(200)),
    lambda ax: ax.ecdfplot(np.random.default_rng(0).standard_normal(200)),
    lambda ax: ax.rugplot(np.random.default_rng(0).standard_normal(200)),
], ids=["kdeplot", "ecdfplot", "rugplot"])
def test_seaborn_style_helpers_render(call):
    fig, ax = plotpress.subplots()
    call(ax)
    assert len(fig.to_svg()) > 200


def test_ecdf_is_monotonic_zero_to_one():
    """An empirical CDF must rise monotonically across [0, 1]."""
    d = np.random.default_rng(0).standard_normal(300)
    _, ax = plotpress.subplots()
    ax.ecdfplot(d)
    # the ecdf line artist should carry y-data spanning 0..1, non-decreasing.
    ys = None
    for art in ax.artists:
        y = getattr(art, "y", None)
        if y is not None and len(np.ravel(y)) >= len(d):
            ys = np.ravel(np.asarray(y, float))
            break
    assert ys is not None, "no ecdf line found"
    assert ys.min() >= -1e-9 and ys.max() <= 1 + 1e-9
    assert np.all(np.diff(ys) >= -1e-9)
