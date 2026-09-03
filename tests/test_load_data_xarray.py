"""plotpress.load_data_xarray(): a uniform grid of recovered data as one
labeled xarray.Dataset, instead of load_data()'s title-keyed dict of dicts.

Needs the optional ``xarray`` extra -- ``pytest.importorskip`` at the top
of every test, so a plain install still runs the rest of the suite.
"""
import numpy as np
import pytest

import plotpress

xr = pytest.importorskip("xarray")


def test_mesh_grid_with_a_shared_xy_grid(tmp_path):
    fig, axes = plotpress.subplots(2, 3, figsize=(9.0, 6.0))
    x = np.linspace(0, 10, 21)
    y = np.linspace(0, 5, 11)
    X, Y = np.meshgrid(x, y)
    grid = np.asarray(axes)
    for i, ax in enumerate(grid.ravel()):
        Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
        ax.pcolormesh(x, y, Z, cmap="viridis")
        ax.set_title(f"panel {i}")
        ax.set_xlabel("t"); ax.set_ylabel("depth")
    p = tmp_path / "mesh_shared.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    assert dict(ds.sizes) == {"row": 2, "col": 3, "y": 11, "x": 21}
    assert set(ds.data_vars) == {"z"}
    # x/y are shared 1-D coordinates, not per-panel, since every panel used
    # the identical grid.
    assert ds["x"].dims == ("x",) and ds["y"].dims == ("y",)
    assert np.allclose(ds["x"].values, x) and np.allclose(ds["y"].values, y)

    for r in range(2):
        for c in range(3):
            i = r * 3 + c
            Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
            assert np.allclose(ds["z"].values[r, c], Z, atol=1e-5), (
                "z at (%d, %d) must match panel %d's own mesh" % (r, c, i))
            assert ds["title"].values[r, c] == f"panel {i}"
    assert (ds["xlabel"].values == "t").all()
    assert (ds["ylabel"].values == "depth").all()
    assert ds.attrs["figsize"] == [9.0, 6.0]


def test_mesh_grid_with_differing_xy_per_panel(tmp_path):
    """Same shape everywhere (required), but each panel used its own x
    range -- x/y must come back as per-panel (row, col, x)/(row, col, y)
    coordinates instead of one shared 1-D array."""
    fig, axes = plotpress.subplots(1, 2)
    x0, y0 = np.linspace(0, 10, 5), np.linspace(0, 5, 4)
    x1, y1 = np.linspace(0, 20, 5), np.linspace(0, 5, 4)   # same shape, different range
    Z0 = np.arange(12.0).reshape(3, 4)
    Z1 = Z0 + 100.0
    axes[0].pcolormesh(x0, y0, Z0)
    axes[1].pcolormesh(x1, y1, Z1)
    p = tmp_path / "mesh_differing.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    assert ds["x"].dims == ("row", "col", "x")
    assert ds["y"].dims == ("row", "col", "y")
    assert np.allclose(ds["z"].values[0, 0], Z0)
    assert np.allclose(ds["z"].values[0, 1], Z1)
    xc0 = (x0[:-1] + x0[1:]) / 2
    xc1 = (x1[:-1] + x1[1:]) / 2
    assert np.allclose(ds["x"].values[0, 0], xc0)
    assert np.allclose(ds["x"].values[0, 1], xc1)


def test_line_grid_with_a_shared_x(tmp_path):
    fig, axes = plotpress.subplots(2, 2)
    x = np.linspace(0, 10, 50)
    grid = np.asarray(axes)
    for i, ax in enumerate(grid.ravel()):
        ax.plot(x, np.sin(x + i))
        ax.set_title(f"p{i}")
    p = tmp_path / "line_shared.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    assert dict(ds.sizes) == {"row": 2, "col": 2, "point": 50}
    assert set(ds.data_vars) == {"y"}
    assert ds["point"].dims == ("point",)
    assert np.allclose(ds["point"].values, x, atol=1e-5)
    for r in range(2):
        for c in range(2):
            i = r * 2 + c
            assert np.allclose(ds["y"].values[r, c], np.sin(x + i), atol=1e-5)


