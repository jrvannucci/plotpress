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
  were. Independent of Hide Annotations below -- an Annotation note stays
  visible while Hide Points is on, and vice versa.
* **Clear Points** -- removes every Point Picking pin, and *only* those --
  an Annotation note survives a Clear Points click untouched. Sits right
  after Point Picking, the tool it clears. A one-shot action, not a mode.
* **Annotation** (internal mode ``note-free``) -- drop a user-written note
  anywhere on the figure, not locked to any datum -- including the margins
  or the gap between subplots. Inside an axes it still tracks that axes'
  data coordinate; outside one it just stays at its fixed figure position.
  (A separate snap-to-nearest-datum variant, "Annotate Point," existed
  briefly here and was removed -- Point Picking already covers snapping to
  a datum; Annotation covers everything else, including a note dropped near
  but not exactly on a point.) Its own box is draggable the same way a
  Point Picking pin's is -- see above -- while Annotation is the active
  mode, independent of a Point Picking pin's own dragging (see
  boxDraggableNow: each kind of pin only drags under the mode that would
  have created it).
* **Hide Annotations** -- the mirror of Hide Points: hides every Annotation
  note without deleting any of them, *plus* every boxed
  ``ax.text()``/``ax.annotate(bbox=...)`` callout the figure itself drew (a
  plain, unboxed label is not a callout in this sense and always stays
  visible) -- a static callout reads the same way on screen as a note, and
  is closer in spirit to one than to a picked data point. Toggling it back
  to "Show Annotations" brings everything back exactly as it was, including
  any text or selection state -- it only ever flips a CSS display rule,
  never touches the underlying marker/text data.
* **Clear Annotations** -- the mirror of Clear Points: removes every
  Annotation note, and *only* those -- a Point Picking pin survives
  untouched. Sits right after Annotation, the tool it clears. A one-shot
  action, not a mode. (Escape still clears everything at once, both kinds
  -- the one place "clear all" still means literally all -- and, unlike
  either Clear button, also deselects the active tool, back to no tool
  active; see below.)

Pan/Zoom and Home sit standalone at the bar's far left, not
behind a menu -- the whole-figure-scoped tool reached for most, and the
reset that undoes it, close enough at hand that a menu's extra click to get
to them isn't worth paying every time. Everything else groups into four
menus by what it does, not the order features were added in --
**Axes**: Axis Span/Zoom, then Reset All Axes, the pair it undoes.
**Point Picking**: the tool, Hide Points, Clear Points, and Extract --
Extract lives here, not in its own menu or under Annotate, because it only
ever returns Point Picking markers (see below). **Annotate**: the tool,
Hide Annotations, then Clear Annotations. **File**: Save, Save As. A
caller's own custom tools get a fifth **Custom** menu, created lazily on
first ``plotpressAddTool()`` call -- never folded into a built-in one.

**Extract** opens a panel to copy out picked points (not annotations -- see
``doExtract()``) as CSV.

**Save As** downloads the current page -- pan/zoom, every pin/annotation,
hidden-legend-series toggles, and Hide Points/Hide Annotations -- as a new,
equally self-contained HTML file: reopening it resumes exactly where this
session left off, not just what was originally plotted. **Save** does the same but
tries to overwrite the file this page was opened from instead of downloading
a new one; that needs the File System Access API (Chromium, a secure
context), so elsewhere it falls back to the same download Save As does.
Both work the same way inside a :class:`~plotpress.Report`'s embedded
figure -- each panel is its own independent document, so saving from one
saves only that panel, not the whole report.

