"""Figure.to_template()/figure_from_template(): reusable, data-free
template snapshots -- twin/secondary/spine/tick/style/id/colorbar
coverage, built standalone with no HTML export or plotted data involved.
(The HTML data round-trip -- load_data()/figure_from_template() -- uses
this exact same shape; see test_svg_output.py for that side.)"""

import json
import warnings

import numpy as np
import pytest

import plotpress
from plotpress.style import Style


def test_to_template_and_figure_from_template_round_trip_grid_and_groups():
    fig, axes = plotpress.subplots(1, 2, figsize=(9.0, 4.0))
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    axes[0].set_title("Left")
    axes[0].set_xlabel("x")
    axes[0].set_xlim(0, 5)
    fig.group("Pair", [axes[0], axes[1]], id="pair-1", color="blue",
             linestyle=":", pad=6.0)

    template = fig.to_template()
    fig2, axes2 = plotpress.figure_from_template(template)

    assert tuple(fig2.figsize) == (9.0, 4.0)
    assert len(fig2.axes) == 2
    assert axes2[0].get_title() == "Left"
    assert axes2[0].get_xlabel() == "x"
    assert axes2[0]._resolved_limits()[0] == (0.0, 5.0)
    [g] = fig2.get_groups()
    assert g.title == "Pair" and g.color == "blue" and g.linestyle == ":"
    assert fig2.get_group(id="pair-1").title == "Pair"


def test_to_template_round_trips_spines_tick_overrides_and_id():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_id("main")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_color("#123456")
    ax.spines["left"].set_linewidth(3.0)
    ax.spines["left"].set_alpha(0.4)
    ax.tick_params(axis="x", color="red", labelsize=8.0)
    ax.tick_params(axis="y", which="minor", width=2.0)
    ax.tick_top()
    ax.tick_right()
    ax.minorticks_on()

    fig2, ax2 = plotpress.figure_from_template(fig.to_template())

    assert fig2.get_ax(id="main") is ax2
    assert ax2.spines["top"].get_visible() is False
    assert ax2.spines["right"].get_color() == "#123456"
    assert ax2.spines["left"].get_linewidth() == 3.0
    assert ax2.spines["left"].get_alpha() == 0.4
    assert ax2._tick_overrides["x"]["spine_color"] == "red"
    assert ax2._tick_overrides["x"]["tick_label_size"] == 8.0
    assert ax2._minor_tick_overrides["y"]["tick_width"] == 2.0
    assert ax2._xtick_side == "top"
    assert ax2._ytick_side == "right"
    assert ax2._minor_ticks_on is True


def test_to_template_excludes_twins_and_secondaries_from_the_grid_axes():
    """Regression for the bug found while building this feature:
    layout_metadata()'s per-axes loop only excluded ax._subplotspec is None
    from "axes" -- but twinx()/twiny()/secondary_xaxis()/secondary_yaxis()
    all copy their *parent's* _subplotspec verbatim (so they stay aligned
    through tight_layout()), so a twin used to be captured as a second,
    unrelated grid axes at the exact same row/col as its parent instead of
    being excluded like the docstring always claimed."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    twin = ax.twinx()
    twin.plot([0, 1], [1, 0])
    sec = ax.secondary_xaxis("top")

    template = fig.to_template()
    assert set(template["axes"]) == {0}   # only the primary axes is a grid cell
    assert set(template["omitted_axes"]) == {1, 2}   # twin + secondary


def test_to_template_round_trips_a_twin_and_a_secondary_overlay():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_ylabel("primary y")
    twin = ax.twinx()
    twin.plot([0, 1], [10, 20])
    twin.set_ylabel("twin y")
    twin.set_ylim(0, 100)
    sec = ax.secondary_xaxis("top", label="secondary x")

    fig2, ax2 = plotpress.figure_from_template(fig.to_template())

    assert len(fig2.axes) == 3
    twin2 = [a for a in fig2.axes if a._twin_of is ax2][0]
    sec2 = [a for a in fig2.axes if a._secondary_of is ax2][0]
    assert twin2._twin_shared == "x"
    assert twin2.get_ylabel() == "twin y"
    assert twin2._resolved_limits()[1] == (0.0, 100.0)
    assert sec2._secondary_dim == "x"
    assert sec2._xtick_side == "top"
    assert sec2.get_xlabel() == "secondary x"


def test_figure_from_template_does_not_warn_about_overlays_or_insets():
    """A twin/secondary/inset is genuinely rebuilt (via "overlays"/"insets",
    not as a grid cell), unlike a truly lost freeform add_axes() rect --
    figure_from_template() must not claim it's "simply absent"."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    ax.twinx().plot([0, 1], [1, 0])
    ax.secondary_xaxis("top")
    ax.inset_axes((0.6, 0.6, 0.3, 0.3))

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig2, ax2 = plotpress.figure_from_template(fig.to_template())
    assert len(fig2.axes) == 4