def test_line_grid_with_differing_x_per_panel(tmp_path):
    fig, axes = plotpress.subplots(1, 2)
    x0 = np.linspace(0, 10, 20)
    x1 = np.linspace(5, 15, 20)   # same length, different range
    axes[0].plot(x0, x0 * 2)
    axes[1].plot(x1, x1 * 3)
    p = tmp_path / "line_differing.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    assert ds["x"].dims == ("row", "col", "point")
    assert np.allclose(ds["y"].values[0, 0], x0 * 2, atol=1e-4)
    assert np.allclose(ds["y"].values[0, 1], x1 * 3, atol=1e-4)
    assert np.allclose(ds["x"].values[0, 0], x0, atol=1e-5)
    assert np.allclose(ds["x"].values[0, 1], x1, atol=1e-5)


@pytest.mark.parametrize("build,match", [
    (lambda fig, ax: (ax.plot([0, 1], [0, 1], label="a"),
                      ax.plot([0, 1], [1, 0], label="b")),
     "2 series, 0 mesh"),
    (lambda fig, ax: (ax.pcolormesh(np.zeros((2, 2))),
                      ax.plot([0, 1], [0, 1])),
     "1 series, 1 mesh"),
], ids=["two_series_one_axes", "mesh_and_series_one_axes"])
def test_more_than_one_plot_kind_on_a_single_axes_raises(tmp_path, build, match):
    fig, ax = plotpress.subplots()
    build(fig, ax)
    p = tmp_path / "bad_axes.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match=match):
        plotpress.load_data_xarray(str(p))


def test_mixed_mesh_and_line_grid_raises(tmp_path):
    fig, axes = plotpress.subplots(1, 2)
    axes[0].pcolormesh(np.zeros((3, 3)))
    axes[1].plot([0, 1], [0, 1])
    p = tmp_path / "mixed.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match="mix of mesh axes and line-series axes"):
        plotpress.load_data_xarray(str(p))


def test_row_or_column_span_raises(tmp_path):
    fig = plotpress.Figure()
    gs = fig.add_gridspec(2, 2)
    ax_top = fig.add_subplot(gs[0, :])
    ax_top.plot([0, 1], [0, 1])
    ax_bl = fig.add_subplot(gs[1, 0]); ax_bl.plot([0, 1], [0, 1])
    ax_br = fig.add_subplot(gs[1, 1]); ax_br.plot([0, 1], [0, 1])
    p = tmp_path / "span.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match="row/column span"):
        plotpress.load_data_xarray(str(p))


def test_mesh_shape_mismatch_across_panels_raises(tmp_path):
    fig, axes = plotpress.subplots(1, 2)
    axes[0].pcolormesh(np.zeros((3, 4)))
    axes[1].pcolormesh(np.zeros((3, 5)))
    p = tmp_path / "shape_mismatch.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match="meshes differ in shape"):
        plotpress.load_data_xarray(str(p))


def test_line_length_mismatch_across_panels_raises(tmp_path):
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot(np.linspace(0, 10, 20), np.linspace(0, 10, 20))
    axes[1].plot(np.linspace(0, 10, 30), np.linspace(0, 10, 30))
    p = tmp_path / "length_mismatch.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match="series differ in length"):
        plotpress.load_data_xarray(str(p))


def test_curvilinear_mesh_raises(tmp_path):
    fig, ax = plotpress.subplots()
    xg, yg = np.meshgrid(np.linspace(0, 1, 4), np.linspace(0, 1, 3))
    xg = xg + 0.05 * yg   # break separability -- a plain meshgrid() of two
                          # 1-D arrays auto-collapses back to rectilinear
                          # (see artists.py's _as_rectilinear_1d), so this
                          # needs a genuine warp to stay curvilinear
    ax.pcolormesh(xg, yg, np.arange(6.0).reshape(2, 3))
    p = tmp_path / "curvilinear.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match="curvilinear"):
        plotpress.load_data_xarray(str(p))


def test_freeform_axes_with_no_grid_cell_raises(tmp_path):
    fig = plotpress.Figure()
    ax = fig.add_axes((0.1, 0.1, 0.8, 0.8))
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "freeform.html"
    fig.save(str(p), interactive=True)
    with pytest.raises(ValueError, match="no recorded grid cell"):
        plotpress.load_data_xarray(str(p))


