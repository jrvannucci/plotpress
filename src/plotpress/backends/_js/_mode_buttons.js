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
        else if (t.action === 'fit-width') fitWidth();
        else if (t.action === 'reset-axes') resetAxes();
        else if (t.action === 'clear-points') clearPointPins();
        else if (t.action === 'clear-annotations') clearAnnotationPins();
        closeAllMenus();
      });
    }
    container.appendChild(b);
    return b;
  });

  // Slice's own options -- an orientation radio pair, plus a toggle button
  // switching the view -- aren't one-shot actions or mode-select buttons,
  // so they're appended straight into the dropdown TOOLS.map() already
  // built (DROPDOWN_FOR_MENU['Slice']), rather than routed through it.
  // There's no drag-to-place mode at all: like the frame-animation slider
  // it's deliberately modeled on (see buildSliceSlider()'s own comment),
  // Slice is driven entirely by a docked play/step control per mesh axes,
  // built once sliceMenuNeeded and rebuilt whenever orientation changes
  // (see buildSliceSliders(), called both below and from the radio's own
  // change handler).
  if (sliceMenuNeeded) {
    var sliceMenu = DROPDOWN_FOR_MENU['Slice'];
    // Every button's own click handler above stops propagation itself (see
    // attachModeButton/the plain-action handler) so the document-level
    // "click anywhere closes every open menu" listener doesn't immediately
    // undo the click that just opened one -- a plain <label>/<input> here
    // has no such handler of its own, so without this, checking a box
    // would toggle it correctly and then instantly close the whole
    // dropdown out from under it (the very next line of read-back state
    // still succeeds, but the user watching it happen sees the menu
    // vanish).
    sliceMenu.addEventListener('click', function (e) { e.stopPropagation(); });

    // The menu below is four radio groups, four checkboxes and three section
    // headings, every one of them the same handful of createElement calls --
    // these three build one each, appended to the menu in call order.
    var menuSection = function (title) {
      var divider = document.createElement('div');
      divider.className = 'plotpress-menu-divider';
      sliceMenu.appendChild(divider);
      if (!title) return;
      var heading = document.createElement('div');
      heading.className = 'plotpress-menu-heading';
      heading.textContent = title;
      sliceMenu.appendChild(heading);
    };
    var menuCheckbox = function (text, checked, onChange) {
      var lbl = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = checked;
      cb.addEventListener('change', function () { onChange(cb.checked); });
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + text));
      sliceMenu.appendChild(lbl);
      return cb;
    };
    // One row of mutually exclusive radios: `pairs` is [[value, text], ...],
    // `current` the value to start checked, and onPick(value) fires for
    // whichever becomes checked. Returns the inputs, so
    // setSliceControlsEnabled() can grey a whole group out at once.
    var menuRadios = function (name, pairs, current, onPick) {
      var row = document.createElement('div');
      row.className = 'plotpress-slice-orient';
      var radios = pairs.map(function (pair) {
        var lbl = document.createElement('label');
        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'plotpress-slice-' + name;
        radio.checked = (pair[0] === current);
        radio.addEventListener('change', function () { onPick(pair[0]); });
        lbl.appendChild(radio);
        lbl.appendChild(document.createTextNode(' ' + pair[1]));
        row.appendChild(lbl);
        return radio;
      });
      sliceMenu.appendChild(row);
      return radios;
    };

    // Top section: the two controls that matter before anything else --
    // whether Slice does anything at all, and (once it does) which of its
    // two views is showing. Everything below is scoped under "Enable
    // Slice" (disabled, not hidden, while it's off, so the rest of the
    // menu still explains itself) and rebuilt fresh whenever it toggles
    // back on.
    menuCheckbox('Enable Slice', SLICE_ENABLED, function (on) {
      SLICE_ENABLED = on;
      setSliceControlsEnabled(on);
      if (on) buildSliceSliders();
      else {
        // Switched off: no profile left for a strip pin to sit on.
        removeSlicePins();
        teardownSliceSliders(); teardownSliceVisuals(); syncSnappedPins();
      }
    });

    // Redraws every slice at its slider's current index, then puts the pins
    // back on the line it just moved: a strip pin's position is a function of
    // the profile's own geometry (companionPlacer's value range and the strip
    // rect), so *any* menu change that redraws a profile -- the view radio,
    // gridlines, the value range -- has to re-resolve them, or they sit where
    // the old scale put them until something else happens to lay them out.
    var rerenderAllSlices = function () {
      var keys = Object.keys(SLICE_SLIDERS);
      keys.forEach(function (k) { renderMeshOrSlice(k, SLICE_SLIDERS[k].api.i); });
      relayoutSlicePins(keys);
      syncSnappedPins();
    };
    // How the slice is shown -- see SLICE_VIEW. Radios, not independent
    // checkboxes: the three are alternatives, and picking one has to end the
    // others. The red cursor only ever shows with the heatmap, so it isn't
    // drawn under 'replace'.
    menuSection('Slice view');
    menuRadios('view', [['cursor', 'Heatmap with cursor'],
                        ['companion', 'Companion panel'],
                        ['replace', 'Profile replaces heatmap']],
               SLICE_VIEW, function (viewKey) {
      SLICE_VIEW = viewKey;
      SLICE_VIEW_ON = viewKey === 'replace';
      SLICE_COMPANION_ON = viewKey === 'companion';
      rerenderAllSlices();
    });
    menuCheckbox('Gridlines on profile', SLICE_GRID, function (on) {
      SLICE_GRID = on;
      rerenderAllSlices();
    });
    // Mirrors each heatmap pin onto the shown profile -- see syncSnappedPins().
    var snapCb = menuCheckbox('Snap pins to slice', SLICE_SNAP, function (on) {
      SLICE_SNAP = on;
      syncSnappedPins();
    });

    // Which axes are sliced: all of them, or only the ones chosen by clicking
    // them on the figure -- see SLICE_SCOPE.
    menuSection('Axes to slice');
    var scopeRadios = menuRadios('scope', [['all', 'All axes'],
                                           ['selected', 'Selected axes']],
                                 SLICE_SCOPE, function (scopeKey) {
      SLICE_SCOPE = scopeKey;
      // Picking "Selected axes" goes straight to choosing on the figure.
      if (scopeKey === 'selected') { setMode('slice-select'); closeAllMenus(); }
      else if (mode === 'slice-select') setMode(null);
      applySliceScope();
    });
    scopeStatusEl = document.createElement('div');
    scopeStatusEl.className = 'plotpress-menu-note';
    sliceMenu.appendChild(scopeStatusEl);
    var chooseBtn = document.createElement('button');
    chooseBtn.textContent = 'Choose axes on figure';
    // Joins the same highlight the other mode buttons get while their tool is
    // selected (setMode toggles .active on every button carrying its mode).
    chooseBtn.dataset.mode = 'slice-select';
    buttons.push(chooseBtn);
    chooseBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (SLICE_SCOPE !== 'selected') return;
      setMode('slice-select');
      closeAllMenus();
    });
    sliceMenu.appendChild(chooseBtn);
    updateScopeStatus();

    menuSection(null);

    // Orientation is figure-wide, not per-axes: switching it rebuilds every
    // mesh's own slider from scratch (buildSliceSliders(), defined with the
    // rest of the tool below) -- a different orientation means a different
    // row/column count (ny vs. nx) and can change which axes are even
    // compatible to link, so there's no sensible way to adjust an existing
    // slider in place.
    var orientRadios = menuRadios('orient',
      [['x', 'Slice X (horizontal cursor)'], ['y', 'Slice Y (vertical cursor)']],
      SLICE_ORIENTATION, function (axKey) {
        SLICE_ORIENTATION = axKey;
        // A strip pin's index is a sample along the profile, and the profile
        // now runs along the other axis -- the same number would silently
        // point at a different datum, so the pins go rather than move.
        removeSlicePins();
        if (SLICE_ENABLED) buildSliceSliders();
      });

    // Collapses every compatible group's sliders into one shared global
    // slider instead of one docked slider per axes each needing its own
    // link checkbox checked by hand -- see SLICE_LINK_ALL's own comment.
    var linkAllCb = menuCheckbox('Link all matching axes', SLICE_LINK_ALL,
      function (on) {
        SLICE_LINK_ALL = on;
        // Same row/column, just driven from one slider instead of many --
        // see rebuildSliceSlidersKeepingIndex().
        if (SLICE_ENABLED) rebuildSliceSlidersKeepingIndex();
      });

    menuSection(null);

    // Value axis range for the slice view -- 'auto' (default) reads *that*
    // row/column's own min/max most clearly but rescales on every step,
    // distracting when scrubbing/playing through several; 'colorbar' holds
    // still at the mesh's own resolved color-scale bounds (pick_data()'s
    // vmin/vmax -- exactly what the colorbar itself is drawn against,
    // whether the caller passed vmin=/vmax= or let it autoscale from the
    // data); 'custom' holds still at whatever the caller types into the
    // two number fields below instead -- for comparing against a range
    // that's neither of the other two (a different mesh's own scale, a
    // fixed domain-specific reference band).
    var rangeRadios = menuRadios('range-mode',
      [['auto', 'Auto (per slice)'], ['colorbar', 'Colorbar range'],
       ['custom', 'Custom:']],
      SLICE_RANGE_MODE, function (modeKey) {
        SLICE_RANGE_MODE = modeKey;
        customMinInput.disabled = customMaxInput.disabled =
          !SLICE_ENABLED || modeKey !== 'custom';
        rerenderAllSlices();
      });

    var customRow = document.createElement('div');
    customRow.className = 'plotpress-slice-custom-range';
    var customMinInput = document.createElement('input');
    var customMaxInput = document.createElement('input');
    [[customMinInput, 'min'], [customMaxInput, 'max']].forEach(function (pair) {
      var input = pair[0];
      input.type = 'number'; input.placeholder = pair[1]; input.step = 'any';
      var initial = pair[1] === 'min' ? SLICE_CUSTOM_MIN : SLICE_CUSTOM_MAX;
      if (initial !== null) input.value = initial;
      input.disabled = (SLICE_RANGE_MODE !== 'custom');
      input.addEventListener('change', function () {
        SLICE_CUSTOM_MIN = customMinInput.value === '' ? null : +customMinInput.value;
        SLICE_CUSTOM_MAX = customMaxInput.value === '' ? null : +customMaxInput.value;
        if (SLICE_RANGE_MODE === 'custom') rerenderAllSlices();
      });
      customRow.appendChild(input);
    });
    sliceMenu.appendChild(customRow);

    // Enables/disables the controls that only mean something once Slice is
    // actually running. The "Slice view" section stays live always ("Enable
    // Slice" itself, the three view radios and "Gridlines on profile"), per
    // the user's own "in their own section" grouping: those only record what
    // the next enable will draw, so there's nothing to grey out. Everything
    // else is greyed out rather than hidden while Slice is off, so the menu
    // still explains what turning it on will offer. The custom min/max inputs
    // fold in their own second condition (only live under 'custom' range
    // mode to begin with) rather than simply mirroring `on`.
    function setSliceControlsEnabled(on) {
      orientRadios.forEach(function (r) { r.disabled = !on; });
      linkAllCb.disabled = !on;
      snapCb.disabled = !on;
      scopeRadios.forEach(function (r) { r.disabled = !on; });
      chooseBtn.disabled = !on;
      rangeRadios.forEach(function (r) { r.disabled = !on; });
      customMinInput.disabled = customMaxInput.disabled =
        !on || SLICE_RANGE_MODE !== 'custom';
    }
    setSliceControlsEnabled(SLICE_ENABLED);
  }

  // Public extension point for a caller's own extra_js= (see Figure.to_html):
  // add a tool to its own menu, created lazily on first call -- a page with
  // no custom tools gets no empty extra menu to explain. Two shapes,
  // mirroring TOOLS above -- {label, onClick}: an always-available action,
  // firing immediately on click, like Extract/Save. {label, mode, onClick,
  // onEnter, onExit, cursor}: a real *mode*, joining the same
  // single-selection group as Pan/Zoom, Axis Span/Zoom, Point
  // Picking, or any Annotate tool -- picking it deselects whatever else was active,
  // and vice versa (see setMode below, and the `buttons` array/dataset.mode
  // CSS-'active' sync inside it, both of which already work for any button
  // in `buttons` generically, custom or not). Selected, a click on the SVG
  // that no built-in mode already claims (`note-plain`/`note-free`/
  // `note-point`/`pick` -- see the
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
    // Escape leaves this mode (see the keydown handler) -- said right in the label.
    if (m === 'slice-select') return 'Choose slice axes · Esc to finish';
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

  // The browser's own crosshair is drawn in one color, which vanishes against a
  // white figure (or a dark one); this draws a black cross with a white halo, so
  // it reads on either.
  var TWO_TONE_CROSS = 'url("data:image/svg+xml;utf8,' +
    "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'>" +
    "<path d='M12 2v20M2 12h20' stroke='white' stroke-width='4'/>" +
    "<path d='M12 2v20M2 12h20' stroke='black' stroke-width='1.5'/></svg>" +
    '") 12 12, crosshair';
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
      mode === 'zoom' ? TWO_TONE_CROSS :
      mode === 'slice-select' ? TWO_TONE_CROSS :
      mode === 'magnify' ? 'zoom-in' :
      isAnnotateMode(mode) ? 'text' :
      (custom && custom.cursor) ? custom.cursor : 'default';
    // Any active mode's own drag can sweep across text the same way
    // Magnify's whole-figure pan always could -- Span/Zoom drag across tick
    // labels and titles, Point Picking/Annotate drag a pin's own text box
    // across other pins' labels -- so disabling selection is scoped to
    // "some tool is selected" generally, not just Magnify specifically.
    // Inert (no mode) leaves normal text selection alone.
    svg.style.userSelect = mode ? 'none' : '';
    refreshDragReady();
    drawSliceSelection();
  }
  setMode(null);  // start inert with an arrow cursor

