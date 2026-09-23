"""Vanilla-JS interactivity injected into interactive HTML/pop-up output.

Fully self-contained (no external requests) so it works under strict CSPs such
as Jupyter and sandboxed webviews.

A menu bar docked above the figure selects one **mode** at a time; nothing is
interactive until a mode is chosen (single selection -- picking one cancels the
others). A single click on a mode item selects it without closing its own
menu (a checkable item, not a one-shot action); double-click the active one
to deselect it back to no tool active -- a persistent mode indicator to the
menu bar's own right always shows which, if any, is active, with no menu
needing to be open. Text on the figure is left unselectable for as long as
any mode is active -- every mode's own drag (a pan, a rubber-band box,
dragging a pin's own label box) can sweep across tick labels, titles, or
another pin's text the same way Pan/Zoom's whole-figure pan always
could, so the selection guard isn't scoped to any one of them.

* **Pan/Zoom** (zoom-in cursor, internal mode ``magnify``) -- the
  same whole-figure wheel zoom as Ctrl+wheel under Axis Zoom, but a *plain*
  wheel, no Ctrl needed -- for wherever holding Ctrl is awkward, or a
  browser/OS extension already claims it. Deliberately its own mode rather
  than folded into Axis Zoom: selecting it is an explicit choice to have
  this figure capture the page's scroll, so it never surprises a reader who
  just wanted Axis Zoom's rubber-band drag. Drag pans the same whole-figure
  view (native scroll under the hood) in any direction, so a zoomed-in
  figure stays fully reachable without switching to Axis Span -- always the
  figure's view, never an axes' own data range, isolating it completely
  from per-axes zoom/pan. Double-click resets that view (there is no
  per-axes zoom here to reset the way Axis Span/Zoom's double-click does).
  Sits standalone at the toolbar's far left, not behind a menu -- the one
  whole-figure-level navigation tool, reached for often enough to be worth
  skipping a menu's extra click (see below).
* **Axis Span** (internal mode ``span``) -- drag to pan (grab cursor).
* **Axis Zoom** (internal mode ``zoom``) -- two distinct gestures (crosshair
  cursor). Drag a rubber-band box to zoom *one axes* into it, in data space
  (ticks recompute). Ctrl+wheel (or a trackpad pinch, which the browser
  reports the same way) zooms the *whole figure* instead, centered on the
  cursor, regardless of which axes (if any) is under it -- the useful
  gesture on a figure with many small axes, where "zoom whatever tiny panel
  the cursor happens to be over" wouldn't be. It grows the SVG's own
  rendered size rather than cropping its viewBox, so it never touches any
  axes' data range, ticks, or pick data -- and the overflow past the
  viewport is real, native-scrollable page content, not merely a cropped
  coordinate system with nothing for a scrollbar to reach. A plain wheel
  (no Ctrl) is left alone to scroll the page as it would over any other
  content.
* **Reset All Axes** -- restores every axes' own pan/zoom (Axis Span/Zoom's
  per-axes data range) back to its original view; leaves whole-figure
  magnification and every pin/annotation untouched. A one-shot action, not
  a mode. In Axis Span/Zoom mode, double-clicking a single plot resets only
  that plot, the same as this does for all of them at once. Sits right
  after Axis Span/Zoom -- the pair of tools it undoes.
* **Home** -- restores whole-figure magnification (Pan/Zoom
  or Ctrl+wheel-under-Axis-Zoom) back to its natural size; leaves every
  axes' own pan/zoom and every pin/annotation untouched. A figure-level
  action, not a mode -- it doesn't select/deselect anything, just fires
  once. Sits standalone right after Pan/Zoom, the tool it undoes -- neither
  Reset button (this one or Reset All Axes, in the Axes menu) clears
  pins/annotations -- a view reset repositions them (they already track
  pan/zoom live, the same machinery an Axis Span drag uses), it doesn't
  delete them; that's what Clear Points/Point Picking's own
  click-a-pin-to-remove-it are for.
* **Fit Width** -- a one-shot snap to whatever whole-figure magnification
  makes the figure exactly as wide as the current browser window, for a
  figure whose natural size (standalone HTML/pop-up output only -- an
  embedded figure, e.g. inside a Report, already CSS-scales to its
  container) is wider than the viewport. Deliberately separate from Home
  rather than folded into it: most figures are already narrower than the
  viewport, and redefining Home as "fit width" would zoom *those* in past
  their natural size by default -- a real regression for the common case to
  fix the uncommon one. Not a persistent "always fit" mode -- like Home, it
  fires once; resizing the window afterward doesn't re-fit automatically.
* **Point Picking** (internal mode ``pick``) -- click a plot to pin an
  annotation of the value there; snaps to the nearest data point, else a
  free coordinate readout (arrow cursor). Click a pin to remove it, or use
  the **Clear Points** button/Escape to remove all of them at once. A
  marker's own dot scales with the axes it lands on, so it never dwarfs a
  tiny panel in a large grid, and stays that same on-screen size at any
  whole-figure zoom level (Pan/Zoom or Axis Zoom's Ctrl+wheel) -- growing
  right along with the rest of the figure would otherwise turn a readable
  dot into a blob covering the very cell it's pointing at a few zoom ticks
  later, defeating the point of zooming in to see it more clearly. Its
  label box sits
  offset from the dot by default; a thin leader line (arrowhead on the dot
  end) connects the two whenever the box isn't already touching the dot,
  and the box itself is draggable -- grab it (not the dot) and move it
  wherever reads best, while Point Picking is the active mode -- without
  moving the dot off the data point it represents.
  A dragged position sticks through every later pan/zoom/arrow-key step and
  a Save/Save As round trip, the same as everything else about the pin.
* **Hide Points** -- hides every Point Picking pin without deleting any of
  them; toggling it back to "Show Points" brings them back exactly as they
  were. Independent of Hide Annotations below -- an annotation note stays
  visible while Hide Points is on, and vice versa.
* **Clear Points** -- removes every Point Picking pin, and *only* those --
  an annotation note survives a Clear Points click untouched. Sits right
  after Point Picking, the tool it clears. A one-shot action, not a mode.
* **Annotate** (internal mode ``note-plain``) -- drop a plain text box
  anywhere on the figure: a caption, not a callout. No dot, no leader
  arrow, and always pinned to a fixed figure position -- even dropped
  inside an axes, it never tracks that axes' data coordinate, since it
  isn't pointing at anything for a pan/zoom to stay aligned with.
* **Annotate Arrow** (internal mode ``note-free``) -- drop a user-written
  note anywhere on the figure, not locked to any datum, but pointing at
  wherever it was actually dropped: a dot at that spot, a draggable label
  box, and a leader arrow connecting the two whenever the box isn't
  already touching the dot. Inside an axes it tracks that axes' data
  coordinate; outside one it stays at its fixed figure position, the same
  as Annotate above.
* **Annotate Point** -- like Point Picking, but prompts for text and locks
  a user-written note to that datum instead of the auto-generated
  readout; still steppable by arrow key and still tracks pan/zoom, using
  the exact same nearest-datum resolution Point Picking's own click
  handler does. Classed as an annotation, not a Point Picking marker: it
  survives a Clear Points click, Hide Points leaves it visible, and it
  never appears in Extract's output (Extract returns only Point Picking
  markers -- see below), the same as every other annotation.

  Each Annotate mode's own box is draggable the same way a Point Picking
  pin's is -- see above -- while that specific mode is active, independent
  of every other kind of pin's own dragging (see boxDraggableNow: each
  kind of pin only drags under the mode that would have created it).
* **Hide Annotations** -- the mirror of Hide Points: hides every annotation
  note (from any of the three Annotate tools above) without deleting any of
  them, *plus* every boxed ``ax.text()``/``ax.annotate(bbox=...)`` callout
  the figure itself drew (a plain, unboxed label is not a callout in this
  sense and always stays visible) -- a static callout reads the same way on
  screen as a note, and is closer in spirit to one than to a picked data
  point. Toggling it back to "Show Annotations" brings everything back
  exactly as it was, including any text or selection state -- it only ever
  flips a CSS display rule, never touches the underlying marker/text data.
* **Clear Annotations** -- the mirror of Clear Points: removes every
  annotation note, and *only* those -- a Point Picking pin survives
  untouched. Sits right after the three Annotate tools it clears. A
  one-shot action, not a mode. (Escape still clears everything at once, both kinds
  -- the one place "clear all" still means literally all -- and, unlike
  either Clear button, also deselects the active tool, back to no tool
  active; see below.)

Pan/Zoom, Home, and Fit Width sit standalone at the bar's far left, not
behind a menu -- the whole-figure-scoped tool reached for most, and the two
resets that undo it, close enough at hand that a menu's extra click to get
to them isn't worth paying every time. Everything else groups into four
menus by what it does, not the order features were added in --
**Axes**: Axis Span/Zoom, then Reset All Axes, the pair it undoes.
**Point Picking**: the tool, Hide Points, Clear Points, and Extract --
Extract lives here, not in its own menu or under Annotate, because it only
ever returns Point Picking markers (see below). **Annotate**: its three
tools (Annotate, Annotate Arrow, Annotate Point), then Hide Annotations
and Clear Annotations. **File**: Save, Save As. A
caller's own custom tools get a fifth **Custom** menu, created lazily on
first ``plotpressAddTool()`` call -- never folded into a built-in one.

**Extract** opens a panel to copy out picked points (not annotations -- see
``doExtract()``) as CSV.

**Save**/**Save As** both persist the current page -- pan/zoom, every
pin/annotation, hidden-legend-series toggles, and Hide Points/Hide
Annotations -- as a self-contained HTML file: reopening it resumes exactly
where this session left off, not just what was originally plotted. They are
functionally identical today: both open the browser's native save picker
(Chromium, a secure context; a plain download everywhere else) pre-filled
with a filename derived from the page's ``<title>``, not a handle to
whatever file the page was originally opened from -- a plain HTML file
opened by double-clicking or navigating to it carries no such handle for
the page to reuse, so there is nothing to reuse it. Overwriting the original
file is one click away (browsers already warn before replacing an existing
file at the same path) rather than automatic. Both work the same way inside
a :class:`~plotpress.Report`'s embedded figure -- each panel is its own
independent document, so saving from one saves only that panel, not the
whole report.

Legend entries remain clickable to toggle series regardless of mode.
"""

