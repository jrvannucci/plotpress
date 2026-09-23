  // ---- save/save as: persist the current pan/zoom, pins, and toggles ----
  // A plain data-only re-serve (Extract) is not "resume where I left off" --
  // this rebuilds the whole page instead, from the same clean pre-mutation
  // snapshot (ORIGINAL_DOC_HTML) every save starts from, plus one new
  // payload script tag the bootstrap below reads back on the saved file's
  // own next load.
  function serializePins() {
    var out = [];
    document.querySelectorAll('.plotpress-pin:not(.plotpress-snapped)').forEach(function (pin) {
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
  // (data.kind set -- a plain Point Picking marker or an Annotate Point
  // note) through addAnchoredPin(), which re-resolves its position from the
  // *current* (already-restored) view via pinAnchor()/resolve() exactly as a
  // fresh click would; an Annotate/Annotate Arrow note or the large-series
  // geometry fallback (no data.kind) directly, converting its own saved
  // data-space x/y through the current view when it has one, or at its
  // saved fixed figure position when it doesn't -- and, for a plain
  // Annotate box, passing noteStyle through to addPin() so it comes back
  // with no dot/arrow, the same as when it was first dropped.
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
        // startBoxDrag) and an Annotate Point note's noteStyle (set by
        // addPointNote *after* its own addAnchoredPin() call returns, so
        // addAnchoredPin itself never learns about it) aren't among them,
        // so both are carried over here explicitly, the same as the
        // free-note branch's full dataset copy below already does for its
        // own pins. Without this, a restored Annotate Point note fell back
        // to boxDraggableNow()'s bare `|| 'arrow'` default -- draggable
        // under Annotate Arrow instead of Annotate Point after every
        // reload, though its dot/arrow/pick-locked geometry (all decided
        // elsewhere, from data.kind) stayed correct.
        if (g && rec.data.boxDx !== undefined) {
          g.dataset.boxDx = rec.data.boxDx; g.dataset.boxDy = rec.data.boxDy;
        }
        if (g && rec.data.noteStyle !== undefined) {
          g.dataset.noteStyle = rec.data.noteStyle;
        }
      } else {
        var px, py;
        if (rec.data.axes !== undefined && CUR[rec.data.axes]) {
          var q = toPixel(CUR[rec.data.axes], +rec.data.x, +rec.data.y);
          px = q.x; py = q.y;
        } else {
          px = +rec.data.px; py = +rec.data.py;
        }
        g = addPin(px, py, rec.text, rec.data.axes, rec.data.noteStyle === 'plain');
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
    // Slice starts from its startup settings (see PLOTPRESS_OPTION_CONFIG), so
    // saving rewrites them to the current state -- enabled, view, chosen axes,
    // slider position -- and the saved file simply reopens the way it was left.
    if (hasOption('slice')) {
      var optionScript = Array.prototype.slice.call(doc.querySelectorAll('script')).filter(function (sc) {
        return sc.textContent.indexOf('window.PLOTPRESS_OPTIONS=') === 0;
      })[0];
      if (optionScript) {
        var cfg = {};
        for (var ok in OPTION_CONFIG) cfg[ok] = OPTION_CONFIG[ok];
        cfg.slice = sliceSaveConfig();
        optionScript.textContent = 'window.PLOTPRESS_OPTIONS=' + JSON.stringify(OPTIONS) +
          ';window.PLOTPRESS_OPTION_CONFIG=' + JSON.stringify(cfg) + ';';
      }
    }
    return '<!doctype html>' + doc.documentElement.outerHTML;
  }

  // The Slice tool's current state, in the same shape Figure.to_html(options=
  // {"slice": {...}}) takes -- see buildSaveHTML.
  function sliceSaveConfig() {
    var c = { enabled: SLICE_ENABLED, view: SLICE_VIEW, orientation: SLICE_ORIENTATION,
              link_all: SLICE_LINK_ALL, snap_pins: SLICE_SNAP, grid: SLICE_GRID, range: SLICE_RANGE_MODE,
              panel_size: SLICE_COMPANION_FRAC };
    if (SLICE_RANGE_MODE === 'custom' && isFiniteNum(SLICE_CUSTOM_MIN) && isFiniteNum(SLICE_CUSTOM_MAX)) {
      c.range_min = SLICE_CUSTOM_MIN; c.range_max = SLICE_CUSTOM_MAX;
    } else if (SLICE_RANGE_MODE === 'custom') {
      c.range = 'auto';   // nothing valid typed in yet: the same thing it drew
    }
    if (SLICE_SCOPE === 'selected') {
      c.axes = Object.keys(SLICE_SELECTED).filter(function (k) { return SLICE_AXES[k]; }).map(Number);
    }
    var idx = currentSliceIndex();
    if (idx !== null) c.index = idx;
    return c;
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

  // Deliberately identical to saveAsNewPage() today, not an accidental
  // duplicate left behind by a refactor: see saveViaPicker()'s own comment
  // above for why there is no writable handle to "the file this page was
  // opened from" for either button to reuse. Kept as its own named function
  // (rather than aliased or merged) so the two toolbar entries stay easy to
  // tell apart if a real overwrite-in-place path is ever added for one of
  // them but not the other.
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
  // within MESH_OVERRIDE_THRESHOLD px if the click also landed inside a mesh
  // cell -- see below -- else within POINT_THRESHOLD px, else a mesh cell,
  // else a pie wedge, else a point regardless of distance) -- kept as its
  // own function since Annotate Point (addPointNote) is a second caller
  // wanting the exact same resolution logic. Returns
  // a steppable anchor ref; ``null`` if there's simply nothing pickable
  // there (the caller may fall back to a geometric readout); or the string
  // ``'blocked'`` for the one case that must produce nothing at all, not a
  // fallback -- a pie axes only has its wedges to pick, so a click that
  // misses every one of them is a genuine miss, not "no data nearby".
  function resolvePickTarget(e) {
    var p = toUser(e);
    // A click on a Slice companion strip -- outside every axes' own (shrunken)
    // heatmap rect, so nothing below would ever see it -- picks a profile
    // sample.
    var stripHit = sliceStripPick(p);
    if (stripHit) return stripHit;
    var a = pickableAxesAt(p);
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
    // np.d/fp.d are squared distances in root SVG user-space units (the
    // same space toPixel()/toUser() both work in) -- a constant number of
    // *those* is not a constant number of actual screen pixels once the
    // whole figure is magnified (Pan/Zoom grows the SVG's own rendered CSS
    // size while its viewBox, and so this space, stays fixed -- see
    // pxPerUser()); an axes' own Axis Span/Zoom, by contrast, already
    // reshapes this same space when the view changes, so it needs no
    // separate handling here. Converting the *distance* to real screen px
    // (rather than the threshold to user-space units) keeps every
    // POINT_THRESHOLD/MESH_OVERRIDE_THRESHOLD comparison below meaning what
    // it says regardless of Pan/Zoom level, the same "constant on-screen
    // size" guarantee a pin's own marker already gets (see layoutPin).
    var scale = pxPerUser();
    var candPx = cand ? Math.sqrt(cand.d) * scale : Infinity;

    var pd = PICK[a.i];
    if (pd && pd.pies && pd.pies.length && !pieHit && !mesh && candPx > POINT_THRESHOLD) {
      return 'blocked';
    }
    // Inside a mesh cell's own bounds, only a genuinely precise click on a
    // line/scatter point overrides it -- see MESH_OVERRIDE_THRESHOLD above.
    var pointThreshold = mesh ? MESH_OVERRIDE_THRESHOLD : POINT_THRESHOLD;
    if (cand && candPx <= pointThreshold) return cand.ref;
    if (mesh) return mesh;
    if (pieHit) return pieHit;
    if (cand) return cand.ref;
    return null;
  }

  // Shared by all three Annotate modes. A cross-origin-equivalent embedding
  // (an <iframe srcdoc=...>, as Report.save() uses for every entry) has its
  // own opaque origin, and browsers silently block alert/confirm/prompt from
  // such a frame -- window.prompt() there can either return null (treated as
  // "cancelled", same as a real one) or throw outright, depending on
  // browser. Catching it keeps the latter from surfacing as an uncaught
  // error on every click while an Annotate mode is active -- console.warn
  // (once, not per click) gives a developer debugging "Annotate does
  // nothing here" an actual lead, since the click itself otherwise looks
  // identical to a user simply cancelling the prompt.
  function promptForAnnotationText() {
    try { return window.prompt('Annotation text:'); }
    catch (err) {
      if (!promptForAnnotationText._warned) {
        promptForAnnotationText._warned = true;
        console.warn('plotpress: window.prompt() is blocked in this frame '
          + '(a cross-origin-equivalent embedding, e.g. Report.save()\'s '
          + '<iframe srcdoc>) -- Annotate cannot ask for text here and '
          + 'will do nothing when clicked.');
      }
      return null;
    }
  }

  // Annotate (internal mode note-plain): drop a plain text box anywhere on
  // the figure -- a caption, not a callout. No dot, no leader arrow (see
  // addPin's plain param), and always pinned to a fixed figure position,
  // even when dropped inside an axes -- unlike Annotate Arrow below, it
  // never tracks that axes' data coordinate, since it isn't pointing at
  // anything in particular for a pan/zoom to keep it aligned with.
  function addPlainNote(e) {
    var text = promptForAnnotationText();
    if (!text) return;
    var p = toUser(e);
    var g = addPin(p.x, p.y, text, undefined, true);
    g.classList.add('plotpress-note');
    g.dataset.annotation = '1';
    g.dataset.noteStyle = 'plain';
    g.dataset.px = p.x; g.dataset.py = p.y;
    refreshOneDragReady(g);
  }

  // Annotate Arrow (internal mode note-free): drop a note anywhere on the
  // whole figure, including the margins or the gap between subplots -- not
  // locked to any datum, but pointing at wherever it was actually dropped (a
  // dot at that spot, a leader arrow to the label box). Inside an axes it
  // still tracks that axes' data coordinate (so it pans/zooms with the plot
  // it was drawn over); outside any axes there is no data coordinate, so it
  // just stays put at its figure pixel position, which nothing in the
  // interactive view moves.
  function addFreeNote(e) {
    var text = promptForAnnotationText();
    if (!text) return;
    var p = toUser(e);
    var a = axesAt(p);
    var g = addPin(p.x, p.y, text, a ? a.i : undefined);
    g.classList.add('plotpress-note');
    g.dataset.annotation = '1';
    g.dataset.noteStyle = 'arrow';
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

  // Annotate Point: lock a user-typed note to the nearest pickable datum --
  // the exact same resolution Point Picking's own click handler uses,
  // including its large-series geometric fallback (see resolvePickTarget and
  // the 'pick' branch below) -- so it's steppable by arrow key and tracks
  // pan/zoom exactly like an ordinary Point Picking pin. Classed as an
  // annotation (addAnchoredPin does this whenever it's given text), so it
  // survives a Clear Points click, is unaffected by Hide Points, and never
  // appears in Extract's output -- Extract returns only Point Picking
  // markers (see doExtract), the same reason every other annotation is
  // already excluded from it.
  function addPointNote(e) {
    var ref = resolvePickTarget(e);
    if (ref === 'blocked') return;
    var p = toUser(e), a = pickableAxesAt(p);
    if (!ref && !a) return;   // nothing pickable here to lock a note to
    var text = promptForAnnotationText();
    if (!text) return;
    var g;
    if (ref) {
      g = addAnchoredPin(ref, ref.index, text);
    } else {
      var v = nearestVertex(a.i, p) || p;              // large-series fallback
      var dd = toData(a.m, v.x, v.y);
      g = addPin(v.x, v.y, text, a.i);
      g.classList.add('plotpress-note');
      g.dataset.annotation = '1';
      g.dataset.x = dd.x; g.dataset.y = dd.y; g.dataset.axes = a.i;
      refreshOneDragReady(g);
    }
    if (g) g.dataset.noteStyle = 'point';
  }

  svg.addEventListener('click', function (e) {
    if (moved) return;
    if (e.target.closest('.plotpress-legend') || e.target.closest('.plotpress-pin')) return;
    if (mode === 'slice-select') { toggleSliceAxis(e); return; }
    if (mode === 'note-plain') { addPlainNote(e); return; }
    if (mode === 'note-free') { addFreeNote(e); return; }
    if (mode === 'note-point') { addPointNote(e); return; }
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

