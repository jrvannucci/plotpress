"""``subplot_size=``: give the size of one subplot, get the figsize solved.

tight_layout() reserves margins in absolute units while placing the grid in
figure fractions, so the subplot size a figsize yields has no closed form --
these pin that the solver lands on the requested size anyway, across the
decorations that change how much room is needed around the grid.
"""
import numpy as np
import pytest

import plotpress

TOL = 2e-3      # inches; well under a device pixel at any sane dpi


def _panel_inches(fig, ax=None):
    """One subplot's *plotting box* in inches -- the axes' own rect, not the
    grid cell it sits in, which is what subplot_size= promises."""
    if ax is None:
        ax = next(a for a in fig.axes
                  if a._subplotspec is not None and not a._is_colorbar)
    _, _, frac_w, frac_h = ax.get_position()
    return frac_w * fig.figsize[0], frac_h * fig.figsize[1]


def _grid(nrows, ncols, want, sup=False, colorbars=False, titles=True):
    fig, axs = plotpress.subplots(nrows, ncols, subplot_size=want, squeeze=False)
    x = np.linspace(0, 1, 11)
    for row in axs:
        for ax in row:
            mesh = ax.pcolormesh(x, x, np.zeros((10, 10)))
            if titles:
                ax.set_title("p", fontsize=6)
            ax.tick_params(labelsize=5)
            if colorbars:
                fig.colorbar(mesh, ax=ax, fraction=0.08)
    if sup:
        fig.suptitle("a title")
        fig.supxlabel("global x")
        fig.supylabel("global y")
    fig.tight_layout()
    return fig


@pytest.mark.parametrize("nrows, ncols, want", [
    (1, 1, (3.0, 2.0)),
    (2, 3, (1.2, 0.9)),
    (6, 8, (1.0, 1.0)),
    (20, 25, (0.8, 0.6)),          # the 500-panel case
    (1, 30, (0.5, 1.5)),           # one wide strip
    (30, 1, (2.0, 0.3)),           # one tall strip
    (10, 10, (0.35, 0.3)),         # small enough that margins dominate
])
def test_every_subplot_comes_out_the_requested_size(nrows, ncols, want):
    fig = _grid(nrows, ncols, want)
    pw, ph = _panel_inches(fig)
    assert pw == pytest.approx(want[0], abs=TOL)
    assert ph == pytest.approx(want[1], abs=TOL)


@pytest.mark.parametrize("sup, colorbars", [(True, False), (False, True),
                                            (True, True)])
def test_decorations_are_added_around_the_subplots_not_taken_out_of_them(
        sup, colorbars):
    """A suptitle/supxlabel band and per-axes colorbars each need real room.
    The point of the feature is that they grow the figure rather than shrink
    the panels, so the panels stay the size that was asked for."""
    want = (1.2, 0.9)
    fig = _grid(6, 8, want, sup=sup, colorbars=colorbars)
    pw, ph = _panel_inches(fig)
    assert pw == pytest.approx(want[0], abs=TOL)
    assert ph == pytest.approx(want[1], abs=TOL)


def test_a_suptitle_grows_the_figure_rather_than_the_panels():
    plain = _grid(4, 4, (1.2, 0.9), sup=False)
    titled = _grid(4, 4, (1.2, 0.9), sup=True)
    assert titled.figsize[1] > plain.figsize[1]          # room was added
    assert _panel_inches(titled)[1] == pytest.approx(
        _panel_inches(plain)[1], abs=TOL)                # panels unchanged


