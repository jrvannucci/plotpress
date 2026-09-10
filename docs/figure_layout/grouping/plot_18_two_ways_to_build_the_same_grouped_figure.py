"""
Two ways to build the same grouped figure
============================================

The same target figure -- a 2x4 grid with its bottom-right cell removed,
split into a full 2x2 "Left" group and an L-shaped 3-panel "Right" group
-- built two different ways.

**Declaratively, with** :class:`~plotpress.figure.GroupLayout`: describe
each group's outer position and inner shape (a ``mask`` for the L), and
:func:`~plotpress.figure.subplots_from_groups` works out the one shared
grid that fits both and creates every axes already assigned to its
group. Best when the shape is known up front and you'd rather not index
into a flat array by hand.

**Imperatively, from an ordinary grid**: call
:func:`~plotpress.figure.subplots` for the full 2x4, delete the cell you
don't want with :meth:`~plotpress.axes.Axes.remove`, then draw the boxes
afterward with :meth:`~plotpress.figure.Figure.group`, passing each a
plain list of the axes it contains. Best when the grid already exists,
when which cells to group is decided from data at runtime, or when you
want a plain ``subplots()`` call you can read at a glance.

Both produce the same structure: same live-axes count, same two group
titles, each group bounding the same cells. The pieces
:class:`~plotpress.figure.GroupLayout` adds on top -- a mask that also
carries ids/titles (``axes_ids``/``axes_titles``), pre-build
:meth:`~plotpress.figure.GroupLayout.remove_group` -- are conveniences
over this same imperative core, not a separate mechanism.
"""
import numpy as np
import plotpress

rng = np.random.default_rng(7)
x = np.linspace(0, 2 * np.pi, 80)


def fill(ax):
    ax.plot(x, np.sin(x + rng.uniform(0, 6)), color="#333333", linewidth=1.1)
    ax.set_xticks([])
    ax.set_yticks([])


# -- 1. Declarative: GroupLayout + subplots_from_groups --------------------
layout = plotpress.GroupLayout(1, 2)
layout.add_group(0, 0, nrows=2, ncols=2, title="Left", color="#1f77b4")
layout.add_group(0, 1, nrows=2, ncols=2, mask=[[1, 1], [1, 0]],
                 title="Right", color="#d62728")

fig_declarative, groups = plotpress.subplots_from_groups(
    layout, figsize=(11, 5.5))
for group in groups.ravel():
    for ax in group.ravel():
        if ax is not None:
            fill(ax)
fig_declarative.group_spacing(wspace=26.0)
fig_declarative.suptitle("1. GroupLayout: describe the shape, let it place everything")
fig_declarative.tight_layout()


# -- 2. Imperative: subplots(), remove(), group() afterward ----------------
fig_manual, axes = plotpress.subplots(2, 4, figsize=(11, 5.5))
axes[1, 3].remove()                       # the cell the mask above dropped
for row in axes:
    for ax in row:
        if ax in fig_manual.axes:         # remove() took axes[1, 3] out
            fill(ax)

fig_manual.group("Left", list(axes[0:2, 0:2].ravel()), color="#1f77b4")
fig_manual.group("Right", [axes[0, 2], axes[0, 3], axes[1, 2]], color="#d62728")
fig_manual.group_spacing(wspace=26.0)
fig_manual.suptitle("2. subplots() + remove() + group(): build the grid, then box it")
fig_manual.tight_layout()


# -- The two figures have the same structure ------------------------------
def summary(fig):
    groups = fig.get_groups()
    return {
        "live axes": len(fig.axes),
        "groups": sorted(g.title for g in groups),
        "Left panels": len(fig.get_group(title="Left").flat_axes()),
        "Right panels": len(fig.get_group(title="Right").flat_axes()),
    }


print("declarative:", summary(fig_declarative))
print("manual:     ", summary(fig_manual))
assert summary(fig_declarative) == summary(fig_manual)
