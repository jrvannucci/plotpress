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
     - 44.2 ms
     - 2.6 ms
   * - ``scatter_5k_points``
     - 15.0 ms
     - 119.5 ms
     - 22.1 ms
   * - ``pcolormesh_300x300``
     - 9.5 ms
     - 5859.0 ms
     - 16.0 ms
   * - ``many_axes_8x8_grid``
     - 37.4 ms
     - 1468.3 ms
     - 64.8 ms

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
   * - ``plot_01_line``
     - 1
     - 1.1 ms
     - 9 KiB
     - 1.6 ms
     - 55 KiB
   * - ``plot_02_scatter``
     - 1
     - 1.9 ms
     - 35 KiB
     - 2.4 ms
     - 83 KiB
   * - ``plot_03_bar``
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 42 KiB
   * - ``plot_04_barh``
     - 1
     - 0.2 ms
     - 3 KiB
     - 0.3 ms
     - 42 KiB
   * - ``plot_05_stem``
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.4 ms
     - 44 KiB
   * - ``plot_06_step``
     - 1
     - 0.3 ms
     - 2 KiB
     - 0.4 ms
     - 42 KiB
   * - ``plot_07_fill_between``
     - 1
     - 1.3 ms
     - 11 KiB
     - 1.8 ms
     - 58 KiB
   * - ``plot_08_stackplot``
     - 1
     - 0.5 ms
     - 4 KiB
     - 0.8 ms
     - 43 KiB
   * - ``plot_09_hist``
     - 1
     - 0.6 ms
     - 5 KiB
     - 0.7 ms
     - 44 KiB
   * - ``plot_10_boxplot``
     - 1
     - 0.3 ms
     - 4 KiB
     - 0.4 ms
     - 43 KiB
   * - ``plot_11_errorbar``
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.5 ms
     - 44 KiB
   * - ``plot_12_violin``
     - 1
     - 1.5 ms
     - 10 KiB
     - 1.9 ms
     - 56 KiB
   * - ``plot_13_eventplot``
     - 1
     - 1.2 ms
     - 15 KiB
     - 1.6 ms
     - 58 KiB
   * - ``plot_14_hist2d``
     - 1
     - 0.6 ms
     - 6 KiB
     - 1.0 ms
     - 53 KiB
   * - ``plot_15_pie``
     - 1
     - 0.1 ms
     - 1 KiB
     - 0.1 ms
     - 40 KiB
   * - ``plot_16_imshow``
     - 1
     - 1.5 ms
     - 15 KiB
     - 7.2 ms
     - 198 KiB
   * - ``plot_17_pcolormesh``
     - 1
     - 3.3 ms
     - 12 KiB
     - 19.2 ms
     - 420 KiB
   * - ``plot_18_contour``
     - 1
     - 33.2 ms
     - 87 KiB
     - 39.1 ms
     - 271 KiB
   * - ``plot_19_quiver``
     - 1
     - 2.0 ms
     - 27 KiB
     - 2.7 ms
     - 77 KiB
   * - ``plot_20_subplots``
     - 4
     - 2.6 ms
     - 22 KiB
     - 4.0 ms
     - 90 KiB
   * - ``plot_21_loglog``
     - 1
     - 1.0 ms
     - 6 KiB
     - 1.3 ms
     - 48 KiB
   * - ``plot_22_annotations``
     - 1
     - 0.6 ms
     - 5 KiB
     - 0.9 ms
     - 48 KiB
   * - ``plot_24_contourf``
     - 1
     - 19.3 ms
     - 11 KiB
     - 20.2 ms
     - 50 KiB
   * - ``plot_25_hexbin``
     - 1
     - 14.5 ms
     - 62 KiB
     - 15.1 ms
     - 101 KiB
   * - ``plot_26_twin_axes``
     - 2
     - 1.6 ms
     - 12 KiB
     - 2.3 ms
     - 63 KiB
   * - ``plot_27_curvilinear_mesh``
     - 1
     - 295.2 ms
     - 41 KiB
     - 295.5 ms
     - 105 KiB
   * - ``plot_28_gouraud``
     - 2
     - 195.1 ms
     - 288 KiB
     - 194.8 ms
     - 339 KiB
   * - ``plot_29_reference_lines``
     - 1
     - 1.8 ms
     - 15 KiB
     - 2.5 ms
     - 68 KiB
   * - ``plot_30_lognorm``
     - 2
     - 7.4 ms
     - 27 KiB
     - 39.9 ms
     - 886 KiB
   * - ``plot_31_shared_colorbar``
     - 6
     - 3.7 ms
     - 20 KiB
     - 13.3 ms
     - 262 KiB
   * - ``plot_32_broken_barh``
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.5 ms
     - 41 KiB
   * - ``plot_33_matshow``
     - 1
     - 0.6 ms
     - 6 KiB
     - 0.7 ms
     - 46 KiB
   * - ``plot_34_spy``
     - 1
     - 0.4 ms
     - 3 KiB
     - 0.6 ms
     - 46 KiB
   * - ``plot_35_stairs``
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 42 KiB
   * - ``plot_36_axline``
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.5 ms
     - 44 KiB
   * - ``scale/plot_01_many_axes``
     - 500
     - 411.6 ms
     - 2.6 MiB
     - 809.6 ms
     - 10.7 MiB
   * - ``scale/plot_02_million_point_line``
     - 1
     - 173.4 ms
     - 46 KiB
     - 202.5 ms
     - 85 KiB
   * - ``scale/plot_03_multimillion_mesh``
     - 1
     - 348.7 ms
     - 774 KiB
     - 344.5 ms
     - 813 KiB
   * - ``scale/plot_04_thousand_series``
     - 1
     - 952.9 ms
     - 6.9 MiB
     - 1419.1 ms
     - 17.2 MiB
   * - ``scale/plot_05_axes_grid_lines``
     - 900
     - 20581.2 ms
     - 2.1 MiB
     - 41212.4 ms
     - 4.1 MiB
   * - ``scale/plot_06_shared_colorbar_lognorm``
     - 144
     - 84.2 ms
     - 466 KiB
     - 237.2 ms
     - 3.8 MiB
   * - ``scale/plot_07_matplotlib_comparison``
     - 1
     - 0.9 ms
     - 4 KiB
     - 1.1 ms
     - 44 KiB
   * - ``scale/plot_08_vector_over_raster``
     - 1
     - 279.0 ms
     - 599 KiB
     - 281.0 ms
     - 658 KiB
   * - ``scale/plot_09_output_scaling``
     - 1
     - 1.6 ms
     - 6 KiB
     - 1.9 ms
     - 46 KiB

The ``scale/plot_01_many_axes`` row is the deliberate stress case: 500 independent pcolormesh axes on one figure. Its interactive HTML is dominated by the 500 embedded mesh ``z`` grids; lower ``fig.to_html(pick_precision=...)`` (or ``fig.save(..., pick_precision=...)``) to trade readout precision for a smaller file.