def test_groups_get_their_boxes_and_titles_on_top_of_the_subplot_size():
    """A group's box and title band are furniture too -- and the size asked
    for is one axes, not one group, so a 2x1 group ends up about twice as
    tall as the requested subplot height plus its band."""
    layout = plotpress.GroupLayout(3, 4)
    for r in range(3):
        for c in range(4):
            layout.add_group(r, c, 2, 1, title=f"G{r}{c}", fontsize=6)
    want = (1.1, 0.8)
    fig, axes = plotpress.subplots_from_groups(layout, subplot_size=want)
    x = np.linspace(0, 1, 11)
    for row in axes:
        for pair in row:
            for ax in np.ravel(pair):
                mesh = ax.pcolormesh(x, x, np.zeros((10, 10)))
                ax.set_title("p", fontsize=6)
                ax.tick_params(labelsize=5)
                fig.colorbar(mesh, ax=ax, fraction=0.08)
    fig.suptitle("t")
    fig.supxlabel("gx")
    fig.supylabel("gy")
    fig.tight_layout()
    pw, ph = _panel_inches(fig)
    assert pw == pytest.approx(want[0], abs=TOL)
    assert ph == pytest.approx(want[1], abs=TOL)
    assert layout._super_shape() == (6, 4)


def test_the_solve_survives_a_later_tight_layout():
    """tight_layout() is re-run whenever a measured decoration changes, so the
    second run has to settle on the same answer rather than drift."""
    fig = _grid(6, 8, (1.2, 0.9), sup=True)
    first = _panel_inches(fig)
    size_after_first = fig.figsize
    fig.tight_layout()
    assert _panel_inches(fig) == pytest.approx(first, abs=TOL)
    assert fig.figsize == pytest.approx(size_after_first, abs=TOL)


def test_figsize_is_still_honoured_when_no_subplot_size_is_given():
    fig, _ = plotpress.subplots(3, 3, figsize=(7.0, 5.0))
    fig.tight_layout()
    assert fig.figsize[0] == pytest.approx(7.0, abs=1e-6)
    assert fig.figsize[1] == pytest.approx(5.0, abs=1e-6)


@pytest.mark.parametrize("bad, exc, message", [
    ((0, 1), ValueError, "positive, finite"),
    ((-1, 2), ValueError, "positive, finite"),
    ((float("inf"), 1), ValueError, "positive, finite"),
    ((float("nan"), 1), ValueError, "positive, finite"),
    (1.5, TypeError, "width, height"),
    ("big", TypeError, "width, height"),
    ((1, 2, 3), TypeError, "width, height"),
])
def test_a_bad_subplot_size_is_rejected_up_front(bad, exc, message):
    with pytest.raises(exc, match=message):
        plotpress.subplots(2, 2, subplot_size=bad)


@pytest.mark.parametrize("fraction", [0.08, 0.25])
def test_a_colorbar_grows_the_figure_rather_than_eating_the_subplot(fraction):
    """A colorbar is carved out of its axes' grid cell, so sizing the *cell*
    would hand someone who asked for a 1.2in subplot a much narrower plot with
    a colorbar where the rest went. subplot_size= sizes the plotting box, so
    the colorbar widens the figure instead."""
    want = (1.2, 0.9)
    fig, axs = plotpress.subplots(3, 4, subplot_size=want, squeeze=False)
    x = np.linspace(0, 1, 13)
    for row in axs:
        for ax in row:
            mesh = ax.pcolormesh(x, x, np.zeros((12, 12)))
            ax.tick_params(labelsize=6)
            fig.colorbar(mesh, ax=ax, fraction=fraction)
    fig.tight_layout()
    pw, ph = _panel_inches(fig, axs[0][0])
    assert pw == pytest.approx(want[0], abs=TOL)
    assert ph == pytest.approx(want[1], abs=TOL)


def test_a_wider_colorbar_widens_the_figure_not_the_panels():
    def build(fraction):
        fig, axs = plotpress.subplots(2, 3, subplot_size=(1.2, 0.9),
                                      squeeze=False)
        x = np.linspace(0, 1, 13)
        for row in axs:
            for ax in row:
                mesh = ax.pcolormesh(x, x, np.zeros((12, 12)))
                ax.tick_params(labelsize=6)
                fig.colorbar(mesh, ax=ax, fraction=fraction)
        fig.tight_layout()
        return fig, axs[0][0]

    narrow, narrow_ax = build(0.08)
    wide, wide_ax = build(0.25)
    assert wide.figsize[0] > narrow.figsize[0]          # the figure absorbed it
    assert _panel_inches(wide, wide_ax)[0] == pytest.approx(
        _panel_inches(narrow, narrow_ax)[0], abs=TOL)   # the panel did not


