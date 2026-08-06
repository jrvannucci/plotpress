Performance
===========

Every example in the plot-type :ref:`reference gallery <gallery>` serialized to static SVG and to self-contained interactive HTML, with output sizes. (The :ref:`real applications <applications>` gallery is not timed here: its figures are variations on the same shapes, and timing another hundred of them would treble the runtime without adding a row that says anything new.) Interactive HTML embeds the same SVG **plus** the per-axes data the toolbar needs for zoom / point-picking (the picked values, and mesh ``z`` grids), so it is larger and slower than SVG -- most for mesh-heavy figures.

Best of 5 runs, one machine. Regenerate with ``python benchmarks/example_timings.py``.

Against other libraries
-----------------------

The same four figures built and serialized to SVG by each library, using its own idiomatic API and no global state on any side. matplotlib goes through the object-oriented ``FigureCanvasSVG`` rather than ``pyplot``; xy renders headlessly through ``Chart.to_svg()``. xy facets by a data column rather than by an arbitrary grid, so its 8x8 case is 64 groups of one long-form table -- the idiomatic equivalent, not a handicap.

These measure **time to produce a static file**, which is the axis plotpress optimizes. It is not the axis xy optimizes: its Rust core decimates by screen resolution for *interactive* exploration of large data, and a single static render does not exercise that.

.. list-table::
   :header-rows: 1
   :widths: 30 16 16 16

   * - Scenario
     - plotpress
     - matplotlib
     - xy
   * - ``line_100k_points``
     - 10.6 ms
     - 64.7 ms
     - 3.1 ms
   * - ``scatter_5k_points``
     - 15.6 ms
     - 153.4 ms
     - 24.8 ms
   * - ``pcolormesh_300x300``
     - 10.9 ms
     - 6802.2 ms
     - 19.0 ms
   * - ``many_axes_8x8_grid``
     - 46.5 ms
     - 1864.2 ms
     - 66.9 ms

Per-example output
------------------

