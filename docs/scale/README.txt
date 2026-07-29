.. _scale_gallery:

Large-scale figures
===================

Figures big enough that build time and file size stop being incidental and
become the design constraint: a million points in one line, millions of mesh
cells, a thousand series on one axes, hundreds of axes on one canvas.

This is the case plotpress is built for, and the examples are arranged to show
*why* rather than to assert it. Each one names the specific thing that would
otherwise dominate -- per-artist Python overhead, one SVG node per datum, a mesh
emitted as a quarter of a million rectangles, pick data inlined at full
precision -- and says what the library does instead. Several are timed in the
figure itself, and one runs the same workloads through matplotlib on the machine
that built these docs and plots both.

The numbers are honest about their limits. They come from one machine, one
Python, one run; they measure figure construction plus serialization, not
interactive redraw; and matplotlib is doing more work than plotpress in several
of them, because it is a far larger library with more to configure. Where
plotpress is faster it is almost always for the same structural reason -- fewer
Python objects and fewer output nodes -- and the comparison example says which
cases those are.
