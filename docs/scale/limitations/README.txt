.. _scale_limits_gallery:

Where it runs out
-----------------

The examples above are the cases the design is good at. These are the ones it is
not, and they are all consequences of the same two decisions that make the rest
fast: a mesh becomes a fixed-resolution image, and everything else becomes vector
nodes that are written out one per drawn thing.

None of these is a bug, and none has a workaround hiding in a keyword argument.
They are the shape of the trade, measured: where a curve stops flattening, where
extra data stops reaching the screen, and where the file grows faster than
anything downstream can consume. The general limitations of the library --
fonts, density estimates, projections -- are documented separately in
:doc:`../../user_guide/limitations`.
