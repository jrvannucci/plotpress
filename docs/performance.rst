Performance
===========

Every :ref:`gallery example <gallery>` serialized to static SVG and to self-contained interactive HTML, with output sizes. Interactive HTML embeds the same SVG **plus** the per-axes data the toolbar needs for zoom / point-picking (the picked values, and mesh ``z`` grids), so it is larger and slower than SVG -- most for mesh-heavy figures.

Best of 5 runs, one machine. Regenerate with ``python benchmarks/example_timings.py``.

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
     - 1.0 ms
     - 9 KiB
     - 1.5 ms
     - 62 KiB
   * - ``plot_02_scatter``
     - 1
     - 1.6 ms
     - 35 KiB
     - 2.0 ms
     - 90 KiB
   * - ``plot_03_bar``
     - 1
     - 0.3 ms
     - 3 KiB
     - 0.4 ms
     - 48 KiB
   * - ``plot_04_barh``
     - 1
     - 0.2 ms
     - 3 KiB
     - 0.3 ms
     - 48 KiB
   * - ``plot_05_stem``
     - 1
     - 0.3 ms
     - 5 KiB
     - 0.4 ms
     - 51 KiB
   * - ``plot_06_step``
     - 1
     - 0.3 ms
     - 2 KiB
     - 0.4 ms
     - 48 KiB
   * - ``plot_07_fill_between``
     - 1
     - 1.4 ms
     - 11 KiB
     - 1.8 ms
     - 65 KiB
   * - ``plot_08_stackplot``
     - 1
     - 0.4 ms
     - 4 KiB
     - 0.6 ms
     - 50 KiB
   * - ``plot_09_hist``
     - 1
     - 0.5 ms
     - 5 KiB
     - 0.6 ms
     - 51 KiB
   * - ``plot_10_boxplot``
     - 1
     - 0.3 ms
     - 4 KiB
     - 0.4 ms
     - 50 KiB
   * - ``plot_11_errorbar``
     - 1
     - 0.3 ms
     - 4 KiB
     - 0.5 ms
     - 50 KiB
   * - ``plot_12_violin``
     - 1
     - 1.4 ms
     - 10 KiB
     - 1.8 ms
     - 63 KiB
   * - ``plot_13_eventplot``
     - 1
     - 1.2 ms
     - 15 KiB
     - 1.6 ms
     - 65 KiB
   * - ``plot_14_hist2d``
     - 1
     - 0.5 ms
     - 6 KiB
     - 0.9 ms
     - 59 KiB
   * - ``plot_15_pie``
     - 1
     - 0.1 ms
     - 1 KiB
     - 0.1 ms
     - 47 KiB
   * - ``plot_16_imshow``
     - 1
     - 2.2 ms
     - 24 KiB
     - 7.7 ms
     - 214 KiB
   * - ``plot_17_pcolormesh``
     - 1
     - 3.5 ms
     - 17 KiB
     - 17.4 ms
     - 432 KiB
   * - ``plot_18_contour``
     - 1
     - 33.1 ms
     - 87 KiB
     - 38.8 ms
     - 278 KiB
   * - ``plot_19_quiver``
     - 1
     - 2.0 ms
     - 27 KiB
     - 2.6 ms
     - 84 KiB
   * - ``plot_20_subplots``
     - 4
     - 2.2 ms
     - 23 KiB
     - 3.5 ms
     - 97 KiB
   * - ``plot_21_loglog``
     - 1
     - 1.1 ms
     - 7 KiB
     - 1.4 ms
     - 55 KiB
   * - ``plot_22_annotations``
     - 1
     - 0.5 ms
     - 5 KiB
     - 0.8 ms
     - 55 KiB
   * - ``plot_23_mesh_grid``
     - 500
     - 282.6 ms
     - 2.9 MiB
     - 649.1 ms
     - 11.0 MiB

The ``plot_23_mesh_grid`` row is the deliberate stress case: 500 independent pcolormesh axes on one figure. Its interactive HTML is dominated by the 500 embedded mesh ``z`` grids; lower ``fig.to_html(pick_precision=...)`` (or ``fig.save(..., pick_precision=...)``) to trade readout precision for a smaller file.
