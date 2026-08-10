.. _live_streaming_gallery:

Live streaming
==============

``plotpress.qt.LiveArtist`` streams data into a Qt window as it's collected --
patching the already-loaded page in place rather than reloading it, so it
holds tens of Hz even on large lines and meshes where a full reload would
collapse to 4-5 Hz. See the "Streaming live data" section of
:doc:`/user_guide/viewing` for the API itself and the measured numbers.

The examples here can't drive a real ``QWebEngineView`` at doc-build time
(CI has no Qt binding installed), so each renders the same acquisition
sequence a ``LiveArtist`` would show live, frame by frame, as a GIF instead.
**Acquisition patterns** covers the shapes data arrives in in the abstract
(sparse vs. dense, growing vs. fixed extent); **Lab instrument examples**
puts those shapes into the specific instruments a working lab actually
watches update in real time.

Every example is split the same way real acquisition code would be: a
callback that receives new data and pushes it to the plot (unchanged when
you swap in a real Qt window), fed by a loop that simulates an instrument
(the part meant to be replaced with your own driver). Copy one, swap its
data source for real hardware, and the plotting side needs no other
change.
