  // ---- slider(s) over extra data dimensions -----------------------------
  // Each "unit" is one control bar. The global unit ("main") is a single bar
  // driving all shared series; a docked unit sits under its axes. Docked units
  // that share a connection index show an index badge + a checkbox to link them
  // so they scrub together on demand.
  // FRAMES/UNITS are parsed up above, alongside PICK, not here -- the Slice
  // menu built alongside every other menu needs FRAMES too, to know about an
  // animated pcolormesh_frames() axes (see SLICE_AXES's own comment).
  var LINKS = {};  // connection index -> [slider api]

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
      resyncSliceForFrameUnit(unit);
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
    // Wrap the SVG so docked sliders can be positioned over it (see
    // ensureSvgWrap()'s own comment -- shared with the Slice tool's own
    // docked sliders, since either may need this and only one should ever
    // actually create it). Sized by the .plotpress-svg-wrap rule in the
    // page's own <style> (see Figure.to_html), not inline here --
    // standalone shrink-wraps it to the SVG's natural size for
    // flex-centering; embedded (standalone=False) stretches it to the
    // container's width so #plotpress-svg's own width:100% has a definite,
    // non-circular size to resolve against instead of falling back to the
    // SVG's fixed width/height attributes.
    ensureSvgWrap();

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
    // If Slice's own global bar (sliceGlobalBar) already exists by the time
    // this runs, it doesn't -- Slice only ever builds one in response to a
    // user action (Enable Slice / Link all matching axes), never at load --
    // but call it anyway rather than assuming the ordering, matching how
    // buildSliceSliders()/teardownSliceSliders() call it back for this bar
    // in the other direction.
    reflowGlobalBars();
    window.addEventListener('resize', positionDocked);
  }

  // Three flavors, all deselecting selectedPin only when it's actually one
  // of the pins being removed -- clearing points shouldn't drop the user's
  // in-progress arrow-key selection of an annotation they were just
  // stepping through, and vice versa. .plotpress-note is the same class
  // all three Annotate modes (addPlainNote/addFreeNote/addPointNote) tag
  // every note with -- see the TOOLS comment above for why that's the
  // reliable point/annotation split, not e.g. a pin's `kind`.
  function isAnnotationPin(p) { return p.classList.contains('plotpress-note'); }

  function clearPointPins() {
    document.querySelectorAll('.plotpress-pin').forEach(function (p) {
      if (!isAnnotationPin(p)) p.remove();
    });
    if (selectedPin && !isAnnotationPin(selectedPin)) selectedPin = null;
    if (SLICE_SNAP) syncSnappedPins();
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
      } else if (mode === 'slice-select') {
        // Choosing Slice axes is a pick-only mode with nothing of the user's to
        // clear: Escape just leaves it, keeping their pins.
        setMode(null);
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
    if (dir) {
      e.preventDefault();
      // A snapped mirror is rebuilt from its source pin, so stepping it directly
      // would just be undone -- step the pin it mirrors, and the mirror follows.
      var target = selectedPin;
      if (target.classList.contains('plotpress-snapped')) {
        var source = document.querySelector('.plotpress-pin[data-snap-uid="' + target.dataset.snapOf + '"]');
        if (source) target = source;
      }
      stepPin(target, dir);
    }
  });

  // Applied last: replays a Save/Save As from an earlier session (view,
  // pins, toggles) now that every function/data structure above exists to
  // do it with -- see buildSaveState()/applySavedState() above.
  // Start Slice in the caller's chosen state (options={"slice": {"enabled":
  // True, ...}}) -- the menu controls above already read the same variables,
  // so this only has to build what "enabled" implies.
  if (sliceMenuNeeded) drawSliceSelection();
  if (sliceMenuNeeded && SLICE_ENABLED) {
    buildSliceSliders();
    if (isFiniteNum(SLICE_CFG.index)) restoreSliceIndex(SLICE_CFG.index);
  }
  var savedStateEl = document.getElementById('plotpress-saved-state');
  if (savedStateEl) applySavedState(JSON.parse(savedStateEl.textContent));