def test_figure_from_template_rebuilds_an_overlay_whose_own_parent_is_an_overlay():
    """A secondary_yaxis()/twinx()/etc.'s own parent can itself be another
    overlay, not just a grid axes -- e.g. a secondary axis mirroring a
    twin's own (independent) y-limits. Each rebuilt overlay must be
    registered so a later overlay entry can resolve it as *its* parent."""
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    twin = ax.twinx()
    twin.plot([0, 1], [1, 0])
    twin.set_ylim(0, 50)
    nested = twin.secondary_yaxis("right")
    nested.set_ylabel("nested")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig2, ax2 = plotpress.figure_from_template(fig.to_template())

    assert len(fig2.axes) == 3
    twin2 = [a for a in fig2.axes if a._twin_of is ax2][0]
    nested2 = [a for a in fig2.axes if a._secondary_of is twin2][0]
    assert nested2.get_ylabel() == "nested"


def test_to_template_round_trips_an_inset_axes():
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    inset = ax.inset_axes((0.6, 0.6, 0.3, 0.3))
    inset.plot([0, 1], [1, 0])
    inset.set_title("zoom")

    fig2, ax2 = plotpress.figure_from_template(fig.to_template())

    assert len(fig2.axes) == 2
    inset2 = [a for a in fig2.axes if a._inset_parent is ax2][0]
    assert inset2._inset_bounds == (0.6, 0.6, 0.3, 0.3)
    assert inset2.get_title() == "zoom"


def test_to_template_captures_colorbar_styling_but_not_the_color_mapping():
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.arange(25, dtype=float).reshape(5, 5))
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.08, pad=0.03, label="units",
                        ticks=[0, 12, 24], format="%.1f")

    template = fig.to_template()
    [entry] = template["colorbars"]
    assert entry["parents"] == [0]
    assert entry["fraction"] == 0.08 and entry["pad"] == 0.03
    assert entry["label"] == "units"
    assert entry["ticks"] == [0, 12, 24]
    assert entry["format"] == "%.1f"
    # Round-trips through real JSON too -- the whole point of a template.
    json.dumps(template)


def test_to_template_warns_and_drops_a_callable_colorbar_format():
    fig, ax = plotpress.subplots()
    mesh = ax.pcolormesh(np.arange(25, dtype=float).reshape(5, 5))
    fig.colorbar(mesh, ax=ax, format=lambda v: f"{v:.0f}%")

    with pytest.warns(UserWarning, match="colorbar's format.*callable"):
        template = fig.to_template()
    assert template["colorbars"][0]["format"] is None
    json.dumps(template)   # still fully JSON-safe despite the drop


def test_to_template_round_trips_style():
    fig, ax = plotpress.subplots(style=Style(spine_color="#00ff00", dpi=150.0))
    ax.plot([0, 1], [0, 1])

    fig2, ax2 = plotpress.figure_from_template(fig.to_template())
    assert fig2.style.spine_color == "#00ff00"
    assert fig2.style.dpi == 150.0

    # An explicit style= override wins over the template's own saved style.
    fig3, ax3 = plotpress.figure_from_template(fig.to_template(), style=Style())
    assert fig3.style.spine_color == "#000000"


def test_figure_from_template_tolerates_a_template_missing_new_keys():
    """A hand-built or older-file dict lacking style/overlays/insets/
    colorbars (e.g. one saved before these fields existed) must still
    work -- every new field is optional, not required."""
    fig, ax = plotpress.subplots(1, 2)
    ax[0].plot([0, 1], [0, 1])
    ax[1].plot([0, 1], [1, 0])
    template = fig.to_template()
    for key in ("style", "overlays", "insets", "colorbars"):
        del template[key]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig2, axes2 = plotpress.figure_from_template(template)   # must not raise
    assert len(fig2.axes) == 2


def test_save_template_and_load_template_round_trip_through_a_json_file(tmp_path):
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    fig.group("G", [axes[0], axes[1]])
    p = tmp_path / "template.json"
    fig.save_template(str(p))

    saved = json.loads(p.read_text(encoding="utf-8"))
    # No plotted data anywhere in the file -- only structure/style keys,
    # never a per-axes "series"/"meshes"/"pies" the way load_data()'s own
    # payload carries.
    assert "series" not in saved and "meshes" not in saved
    for spec in saved["axes"].values():
        assert "series" not in spec and "meshes" not in spec and "pies" not in spec
    loaded = plotpress.load_template(str(p))
    fig2, axes2 = plotpress.figure_from_template(loaded)
    assert len(fig2.axes) == 2
    assert [g.title for g in fig2.get_groups()] == ["G"]
