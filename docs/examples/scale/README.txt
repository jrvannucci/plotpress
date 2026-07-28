.. _scale_gallery:

Large-scale figures
-------------------

Figures big enough that build time and file size become the design constraint --
hundreds of axes on one canvas, or hundreds of thousands of mesh cells. These
are where avoiding per-artist Python overhead and rasterizing meshes to a single
embedded image stop being implementation details and start being the reason the
figure renders at all.
