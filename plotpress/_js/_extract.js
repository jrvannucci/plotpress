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
    } else if (anchor && anchor.kind === 'slice') {
      var sp = slicePinPoint(anchor.axes, +pin.dataset.index);
      rec.axes = +anchor.axes; rec.kind = 'slice'; rec.index = +pin.dataset.index;
      if (sp) { rec.x = sp.x; rec.y = sp.y; rec[sp.name] = sp.z; }
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
        // Dropped outside any axes (or an Annotate box, which is always
        // figure-fixed) -- there is no data coordinate to give it, only a
        // fixed figure pixel position.
        rec.px = +pin.dataset.px; rec.py = +pin.dataset.py;
      }
    } else {
      rec.kind = 'free';
      if (pin.dataset.axes !== undefined) rec.axes = +pin.dataset.axes;
      rec.x = +pin.dataset.x; rec.y = +pin.dataset.y;
    }
    // An Annotate Point note's user text rides alongside its anchor's own
    // structured fields (x/y/z/...) set above, rather than replacing them --
    // a caller reading plotpressGetMarkers() (Extract itself never sees
    // these; see addPointNote) gets both the datum it's locked to and the
    // note text pinned there.
    if (pin.dataset.customLabel !== undefined) rec.text = pin.dataset.customLabel;
    // Identify the source panel by name, not just its bare index -- falls
    // back to a generated name when that axes has no title set, so every
    // record carries one. xlabel/ylabel/zlabel (zlabel from any colorbar
    // attached to this axes, shared or not) ride along too, so a value
    // pulled out of context still says what it means, not just a bare
    // number -- including a label set with visible=False, which is drawn
    // nowhere but still carries here. The figure's own supxlabel/supylabel/
    // suptitle come along after (only when set) as the shared-axis fallback.
    // group is the title of whichever fig.group() box this axes sits in
    // (joined with ", " if it's in more than one, empty if none), so a
    // marker from a clustered panel says which cluster it came from. Any
    // per-axes context (Axes.set_pick_context) rides along as well, without
    // clobbering a structured field of the same name (x, y, kind, ...) that
    // the picked data itself already set.
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
    // Figure-level shared labels -- added only when the figure has them, so a
    // record from a figure with none is unchanged. A per-axes xlabel/ylabel
    // (visible or hidden) still rides alongside above; these are the fallback
    // for a grid that carries only one shared sup-label.
    var lx = LAYOUT.supxlabel && LAYOUT.supxlabel.text;
    var ly = LAYOUT.supylabel && LAYOUT.supylabel.text;
    var lt = LAYOUT.suptitle && LAYOUT.suptitle.text;
    if (lx) rec.supxlabel = lx;
    if (ly) rec.supylabel = ly;
    if (lt) rec.suptitle = lt;
    return rec;
  }

  // Every pin, Point Picking and every Annotate tool alike -- this is the general
  // public query (window.plotpressGetMarkers, qt.py's LiveArtist marker
  // sync, a custom tool's own onClick logging its progress), not Extract's.
  // Extract itself is narrower -- see doExtract below.
  function getMarkers() {
    return Array.prototype.map.call(
      document.querySelectorAll('.plotpress-pin:not(.plotpress-snapped)'), markerRecord);
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

  function showExtractPanel(records, csv, json, notice, sendAnyway) {
    var old = document.querySelector('.plotpress-extract');
    if (old) old.remove();
    var panel = document.createElement('div');
    panel.className = 'plotpress-extract';
    var head = document.createElement('div');
    head.style.cssText = 'font-weight:600;margin-bottom:6px';
    head.textContent = records.length + ' marker' + (records.length === 1 ? '' : 's');
    var ta = document.createElement('textarea');
    ta.readOnly = true;
    // The text shown (and copied) follows the format radios; JSON is the default.
    var format = 'json';
    var current = function () { return format === 'json' ? json : (csv || '(no markers)'); };
    ta.value = current();
    var formats = document.createElement('div');
    formats.style.cssText = 'display:flex;gap:12px;margin-bottom:6px;font-size:12px';
    [['json', 'JSON'], ['csv', 'CSV']].forEach(function (pair) {
      var lbl = document.createElement('label');
      lbl.style.cssText = 'display:flex;align-items:center;gap:4px;cursor:pointer';
      var radio = document.createElement('input');
      radio.type = 'radio'; radio.name = 'plotpress-extract-format';
      radio.checked = (pair[0] === format);
      radio.addEventListener('change', function () {
        format = pair[0]; ta.value = current(); ta.select();
      });
      lbl.appendChild(radio); lbl.appendChild(document.createTextNode(pair[1]));
      formats.appendChild(lbl);
    });
    var btns = document.createElement('div');
    btns.style.cssText = 'display:flex;gap:6px;margin-top:6px;flex-wrap:wrap';
    function mk(txt, fn) {
      var b = document.createElement('button');
      b.textContent = txt; b.addEventListener('click', fn); return b;
    }
    var copy = mk('Copy', function () {
      ta.select();
      var done = function () {
        copy.textContent = 'Copied!';
        setTimeout(function () { copy.textContent = 'Copy'; }, 1200);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(ta.value).then(done, function () {
        try { document.execCommand('copy'); done(); } catch (e) {}
      });
      else { try { document.execCommand('copy'); done(); } catch (e) {} }
    });
    btns.appendChild(copy);
    btns.appendChild(mk('Download CSV', function () { download('markers.csv', csv, 'text/csv'); }));
    btns.appendChild(mk('Download JSON', function () { download('markers.json', json, 'application/json'); }));
    // Only in wait-for-extract mode, where sending closes the window: the user
    // gets to read the notice first and choose to go ahead without those pins.
    if (sendAnyway) {
      btns.appendChild(mk('Extract without them', function () { panel.remove(); sendAnyway(); }));
    }
    btns.appendChild(mk('Close', function () { panel.remove(); }));
    panel.appendChild(head);
    if (notice) {
      var warn = document.createElement('div');
      warn.className = 'plotpress-extract-notice';
      warn.style.cssText = 'background:#fef3c7;color:#92400e;border:1px solid #f59e0b;' +
        'border-radius:4px;padding:6px 8px;margin-bottom:6px;font-size:12px;line-height:1.35';
      warn.textContent = notice;
      panel.appendChild(warn);
    }
    panel.appendChild(formats); panel.appendChild(ta); panel.appendChild(btns);
    document.body.appendChild(panel);
    ta.focus(); ta.select();
  }

  // Point Picking markers only, not annotation notes -- Extract now lives
  // solely under the Point Picking menu (see TOOLS above), so its own
  // output scopes to match; an annotation note (from any of the three
  // Annotate tools, Annotate Point included) has nothing to "extract" in
  // the same sense a picked data value does. :not(.plotpress-note) is the
  // one line doing that filtering -- getMarkers() above (and every other
  // .plotpress-pin selector in this file that isn't already kind-specific,
  // like drag-ready and clearAllPins) deliberately still covers both kinds.
  // Slice profile pins are left out: a point picked on the profile is the same
  // point as a cell of the heatmap, and the heatmap is where the data lives, so
  // Extract reports the heatmap side only. With Snap pins to slice on, a pin
  // placed on the profile has a heatmap mirror (marked .plotpress-snapped) and
  // *that* is what's extracted for it -- unless a heatmap pin already covers the
  // same cell, so no point is ever reported twice.
  // Pins placed on the Slice profile are never extracted themselves, so one with
  // no heatmap mirror to stand in for it is simply missing from the output --
  // the user has to be told, not left to notice a short list. Returns the
  // message, or '' when nothing was left out.
  function sliceExtractNotice() {
    var lost = 0;
    document.querySelectorAll('.plotpress-pin[data-kind="slice"]:not(.plotpress-snapped)').forEach(function (p) {
      var uid = p.dataset.snapUid;
      if (uid === undefined || !document.querySelector('.plotpress-snapped[data-snap-of="' + uid + '"]')) lost++;
    });
    if (!lost) return '';
    var what = lost + ' pin' + (lost === 1 ? '' : 's') + ' placed on the slice ' +
               (lost === 1 ? 'was' : 'were') + ' not extracted. ';
    return SLICE_SNAP
      ? what + 'They have no heatmap point to extract (no value at that sample, or the ' +
        'companion panel is off).'
      : what + 'Slice pins are left out to avoid duplicating heatmap points -- turn on ' +
        '"Snap pins to slice" in the Slice menu to extract them as heatmap points.';
  }
  function doExtract() {
    var pins = Array.prototype.slice.call(document.querySelectorAll(
      '.plotpress-pin:not(.plotpress-note):not([data-kind="slice"])'));
    var recKey = function (r) { return r.axes + '|' + r.kind + '|' + r.index; };
    var have = {};
    pins.forEach(function (pin) {
      if (!pin.classList.contains('plotpress-snapped')) have[recKey(markerRecord(pin))] = true;
    });
    var records = [];
    pins.forEach(function (pin) {
      var rec = markerRecord(pin);
      if (pin.classList.contains('plotpress-snapped')) {
        if (have[recKey(rec)]) return;
        have[recKey(rec)] = true;
      }
      records.push(rec);
    });
    var notice = sliceExtractNotice();
    // Hand off to Python when running inside the native (pywebview) window.
    var send = function () {
      try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.extract) {
          window.pywebview.api.extract(records);
        }
      } catch (e) {}
    };
    var csvText = toCSV(records), jsonText = JSON.stringify(records, null, 2);
    if (window.PLOTPRESS_WAIT_EXTRACT) {
      // The kernel closes this window on receipt, so a notice would vanish the
      // moment it was sent: hold the send back behind a panel instead.
      if (notice) showExtractPanel(records, csvText, jsonText, notice, send);
      else send();
      return;
    }
    send();
    showExtractPanel(records, csvText, jsonText, notice);
  }
  window.plotpressExtract = doExtract;

