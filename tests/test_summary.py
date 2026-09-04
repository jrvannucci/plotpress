"""Figure.print_layout_summary() / Axes.print_summary().

Both print to stdout and return None -- meant for a REPL/notebook, not
programmatic use (per their own docstrings) -- so these tests assert on
the printed text via ``capsys``, the same pattern ``test_performance.py``
already uses for a print-based method, rather than trying to parse a
return value that deliberately doesn't exist.
"""
import plotpress


def test_print_layout_summary_reports_grid_position_and_artists(capsys):
    fig, axes = plotpress.subplots(1, 2, figsize=(8.0, 4.0))
    axes[0].plot([0, 1, 2], [0, 1, 4])
    axes[0].set_title("left")
    axes[1].bar([0, 1, 2], [3, 7, 5])
    fig.print_layout_summary()
    out = capsys.readouterr().out
    assert "Figure: 2 axes (2 visible)" in out
    assert "Axes 0:" in out and "Axes 1:" in out
    assert "row 0, col 0 of a 1x2 grid" in out
    assert "row 0, col 1 of a 1x2 grid" in out
    assert "1 Line2D" in out
    assert "1 Bars" in out
    assert "'left'" in out   # title, repr'd
    assert "to_vega():      OK" in out
    assert "to_vega_lite(): OK" in out


def test_print_layout_summary_names_twin_and_legend_gap(capsys):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1], label="primary")
    ax.legend()
    ax2 = ax.twinx()
    ax2.plot([0, 1], [1, 0], color="red")
    fig.print_layout_summary()
    out = capsys.readouterr().out
    assert "twinx() overlay of axes 0" in out
    assert "to_vega():      1 gap(s)" in out
    assert "has a legend" in out
    # The twin itself has nothing unsupported on it.
    assert "Axes 1:\n  position:  twinx() overlay of axes 0" in out


def test_print_layout_summary_names_unsupported_artist_per_exporter(capsys):
    fig, ax = plotpress.subplots()
    ax.boxplot([[1, 2, 3, 4, 5]])
    fig.print_layout_summary()
    out = capsys.readouterr().out
    assert "[vega] figure_to_vega(): axes 0 has a BoxPlot" in out
    assert "[vega-lite] figure_to_vega_lite(): axes 0 has a BoxPlot" in out


def test_print_layout_summary_reports_figure_group_boxes(capsys):
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].plot([0, 1], [1, 0])
    fig.group("Panel A", list(axes))
    fig.print_layout_summary()
    out = capsys.readouterr().out
    assert "Figure.group() boxes: 'Panel A'" in out


def test_axes_print_summary_matches_the_figure_level_entry_for_that_axes(capsys):
    """Regression against divergence: the same axes must describe itself
    identically whether asked via fig.print_layout_summary() or its own
    ax.print_summary() -- both share _axes_summary_lines()."""
    fig, axes = plotpress.subplots(1, 2)
    axes[0].plot([0, 1], [0, 1])
    axes[1].scatter([0, 1, 2], [2, 1, 0])

    fig.print_layout_summary()
    fig_out = capsys.readouterr().out
    fig_axes1_block = fig_out.split("Axes 1:")[1]

    axes[1].print_summary()
    ax_out = capsys.readouterr().out
    assert ax_out.startswith("Axes 1:")
    ax_block = ax_out[len("Axes 1:"):]

    assert ax_block.strip() == fig_axes1_block.strip()


def test_axes_print_summary_reports_inset_position_and_caveat(capsys):
    fig, ax = plotpress.subplots()
    ax.plot([0, 1], [0, 1])
    inset = ax.inset_axes((0.6, 0.6, 0.3, 0.3))
    inset.plot([0, 1], [1, 0])
    inset.print_summary()
    out = capsys.readouterr().out
    assert "position:  inset of axes 0" in out
    assert "to_vega_lite(): 1 gap(s)" in out
    assert "is an inset_axes()" in out


def test_axes_print_summary_reports_log_scale_and_inversion(capsys):
    fig, ax = plotpress.subplots()
    ax.plot([1, 10, 100], [1, 2, 3])
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.print_summary()
    out = capsys.readouterr().out
    assert "x:  log," in out
    assert "y:  linear," in out and "(inverted)" in out
