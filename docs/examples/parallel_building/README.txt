.. _parallel_building_gallery:

Building a figure across processes
=====================================

A ``Figure`` isn't itself something a ``joblib``/``multiprocessing`` worker
can share with the process that owns it -- pickling one to hand it to a
worker (or back) always produces a copy, never a live reference, so
mutating an axes inside a worker never touches the original. ``fig.adopt_axes()``
is the fix: it merges an axes built standalone -- most often a worker's
returned copy -- into the real figure, in place of whichever of its own
axes shares that grid position.
