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
     - 8.8 ms
     - 44.4 ms
     - 2.5 ms
   * - ``scatter_5k_points``
     - 15.4 ms
     - 121.7 ms
     - 22.4 ms
   * - ``pcolormesh_300x300``
     - 8.8 ms
     - 5801.1 ms
     - 16.7 ms
   * - ``many_axes_8x8_grid``
     - 38.4 ms
     - 1408.7 ms
     - 62.1 ms

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
     - 1.1 ms
     - 9 KiB
     - 1.9 ms
     - 61 KiB
   * - :ref:`pairwise/plot_02_scatter <sphx_glr_auto_examples_pairwise_plot_02_scatter.py>`
     - 1
     - 1.8 ms
     - 36 KiB
     - 2.5 ms
     - 88 KiB
   * - :ref:`pairwise/plot_03_bar <sphx_glr_auto_examples_pairwise_plot_03_bar.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 0.5 ms
     - 51 KiB
   * - :ref:`pairwise/plot_04_barh <sphx_glr_auto_examples_pairwise_plot_04_barh.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 51 KiB
   * - :ref:`pairwise/plot_05_stem <sphx_glr_auto_examples_pairwise_plot_05_stem.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.5 ms
     - 54 KiB
   * - :ref:`pairwise/plot_06_step <sphx_glr_auto_examples_pairwise_plot_06_step.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.5 ms
     - 51 KiB
   * - :ref:`pairwise/plot_07_fill_between <sphx_glr_auto_examples_pairwise_plot_07_fill_between.py>`
     - 1
     - 1.3 ms
     - 11 KiB
     - 2.1 ms
     - 64 KiB
   * - :ref:`pairwise/plot_08_stackplot <sphx_glr_auto_examples_pairwise_plot_08_stackplot.py>`
     - 1
     - 0.5 ms
     - 4 KiB
     - 0.8 ms
     - 53 KiB
   * - :ref:`pairwise/plot_09_loglog <sphx_glr_auto_examples_pairwise_plot_09_loglog.py>`
     - 1
     - 1.0 ms
     - 6 KiB
     - 1.5 ms
     - 55 KiB
   * - :ref:`pairwise/plot_10_reference_lines <sphx_glr_auto_examples_pairwise_plot_10_reference_lines.py>`
     - 1
     - 1.8 ms
     - 16 KiB
     - 2.8 ms
     - 72 KiB
   * - :ref:`pairwise/plot_11_broken_barh <sphx_glr_auto_examples_pairwise_plot_11_broken_barh.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.8 ms
     - 51 KiB
   * - :ref:`pairwise/plot_12_stairs <sphx_glr_auto_examples_pairwise_plot_12_stairs.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.5 ms
     - 51 KiB
   * - :ref:`pairwise/plot_13_axline <sphx_glr_auto_examples_pairwise_plot_13_axline.py>`
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.8 ms
     - 53 KiB
   * - :ref:`distributions/plot_01_hist <sphx_glr_auto_examples_distributions_plot_01_hist.py>`
     - 1
     - 0.6 ms
     - 5 KiB
     - 0.8 ms
     - 54 KiB
   * - :ref:`distributions/plot_02_boxplot <sphx_glr_auto_examples_distributions_plot_02_boxplot.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.6 ms
     - 53 KiB
   * - :ref:`distributions/plot_03_errorbar <sphx_glr_auto_examples_distributions_plot_03_errorbar.py>`
     - 1
     - 0.4 ms
     - 5 KiB
     - 0.6 ms
     - 53 KiB
   * - :ref:`distributions/plot_04_violin <sphx_glr_auto_examples_distributions_plot_04_violin.py>`
     - 1
     - 1.4 ms
     - 10 KiB
     - 2.5 ms
     - 62 KiB
   * - :ref:`distributions/plot_05_eventplot <sphx_glr_auto_examples_distributions_plot_05_eventplot.py>`
     - 1
     - 1.2 ms
     - 16 KiB
     - 1.9 ms
     - 66 KiB
   * - :ref:`distributions/plot_06_hist2d <sphx_glr_auto_examples_distributions_plot_06_hist2d.py>`
     - 1
     - 0.7 ms
     - 6 KiB
     - 1.5 ms
     - 59 KiB
   * - :ref:`distributions/plot_07_pie <sphx_glr_auto_examples_distributions_plot_07_pie.py>`
     - 1
     - 0.1 ms
     - 1 KiB
     - 0.2 ms
     - 49 KiB
   * - :ref:`distributions/plot_08_hexbin <sphx_glr_auto_examples_distributions_plot_08_hexbin.py>`
     - 1
     - 13.9 ms
     - 63 KiB
     - 22.4 ms
     - 128 KiB
   * - :ref:`gridded_data/plot_01_imshow <sphx_glr_auto_examples_gridded_data_plot_01_imshow.py>`
     - 1
     - 1.5 ms
     - 15 KiB
     - 5.6 ms
     - 139 KiB
   * - :ref:`gridded_data/plot_02_pcolormesh <sphx_glr_auto_examples_gridded_data_plot_02_pcolormesh.py>`
     - 1
     - 3.3 ms
     - 13 KiB
     - 14.8 ms
     - 271 KiB
   * - :ref:`gridded_data/plot_03_contour <sphx_glr_auto_examples_gridded_data_plot_03_contour.py>`
     - 1
     - 32.4 ms
     - 87 KiB
     - 37.0 ms
     - 212 KiB
   * - :ref:`gridded_data/plot_04_quiver <sphx_glr_auto_examples_gridded_data_plot_04_quiver.py>`
     - 1
     - 2.1 ms
     - 27 KiB
     - 2.9 ms
     - 82 KiB
   * - :ref:`gridded_data/plot_05_contourf <sphx_glr_auto_examples_gridded_data_plot_05_contourf.py>`
     - 1
     - 18.6 ms
     - 12 KiB
     - 39.6 ms
     - 363 KiB
   * - :ref:`gridded_data/plot_06_curvilinear_mesh <sphx_glr_auto_examples_gridded_data_plot_06_curvilinear_mesh.py>`
     - 1
     - 293.1 ms
     - 41 KiB
     - 290.2 ms
     - 127 KiB
   * - :ref:`gridded_data/plot_07_gouraud <sphx_glr_auto_examples_gridded_data_plot_07_gouraud.py>`
     - 2
     - 199.9 ms
     - 289 KiB
     - 201.9 ms
     - 349 KiB
   * - :ref:`gridded_data/plot_08_lognorm <sphx_glr_auto_examples_gridded_data_plot_08_lognorm.py>`
     - 2
     - 7.0 ms
     - 28 KiB
     - 29.4 ms
     - 498 KiB
   * - :ref:`gridded_data/plot_09_matshow <sphx_glr_auto_examples_gridded_data_plot_09_matshow.py>`
     - 1
     - 0.6 ms
     - 7 KiB
     - 0.9 ms
     - 55 KiB
   * - :ref:`gridded_data/plot_10_spy <sphx_glr_auto_examples_gridded_data_plot_10_spy.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 1.0 ms
     - 54 KiB
   * - :ref:`multi_axes/plot_01_subplots <sphx_glr_auto_examples_multi_axes_plot_01_subplots.py>`
     - 4
     - 2.5 ms
     - 23 KiB
     - 4.4 ms
     - 87 KiB
   * - :ref:`multi_axes/plot_02_annotations <sphx_glr_auto_examples_multi_axes_plot_02_annotations.py>`
     - 1
     - 0.6 ms
     - 6 KiB
     - 1.1 ms
     - 56 KiB
   * - :ref:`multi_axes/plot_03_twin_axes <sphx_glr_auto_examples_multi_axes_plot_03_twin_axes.py>`
     - 2
     - 1.6 ms
     - 12 KiB
     - 2.5 ms
     - 67 KiB
   * - :ref:`multi_axes/plot_04_shared_colorbar <sphx_glr_auto_examples_multi_axes_plot_04_shared_colorbar.py>`
     - 6
     - 3.7 ms
     - 22 KiB
     - 11.5 ms
     - 188 KiB
   * - :ref:`animation/plot_01_plot_frames <sphx_glr_auto_examples_animation_plot_01_plot_frames.py>`
     - 1
     - 0.7 ms
     - 6 KiB
     - 4.6 ms
     - 87 KiB
   * - :ref:`animation/plot_02_pcolormesh_frames <sphx_glr_auto_examples_animation_plot_02_pcolormesh_frames.py>`
     - 4
     - 3.8 ms
     - 23 KiB
     - 71.3 ms
     - 410 KiB
   * - :ref:`scale/plot_01_many_axes <sphx_glr_auto_scale_plot_01_many_axes.py>`
     - 500
     - 410.1 ms
     - 2.7 MiB
     - 836.0 ms
     - 7.3 MiB
   * - :ref:`scale/plot_02_million_point_line <sphx_glr_auto_scale_plot_02_million_point_line.py>`
     - 1
     - 161.3 ms
     - 47 KiB
     - 176.0 ms
     - 95 KiB
   * - :ref:`scale/plot_03_multimillion_mesh <sphx_glr_auto_scale_plot_03_multimillion_mesh.py>`
     - 1
     - 330.7 ms
     - 775 KiB
     - 365.7 ms
     - 1.0 MiB
   * - :ref:`scale/plot_04_thousand_series <sphx_glr_auto_scale_plot_04_thousand_series.py>`
     - 1
     - 910.0 ms
     - 6.9 MiB
     - 1361.5 ms
     - 12.1 MiB
   * - :ref:`scale/plot_05_axes_grid_lines <sphx_glr_auto_scale_plot_05_axes_grid_lines.py>`
     - 900
     - 20674.4 ms
     - 2.4 MiB
     - 40809.2 ms
     - 3.5 MiB
   * - :ref:`scale/plot_06_shared_colorbar_lognorm <sphx_glr_auto_scale_plot_06_shared_colorbar_lognorm.py>`
     - 144
     - 83.2 ms
     - 508 KiB
     - 232.4 ms
     - 2.4 MiB
   * - :ref:`scale/plot_07_matplotlib_comparison <sphx_glr_auto_scale_plot_07_matplotlib_comparison.py>`
     - 1
     - 0.9 ms
     - 5 KiB
     - 1.2 ms
     - 53 KiB
   * - :ref:`scale/plot_08_vector_over_raster <sphx_glr_auto_scale_plot_08_vector_over_raster.py>`
     - 1
     - 271.6 ms
     - 599 KiB
     - 315.9 ms
     - 1.1 MiB
   * - :ref:`scale/plot_09_output_scaling <sphx_glr_auto_scale_plot_09_output_scaling.py>`
     - 1
     - 1.5 ms
     - 6 KiB
     - 2.0 ms
     - 56 KiB