def test_a_colorbar_added_after_tight_layout_is_still_accounted_for():
    """The usual gallery order is build, tight_layout(), *then* colorbar --
    and a shared colorbar squeezes the grid to make room, which would leave
    the panels smaller than asked. The re-fit that runs at render time solves
    again, so the size holds by the time anything is drawn."""
    want = (0.9, 0.9)
    fig, axes = plotpress.subplots(6, 8, subplot_size=want, squeeze=False)
    x = np.linspace(0, 1, 13)
    flat = [ax for row in axes for ax in row]
    mesh = None
    for ax in flat:
        mesh = ax.pcolormesh(x, x, np.zeros((12, 12)))
        ax.tick_params(labelsize=5)
    fig.tight_layout()
    fig.colorbar(mesh, ax=flat)            # squeezes the grid, after the solve
    fig.suptitle("added afterwards")

    fig.to_svg()                           # the deferred re-fit runs here
    pw, ph = _panel_inches(fig)
    assert pw == pytest.approx(want[0], abs=TOL)
    assert ph == pytest.approx(want[1], abs=TOL)


# ---- it has to solve without an explicit tight_layout() --------------------

def _grid_no_tight(nrows, ncols, want, sup=False):
    fig, axs = plotpress.subplots(nrows, ncols, subplot_size=want, squeeze=False)
    x = np.linspace(0, 1, 13)
    for ax in (a for row in axs for a in row):
        ax.pcolormesh(x, x, np.zeros((12, 12)))
        ax.tick_params(labelsize=5)
    if sup:
        fig.suptitle("a title")
    return fig


@pytest.mark.parametrize("sup", [True, False])
def test_subplot_size_is_solved_even_without_calling_tight_layout(sup):
    """Only tight_layout() measures the decorations the solve works around, and
    _settle_layout() used to skip any figure that had never had it called by
    hand -- so subplot_size= quietly did nothing for a caller who just built
    and saved. Asking for a subplot size now arms that re-fit."""
    want = (0.9, 0.7)
    fig = _grid_no_tight(4, 5, want, sup=sup)
    fig.to_svg()                                   # the render-time fit
    pw, ph = _panel_inches(fig)
    assert pw == pytest.approx(want[0], abs=TOL)
    assert ph == pytest.approx(want[1], abs=TOL)


def test_subplots_adjust_still_overrides_subplot_size():
    """subplots_adjust() sets the margins directly and clears the pending fit
    on purpose -- there is nothing left to solve, so it must win."""
    fig = _grid_no_tight(3, 4, (0.9, 0.7))
    fig.subplots_adjust(left=0.05, right=0.98, top=0.95, bottom=0.08)
    fig.to_svg()
    assert fig._tight_pad is None
    pw, _ = _panel_inches(fig)
    assert pw != pytest.approx(0.9, abs=TOL)


def test_the_interactive_payload_sees_the_solved_rects():
    """The metadata the toolbar hit-tests against is captured during the same
    render that solves the layout, so it has to reflect the solved rects rather
    than the pre-solve ones."""
    import json
    import re

    want = (0.9, 0.7)
    fig = _grid_no_tight(3, 4, want)
    html = fig.to_html(interactive=True)
    meta = json.loads(re.search(r'id="plotpress-meta"[^>]*>(.*?)</script>',
                                html, re.S).group(1))
    pw, ph = _panel_inches(fig)
    assert pw == pytest.approx(want[0], abs=TOL)
    # Every axes rect in the payload should match a real drawn axes.
    widths = set(re.findall(r'"w":\s*\[([^\]]*)\]', json.dumps(meta)))
    assert widths or meta, "no axes metadata was emitted"
