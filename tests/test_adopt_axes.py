"""Figure.adopt_axes(): merging an axes built in another process back in.

Most of these need only stdlib pickle -- that alone proves adopt_axes()
correctly repairs the SubplotSpec/`.figure` state a process boundary always
breaks, without needing a real subprocess to demonstrate it. A couple of
tests additionally drive a real joblib worker (a genuine OS subprocess, not
joblib's n_jobs=1 in-process fallback, which doesn't pickle at all and so
proves nothing about this) to confirm the same holds true end to end, not
just under a same-process pickle round trip.
"""
import pickle

import numpy as np
import pytest

import plotpress

joblib = pytest.importorskip("joblib", reason="needs the 'docs' extra (or `pip install joblib`)")


def test_adopt_axes_replaces_the_correct_slot_leaving_others_untouched():
    """The case the feature exists for: reprocess ONE panel of an
    otherwise-finished figure and merge just that one back in -- every
    other axes must come out byte-identical, and the adopted one must
    land at exactly the rect its slot already had."""
    fig, axes = plotpress.subplots(3, 3, figsize=(9, 9))
    flat = list(axes.ravel())
    for i, ax in enumerate(flat):
        ax.plot([0, 1], [0, i])
        ax.set_title(f"original {i}")
    fig.tight_layout()
    original_rects = [ax._rect for ax in flat]

    TARGET = 4
    copy = pickle.loads(pickle.dumps(flat[TARGET]))
    assert copy is not flat[TARGET]          # a real copy, not the same object
    assert copy.figure is not fig            # -- and not attached to this figure

    copy.set_title("REPLACED")
    returned = fig.adopt_axes(copy)

    assert returned is copy
    assert copy.figure is fig
    assert fig.axes[TARGET] is copy
    assert len(fig.axes) == 9

    for i, ax in enumerate(fig.axes):
        if i == TARGET:
            continue
        assert ax._rect == original_rects[i]
        assert ax._title == f"original {i}"

    fig.tight_layout()
    assert fig.axes[TARGET]._rect == original_rects[TARGET]
    assert fig.axes[TARGET]._title == "REPLACED"

    svg = fig.to_svg()
    assert svg.count("REPLACED") == 1
    for i in range(9):
        if i != TARGET:
            assert f"original {i}" in svg


def test_adopt_axes_works_repeatedly_one_slot_at_a_time():
    """Reprocessing several panels, one adopt_axes() call each, must not
    interfere with each other -- covers the exact `for ax in results:
    fig.adopt_axes(ax)` loop the feature is meant for."""
    fig, axes = plotpress.subplots(2, 2)
    flat = list(axes.ravel())
    for i, ax in enumerate(flat):
        ax.set_title(f"pre {i}")

    for i in (0, 2, 3):
        copy = pickle.loads(pickle.dumps(flat[i]))
        copy.set_title(f"post {i}")
        fig.adopt_axes(copy)

    titles = [ax._title for ax in fig.axes]
    assert titles == ["post 0", "pre 1", "post 2", "post 3"]
    assert len(fig.axes) == 4


def test_adopt_axes_appends_a_colorbar_instead_of_replacing_a_slot():
    """A colorbar axes has no SubplotSpec (it was never on the grid) --
    adopt_axes() must append it, not search for a slot to replace, and
    its own reference to the axes it belongs to must survive intact when
    both are pickled and adopted together."""
    fig, axes = plotpress.subplots(2, 2)
    specs = [ax._subplotspec for ax in axes.ravel()]

    scratch = plotpress.Figure()
    worker_ax = scratch.add_subplot(specs[0])
    mesh = worker_ax.pcolormesh(np.zeros((3, 3)))
    worker_cax = scratch.colorbar(mesh, ax=worker_ax)

    ax, cax = pickle.loads(pickle.dumps((worker_ax, worker_cax)))
    assert ax.figure is not fig and cax.figure is not fig

    fig.adopt_axes(ax)
    fig.adopt_axes(cax)

    assert len(fig.axes) == 5   # 4 panels + 1 colorbar
    assert cax.figure is fig
    assert cax._cbar_parents[0] is ax   # survived the pickle round trip as-is
    assert fig.axes[0] is ax

    fig.tight_layout()
    fig.to_svg()   # must not raise


