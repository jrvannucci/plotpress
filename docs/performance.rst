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
     - 9.0 ms
     - 43.6 ms
     - 2.6 ms
   * - ``scatter_5k_points``
     - 14.9 ms
     - 117.0 ms
     - 22.0 ms
   * - ``pcolormesh_300x300``
     - 9.0 ms
     - 5688.0 ms
     - 15.9 ms
   * - ``many_axes_8x8_grid``
     - 36.7 ms
     - 1418.4 ms
     - 61.4 ms

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
   * - :ref:`pairwise/plot_01_line <sphx_glr_auto_examples_pairwise_plot_01_line.py>`
     - 1
     - 1.2 ms
     - 9 KiB
     - 1.7 ms
     - 63 KiB
   * - :ref:`pairwise/plot_02_scatter <sphx_glr_auto_examples_pairwise_plot_02_scatter.py>`
     - 1
     - 1.8 ms
     - 36 KiB
     - 2.4 ms
     - 91 KiB
   * - :ref:`pairwise/plot_03_bar <sphx_glr_auto_examples_pairwise_plot_03_bar.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.5 ms
     - 49 KiB
   * - :ref:`pairwise/plot_04_barh <sphx_glr_auto_examples_pairwise_plot_04_barh.py>`
     - 1
     - 0.2 ms
     - 3 KiB
     - 0.4 ms
     - 49 KiB
   * - :ref:`pairwise/plot_05_stem <sphx_glr_auto_examples_pairwise_plot_05_stem.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.4 ms
     - 52 KiB
   * - :ref:`pairwise/plot_06_step <sphx_glr_auto_examples_pairwise_plot_06_step.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 49 KiB
   * - :ref:`pairwise/plot_07_fill_between <sphx_glr_auto_examples_pairwise_plot_07_fill_between.py>`
     - 1
     - 1.3 ms
     - 11 KiB
     - 1.9 ms
     - 66 KiB
   * - :ref:`pairwise/plot_08_stackplot <sphx_glr_auto_examples_pairwise_plot_08_stackplot.py>`
     - 1
     - 0.5 ms
     - 4 KiB
     - 0.8 ms
     - 51 KiB
   * - :ref:`pairwise/plot_09_loglog <sphx_glr_auto_examples_pairwise_plot_09_loglog.py>`
     - 1
     - 1.0 ms
     - 6 KiB
     - 1.3 ms
     - 55 KiB
   * - :ref:`pairwise/plot_10_reference_lines <sphx_glr_auto_examples_pairwise_plot_10_reference_lines.py>`
     - 1
     - 1.9 ms
     - 16 KiB
     - 2.7 ms
     - 75 KiB
   * - :ref:`pairwise/plot_11_broken_barh <sphx_glr_auto_examples_pairwise_plot_11_broken_barh.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.8 ms
     - 49 KiB
   * - :ref:`pairwise/plot_12_stairs <sphx_glr_auto_examples_pairwise_plot_12_stairs.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 50 KiB
   * - :ref:`pairwise/plot_13_axline <sphx_glr_auto_examples_pairwise_plot_13_axline.py>`
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.6 ms
     - 51 KiB
   * - :ref:`distributions/plot_01_hist <sphx_glr_auto_examples_distributions_plot_01_hist.py>`
     - 1
     - 0.6 ms
     - 5 KiB
     - 0.8 ms
     - 52 KiB
   * - :ref:`distributions/plot_02_boxplot <sphx_glr_auto_examples_distributions_plot_02_boxplot.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.5 ms
     - 51 KiB
   * - :ref:`distributions/plot_03_errorbar <sphx_glr_auto_examples_distributions_plot_03_errorbar.py>`
     - 1
     - 0.4 ms
     - 5 KiB
     - 0.5 ms
     - 51 KiB
   * - :ref:`distributions/plot_04_violin <sphx_glr_auto_examples_distributions_plot_04_violin.py>`
     - 1
     - 1.6 ms
     - 10 KiB
     - 2.4 ms
     - 64 KiB
   * - :ref:`distributions/plot_05_eventplot <sphx_glr_auto_examples_distributions_plot_05_eventplot.py>`
     - 1
     - 1.4 ms
     - 16 KiB
     - 1.8 ms
     - 65 KiB
   * - :ref:`distributions/plot_06_hist2d <sphx_glr_auto_examples_distributions_plot_06_hist2d.py>`
     - 1
     - 0.8 ms
     - 6 KiB
     - 2.0 ms
     - 61 KiB
   * - :ref:`distributions/plot_07_pie <sphx_glr_auto_examples_distributions_plot_07_pie.py>`
     - 1
     - 0.1 ms
     - 1 KiB
     - 0.3 ms
     - 48 KiB
   * - :ref:`distributions/plot_08_hexbin <sphx_glr_auto_examples_distributions_plot_08_hexbin.py>`
     - 1
     - 14.8 ms
     - 63 KiB
     - 22.4 ms
     - 143 KiB
   * - :ref:`gridded_data/plot_01_imshow <sphx_glr_auto_examples_gridded_data_plot_01_imshow.py>`
     - 1
     - 1.9 ms
     - 15 KiB
     - 8.4 ms
     - 208 KiB
   * - :ref:`gridded_data/plot_02_pcolormesh <sphx_glr_auto_examples_gridded_data_plot_02_pcolormesh.py>`
     - 1
     - 3.3 ms
     - 13 KiB
     - 21.6 ms
     - 432 KiB
   * - :ref:`gridded_data/plot_03_contour <sphx_glr_auto_examples_gridded_data_plot_03_contour.py>`
     - 1
     - 32.6 ms
     - 87 KiB
     - 39.6 ms
     - 284 KiB
   * - :ref:`gridded_data/plot_04_quiver <sphx_glr_auto_examples_gridded_data_plot_04_quiver.py>`
     - 1
     - 2.1 ms
     - 27 KiB
     - 2.9 ms
     - 85 KiB
   * - :ref:`gridded_data/plot_05_contourf <sphx_glr_auto_examples_gridded_data_plot_05_contourf.py>`
     - 1
     - 19.7 ms
     - 12 KiB
     - 51.2 ms
     - 646 KiB
   * - :ref:`gridded_data/plot_06_curvilinear_mesh <sphx_glr_auto_examples_gridded_data_plot_06_curvilinear_mesh.py>`
     - 1
     - 288.5 ms
     - 41 KiB
     - 286.0 ms
     - 160 KiB
   * - :ref:`gridded_data/plot_07_gouraud <sphx_glr_auto_examples_gridded_data_plot_07_gouraud.py>`
     - 2
     - 197.7 ms
     - 289 KiB
     - 199.8 ms
     - 358 KiB
   * - :ref:`gridded_data/plot_08_lognorm <sphx_glr_auto_examples_gridded_data_plot_08_lognorm.py>`
     - 2
     - 7.5 ms
     - 28 KiB
     - 45.5 ms
     - 903 KiB
   * - :ref:`gridded_data/plot_09_matshow <sphx_glr_auto_examples_gridded_data_plot_09_matshow.py>`
     - 1
     - 0.6 ms
     - 7 KiB
     - 0.9 ms
     - 54 KiB
   * - :ref:`gridded_data/plot_10_spy <sphx_glr_auto_examples_gridded_data_plot_10_spy.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 0.9 ms
     - 54 KiB
   * - :ref:`multi_axes/plot_01_subplots <sphx_glr_auto_examples_multi_axes_plot_01_subplots.py>`
     - 4
     - 2.8 ms
     - 23 KiB
     - 4.5 ms
     - 99 KiB
   * - :ref:`multi_axes/plot_02_annotations <sphx_glr_auto_examples_multi_axes_plot_02_annotations.py>`
     - 1
     - 0.6 ms
     - 6 KiB
     - 0.9 ms
     - 56 KiB
   * - :ref:`multi_axes/plot_03_twin_axes <sphx_glr_auto_examples_multi_axes_plot_03_twin_axes.py>`
     - 2
     - 1.7 ms
     - 12 KiB
     - 2.5 ms
     - 71 KiB
   * - :ref:`multi_axes/plot_04_shared_colorbar <sphx_glr_auto_examples_multi_axes_plot_04_shared_colorbar.py>`
     - 6
     - 4.0 ms
     - 22 KiB
     - 15.0 ms
     - 280 KiB
   * - :ref:`animation/plot_01_plot_frames <sphx_glr_auto_examples_animation_plot_01_plot_frames.py>`
     - 1
     - 0.7 ms
     - 6 KiB
     - 4.2 ms
     - 116 KiB
   * - :ref:`animation/plot_02_pcolormesh_frames <sphx_glr_auto_examples_animation_plot_02_pcolormesh_frames.py>`
     - 4
     - 4.7 ms
     - 23 KiB
     - 69.9 ms
     - 409 KiB
   * - :ref:`scale/plot_01_many_axes <sphx_glr_auto_scale_plot_01_many_axes.py>`
     - 500
     - 411.8 ms
     - 2.7 MiB
     - 919.3 ms
     - 11.4 MiB
   * - :ref:`scale/plot_02_million_point_line <sphx_glr_auto_scale_plot_02_million_point_line.py>`
     - 1
     - 173.3 ms
     - 47 KiB
     - 193.8 ms
     - 93 KiB
   * - :ref:`scale/plot_03_multimillion_mesh <sphx_glr_auto_scale_plot_03_multimillion_mesh.py>`
     - 1
     - 332.4 ms
     - 775 KiB
     - 377.2 ms
     - 1.3 MiB
   * - :ref:`scale/plot_04_thousand_series <sphx_glr_auto_scale_plot_04_thousand_series.py>`
     - 1
     - 911.9 ms
     - 6.9 MiB
     - 1470.2 ms
     - 17.2 MiB
   * - :ref:`scale/plot_05_axes_grid_lines <sphx_glr_auto_scale_plot_05_axes_grid_lines.py>`
     - 900
     - 20513.6 ms
     - 2.4 MiB
     - 40011.8 ms
     - 4.7 MiB
   * - :ref:`scale/plot_06_shared_colorbar_lognorm <sphx_glr_auto_scale_plot_06_shared_colorbar_lognorm.py>`
     - 144
     - 80.1 ms
     - 508 KiB
     - 273.9 ms
     - 4.1 MiB
   * - :ref:`scale/plot_07_matplotlib_comparison <sphx_glr_auto_scale_plot_07_matplotlib_comparison.py>`
     - 1
     - 0.9 ms
     - 5 KiB
     - 1.1 ms
     - 51 KiB
   * - :ref:`scale/plot_08_vector_over_raster <sphx_glr_auto_scale_plot_08_vector_over_raster.py>`
     - 1
     - 268.6 ms
     - 599 KiB
     - 327.4 ms
     - 1.4 MiB
   * - :ref:`scale/plot_09_output_scaling <sphx_glr_auto_scale_plot_09_output_scaling.py>`
     - 1
     - 1.6 ms
     - 6 KiB
     - 1.9 ms
     - 54 KiB

The ``scale/plot_01_many_axes`` row is the deliberate stress case: 500 independent pcolormesh axes on one figure. Its interactive HTML is dominated by the 500 embedded mesh ``z`` grids; lower ``fig.to_html(pick_precision=...)`` (or ``fig.save(..., pick_precision=...)``) to trade readout precision for a smaller file, or cap the total embedded amount directly with ``pick_max_mesh_cells`` / ``pick_max_points`` -- a mesh over the cap is block-averaged down to it rather than dropped, so a click still answers with a real, if coarser, value.
