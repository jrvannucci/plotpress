.. _data_roundtrip_gallery:

Reloading data from a saved HTML
---------------------------------

``plotpress.load_data()`` reads the plotted data straight back out of a
saved interactive HTML file -- no need for the original Python objects
that built it to still be around. These examples round-trip through it:
reload a figure's data, transform it, and rebuild a new figure in a
similar layout.