def test_adopt_axes_rejects_a_spec_with_no_matching_slot():
    """A clear error, not a silent append or a broken layout, when the
    axes being adopted doesn't belong to this figure's own grid shape."""
    fig2x2, _ = plotpress.subplots(2, 2)
    fig3x3, axes3x3 = plotpress.subplots(3, 3)
    foreign = pickle.loads(pickle.dumps(axes3x3.ravel()[0]))

    with pytest.raises(ValueError, match="no existing axes"):
        fig2x2.adopt_axes(foreign)


def test_adopt_axes_through_a_real_joblib_subprocess():
    """The same replace-one-slot case as the first test, but driven
    through an actual OS subprocess (n_jobs=2 forces joblib's loky
    backend to really fork/spawn, unlike n_jobs=1's in-process
    fallback) -- proves the fix holds for a genuine process boundary,
    not just a bare pickle.dumps/loads round trip."""
    fig, axes = plotpress.subplots(2, 2, figsize=(8, 6))
    flat = list(axes.ravel())
    for i, ax in enumerate(flat):
        ax.set_title(f"pre {i}")
    fig.tight_layout()
    other_rects = {i: flat[i]._rect for i in (1, 2, 3)}

    def _build(ax, x, y):
        ax.plot(x, y)
        ax.set_title("built in a subprocess")
        return ax

    x = np.linspace(0, 1, 10)
    (built,) = joblib.Parallel(n_jobs=2)(
        [joblib.delayed(_build)(flat[0], x, x**2)]
    )
    assert built is not flat[0]
    assert built.figure is not fig

    fig.adopt_axes(built)
    assert fig.axes[0]._title == "built in a subprocess"
    for i in (1, 2, 3):
        assert fig.axes[i]._title == f"pre {i}"
        assert fig.axes[i]._rect == other_rects[i]

    fig.tight_layout()
    fig.to_svg()


def test_adopt_axes_supports_the_dict_kwargs_worker_pattern():
    """The documented pattern end to end: a dict of per-panel kwargs
    (ax/data/title) fed to one function via **kwargs, dispatched through
    joblib, merged back with adopt_axes() -- and the SAME function
    called directly (no joblib) for live debugging, unchanged."""

    def analyze_panel(ax, x, y, title):
        coeffs = np.polyfit(x, y, deg=1)
        ax.scatter(x, y)
        ax.plot(x, np.polyval(coeffs, x), color="red")
        ax.set_title(f"{title} slope={coeffs[0]:.1f}")
        return ax

    rng = np.random.default_rng(0)
    fig, axes = plotpress.subplots(1, 2, figsize=(8, 4))
    x = np.linspace(0, 5, 20)
    panels = {
        "a": {"ax": axes[0], "x": x, "y": 2 * x + rng.normal(size=x.shape), "title": "a"},
        "b": {"ax": axes[1], "x": x, "y": -3 * x + rng.normal(size=x.shape), "title": "b"},
    }

    built = joblib.Parallel(n_jobs=2)(
        joblib.delayed(analyze_panel)(**kw) for kw in panels.values()
    )
    for built_ax in built:
        fig.adopt_axes(built_ax)
    fig.tight_layout()
    svg = fig.to_svg()
    # Not an exact fitted value -- noise moves it -- just that each panel's
    # own distinct, independently-computed title made it into the render.
    assert "a slope=" in svg
    assert "b slope=" in svg
    assert "a slope=" in fig.axes[0]._title
    assert "b slope=" in fig.axes[1]._title

    # -- the same function, called directly: no joblib, no adopt_axes --
    dbg_fig, dbg_ax = plotpress.subplots()
    analyze_panel(dbg_ax, x, 5 * x + rng.normal(size=x.shape), "debug")
    assert "debug slope=" in dbg_fig.to_svg()
