"""simpleplot's defining property: no global state. Figures are fully independent."""

import numpy as np
import pytest

import simpleplot


def test_no_pyplot_or_current_figure():
    # There must be no global "current figure/axes" or global rcParams.
    assert not hasattr(simpleplot, "pyplot")
    assert not hasattr(simpleplot, "gcf")
    assert not hasattr(simpleplot, "gca")
    assert not hasattr(simpleplot, "rcParams")


def test_two_figures_are_independent():
    f1, a1 = simpleplot.subplots()
    f2, a2 = simpleplot.subplots()
    a1.plot([0, 1, 2], [0, 1, 2])
    assert len(a1.artists) == 1
    assert len(a2.artists) == 0  # f2 untouched by drawing on f1


def test_style_is_per_figure():
    f1 = simpleplot.Figure()
    f2 = simpleplot.Figure()
    f1.style.line_width = 99.0
    assert f2.style.line_width != 99.0  # styles are not shared


def test_style_copy_does_not_mutate_source():
    base = simpleplot.Style()
    variant = base.copy(line_width=42.0)
    assert base.line_width != 42.0
    assert variant.line_width == 42.0
    # Color cycle must be a distinct list, not a shared reference.
    variant.color_cycle.append("#000000")
    assert "#000000" not in base.color_cycle


def test_a_norm_is_not_mutated_by_the_artists_it_is_given_to():
    """Autoscaling writes vmin/vmax back, so a norm reused across figures used
    to stay pinned to whichever data reached it first."""
    norm = simpleplot.Normalize()

    f1, a1 = simpleplot.subplots()
    a1.pcolormesh(np.arange(9.0).reshape(3, 3), norm=norm)
    f1.to_svg()
    assert norm.vmin is None and norm.vmax is None

    f2, a2 = simpleplot.subplots()
    mesh = a2.pcolormesh(np.arange(9.0).reshape(3, 3) * 100, norm=norm)
    f2.to_svg()
    assert norm.vmin is None and norm.vmax is None
    # ...and the second figure scaled to its own data, not the first's.
    assert (mesh.norm.vmin, mesh.norm.vmax) == (0.0, 800.0)


def test_norm_with_explicit_limits_still_puts_artists_on_one_scale():
    shared = simpleplot.Normalize(0, 100)
    _, axes = simpleplot.subplots(1, 2)
    a = axes[0].pcolormesh(np.arange(9.0).reshape(3, 3), norm=shared)
    b = axes[1].pcolormesh(np.arange(9.0).reshape(3, 3) * 1000, norm=shared)
    assert (a.norm.vmin, a.norm.vmax) == (b.norm.vmin, b.norm.vmax) == (0, 100)
    assert (shared.vmin, shared.vmax) == (0, 100)


@pytest.mark.parametrize("norm,attr,value", [
    (simpleplot.LogNorm(), None, None),
    (simpleplot.PowerNorm(0.4), "gamma", 0.4),
    (simpleplot.SymLogNorm(1.5), "linthresh", 1.5),
])
def test_norm_subclasses_survive_being_copied_per_artist(norm, attr, value):
    _, ax = simpleplot.subplots()
    mesh = ax.pcolormesh(np.arange(1.0, 10.0).reshape(3, 3), norm=norm)
    assert type(mesh.norm) is type(norm)
    if attr is not None:
        assert getattr(mesh.norm, attr) == value
    assert norm.vmin is None          # the caller's instance stays pristine


def test_scatter_and_imshow_norms_are_private_too():
    norm = simpleplot.Normalize()
    for draw in (lambda ax: ax.scatter([0, 1], [0, 1], c=[5.0, 50.0], norm=norm),
                 lambda ax: ax.imshow(np.arange(9.0).reshape(3, 3), norm=norm)):
        fig, ax = simpleplot.subplots()
        draw(ax)
        fig.to_svg()
    assert norm.vmin is None and norm.vmax is None


def test_color_cycle_is_per_axes():
    _, ax = simpleplot.subplots()
    l1 = ax.plot([0, 1], [0, 1])
    l2 = ax.plot([0, 1], [1, 2])
    assert l1.color != l2.color  # cycle advances
