"""
Mosaic titles, planning a layout ahead, and an ordinary grid's own lookup
============================================================================

Three smaller pieces that round out the lookup API, none of which fit
naturally into the bigger examples elsewhere in this gallery:

``axes_titles`` is ``axes_ids``'s sibling on
:meth:`~plotpress.figure.GroupLayout.add_group` -- the same mosaic-style
"a non-``None`` entry marks presence *and* sets one thing about that
axes" idea, just setting each axes' *drawn* title instead of its
(undrawn, unique) id.

``GroupLayout.remove_group(row, col)`` drops a *planned* group before
anything is built -- for when a layout is easier to describe as "the full
shape, minus a couple of cells" than to build up cell by cell.
:meth:`~plotpress.figure.Figure.remove_group` (see
:doc:`plot_15_dashboard_mixed_shapes_and_masks` for that one) is its
post-build sibling.

``Figure.get_ax(row=, col=)`` also works with no groups involved at all
-- a plain axes' own position in an ordinary
:func:`~plotpress.figure.subplots` grid, shown last specifically to
contrast with :meth:`~plotpress.figure.Group.get_ax`'s *inner* position
used everywhere else in this gallery. See
:doc:`plot_17_finding_groups_and_axes_again` for the rest of the lookup
API -- ``get_group``, ``id=``, ``many=True`` -- as its own dedicated
example.
"""
import numpy as np
import plotpress

# -- axes_titles: mosaic-style presence + each axes' own drawn title -------
layout = plotpress.GroupLayout(1, 2)
layout.add_group(0, 0, axes_titles=[["sin", "cos"]], title="Trig")
layout.add_group(0, 1, 2, 2, title="Grid")   # a plain rectangle alongside it

# The 2x2 "Grid" group isn't needed for anything below -- planned as part
# of a bigger layout, then dropped before building, the same way it could
# have simply never been added, just easier to describe this way when a
# layout starts as "the full shape" and gets trimmed down from there.
layout.remove_group(0, 1)

fig, axes = plotpress.subplots_from_groups(layout, figsize=(7, 3.2))
x = np.linspace(0, 2 * np.pi, 100)
trig = fig.get_group(title="Trig")
trig.get_ax(title="sin").plot(x, np.sin(x), color="#1f77b4")
trig.get_ax(title="cos").plot(x, np.cos(x), color="#d62728")
# Each axes' title is real, drawn text -- get_ax(title=) found it the same
# way a reader would, by what's actually printed above the panel.
print([ax.get_title() for ax in trig.flat_axes()])
fig.tight_layout()   # reserves room for "Trig"'s own box/title above the panels

# -- Figure.get_ax(row=, col=): the *ordinary*, ungrouped case -------------
# No GroupLayout here at all -- row/col is just this axes' own position in
# a plain subplots() grid, the case Group.get_ax()'s own row/col
# elsewhere in this gallery is deliberately *not*: that one addresses a
# group's inner shape; this one addresses the whole figure's only shape.
fig2, axes2 = plotpress.subplots(2, 2, figsize=(6, 5))
for r in range(2):
    for c in range(2):
        axes2[r, c].plot(x, np.sin(x + r + c))
bottom_right = fig2.get_ax(row=1, col=1)
assert bottom_right is axes2[1, 1]
for side in bottom_right.spines:
    bottom_right.spines[side].set_color("#2ca02c")
    bottom_right.spines[side].set_linewidth(2.0)
fig2.tight_layout()