def test_multi_figure_report_needs_a_figure_selector(tmp_path):
    fig1, ax1 = plotpress.subplots()
    ax1.pcolormesh(np.zeros((3, 3)))
    fig2, ax2 = plotpress.subplots()
    ax2.pcolormesh(np.ones((3, 3)) * 50)
    report = plotpress.Report()
    report.add(fig1, title="First")
    report.add(fig2, title="Second")
    p = tmp_path / "report.html"
    report.save(str(p))

    with pytest.raises(ValueError, match="this file has 2 figures"):
        plotpress.load_data_xarray(str(p))

    ds_by_index = plotpress.load_data_xarray(str(p), figure=1)
    ds_by_title = plotpress.load_data_xarray(str(p), figure="Second")
    assert ds_by_index["z"].values[0, 0, 0, 0] == 50.0
    assert ds_by_title["z"].values[0, 0, 0, 0] == 50.0
    assert ds_by_index.attrs["title"] == "Second"

    with pytest.raises(ValueError, match="no figure titled"):
        plotpress.load_data_xarray(str(p), figure="Nope")
    with pytest.raises(ValueError, match="figure index 5 out of range"):
        plotpress.load_data_xarray(str(p), figure=5)


def test_missing_xarray_raises_a_clear_import_error(tmp_path, monkeypatch):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    p = tmp_path / "no_xarray.html"
    fig.save(str(p), interactive=True)

    import builtins
    real_import = builtins.__import__

    def blocked(name, *a, **kw):
        if name == "xarray":
            raise ImportError("simulated: xarray not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ImportError, match=r"pip install plotpress\[xarray\]"):
        plotpress.load_data_xarray(str(p))


def test_missing_subplots_come_back_nan_with_has_data_false(tmp_path):
    """A grid cell with nothing plotted on it (or no axes at all) used to
    make load_data_xarray() refuse the whole figure -- it now comes back
    NaN, distinguished from a panel whose real data legitimately happened
    to be all-NaN by the has_data coordinate."""
    fig, axes = plotpress.subplots(2, 2, figsize=(6.0, 6.0))
    x = np.linspace(0, 10, 5)
    y = np.linspace(0, 5, 4)
    Z = np.arange(12.0).reshape(3, 4)
    axes[0, 0].pcolormesh(x, y, Z)
    axes[0, 0].set_title("filled")
    axes[1, 0].pcolormesh(x, y, Z + 100.0)
    axes[1, 0].set_title("also filled")
    # (0, 1) and (1, 1) are left entirely unplotted.
    p = tmp_path / "mesh_with_gaps.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    assert dict(ds.sizes) == {"row": 2, "col": 2, "y": 3, "x": 4}
    assert ds["has_data"].values.tolist() == [[True, False], [True, False]]
    assert np.allclose(ds["z"].values[0, 0], Z)
    assert np.allclose(ds["z"].values[1, 0], Z + 100.0)
    assert np.isnan(ds["z"].values[0, 1]).all()
    assert np.isnan(ds["z"].values[1, 1]).all()
    assert ds["title"].values[0, 0] == "filled"
    assert ds["title"].values[0, 1] == ""   # missing panel, not None


def test_missing_subplots_in_a_line_grid_also_come_back_nan(tmp_path):
    fig, axes = plotpress.subplots(1, 3)
    x = np.linspace(0, 1, 5)
    axes[0].plot(x, x)
    axes[2].plot(x, x * 2)
    # axes[1] left unplotted.
    p = tmp_path / "line_with_gap.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    assert ds["has_data"].values.tolist() == [[True, False, True]]
    assert np.allclose(ds["y"].values[0, 0], x)
    assert np.isnan(ds["y"].values[0, 1]).all()
    assert np.allclose(ds["y"].values[0, 2], x * 2)


def test_attrs_layout_matches_load_data_and_feeds_subplots_from_layout(tmp_path):
    """The whole layout dict load_data() returns under "layout" is now also
    reachable straight off the Dataset -- no second, separate load_data()
    call (a second parse of the file) just to get it before replotting."""
    fig, axes = plotpress.subplots(1, 2, figsize=(8.0, 4.0))
    x = np.linspace(0, 1, 5)
    for i, ax in enumerate(axes):
        ax.plot(x, x * (i + 1))
        ax.set_title(f"panel {i}")
        ax.set_xlabel("t")
    p = tmp_path / "layout_attr.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    expected_layout = plotpress.load_data(str(p), by_index=True)[0]["layout"]
    assert ds.attrs["layout"] == expected_layout

    fig2, axes2 = plotpress.subplots_from_layout(ds.attrs["layout"])
    # squeezed to 1-D, same as plotpress.subplots(1, 2) itself would return.
    assert axes2.shape == (2,)
    assert axes2[0].get_title() == "panel 0"
    assert axes2[1].get_title() == "panel 1"
    assert axes2[0].get_xlabel() == "t"


def test_select_panel_by_title_drops_row_and_col(tmp_path):
    fig, axes = plotpress.subplots(2, 3, figsize=(9.0, 6.0))
    x = np.linspace(0, 10, 21)
    y = np.linspace(0, 5, 11)
    X, Y = np.meshgrid(x, y)
    grid = np.asarray(axes)
    for i, ax in enumerate(grid.ravel()):
        Z = np.sin(X - 0.3 * i) * np.exp(-0.05 * Y)
        ax.pcolormesh(x, y, Z, cmap="viridis")
        ax.set_title(f"panel {i}")
    p = tmp_path / "select_panel.html"
    fig.save(str(p), interactive=True)

    ds = plotpress.load_data_xarray(str(p))
    by_title = plotpress.select_panel(ds, title="panel 4")
    by_position = plotpress.select_panel(ds, row=1, col=1)   # panel 4 is (1, 1)

    assert "row" not in by_title.dims and "col" not in by_title.dims
    assert by_title["z"].dims == ("y", "x")
    assert by_title["title"].item() == "panel 4"
    assert np.array_equal(by_title["z"].values, by_position["z"].values)
    assert np.array_equal(by_title["z"].values, ds["z"].values[1, 1])


def test_select_panel_argument_errors(tmp_path):
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    axes[0].set_title("same")
    axes[1].set_title("same")   # deliberately not unique
    p = tmp_path / "select_panel_errors.html"
    fig.save(str(p), interactive=True)
    ds = plotpress.load_data_xarray(str(p))

    with pytest.raises(ValueError, match="no panel titled"):
        plotpress.select_panel(ds, title="nope")
    with pytest.raises(ValueError, match="not unique"):
        plotpress.select_panel(ds, title="same")
    with pytest.raises(ValueError, match="not both"):
        plotpress.select_panel(ds, title="same", row=0)
    with pytest.raises(ValueError, match="row=.*col="):
        plotpress.select_panel(ds)
    with pytest.raises(ValueError, match="row=.*col="):
        plotpress.select_panel(ds, row=0)   # col missing


def test_select_panel_multiple_returns_every_duplicate_as_a_list(tmp_path):
    fig, axes = plotpress.subplots(1, 3)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    axes[2].plot([0, 1], [0.5, 0.5])
    axes[0].set_title("dup")
    axes[1].set_title("dup")
    axes[2].set_title("unique")
    p = tmp_path / "select_panel_multiple.html"
    fig.save(str(p), interactive=True)
    ds = plotpress.load_data_xarray(str(p))

    dups = plotpress.select_panel(ds, title="dup", multiple=True)
    assert isinstance(dups, list) and len(dups) == 2
    assert [p["title"].item() for p in dups] == ["dup", "dup"]
    assert np.allclose(dups[0]["y"].values, [0, 1])
    assert np.allclose(dups[1]["y"].values, [1, 0])

    # multiple=True still returns a list even when exactly one thing matched
    # -- a unique title, or an explicit row=/col= -- so a caller looping
    # over the result never has to branch on how many actually matched.
    unique = plotpress.select_panel(ds, title="unique", multiple=True)
    assert isinstance(unique, list) and len(unique) == 1
    assert unique[0]["title"].item() == "unique"

    by_position = plotpress.select_panel(ds, row=0, col=2, multiple=True)
    assert isinstance(by_position, list) and len(by_position) == 1
    assert by_position[0]["title"].item() == "unique"
