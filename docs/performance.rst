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
   :widths: 24 19 19 19

   * - Scenario
     - plotpress (time / size)
     - matplotlib (time / size)
     - xy (time / size)
   * - ``line_100k_points``
     - 8.8 ms / 17 KiB
     - 41.1 ms / 24 KiB
     - 2.5 ms / 31 KiB
   * - ``scatter_5k_points``
     - 14.9 ms / 137 KiB
     - 118.1 ms / 533 KiB
     - 22.2 ms / 360 KiB
   * - ``pcolormesh_300x300``
     - 9.2 ms / 45 KiB
     - 5661.0 ms / 15.4 MiB
     - 15.6 ms / 95 KiB
   * - ``many_axes_8x8_grid``
     - 36.1 ms / 336 KiB
     - 1317.6 ms / 331 KiB
     - 58.9 ms / 361 KiB

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
     - 1.6 ms
     - 10 KiB
     - 3.0 ms
     - 85 KiB
   * - :ref:`pairwise/plot_02_scatter <sphx_glr_auto_examples_pairwise_plot_02_scatter.py>`
     - 1
     - 3.1 ms
     - 44 KiB
     - 3.9 ms
     - 119 KiB
   * - :ref:`pairwise/plot_03_bar <sphx_glr_auto_examples_pairwise_plot_03_bar.py>`
     - 1
     - 0.5 ms
     - 4 KiB
     - 0.9 ms
     - 75 KiB
   * - :ref:`pairwise/plot_04_barh <sphx_glr_auto_examples_pairwise_plot_04_barh.py>`
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.8 ms
     - 75 KiB
   * - :ref:`pairwise/plot_05_stem <sphx_glr_auto_examples_pairwise_plot_05_stem.py>`
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.6 ms
     - 76 KiB
   * - :ref:`pairwise/plot_06_step <sphx_glr_auto_examples_pairwise_plot_06_step.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.6 ms
     - 73 KiB
   * - :ref:`pairwise/plot_07_fill_between <sphx_glr_auto_examples_pairwise_plot_07_fill_between.py>`
     - 2
     - 4.0 ms
     - 21 KiB
     - 5.6 ms
     - 104 KiB
   * - :ref:`pairwise/plot_08_stackplot <sphx_glr_auto_examples_pairwise_plot_08_stackplot.py>`
     - 1
     - 0.5 ms
     - 4 KiB
     - 0.9 ms
     - 75 KiB
   * - :ref:`pairwise/plot_09_loglog <sphx_glr_auto_examples_pairwise_plot_09_loglog.py>`
     - 3
     - 2.2 ms
     - 14 KiB
     - 3.4 ms
     - 88 KiB
   * - :ref:`pairwise/plot_10_reference_lines <sphx_glr_auto_examples_pairwise_plot_10_reference_lines.py>`
     - 1
     - 1.8 ms
     - 16 KiB
     - 3.0 ms
     - 94 KiB
   * - :ref:`pairwise/plot_11_broken_barh <sphx_glr_auto_examples_pairwise_plot_11_broken_barh.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 0.9 ms
     - 74 KiB
   * - :ref:`pairwise/plot_12_stairs <sphx_glr_auto_examples_pairwise_plot_12_stairs.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.6 ms
     - 74 KiB
   * - :ref:`pairwise/plot_13_axline <sphx_glr_auto_examples_pairwise_plot_13_axline.py>`
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.9 ms
     - 75 KiB
   * - :ref:`pairwise/plot_14_hlines_vlines <sphx_glr_auto_examples_pairwise_plot_14_hlines_vlines.py>`
     - 2
     - 1.6 ms
     - 14 KiB
     - 2.8 ms
     - 92 KiB
   * - :ref:`pairwise/plot_15_linestyles <sphx_glr_auto_examples_pairwise_plot_15_linestyles.py>`
     - 2
     - 3.8 ms
     - 29 KiB
     - 6.5 ms
     - 116 KiB
   * - :ref:`distributions/plot_01_hist <sphx_glr_auto_examples_distributions_plot_01_hist.py>`
     - 1
     - 1.0 ms
     - 8 KiB
     - 1.4 ms
     - 80 KiB
   * - :ref:`distributions/plot_02_boxplot <sphx_glr_auto_examples_distributions_plot_02_boxplot.py>`
     - 1
     - 0.3 ms
     - 4 KiB
     - 0.6 ms
     - 75 KiB
   * - :ref:`distributions/plot_03_errorbar <sphx_glr_auto_examples_distributions_plot_03_errorbar.py>`
     - 1
     - 0.4 ms
     - 5 KiB
     - 0.6 ms
     - 75 KiB
   * - :ref:`distributions/plot_04_violin <sphx_glr_auto_examples_distributions_plot_04_violin.py>`
     - 1
     - 1.5 ms
     - 10 KiB
     - 2.7 ms
     - 85 KiB
   * - :ref:`distributions/plot_05_eventplot <sphx_glr_auto_examples_distributions_plot_05_eventplot.py>`
     - 1
     - 1.2 ms
     - 16 KiB
     - 1.9 ms
     - 88 KiB
   * - :ref:`distributions/plot_06_hist2d <sphx_glr_auto_examples_distributions_plot_06_hist2d.py>`
     - 1
     - 0.7 ms
     - 6 KiB
     - 1.7 ms
     - 82 KiB
   * - :ref:`distributions/plot_07_pie <sphx_glr_auto_examples_distributions_plot_07_pie.py>`
     - 1
     - 0.1 ms
     - 1 KiB
     - 0.3 ms
     - 72 KiB
   * - :ref:`distributions/plot_08_hexbin <sphx_glr_auto_examples_distributions_plot_08_hexbin.py>`
     - 1
     - 13.8 ms
     - 63 KiB
     - 22.4 ms
     - 151 KiB
   * - :ref:`gridded_data/plot_01_imshow <sphx_glr_auto_examples_gridded_data_plot_01_imshow.py>`
     - 1
     - 1.7 ms
     - 17 KiB
     - 6.3 ms
     - 164 KiB
   * - :ref:`gridded_data/plot_02_pcolormesh <sphx_glr_auto_examples_gridded_data_plot_02_pcolormesh.py>`
     - 1
     - 17.7 ms
     - 50 KiB
     - 40.3 ms
     - 544 KiB
   * - :ref:`gridded_data/plot_03_contour <sphx_glr_auto_examples_gridded_data_plot_03_contour.py>`
     - 1
     - 32.4 ms
     - 87 KiB
     - 37.0 ms
     - 235 KiB
   * - :ref:`gridded_data/plot_04_quiver <sphx_glr_auto_examples_gridded_data_plot_04_quiver.py>`
     - 1
     - 2.1 ms
     - 27 KiB
     - 3.1 ms
     - 104 KiB
   * - :ref:`gridded_data/plot_05_contourf <sphx_glr_auto_examples_gridded_data_plot_05_contourf.py>`
     - 1
     - 18.2 ms
     - 12 KiB
     - 82.9 ms
     - 1.3 MiB
   * - :ref:`gridded_data/plot_06_curvilinear_mesh <sphx_glr_auto_examples_gridded_data_plot_06_curvilinear_mesh.py>`
     - 1
     - 290.3 ms
     - 41 KiB
     - 283.9 ms
     - 149 KiB
   * - :ref:`gridded_data/plot_07_gouraud <sphx_glr_auto_examples_gridded_data_plot_07_gouraud.py>`
     - 2
     - 184.7 ms
     - 289 KiB
     - 184.0 ms
     - 372 KiB
   * - :ref:`gridded_data/plot_08_lognorm <sphx_glr_auto_examples_gridded_data_plot_08_lognorm.py>`
     - 2
     - 7.0 ms
     - 29 KiB
     - 29.5 ms
     - 521 KiB
   * - :ref:`gridded_data/plot_09_matshow <sphx_glr_auto_examples_gridded_data_plot_09_matshow.py>`
     - 1
     - 0.6 ms
     - 7 KiB
     - 1.0 ms
     - 78 KiB
   * - :ref:`gridded_data/plot_10_spy <sphx_glr_auto_examples_gridded_data_plot_10_spy.py>`
     - 1
     - 0.4 ms
     - 3 KiB
     - 1.0 ms
     - 77 KiB
   * - :ref:`gridded_data/plot_11_colormap_reference <sphx_glr_auto_examples_gridded_data_plot_11_colormap_reference.py>`
     - 5
     - 4.0 ms
     - 42 KiB
     - 11.6 ms
     - 180 KiB
   * - :ref:`multi_axes/plot_01_subplots <sphx_glr_auto_examples_multi_axes_plot_01_subplots.py>`
     - 4
     - 2.5 ms
     - 24 KiB
     - 4.7 ms
     - 111 KiB
   * - :ref:`multi_axes/plot_02_annotations <sphx_glr_auto_examples_multi_axes_plot_02_annotations.py>`
     - 1
     - 0.6 ms
     - 6 KiB
     - 1.2 ms
     - 78 KiB
   * - :ref:`multi_axes/plot_03_twin_axes <sphx_glr_auto_examples_multi_axes_plot_03_twin_axes.py>`
     - 4
     - 3.1 ms
     - 24 KiB
     - 5.1 ms
     - 110 KiB
   * - :ref:`multi_axes/plot_04_shared_colorbar <sphx_glr_auto_examples_multi_axes_plot_04_shared_colorbar.py>`
     - 6
     - 3.7 ms
     - 22 KiB
     - 12.2 ms
     - 213 KiB
   * - :ref:`animation/plot_01_plot_frames <sphx_glr_auto_examples_animation_plot_01_plot_frames.py>`
     - 1
     - 0.7 ms
     - 6 KiB
     - 4.8 ms
     - 110 KiB
   * - :ref:`animation/plot_02_pcolormesh_frames <sphx_glr_auto_examples_animation_plot_02_pcolormesh_frames.py>`
     - 4
     - 3.8 ms
     - 23 KiB
     - 246.8 ms
     - 3.7 MiB
   * - :ref:`scale/plot_01_many_axes <sphx_glr_auto_scale_plot_01_many_axes.py>`
     - 500
     - 395.9 ms
     - 2.7 MiB
     - 836.3 ms
     - 7.5 MiB
   * - :ref:`scale/plot_02_million_point_line <sphx_glr_auto_scale_plot_02_million_point_line.py>`
     - 1
     - 156.8 ms
     - 47 KiB
     - 184.9 ms
     - 117 KiB
   * - :ref:`scale/plot_03_multimillion_mesh <sphx_glr_auto_scale_plot_03_multimillion_mesh.py>`
     - 1
     - 320.6 ms
     - 775 KiB
     - 419.8 ms
     - 2.1 MiB
   * - :ref:`scale/plot_04_thousand_series <sphx_glr_auto_scale_plot_04_thousand_series.py>`
     - 1
     - 887.8 ms
     - 6.9 MiB
     - 1362.2 ms
     - 12.1 MiB
   * - :ref:`scale/plot_05_axes_grid_lines <sphx_glr_auto_scale_plot_05_axes_grid_lines.py>`
     - 900
     - 20173.4 ms
     - 2.4 MiB
     - 58817.4 ms
     - 3.9 MiB
   * - :ref:`scale/plot_06_shared_colorbar_lognorm <sphx_glr_auto_scale_plot_06_shared_colorbar_lognorm.py>`
     - 144
     - 81.5 ms
     - 514 KiB
     - 236.8 ms
     - 2.5 MiB
   * - :ref:`scale/plot_07_matplotlib_comparison <sphx_glr_auto_scale_plot_07_matplotlib_comparison.py>`
     - 1
     - 0.9 ms
     - 5 KiB
     - 1.3 ms
     - 76 KiB
   * - :ref:`scale/plot_08_vector_over_raster <sphx_glr_auto_scale_plot_08_vector_over_raster.py>`
     - 1
     - 266.3 ms
     - 600 KiB
     - 437.4 ms
     - 3.2 MiB
   * - :ref:`scale/plot_09_output_scaling <sphx_glr_auto_scale_plot_09_output_scaling.py>`
     - 1
     - 1.6 ms
     - 7 KiB
     - 2.3 ms
     - 79 KiB
   * - :ref:`scale/plot_10_many_groups_with_colorbars <sphx_glr_auto_scale_plot_10_many_groups_with_colorbars.py>`
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.6 ms
     - 74 KiB

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
     - 3.0 ms
     - 85 KiB
     - 2.7 ms
     - 88 KiB
     - 1.04x
     - 0.88x
   * - :ref:`pairwise/plot_02_scatter <sphx_glr_auto_examples_pairwise_plot_02_scatter.py>`
     - 3.9 ms
     - 119 KiB
     - 3.5 ms
     - 123 KiB
     - 1.03x
     - 0.89x
   * - :ref:`pairwise/plot_03_bar <sphx_glr_auto_examples_pairwise_plot_03_bar.py>`
     - 0.9 ms
     - 75 KiB
     - 0.8 ms
     - 75 KiB
     - 0.99x
     - 0.99x
   * - :ref:`pairwise/plot_04_barh <sphx_glr_auto_examples_pairwise_plot_04_barh.py>`
     - 0.8 ms
     - 75 KiB
     - 0.7 ms
     - 75 KiB
     - 0.99x
     - 0.81x
   * - :ref:`pairwise/plot_05_stem <sphx_glr_auto_examples_pairwise_plot_05_stem.py>`
     - 0.6 ms
     - 76 KiB
     - 0.5 ms
     - 76 KiB
     - 0.99x
     - 0.95x
   * - :ref:`pairwise/plot_06_step <sphx_glr_auto_examples_pairwise_plot_06_step.py>`
     - 0.6 ms
     - 73 KiB
     - 0.5 ms
     - 73 KiB
     - 0.99x
     - 0.92x
   * - :ref:`pairwise/plot_07_fill_between <sphx_glr_auto_examples_pairwise_plot_07_fill_between.py>`
     - 5.6 ms
     - 104 KiB
     - 5.1 ms
     - 112 KiB
     - 1.08x
     - 0.90x
   * - :ref:`pairwise/plot_08_stackplot <sphx_glr_auto_examples_pairwise_plot_08_stackplot.py>`
     - 0.9 ms
     - 75 KiB
     - 0.9 ms
     - 75 KiB
     - 0.99x
     - 0.92x
   * - :ref:`pairwise/plot_09_loglog <sphx_glr_auto_examples_pairwise_plot_09_loglog.py>`
     - 3.4 ms
     - 88 KiB
     - 2.9 ms
     - 91 KiB
     - 1.03x
     - 0.85x
   * - :ref:`pairwise/plot_10_reference_lines <sphx_glr_auto_examples_pairwise_plot_10_reference_lines.py>`
     - 3.0 ms
     - 94 KiB
     - 2.7 ms
     - 99 KiB
     - 1.05x
     - 0.93x
   * - :ref:`pairwise/plot_11_broken_barh <sphx_glr_auto_examples_pairwise_plot_11_broken_barh.py>`
     - 0.9 ms
     - 74 KiB
     - 0.8 ms
     - 73 KiB
     - 0.99x
     - 0.93x
   * - :ref:`pairwise/plot_12_stairs <sphx_glr_auto_examples_pairwise_plot_12_stairs.py>`
     - 0.6 ms
     - 74 KiB
     - 0.5 ms
     - 73 KiB
     - 0.99x
     - 0.90x
   * - :ref:`pairwise/plot_13_axline <sphx_glr_auto_examples_pairwise_plot_13_axline.py>`
     - 0.9 ms
     - 75 KiB
     - 0.7 ms
     - 75 KiB
     - 1.00x
     - 0.78x
   * - :ref:`pairwise/plot_14_hlines_vlines <sphx_glr_auto_examples_pairwise_plot_14_hlines_vlines.py>`
     - 2.8 ms
     - 92 KiB
     - 2.7 ms
     - 97 KiB
     - 1.06x
     - 0.95x
   * - :ref:`pairwise/plot_15_linestyles <sphx_glr_auto_examples_pairwise_plot_15_linestyles.py>`
     - 6.5 ms
     - 116 KiB
     - 6.1 ms
     - 129 KiB
     - 1.11x
     - 0.93x
   * - :ref:`distributions/plot_01_hist <sphx_glr_auto_examples_distributions_plot_01_hist.py>`
     - 1.4 ms
     - 80 KiB
     - 1.3 ms
     - 80 KiB
     - 1.00x
     - 0.93x
   * - :ref:`distributions/plot_02_boxplot <sphx_glr_auto_examples_distributions_plot_02_boxplot.py>`
     - 0.6 ms
     - 75 KiB
     - 0.5 ms
     - 74 KiB
     - 0.99x
     - 0.85x
   * - :ref:`distributions/plot_03_errorbar <sphx_glr_auto_examples_distributions_plot_03_errorbar.py>`
     - 0.6 ms
     - 75 KiB
     - 0.6 ms
     - 75 KiB
     - 0.99x
     - 0.90x
   * - :ref:`distributions/plot_04_violin <sphx_glr_auto_examples_distributions_plot_04_violin.py>`
     - 2.7 ms
     - 85 KiB
     - 2.1 ms
     - 88 KiB
     - 1.03x
     - 0.79x
   * - :ref:`distributions/plot_05_eventplot <sphx_glr_auto_examples_distributions_plot_05_eventplot.py>`
     - 1.9 ms
     - 88 KiB
     - 1.7 ms
     - 89 KiB
     - 1.01x
     - 0.90x
   * - :ref:`distributions/plot_06_hist2d <sphx_glr_auto_examples_distributions_plot_06_hist2d.py>`
     - 1.7 ms
     - 82 KiB
     - 1.4 ms
     - 85 KiB
     - 1.05x
     - 0.82x
   * - :ref:`distributions/plot_07_pie <sphx_glr_auto_examples_distributions_plot_07_pie.py>`
     - 0.3 ms
     - 72 KiB
     - 0.2 ms
     - 72 KiB
     - 0.99x
     - 0.75x
   * - :ref:`distributions/plot_08_hexbin <sphx_glr_auto_examples_distributions_plot_08_hexbin.py>`
     - 22.4 ms
     - 151 KiB
     - 22.5 ms
     - 166 KiB
     - 1.11x
     - 1.00x
   * - :ref:`gridded_data/plot_01_imshow <sphx_glr_auto_examples_gridded_data_plot_01_imshow.py>`
     - 6.3 ms
     - 164 KiB
     - 8.8 ms
     - 234 KiB
     - 1.43x
     - 1.40x
   * - :ref:`gridded_data/plot_02_pcolormesh <sphx_glr_auto_examples_gridded_data_plot_02_pcolormesh.py>`
     - 40.3 ms
     - 544 KiB
     - 53.6 ms
     - 871 KiB
     - 1.60x
     - 1.33x
   * - :ref:`gridded_data/plot_03_contour <sphx_glr_auto_examples_gridded_data_plot_03_contour.py>`
     - 37.0 ms
     - 235 KiB
     - 39.5 ms
     - 308 KiB
     - 1.31x
     - 1.07x
   * - :ref:`gridded_data/plot_04_quiver <sphx_glr_auto_examples_gridded_data_plot_04_quiver.py>`
     - 3.1 ms
     - 104 KiB
     - 2.8 ms
     - 108 KiB
     - 1.04x
     - 0.92x
   * - :ref:`gridded_data/plot_05_contourf <sphx_glr_auto_examples_gridded_data_plot_05_contourf.py>`
     - 82.9 ms
     - 1.3 MiB
     - 126.0 ms
     - 2.4 MiB
     - 1.88x
     - 1.52x
   * - :ref:`gridded_data/plot_06_curvilinear_mesh <sphx_glr_auto_examples_gridded_data_plot_06_curvilinear_mesh.py>`
     - 283.9 ms
     - 149 KiB
     - 281.6 ms
     - 184 KiB
     - 1.23x
     - 0.99x
   * - :ref:`gridded_data/plot_07_gouraud <sphx_glr_auto_examples_gridded_data_plot_07_gouraud.py>`
     - 184.0 ms
     - 372 KiB
     - 184.9 ms
     - 382 KiB
     - 1.03x
     - 1.00x
   * - :ref:`gridded_data/plot_08_lognorm <sphx_glr_auto_examples_gridded_data_plot_08_lognorm.py>`
     - 29.5 ms
     - 521 KiB
     - 45.4 ms
     - 927 KiB
     - 1.78x
     - 1.54x
   * - :ref:`gridded_data/plot_09_matshow <sphx_glr_auto_examples_gridded_data_plot_09_matshow.py>`
     - 1.0 ms
     - 78 KiB
     - 0.9 ms
     - 78 KiB
     - 1.00x
     - 0.87x
   * - :ref:`gridded_data/plot_10_spy <sphx_glr_auto_examples_gridded_data_plot_10_spy.py>`
     - 1.0 ms
     - 77 KiB
     - 0.8 ms
     - 78 KiB
     - 1.02x
     - 0.81x
   * - :ref:`gridded_data/plot_11_colormap_reference <sphx_glr_auto_examples_gridded_data_plot_11_colormap_reference.py>`
     - 11.6 ms
     - 180 KiB
     - 10.9 ms
     - 232 KiB
     - 1.28x
     - 0.95x
   * - :ref:`multi_axes/plot_01_subplots <sphx_glr_auto_examples_multi_axes_plot_01_subplots.py>`
     - 4.7 ms
     - 111 KiB
     - 4.5 ms
     - 125 KiB
     - 1.12x
     - 0.97x
   * - :ref:`multi_axes/plot_02_annotations <sphx_glr_auto_examples_multi_axes_plot_02_annotations.py>`
     - 1.2 ms
     - 78 KiB
     - 1.2 ms
     - 80 KiB
     - 1.02x
     - 0.95x
   * - :ref:`multi_axes/plot_03_twin_axes <sphx_glr_auto_examples_multi_axes_plot_03_twin_axes.py>`
     - 5.1 ms
     - 110 KiB
     - 4.9 ms
     - 121 KiB
     - 1.10x
     - 0.96x
   * - :ref:`multi_axes/plot_04_shared_colorbar <sphx_glr_auto_examples_multi_axes_plot_04_shared_colorbar.py>`
     - 12.2 ms
     - 213 KiB
     - 15.2 ms
     - 306 KiB
     - 1.44x
     - 1.25x
   * - :ref:`animation/plot_01_plot_frames <sphx_glr_auto_examples_animation_plot_01_plot_frames.py>`
     - 4.8 ms
     - 110 KiB
     - 4.0 ms
     - 140 KiB
     - 1.27x
     - 0.82x
   * - :ref:`animation/plot_02_pcolormesh_frames <sphx_glr_auto_examples_animation_plot_02_pcolormesh_frames.py>`
     - 246.8 ms
     - 3.7 MiB
     - 352.0 ms
     - 6.1 MiB
     - 1.64x
     - 1.43x
   * - :ref:`scale/plot_01_many_axes <sphx_glr_auto_scale_plot_01_many_axes.py>`
     - 836.3 ms
     - 7.5 MiB
     - 919.7 ms
     - 11.7 MiB
     - 1.55x
     - 1.10x
   * - :ref:`scale/plot_02_million_point_line <sphx_glr_auto_scale_plot_02_million_point_line.py>`
     - 184.9 ms
     - 117 KiB
     - 184.5 ms
     - 117 KiB
     - 1.00x
     - 1.00x
   * - :ref:`scale/plot_03_multimillion_mesh <sphx_glr_auto_scale_plot_03_multimillion_mesh.py>`
     - 419.8 ms
     - 2.1 MiB
     - 467.5 ms
     - 3.3 MiB
     - 1.58x
     - 1.11x
   * - :ref:`scale/plot_04_thousand_series <sphx_glr_auto_scale_plot_04_thousand_series.py>`
     - 1362.2 ms
     - 12.1 MiB
     - 1460.5 ms
     - 17.3 MiB
     - 1.42x
     - 1.07x
   * - :ref:`scale/plot_05_axes_grid_lines <sphx_glr_auto_scale_plot_05_axes_grid_lines.py>`
     - 58817.4 ms
     - 3.9 MiB
     - 58642.3 ms
     - 5.1 MiB
     - 1.29x
     - 1.00x
   * - :ref:`scale/plot_06_shared_colorbar_lognorm <sphx_glr_auto_scale_plot_06_shared_colorbar_lognorm.py>`
     - 236.8 ms
     - 2.5 MiB
     - 285.1 ms
     - 4.1 MiB
     - 1.69x
     - 1.20x
   * - :ref:`scale/plot_07_matplotlib_comparison <sphx_glr_auto_scale_plot_07_matplotlib_comparison.py>`
     - 1.3 ms
     - 76 KiB
     - 1.3 ms
     - 76 KiB
     - 0.99x
     - 0.95x
   * - :ref:`scale/plot_08_vector_over_raster <sphx_glr_auto_scale_plot_08_vector_over_raster.py>`
     - 437.4 ms
     - 3.2 MiB
     - 531.2 ms
     - 5.6 MiB
     - 1.75x
     - 1.21x
   * - :ref:`scale/plot_09_output_scaling <sphx_glr_auto_scale_plot_09_output_scaling.py>`
     - 2.3 ms
     - 79 KiB
     - 2.2 ms
     - 78 KiB
     - 0.99x
     - 0.97x
   * - :ref:`scale/plot_10_many_groups_with_colorbars <sphx_glr_auto_scale_plot_10_many_groups_with_colorbars.py>`
     - 0.6 ms
     - 74 KiB
     - 0.5 ms
     - 74 KiB
     - 0.99x
     - 0.90x

"Size"/"Time" are JSON relative to binary -- 2.0x under Size means the JSON payload is twice the binary one's size; under Time means it took twice as long to build. A ratio near 1.0x on a small figure means the encoder found nothing worth switching: every array in it was already under the threshold where a base64 wrapper costs more than it saves.