Legend entries remain clickable to toggle series regardless of mode.
"""

_JS_SOURCE = r"""
(function () {
  var svg = document.getElementById('plotpress-svg');
  if (!svg) return;
  // Captured before anything below mutates the DOM (the toolbar, its
  // injected <style>, sliders, ...) -- Save/Save As (far below) rebuild a
  // fresh copy of the page from this, plus one new payload script tag, so
  // the saved file's own toolbar script starts from the same clean slate
  // this one did rather than duplicating whatever this session has already
  // added to the live document.
  var ORIGINAL_DOC_HTML = document.documentElement.outerHTML;
  var SVGNS = 'http://www.w3.org/2000/svg';
  // The arrowhead every pin's box-to-dot leader line ends in (see
  // layoutPinArrow) -- one shared <marker> def, not one per pin, the same
  // "define once" reasoning as the injected <style> block below. Added
  // after ORIGINAL_DOC_HTML above is captured, so a Save/Save As copy's own
  // script (re-run fresh on that copy's own load) inserts its own rather
  // than inheriting two.
  var defs = document.createElementNS(SVGNS, 'defs');
  var arrowMarker = document.createElementNS(SVGNS, 'marker');
  arrowMarker.setAttribute('id', 'plotpress-pin-arrow');
  arrowMarker.setAttribute('viewBox', '0 0 8 8');
  arrowMarker.setAttribute('refX', '7'); arrowMarker.setAttribute('refY', '4');
  arrowMarker.setAttribute('markerWidth', '6'); arrowMarker.setAttribute('markerHeight', '6');
  arrowMarker.setAttribute('orient', 'auto');
  var arrowHead = document.createElementNS(SVGNS, 'path');
  arrowHead.setAttribute('d', 'M0,0 L8,4 L0,8 Z'); arrowHead.setAttribute('fill', '#666');
  arrowMarker.appendChild(arrowHead);
  defs.appendChild(arrowMarker);
  svg.insertBefore(defs, svg.firstChild);
  var vb = svg.getAttribute('viewBox').split(/\s+/).map(Number);
  var home = vb.slice();
  // `view` itself never changes any more -- kept only so pxPerUser() below
  // (unchanged) keeps reading a correct px-per-user-unit ratio, since it
  // divides the SVG's *rendered* CSS width by this. Whole-figure zoom now
  // grows/shrinks that rendered width directly (see zoomTo/applyZoomSize)
  // instead of cropping the viewBox, so real content overflows the page for
  // the browser's own scrollbars to reach -- cropping left nothing for a
  // scrollbar to scroll, since the SVG's on-page size never changed; only
  // custom drag-to-pan could reach the rest of a zoomed-in figure.
  var view = vb.slice();
  var zoomScale = 1;
  // The SVG's own on-page CSS size at zoomScale 1 -- the baseline zoomTo()
  // scales from, and what a pin's own 1/zoomScale compensation (see
  // layoutPin) assumes applyZoomSize is scaling up from. Read once, now: by
  // the time this script runs (placed right after the SVG in the
  // document), the browser has already laid it out, so this reflects its
  // true natural size (fixed pixels in a standalone file; whatever its
  // container currently resolves width:100% to, embedded) -- inserting the
  // menu bar later doesn't change it, since the bar is position:fixed and
  // so never participates in document flow/layout at all.
  var naturalW = svg.getBoundingClientRect().width;
  var naturalH = svg.getBoundingClientRect().height;
  var wrap = null;              // container holding the svg (for docked sliders)
  var dockedSliders = [];       // [{box, axesKey}] repositioned on pan/zoom
  var CURRENT_FRAME = {};       // slider unit -> current frame index
  var FRAME_INDEX = {};         // frame series id -> {entry, axesKey}
  var selectedPin = null;       // pin currently selected for arrow-key movement
  function apply() {
    svg.setAttribute('viewBox', view.join(' '));
    positionDocked();
  }

  // Re-measure the natural size on a window resize, but only while at 1x --
  // svg.style.width/height are unset there, so getBoundingClientRect() still
  // reflects the page's own current sizing rather than a stale zoomed value.
  // (A resize *while* zoomed is left as a known gap: rare enough, and there
  // is no natural size to re-derive from at that point anyway.)
  window.addEventListener('resize', function () {
    if (zoomScale === 1) {
      naturalW = svg.getBoundingClientRect().width;
      naturalH = svg.getBoundingClientRect().height;
    }
  });

  function applyZoomSize() {
    var zoomed = zoomScale > 1;
    document.body.classList.toggle('plotpress-zoomed', zoomed);
    if (zoomed) {
      svg.style.width = (naturalW * zoomScale) + 'px';
      svg.style.height = (naturalH * zoomScale) + 'px';
    } else {
      svg.style.width = ''; svg.style.height = '';
    }
    // Every pin's own 1/zoomScale compensation (see layoutPin) has to be
    // refreshed here too, not just when a pin is first dropped or moved --
    // otherwise a pin placed *before* this zoom change keeps whatever
    // scale factor it was born with, drifting out of sync with pins
    // dropped after it.
    document.querySelectorAll('.plotpress-pin').forEach(updatePinTransform);
    positionDocked();
  }

  // Whole-figure zoom, centered on the cursor. Grows/shrinks the SVG's own
  // rendered CSS size (never its viewBox or any axes' data range), so it's
  // the gesture that works uniformly across a figure with many small axes,
  // unlike a per-axes data zoom that only affects whichever panel happens to
  // be under the cursor -- and so the browser's native scrollbars, not a
  // custom drag, are what reach the rest of a zoomed-in figure. Clamped to
  // never shrink below the figure's own natural size (zooming "out" past
  // that has nothing left to reveal) or grow past a point where scrolling
  // further would gain nothing but more of it.
  // The compensating scroll below can only re-anchor the cursor's point once
  // there is somewhere to scroll *to* -- while the zoomed-in figure still
  // fits inside the viewport with room to spare, there is no overflow yet
  // for scrollBy() to spend, and the point under the cursor drifts slightly
  // for these first few ticks (layout alone decides where the bigger SVG
  // lands). Self-corrects the moment real overflow exists, which is also
  // the moment "did the point stay under the cursor" starts to matter --
  // nothing is scrolled out of view yet at this stage regardless.
  function zoomTo(clientX, clientY, factor) {
    var newScale = Math.max(1, Math.min(20, zoomScale * factor));
    if (newScale === zoomScale) return;
    var before = svg.getBoundingClientRect();
    var fx = (clientX - before.left) / before.width;
    var fy = (clientY - before.top) / before.height;
    zoomScale = newScale;
    applyZoomSize();
    var after = svg.getBoundingClientRect();
    window.scrollBy(
      (after.left + fx * after.width) - clientX,
      (after.top + fy * after.height) - clientY
    );
  }

  // Map an svg user-space point to pixels within the svg wrapper (honors the
  // current viewBox, so docked sliders track their axes during pan/zoom).
  function positionDocked() {
    if (!wrap || !dockedSliders.length) return;
    var wr = wrap.getBoundingClientRect();
    var ctm = svg.getScreenCTM();
    dockedSliders.forEach(function (ds) {
      var m = META[ds.axesKey];
      if (!m) return;
      var pt = svg.createSVGPoint();
      pt.x = m.x + m.w / 2; pt.y = m.y + m.h;
      var s = pt.matrixTransform(ctm);
      ds.box.style.left = Math.round(s.x - wr.left - ds.box.offsetWidth / 2) + 'px';
      ds.box.style.top = Math.round(s.y - wr.top + 30) + 'px';
    });
  }

  // IEEE 754 half-precision (float16) -> plain JS number. There's no native
  // Float16Array yet, so a mesh/series array narrow enough to fit in
  // float16 (see figure._fits_float16) decodes through this instead of a
  // free typed-array view.
  function halfToFloat(h) {
    var s = (h & 0x8000) ? -1 : 1, e = (h & 0x7C00) >> 10, f = h & 0x03FF;
    if (e === 0) return s * Math.pow(2, -14) * (f / 1024);
    if (e === 0x1F) return f ? NaN : s * Infinity;
    return s * Math.pow(2, e - 15) * (1 + f / 1024);
  }

  function b64ToBytes(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }

  // A long numeric array (a mesh z grid, an animated line's per-frame Y)
  // embeds as {"__f32__": "<base64>"} or {"__f16__": "<base64>"} rather than
  // JSON number text -- see figure._encode_binary_arrays for why, and which
  // width. Reverse it in place: a Float32Array indexes and iterates just
  // like the plain Array it replaces, so nothing downstream needs to know
  // which one it got.
  function reviveBinary(obj) {
    if (obj && typeof obj === 'object') {
      if (typeof obj.__f32__ === 'string') {
        return new Float32Array(b64ToBytes(obj.__f32__).buffer);
      }
      if (typeof obj.__f16__ === 'string') {
        var u16 = new Uint16Array(b64ToBytes(obj.__f16__).buffer);
        var out = new Float32Array(u16.length);
        for (var h = 0; h < u16.length; h++) out[h] = halfToFloat(u16[h]);
        return out;
      }
      if (Array.isArray(obj)) {
        for (var j = 0; j < obj.length; j++) obj[j] = reviveBinary(obj[j]);
      } else {
        for (var k in obj) obj[k] = reviveBinary(obj[k]);
      }
    }
    return obj;
  }

  // meta embeds column-wise (one array per field, one key list total) when
  // binary_pick_data=True -- see figure._columnarize_meta -- or the plain
  // {axesIndex: {field: value}} shape when it's False. Detect which (a
  // legitimate per-axes object never has literal "cols"/"index"/"keys"
  // properties, since axes indices are plain integers) and always return
  // the latter, so everything downstream keeps reading
  // META[axesIndex].field exactly as before either way.
  function expandColumnarMeta(payload) {
    if (!payload || !payload.cols || !payload.index || !payload.keys) return payload;
    var out = {};
    for (var i = 0; i < payload.index.length; i++) {
      var entry = {};
      for (var k = 0; k < payload.keys.length; k++) {
        var key = payload.keys[k];
        entry[key] = payload.cols[key][i];
      }
      out[payload.index[i]] = entry;
    }
    return out;
  }

  var metaEl = document.getElementById('plotpress-meta');
  var META = metaEl ? expandColumnarMeta(reviveBinary(JSON.parse(metaEl.textContent))) : {};
  var styleEl = document.getElementById('plotpress-style');
  var STYLE = styleEl ? JSON.parse(styleEl.textContent) : {};

  // CUR holds each axes' *current* limits (mutated by per-axes data zoom);
  // META stays the original. All data<->pixel math reads CUR; the artist zoom
  // group is remapped by an affine from META (original) to CUR (current).
  var CUR = {};
  Object.keys(META).forEach(function (k) {
    CUR[k] = {}; for (var f in META[k]) CUR[k][f] = META[k][f];
  });

  var mode = null;             // null => inert (no interaction) by default
  var down = null, moved = false, panV = null, rubber = null, panAxes = null;

  // ---- toolbar -----------------------------------------------------------
  // A docked menu bar (Axes / Point Picking / Annotate / File) -- docked in
  // the sense that it's a real, single row spanning the figure's own
  // width, not the sense that it takes up layout space of its own:
  // position:fixed, pinned to the viewport's top-left corner, exactly like
  // the flat toolbar this design replaces. That's deliberate, not an
  // oversight -- an in-flow bar (this design's first attempt) scrolls away
  // with the rest of the page the moment Pan/Zoom's whole-figure
  // Magnify makes the figure bigger than the window and the user pans or
  // scrolls to reach the rest of it, and position:sticky (the natural next
  // attempt, "in flow until you'd scroll past it, then pinned") turned out
  // not to reliably track a *dynamically* resized ancestor's bounds across
  // browsers either -- so plotpress/figure.py's _toolbar_clearance is back
  // to reserving real padding for it (standalone=False's body, and
  // Report.save's <iframe> height guess), the same job it always did.
  var style = document.createElement('style');
  style.textContent =
    // width:100% -- not a JS-computed pin to the figure's own width -- so
    // the bar always spans the entire window, independent of how wide any
    // one figure on the page happens to be (a position:fixed element's
    // percentage width resolves against the viewport itself, the initial
    // containing block, not against any narrower ancestor). The mode
    // indicator's own margin-left:auto (see .plotpress-mode-indicator
    // below) then rides the far right edge of that full-width bar.
    // overflow: default (visible) is deliberate, not an oversight -- a
    // dropdown (.plotpress-menu-dropdown below) is an absolutely
    // positioned descendant that pops open *below* this row's own box, and
    // setting overflow-x to anything but visible here (even leaving
    // overflow-y itself unset) computes overflow-y to auto too, silently
    // clipping every open dropdown out of view. white-space:nowrap on the
    // label/button rules below still keeps every label from wrapping onto
    // a second line even on a figure narrower than the bar's full content
    // needs; on a genuinely narrow window the rightmost items (the mode
    // indicator especially) can render past the visible edge with no way
    // to scroll to them, a real but much rarer tradeoff than dropdowns
    // that never show at all.
    '.plotpress-menubar{display:flex;align-items:center;gap:2px;' +
    'position:fixed;top:0;left:0;z-index:1500;width:100%;box-sizing:border-box;' +
    'padding:5px 8px;background:#fafbfc;' +
    'border-bottom:1px solid #d5d9e0;font:12px system-ui,sans-serif}' +
    '.plotpress-menu{position:relative}' +
    '.plotpress-menu-label{display:flex;align-items:center;gap:5px;' +
    'padding:5px 10px;border:1px solid transparent;background:transparent;' +
    'color:#222;border-radius:6px;cursor:pointer;white-space:nowrap;' +
    'font:600 12px system-ui,sans-serif}' +
    '.plotpress-menu-label:hover{background:#eef0f3}' +
    '.plotpress-menu.open .plotpress-menu-label{background:#e8eeff;' +
    'color:#2b5bd7}' +
    '.plotpress-chev{font-size:9px;opacity:.6}' +
    '.plotpress-menu-dropdown{position:absolute;top:calc(100% + 5px);' +
    'left:0;min-width:170px;background:#fff;border:1px solid #b8b8b8;' +
    'border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.16);padding:5px;' +
    'display:none;flex-direction:column;gap:1px;z-index:1000}' +
    '.plotpress-menu.open .plotpress-menu-dropdown{display:flex}' +
    // .plotpress-toolbar now names a dropdown's own item list -- kept as
    // the class every button-styling rule below keys off, and what
    // tests/test_pick_interactive.py's _click_mode() selects buttons by,
    // stable across the redesign on purpose.
    // No display: here on purpose -- a dropdown carries both
    // .plotpress-menu-dropdown (display:none by default, display:flex only
    // while .open, see above) and .plotpress-toolbar (kept as the stable
    // class tests/test_pick_interactive.py's _click_mode() selects buttons
    // by); giving this rule its own display:flex would tie its specificity
    // with .plotpress-menu-dropdown's, and being the later rule, silently
    // win, keeping every dropdown visible regardless of .open.
    '.plotpress-toolbar{flex-direction:column;gap:1px}' +
    '.plotpress-toolbar button{display:flex;align-items:center;gap:8px;' +
    'width:100%;text-align:left;padding:7px 9px;border:none;white-space:nowrap;' +
    'background:transparent;color:#222;border-radius:5px;cursor:pointer;' +
    'font:12px system-ui,sans-serif}' +
    '.plotpress-toolbar button:hover{background:#f1f1f1}' +
    '.plotpress-toolbar button.active{background:#2b8cff;color:#fff}' +
    '.plotpress-toolbar button.toggled{background:#e8eeff;color:#2b5bd7}' +
    // Pan/Zoom and Home sit directly on the bar, not behind a
    // menu -- the whole-figure tool reached for constantly, and the reset
    // that undoes it, close enough to be worth skipping a menu's extra
    // click every time (see the standaloneGroup comment below). Still
    // .plotpress-toolbar (the stable test-selector class, see above) so
    // button/.active/.toggled styling and every existing click-by-label
    // test helper keep working unchanged. Needs its own explicit
    // display:flex, unlike a real dropdown -- .plotpress-toolbar itself
    // carries none (see the comment on it above: a dropdown's display
    // toggles via .plotpress-menu-dropdown/.open instead), but this group
    // is never a .plotpress-menu-dropdown, so nothing else would ever give
    // it one; flex-direction/width also overridden back to a normal
    // horizontal bar group here, later in source than the column-flex
    // .plotpress-toolbar rule above so it actually wins (same tied-
    // specificity trap noted there).
    '.plotpress-standalone-group{display:flex;flex-direction:row;gap:2px}' +
    '.plotpress-standalone-group button{width:auto;font-weight:600}' +
    '.plotpress-menubar-divider{width:1px;align-self:stretch;' +
    'background:#d5d9e0;margin:0 4px}' +
    '.plotpress-menu-divider{height:1px;background:#e4e6ea;margin:4px 2px}' +
    '.plotpress-mode-indicator{display:flex;align-items:center;gap:6px;' +
    'margin-left:auto;padding:4px 10px 4px 8px;background:#eef2ff;' +
    'border-radius:999px;font:500 11px system-ui,sans-serif;color:#2b5bd7;' +
    'white-space:nowrap}' +
    '.plotpress-mode-dot{width:6px;height:6px;border-radius:50%;' +
    'background:#2b6cff;flex:none}' +
    '.plotpress-sliders{position:fixed;bottom:12px;left:50%;' +
    'transform:translateX(-50%);display:flex;flex-direction:column;' +
    'gap:6px;z-index:1000}' +
    '.plotpress-slider{display:flex;align-items:center;gap:12px;' +
    'background:#fff;padding:8px 16px;border:1px solid #b8b8b8;' +
    'border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.2);' +
    'font:12px system-ui,sans-serif}' +
    '.plotpress-slider input[type=range]{width:240px}' +
    '.plotpress-slider .val{min-width:90px;font-variant-numeric:tabular-nums}' +
    '.plotpress-slider button{padding:3px 8px;border:1px solid #b8b8b8;' +
    'background:#fff;border-radius:5px;cursor:pointer;font-size:13px;' +
    'line-height:1.1}' +
    '.plotpress-slider button:hover{background:#f1f1f1}' +
    '.plotpress-slider .link{display:flex;align-items:center;gap:4px;' +
    'font-size:11px;color:#555;cursor:pointer;user-select:none}' +
    '.plotpress-slider .idx{background:#e8eeff;border:1px solid #b9c6ef;' +
    'border-radius:4px;padding:0 5px;font-weight:600;color:#2b5bd7}' +
    '.plotpress-pin.selected circle{fill:#2b8cff}' +   /* r itself: selectPin(), scaled per-pin */
    '.plotpress-pin.plotpress-note rect{fill:#b45309}' +   /* user notes: amber */
    // Hide Points/Hide Annotations toggle independently -- one class per
    // kind, keyed the same way Clear Points/Clear Annotations and
    // isAnnotationPin() already split .plotpress-pin by .plotpress-note.
    '.plotpress-hide-points .plotpress-pin:not(.plotpress-note){display:none}' +
    '.plotpress-hide-annotations .plotpress-pin.plotpress-note{display:none}' +
    // "move" only on the box itself (not the dot, which stays a plain
    // click target -- see contextmenu/click above) and only while the
    // mode that would let a drag actually happen is active -- see
    // boxDraggableNow/refreshDragReady.
    '.plotpress-pin.plotpress-drag-ready rect,' +
    '.plotpress-pin.plotpress-drag-ready text{cursor:move}' +
    // A boxed ax.text()/ax.annotate() call -- see svg._render_text's
    // plotpress-textbox group -- is a *static* callout the figure itself
    // drew, not an interactive pin, but it reads the same way on screen and
    // is closer in spirit to a user-written note than a picked data point,
    // so Hide Annotations takes it too.
    '.plotpress-hide-annotations .plotpress-textbox{display:none}' +
    '.plotpress-zoom line,.plotpress-zoom path{vector-effect:non-scaling-stroke}' +
    // Markers are the one exception: a marker's size represents a footprint
    // on the data (scatter's `s=`, plot's `markersize=`), so a per-axes
    // rubber-band zoom should grow/shrink it right along with the axis --
    // unlike a line's stroke width, which stays a constant screen size on
    // purpose. Without this, a marker sized for the full view stays exactly
    // that many screen pixels after zooming into a small region and can
    // swallow the entire (now much smaller) visible axis. Higher-specificity
    // selector wins over the rule above regardless of source order.
    '.plotpress-zoom .plotpress-marker path{vector-effect:none}' +
    // Standalone's body centers the figure with flex, which clips (rather
    // than making scrollable) any child that grows past it -- a zoomed-in
    // SVG would be reachable on only one side, never both. Switching to
    // block + overflow:auto for as long as the figure is actually zoomed
    // (see applyZoomSize) restores real, both-directions scrolling; the
    // default centered layout returns the moment zoomScale is back to 1.
    'body.plotpress-zoomed{display:block;overflow:auto}' +
    '.plotpress-extract{position:fixed;top:44px;right:10px;width:360px;' +
    'max-height:72vh;overflow:auto;background:#fff;border:1px solid #b8b8b8;' +
    'border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);padding:10px;' +
    'z-index:2000;font:12px system-ui,sans-serif}' +
    '.plotpress-extract textarea{width:100%;height:180px;box-sizing:border-box;' +
    'font:11px ui-monospace,monospace;resize:vertical}' +
    '.plotpress-extract button{padding:4px 8px;border:1px solid #b8b8b8;' +
    'background:#fff;border-radius:5px;cursor:pointer}';
  document.head.appendChild(style);

  var menubar = document.createElement('div');
  menubar.className = 'plotpress-menubar';
  var menuNodes = [];
  function closeAllMenus() {
    menuNodes.forEach(function (m) { m.classList.remove('open'); });
  }
  function buildMenu(label) {
    var menu = document.createElement('div');
    menu.className = 'plotpress-menu';
    var labelBtn = document.createElement('button');
    labelBtn.className = 'plotpress-menu-label';
    labelBtn.appendChild(document.createTextNode(label + ' '));
    var chev = document.createElement('span');
    chev.className = 'plotpress-chev';
    chev.textContent = '▾';
    labelBtn.appendChild(chev);
    labelBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var willOpen = !menu.classList.contains('open');
      closeAllMenus();
      if (willOpen) menu.classList.add('open');
    });
    var dropdown = document.createElement('div');
    dropdown.className = 'plotpress-toolbar plotpress-menu-dropdown';
    menu.appendChild(labelBtn);
    menu.appendChild(dropdown);
    menubar.appendChild(menu);
    menuNodes.push(menu);
    return dropdown;
  }
  // Closing on any click outside every menu -- not just the menubar --
  // covers interacting with the SVG itself (picking a point, panning) the
  // same way a real desktop app's menu would: doing something with an open
  // dropdown still showing dismisses it. Escape closes one too (see the
  // keydown handler far below) -- but only that, when one is open: Escape
  // otherwise means "clear every pin/annotation" (clearAllPins), and a menu
  // being open must not silently reroute a plain "close this menu" press
  // into wiping every pin instead.
  document.addEventListener('click', function () { closeAllMenus(); });

  // Pan/Zoom and Home sit standalone at the far left (see
  // standaloneGroup below), not behind their own "Figure" menu -- an
  // earlier version of this design tucked them (and Hide All) into one,
  // but a menu just to hold the one tool reached for most, plus the reset
  // that undoes it, cost a click every single time for no real grouping
  // benefit; Hide All itself later split into the per-kind Hide
  // Points/Hide Annotations that now live in the Point Picking/Annotate
  // menus below, alongside Clear Points/Clear Annotations. Four menus for
  // everything else, split by scope: whole-figure-vs-per-axes vs. Point
  // Picking pulled onto its own, since it's the next most-reached-for
  // tool. `row` from the old two-row layout becomes `menu` below; the
  // reasoning for each button's own position otherwise carries over
  // unchanged from the two-row design this replaces -- Axis Span/Zoom lead
  // Axes, Reset All Axes after them -- the pair it undoes. Point Picking,
  // Hide Points, Clear Points, and Extract share a menu now: Extract only
  // ever returns Point Picking markers (see doExtract() below), so it
  // moved out of a standalone spot in the old Annotation row to sit with
  // the tool it actually reads from -- Annotate has no export of its own.
  // Save/Save As get their own File menu instead of trailing Figure the
  // way they trailed Navigation before -- persisting pan/zoom/pins/toggles
  // is squarely "do something with the view", the reasoning that kept them
  // off a row of their own previously, but a third or fourth *menu* costs
  // nothing a third *row* wouldn't have.
  var TOOLS = [
    { mode: 'magnify', label: 'Pan/Zoom', standalone: true },
    { action: 'reset-figure', label: 'Home', standalone: true },
    { mode: 'span', label: 'Axis Span', menu: 'Axes' },
    { mode: 'zoom', label: 'Axis Zoom', menu: 'Axes' },
    { action: 'reset-axes', label: 'Reset All Axes', menu: 'Axes', divider: true },
    { mode: 'pick', label: 'Point Picking', menu: 'Point Picking' },
    { action: 'toggle-points', label: 'Hide Points', menu: 'Point Picking', divider: true },
    { action: 'clear-points', label: 'Clear Points', menu: 'Point Picking', divider: true },
    { action: 'extract', label: 'Extract', menu: 'Point Picking', divider: true },
    { mode: 'note-free', label: 'Annotation', menu: 'Annotate' },
    { action: 'toggle-annotations', label: 'Hide Annotations', menu: 'Annotate', divider: true },
    { action: 'clear-annotations', label: 'Clear Annotations', menu: 'Annotate', divider: true },
    { action: 'save', label: 'Save', menu: 'File' },
    { action: 'save-as', label: 'Save As', menu: 'File' },
  ];
  var pointsHidden = false;
  var annotationsHidden = false;
  // Hide Points/Hide Annotations toggle independently -- one class per kind
  // (see the .plotpress-hide-points/.plotpress-hide-annotations CSS rules
  // above), the same split Clear Points/Clear Annotations already use.
  // Hide Annotations additionally takes every figure-drawn boxed callout --
  // not scoped to "annotations" specifically despite the CSS class name,
  // see the CSS comment above for why it landed here rather than under
  // Hide Points.
  function togglePointsHidden(b) {
    pointsHidden = !pointsHidden;
    svg.classList.toggle('plotpress-hide-points', pointsHidden);
    b.textContent = pointsHidden ? 'Show Points' : 'Hide Points';
    b.classList.toggle('toggled', pointsHidden);
  }
  function toggleAnnotationsHidden(b) {
    annotationsHidden = !annotationsHidden;
    svg.classList.toggle('plotpress-hide-annotations', annotationsHidden);
    b.textContent = annotationsHidden ? 'Show Annotations' : 'Hide Annotations';
    b.classList.toggle('toggled', annotationsHidden);
  }
  // Pan/Zoom and Home sit directly on the bar, at the far
  // left, rather than behind their own "Figure" menu -- reached for often
  // enough (Pan/Zoom especially) that the extra click to open a
  // menu first isn't worth paying every time, unlike everything else,
  // which stays menu-grouped. Still .plotpress-toolbar (see the CSS
  // comment above) so every button/.active/.toggled style and the existing
  // click-by-label test helpers keep finding them the same way.
  var standaloneGroup = document.createElement('div');
  standaloneGroup.className = 'plotpress-toolbar plotpress-standalone-group';
  menubar.appendChild(standaloneGroup);
  var standaloneDivider = document.createElement('div');
  standaloneDivider.className = 'plotpress-menubar-divider';
  menubar.appendChild(standaloneDivider);

  var DROPDOWN_FOR_MENU = {};
  ['Axes', 'Point Picking', 'Annotate', 'File'].forEach(function (name) {
    DROPDOWN_FOR_MENU[name] = buildMenu(name);
  });

  // A mode item is checkable, not a one-shot action: a single click selects
  // it without closing its own menu, so picking a different tool from the
  // same menu -- or double-clicking this one to clear it -- doesn't need
  // reopening it first. A single click can't double as "click the active
  // one again to turn it off" the way the old flat toolbar row's buttons
  // could: in a menu, one click already means "choose this", so reusing it
  // for "and now un-choose it" would be ambiguous. Double-click is
  // unambiguous instead -- but naively wiring that as its own 'dblclick'
  // listener (fired strictly after both 'click' events, per the DOM spec)
  // deselects unconditionally: double-clicking a tool that was *not* yet
  // active would still select-then-immediately-deselect it, since by the
  // time 'dblclick' runs, this tool's own first click has already made it
  // the active one. `e.detail` (the browser's own same-target click count)
  // sidesteps that: captured only on a sequence's first click, so a second
  // click can tell "was this already active before *this* gesture" apart
  // from "just became active because of this gesture's own first click".
  // `alwaysClose` is for the standalone group above -- it has no dropdown
  // of its own to keep open, so selecting one of its tools should still
  // close whatever *other* menu happens to be open, the same as any
  // one-shot action does.
  function attachModeButton(b, m, alwaysClose) {
    var startedActive = false;
    b.addEventListener('click', function (e) {
      e.stopPropagation();   // else the document-level listener (below)
                             // sees the same click bubble up and closes
                             // this menu right back -- a mode selection is
                             // meant to stay open.
      if (e.detail < 2) startedActive = (mode === m);
      if (e.detail >= 2 && startedActive) { setMode(null); closeAllMenus(); return; }
      setMode(m);
      if (alwaysClose) closeAllMenus();
    });
    // Swallow the native dblclick too -- otherwise a fast double-click
    // falls through to the browser's own default double-click text
    // selection on whatever's nearby.
    b.addEventListener('dblclick', function (e) { e.preventDefault(); });
  }
  var buttons = TOOLS.map(function (t) {
    var container = t.standalone ? standaloneGroup : DROPDOWN_FOR_MENU[t.menu];
    if (t.divider) {
      var div = document.createElement('div');
      div.className = 'plotpress-menu-divider';
      container.appendChild(div);
    }
    var b = document.createElement('button');
    b.textContent = t.label;
    if (t.mode) {
      b.dataset.mode = t.mode;
      attachModeButton(b, t.mode, t.standalone);
    } else {
      b.addEventListener('click', function (e) {
        e.stopPropagation();   // else the document-level listener (below)
                               // sees the same click bubble up and closes
                               // this menu right back.
        if (t.action === 'extract') doExtract();
        else if (t.action === 'toggle-points') togglePointsHidden(b);
        else if (t.action === 'toggle-annotations') toggleAnnotationsHidden(b);
        else if (t.action === 'save') overwriteCurrentPage();
        else if (t.action === 'save-as') saveAsNewPage();
        else if (t.action === 'reset-figure') { zoomScale = 1; applyZoomSize(); }
        else if (t.action === 'reset-axes') resetAxes();
        else if (t.action === 'clear-points') clearPointPins();
        else if (t.action === 'clear-annotations') clearAnnotationPins();
        closeAllMenus();
      });
    }
    container.appendChild(b);
    return b;
  });

  // Public extension point for a caller's own extra_js= (see Figure.to_html):
  // add a tool to its own menu, created lazily on first call -- a page with
  // no custom tools gets no empty extra menu to explain. Two shapes,
  // mirroring TOOLS above -- {label, onClick}: an always-available action,
  // firing immediately on click, like Extract/Save. {label, mode, onClick,
  // onEnter, onExit, cursor}: a real *mode*, joining the same
  // single-selection group as Pan/Zoom, Axis Span/Zoom, Point
  // Picking, or Annotation -- picking it deselects whatever else was active,
  // and vice versa (see setMode below, and the `buttons` array/dataset.mode
  // CSS-'active' sync inside it, both of which already work for any button
  // in `buttons` generically, custom or not). Selected, a click on the SVG
  // that no built-in mode already claims (`note-free`/`pick` -- see the
  // top-level click listener's own custom-mode fallback) calls
  // onClick(event, toUser(event)) -- the same svg-event-to-user-space-point
  // helper Span/Zoom/pick already build on, so a custom tool gets a real
  // data-space point for free rather than raw client pixels. onEnter/onExit
  // fire when the mode is selected/deselected (setMode's own prevMode
  // bookkeeping below), and `cursor` sets svg.style.cursor while it's
  // active, the same as a built-in mode's own fixed cursor choice does.
  // One side effect a custom mode inherits with no opt-out: selecting it
  // also disables text selection on the figure (setMode's own
  // svg.style.userSelect line), the same as every built-in mode -- a
  // custom tool whose own interaction depends on letting the user select
  // text will need to restore it manually from its own onEnter/onExit.
  var CUSTOM_MODES = {};
  var customDropdown = null;   // created on first addTool() call, not up front
  function addTool(opts) {
    var b = document.createElement('button');
    b.textContent = opts.label;
    if (opts.mode) {
      b.dataset.mode = opts.mode;
      CUSTOM_MODES[opts.mode] = opts;
      attachModeButton(b, opts.mode);
    } else {
      b.addEventListener('click', function (ev) {
        ev.stopPropagation();
        if (opts.onClick) opts.onClick(ev);
        closeAllMenus();
      });
    }
    if (!customDropdown) {
      customDropdown = buildMenu('Custom');
      // buildMenu() appends to menubar's end, which -- since the mode
      // indicator is already there by the time any addTool() call can run
      // -- would otherwise land the Custom menu after it instead of
      // alongside the five built-in ones.
      menubar.insertBefore(customDropdown.parentElement, modeIndicator);
    }
    customDropdown.appendChild(b);
    buttons.push(b);
    return b;
  }
  window.plotpressAddTool = addTool;

  var modeIndicator = document.createElement('span');
  modeIndicator.className = 'plotpress-mode-indicator';
  var modeDot = document.createElement('span');
  modeDot.className = 'plotpress-mode-dot';
  var modeText = document.createElement('span');
  modeIndicator.appendChild(modeDot);
  modeIndicator.appendChild(modeText);
  menubar.appendChild(modeIndicator);

  function modeLabel(m) {
    if (!m) return 'No tool active';
    for (var i = 0; i < TOOLS.length; i++) {
      if (TOOLS[i].mode === m) return TOOLS[i].label;
    }
    return (CUSTOM_MODES[m] && CUSTOM_MODES[m].label) || m;
  }

  // Inserted as the very first thing in the body, same corner the old flat
  // toolbar row always occupied -- harmless regardless of exactly where it
  // sits in the DOM, since position:fixed ignores document flow/layout
  // entirely and z-index (see the CSS above) settles any stacking order
  // question on its own; first-child just keeps a reader's tab order
  // matching what's visually first. Its width:100% (see the CSS above)
  // needs no JS help spanning the window -- unlike the figure it sits
  // above, which really is only ever as wide as naturalW/zoomScale say.
  document.body.insertBefore(menubar, document.body.firstChild);

  function setMode(m) {
    // Cancel anything in progress and clear transient state.
    down = null; removeRubber();
    var prevMode = mode;
    // Home and Reset All Axes are one-shot actions dispatched directly by
    // their own button handler (see `buttons` above), not modes -- this
    // only ever sees a real mode name now. Always sets the target mode
    // directly, never toggles: a click on a menu item always selects it
    // (see the buttons.map click handler above); double-click is the only
    // way to deselect (see attachDeselect above), called with m=null.
    mode = m;
    // A custom tool's own onEnter/onExit (see addTool/plotpressAddTool) --
    // fired after the mode itself has already changed, so either callback
    // can safely read the new `mode`/call setMode() again without racing
    // its own transition.
    if (prevMode && CUSTOM_MODES[prevMode] && CUSTOM_MODES[prevMode].onExit) {
      CUSTOM_MODES[prevMode].onExit();
    }
    if (mode && CUSTOM_MODES[mode] && CUSTOM_MODES[mode].onEnter) {
      CUSTOM_MODES[mode].onEnter();
    }
    buttons.forEach(function (b) {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    modeText.textContent = modeLabel(mode);
    var custom = mode && CUSTOM_MODES[mode];
    svg.style.cursor =
      mode === 'span' ? 'grab' :
      mode === 'zoom' ? 'crosshair' :
      mode === 'magnify' ? 'zoom-in' :
      mode === 'note-free' ? 'text' :
      (custom && custom.cursor) ? custom.cursor : 'default';
    // Any active mode's own drag can sweep across text the same way
    // Magnify's whole-figure pan always could -- Span/Zoom drag across tick
    // labels and titles, Point Picking/Annotation drag a pin's own text box
    // across other pins' labels -- so disabling selection is scoped to
    // "some tool is selected" generally, not just Magnify specifically.
    // Inert (no mode) leaves normal text selection alone.
    svg.style.userSelect = mode ? 'none' : '';
    refreshDragReady();
  }
  setMode(null);  // start inert with an arrow cursor

  // ---- helpers -----------------------------------------------------------
  function toUser(e) {
    var pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }
  function pxPerUser() {
    return svg.getBoundingClientRect().width / view[2];
  }

  // ---- rubber-band box (zoom mode) --------------------------------------
  function startRubber(e) {
    var p = toUser(e);
    var el = document.createElementNS(SVGNS, 'rect');
    el.setAttribute('class', 'plotpress-rubber');
    el.setAttribute('fill', '#2b8cff'); el.setAttribute('fill-opacity', 0.15);
    el.setAttribute('stroke', '#2b8cff');
    el.setAttribute('stroke-width', 1 / pxPerUser());
    svg.appendChild(el);
    rubber = { x0: p.x, y0: p.y, el: el };
  }
  function updateRubber(e) {
    var p = toUser(e), el = rubber.el;
    el.setAttribute('x', Math.min(rubber.x0, p.x));
    el.setAttribute('y', Math.min(rubber.y0, p.y));
    el.setAttribute('width', Math.abs(p.x - rubber.x0));
    el.setAttribute('height', Math.abs(p.y - rubber.y0));
  }
  function finishRubber(e) {
    var p = toUser(e);
    var x0 = Math.min(rubber.x0, p.x), y0 = Math.min(rubber.y0, p.y);
    var x1 = Math.max(rubber.x0, p.x), y1 = Math.max(rubber.y0, p.y);
    removeRubber();
    if (x1 - x0 < 4 || y1 - y0 < 4) return;
    var a = axesAt({ x: (x0 + x1) / 2, y: (y0 + y1) / 2 });
    if (!a) return;                          // box-zoom the axes under the box
    var c = CUR[a.i], d0 = toData(c, x0, y0), d1 = toData(c, x1, y1);
    c.xmin = Math.min(d0.x, d1.x); c.xmax = Math.max(d0.x, d1.x);
    c.ymin = Math.min(d0.y, d1.y); c.ymax = Math.max(d0.y, d1.y);
    refreshAxes(a.i);
  }
  function removeRubber() {
    if (rubber && rubber.el && rubber.el.parentNode) {
      rubber.el.parentNode.removeChild(rubber.el);
    }
    rubber = null;
  }

  // ---- pan / zoom drivers ------------------------------------------------
  svg.addEventListener('wheel', function (e) {
    // Under Zoom, only Ctrl+wheel (or a trackpad pinch, which the browser
    // reports as a wheel event with ctrlKey already set) zooms -- a plain
    // scroll must fall through to the page's own scrolling untouched, the
    // same as it would over any other content, rather than this figure
    // hijacking it just because Zoom happens to be the active tool. Magnify
    // is the explicit opt-in past that: selecting it says a plain wheel
    // here should zoom, Ctrl or not -- for wherever holding Ctrl is awkward
    // or already claimed by the browser/OS.
    var zooming = mode === 'magnify' || (mode === 'zoom' && e.ctrlKey);
    if (!zooming) return;
    e.preventDefault();
    zoomTo(e.clientX, e.clientY, e.deltaY < 0 ? 1.25 : 0.8);
  }, { passive: false });

  // Whole-figure pan: scrolls the page, exactly what the wheel now does
  // under Magnify (or Ctrl+wheel under Zoom) by growing the SVG's own
  // rendered size -- never an individual axes' own data range/ticks.
  // Shared by Span's "over the margins" drag and Magnify's drag, so a
  // zoomed-in view stays reachable in every direction without leaving the
  // tool that zoomed it.
  function panWholeFigureTo(e) {
    window.scrollTo(panV.x - (e.clientX - down.x), panV.y - (e.clientY - down.y));
  }

  svg.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;   // ignore right/middle button (right = delete pin)
    if (!mode || e.target.closest('.plotpress-pin')) return;
    down = { x: e.clientX, y: e.clientY }; moved = false;
    if (mode === 'span') {
      var pdn = toUser(e), a = axesAt(pdn);
      if (a) {
        // per-axes data pan over a plot (directed edges: honors inverted axes)
        panAxes = { key: a.i, downUser: pdn, start: edges(CUR[a.i]) };
      } else {
        panV = { x: window.scrollX, y: window.scrollY };   // over margins: whole-figure pan
      }
      svg.style.cursor = 'grabbing';
    } else if (mode === 'zoom') { startRubber(e); }
    else if (mode === 'magnify') {
      // Always the whole-figure view, regardless of what's under the
      // cursor -- Magnify never touches axes data, only what part of the
      // rendered figure is currently visible (see the wheel handler above).
      panV = { x: window.scrollX, y: window.scrollY };
      svg.style.cursor = 'grabbing';
    }
  });
  window.addEventListener('mousemove', function (e) {
    if (!down) return;
    if (Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y) > 3) moved = true;
    if (mode === 'span' && panAxes) {
      var m = CUR[panAxes.key], s = panAxes.start, pc = toUser(e);
      var dfx = (pc.x - panAxes.downUser.x) / m.w * (s.fx1 - s.fx0);
      var dfy = (pc.y - panAxes.downUser.y) / m.h * (s.fy1 - s.fy0);
      setXLim(m, s.fx0 - dfx, s.fx1 - dfx);
      setYLim(m, s.fy0 + dfy, s.fy1 + dfy);
      refreshAxes(panAxes.key);
    } else if (mode === 'span' || mode === 'magnify') {
      panWholeFigureTo(e);
    } else if (mode === 'zoom' && rubber) {
      updateRubber(e);
    }
  });
  window.addEventListener('mouseup', function (e) {
    if (!down) return;
    if (mode === 'span') svg.style.cursor = 'grab';
    else if (mode === 'magnify') svg.style.cursor = 'zoom-in';
    else if (mode === 'zoom' && rubber) finishRubber(e);
    down = null; panAxes = null;
  });

  // Double-click a plot (while panning/zooming) resets just that plot's view.
  // Under Magnify, there is no per-axes view to reset -- only the whole
  // figure's, exactly what its wheel zoom and drag pan both operate on (see
  // above), so double-click resets that instead of doing nothing.
  svg.addEventListener('dblclick', function (e) {
    if (mode === 'magnify') {
      e.preventDefault();
      zoomScale = 1; applyZoomSize();
      return;
    }
    if (mode !== 'span' && mode !== 'zoom') return;
    e.preventDefault();
    var a = axesAt(toUser(e));
    if (a) resetAxesOne(a.i);
  });

  // ---- legend toggle (always available) ---------------------------------
  document.querySelectorAll('.plotpress-legend text').forEach(function (t) {
    var label = t.textContent;
    t.style.cursor = 'pointer';
    t.addEventListener('click', function (e) {
      e.stopPropagation();
      document.querySelectorAll('.plotpress-series').forEach(function (s) {
        if (s.getAttribute('data-label') === label) {
          var hidden = s.style.display === 'none';
          s.style.display = hidden ? '' : 'none';
          t.style.opacity = hidden ? '1' : '0.4';
        }
      });
    });
  });

  // ---- point picking (pick mode) ----------------------------------------
  var pickEl = document.getElementById('plotpress-pick');
  var PICK = pickEl ? reviveBinary(JSON.parse(pickEl.textContent)) : {};
  var POINT_THRESHOLD = 28;  // px: snap to an embedded point within this radius

  // PICK is a closure over this IIFE -- unreachable from outside, which is
  // exactly right for the embedded payload itself, but a live-updating
  // caller (plotpress.qt.LiveArtist) that patches the SVG in place via
  // page().runJavaScript() has no other way to keep picking in sync with
  // what's now on screen. axesIndex/entryJson mirror pick_data()'s own
  // per-axes shape ({"series":[...],"meshes":[...],"pies":[...]}), so this
  // is a straight swap, not a merge.
  window.plotpressUpdatePick = function (axesIndex, entryJson) {
    PICK[axesIndex] = JSON.parse(entryJson);
  };

  // Highest index (most recently added) first, so an axes nested inside a
  // larger one -- an inset, or a twin/secondary overlaid on its parent --
  // wins the hit test. Ascending order always resolved to whichever axes was
  // created first, which for an inset meant its *parent*, making the inset
  // itself permanently unreachable by click, wheel, or drag.
  function axesAt(p) {
    var keys = Object.keys(CUR).map(Number).sort(function (a, b) { return b - a; });
    for (var idx = 0; idx < keys.length; idx++) {
      var k = String(keys[idx]), m = CUR[k];
      if (p.x >= m.x && p.x <= m.x + m.w && p.y >= m.y && p.y <= m.y + m.h) {
        return { i: k, m: m };
      }
    }
    return null;
  }
  // Point Picking only -- an axes with pickable=false (see
  // Axes.set_pickable) is treated as if the click missed every axes, so a
  // figure can restrict that tool to a single panel by disabling the rest.
  // Axis Span, Axis Zoom, Pan/Zoom, and Annotation go through
  // axesAt() directly and ignore this flag.
  function pickableAxesAt(p) {
    var a = axesAt(p);
    return (a && a.m.pickable === false) ? null : a;
  }
  function fwd(v, s) { return s === 'log' ? Math.log10(v) : v; }
  function inv(u, s) { return s === 'log' ? Math.pow(10, u) : u; }

  // An axes' limits in transformed (log-aware) space, *directed*: on an
  // inverted axis they come back swapped, exactly as _render_axes swaps the
  // limits it hands LinearTransform. Everything that maps between data and
  // pixels goes through this, so inverted axes behave like normal ones.
  function edges(m) {
    var fx0 = fwd(m.xmin, m.xscale), fx1 = fwd(m.xmax, m.xscale);
    var fy0 = fwd(m.ymin, m.yscale), fy1 = fwd(m.ymax, m.yscale);
    if (m.xinv) { var tx = fx0; fx0 = fx1; fx1 = tx; }
    if (m.yinv) { var ty = fy0; fy0 = fy1; fy1 = ty; }
    return { fx0: fx0, fx1: fx1, fy0: fy0, fy1: fy1 };
  }
  // Directed transformed edges -> data limits (min/max, since inv is monotonic).
  function setXLim(m, a, b) {
    m.xmin = inv(Math.min(a, b), m.xscale); m.xmax = inv(Math.max(a, b), m.xscale);
  }
  function setYLim(m, a, b) {
    m.ymin = inv(Math.min(a, b), m.yscale); m.ymax = inv(Math.max(a, b), m.yscale);
  }
  function toPixel(m, dx, dy) {
    var e = edges(m);
    return { x: m.x + (fwd(dx, m.xscale) - e.fx0) / (e.fx1 - e.fx0) * m.w,
             y: m.y + (e.fy1 - fwd(dy, m.yscale)) / (e.fy1 - e.fy0) * m.h };
  }
  function toData(m, px, py) {
    var e = edges(m);
    return { x: inv(e.fx0 + (px - m.x) / m.w * (e.fx1 - e.fx0), m.xscale),
             y: inv(e.fy1 - (py - m.y) / m.h * (e.fy1 - e.fy0), m.yscale) };
  }

  // ---- per-axes data zoom (client-side re-render) -----------------------
  function jsNiceTicks(lo, hi, n) {
    if (lo === hi) { lo -= 0.5; hi += 0.5; }
    var raw = (hi - lo) / (n || 5);
    var mag = Math.pow(10, Math.floor(Math.log10(raw))), norm = raw / mag, step;
    if (norm < 1.5) step = mag; else if (norm < 3) step = 2 * mag;
    else if (norm < 7) step = 5 * mag; else step = 10 * mag;
    var out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(v);
    return { ticks: out, step: step };
  }
  // Match the Python renderer's exponential style: "1e5", "1.2e-4".
  function expFmt(v, digits) {
    var p = v.toExponential(digits).split('e');
    return p[0].replace(/\.?0+$/, '') + 'e' + parseInt(p[1], 10);
  }
  function fmtTick(v, step) {
    if (Math.abs(v) < step * 1e-6) return '0';
    var a = Math.abs(v);
    if (a >= 1e5 || a < 1e-3) return expFmt(v, 1);
    var dec = step >= 1 ? 0 : Math.min(6, Math.ceil(-Math.log10(step)));
    var out = v.toFixed(dec);
    return out.indexOf('.') >= 0 ? out.replace(/0+$/, '').replace(/\.$/, '') : out;
  }
  function fmtNum(v) {
    var a = Math.abs(v);
    if (a !== 0 && (a < 1e-3 || a >= 1e5)) return expFmt(v, 0);
    return (Math.round(v * 1e6) / 1e6).toString();
  }
  // Mirrors ticker.log_ticks: decades *inside* [lo, hi] only -- a tick outside
  // the limits lands outside the axes box and is not clipped -- falling back to
  // 1-2-5 and then linear ticks for ranges narrower than a decade (which a
  // zoom reaches almost immediately).
  function jsLogTicks(lo, hi) {
    if (lo <= 0) lo = hi > 0 ? hi / 1000 : 1e-3;
    var e0 = Math.floor(Math.log10(lo)), e1 = Math.ceil(Math.log10(hi)), e, i;
    function inside(vals) {
      var keep = [];
      for (var k = 0; k < vals.length; k++)
        if (vals[k] >= lo * (1 - 1e-9) && vals[k] <= hi * (1 + 1e-9)) keep.push(vals[k]);
      return keep;
    }
    var decades = [];
    for (e = e0; e <= e1; e++) decades.push(Math.pow(10, e));
    var out = inside(decades);
    if (out.length >= 3) return out;
    var fine = [], mant = [1, 2, 5];
    for (e = e0; e <= e1; e++)
      for (i = 0; i < 3; i++) fine.push(mant[i] * Math.pow(10, e));
    fine.sort(function (a, b) { return a - b; });
    out = inside(fine);
    return out.length >= 2 ? out : jsNiceTicks(lo, hi, 5).ticks;
  }
  function allDistinct(a) {
    for (var i = 0; i < a.length; i++)
      for (var j = i + 1; j < a.length; j++) if (a[i] === a[j]) return false;
    return true;
  }
  // Format v against a shared exponent: "1.002e5". Mirrors ticker._sci_tick.
  function sciShared(v, exp, dec) {
    var mant = (v / Math.pow(10, exp)).toFixed(dec);
    if (mant.indexOf('.') >= 0) mant = mant.replace(/0+$/, '').replace(/\.$/, '');
    return mant + 'e' + exp;
  }
  // Mirrors ticker.format_ticks. Per-value formatting rounds to one mantissa
  // digit, so zooming into a narrow band at high magnitude labels every tick
  // "1e5". When that collides, share one exponent across the set and carry
  // enough mantissa digits to resolve the step.
  function fmtTickSet(ticks, step) {
    var labels = ticks.map(function (v) { return fmtTick(v, step); });
    if (allDistinct(labels)) return labels;
    var peak = 0;
    for (var i = 0; i < ticks.length; i++) peak = Math.max(peak, Math.abs(ticks[i]));
    if (!step || !peak || !isFinite(peak)) return labels;
    var exp = Math.floor(Math.log10(peak));
    var dec = Math.max(0, Math.min(12, Math.ceil(exp - Math.log10(step) - 1e-9)));
    var shared = ticks.map(function (v) { return sciShared(v, exp, dec); });
    return allDistinct(shared) ? shared : labels;
  }
  // Ticks + their rendered labels for one axis, respecting its scale.
  function axisTicks(lo, hi, scale) {
    if (scale === 'log') {
      var lt = jsLogTicks(lo, hi);
      return { ticks: lt, labels: lt.map(function (v) { return fmtNum(v); }), step: null };
    }
    var r = jsNiceTicks(lo, hi, 5);
    return { ticks: r.ticks, labels: fmtTickSet(r.ticks, r.step), step: r.step };
  }

  // Mirrors ticker.minor_ticks: unlabeled subdivisions within [lo, hi]. Log
  // is the 2..9 sub-decade marks per decade the range spans; linear
  // subdivides the major step by a count keyed off its leading digit
  // (1->5, 2->4, 5->5, matching nice_ticks' own 1-2-5 convention) and walks
  // outward from the first major tick, so minor ticks land on round
  // subdivisions of the major grid rather than an independent one that may
  // not line up with it.
  function jsMinorTicks(majorTicks, step, lo, hi, scale) {
    if (scale === 'log') {
      if (lo <= 0) lo = hi > 0 ? hi / 1000 : 1e-3;
      var e0 = Math.floor(Math.log10(lo)), e1 = Math.ceil(Math.log10(hi)), out = [];
      for (var e = e0; e <= e1; e++)
        for (var d = 2; d <= 9; d++) {
          var v = d * Math.pow(10, e);
          if (v >= lo && v <= hi) out.push(v);
        }
      return out;
    }
    if (majorTicks.length < 2 || !step) return [];
    var mag = Math.pow(10, Math.floor(Math.log10(Math.abs(step))));
    var lead = Math.round(Math.abs(step) / mag);
    var n = lead === 2 ? 4 : 5;   // 1->5, 2->4, 5->5 (and any other lead->5)
    var substep = step / n;
    var ticks = [];
    var k0 = Math.floor((lo - majorTicks[0]) / substep) - 1;
    var k1 = Math.ceil((hi - majorTicks[0]) / substep) + 1;
    for (var k = k0; k <= k1; k++) {
      var v2 = majorTicks[0] + k * substep;
      if (v2 < lo - substep * 1e-6 || v2 > hi + substep * 1e-6) continue;
      var onMajor = false;
      for (var m = 0; m < majorTicks.length; m++) {
        if (Math.abs(majorTicks[m] - v2) < Math.abs(substep) * 1e-6) { onMajor = true; break; }
      }
      if (!onMajor) ticks.push(v2);
    }
    return ticks;
  }

  // Effective tick style for one axis: `ov` (a raw tick_params() override, or
  // null/undefined) layered onto `base` field-by-field -- mirrors Python's
  // `Style.copy(**overrides)`. `base` is the figure-wide STYLE for a major
  // axis, or the already-resolved major style for that axis' minor ticks
  // (Axes.tick_params(which='minor') itself layers onto the major override,
  // not the figure default -- see svg._render_axes).
  function effTickStyle(base, ov) {
    if (!ov) return base;
    return {
      ts: ov.tick_size !== undefined ? ov.tick_size : base.ts,
      tw: ov.tick_width !== undefined ? ov.tick_width : base.tw,
      fs: ov.tick_label_size !== undefined ? ov.tick_label_size : base.fs,
      col: ov.spine_color !== undefined ? ov.spine_color : base.col,
      text: ov.text_color !== undefined ? ov.text_color : base.text,
    };
  }

  // Rebuild an axes' grid + ticks + numeric labels from its current limits.
  function rebuildTicks(key) {
    var om = META[key];
    if (!om || om.axis_off || om.xfixed || om.yfixed) return;  // leave as rendered
    var g = document.getElementById('ticks' + key);
    if (!g) return;
    var m = CUR[key];
    var xr = axisTicks(m.xmin, m.xmax, m.xscale);
    var yr = axisTicks(m.ymin, m.ymax, m.yscale);
    var parts = [];
    var xTop = om.xside === 'top', yRight = om.yside === 'right';
    var xAxis = xTop ? m.y : m.y + m.h, xSign = xTop ? -1 : 1;
    var yAxis = yRight ? m.x + m.w : m.x, ySign = yRight ? 1 : -1;

    // Per-axis effective style -- tick_params(axis='x'/'y', ...) overrides
    // (see Axes.tick_params) survive this rebuild instead of always falling
    // back to the figure-wide default the moment a styled axes is panned or
    // zoomed.
    var globalStyle = { ts: STYLE.tick_size, tw: STYLE.tick_width,
                        fs: STYLE.tick_label_size, col: STYLE.spine, text: STYLE.text };
    var tso = om.tick_style || {};
    var xStyle = effTickStyle(globalStyle, tso.x);
    var yStyle = effTickStyle(globalStyle, tso.y);

    if (om.grid) {
      var gl = [];
      xr.ticks.forEach(function (xt) { var px = toPixel(m, xt, m.ymin).x;
        gl.push('<line x1="' + px.toFixed(2) + '" y1="' + m.y.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + (m.y + m.h).toFixed(2) + '"/>'); });
      yr.ticks.forEach(function (yt) { var py = toPixel(m, m.xmin, yt).y;
        gl.push('<line x1="' + m.x.toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + (m.x + m.w).toFixed(2) + '" y2="' + py.toFixed(2) + '"/>'); });
      // om.grid_alpha is null unless grid(alpha=...) actually overrode the
      // figure default -- a plain `||` would also treat a real alpha=0
      // override as falsy and silently revert to the figure default.
      var gridAlpha = (om.grid_alpha == null) ? STYLE.grid_alpha : om.grid_alpha;
      parts.push('<g stroke="' + STYLE.grid_color + '" stroke-width="' + STYLE.grid_width + '" stroke-opacity="' + gridAlpha + '">' + gl.join('') + '</g>');
    }
    var xmarks = [], ymarks = [], labels = [];
    xr.ticks.forEach(function (xt, i) {
      var px = toPixel(m, xt, m.ymin).x;
      var ly = xAxis + xSign * xStyle.ts + (xTop ? -3 : xStyle.fs);
      xmarks.push('<line x1="' + px.toFixed(2) + '" y1="' + xAxis.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + (xAxis + xSign * xStyle.ts).toFixed(2) + '"/>');
      labels.push('<text x="' + px.toFixed(2) + '" y="' + ly.toFixed(2) + '" text-anchor="middle" font-size="' + xStyle.fs + '" fill="' + xStyle.text + '">' + xr.labels[i] + '</text>');
    });
    yr.ticks.forEach(function (yt, i) {
      var py = toPixel(m, m.xmin, yt).y;
      var lx = yAxis + ySign * yStyle.ts + (yRight ? 2 : -2);
      ymarks.push('<line x1="' + yAxis.toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + (yAxis + ySign * yStyle.ts).toFixed(2) + '" y2="' + py.toFixed(2) + '"/>');
      labels.push('<text x="' + lx.toFixed(2) + '" y="' + (py + yStyle.fs * 0.35).toFixed(2) + '" text-anchor="' + (yRight ? 'start' : 'end') + '" font-size="' + yStyle.fs + '" fill="' + yStyle.text + '">' + yr.labels[i] + '</text>');
    });
    parts.push('<g stroke="' + xStyle.col + '" stroke-width="' + xStyle.tw + '">' + xmarks.join('') + '</g>');
    parts.push('<g stroke="' + yStyle.col + '" stroke-width="' + yStyle.tw + '">' + ymarks.join('') + '</g>');
    parts.push(labels.join(''));
    if (om.minor) {
      // Unlabeled, drawn shorter than the major marks -- mirrors
      // svg._render_minor_ticks exactly (same 0.6x length convention, and
      // the same "minor override layers onto the resolved major style").
      var xMinorStyle = effTickStyle(xStyle, tso.xminor);
      var yMinorStyle = effTickStyle(yStyle, tso.yminor);
      var xmts = xMinorStyle.ts * 0.6, ymts = yMinorStyle.ts * 0.6;
      var xmmarks = [], ymmarks = [];
      jsMinorTicks(xr.ticks, xr.step, m.xmin, m.xmax, m.xscale).forEach(function (xt) {
        var px = toPixel(m, xt, m.ymin).x;
        xmmarks.push('<line x1="' + px.toFixed(2) + '" y1="' + xAxis.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + (xAxis + xSign * xmts).toFixed(2) + '"/>');
      });
      jsMinorTicks(yr.ticks, yr.step, m.ymin, m.ymax, m.yscale).forEach(function (yt) {
        var py = toPixel(m, m.xmin, yt).y;
        ymmarks.push('<line x1="' + yAxis.toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + (yAxis + ySign * ymts).toFixed(2) + '" y2="' + py.toFixed(2) + '"/>');
      });
      parts.push('<g stroke="' + xMinorStyle.col + '" stroke-width="' + xMinorStyle.tw + '">' + xmmarks.join('') + '</g>');
      parts.push('<g stroke="' + yMinorStyle.col + '" stroke-width="' + yMinorStyle.tw + '">' + ymmarks.join('') + '</g>');
    }
    g.innerHTML = parts.join('');
  }

  // The affine that remaps the artist group from its original limits (META)
  // to the current ones (CUR) -- i.e. exactly the CSS matrix(...) transform
  // applyAxesTransform() puts on <g id="zoom{key}">. Factored out so
  // nearestVertex() can invert it too (see there for why that matters).
  function zoomAffine(key) {
    var o = META[key], c = CUR[key];
    // Work in transformed (log-aware), direction-aware space so the remap
    // stays affine. Both sets carry the same inversion flags, so an inverted
    // axis simply zooms/pans in its own direction.
    var oe = edges(o), ce = edges(c);
    var ofx0 = oe.fx0, ofx1 = oe.fx1, cfx0 = ce.fx0, cfx1 = ce.fx1;
    var ofy0 = oe.fy0, ofy1 = oe.fy1, cfy0 = ce.fy0, cfy1 = ce.fy1;
    var sx = (ofx1 - ofx0) / (cfx1 - cfx0);
    var sy = (ofy1 - ofy0) / (cfy1 - cfy0);
    var tx = o.x * (1 - sx) + (ofx0 - cfx0) / (cfx1 - cfx0) * o.w;
    var ty = o.y * (1 - sy) + (cfy1 - ofy1) / (cfy1 - cfy0) * o.h;
    return { sx: sx, sy: sy, tx: tx, ty: ty };
  }

  // Remap the artist group from original limits (META) to current (CUR).
  function applyAxesTransform(key) {
    var g = document.getElementById('zoom' + key);
    if (!g) return;
    var t = zoomAffine(key);
    if (Math.abs(t.sx - 1) < 1e-9 && Math.abs(t.sy - 1) < 1e-9 &&
        Math.abs(t.tx) < 1e-6 && Math.abs(t.ty) < 1e-6) {
      g.removeAttribute('transform');
    } else {
      g.setAttribute('transform', 'matrix(' + t.sx + ',0,0,' + t.sy + ',' + t.tx + ',' + t.ty + ')');
    }
  }

  function pinAxesKey(pin) {
    if (pin.dataset.axes !== undefined) return pin.dataset.axes;
    if (pin.dataset.frameId && FRAME_INDEX[pin.dataset.frameId])
      return String(FRAME_INDEX[pin.dataset.frameId].axesKey);
    return null;
  }
  function relayoutPins(key) {
    document.querySelectorAll('.plotpress-pin').forEach(function (pin) {
      if (pinAxesKey(pin) !== String(key)) return;
      var anchor = pinAnchor(pin);
      if (anchor) {
        var a = resolve(anchor, +pin.dataset.index);
        if (a) layoutPin(pin, a.px, a.py, pinLabel(pin, a.label));
      } else if (pin.dataset.x !== undefined && CUR[key]) {
        var q = toPixel(CUR[key], +pin.dataset.x, +pin.dataset.y);
        layoutPin(pin, q.x, q.y, pin.querySelector('text').textContent);
      }
    });
  }

  // A data-anchored text()/annotate() label -- svg.py's plotpress-cscale
  // group, opened around its glyphs (and bbox, if any) with data-x0/data-y0
  // holding the anchor point zoomAffine() itself already maps correctly.
  // Composing this group's counter-scale with the zoom{key} group's own
  // matrix(sx,0,0,sy,...) leaves that anchor point exactly where plain
  // ancestor scaling already puts it (so it still tracks the data), while
  // canceling the *local* stretch around it -- the label keeps a constant
  // screen size instead of growing or shrinking with the zoom level, the
  // same as a title, tick label, or point-pick pin already does. Unlike a
  // marker (a footprint *on* the data, deliberately scaling with the axis --
  // see the marker-scaling fix), a label exists to be read.
  function relayoutTextCounterScale(key) {
    var t = zoomAffine(key);
    document.querySelectorAll('.plotpress-cscale').forEach(function (g) {
      if (g.dataset.axes !== String(key)) return;
      var x0 = +g.dataset.x0, y0 = +g.dataset.y0;
      var isx = t.sx ? 1 / t.sx : 1, isy = t.sy ? 1 / t.sy : 1;
      g.setAttribute('transform',
        'translate(' + x0 + ',' + y0 + ') scale(' + isx + ',' + isy + ') ' +
        'translate(' + (-x0) + ',' + (-y0) + ')');
    });
  }

  // A twin/secondary axes occupies the exact same pixel rect as its parent,
  // so only one of them is ever the axesAt() hit -- whichever one changed
  // must push its new limits onto the other(s), or the pair visually comes
  // apart: one moves under the drag, the other stays frozen at its initial
  // view. A twin shares only its `twin_shared` dimension (its other axis is
  // independent, real data); a secondary axis has no data of its own and
  // mirrors both dimensions unconditionally. Normalizing to a single "root"
  // axes first (the plain axes a twin/secondary is attached to) means a drag
  // that happens to hit the twin/secondary itself -- possible now that
  // axesAt() prefers the most-recently-added match -- still fans out to every
  // sibling instead of only updating one leg of the link.
  function syncLinked(key) {
    var m = META[key];
    if (!m) return;
    var root = key, rc = CUR[key];
    if (m.twin_of !== null && m.twin_of !== undefined && CUR[String(m.twin_of)]) {
      root = String(m.twin_of);
      var pc = CUR[root];
      if (m.twin_shared === 'x') { pc.xmin = rc.xmin; pc.xmax = rc.xmax; }
      else if (m.twin_shared === 'y') { pc.ymin = rc.ymin; pc.ymax = rc.ymax; }
      applyAxesTransform(root); rebuildTicks(root); relayoutPins(root); relayoutTextCounterScale(root);
      rc = pc;
    } else if (m.secondary_of !== null && m.secondary_of !== undefined &&
              CUR[String(m.secondary_of)]) {
      root = String(m.secondary_of);
      var pc2 = CUR[root];
      pc2.xmin = rc.xmin; pc2.xmax = rc.xmax; pc2.ymin = rc.ymin; pc2.ymax = rc.ymax;
      applyAxesTransform(root); rebuildTicks(root); relayoutPins(root); relayoutTextCounterScale(root);
      rc = pc2;
    }
    for (var k in META) {
      if (k === key || k === root) continue;
      var mo = META[k], dst = CUR[k];
      if (String(mo.twin_of) === root) {
        if (mo.twin_shared === 'x') { dst.xmin = rc.xmin; dst.xmax = rc.xmax; }
        else if (mo.twin_shared === 'y') { dst.ymin = rc.ymin; dst.ymax = rc.ymax; }
        applyAxesTransform(k); rebuildTicks(k); relayoutPins(k); relayoutTextCounterScale(k);
      } else if (String(mo.secondary_of) === root) {
        dst.xmin = rc.xmin; dst.xmax = rc.xmax; dst.ymin = rc.ymin; dst.ymax = rc.ymax;
        applyAxesTransform(k); rebuildTicks(k); relayoutPins(k); relayoutTextCounterScale(k);
      }
    }
  }

  function refreshAxes(key) {
    applyAxesTransform(key); rebuildTicks(key); relayoutPins(key); relayoutTextCounterScale(key);
    syncLinked(key);
  }
  function resetAxesOne(key) {
    for (var f in META[key]) CUR[key][f] = META[key][f];
    var g = document.getElementById('zoom' + key);
    if (g) g.removeAttribute('transform');
    rebuildTicks(key);
    relayoutPins(key);
    relayoutTextCounterScale(key);
    // Otherwise double-clicking just the parent of a pan-desynced twin/
    // secondary snaps the parent back but leaves the other one stranded at
    // whatever view it last drifted to.
    syncLinked(key);
  }
  function resetAxes() { Object.keys(META).forEach(resetAxesOne); }

  // Nearest embedded data point (carries any extra dims: c, z, ...).
  function nearestPoint(key, m, p) {
    var pd = PICK[key];
    if (!pd) return null;
    var best = null;
    pd.series.forEach(function (s, si) {
      for (var j = 0; j < s.x.length; j++) {
        var q = toPixel(m, s.x[j], s.y[j]);
        var d = (q.x - p.x) * (q.x - p.x) + (q.y - p.y) * (q.y - p.y);
        if (!best || d < best.d) {
          best = { d: d, ref: { kind: 'points', axes: key, series: si,
                                index: j, ptype: s.kind } };
        }
      }
    });
    return best;
  }

  // Index of the edge bucket containing v (edges.length - 1 buckets, i.e. one
  // per cell) -- a plain linear scan, since a capped mesh has at most a few
  // hundred edges per axis. Dividing the extent evenly instead of searching
  // the real edges is only correct for a uniform grid; pcolormesh/contour
  // both explicitly allow non-uniform spacing.
  function bucketIndex(edges, v) {
    var n = edges.length - 1;
    if (v <= edges[0]) return 0;
    if (v >= edges[n]) return n - 1;
    for (var i = 0; i < n; i++) {
      if (v >= edges[i] && v <= edges[i + 1]) return i;
    }
    return n - 1;
  }

  // A cell's center in data space, for placing a marker / reading it back.
  // A curvilinear mesh has no separable edges -- xc/yc give every cell's
  // center directly (see plotpress.svg._curvilinear_centers). A contour's
  // "cells" are really point samples: xcoord/ycoord (when present) are the
  // exact sample coordinates, which for non-uniform spacing generally isn't
  // the same as the midpoint of its implied edges.
  function meshCellCenter(mesh, idx) {
    var nx = mesh.shape[1];
    if (mesh.curvilinear) return { x: mesh.xc[idx], y: mesh.yc[idx] };
    var row = Math.floor(idx / nx), col = idx % nx;
    if (mesh.xcoord) return { x: mesh.xcoord[col], y: mesh.ycoord[row] };
    var xe = mesh.xedges, ye = mesh.yedges;
    return { x: (xe[col] + xe[col + 1]) / 2, y: (ye[row] + ye[row + 1]) / 2 };
  }

  // Mesh cell under a data coordinate -> anchor ref (steppable by cell).
  // `p` (pixel point) is only needed for a curvilinear mesh's nearest-center
  // search, which has to compare in pixel space the same way nearestPoint()
  // does for a scatter series -- data-space distance would be meaningless
  // whenever x and y are in different units/scales.
  function meshAt(key, dx, dy, p) {
    var pd = PICK[key];
    if (!pd) return null;
    var m = CUR[key];
    for (var t = 0; t < pd.meshes.length; t++) {
      var mesh = pd.meshes[t], e = mesh.extent;
      // Test containment in *pixel* space, with a couple pixels of slack: a
      // click aimed at the mesh's boundary (its edge is exactly where a user
      // would click to hit the outermost cell) can round-trip through
      // toData() landing a hair outside the extent in data space -- fine
      // there, since a data-space epsilon that's meaningful for a [0, 1]
      // axis is meaningless for a [0, 1e6] one, but wrong in pixel space,
      // where "a hair" is the same couple of pixels regardless of scale.
      var c0 = toPixel(m, e[0], e[2]), c1 = toPixel(m, e[1], e[3]);
      var px0 = Math.min(c0.x, c1.x) - 2, px1 = Math.max(c0.x, c1.x) + 2;
      var py0 = Math.min(c0.y, c1.y) - 2, py1 = Math.max(c0.y, c1.y) + 2;
      if (p.x < px0 || p.x > px1 || p.y < py0 || p.y > py1) continue;
      dx = Math.min(e[1], Math.max(e[0], dx));
      dy = Math.min(e[3], Math.max(e[2], dy));
      if (mesh.curvilinear) {
        var best = -1, bd = Infinity;
        for (var c = 0; c < mesh.xc.length; c++) {
          var q = toPixel(m, mesh.xc[c], mesh.yc[c]);
          var dd = (q.x - p.x) * (q.x - p.x) + (q.y - p.y) * (q.y - p.y);
          if (dd < bd) { bd = dd; best = c; }
        }
        if (best < 0) continue;
        return { kind: 'mesh', axes: key, mesh: t, index: best };
      }
      var nx = mesh.shape[1];
      var col = bucketIndex(mesh.xedges, dx), row = bucketIndex(mesh.yedges, dy);
      return { kind: 'mesh', axes: key, mesh: t, index: row * nx + col };
    }
    return null;
  }

  // A pcolormesh_frames() mesh under a data coordinate -> anchor ref, exactly
  // like meshAt() above but sourced from FRAMES (per-frame z, geometry shared
  // across frames) instead of the static PICK payload -- a slider-driven mesh
  // has no entry in PICK at all (see frame_data()), so a click on one used to
  // find nothing to pick, however close to a cell center.
  function meshFrameAt(key, dx, dy, p) {
    var entries = FRAMES && FRAMES[key];
    if (!entries) return null;
    var m = CUR[key];
    for (var t = 0; t < entries.length; t++) {
      var mesh = entries[t];
      if (!mesh.z) continue;   // a frame-line entry, not a frame-mesh one
      var e = mesh.extent;
      var c0 = toPixel(m, e[0], e[2]), c1 = toPixel(m, e[1], e[3]);
      var px0 = Math.min(c0.x, c1.x) - 2, px1 = Math.max(c0.x, c1.x) + 2;
      var py0 = Math.min(c0.y, c1.y) - 2, py1 = Math.max(c0.y, c1.y) + 2;
      if (p.x < px0 || p.x > px1 || p.y < py0 || p.y > py1) continue;
      dx = Math.min(e[1], Math.max(e[0], dx));
      dy = Math.min(e[3], Math.max(e[2], dy));
      if (mesh.curvilinear) {
        var best = -1, bd = Infinity;
        for (var c = 0; c < mesh.xc.length; c++) {
          var q = toPixel(m, mesh.xc[c], mesh.yc[c]);
          var dd = (q.x - p.x) * (q.x - p.x) + (q.y - p.y) * (q.y - p.y);
          if (dd < bd) { bd = dd; best = c; }
        }
        if (best < 0) continue;
        return { kind: 'meshframe', axes: key, id: mesh.id, unit: mesh.unit, index: best };
      }
      var nx = mesh.shape[1];
      var col = bucketIndex(mesh.xedges, dx), row = bucketIndex(mesh.yedges, dy);
      return { kind: 'meshframe', axes: key, id: mesh.id, unit: mesh.unit,
               index: row * nx + col };
    }
    return null;
  }

  // Pie wedge under a pixel point -> anchor ref (steppable by wedge).
  function pieCenter(m, pie) {
    return { cx: m.x + m.w / 2, cy: m.y + m.h / 2,
             R: 0.42 * Math.min(m.w, m.h) * (pie.radius || 1) };
  }
  function pieAt(key, p) {
    var pd = PICK[key];
    if (!pd || !pd.pies) return null;
    var m = META[key];
    for (var t = 0; t < pd.pies.length; t++) {
      var pie = pd.pies[t], c = pieCenter(m, pie);
      var dx = p.x - c.cx, dy = p.y - c.cy;
      if (dx * dx + dy * dy > c.R * c.R) continue;
      var ang = Math.atan2(-dy, dx);              // math angle (y up)
      var start = pie.startangle * Math.PI / 180, cum = 0;
      for (var wi = 0; wi < pie.fracs.length; wi++) {
        var a0 = start - 2 * Math.PI * cum;
        var span = 2 * Math.PI * pie.fracs[wi];
        var d = (a0 - ang) % (2 * Math.PI); if (d < 0) d += 2 * Math.PI;
        if (d <= span + 1e-9) return { kind: 'pie', axes: key, pie: t, index: wi };
        cum += pie.fracs[wi];
      }
    }
    return null;
  }

  // Geometry fallback for series too large to embed (x/y only). The raw
  // d/cx/cy attributes queried here are whatever svg.py wrote at export time
  // -- pixel positions in the *original* (pre-pan/zoom) axes limits, i.e. the
  // zoom{i} group's local space before applyAxesTransform() puts a CSS
  // matrix(...) on it. `p` (from toUser(e)) is root/current-view space, the
  // space that matrix maps *into* -- comparing them directly, as this used
  // to, silently returned the nearest vertex in the wrong space the moment
  // the axes had been panned or zoomed. Map p through the inverse of that
  // same affine first, then map the winning point back, so both the search
  // and the returned pixel position agree with what's actually on screen.
  function nearestVertex(i, p) {
    var t = zoomAffine(i);
    var lp = { x: (p.x - t.tx) / t.sx, y: (p.y - t.ty) / t.sy };
    var best = null, bd = Infinity;
    document.querySelectorAll('[id^="s' + i + '_"]').forEach(function (el) {
      var tag = el.tagName.toLowerCase(), pts = [];
      if (tag === 'line') return;
      if (tag === 'path') {
        var nums = (el.getAttribute('d') || '').match(/-?\d+(?:\.\d+)?/g) || [];
        for (var j = 0; j + 1 < nums.length; j += 2) pts.push({ x: +nums[j], y: +nums[j + 1] });
      } else if (tag === 'circle') {
        pts.push({ x: +el.getAttribute('cx'), y: +el.getAttribute('cy') });
      } else {
        el.querySelectorAll('circle').forEach(function (c) {
          pts.push({ x: +c.getAttribute('cx'), y: +c.getAttribute('cy') });
        });
      }
      for (var q = 0; q < pts.length; q++) {
        var d = (pts[q].x - lp.x) * (pts[q].x - lp.x) + (pts[q].y - lp.y) * (pts[q].y - lp.y);
        if (d < bd) { bd = d; best = pts[q]; }
      }
    });
    return best ? { x: best.x * t.sx + t.tx, y: best.y * t.sy + t.ty } : null;
  }

  function fmt(v) {
    var a = Math.abs(v);
    if (a !== 0 && (a < 1e-3 || a >= 1e5)) return v.toExponential(2);
    return (Math.round(v * 1000) / 1000).toString();
  }

  // Local, origin-relative coordinates -- (0,0) is the pin's own anchor --
  // plus a group-level transform (translate to the anchor, scale by
  // 1/zoomScale) instead of baking px/py straight into each child. Whole-
  // figure zoom (see applyZoomSize) grows the *entire* SVG's rendered CSS
  // size uniformly, which would otherwise carry a pin's fixed viewBox-unit
  // radius up right along with the data -- readable as "8px" at rest and a
  // 50px+ blob covering the very mesh cell it's pointing at eight ticks of
  // Magnify later, the opposite of what zooming in is for. The 1/zoomScale
  // factor cancels that growth out, so a pin renders at the same on-screen
  // size at any zoom level; updatePinTransform() (called from
  // applyZoomSize() for every existing pin, not just the one being laid
  // out here) is what keeps that true as zoomScale changes after the pin
  // already exists.
  function layoutPin(g, px, py, label) {
    var fs = 11, padx = 5, pady = 3;
    var bw = label.length * fs * 0.55 + padx * 2, bh = fs + pady * 2;
    // A user-dragged box (see startBoxDrag) keeps its own chosen offset
    // from the dot across every later re-layout (pan, zoom, arrow-key
    // step) -- the default top-right placement only applies until the box
    // is actually moved once.
    var bx = g.dataset.boxDx !== undefined ? +g.dataset.boxDx : 8;
    var by = g.dataset.boxDy !== undefined ? +g.dataset.boxDy : -bh - 4;
    var dot = g.querySelector('circle'), rect = g.querySelector('rect'),
        text = g.querySelector('text'), arrow = g.querySelector('.plotpress-pin-arrow');
    dot.setAttribute('cx', 0); dot.setAttribute('cy', 0);
    rect.setAttribute('x', bx); rect.setAttribute('y', by);
    rect.setAttribute('width', bw); rect.setAttribute('height', bh);
    text.setAttribute('x', bx + padx); text.setAttribute('y', by + fs + pady - 2);
    text.textContent = label;
    syncPinArrow(g);
    g.dataset.anchorX = px; g.dataset.anchorY = py;
    updatePinTransform(g);
  }

  // Re-lays-out just the leader line, from whatever the box/dot's own
  // current attributes already are -- called after layoutPin() has just
  // set the box (dot/rect already current), and again from selectPin()
  // when a dot's rendered radius itself changes (selecting/deselecting)
  // without anything else about the pin moving. Reads the dot's *rendered*
  // `r` attribute, not the resting dataset.pinR: selectPin() enlarges a
  // selected dot to 1.4x that resting size without going through
  // layoutPin() again, and a freshly dropped pin starts selected (see
  // addPin()) -- feeding the arrow the resting radius while the dot itself
  // was already bigger left the arrowhead visibly short of the dot's own
  // edge on every single pin, not just an edge case.
  function syncPinArrow(g) {
    var rect = g.querySelector('rect'), dot = g.querySelector('circle'),
        arrow = g.querySelector('.plotpress-pin-arrow');
    if (!rect || !dot || !arrow) return;
    layoutPinArrow(arrow, +rect.getAttribute('x'), +rect.getAttribute('y'),
                   +rect.getAttribute('width'), +rect.getAttribute('height'),
                   +dot.getAttribute('r'));
  }

  // The leader line from the box's edge to the dot's own edge (not its
  // center -- the arrowhead should land on the dot, not point past it).
  // "Nearest point on the box's rectangle to the origin" (clamp 0 into the
  // box's own x/y bounds) is the box-end regardless of which side/corner of
  // the dot the box currently sits on, including after an arbitrary drag.
  function layoutPinArrow(arrow, bx, by, bw, bh, r) {
    if (!arrow) return;
    var lx = Math.max(bx, Math.min(bx + bw, 0));
    var ly = Math.max(by, Math.min(by + bh, 0));
    var d = Math.hypot(lx, ly);
    // The box already overlaps/touches the dot -- no line to draw (and
    // dividing by d below would be undefined at d===0).
    if (d <= r) {
      arrow.setAttribute('x1', 0); arrow.setAttribute('y1', 0);
      arrow.setAttribute('x2', 0); arrow.setAttribute('y2', 0);
      return;
    }
    // The point on the (lx,ly)->(0,0) segment exactly r from the origin --
    // scaling (lx,ly) by r/d (not 1 - r/d, which barely moves it at all
    // once the box is far from the dot) lands there regardless of d.
    var k = r / d;
    arrow.setAttribute('x1', lx); arrow.setAttribute('y1', ly);
    arrow.setAttribute('x2', lx * k); arrow.setAttribute('y2', ly * k);
  }

  function updatePinTransform(g) {
    g.setAttribute('transform', 'translate(' + g.dataset.anchorX + ',' +
      g.dataset.anchorY + ') scale(' + (1 / zoomScale) + ')');
  }

  // The selected dot draws a bit larger than its resting size -- scaled from
  // that pin's *own* radius (see pinRadius), not a flat bump, so a selected
  // marker on a tiny panel still reads as "this one, bigger" rather than
  // ballooning back up to the fixed size pinRadius was added to avoid. Each
  // dot whose radius actually changes here gets its own leader arrow synced
  // right after -- see syncPinArrow's own comment for why this can't wait
  // for the next ordinary re-layout.
  function selectPin(g) {
    if (selectedPin && selectedPin !== g) {
      selectedPin.classList.remove('selected');
      var prevDot = selectedPin.querySelector('circle');
      if (prevDot) prevDot.setAttribute('r', selectedPin.dataset.pinR || 3.5);
      syncPinArrow(selectedPin);
    }
    selectedPin = g;
    if (g) {
      g.classList.add('selected');
      var dot = g.querySelector('circle');
      if (dot) dot.setAttribute('r', (parseFloat(g.dataset.pinR) || 3.5) * 1.4);
      syncPinArrow(g);
    }
  }

  // A marker sized for a huge grid's tiny panels would be a fixed 3.5px dot
  // sitting like a boulder on an axes 40px across -- scale it to the axes
  // it actually belongs to instead, clamped so it never shrinks below
  // comfortably clickable or grows past the size that already looked right
  // on a normal, single-axes figure. `axesKey` is left out (undefined) for
  // a free annotation, which belongs to no axes at all -- falls back to
  // that same normal-figure default.
  function pinRadius(axesKey) {
    var m = axesKey !== undefined && axesKey !== null ? CUR[axesKey] : null;
    if (!m) return 3.5;
    return Math.max(2.0, Math.min(3.5, Math.min(m.w, m.h) * 0.045));
  }

  function addPin(px, py, label, axesKey) {
    var g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', 'plotpress-pin'); g.style.cursor = 'pointer';
    var r = pinRadius(axesKey);
    g.dataset.pinR = r;
    var dot = document.createElementNS(SVGNS, 'circle');
    dot.setAttribute('r', r); dot.setAttribute('fill', '#111');
    dot.setAttribute('stroke', '#fff'); dot.setAttribute('stroke-width', 1);
    var arrow = document.createElementNS(SVGNS, 'line');
    arrow.setAttribute('class', 'plotpress-pin-arrow');
    arrow.setAttribute('stroke', '#666'); arrow.setAttribute('stroke-width', 1);
    arrow.setAttribute('marker-end', 'url(#plotpress-pin-arrow)');
    var rect = document.createElementNS(SVGNS, 'rect');
    rect.setAttribute('rx', 3); rect.setAttribute('fill', '#111');
    rect.setAttribute('fill-opacity', 0.85);
    var text = document.createElementNS(SVGNS, 'text');
    text.setAttribute('font-size', 11); text.setAttribute('fill', '#fff');
    g.appendChild(dot); g.appendChild(arrow); g.appendChild(rect); g.appendChild(text);
    layoutPin(g, px, py, label);
    // Left-click selects (arrow keys then step it); right-click deletes;
    // a left-click/drag specifically on the box (not the dot) repositions
    // its label -- see startBoxDrag -- while the mode that would have
    // created this kind of pin is the active one (boxDraggableNow).
    g.addEventListener('click', function (ev) { ev.stopPropagation(); selectPin(g); });
    g.addEventListener('contextmenu', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      if (selectedPin === g) selectedPin = null;
      g.remove();
    });
    g.addEventListener('mousedown', function (ev) {
      if (ev.button !== 0 || (ev.target !== rect && ev.target !== text)) return;
      if (!boxDraggableNow(g)) return;
      startBoxDrag(g, ev);
    });
    svg.appendChild(g);
    selectPin(g);   // a freshly dropped marker starts selected
    refreshOneDragReady(g);
    return g;
  }

  // Draggable exactly when the mode that would have created this kind of
  // pin is the active one -- a plain Point Picking pin under 'pick', every
  // Annotation-classed pin (a free note, or a legacy "Annotate Point"
  // restore -- see restorePins) under 'note-free'. The same split Clear
  // Points/Clear Annotations already use (see isAnnotationPin above).
  function boxDraggableNow(g) {
    return isAnnotationPin(g) ? mode === 'note-free' : mode === 'pick';
  }

  // Just this one pin -- O(1), not a full document sweep -- for the common
  // case of a single pin's own draggability possibly changing (created,
  // just gained/lost .plotpress-note). A mode CHANGE (see setMode) still
  // needs the full sweep below, since every existing pin's answer can flip
  // at once; creating/restoring pins one at a time never needs more than
  // this, and restorePins() replaying a whole saved file through addPin()/
  // addAnchoredPin() one call at a time is exactly the case where an O(n)
  // sweep *per pin created* would make loading n saved pins O(n^2).
  function refreshOneDragReady(g) {
    g.classList.toggle('plotpress-drag-ready', boxDraggableNow(g));
  }

  // Refreshed on every mode change (every existing pin's answer can flip at
  // once) and once after a whole restorePins() replay -- purely a cursor
  // hint (the actual drag gate is boxDraggableNow(), checked fresh at
  // mousedown regardless of this class), but a "move" cursor over a box
  // that's about to not respond to a drag would be its own small bug.
  function refreshDragReady() {
    document.querySelectorAll('.plotpress-pin').forEach(refreshOneDragReady);
  }

  // Repositions a pin's own label box independent of its anchor (the dot
  // stays exactly on the data point/cell it represents) -- converts the
  // mouse's on-screen pixel delta into the box's *local* coordinate space
  // (see layoutPin's own comment on that space): a local unit there is
  // 1/zoomScale user-space units (the group's own scale(1/zoomScale)
  // keeps a pin's on-screen size constant under whole-figure zoom), and a
  // user-space unit is 1/pxPerUser() screen pixels -- so a screen delta
  // needs multiplying by zoomScale and dividing by pxPerUser() to land in
  // local units, the exact inverse of what rendering does to local
  // coordinates to put them on screen.
  function startBoxDrag(g, ev) {
    ev.stopPropagation(); ev.preventDefault();
    selectPin(g);
    var startX = ev.clientX, startY = ev.clientY;
    var rect = g.querySelector('rect');
    var bx0 = +rect.getAttribute('x'), by0 = +rect.getAttribute('y');
    var text = g.querySelector('text');
    function onMove(e) {
      var k = zoomScale / pxPerUser();
      g.dataset.boxDx = bx0 + (e.clientX - startX) * k;
      g.dataset.boxDy = by0 + (e.clientY - startY) * k;
      layoutPin(g, +g.dataset.anchorX, +g.dataset.anchorY, text.textContent);
    }
    function onUp() {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  // The (x, y, vals) arrays a point/frame anchor refers to, at the live frame.
  function seriesOf(anchor) {
    if (anchor.kind === 'frame') {
      var rec = FRAME_INDEX[anchor.id];
      if (!rec) return null;
      var f = CURRENT_FRAME[anchor.unit] || 0, e = rec.entry;
      return { axes: rec.axesKey, x: e.shared_x ? e.x : e.x[f], y: e.Y[f], vals: null };
    }
    var s = PICK[anchor.axes] && PICK[anchor.axes].series[anchor.series];
    return s ? { axes: anchor.axes, x: s.x, y: s.y, vals: s.vals } : null;
  }

  // Resolve a marker anchor at an index/cell -> pixel position + label.
  function resolve(anchor, index) {
    if (anchor.kind === 'pie') {
      var pd = PICK[anchor.axes], pie = pd.pies[anchor.pie], m = META[anchor.axes];
      var n = pie.fracs.length, idx = ((index % n) + n) % n;
      var c = pieCenter(m, pie), cum = 0;
      for (var w = 0; w < idx; w++) cum += pie.fracs[w];
      var a0 = pie.startangle * Math.PI / 180 - 2 * Math.PI * cum;
      var am = a0 - Math.PI * pie.fracs[idx];   // wedge bisector
      var lbl = (pie.labels ? pie.labels[idx] + ': ' : '') + fmt(pie.values[idx]) +
                ' (' + (pie.fracs[idx] * 100).toFixed(1) + '%)';
      return { px: c.cx + 0.6 * c.R * Math.cos(am),
               py: c.cy - 0.6 * c.R * Math.sin(am), index: idx, label: lbl };
    }
    if (anchor.kind === 'mesh') {
      var mesh = PICK[anchor.axes] && PICK[anchor.axes].meshes[anchor.mesh];
      if (!mesh) return null;
      var nx = mesh.shape[1], ny = mesh.shape[0];
      var idx = Math.max(0, Math.min(nx * ny - 1, index));
      var cc = meshCellCenter(mesh, idx);
      var q = toPixel(CUR[anchor.axes], cc.x, cc.y);
      return { px: q.x, py: q.y, index: idx, label: 'x=' + fmt(cc.x) + ', y=' +
               fmt(cc.y) + ', ' + (mesh.name || 'z') + '=' + fmt(mesh.z[idx]) };
    }
    if (anchor.kind === 'meshframe') {
      var rec = FRAME_INDEX[anchor.id];
      if (!rec) return null;
      var mesh = rec.entry, f = CURRENT_FRAME[mesh.unit] || 0;
      var nx = mesh.shape[1], ny = mesh.shape[0];
      var idx = Math.max(0, Math.min(nx * ny - 1, index));
      var cc = meshCellCenter(mesh, idx);
      // The cell's own position never changes frame to frame (mesh_frames'
      // X/Y are shared, only C animates) -- only the value in its label does.
      var q = toPixel(CUR[rec.axesKey], cc.x, cc.y);
      return { px: q.x, py: q.y, index: idx, label: 'x=' + fmt(cc.x) + ', y=' +
               fmt(cc.y) + ', ' + (mesh.name || 'z') + '=' + fmt(mesh.z[f][idx]) };
    }
    var s = seriesOf(anchor);
    if (!s) return null;
    var j = Math.max(0, Math.min(s.x.length - 1, index));
    var q2 = toPixel(CUR[s.axes], s.x[j], s.y[j]);
    var lbl = 'x=' + fmt(s.x[j]) + ', y=' + fmt(s.y[j]);
    if (s.vals) for (var k in s.vals) lbl += ', ' + k + '=' + fmt(s.vals[k][j]);
    return { px: q2.x, py: q2.y, index: j, label: lbl };
  }

  // Directional nearest neighbour (pixel space) for scatter clouds.
  function scatterNeighbor(anchor, cur, dir) {
    var s = seriesOf(anchor), m = CUR[anchor.axes];
    var c = toPixel(m, s.x[cur], s.y[cur]);
    var best = cur, bd = Infinity;
    for (var j = 0; j < s.x.length; j++) {
      if (j === cur) continue;
      var q = toPixel(m, s.x[j], s.y[j]);
      var dx = q.x - c.x, dy = q.y - c.y;   // pixel y grows downward
      var ok = dir === 'right' ? dx > 0.5 : dir === 'left' ? dx < -0.5 :
               dir === 'up' ? dy < -0.5 : dy > 0.5;
      if (!ok) continue;
      var dist = dx * dx + dy * dy;
      if (dist < bd) { bd = dist; best = j; }
    }
    return best;
  }

  // Next index/cell for a marker given an arrow direction.
  function neighbor(anchor, index, dir) {
    if (anchor.kind === 'pie') {
      var n = PICK[anchor.axes].pies[anchor.pie].fracs.length;
      return index + ((dir === 'right' || dir === 'up') ? 1 : -1) + n;  // resolve wraps
    }
    if (anchor.kind === 'mesh' || anchor.kind === 'meshframe') {
      var mesh = anchor.kind === 'mesh' ? PICK[anchor.axes].meshes[anchor.mesh]
                                        : FRAME_INDEX[anchor.id].entry;
      var nx = mesh.shape[1], ny = mesh.shape[0];
      var row = Math.floor(index / nx), col = index % nx;
      // Row/col grow with data value, not screen position -- on an inverted
      // axis, larger data value is drawn toward the *start* of the screen
      // (left/top), so the arrow key's screen-space meaning flips too.
      var am = META[anchor.axes] || {};
      var right = am.xinv ? -1 : 1, up = am.yinv ? -1 : 1;
      if (dir === 'right') col = Math.min(nx - 1, Math.max(0, col + right));
      else if (dir === 'left') col = Math.min(nx - 1, Math.max(0, col - right));
      else if (dir === 'up') row = Math.min(ny - 1, Math.max(0, row + up));
      else row = Math.min(ny - 1, Math.max(0, row - up));
      return row * nx + col;
    }
    if (anchor.kind === 'points' && anchor.ptype === 'scatter') {
      return scatterNeighbor(anchor, index, dir);
    }
    // line / frame: step in array order
    return index + ((dir === 'right' || dir === 'up') ? 1 : -1);
  }

  function pinAnchor(pin) {
    var k = pin.dataset.kind;
    if (!k) return null;   // mesh-less fallback pins aren't steppable
    if (k === 'frame') return { kind: 'frame', id: pin.dataset.frameId, unit: pin.dataset.frameUnit };
    if (k === 'meshframe') return { kind: 'meshframe', axes: pin.dataset.axes,
                                    id: pin.dataset.frameId, unit: pin.dataset.frameUnit };
    if (k === 'mesh') return { kind: 'mesh', axes: pin.dataset.axes, mesh: +pin.dataset.mesh };
    if (k === 'pie') return { kind: 'pie', axes: pin.dataset.axes, pie: +pin.dataset.pie };
    return { kind: 'points', axes: pin.dataset.axes, series: +pin.dataset.series,
             ptype: pin.dataset.ptype };
  }

  // `text`, when given, overrides the auto-generated "x=.., y=.." readout --
  // an "Annotate Point" note locked to this anchor. It has to be threaded
  // through stepPin/relayoutPins too, or the very first re-layout (a step, a
  // pan, a zoom) would stomp the user's text back to the plain readout.
  function addAnchoredPin(anchor, index, text) {
    var a = resolve(anchor, index);
    if (!a) return;
    var g = addPin(a.px, a.py, text !== undefined ? text : a.label, anchor.axes);
    g.dataset.kind = anchor.kind;
    g.dataset.index = a.index;
    if (text !== undefined) { g.dataset.customLabel = text; g.classList.add('plotpress-note'); }
    if (anchor.kind === 'frame') {
      g.dataset.frameId = anchor.id; g.dataset.frameUnit = anchor.unit;
    } else if (anchor.kind === 'meshframe') {
      g.dataset.axes = anchor.axes;
      g.dataset.frameId = anchor.id; g.dataset.frameUnit = anchor.unit;
    } else if (anchor.kind === 'mesh') {
      g.dataset.axes = anchor.axes; g.dataset.mesh = anchor.mesh;
    } else if (anchor.kind === 'pie') {
      g.dataset.axes = anchor.axes; g.dataset.pie = anchor.pie;
    } else {
      g.dataset.axes = anchor.axes; g.dataset.series = anchor.series;
      g.dataset.ptype = anchor.ptype;
    }
    // addPin() already refreshed drag-readiness once, before the
    // .plotpress-note class above (a legacy "Annotate Point" restore) was
    // applied -- that class is what boxDraggableNow() itself keys its
    // point-picking-vs-annotation split on, so it has to run again now
    // that it's actually set.
    if (text !== undefined) refreshOneDragReady(g);
    return g;
  }

  function pinLabel(pin, autoLabel) {
    return pin.dataset.customLabel !== undefined ? pin.dataset.customLabel : autoLabel;
  }

  // Move a marker to a neighbouring point/cell (arrow keys).
  function stepPin(pin, dir) {
    var anchor = pinAnchor(pin);
    if (!anchor) return;
    var a = resolve(anchor, neighbor(anchor, +pin.dataset.index, dir));
    if (!a) return;
    pin.dataset.index = a.index;
    layoutPin(pin, a.px, a.py, pinLabel(pin, a.label));
  }

  // ---- extract markers --------------------------------------------------
  // Structured values for one marker (numbers, incl. any extra dims).
  function markerRecord(pin) {
    var anchor = pinAnchor(pin), rec = {};
    if (anchor && anchor.kind === 'pie') {
      var pie = PICK[anchor.axes].pies[anchor.pie], idx = +pin.dataset.index;
      rec.axes = +anchor.axes; rec.kind = 'pie'; rec.index = idx;
      rec.value = pie.values[idx]; rec.fraction = pie.fracs[idx];
      if (pie.labels) rec.label = pie.labels[idx];
    } else if (anchor && anchor.kind === 'mesh') {
      var mesh = PICK[anchor.axes].meshes[anchor.mesh];
      var idx = +pin.dataset.index;
      var cc = meshCellCenter(mesh, idx);
      rec.axes = +anchor.axes; rec.kind = 'mesh'; rec.index = idx;
      rec.x = cc.x; rec.y = cc.y;
      rec[mesh.name || 'z'] = mesh.z[idx];
    } else if (anchor && anchor.kind === 'meshframe') {
      var mesh = FRAME_INDEX[anchor.id].entry, idx = +pin.dataset.index;
      var f = CURRENT_FRAME[mesh.unit] || 0;
      var cc = meshCellCenter(mesh, idx);
      rec.axes = +anchor.axes; rec.kind = 'meshframe'; rec.index = idx;
      rec.x = cc.x; rec.y = cc.y;
      rec[mesh.name || 'z'] = mesh.z[f][idx];
    } else if (anchor) {
      var s = seriesOf(anchor), j = +pin.dataset.index;
      rec.axes = +s.axes; rec.kind = anchor.kind; rec.index = j;
      rec.x = s.x[j]; rec.y = s.y[j];
      // s.vals comes from the plotting call's own pick_values={...} -- an
      // arbitrary, user-chosen key (e.g. "kind") must not clobber the
      // structured fields just set above, same rule set_pick_context
      // follows below for its own axes-level context.
      if (s.vals) for (var k in s.vals) if (!(k in rec)) rec[k] = s.vals[k][j];
    } else if (pin.dataset.annotation) {
      rec.kind = 'annotation';
      rec.text = pin.querySelector('text').textContent;
      if (pin.dataset.axes !== undefined) {
        rec.axes = +pin.dataset.axes;
        rec.x = +pin.dataset.x; rec.y = +pin.dataset.y;
      } else {
        // Dropped outside any axes (an Annotation note in the figure's
        // margins or between panels) -- there is no data coordinate to give
        // it, only a fixed figure pixel position.
        rec.px = +pin.dataset.px; rec.py = +pin.dataset.py;
      }
    } else {
      rec.kind = 'free';
      if (pin.dataset.axes !== undefined) rec.axes = +pin.dataset.axes;
      rec.x = +pin.dataset.x; rec.y = +pin.dataset.y;
    }
    // A legacy "Annotate Point" note's user text (see the restore-a-pin
    // comment above -- that mode no longer creates new pins, only old saved
    // files can still carry one) rides alongside its anchor's own
    // structured fields (x/y/z/...) set above, rather than replacing them.
    if (pin.dataset.customLabel !== undefined) rec.text = pin.dataset.customLabel;
    // Identify the source panel by name, not just its bare index -- falls
    // back to a generated name when that axes has no title set, so every
    // record carries one. xlabel/ylabel/zlabel (zlabel from any colorbar
    // attached to this axes, shared or not) ride along too, so a value
    // pulled out of context still says what it means, not just a bare
    // number. group is the title of whichever fig.group() box this axes
    // sits in (joined with ", " if it's in more than one, empty if none),
    // so a marker from a clustered panel says which cluster it came from.
    // Any per-axes context (Axes.set_pick_context) rides along as well,
    // without clobbering a structured field of the same name (x, y,
    // kind, ...) that the picked data itself already set.
    if (rec.axes !== undefined) {
      var am = META[rec.axes];
      rec.axes_title = (am && am.title) ? am.title : ('axes ' + rec.axes);
      rec.xlabel = am ? am.xlabel : '';
      rec.ylabel = am ? am.ylabel : '';
      rec.zlabel = am ? am.zlabel : '';
      rec.group = am ? am.group : '';
      if (am && am.context) {
        for (var ck in am.context) if (!(ck in rec)) rec[ck] = am.context[ck];
      }
    }
    return rec;
  }

  // Every pin, Point Picking and Annotation alike -- this is the general
  // public query (window.plotpressGetMarkers, qt.py's LiveArtist marker
  // sync, a custom tool's own onClick logging its progress), not Extract's.
  // Extract itself is narrower -- see doExtract below.
  function getMarkers() {
    return Array.prototype.map.call(
      document.querySelectorAll('.plotpress-pin'), markerRecord);
  }
  window.plotpressGetMarkers = getMarkers;   // programmatic access

  // For a custom tool (see addTool/plotpressAddTool): the same axes-lookup
  // + pixel-to-data conversion Point Picking itself uses, minus dropping a
  // pin -- so a custom onClick can work in real data units, not just the
  // raw SVG-space point it's already handed, without reimplementing the
  // per-axes log-scale/inverted-axis-aware transform. Returns null off any
  // (pickable) axes, same as a Point Picking click there does nothing.
  window.plotpressToData = function (p) {
    var a = pickableAxesAt(p);
    if (!a) return null;
    var d = toData(a.m, p.x, p.y);
    return { axes: a.i, x: d.x, y: d.y };
  };

  // RFC 4180 field quoting -- a bare comma/quote/newline (annotation text,
  // an axes_title, a pie label, a set_pick_context() string) otherwise
  // shifts every column after it in that row.
  function csvField(v) {
    var s = v === undefined || v === null ? '' : String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function toCSV(recs) {
    if (!recs.length) return '';
    var keys = [];
    recs.forEach(function (r) {
      for (var k in r) if (keys.indexOf(k) < 0) keys.push(k);
    });
    var lines = [keys.map(csvField).join(',')];
    recs.forEach(function (r) {
      lines.push(keys.map(function (k) { return csvField(r[k]); }).join(','));
    });
    return lines.join('\n');
  }

  function download(name, text, type) {
    var blob = new Blob([text], { type: type });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 0);
  }

  function showExtractPanel(records, csv, json) {
    var old = document.querySelector('.plotpress-extract');
    if (old) old.remove();
    var panel = document.createElement('div');
    panel.className = 'plotpress-extract';
    var head = document.createElement('div');
    head.style.cssText = 'font-weight:600;margin-bottom:6px';
    head.textContent = records.length + ' marker' + (records.length === 1 ? '' : 's');
    var ta = document.createElement('textarea');
    ta.readOnly = true; ta.value = csv || '(no markers)';
    var btns = document.createElement('div');
    btns.style.cssText = 'display:flex;gap:6px;margin-top:6px;flex-wrap:wrap';
    function mk(txt, fn) {
      var b = document.createElement('button');
      b.textContent = txt; b.addEventListener('click', fn); return b;
    }
    var copy = mk('Copy CSV', function () {
      ta.select();
      var done = function () {
        copy.textContent = 'Copied!';
        setTimeout(function () { copy.textContent = 'Copy CSV'; }, 1200);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(csv).then(done, function () {
        try { document.execCommand('copy'); done(); } catch (e) {}
      });
      else { try { document.execCommand('copy'); done(); } catch (e) {} }
    });
    btns.appendChild(copy);
    btns.appendChild(mk('Download CSV', function () { download('markers.csv', csv, 'text/csv'); }));
    btns.appendChild(mk('Download JSON', function () { download('markers.json', json, 'application/json'); }));
    btns.appendChild(mk('Close', function () { panel.remove(); }));
    panel.appendChild(head); panel.appendChild(ta); panel.appendChild(btns);
    document.body.appendChild(panel);
    ta.focus(); ta.select();
  }

  // Point Picking markers only, not Annotation notes -- Extract now lives
  // solely under the Point Picking menu (see TOOLS above), so its own
  // output scopes to match; an Annotation note has nothing to "extract" in
  // the same sense a picked data value does. :not(.plotpress-note) is the
  // one line doing that filtering -- getMarkers() above (and every other
  // .plotpress-pin selector in this file that isn't already kind-specific,
  // like drag-ready and clearAllPins) deliberately still covers both kinds.
  function doExtract() {
    var records = Array.prototype.map.call(
      document.querySelectorAll('.plotpress-pin:not(.plotpress-note)'), markerRecord);
    // Hand off to Python when running inside the native (pywebview) window.
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.extract) {
        window.pywebview.api.extract(records);
      }
    } catch (e) {}
    // In wait-for-extract mode the kernel closes the window on receipt, so skip
    // the panel; otherwise show it for copy/download.
    if (!window.PLOTPRESS_WAIT_EXTRACT) {
      showExtractPanel(records, toCSV(records), JSON.stringify(records, null, 2));
    }
  }
  window.plotpressExtract = doExtract;

  // ---- save/save as: persist the current pan/zoom, pins, and toggles ----
  // A plain data-only re-serve (Extract) is not "resume where I left off" --
  // this rebuilds the whole page instead, from the same clean pre-mutation
  // snapshot (ORIGINAL_DOC_HTML) every save starts from, plus one new
  // payload script tag the bootstrap below reads back on the saved file's
  // own next load.
  function serializePins() {
    var out = [];
    document.querySelectorAll('.plotpress-pin').forEach(function (pin) {
      var d = {};
      for (var k in pin.dataset) d[k] = pin.dataset[k];
      out.push({
        data: d, note: pin.classList.contains('plotpress-note'),
        selected: pin === selectedPin,
        text: pin.querySelector('text').textContent,
      });
    });
    return out;
  }

  // Rebuilds each pin the same way it was first created: an anchored pin
  // (data.kind set -- Point Picking today, or a legacy Annotate Point pin
  // restored from a page saved before that mode was removed) through
  // addAnchoredPin(),
  // which re-resolves its position from the *current* (already-restored)
  // view via pinAnchor()/resolve() exactly as a fresh click would; a free
  // annotation or the large-series geometry fallback (no data.kind) directly,
  // converting its own saved data-space x/y through the current view when it
  // has one, or at its saved fixed figure position when it doesn't.
  function restorePins(saved) {
    var toSelect = null;
    saved.forEach(function (rec) {
      var g;
      if (rec.data.kind) {
        var scratch = document.createElementNS(SVGNS, 'g');
        for (var k in rec.data) scratch.dataset[k] = rec.data[k];
        var anchor = pinAnchor(scratch);
        if (!anchor) return;
        g = addAnchoredPin(anchor, +rec.data.index, rec.data.customLabel);
        // addAnchoredPin() only copies the specific fields it knows about
        // onto the fresh pin it creates -- a dragged box's own offset (see
        // startBoxDrag) isn't one of them, so it's carried over here
        // explicitly, the same as the free-note branch's full dataset copy
        // below already does for its own pins.
        if (g && rec.data.boxDx !== undefined) {
          g.dataset.boxDx = rec.data.boxDx; g.dataset.boxDy = rec.data.boxDy;
        }
      } else {
        var px, py;
        if (rec.data.axes !== undefined && CUR[rec.data.axes]) {
          var q = toPixel(CUR[rec.data.axes], +rec.data.x, +rec.data.y);
          px = q.x; py = q.y;
        } else {
          px = +rec.data.px; py = +rec.data.py;
        }
        g = addPin(px, py, rec.text, rec.data.axes);
        for (var k2 in rec.data) g.dataset[k2] = rec.data[k2];
      }
      if (!g) return;
      if (rec.note) g.classList.add('plotpress-note');
      if (rec.selected) toSelect = g;
      // Both branches above set g.dataset.boxDx *after* addPin()'s own
      // initial layoutPin() call already ran (with the default offset,
      // since the dataset didn't have it yet at that point) -- applying a
      // restored custom offset needs one more explicit re-layout.
      if (g.dataset.boxDx !== undefined) {
        layoutPin(g, +g.dataset.anchorX, +g.dataset.anchorY, g.querySelector('text').textContent);
      }
    });
    selectPin(toSelect);
    refreshDragReady();
  }

  function buildSaveState() {
    var axesView = {};
    Object.keys(CUR).forEach(function (k) {
      var c = CUR[k];
      axesView[k] = { xmin: c.xmin, xmax: c.xmax, ymin: c.ymin, ymax: c.ymax };
    });
    var hiddenLabels = [];
    document.querySelectorAll('.plotpress-series').forEach(function (s) {
      if (s.style.display !== 'none') return;
      var label = s.getAttribute('data-label');
      if (hiddenLabels.indexOf(label) < 0) hiddenLabels.push(label);
    });
    return {
      zoomScale: zoomScale, scrollX: window.scrollX, scrollY: window.scrollY,
      axes: axesView, pins: serializePins(),
      pointsHidden: pointsHidden, annotationsHidden: annotationsHidden,
      hiddenLegendLabels: hiddenLabels,
    };
  }

  function applySavedState(state) {
    if (!state) return;
    // Zoom before scroll: scrolling to a saved position only lands right if
    // the page is already the size that position was saved from.
    if (state.zoomScale) { zoomScale = state.zoomScale; applyZoomSize(); }
    if (state.scrollX !== undefined) window.scrollTo(state.scrollX, state.scrollY);
    if (state.axes) {
      Object.keys(state.axes).forEach(function (k) {
        if (!CUR[k]) return;
        var a = state.axes[k], c = CUR[k];
        c.xmin = a.xmin; c.xmax = a.xmax; c.ymin = a.ymin; c.ymax = a.ymax;
        refreshAxes(k);
      });
    }
    if (state.pointsHidden) {
      var pointsBtn = buttons.filter(function (b) {
        return b.textContent === 'Hide Points' || b.textContent === 'Show Points';
      })[0];
      if (pointsBtn) togglePointsHidden(pointsBtn);
    }
    if (state.annotationsHidden) {
      var annotBtn = buttons.filter(function (b) {
        return b.textContent === 'Hide Annotations' || b.textContent === 'Show Annotations';
      })[0];
      if (annotBtn) toggleAnnotationsHidden(annotBtn);
    }
    (state.hiddenLegendLabels || []).forEach(function (label) {
      document.querySelectorAll('.plotpress-legend text').forEach(function (t) {
        if (t.textContent === label) t.style.opacity = '0.4';
      });
      document.querySelectorAll('.plotpress-series').forEach(function (s) {
        if (s.getAttribute('data-label') === label) s.style.display = 'none';
      });
    });
    if (state.pins) restorePins(state.pins);   // last: needs the view above already in place
  }

  function buildSaveHTML() {
    // A stale payload from an earlier save has to come out through a real
    // DOM (DOMParser), not a raw string/regex replace against
    // ORIGINAL_DOC_HTML: that string is the *whole* page, which includes
    // this very script's own source -- and this function's source text
    // necessarily spells out id="plotpress-saved-state" itself (to build
    // and to look for that same tag). A regex scanning raw text can't tell
    // that occurrence apart from a genuine tag and matches from there
    // instead, non-greedily eating everything up to the real </script> that
    // ends the whole interactive script -- silently truncating every saved
    // copy's own toolbar script mid-function. A parsed DOM has no such
    // ambiguity: getElementById only ever matches a real element, never
    // text sitting inside another element's own content.
    var doc = new DOMParser().parseFromString(ORIGINAL_DOC_HTML, 'text/html');
    var stale = doc.getElementById('plotpress-saved-state');
    if (stale) stale.remove();
    var script = doc.createElement('script');
    script.type = 'application/json';
    script.id = 'plotpress-saved-state';
    // Escaped the same way figure._json_payload() escapes every other
    // embedded payload: raw text elements serialize verbatim, so a saved
    // annotation whose text happened to contain "</script>" would otherwise
    // round-trip into literally invalid, unparseable markup.
    script.textContent = JSON.stringify(buildSaveState())
      .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');
    // As the *first* child of body, not appended at the end: the toolbar
    // script that reads this back runs synchronously the moment the parser
    // reaches its own closing tag, before it has seen any later sibling --
    // appended after it, this element would not exist in the DOM yet at the
    // point document.getElementById('plotpress-saved-state') looks for it.
    doc.body.insertBefore(script, doc.body.firstChild);
    return '<!doctype html>' + doc.documentElement.outerHTML;
  }

  function suggestedFilename() {
    var t = (document.title || 'plotpress-figure').replace(/[^\w.-]+/g, '_').toLowerCase();
    return /\.html?$/.test(t) ? t : t + '.html';
  }

  function downloadHTML(htmlText, filename) {
    var blob = new Blob([htmlText], { type: 'text/html' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  // Both Save and Save As need a way to let the user choose where the file
  // goes and what it's called -- the File System Access API's picker
  // (Chromium, a secure context only) is the only thing in a browser that
  // can show that dialog at all; a plain download never does; the browser's
  // own "always ask where to save" setting is outside the page's control
  // either way. A page can also never be handed a writable handle to the
  // exact file it was itself opened from (file:// has no such API), so even
  // Save's "overwrite in place" is really "pick a destination, defaulting to
  // this file's own name" rather than a silent, prompt-free write. Anywhere
  // the picker API is unavailable (Firefox, Safari, a non-secure origin),
  // both fall back to the same plain download -- always a new file there,
  // with no dialog, since nothing in the page can produce one.
  function saveViaPicker(htmlText) {
    if (!window.showSaveFilePicker) { downloadHTML(htmlText, suggestedFilename()); return; }
    window.showSaveFilePicker({
      suggestedName: suggestedFilename(),
      types: [{ description: 'HTML', accept: { 'text/html': ['.html'] } }],
    }).then(function (handle) {
      return handle.createWritable().then(function (w) {
        return w.write(htmlText).then(function () { return w.close(); });
      });
    }).catch(function (err) {
      if (err && err.name === 'AbortError') return;   // user cancelled the picker
      downloadHTML(htmlText, suggestedFilename());
    });
  }

  function saveAsNewPage() {
    saveViaPicker(buildSaveHTML());
  }

  function overwriteCurrentPage() {
    saveViaPicker(buildSaveHTML());
  }

  // Nearest vertex of an animated (frame) series at its current frame.
  function nearestFrameVertex(axesKey, m, p) {
    if (!FRAMES || !FRAMES[axesKey]) return null;
    var best = null;
    FRAMES[axesKey].forEach(function (e) {
      if (!e.Y) return;   // a frame-mesh entry, not a frame-line one -- see meshFrameAt()
      var f = CURRENT_FRAME[e.unit] || 0;
      var xs = e.shared_x ? e.x : e.x[f], ys = e.Y[f];
      for (var j = 0; j < ys.length; j++) {
        var q = toPixel(m, xs[j], ys[j]);
        var d = (q.x - p.x) * (q.x - p.x) + (q.y - p.y) * (q.y - p.y);
        if (!best || d < best.d) {
          best = { d: d, ref: { kind: 'frame', id: e.id, unit: e.unit, index: j } };
        }
      }
    });
    return best;
  }

  // The same target Point Picking resolves a click to (a point/frame vertex
  // within POINT_THRESHOLD px, else a mesh cell, else a pie wedge, else a
  // point regardless of distance) -- kept as its own function for the
  // pick-mode click handler's own readability (it used to also serve the
  // now-removed "Annotate Point" mode, a second caller wanting the exact
  // same resolution logic). Returns
  // a steppable anchor ref; ``null`` if there's simply nothing pickable
  // there (the caller may fall back to a geometric readout); or the string
  // ``'blocked'`` for the one case that must produce nothing at all, not a
  // fallback -- a pie axes only has its wedges to pick, so a click that
  // misses every one of them is a genuine miss, not "no data nearby".
  function resolvePickTarget(e) {
    var p = toUser(e), a = pickableAxesAt(p);
    if (!a) return null;
    var m = a.m;
    var np = nearestPoint(a.i, m, p);
    var fp = nearestFrameVertex(a.i, m, p);
    var d = toData(m, p.x, p.y);
    var mesh = meshAt(a.i, d.x, d.y, p) || meshFrameAt(a.i, d.x, d.y, p);
    var pieHit = pieAt(a.i, p);

    var cand = null;
    if (np) cand = { d: np.d, ref: np.ref };
    if (fp && (!cand || fp.d < cand.d)) cand = { d: fp.d, ref: fp.ref };

    var pd = PICK[a.i];
    if (pd && pd.pies && pd.pies.length && !pieHit && !mesh &&
        (!cand || Math.sqrt(cand.d) > POINT_THRESHOLD)) {
      return 'blocked';
    }
    if (cand && Math.sqrt(cand.d) <= POINT_THRESHOLD) return cand.ref;
    if (mesh) return mesh;
    if (pieHit) return pieHit;
    if (cand) return cand.ref;
    return null;
  }

  // Annotation (internal mode note-free): drop a note anywhere on the whole
  // figure, including the margins or the gap between subplots -- not locked
  // to any datum. Inside an axes it still tracks that axes' data coordinate
  // (so it pans/zooms with the plot it was drawn over); outside any axes
  // there is no data coordinate, so it just stays put at its figure pixel
  // position, which nothing in the interactive view moves. A separate
  // snap-to-nearest-datum variant ("Annotate Point") existed briefly here
  // and was removed -- Point Picking already covers snapping to a datum.
  function addFreeNote(e) {
    var p = toUser(e);
    // A cross-origin-equivalent embedding (an <iframe srcdoc=...>, as
    // Report.save() uses for every entry) has its own opaque origin, and
    // browsers silently block alert/confirm/prompt from such a frame --
    // window.prompt() there can either return null (treated as "cancelled"
    // below, same as a real one) or throw outright, depending on browser.
    // Catching it keeps the latter from surfacing as an uncaught error on
    // every click while this mode is active -- console.warn (once, not per
    // click) gives a developer debugging "Annotation does nothing here" an
    // actual lead, since the click itself otherwise looks identical to a
    // user simply cancelling the prompt.
    var text;
    try { text = window.prompt('Annotation text:'); }
    catch (err) {
      if (!addFreeNote._warned) {
        addFreeNote._warned = true;
        console.warn('plotpress: window.prompt() is blocked in this frame '
          + '(a cross-origin-equivalent embedding, e.g. Report.save()\'s '
          + '<iframe srcdoc>) -- the Annotation tool cannot ask for text '
          + 'here and will do nothing when clicked.');
      }
      return;
    }
    if (!text) return;
    var a = axesAt(p);
    var g = addPin(p.x, p.y, text, a ? a.i : undefined);
    g.classList.add('plotpress-note');
    g.dataset.annotation = '1';
    if (a) {
      var d = toData(a.m, p.x, p.y);
      g.dataset.x = d.x; g.dataset.y = d.y; g.dataset.axes = a.i;
    } else {
      g.dataset.px = p.x; g.dataset.py = p.y;
    }
    // addPin() already refreshed drag-readiness once, before the
    // .plotpress-note class above was applied -- see the same note in
    // addAnchoredPin().
    refreshOneDragReady(g);
  }

  svg.addEventListener('click', function (e) {
    if (moved) return;
    if (e.target.closest('.plotpress-legend') || e.target.closest('.plotpress-pin')) return;
    if (mode === 'note-free') { addFreeNote(e); return; }
    if (mode === 'pick') {
      var ref = resolvePickTarget(e);
      if (ref === 'blocked') return;
      if (ref) { addAnchoredPin(ref, ref.index); return; }
      var p = toUser(e), a = pickableAxesAt(p);
      if (!a) return;
      var v = nearestVertex(a.i, p) || p;              // large-series fallback
      var dd = toData(a.m, v.x, v.y);
      var g = addPin(v.x, v.y, 'x=' + fmt(dd.x) + ', y=' + fmt(dd.y), a.i);
      g.dataset.x = dd.x; g.dataset.y = dd.y; g.dataset.axes = a.i;
      return;
    }
    // A custom tool's own mode (see addTool/plotpressAddTool) -- every
    // built-in click-driven mode above has already had first refusal, so
    // this only ever fires for a mode this build doesn't know about itself.
    var custom = mode && CUSTOM_MODES[mode];
    if (custom && custom.onClick) custom.onClick(e, toUser(e));
  });

  // ---- slider(s) over extra data dimensions -----------------------------
  // Each "unit" is one control bar. The global unit ("main") is a single bar
  // driving all shared series; a docked unit sits under its axes. Docked units
  // that share a connection index show an index badge + a checkbox to link them
  // so they scrub together on demand.
  var framesEl = document.getElementById('plotpress-frames');
  var unitsEl = document.getElementById('plotpress-sliders');
  var FRAMES = framesEl ? reviveBinary(JSON.parse(framesEl.textContent)) : null;
  var UNITS = unitsEl ? JSON.parse(unitsEl.textContent) : null;
  var LINKS = {};  // connection index -> [slider api]
  if (FRAMES) {
    for (var fk in FRAMES) {
      FRAMES[fk].forEach(function (e) { FRAME_INDEX[e.id] = { entry: e, axesKey: fk }; });
    }
  }

  // Move any pins attached to this unit's series to the new frame's vertex.
  function updateFramePins(unit, f) {
    var pins = document.querySelectorAll('.plotpress-pin[data-frame-unit="' + unit + '"]');
    for (var i = 0; i < pins.length; i++) {
      var pin = pins[i];
      var a = resolve(pinAnchor(pin), +pin.dataset.index);  // uses current frame
      // pinLabel(), not a.label directly -- an Annotate Point note's
      // customLabel has to survive a frame-slider scrub the same way it
      // already survives pan/zoom (relayoutPins) and arrow-key stepping
      // (stepPin), or scrubbing silently stomps the user's text back to the
      // auto-generated readout.
      if (a) layoutPin(pin, a.px, a.py, pinLabel(pin, a.label));
    }
  }

  function drawFrame(unit, f) {
    if (!FRAMES) return;
    for (var key in FRAMES) {
      var m = CUR[key];
      if (!m) continue;
      FRAMES[key].forEach(function (e) {
        if (e.unit !== unit) return;
        var el = document.getElementById(e.id);
        if (!el) return;
        if (e.hrefs) {
          // A mesh: every frame shares one X/Y grid, so only the pixel
          // content changes -- swap the image, not its position.
          el.setAttribute('href', e.hrefs[f]);
          return;
        }
        var xs = e.shared_x ? e.x : e.x[f];
        var ys = e.Y[f], d = '';
        for (var j = 0; j < ys.length; j++) {
          var q = toPixel(m, xs[j], ys[j]);
          d += (j === 0 ? 'M' : 'L') + q.x.toFixed(2) + ',' + q.y.toFixed(2);
        }
        el.setAttribute('d', d);
      });
    }
    updateFramePins(unit, f);
  }

  function buildSlider(unit, spec, opts) {
    var box = document.createElement('div');
    box.className = 'plotpress-slider';
    var api = { index: spec.index, checkbox: null, external: null, frame: 0 };

    // Index badge + link checkbox (only when this index is shared by 2+ units).
    if (opts.showLink) {
      var link = document.createElement('label');
      link.className = 'link';
      link.title = 'link all "' + spec.index + '" sliders to scrub together';
      api.checkbox = document.createElement('input');
      api.checkbox.type = 'checkbox';
      var idx = document.createElement('span');
      idx.className = 'idx'; idx.textContent = spec.index;
      link.appendChild(api.checkbox); link.appendChild(idx);
      box.appendChild(link);
    }

    var input = document.createElement('input');
    input.type = 'range'; input.min = 0; input.max = spec.n - 1;
    input.step = 1; input.value = 0;
    if (opts.inputWidth) input.style.width = opts.inputWidth + 'px';
    var val = document.createElement('span'); val.className = 'val';

    var timer = null;
    var applyFrame = function (f) {
      api.frame = (f % spec.n + spec.n) % spec.n;
      CURRENT_FRAME[unit] = api.frame;
      input.value = api.frame;
      drawFrame(unit, api.frame);
      val.textContent = spec.label + ' = ' + fmt(spec.values[api.frame]);
    };
    api.external = applyFrame;  // set from a linked peer, no re-propagation
    var setFrame = function (f) {
      applyFrame(f);
      if (api.checkbox && api.checkbox.checked) {
        (LINKS[spec.index] || []).forEach(function (o) {
          if (o !== api && o.checkbox && o.checkbox.checked) o.external(api.frame);
        });
      }
    };

    var sbtn = function (txt, title) {
      var b = document.createElement('button');
      b.textContent = txt; b.title = title;
      return b;
    };
    var back = sbtn('⏮', 'step back');
    var playBtn = sbtn('▶', 'play');
    var fwd = sbtn('⏭', 'step forward');
    var pause = function () {
      if (timer) { clearInterval(timer); timer = null; }
      playBtn.textContent = '▶'; playBtn.title = 'play';
    };
    var play = function () {
      if (timer) return;
      playBtn.textContent = '⏸'; playBtn.title = 'pause';
      timer = setInterval(function () { setFrame(api.frame + 1); }, 80);
    };
    back.addEventListener('click', function () { pause(); setFrame(api.frame - 1); });
    fwd.addEventListener('click', function () { pause(); setFrame(api.frame + 1); });
    playBtn.addEventListener('click', function () { timer ? pause() : play(); });
    input.addEventListener('input', function () { pause(); setFrame(+input.value); });

    // When linking is switched on, snap to an already-linked peer's frame.
    if (api.checkbox) {
      api.checkbox.addEventListener('change', function () {
        if (!api.checkbox.checked) return;
        var peer = (LINKS[spec.index] || []).find(function (o) {
          return o !== api && o.checkbox && o.checkbox.checked;
        });
        if (peer) setFrame(peer.frame);
      });
      (LINKS[spec.index] = LINKS[spec.index] || []).push(api);
    }

    box.appendChild(back); box.appendChild(playBtn); box.appendChild(fwd);
    box.appendChild(input); box.appendChild(val);
    return { box: box, setFrame: setFrame };
  }

  if (UNITS && FRAMES) {
    // Wrap the SVG so docked sliders can be positioned over it. Sized by the
    // .plotpress-svg-wrap rule in the page's own <style> (see Figure.to_html),
    // not inline here -- standalone shrink-wraps it to the SVG's natural size
    // for flex-centering; embedded (standalone=False) stretches it to the
    // container's width so #plotpress-svg's own width:100% has a definite,
    // non-circular size to resolve against instead of falling back to the
    // SVG's fixed width/height attributes.
    wrap = document.createElement('div');
    wrap.className = 'plotpress-svg-wrap';
    svg.parentNode.insertBefore(wrap, svg);
    wrap.appendChild(svg);

    // How many units share each connection index (>=2 => offer linking).
    var indexCount = {};
    Object.keys(UNITS).forEach(function (u) {
      var ix = UNITS[u].index;
      if (ix != null) indexCount[ix] = (indexCount[ix] || 0) + 1;
    });

    var globalBar = null;
    var order = Object.keys(UNITS).sort(function (a, b) {
      if (a === 'main') return -1;
      if (b === 'main') return 1;
      return a < b ? -1 : 1;
    });
    order.forEach(function (u) {
      var spec = UNITS[u];
      if (spec.global) {
        if (!globalBar) {
          globalBar = document.createElement('div');
          globalBar.className = 'plotpress-sliders';
          document.body.appendChild(globalBar);
        }
        var g = buildSlider(u, spec, { inputWidth: 240, showLink: false });
        globalBar.appendChild(g.box); g.setFrame(0);
      } else {
        var m = META[spec.axes] || { x: 0, y: 0, w: home[2], h: home[3] };
        var showLink = indexCount[spec.index] >= 2;
        var iw = Math.max(80, Math.min(240, m.w - (showLink ? 210 : 175)));
        var r = buildSlider(u, spec, { inputWidth: iw, showLink: showLink });
        r.box.style.position = 'absolute';
        r.box.style.whiteSpace = 'nowrap';
        wrap.appendChild(r.box);
        dockedSliders.push({ box: r.box, axesKey: spec.axes });
        r.setFrame(0);
      }
    });
    positionDocked();
    window.addEventListener('resize', positionDocked);
  }

  // Three flavors, all deselecting selectedPin only when it's actually one
  // of the pins being removed -- clearing points shouldn't drop the user's
  // in-progress arrow-key selection of an annotation they were just
  // stepping through, and vice versa. .plotpress-note is the same class
  // addFreeNote() (Annotation mode) tags every note with -- see the TOOLS
  // comment above for why that's the reliable point/annotation split, not
  // e.g. a pin's `kind`.
  function isAnnotationPin(p) { return p.classList.contains('plotpress-note'); }

  function clearPointPins() {
    document.querySelectorAll('.plotpress-pin').forEach(function (p) {
      if (!isAnnotationPin(p)) p.remove();
    });
    if (selectedPin && !isAnnotationPin(selectedPin)) selectedPin = null;
  }

  function clearAnnotationPins() {
    document.querySelectorAll('.plotpress-pin').forEach(function (p) {
      if (isAnnotationPin(p)) p.remove();
    });
    if (selectedPin && isAnnotationPin(selectedPin)) selectedPin = null;
  }

  // Escape's own "clear everything" -- the one place that still removes
  // every pin/annotation in one shot, now that Clear Points/Clear
  // Annotations are each scoped to just one kind. Composed from those two
  // rather than a third independent removal loop: every .plotpress-pin is
  // either an annotation or not, so the pair together is exhaustive, and
  // selectedPin ends up null either way (whichever of the two actually
  // held it clears it -- the other is a no-op against an already-cleared
  // selectedPin).
  function clearAllPins() {
    clearPointPins();
    clearAnnotationPins();
  }

  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      // An open menu eats Escape first -- closing it, the way any dropdown
      // would, rather than falling through to clearAllPins()/setMode(null)
      // underneath: a user pressing Escape just to dismiss a menu they
      // opened to look around must never silently lose every
      // pin/annotation (or the tool they had selected) as a side effect of
      // that.
      if (menuNodes.some(function (m) { return m.classList.contains('open'); })) {
        closeAllMenus();
      } else {
        // Also deselects the active tool (if any), not just clearAllPins()
        // -- the only way back to "no tool active" for a keyboard-only
        // user, who has no double-click to deselect with (see
        // attachModeButton above: a keyboard-triggered click can't be told
        // apart from a mouse single-click, so it always selects, never
        // deselects).
        clearAllPins();
        setMode(null);
      }
      return;
    }
    if (!selectedPin) return;
    var dir = e.key === 'ArrowRight' ? 'right' : e.key === 'ArrowLeft' ? 'left' :
              e.key === 'ArrowUp' ? 'up' : e.key === 'ArrowDown' ? 'down' : null;
    if (dir) { e.preventDefault(); stepPin(selectedPin, dir); }
  });

  // Applied last: replays a Save/Save As from an earlier session (view,
  // pins, toggles) now that every function/data structure above exists to
  // do it with -- see buildSaveState()/applySavedState() above.
  var savedStateEl = document.getElementById('plotpress-saved-state');
  if (savedStateEl) applySavedState(JSON.parse(savedStateEl.textContent));
})();
"""


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