import os

_JS_DIR = os.path.join(os.path.dirname(__file__), "_js")
# The IIFE wrapper stays here, not in any fragment -- everything inside was
# split by section boundary only, never reordered, so concatenating these in
# the order below reconstructs the exact same script byte-for-byte (verified
# against the pre-split file when this split was made). Splitting the JS
# itself (not just where the Python `_JS_SOURCE` variable is defined) is what
# makes "where's the Slice code" a file jump instead of grepping one
# multi-thousand-line string -- _slice.js alone is most of what this file
# grew by when the Slice tool was added.
_JS_FRAGMENTS = [
    "_core.js",              # DOM/page setup, binary+columnar payload decoding,
                              # pan/zoom/layout primitives, META/STYLE/LAYOUT/CUR
    "_toolbar.js",            # menu bar, TOOLS, startup options, PICK/FRAMES/UNITS
    "_mode_buttons.js",       # per-mode toolbar buttons, custom tools, setMode()
    "_pan_zoom.js",           # pointer-to-data helpers, rubber-band box, pan/zoom drag
    "_slice.js",              # the Slice tool + its companion panel
    "_legend_and_pick.js",    # legend click-to-hide, Point Picking mode, per-axes zoom
    "_ticks_pins_and_geometry.js",  # tick/locator/formatter parity with ticker.py,
                              # the pin registry, and pixel-space nearest-point picking
    "_extract.js",            # the Extract-to-CSV/JSON panel
    "_save.js",               # Save / Save As, and replaying saved state on reload
    "_sliders.js",            # frame/data sliders (plot_frames/pcolormesh_frames)
]


def _read_js_fragment(name: str) -> str:
    with open(os.path.join(_JS_DIR, name), encoding="utf-8") as fh:
        return fh.read()


_JS_SOURCE = (
    "\n(function () {\n"
    + "".join(_read_js_fragment(name) for name in _JS_FRAGMENTS)
    + "})();\n"
)


def _strip(source: str) -> str:
    """Drop comment-only lines, blank lines, and leading indentation.

    The whole toolbar is inlined into *every* interactive figure, so these
    bytes are paid once per figure rather than once per page -- 47 KiB of
    source became the single largest fixed component of an interactive HTML
    file.

    Deliberately conservative: newlines are kept, because JavaScript's
    automatic semicolon insertion makes joining lines unsafe, and a line is
    only treated as a comment when its *stripped* form begins with ``//``,
    which cannot occur inside a string here -- the source contains no template
    literals and no line-continued strings, so no string spans a line break.
    Identifier renaming is left to a real minifier if it is ever wanted.
    """
    out = []
    for line in source.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        out.append(s)
    return "\n".join(out)


INTERACTIVE_JS = _strip(_JS_SOURCE)
