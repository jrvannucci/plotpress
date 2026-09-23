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
    // box-sizing so fitDropdown's max-height bounds the whole box: with the
    // default content-box it bounded the item list alone, and the 5px padding
    // plus 1px border still pushed the menu past the viewport edge.
    '.plotpress-menu-dropdown{position:absolute;top:calc(100% + 5px);' +
    'left:0;min-width:170px;background:#fff;border:1px solid #b8b8b8;' +
    'border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.16);padding:5px;' +
    'box-sizing:border-box;' +
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
    '.plotpress-menu-heading{font:600 11px system-ui,sans-serif;color:#6b7280;' +
    'padding:4px 10px 2px}' +
    '.plotpress-menu-note{font:11px system-ui,sans-serif;color:#6b7280;' +
    'padding:0 10px 4px;max-width:210px}' +
    '.plotpress-mode-indicator{display:flex;align-items:center;gap:6px;' +
    'margin-left:auto;padding:4px 10px 4px 8px;background:#eef2ff;' +
    'border-radius:999px;font:500 11px system-ui,sans-serif;color:#2b5bd7;' +
    'white-space:nowrap}' +
    '.plotpress-mode-dot{width:6px;height:6px;border-radius:50%;' +
    'background:#2b6cff;flex:none}' +
    // overflow-y on the bar itself, with the height bound set by
    // reflowGlobalBars: "Link all matching axes" makes one global
    // slider per compatible group, so a figure whose meshes come in
    // many different grid shapes gets many of them stacked here. Fixed
    // to the bottom with nothing bounding the column, the stack simply
    // grew off the top of the window -- 24 groups made a 1319px bar in
    // a 900px viewport and put eight sliders somewhere no one could
    // reach, since a fixed element does not scroll with the page.
    '.plotpress-sliders{position:fixed;bottom:12px;left:50%;' +
    'transform:translateX(-50%);display:flex;flex-direction:column;' +
    'gap:6px;z-index:1000;overflow-y:auto;overscroll-behavior:contain}' +
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
    // Slice's own menu controls -- a radio pair plus two checkboxes -- are
    // plain <label>s, not .plotpress-toolbar <button>s, so they need their
    // own (much smaller) padding/hover rule instead of inheriting one.
    '.plotpress-menu-dropdown label{display:flex;align-items:center;' +
    'gap:6px;padding:5px 9px;border-radius:5px;font:12px system-ui,' +
    'sans-serif;color:#222;cursor:pointer;white-space:nowrap}' +
    '.plotpress-menu-dropdown label:hover{background:#f1f1f1}' +
    '.plotpress-slice-orient{display:flex;flex-direction:column}' +
    '.plotpress-slice-custom-range{display:flex;gap:6px;padding:3px 9px 5px 27px}' +
    '.plotpress-slice-custom-range input{width:64px;font:12px system-ui,' +
    'sans-serif;padding:3px 5px;border:1px solid #ccc;border-radius:4px}' +
    '.plotpress-slice-custom-range input:disabled{background:#f3f3f3;color:#999}' +
    // Drawn on the outer (untransformed) <svg>, not inside any axes' own
    // g#zoom{key} -- see drawCursor()/renderSliceAxes()'s own comments for
    // why -- so neither needs vector-effect:non-scaling-stroke the way
    // .plotpress-zoom content does; their stroke-width is recomputed in JS
    // for the current zoom instead (matches .plotpress-rubber).
    '.plotpress-slice-cursor{pointer-events:none}' +
    '.plotpress-slice-line{pointer-events:none}' +
    '.plotpress-slice-ticks text{fill:#444;font:9px system-ui,sans-serif}' +
    '.plotpress-pin.selected circle{fill:#2b8cff}' +   /* r itself: selectPin(), scaled per-pin */
    '.plotpress-pin.plotpress-note rect{fill:#b45309}' +   /* user notes: amber */
    // Hide Points/Hide Annotations toggle independently -- one class per
    // kind, keyed the same way Clear Points/Clear Annotations and
    // isAnnotationPin() already split .plotpress-pin by .plotpress-note.
    // Slice hides a mesh through this class, never through the element's
    // own style.display -- that one already belongs to the legend's
    // click-to-hide toggle, and whichever of the two wrote last simply
    // undid the other (a slider step brought back a mesh the legend had
    // hidden). With the two on separate channels, a mesh stays hidden
    // while *either* wants it hidden, which is what both actually mean.
    '.plotpress-slice-hidden{display:none}' +
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
  // Keep an open dropdown inside the viewport. A figure embedded in a page
  // (a Report panel, a docs gallery iframe) gets whatever height the host
  // gave it, which can be barely taller than the figure itself -- and the
  // Slice menu is the tallest of them. Absolutely positioned at
  // top:100% with nothing bounding it, the bottom of the list simply fell
  // outside the document: not scrolled off, *clipped away*, since an iframe
  // has no viewport of its own to scroll and the items were unreachable.
  // So it is measured on open and given a real max-height, scrolling
  // internally when that is all the room there is -- and flipped above the
  // button instead when that side has meaningfully more space. The same
  // clamp keeps a menu near the right edge from running off the side.
  function fitDropdown(btn, dropdown) {
    dropdown.style.maxHeight = '';
    dropdown.style.overflowY = '';
    dropdown.style.top = '';
    dropdown.style.bottom = '';
    dropdown.style.left = '';
    var GAP = 5, MARGIN = 4;
    var b = btn.getBoundingClientRect();
    var vh = document.documentElement.clientHeight;
    var vw = document.documentElement.clientWidth;
    var below = vh - b.bottom - GAP - MARGIN, above = b.top - GAP - MARGIN;
    var needed = dropdown.scrollHeight;
    // Flip up only when below genuinely cannot hold it and above is roomier;
    // otherwise stay put, so a menu doesn't jump sides for a few pixels.
    if (needed > below && above > below) {
      dropdown.style.top = 'auto';
      dropdown.style.bottom = 'calc(100% + ' + GAP + 'px)';
      if (needed > above) {
        dropdown.style.maxHeight = Math.max(80, above) + 'px';
        dropdown.style.overflowY = 'auto';
      }
    } else if (needed > below) {
      dropdown.style.maxHeight = Math.max(80, below) + 'px';
      dropdown.style.overflowY = 'auto';
    }
    // Horizontal: nudge left so the right edge stays on screen.
    var d = dropdown.getBoundingClientRect();
    var overflowRight = d.right - (vw - MARGIN);
    if (overflowRight > 0) {
      dropdown.style.left = Math.round(-Math.min(overflowRight, b.left - MARGIN)) + 'px';
    }
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
      if (willOpen) { menu.classList.add('open'); fitDropdown(labelBtn, dropdown); }
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
    { action: 'fit-width', label: 'Fit Width', standalone: true },
    { mode: 'span', label: 'Axis Span', menu: 'Axes' },
    { mode: 'zoom', label: 'Axis Zoom', menu: 'Axes' },
    { action: 'reset-axes', label: 'Reset All Axes', menu: 'Axes', divider: true },
    { mode: 'pick', label: 'Point Picking', menu: 'Point Picking' },
    { action: 'toggle-points', label: 'Hide Points', menu: 'Point Picking', divider: true },
    { action: 'clear-points', label: 'Clear Points', menu: 'Point Picking', divider: true },
    { action: 'extract', label: 'Extract', menu: 'Point Picking', divider: true },
    { mode: 'note-plain', label: 'Annotate', menu: 'Annotate' },
    { mode: 'note-free', label: 'Annotate Arrow', menu: 'Annotate' },
    { mode: 'note-point', label: 'Annotate Point', menu: 'Annotate' },
    { action: 'toggle-annotations', label: 'Hide Annotations', menu: 'Annotate', divider: true },
    { action: 'clear-annotations', label: 'Clear Annotations', menu: 'Annotate', divider: true },
    { action: 'save', label: 'Save', menu: 'File' },
    { action: 'save-as', label: 'Save As', menu: 'File' },
  ];
  // Optional add-ons, opted in by name from Python (Figure.to_html's
  // options=, emitted as window.PLOTPRESS_OPTIONS). Everything in TOOLS above
  // -- navigation, Axes, Point Picking, Annotate, File -- is unconditional;
  // options only add menus beyond it. With no config at all (this JS loaded
  // some other way) every add-on is on, rather than silently omitting one.
  var OPTIONS = window.PLOTPRESS_OPTIONS || ['slice'];
  function hasOption(name) { return OPTIONS.indexOf(name) !== -1; }
  // Per-option startup settings (options={"slice": {...}} on the Python
  // side) -- the state the tool's menu would otherwise begin in.
  var OPTION_CONFIG = window.PLOTPRESS_OPTION_CONFIG || {};
  var SLICE_CFG = OPTION_CONFIG['slice'] || {};
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

  // Parsed here (rather than down by the rest of point-picking's own setup,
  // its more natural home) so the Slice menu below -- built once, alongside
  // every other menu -- already knows whether the figure has anything to
  // slice. PICK is otherwise exactly what point-picking itself reads later.
  var pickEl = document.getElementById('plotpress-pick');
  var PICK = pickEl ? reviveBinary(JSON.parse(pickEl.textContent)) : {};

  // Likewise parsed here rather than down by the rest of the frame-slider's
  // own setup (see the "slider(s) over extra data dimensions" section
  // below, its more natural home) -- an axes whose only mesh is an animated
  // pcolormesh_frames() one has no entry in PICK at all (see frame_data()),
  // so SLICE_AXES below needs FRAMES too, or it would silently offer no
  // Slice menu (or, on a figure that also has an ordinary pcolormesh, no
  // slider for that one axes) for an animated mesh with no indication why.
  var framesEl = document.getElementById('plotpress-frames');
  var unitsEl = document.getElementById('plotpress-sliders');
  var FRAMES = framesEl ? reviveBinary(JSON.parse(framesEl.textContent)) : null;
  var UNITS = unitsEl ? JSON.parse(unitsEl.textContent) : null;
  if (FRAMES) {
    for (var fk in FRAMES) {
      FRAMES[fk].forEach(function (e) { FRAME_INDEX[e.id] = { entry: e, axesKey: fk }; });
    }
  }

  // One mesh axes -> its first slice-eligible mesh: either its own index
  // into that axes' PICK[key].meshes array (a plain pcolormesh/imshow), or
  // -- when the axes has no PICK entry at all, only an animated
  // pcolormesh_frames() one -- a direct reference to its FRAMES[key] entry
  // instead (see meshEntryForAxes, which resolves that reference to
  // whichever frame is currently showing on every read, since a mesh's own
  // z data changes with the frame even though its edges/vmin/vmax don't). A
  // curvilinear mesh has no single well-defined row/column to slice (see
  // QuadMesh.curvilinear), so it's excluded here rather than partway into a
  // drag. "pcolormesh"/"image" (see svg.py's pick_data()) share one entry
  // shape (z/xedges/yedges), so both slice identically -- Slice doesn't
  // otherwise care which produced the data.
  // An inset axes is left out: it's a small overlay on another axes, not a
  // heatmap to scrub, and a cursor/slider on it would sit on top of its parent's.
  var isInsetAxes = function (k) { return !!META[k] && META[k].inset_of != null; };
  var SLICE_AXES = {};
  for (var sliceKey in PICK) {
    if (isInsetAxes(sliceKey)) continue;
    var sliceMeshes = (PICK[sliceKey] && PICK[sliceKey].meshes) || [];
    for (var smi = 0; smi < sliceMeshes.length; smi++) {
      var sme = sliceMeshes[smi];
      if ((sme.kind === 'pcolormesh' || sme.kind === 'image') && !sme.curvilinear) {
        SLICE_AXES[sliceKey] = { meshIndex: smi };
        break;
      }
    }
  }
  if (FRAMES) {
    for (var frameSliceKey in FRAMES) {
      if (SLICE_AXES[frameSliceKey] || isInsetAxes(frameSliceKey)) continue;   // already has a static mesh / an inset
      var frameEntries = FRAMES[frameSliceKey];
      for (var fei = 0; fei < frameEntries.length; fei++) {
        var fe = frameEntries[fei];
        // A FrameLine2D entry has no "kind" at all (see frame_data()) --
        // only a FrameQuadMesh's does -- so this can't mistake one for a
        // slice-eligible mesh.
        if (fe.kind === 'pcolormesh' && !fe.curvilinear) {
          SLICE_AXES[frameSliceKey] = { frameEntry: fe };
          break;
        }
      }
    }
  }
  var sliceMenuNeeded = hasOption('slice') && Object.keys(SLICE_AXES).length > 0;
  // Figure-wide Slice state, declared here (not down by the rest of the
  // tool's own implementation) so the menu-building code just below --
  // which reads SLICE_ORIENTATION to set the radios' initial checked state
  // -- sees the real value, not undefined from an as-yet-unassigned hoisted
  // var. 'x' = a horizontal cursor at a fixed Y, slicing one *row* (values
  // vs. X); 'y' = a vertical cursor at a fixed X, slicing one *column*
  // (values vs. Y) -- matching the menu's own "Slice X (horizontal
  // cursor)"/"Slice Y (vertical cursor)" labels. SLICE_STATE is per mesh
  // axes; the rest are figure-wide.
  // Off by default -- Slice is otherwise the only tool in this toolbar
  // that puts something on screen (docked sliders, a cursor line) without
  // the caller asking for it first; every other tool (Point Picking,
  // Annotate, ...) stays completely inert until its own mode is selected.
  // The Slice *menu* still always exists whenever there's a mesh to slice
  // (sliceMenuNeeded), so it's always reachable, but nothing about the
  // figure changes until this is checked -- unchecking it later tears
  // everything back down to a plain, unmodified pcolormesh.
  var SLICE_ENABLED = SLICE_CFG.enabled === true;
  var SLICE_ORIENTATION = SLICE_CFG.orientation === 'y' ? 'y' : 'x';
  // How a mesh's slice is shown -- 'cursor': the heatmap with just a dashed
  // cursor on the slice; 'companion': the profile in a strip carved out of
  // the mesh's own axes, beside the heatmap (see ensureCompanionLayout());
  // 'replace': the profile drawn in the heatmap's place. One choice, so
  // the two flags below can never both be set.
  var SLICE_VIEW = (SLICE_CFG.view === 'cursor' || SLICE_CFG.view === 'replace')
                   ? SLICE_CFG.view : 'companion';
  var SLICE_VIEW_ON = SLICE_VIEW === 'replace';
  var SLICE_COMPANION_ON = SLICE_VIEW === 'companion';
  var SLICE_SNAP = SLICE_CFG.snap_pins === true;   // see syncSnappedPins()
  // Light gridlines on the profile (the strip or the replace view): at the value
  // ticks, and at the spatial ticks the heatmap's own axis carries. On unless
  // switched off, since the strip has always drawn its value guides.
  var SLICE_GRID = SLICE_CFG.grid !== false;
  // Which axes get sliced: every slice-eligible mesh ('all'), or only the ones
  // the user chose ('selected') -- picked by clicking axes on the figure
  // (mode 'slice-select', see toggleSliceAxis) or given up front by the
  // caller's `axes` setting. Axes outside the scope are left as plain
  // heatmaps: no slider, cursor or strip, and not part of any link group.
  var SLICE_SCOPE = Array.isArray(SLICE_CFG.axes) ? 'selected' : 'all';
  var SLICE_SELECTED = {};   // axes key -> true
  // Set by the menu code below; declared here, before it, because a `var x = null`
  // further down the file would run *after* that assignment and wipe it.
  var scopeStatusEl = null;
  if (Array.isArray(SLICE_CFG.axes)) {
    SLICE_CFG.axes.forEach(function (k) { SLICE_SELECTED[String(k)] = true; });
  }
  // isFiniteNum, not the bare isFinite: isFinite(null) is true and +null is 0,
  // so a null in the config read as a real number and gave, for instance, a
  // zero-height companion strip. Figure.to_html()'s own validation rejects one
  // before it can get here, but a saved page edited by hand has no such gate.
  var SLICE_COMPANION_FRAC = isFiniteNum(SLICE_CFG.panel_size) ? +SLICE_CFG.panel_size : 0.3;
  // Off (default): every axes gets its own docked slider; a compatible
  // group of 2+ additionally gets a link checkbox+badge on each member,
  // opt-in and manual. On: skips the per-axes checkbox dance entirely --
  // every compatible group of 2+ instead gets *one* global slider (the
  // fixed bottom bar) driving every member at once, the answer to "500
  // meshes, all coupled, clicking 500 checkboxes isn't feasible" --
  // see buildSliceSliders()'s own comment for the full layout logic.
  var SLICE_LINK_ALL = SLICE_CFG.link_all === true;
  var sliceGlobalBar = null;   // the fixed bottom bar SLICE_LINK_ALL sliders dock in
  // Value-axis bounds for the slice view: 'auto' (each slice's own
  // min/max -- reads that one slice most clearly, but rescales on every
  // step), 'colorbar' (the mesh's resolved color-scale bounds -- holds
  // still across every slice, matching what the colorbar itself shows),
  // or 'custom' (SLICE_CUSTOM_MIN/MAX, typed in by hand -- for comparing
  // against a range that's neither, e.g. matching a different mesh's scale
  // or a domain-specific reference band).
  var SLICE_RANGE_MODE = (SLICE_CFG.range === 'colorbar' || SLICE_CFG.range === 'custom')
                         ? SLICE_CFG.range : 'auto';
  var SLICE_CUSTOM_MIN = isFiniteNum(SLICE_CFG.range_min) ? +SLICE_CFG.range_min : null;
  var SLICE_CUSTOM_MAX = isFiniteNum(SLICE_CFG.range_max) ? +SLICE_CFG.range_max : null;
  var SLICE_STATE = {};    // axesKey -> {orientation, index, fixedCoord, cursorEl, sliceEl, tickGroup}
  var SLICE_SLIDERS = {};  // axesKey -> {box, api} -- the docked play/step control
  var SLICE_LINKS = {};    // link index -> [slider api], mirrors frame sliders' LINKS

  var DROPDOWN_FOR_MENU = {};
  var MENU_NAMES = ['Axes', 'Point Picking', 'Annotate'];
  if (sliceMenuNeeded) MENU_NAMES.push('Slice');
  MENU_NAMES.push('File');
  MENU_NAMES.forEach(function (name) {
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