The ``scale/plot_01_many_axes`` row is the deliberate stress case: 500 independent pcolormesh axes on one figure. Its interactive HTML is dominated by the 500 embedded mesh ``z`` grids; lower ``fig.to_html(pick_precision=...)`` (or ``fig.save(..., pick_precision=...)``) to trade readout precision for a smaller file, or cap the total embedded amount directly with ``pick_max_mesh_cells`` / ``pick_max_points`` -- a mesh over the cap is block-averaged down to it rather than dropped, so a click still answers with a real, if coarser, value.

Binary vs. JSON pick data
--------------------------

``fig.to_html()``/``fig.save(...html)`` embed long point-pick arrays (mesh ``z`` grids, animated line frames) as base64 float32 bytes by default (``binary_pick_data=True``) rather than JSON number text. Below is every example above, both ways: most are small enough that neither the array-length threshold nor the file size difference matters: the JSON version is well under a point-pick array's own threshold to begin with. It shows up once a mesh or a long series does most of the work, which is exactly the ``scale/`` rows.

.. list-table::
   :header-rows: 1
   :widths: 30 11 11 11 11 8 8

   * - Example
     - Binary
     - Binary size
     - JSON
     - JSON size
     - Size
     - Time
   * - :ref:`pairwise/plot_01_line <sphx_glr_auto_examples_pairwise_plot_01_line.py>`
     - 1.9 ms
     - 61 KiB
     - 1.7 ms
     - 64 KiB
     - 1.05x
     - 0.90x
   * - :ref:`pairwise/plot_02_scatter <sphx_glr_auto_examples_pairwise_plot_02_scatter.py>`
     - 2.5 ms
     - 88 KiB
     - 2.4 ms
     - 92 KiB
     - 1.04x
     - 0.96x
   * - :ref:`pairwise/plot_03_bar <sphx_glr_auto_examples_pairwise_plot_03_bar.py>`
     - 0.5 ms
     - 51 KiB
     - 0.5 ms
     - 51 KiB
     - 0.99x
     - 0.88x
   * - :ref:`pairwise/plot_04_barh <sphx_glr_auto_examples_pairwise_plot_04_barh.py>`
     - 0.4 ms
     - 51 KiB
     - 0.4 ms
     - 51 KiB
     - 0.99x
     - 0.87x
   * - :ref:`pairwise/plot_05_stem <sphx_glr_auto_examples_pairwise_plot_05_stem.py>`
     - 0.5 ms
     - 54 KiB
     - 0.4 ms
     - 53 KiB
     - 0.99x
     - 0.87x
   * - :ref:`pairwise/plot_06_step <sphx_glr_auto_examples_pairwise_plot_06_step.py>`
     - 0.5 ms
     - 51 KiB
     - 0.4 ms
     - 51 KiB
     - 0.99x
     - 0.87x
   * - :ref:`pairwise/plot_07_fill_between <sphx_glr_auto_examples_pairwise_plot_07_fill_between.py>`
     - 2.1 ms
     - 64 KiB
     - 1.9 ms
     - 67 KiB
     - 1.05x
     - 0.87x
   * - :ref:`pairwise/plot_08_stackplot <sphx_glr_auto_examples_pairwise_plot_08_stackplot.py>`
     - 0.8 ms
     - 53 KiB
     - 0.7 ms
     - 52 KiB
     - 0.99x
     - 0.91x
   * - :ref:`pairwise/plot_09_loglog <sphx_glr_auto_examples_pairwise_plot_09_loglog.py>`
     - 1.5 ms
     - 55 KiB
     - 1.3 ms
     - 56 KiB
     - 1.02x
     - 0.87x
   * - :ref:`pairwise/plot_10_reference_lines <sphx_glr_auto_examples_pairwise_plot_10_reference_lines.py>`
     - 2.8 ms
     - 72 KiB
     - 2.6 ms
     - 77 KiB
     - 1.07x
     - 0.93x
   * - :ref:`pairwise/plot_11_broken_barh <sphx_glr_auto_examples_pairwise_plot_11_broken_barh.py>`
     - 0.8 ms
     - 51 KiB
     - 0.7 ms
     - 51 KiB
     - 0.99x
     - 0.89x
   * - :ref:`pairwise/plot_12_stairs <sphx_glr_auto_examples_pairwise_plot_12_stairs.py>`
     - 0.5 ms
     - 51 KiB
     - 0.4 ms
     - 51 KiB
     - 0.99x
     - 0.88x
   * - :ref:`pairwise/plot_13_axline <sphx_glr_auto_examples_pairwise_plot_13_axline.py>`
     - 0.8 ms
     - 53 KiB
     - 0.6 ms
     - 53 KiB
     - 1.00x
     - 0.76x
   * - :ref:`distributions/plot_01_hist <sphx_glr_auto_examples_distributions_plot_01_hist.py>`
     - 0.8 ms
     - 54 KiB
     - 0.7 ms
     - 53 KiB
     - 0.99x
     - 0.91x
   * - :ref:`distributions/plot_02_boxplot <sphx_glr_auto_examples_distributions_plot_02_boxplot.py>`
     - 0.6 ms
     - 53 KiB
     - 0.5 ms
     - 52 KiB
     - 0.99x
     - 0.85x
   * - :ref:`distributions/plot_03_errorbar <sphx_glr_auto_examples_distributions_plot_03_errorbar.py>`
     - 0.6 ms
     - 53 KiB
     - 0.5 ms
     - 52 KiB
     - 0.99x
     - 0.89x
   * - :ref:`distributions/plot_04_violin <sphx_glr_auto_examples_distributions_plot_04_violin.py>`
     - 2.5 ms
     - 62 KiB
     - 2.0 ms
     - 65 KiB
     - 1.05x
     - 0.78x
   * - :ref:`distributions/plot_05_eventplot <sphx_glr_auto_examples_distributions_plot_05_eventplot.py>`
     - 1.9 ms
     - 66 KiB
     - 1.7 ms
     - 67 KiB
     - 1.02x
     - 0.91x
   * - :ref:`distributions/plot_06_hist2d <sphx_glr_auto_examples_distributions_plot_06_hist2d.py>`
     - 1.5 ms
     - 59 KiB
     - 1.3 ms
     - 63 KiB
     - 1.06x
     - 0.82x
   * - :ref:`distributions/plot_07_pie <sphx_glr_auto_examples_distributions_plot_07_pie.py>`
     - 0.2 ms
     - 49 KiB
     - 0.2 ms
     - 49 KiB
     - 0.99x
     - 0.73x
   * - :ref:`distributions/plot_08_hexbin <sphx_glr_auto_examples_distributions_plot_08_hexbin.py>`
     - 22.4 ms
     - 128 KiB
     - 22.6 ms
     - 144 KiB
     - 1.12x
     - 1.01x
   * - :ref:`gridded_data/plot_01_imshow <sphx_glr_auto_examples_gridded_data_plot_01_imshow.py>`
     - 5.6 ms
     - 139 KiB
     - 8.4 ms
     - 209 KiB
     - 1.50x
     - 1.50x
   * - :ref:`gridded_data/plot_02_pcolormesh <sphx_glr_auto_examples_gridded_data_plot_02_pcolormesh.py>`
     - 14.8 ms
     - 271 KiB
     - 22.4 ms
     - 434 KiB
     - 1.60x
     - 1.51x
   * - :ref:`gridded_data/plot_03_contour <sphx_glr_auto_examples_gridded_data_plot_03_contour.py>`
     - 37.0 ms
     - 212 KiB
     - 39.5 ms
     - 285 KiB
     - 1.34x
     - 1.07x
   * - :ref:`gridded_data/plot_04_quiver <sphx_glr_auto_examples_gridded_data_plot_04_quiver.py>`
     - 2.9 ms
     - 82 KiB
     - 2.7 ms
     - 86 KiB
     - 1.05x
     - 0.93x
   * - :ref:`gridded_data/plot_05_contourf <sphx_glr_auto_examples_gridded_data_plot_05_contourf.py>`
     - 39.6 ms
     - 363 KiB
     - 49.8 ms
     - 647 KiB
     - 1.78x
     - 1.26x
   * - :ref:`gridded_data/plot_06_curvilinear_mesh <sphx_glr_auto_examples_gridded_data_plot_06_curvilinear_mesh.py>`
     - 290.2 ms
     - 127 KiB
     - 290.2 ms
     - 162 KiB
     - 1.27x
     - 1.00x
   * - :ref:`gridded_data/plot_07_gouraud <sphx_glr_auto_examples_gridded_data_plot_07_gouraud.py>`
     - 201.9 ms
     - 349 KiB
     - 197.7 ms
     - 359 KiB
     - 1.03x
     - 0.98x
   * - :ref:`gridded_data/plot_08_lognorm <sphx_glr_auto_examples_gridded_data_plot_08_lognorm.py>`
     - 29.4 ms
     - 498 KiB
     - 44.6 ms
     - 904 KiB
     - 1.82x
     - 1.52x
   * - :ref:`gridded_data/plot_09_matshow <sphx_glr_auto_examples_gridded_data_plot_09_matshow.py>`
     - 0.9 ms
     - 55 KiB
     - 0.8 ms
     - 56 KiB
     - 1.01x
     - 0.87x
   * - :ref:`gridded_data/plot_10_spy <sphx_glr_auto_examples_gridded_data_plot_10_spy.py>`
     - 1.0 ms
     - 54 KiB
     - 0.8 ms
     - 56 KiB
     - 1.03x
     - 0.80x
   * - :ref:`multi_axes/plot_01_subplots <sphx_glr_auto_examples_multi_axes_plot_01_subplots.py>`
     - 4.4 ms
     - 87 KiB
     - 4.2 ms
     - 101 KiB
     - 1.15x
     - 0.97x
   * - :ref:`multi_axes/plot_02_annotations <sphx_glr_auto_examples_multi_axes_plot_02_annotations.py>`
     - 1.1 ms
     - 56 KiB
     - 0.9 ms
     - 57 KiB
     - 1.03x
     - 0.83x
   * - :ref:`multi_axes/plot_03_twin_axes <sphx_glr_auto_examples_multi_axes_plot_03_twin_axes.py>`
     - 2.5 ms
     - 67 KiB
     - 2.4 ms
     - 72 KiB
     - 1.08x
     - 0.95x
   * - :ref:`multi_axes/plot_04_shared_colorbar <sphx_glr_auto_examples_multi_axes_plot_04_shared_colorbar.py>`
     - 11.5 ms
     - 188 KiB
     - 14.8 ms
     - 281 KiB
     - 1.49x
     - 1.28x
   * - :ref:`animation/plot_01_plot_frames <sphx_glr_auto_examples_animation_plot_01_plot_frames.py>`
     - 4.6 ms
     - 87 KiB
     - 3.8 ms
     - 117 KiB
     - 1.34x
     - 0.83x
   * - :ref:`animation/plot_02_pcolormesh_frames <sphx_glr_auto_examples_animation_plot_02_pcolormesh_frames.py>`
     - 71.3 ms
     - 410 KiB
     - 68.6 ms
     - 411 KiB
     - 1.00x
     - 0.96x
   * - :ref:`scale/plot_01_many_axes <sphx_glr_auto_scale_plot_01_many_axes.py>`
     - 836.0 ms
     - 7.3 MiB
     - 919.2 ms
     - 11.4 MiB
     - 1.57x
     - 1.10x
   * - :ref:`scale/plot_02_million_point_line <sphx_glr_auto_scale_plot_02_million_point_line.py>`
     - 176.0 ms
     - 95 KiB
     - 177.4 ms
     - 94 KiB
     - 1.00x
     - 1.01x
   * - :ref:`scale/plot_03_multimillion_mesh <sphx_glr_auto_scale_plot_03_multimillion_mesh.py>`
     - 365.7 ms
     - 1.0 MiB
     - 374.6 ms
     - 1.3 MiB
     - 1.22x
     - 1.02x
   * - :ref:`scale/plot_04_thousand_series <sphx_glr_auto_scale_plot_04_thousand_series.py>`
     - 1361.5 ms
     - 12.1 MiB
     - 1476.2 ms
     - 17.3 MiB
     - 1.42x
     - 1.08x
   * - :ref:`scale/plot_05_axes_grid_lines <sphx_glr_auto_scale_plot_05_axes_grid_lines.py>`
     - 40809.2 ms
     - 3.5 MiB
     - 40879.0 ms
     - 4.7 MiB
     - 1.32x
     - 1.00x
   * - :ref:`scale/plot_06_shared_colorbar_lognorm <sphx_glr_auto_scale_plot_06_shared_colorbar_lognorm.py>`
     - 232.4 ms
     - 2.4 MiB
     - 284.1 ms
     - 4.1 MiB
     - 1.71x
     - 1.22x
   * - :ref:`scale/plot_07_matplotlib_comparison <sphx_glr_auto_scale_plot_07_matplotlib_comparison.py>`
     - 1.2 ms
     - 53 KiB
     - 1.1 ms
     - 53 KiB
     - 0.99x
     - 0.94x
   * - :ref:`scale/plot_08_vector_over_raster <sphx_glr_auto_scale_plot_08_vector_over_raster.py>`
     - 315.9 ms
     - 1.1 MiB
     - 330.7 ms
     - 1.4 MiB
     - 1.37x
     - 1.05x
   * - :ref:`scale/plot_09_output_scaling <sphx_glr_auto_scale_plot_09_output_scaling.py>`
     - 2.0 ms
     - 56 KiB
     - 1.9 ms
     - 55 KiB
     - 0.99x
     - 0.95x

"Size"/"Time" are JSON relative to binary -- 2.0x under Size means the JSON payload is twice the binary one's size; under Time means it took twice as long to build. A ratio near 1.0x on a small figure means the encoder found nothing worth switching: every array in it was already under the threshold where a base64 wrapper costs more than it saves.