.. list-table::
   :header-rows: 1
   :widths: 34 8 12 12 12 12

   * - Example
     - Axes
     - SVG
     - SVG size
     - HTML
     - HTML size
   * - :ref:`plot_01_line <sphx_glr_auto_examples_plot_01_line.py>`
     - 1
     - 1.2 ms
     - 9 KiB
     - 1.9 ms
     - 59 KiB
   * - :ref:`plot_02_scatter <sphx_glr_auto_examples_plot_02_scatter.py>`
     - 1
     - 2.0 ms
     - 35 KiB
     - 2.4 ms
     - 87 KiB
   * - :ref:`plot_03_bar <sphx_glr_auto_examples_plot_03_bar.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.5 ms
     - 45 KiB
   * - :ref:`plot_04_barh <sphx_glr_auto_examples_plot_04_barh.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 45 KiB
   * - :ref:`plot_05_stem <sphx_glr_auto_examples_plot_05_stem.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.4 ms
     - 48 KiB
   * - :ref:`plot_06_step <sphx_glr_auto_examples_plot_06_step.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.5 ms
     - 45 KiB
   * - :ref:`plot_07_fill_between <sphx_glr_auto_examples_plot_07_fill_between.py>`
     - 1
     - 1.4 ms
     - 11 KiB
     - 2.0 ms
     - 62 KiB
   * - :ref:`plot_08_stackplot <sphx_glr_auto_examples_plot_08_stackplot.py>`
     - 1
     - 0.7 ms
     - 4 KiB
     - 0.9 ms
     - 47 KiB
   * - :ref:`plot_09_hist <sphx_glr_auto_examples_plot_09_hist.py>`
     - 1
     - 0.6 ms
     - 5 KiB
     - 0.8 ms
     - 48 KiB
   * - :ref:`plot_10_boxplot <sphx_glr_auto_examples_plot_10_boxplot.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.5 ms
     - 47 KiB
   * - :ref:`plot_11_errorbar <sphx_glr_auto_examples_plot_11_errorbar.py>`
     - 1
     - 0.5 ms
     - 5 KiB
     - 0.5 ms
     - 47 KiB
   * - :ref:`plot_12_violin <sphx_glr_auto_examples_plot_12_violin.py>`
     - 1
     - 1.7 ms
     - 10 KiB
     - 2.4 ms
     - 60 KiB
   * - :ref:`plot_13_eventplot <sphx_glr_auto_examples_plot_13_eventplot.py>`
     - 1
     - 1.4 ms
     - 16 KiB
     - 2.4 ms
     - 62 KiB
   * - :ref:`plot_14_hist2d <sphx_glr_auto_examples_plot_14_hist2d.py>`
     - 1
     - 1.0 ms
     - 6 KiB
     - 1.5 ms
     - 58 KiB
   * - :ref:`plot_15_pie <sphx_glr_auto_examples_plot_15_pie.py>`
     - 1
     - 0.1 ms
     - 1 KiB
     - 0.1 ms
     - 44 KiB
   * - :ref:`plot_16_imshow <sphx_glr_auto_examples_plot_16_imshow.py>`
     - 1
     - 2.1 ms
     - 15 KiB
     - 8.4 ms
     - 204 KiB
   * - :ref:`plot_17_pcolormesh <sphx_glr_auto_examples_plot_17_pcolormesh.py>`
     - 1
     - 4.3 ms
     - 13 KiB
     - 22.0 ms
     - 428 KiB
   * - :ref:`plot_18_contour <sphx_glr_auto_examples_plot_18_contour.py>`
     - 1
     - 36.1 ms
     - 87 KiB
     - 42.0 ms
     - 280 KiB
   * - :ref:`plot_19_quiver <sphx_glr_auto_examples_plot_19_quiver.py>`
     - 1
     - 2.2 ms
     - 27 KiB
     - 2.7 ms
     - 81 KiB
   * - :ref:`plot_20_subplots <sphx_glr_auto_examples_plot_20_subplots.py>`
     - 4
     - 2.7 ms
     - 23 KiB
     - 4.3 ms
     - 95 KiB
   * - :ref:`plot_21_loglog <sphx_glr_auto_examples_plot_21_loglog.py>`
     - 1
     - 1.1 ms
     - 6 KiB
     - 1.3 ms
     - 51 KiB
   * - :ref:`plot_22_annotations <sphx_glr_auto_examples_plot_22_annotations.py>`
     - 1
     - 0.9 ms
     - 6 KiB
     - 0.9 ms
     - 52 KiB
   * - :ref:`plot_24_contourf <sphx_glr_auto_examples_plot_24_contourf.py>`
     - 1
     - 23.4 ms
     - 12 KiB
     - 55.3 ms
     - 642 KiB
   * - :ref:`plot_25_hexbin <sphx_glr_auto_examples_plot_25_hexbin.py>`
     - 1
     - 15.9 ms
     - 63 KiB
     - 15.7 ms
     - 105 KiB
   * - :ref:`plot_26_twin_axes <sphx_glr_auto_examples_plot_26_twin_axes.py>`
     - 2
     - 2.0 ms
     - 12 KiB
     - 2.8 ms
     - 67 KiB
   * - :ref:`plot_27_curvilinear_mesh <sphx_glr_auto_examples_plot_27_curvilinear_mesh.py>`
     - 1
     - 308.1 ms
     - 41 KiB
     - 309.7 ms
     - 156 KiB
   * - :ref:`plot_28_gouraud <sphx_glr_auto_examples_plot_28_gouraud.py>`
     - 2
     - 211.0 ms
     - 289 KiB
     - 210.3 ms
     - 354 KiB
   * - :ref:`plot_29_reference_lines <sphx_glr_auto_examples_plot_29_reference_lines.py>`
     - 1
     - 2.3 ms
     - 16 KiB
     - 3.4 ms
     - 71 KiB
   * - :ref:`plot_30_lognorm <sphx_glr_auto_examples_plot_30_lognorm.py>`
     - 2
     - 8.5 ms
     - 28 KiB
     - 44.9 ms
     - 899 KiB
   * - :ref:`plot_31_shared_colorbar <sphx_glr_auto_examples_plot_31_shared_colorbar.py>`
     - 6
     - 5.2 ms
     - 21 KiB
     - 16.1 ms
     - 275 KiB
   * - :ref:`plot_32_broken_barh <sphx_glr_auto_examples_plot_32_broken_barh.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 0.5 ms
     - 45 KiB
   * - :ref:`plot_33_matshow <sphx_glr_auto_examples_plot_33_matshow.py>`
     - 1
     - 0.6 ms
     - 7 KiB
     - 0.8 ms
     - 51 KiB
   * - :ref:`plot_34_spy <sphx_glr_auto_examples_plot_34_spy.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 0.7 ms
     - 50 KiB
   * - :ref:`plot_35_stairs <sphx_glr_auto_examples_plot_35_stairs.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.7 ms
     - 46 KiB
   * - :ref:`plot_36_axline <sphx_glr_auto_examples_plot_36_axline.py>`
     - 1
     - 0.6 ms
     - 4 KiB
     - 0.8 ms
     - 48 KiB
   * - :ref:`scale/plot_01_many_axes <sphx_glr_auto_scale_plot_01_many_axes.py>`
     - 500
     - 564.7 ms
     - 2.7 MiB
     - 1054.3 ms
     - 11.3 MiB
   * - :ref:`scale/plot_02_million_point_line <sphx_glr_auto_scale_plot_02_million_point_line.py>`
     - 1
     - 210.7 ms
     - 46 KiB
     - 221.4 ms
     - 89 KiB
   * - :ref:`scale/plot_03_multimillion_mesh <sphx_glr_auto_scale_plot_03_multimillion_mesh.py>`
     - 1
     - 346.4 ms
     - 775 KiB
     - 403.1 ms
     - 1.3 MiB
   * - :ref:`scale/plot_04_thousand_series <sphx_glr_auto_scale_plot_04_thousand_series.py>`
     - 1
     - 951.8 ms
     - 6.9 MiB
     - 1421.7 ms
     - 17.2 MiB
   * - :ref:`scale/plot_05_axes_grid_lines <sphx_glr_auto_scale_plot_05_axes_grid_lines.py>`
     - 900
     - 22360.4 ms
     - 2.3 MiB
     - 42006.6 ms
     - 4.5 MiB
   * - :ref:`scale/plot_06_shared_colorbar_lognorm <sphx_glr_auto_scale_plot_06_shared_colorbar_lognorm.py>`
     - 144
     - 99.5 ms
     - 502 KiB
     - 254.3 ms
     - 4.0 MiB
   * - :ref:`scale/plot_07_matplotlib_comparison <sphx_glr_auto_scale_plot_07_matplotlib_comparison.py>`
     - 1
     - 1.0 ms
     - 5 KiB
     - 1.2 ms
     - 47 KiB
   * - :ref:`scale/plot_08_vector_over_raster <sphx_glr_auto_scale_plot_08_vector_over_raster.py>`
     - 1
     - 285.9 ms
     - 599 KiB
     - 339.6 ms
     - 1.4 MiB
   * - :ref:`scale/plot_09_output_scaling <sphx_glr_auto_scale_plot_09_output_scaling.py>`
     - 1
     - 1.8 ms
     - 6 KiB
     - 2.3 ms
     - 50 KiB

The ``scale/plot_01_many_axes`` row is the deliberate stress case: 500 independent pcolormesh axes on one figure. Its interactive HTML is dominated by the 500 embedded mesh ``z`` grids; lower ``fig.to_html(pick_precision=...)`` (or ``fig.save(..., pick_precision=...)``) to trade readout precision for a smaller file.
