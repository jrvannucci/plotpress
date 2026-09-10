API reference
=============

Top level
---------

.. currentmodule:: plotpress

.. autosummary::

   Figure
   subplots
   subplots_from_layout
   subplots_from_groups
   GroupLayout
   Group
   Report
   load_data
   load_data_xarray
   select_panel
   Style
   Normalize
   get_cmap
   available_colormaps

Figure
------

.. autoclass:: plotpress.figure.Figure
   :members:
   :undoc-members:

.. autofunction:: plotpress.subplots

.. autofunction:: plotpress.subplots_from_layout

Grouping
--------

.. autofunction:: plotpress.subplots_from_groups

.. autoclass:: plotpress.figure.GroupLayout
   :members:

.. autoclass:: plotpress.figure.Group
   :members:

Report
------

.. autoclass:: plotpress.figure.Report
   :members:

.. autofunction:: plotpress.load_data

.. autofunction:: plotpress.load_data_xarray

.. autofunction:: plotpress.select_panel

Axes
----

.. autoclass:: plotpress.axes.Axes
   :members:
   :undoc-members:

Ticks & dates
-------------

Backs :meth:`~plotpress.axes.Axes.set_xlocator`/``set_ylocator``/
``set_xformat``/``set_yformat``'s spec grammar, and the datetime conversion
:meth:`~plotpress.axes.Axes.plot` (and every other plotting method) applies
automatically to datetime-like ``x``/``y`` data -- documented here for
anyone building a spec by hand, or converting a date to/from the plain
float days-since-epoch every plotpress axis works in internally.

.. automodule:: plotpress.dates
   :members:

.. automodule:: plotpress.ticker
   :members:

Style & colors
--------------

.. autoclass:: plotpress.style.Style
   :members:

.. autoclass:: plotpress.colors.Normalize
   :members:
