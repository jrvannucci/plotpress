  // ---- Slice tool (pcolormesh/imshow row/column profile) -----------------
  // Modeled directly on the frame-animation slider (buildSlider, above) --
  // stepping through a mesh's rows/columns is the same interaction as
  // stepping through animation frames, so it gets the identical widget
  // (play/pause/step-forward/step-back + a scrub range), docked under its
  // own axes via the same wrap/dockedSliders/positionDocked machinery, with
  // linking via the same index/checkbox/external fan-out pattern
  // (SLICE_LINKS mirrors LINKS). There is no separate "drag on the mesh"
  // mode: the slider is the one way to move a slice, exactly like a frame
  // slider is the one way to change frames.
  function meshEntryForAxes(key) {
    var info = SLICE_AXES[key];
    if (!info) return null;
    if (info.frameEntry) {
      // A FrameQuadMesh's entry carries one z per frame (frame_data() pops
      // each frame's z into its own array-of-arrays; everything else --
      // edges/vmin/vmax/curvilinear -- is shared across frames, since every
      // frame draws over the same grid) -- resolved to whichever frame is
      // currently showing on every call, not cached, so a slice/cursor
      // redraw always reflects the frame the mesh itself is on. Shaped to
      // match a plain PICK mesh entry so every other Slice function below
      // (computeSliceByIndex, edgesMatch, sliceSpecFor, ...) can read either
      // one identically.
      var e = info.frameEntry;
      return {
        xedges: e.xedges, yedges: e.yedges, xc: e.xc, yc: e.yc,
        shape: e.shape, z: e.z[CURRENT_FRAME[e.unit] || 0],
        vmin: e.vmin, vmax: e.vmax, curvilinear: e.curvilinear, name: e.name,
      };
    }
    var meshes = (PICK[key] && PICK[key].meshes) || [];
    return meshes[info.meshIndex] || null;
  }
  function cellMidpoints(edges) {
    var out = [];
    for (var i = 0; i < edges.length - 1; i++) out.push((edges[i] + edges[i + 1]) / 2);
    return out;
  }
  function isFiniteNum(v) { return typeof v === 'number' && isFinite(v); }

  // The 1-D profile at row/column `index` along `orientation`, plus the
  // fixed coordinate that row/column actually sits at (its own midpoint) --
  // z is a *flat*, row-major array (shape [ny, nx], row 0 = ymin -- see
  // pick_data()/reviveBinary, which decodes a large mesh's z straight into
  // a flat typed array, never a nested one), so a cell is z[row*nx+col],
  // not z[row][col].
  function computeSliceByIndex(key, orientation, index) {
    var entry = meshEntryForAxes(key);
    if (!entry) return null;
    var z = entry.z, xedges = entry.xedges, yedges = entry.yedges;
    var ny = entry.shape[0], nx = entry.shape[1];
    if (orientation === 'x') {
      var row = Math.max(0, Math.min(ny - 1, index));
      var ysRow = [];
      for (var c = 0; c < nx; c++) ysRow.push(z[row * nx + c]);
      return { xs: cellMidpoints(xedges), ys: ysRow,
              fixedCoord: (yedges[row] + yedges[row + 1]) / 2 };
    }
    var col = Math.max(0, Math.min(nx - 1, index));
    var ysCol = [];
    for (var r = 0; r < ny; r++) ysCol.push(z[r * nx + col]);
    return { xs: cellMidpoints(yedges), ys: ysCol,
            fixedCoord: (xedges[col] + xedges[col + 1]) / 2 };
  }

  // Two mesh axes are compatible for linking iff they share the same values
  // along whichever axis the current orientation holds fixed -- Y for a
  // horizontal (X) slice, X for a vertical (Y) one -- so index i means the
  // same row/column position on both. Matches the user-facing "share the
  // same values on the axis" framing directly.
  function edgesMatch(k1, k2, orientation) {
    var e1 = meshEntryForAxes(k1), e2 = meshEntryForAxes(k2);
    if (!e1 || !e2) return false;
    var a1 = orientation === 'x' ? e1.yedges : e1.xedges;
    var a2 = orientation === 'x' ? e2.yedges : e2.xedges;
    if (!a1 || !a2 || a1.length !== a2.length) return false;
    for (var i = 0; i < a1.length; i++) {
      if (Math.abs(a1[i] - a2[i]) > 1e-9 * Math.max(1, Math.abs(a1[i]))) return false;
    }
    return true;
  }
  // Groups every slice-eligible axes by mutual edgesMatch() compatibility
  // under the current orientation. Returns the raw groups (each an array of
  // axes keys, in no particular order) -- callers needing just "axesKey ->
  // link index string for axes in a group of >=2" (the per-slider
  // checkbox/badge case) derive that with sliceLinkIndexOf() below; the
  // "one shared global slider per group" case (buildSliceSliders(), when
  // SLICE_LINK_ALL) needs the full member list per group instead, which a
  // flattened index map can't give back.
  function sliceScopeKeys() {
    var keys = Object.keys(SLICE_AXES);
    return SLICE_SCOPE === 'selected' ? keys.filter(function (k) { return SLICE_SELECTED[k]; }) : keys;
  }
  function updateScopeStatus() {
    if (!scopeStatusEl) return;
    var n = Object.keys(SLICE_SELECTED).filter(function (k) { return SLICE_AXES[k]; }).length;
    scopeStatusEl.textContent = SLICE_SCOPE === 'all' ? 'Slicing every mesh'
      : n ? n + ' selected \u2014 click an axes to add or remove it'
          : 'None selected \u2014 click axes on the figure';
  }
  // While choosing, dashed-outlines the axes that are still choosable, so it's
  // clear what can be clicked. A chosen axes needs no marker of its own: it is
  // the one whose frame now holds the slice (strip, cursor or profile).
  function drawSliceSelection() {
    var old = svg.querySelector('g.plotpress-slice-select');
    if (old) old.remove();
    // setMode(null) runs at startup, before any of the Slice state exists.
    if (SLICE_SCOPE !== 'selected' || !sliceMenuNeeded || mode !== 'slice-select') return;
    var g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', 'plotpress-slice-select');
    g.setAttribute('pointer-events', 'none');
    Object.keys(SLICE_AXES).forEach(function (k) {
      var o = META[k];
      if (!o || SLICE_SELECTED[k]) return;
      var r = document.createElementNS(SVGNS, 'rect');
      r.setAttribute('x', o.x + 1); r.setAttribute('y', o.y + 1);
      r.setAttribute('width', o.w - 2); r.setAttribute('height', o.h - 2);
      r.setAttribute('fill', 'none');
      r.setAttribute('stroke', '#9ca3af'); r.setAttribute('stroke-width', 1);
      r.setAttribute('stroke-dasharray', '4,3');
      g.appendChild(r);
    });
    svg.appendChild(g);
  }
  function currentSliceIndex() {
    var ks = Object.keys(SLICE_SLIDERS);
    return ks.length ? SLICE_SLIDERS[ks[0]].api.i : null;
  }
  function restoreSliceIndex(index) {
    var started = [];
    Object.keys(SLICE_SLIDERS).forEach(function (k) {
      var built = SLICE_SLIDERS[k];
      if (started.indexOf(built) !== -1) return;
      started.push(built);
      var top = +built.box.querySelector('input[type=range]').max;
      built.api.external(Math.max(0, Math.min(index, top)));
    });
  }
  // Rebuild every slider but leave the slice where the user had it. For a
  // change that alters how many sliders there are without changing what an
  // index *means* -- the scope, or "Link all matching axes" collapsing a
  // group's sliders into one -- snapping back to the first row/column throws
  // away the position they scrubbed to for no reason. An orientation change
  // is deliberately not one of these: index 5 is row 5 one way and column 5
  // the other, so that one does start over.
  function rebuildSliceSlidersKeepingIndex() {
    var keep = currentSliceIndex();
    buildSliceSliders();
    if (keep !== null) restoreSliceIndex(keep);
  }
  // The scope changed: redraw the outlines and, if Slice is on, rebuild the
  // sliders for just the axes now in scope.
  function applySliceScope() {
    drawSliceSelection();
    updateScopeStatus();
    if (SLICE_ENABLED) rebuildSliceSlidersKeepingIndex();
  }
  // A click in 'slice-select' mode toggles the (topmost) mesh axes under it.
  function toggleSliceAxis(e) {
    var p = toUser(e), hit = null;
    Object.keys(SLICE_AXES).map(Number).sort(function (a, b) { return b - a; }).some(function (k) {
      var o = META[k];
      if (o && p.x >= o.x && p.x <= o.x + o.w && p.y >= o.y && p.y <= o.y + o.h) {
        hit = String(k); return true;
      }
      return false;
    });
    if (hit === null) return;
    if (SLICE_SELECTED[hit]) delete SLICE_SELECTED[hit]; else SLICE_SELECTED[hit] = true;
    applySliceScope();
  }
  function computeSliceLinkGroups(orientation) {
    var keys = sliceScopeKeys(), groups = [];
    keys.forEach(function (k) {
      for (var g = 0; g < groups.length; g++) {
        if (edgesMatch(k, groups[g][0], orientation)) { groups[g].push(k); return; }
      }
      groups.push([k]);
    });
    return groups;
  }
  // axesKey -> link index string, for axes in a group of >=2 only (a lone,
  // incompatible mesh has nothing to link to and gets no badge/checkbox --
  // mirrors indexCount/showLink in the frame-slider setup below).
  function sliceLinkIndexOf(groups) {
    var linkIndexOf = {};
    groups.forEach(function (g, gi) {
      if (g.length < 2) return;
      g.forEach(function (k) { linkIndexOf[k] = 'slice' + gi; });
    });
    return linkIndexOf;
  }

  // Ensure the cursor line for `key` exists, appended to the outer,
  // untransformed <svg> and positioned with already-final pixel coordinates
  // (toPixel against the *current* CUR[key]) -- like the rubber-band box
  // and point-pick pins, not inside g#zoom{key}, which carries its own
  // separate META->CUR CSS matrix() transform (applyAxesTransform) that
  // would double-apply on top of coordinates already computed for the
  // current view.
  function drawCursor(key, orientation, coord) {
    var st = SLICE_STATE[key] || (SLICE_STATE[key] = {});
    var m = CUR[key];
    if (!m) return;
    if (!st.cursorEl) {
      var el = document.createElementNS(SVGNS, 'line');
      el.setAttribute('class', 'plotpress-slice-cursor');
      el.setAttribute('stroke', '#d62728');
      el.setAttribute('stroke-dasharray', '4,3');
      svg.appendChild(el);
      st.cursorEl = el;
    }
    st.cursorEl.setAttribute('stroke-width', 1 / sliceScale());
    if (orientation === 'x') {
      var py = toPixel(m, m.xmin, coord).y;
      st.cursorEl.setAttribute('x1', m.x); st.cursorEl.setAttribute('x2', m.x + m.w);
      st.cursorEl.setAttribute('y1', py); st.cursorEl.setAttribute('y2', py);
    } else {
      var px = toPixel(m, coord, m.ymin).x;
      st.cursorEl.setAttribute('y1', m.y); st.cursorEl.setAttribute('y2', m.y + m.h);
      st.cursorEl.setAttribute('x1', px); st.cursorEl.setAttribute('x2', px);
    }
  }

  // The value axis' bounds for one slice under the current range mode --
  // shared by the in-place 1-D view and the companion strip so both read the
  // same 'auto'/'colorbar'/'custom' choice identically. Never degenerate
  // (vmin === vmax would divide by zero placing anything on it).
  // The *unsliced* (shared) axis' own ticks -- exactly the ones rebuildTicks
  // draws on the heatmap, so the strip's gridlines sit on the heatmap's ticks
  // and the replace view relabels that axis the way it was already labelled.
  // resolveAxisTicks, not axisTicks: the latter only knows "nice numbers" plus
  // log, and silently drops this axis' categories, locator, date handling and
  // format -- an axes with set_xlocator({"kind": "multiple", "base": 2.5})
  // ticked 0/2.5/5/7.5/10 on the heatmap and 0/2/4/6/8/10 here. Limits are
  // passed in CUR's own order (not min/max-normalized) for the same reason
  // rebuildTicks does: an inverted axis must resolve to the same ticks there
  // as here, and toPixel already places them correctly either way.
  // Null for an axes rebuildTicks itself leaves alone -- fixed ticks or
  // axis_off -- where nothing here can reproduce what is actually drawn.
  function spatialTicks(key, isX) {
    var om = META[key], m = CUR[key];
    if (!om || !m || om.axis_off || om.xfixed || om.yfixed) return null;
    return isX ? resolveAxisTicks(om, m.xmin, m.xmax, m.xscale, true)
               : resolveAxisTicks(om, m.ymin, m.ymax, m.yscale, false);
  }
  function sliceValueRange(key, finiteYs) {
    var entryForRange = meshEntryForAxes(key);
    var vmin, vmax;
    if (SLICE_RANGE_MODE === 'colorbar' && entryForRange
       && isFiniteNum(entryForRange.vmin) && isFiniteNum(entryForRange.vmax)) {
      vmin = entryForRange.vmin; vmax = entryForRange.vmax;
    } else if (SLICE_RANGE_MODE === 'custom' && isFiniteNum(SLICE_CUSTOM_MIN)
              && isFiniteNum(SLICE_CUSTOM_MAX) && SLICE_CUSTOM_MIN < SLICE_CUSTOM_MAX) {
      vmin = SLICE_CUSTOM_MIN; vmax = SLICE_CUSTOM_MAX;
    } else {
      // 'auto' (or 'custom' with nothing valid typed in yet) -- the
      // slice's own min/max.
      vmin = Math.min.apply(null, finiteYs); vmax = Math.max.apply(null, finiteYs);
    }
    if (vmin === vmax) { vmin -= 0.5; vmax += 0.5; }
    return { vmin: vmin, vmax: vmax };
  }

  // ---- companion panel -----------------------------------------------------
  // Shows the profile beside the heatmap instead of in place of it, by
  // splitting the mesh axes' *own* rect: a strip (above the heatmap for an X
  // slice, to its left for a Y slice) holds the profile, and the heatmap
  // shrinks into the rest. Nothing outside that rect moves -- the same
  // "only ever touch your own pre-computed rect" rule every other tool here
  // relies on, which a true sibling axes (needing the JS to reflow the whole
  // figure) would break.
  //
  // The shrunken heatmap rect lives in CUR[key] (x/y/w/h), so everything that
  // maps data<->pixels through CUR -- toPixel, picking, pan/zoom, pins, tick
  // rebuilds -- follows it for free; zoomAffine() maps META's rect to CUR's
  // for the artist group, and the clip rect is resized to match. The strip's
  // profile is positioned with the same CUR limits along the shared axis, so
  // it stays aligned with the heatmap through every pan/zoom.
  //
  // Skipped (the axes keeps the plain cursor + slider) only for an inset, or an
  // axes that has one -- see computeCompanionEligibility(). Twin/secondary axes
  // shrink together with their parent (overlaysOf), and fixed ticks are remapped
  // (remapFixedTicks).
  // Axes drawn on top of `key` in exactly its rect (twinx/twiny, secondary axes):
  // they share the layout, so they shrink with it.
  var OVERLAYS = null;
  function overlaysOf(key) {
    if (OVERLAYS === null) {
      OVERLAYS = {};
      for (var mk in META) {
        var m = META[mk], parent = m.twin_of != null ? m.twin_of : m.secondary_of;
        if (parent != null) (OVERLAYS[String(parent)] = OVERLAYS[String(parent)] || []).push(String(mk));
      }
    }
    return OVERLAYS[String(key)] || [];
  }
  // Which axes can take a companion strip, for all of them in one pass (a
  // per-axes scan of every other axes is quadratic -- a million rect tests at a
  // thousand axes). An axes is ruled out if it's a twin/secondary itself, or if
  // another (non-overlay) axes is nested inside it or it inside another -- an
  // inset, laid out in the original rect, wouldn't line up with a shrunken
  // heatmap. Axes are bucketed by center so only near neighbors are compared.
  // (An axis_off axes is fine: no ticks to align. Fixed ticks are remapped by
  // remapFixedTicks.)
  var COMPANION_OK = null;
  function computeCompanionEligibility() {
    COMPANION_OK = {};
    var keys = Object.keys(META), CELL = 64, buckets = {};
    var inside = function (a, b) {   // is rect a within rect b (1px slack)?
      return a.x >= b.x - 1 && a.y >= b.y - 1 && a.x + a.w <= b.x + b.w + 1 && a.y + a.h <= b.y + b.h + 1;
    };
    keys.forEach(function (k) {
      var m = META[k];
      COMPANION_OK[k] = m.secondary_of == null && m.twin_of == null;
      var bk = Math.floor((m.x + m.w / 2) / CELL) + ',' + Math.floor((m.y + m.h / 2) / CELL);
      (buckets[bk] = buckets[bk] || []).push(k);
    });
    keys.forEach(function (a) {
      var A = META[a], overlays = overlaysOf(a);
      // Any axes nested in A has its center inside A: look only at the buckets A covers.
      for (var cx = Math.floor(A.x / CELL); cx <= Math.floor((A.x + A.w) / CELL); cx++) {
        for (var cy = Math.floor(A.y / CELL); cy <= Math.floor((A.y + A.h) / CELL); cy++) {
          (buckets[cx + ',' + cy] || []).forEach(function (b) {
            if (b === a || overlays.indexOf(b) !== -1 || overlaysOf(b).indexOf(a) !== -1) return;
            if (inside(META[b], A)) { COMPANION_OK[a] = false; COMPANION_OK[b] = false; }
          });
        }
      }
    });
  }
  function companionEligible(key) {
    if (COMPANION_OK === null) computeCompanionEligibility();
    return !!COMPANION_OK[key];
  }
  // How much of the axes the strip takes: the caller's own panel_size share,
  // raised to a 28px floor so a strip on an ordinary axes stays legible --
  // but never past half the axes (or the caller's share, if they asked for
  // more than half), because that floor is a *minimum* for a normal-sized
  // panel, not a claim on one too small to hold it. Without the cap, a stack
  // of short panels (14 rows in a 5-inch figure is ~23px each) gave the strip
  // more than the whole axes and left the heatmap with a negative rect --
  // silently, since a negative width/height throws nothing, it just draws
  // nothing at all.
  function companionSize(key) {
    var o = META[key];
    var span = SLICE_ORIENTATION === 'x' ? o.h : o.w;
    var want = Math.round(span * SLICE_COMPANION_FRAC);
    return Math.max(1, Math.min(Math.max(28, want), Math.max(want, Math.floor(span / 2))));
  }
  function setClipRect(key, r) {
    var cr = document.querySelector('#clip' + key + ' rect');
    if (!cr) return;
    cr.setAttribute('x', r.x); cr.setAttribute('y', r.y);
    cr.setAttribute('width', r.w); cr.setAttribute('height', r.h);
  }
  // A colorbar attached to just this axes (see svg._render_colorbar's
  // g.plotpress-colorbar wrapper) shrinks to the heatmap's share of the rect
  // along with it, or it would run up beside the strip too. It's static SVG
  // in the axes' *original* rect, so it's remapped by the same rect change
  // the heatmap gets (y' = c.y + (y - o.y) * c.h/o.h); the gradient and the
  // tick spacing scale with it, while the tick labels are counter-scaled
  // around their own anchor so the text isn't squashed.
  var COLORBAR_GROUPS = null;
  function alignColorbars(key) {
    var rectMap = function (k) {   // how axes k's rect changed: y' = ty + y * sy
      var o = META[k], c = CUR[k];
      if (!o || !c) return null;
      var sy = c.h / o.h;
      return { sy: sy, ty: c.y - o.y * sy };
    };
    if (COLORBAR_GROUPS === null) COLORBAR_GROUPS = Array.prototype.slice.call(
      document.querySelectorAll('g.plotpress-colorbar'));   // static: indexed once
    COLORBAR_GROUPS.forEach(function (g) {
      var parents = (g.getAttribute('data-parents') || '').split(',');
      if (parents.indexOf(String(key)) === -1) return;
      // A colorbar shared by several axes only follows when they all changed the
      // same way (e.g. a row of meshes all sliced); otherwise it stays as drawn.
      var first = rectMap(parents[0]), agree = !!first;
      parents.forEach(function (k) {
        var m = rectMap(k);
        if (!m || !first || Math.abs(m.sy - first.sy) > 1e-9 || Math.abs(m.ty - first.ty) > 1e-6) agree = false;
      });
      var sy = agree ? first.sy : 1, ty = agree ? first.ty : 0;
      var same = Math.abs(sy - 1) < 1e-9 && Math.abs(ty) < 1e-6;
      if (same) g.removeAttribute('transform');
      else g.setAttribute('transform', 'matrix(1,0,0,' + sy + ',0,' + ty + ')');
      g.querySelectorAll('text').forEach(function (t) {
        if (same) { t.removeAttribute('transform'); return; }
        var x = t.getAttribute('x'), y = t.getAttribute('y');
        t.setAttribute('transform', 'translate(' + x + ',' + y + ') scale(1,' + (1 / sy)
                       + ') translate(' + (-x) + ',' + (-y) + ')');
      });
      g.querySelectorAll('line, rect').forEach(function (v) {
        if (same) v.removeAttribute('vector-effect');
        else v.setAttribute('vector-effect', 'non-scaling-stroke');
      });
    });
  }
  // Static tick marks/labels/grid of an axes with fixed ticks (set_xticks/
  // set_yticks) can't be rebuilt from the view (rebuildTicks leaves them as
  // rendered), so when the heatmap's rect shrinks they're remapped in place --
  // only the coordinate along the shrinking dimension, and only for what sits
  // over the heatmap: tick marks and labels on the far side of the axes stay
  // with the frame. Originals are kept on the element so this is repeatable.
  function remapFixedTicks(key) {
    var om = META[key], c = CUR[key];
    if (!om || !(om.xfixed || om.yfixed)) return;
    var g = document.getElementById('ticks' + key);
    if (!g) return;
    var sx = c.w / om.w, sy = c.h / om.h, bottom = om.y + om.h, right = om.x + om.w;
    var shrinkY = c.h !== om.h, shrinkX = c.w !== om.w;
    var my = function (y) { return (y >= om.y - 0.01 && y <= bottom + 0.01) ? c.y + (y - om.y) * sy : y; };
    var mx = function (x) { return (x >= om.x - 0.01 && x <= right + 0.01) ? c.x + (x - om.x) * sx : x; };
    g.querySelectorAll('line').forEach(function (l) {
      if (l.dataset.orig === undefined) {
        l.dataset.orig = ['x1', 'y1', 'x2', 'y2'].map(function (a) { return l.getAttribute(a); }).join(',');
      }
      var v = l.dataset.orig.split(',').map(Number);
      var x1 = v[0], y1 = v[1], x2 = v[2], y2 = v[3];
      if (shrinkY) { y1 = my(y1); y2 = my(y2); }
      if (shrinkX) {
        if (v[1] === v[3]) {
          // Horizontal: a line spanning the whole width is a grid line, which now
          // starts at the heatmap's edge; a short one starting *at* the frame is a
          // y-tick mark, which stays with the frame.
          if (v[0] <= om.x + 0.5 && v[2] >= right - 0.5) { x1 = c.x; x2 = v[2]; }
          else if (v[0] > om.x + 0.5) { x1 = mx(v[0]); x2 = mx(v[2]); }
        } else {
          x1 = mx(v[0]); x2 = mx(v[2]);
        }
      }
      l.setAttribute('x1', x1); l.setAttribute('y1', y1); l.setAttribute('x2', x2); l.setAttribute('y2', y2);
    });
    g.querySelectorAll('text').forEach(function (t) {
      if (t.dataset.orig === undefined) {
        t.dataset.orig = t.getAttribute('x') + ',' + t.getAttribute('y') + ',' + (t.getAttribute('transform') || '');
      }
      var parts = t.dataset.orig.split(','), ox = +parts[0], oy = +parts[1];
      var x = shrinkX ? mx(ox) : ox, y = shrinkY ? my(oy) : oy;
      t.setAttribute('x', x); t.setAttribute('y', y);
      if (parts.length > 2 && parts.slice(2).join(',')) {
        // A rotated label pivots on its own anchor, which just moved.
        t.setAttribute('transform', parts.slice(2).join(',').replace(
          /rotate\(([-\d.]+)[ ,]+[-\d.]+[ ,]+[-\d.]+\)/, 'rotate($1 ' + x + ' ' + y + ')'));
      }
    });
  }
  // Puts one axes' rect (and everything derived from it) at (ex, ey, ew, eh).
  function setAxesRect(k, ex, ey, ew, eh, anchor) {
    var c = CUR[k];
    c.x = ex; c.y = ey; c.w = ew; c.h = eh;
    // A Y slice's strip sits between the y tick labels and the heatmap, so
    // those stay at the axes' original left edge, not the heatmap's.
    if (anchor === null) delete c.tickAnchorX; else c.tickAnchorX = anchor;
    setClipRect(k, c);
    applyAxesTransform(k); rebuildTicks(k); remapFixedTicks(k); relayoutPins(k);
    relayoutTextCounterScale(k);
    alignColorbars(k);
  }
  // Puts `key` and every axes overlaid on it (twinx/twiny, secondary) in the
  // rect (ex, ey, ew, eh), skipping whichever are already there. Each is
  // checked on its own rather than gating all of them on the parent's rect:
  // resetAxesOne() puts a single axes back in META's full rect (a double-click
  // reset, or Reset All Axes reaching the twin after the parent), so "the
  // parent already matches" is no reason to leave a twin stranded unsplit,
  // with its ticks spread over a rect its parent's heatmap no longer fills.
  function setAxesRectWithOverlays(key, ex, ey, ew, eh, anchor) {
    [key].concat(overlaysOf(key)).forEach(function (k) {
      var c = CUR[k];
      if (!c) return;
      if (c.x !== ex || c.y !== ey || c.w !== ew || c.h !== eh
          || (anchor === null) !== (c.tickAnchorX == null)) {
        setAxesRect(k, ex, ey, ew, eh, anchor);
      }
    });
  }
  function ensureCompanionLayout(key) {
    var o = META[key];
    var s = companionSize(key);
    var ex = o.x, ey = o.y, ew = o.w, eh = o.h, anchor = null;
    if (SLICE_ORIENTATION === 'x') { ey = o.y + s; eh = o.h - s; }
    else { ex = o.x + s; ew = o.w - s; anchor = o.x; }
    setAxesRectWithOverlays(key, ex, ey, ew, eh, anchor);
    return s;
  }
  function removeCompanion(key) {
    var st = SLICE_STATE[key];
    if (st && st.compGroup) {
      st.compGroup.remove(); st.compGroup = null;
      // Nothing left for them to point at -- unless the replace view is taking over
      // as the profile, in which case they carry across.
      if (!SLICE_VIEW_ON) removeSlicePins(key);
    }
    var o = META[key];
    if (!o || !CUR[key]) return;
    setAxesRectWithOverlays(key, o.x, o.y, o.w, o.h, null);
  }
  function companionClip(key, r) {
    var id = 'sliceclip' + key;
    var cp = document.getElementById(id);
    if (!cp) {
      var defs = svg.querySelector('defs');
      if (!defs) { defs = document.createElementNS(SVGNS, 'defs'); svg.insertBefore(defs, svg.firstChild); }
      cp = document.createElementNS(SVGNS, 'clipPath');
      cp.setAttribute('id', id);
      cp.appendChild(document.createElementNS(SVGNS, 'rect'));
      defs.appendChild(cp);
    }
    var cr = cp.firstChild;
    cr.setAttribute('x', r.x); cr.setAttribute('y', r.y);
    cr.setAttribute('width', r.w); cr.setAttribute('height', r.h);
    return 'url(#' + id + ')';
  }
  // Maps a slice sample to its spot in the strip -- the one place that knows
  // the strip's geometry, shared by drawing the profile and by Point Picking
  // pins on it (slicePinPoint), so a pin can never disagree with the line it
  // sits on. Null when the whole slice is NaN.
  // Which profile view (if any) is currently showing for an axes -- the strip
  // beside the heatmap, or the profile drawn in the heatmap's place.
  function profileMode(key) {
    var st = SLICE_STATE[key];
    if (!st || typeof st.index !== 'number') return null;
    if (st.compGroup) return 'companion';
    if (SLICE_VIEW_ON && st.sliceEl) return 'replace';
    return null;
  }
  function companionPlacer(key, slice, mode) {
    var o = META[key], m = CUR[key];
    var finiteYs = slice.ys.filter(isFiniteNum);
    if (!finiteYs.length) return null;
    var isX = SLICE_ORIENTATION === 'x', replace = mode === 'replace';
    // The area the profile is drawn in: the strip carved out of the axes, or (for
    // the replace view) the whole heatmap rect -- with no inner margin there,
    // matching how renderMeshOrSlice draws that line.
    var s = replace ? (isX ? m.h : m.w) : companionSize(key), pad = replace ? 0 : 4;
    var R = replace ? { x: m.x, y: m.y, w: m.w, h: m.h }
                    : (isX ? { x: o.x, y: o.y, w: o.w, h: s } : { x: o.x, y: o.y, w: s, h: o.h });
    var range = sliceValueRange(key, finiteYs), vmin = range.vmin, vmax = range.vmax;
    var span = s - 2 * pad;
    var off = function (v) { return pad + (v - vmin) / (vmax - vmin) * span; };
    return {
      s: s, isX: isX, vmin: vmin, vmax: vmax, off: off, strip: R,
      // Where sample j sits along the shared axis (the heatmap's own x for an
      // X slice, y for a Y slice) -- independent of its value.
      along: function (j) {
        return isX ? toPixel(m, slice.xs[j], m.ymin).x : toPixel(m, m.xmin, slice.xs[j]).y;
      },
      // Pixel position of sample j; null if its value is missing.
      at: function (j) {
        var v = slice.ys[j];
        if (!isFiniteNum(v)) return null;
        var along = isX ? toPixel(m, slice.xs[j], m.ymin).x : toPixel(m, m.xmin, slice.xs[j]).y;
        return isX ? { px: along, py: R.y + R.h - off(v) } : { px: R.x + off(v), py: along };
      }
    };
  }
  function drawCompanion(key, slice) {
    var st = SLICE_STATE[key], o = META[key];
    if (!st.compGroup) {
      st.compGroup = document.createElementNS(SVGNS, 'g');
      st.compGroup.setAttribute('class', 'plotpress-slice-companion');
      svg.appendChild(st.compGroup);
    }
    var pl = companionPlacer(key, slice);
    var s = companionSize(key), isX = SLICE_ORIENTATION === 'x';
    var parts = [];
    var sepCol = STYLE.spine || '#444', fs = Math.max(8, (STYLE.tick_label_size || 10) - 1);
    var txtCol = STYLE.text || '#222';
    if (pl) {
      var tk = axisTicks(pl.vmin, pl.vmax, 'linear');
      var guides = [], labels = [], lastLabelOff = -Infinity;
      for (var j = 0; j < tk.ticks.length; j++) {
        var off = pl.off(tk.ticks[j]);
        // The strip is only a few labels tall/wide -- drop any that would
        // run into the previous one rather than print them on top of each
        // other.
        if (off - lastLabelOff < (isX ? fs + 4 : 26)) continue;
        lastLabelOff = off;
        if (isX) {
          var gy = o.y + s - off;
          guides.push('<line x1="' + o.x + '" y1="' + gy.toFixed(2) + '" x2="' + (o.x + o.w) + '" y2="' + gy.toFixed(2) + '"/>');
          labels.push('<text x="' + (o.x + 3) + '" y="' + (gy + 3).toFixed(2) + '" text-anchor="start">' + tk.labels[j] + '</text>');
        } else {
          var gx = o.x + off;
          guides.push('<line x1="' + gx.toFixed(2) + '" y1="' + o.y + '" x2="' + gx.toFixed(2) + '" y2="' + (o.y + o.h) + '"/>');
          labels.push('<text x="' + gx.toFixed(2) + '" y="' + (o.y + o.h + fs + 3) + '" text-anchor="middle">' + tk.labels[j] + '</text>');
        }
      }
      if (SLICE_GRID) {
        // Along the shared axis too: the heatmap's own tick positions, so a
        // vertical (X slice) or horizontal (Y slice) line lines up with its
        // ticks. None when spatialTicks() can't say where those are (fixed
        // ticks, axis_off) -- a guide that claims to mark a tick and doesn't
        // is worse than no guide, so only the value guides are drawn there.
        var mm = CUR[key];
        var stk2 = spatialTicks(key, isX) || { ticks: [] };
        for (var g2 = 0; g2 < stk2.ticks.length; g2++) {
          if (isX) {
            var ax2 = toPixel(mm, stk2.ticks[g2], mm.ymin).x;
            guides.push('<line x1="' + ax2.toFixed(2) + '" y1="' + o.y + '" x2="' + ax2.toFixed(2) + '" y2="' + (o.y + s) + '"/>');
          } else {
            var ay2 = toPixel(mm, mm.xmin, stk2.ticks[g2]).y;
            guides.push('<line x1="' + o.x + '" y1="' + ay2.toFixed(2) + '" x2="' + (o.x + s) + '" y2="' + ay2.toFixed(2) + '"/>');
          }
        }
        parts.push('<g stroke="#e3e3e3" stroke-width="0.8" clip-path="' + companionClip(key, pl.strip) + '">' + guides.join('') + '</g>');
      }
      // Inside the strip with a white halo, not out in the gutter: the gap
      // between neighboring axes is too narrow to hold a value label.
      parts.push('<g font-size="' + fs + '" fill="' + txtCol
        + '" stroke="#fff" stroke-width="3" paint-order="stroke">' + labels.join('') + '</g>');
      var d = '', started = false;
      for (var i = 0; i < slice.xs.length; i++) {
        var q = pl.at(i);
        if (!q) { started = false; continue; }
        d += (started ? 'L' : 'M') + q.px.toFixed(2) + ',' + q.py.toFixed(2);
        started = true;
      }
      parts.push('<path d="' + d + '" fill="none" stroke="#1f77b4" stroke-width="1.5" clip-path="' + companionClip(key, pl.strip) + '"/>');
    }
    // What the strip shows: the fixed coordinate the cursor sits on.
    var caption = (isX ? 'y = ' : 'x = ') + fmt(slice.fixedCoord);
    parts.push('<text x="' + (isX ? o.x + o.w - 4 : o.x + s - 3) + '" y="' + (o.y + fs + 2)
      + '" text-anchor="end" font-size="' + fs + '" fill="#666">' + caption + '</text>');
    parts.push(isX
      ? '<line x1="' + o.x + '" y1="' + (o.y + s) + '" x2="' + (o.x + o.w) + '" y2="' + (o.y + s) + '" stroke="' + sepCol + '"/>'
      : '<line x1="' + (o.x + s) + '" y1="' + o.y + '" x2="' + (o.x + s) + '" y2="' + (o.y + o.h) + '" stroke="' + sepCol + '"/>');
    st.compGroup.innerHTML = parts.join('');
  }

  // ---- Point Picking on the companion strip --------------------------------
  // A pin on the profile is a {kind: 'slice', axes} anchor whose index is a
  // sample along the shared axis. It's re-resolved from the *current* slice
  // every time (pan/zoom, slider step), so it rides the line as it moves and
  // reports the value the slice holds now; arrow keys step along it. Only the
  // companion strip is pickable this way -- the in-place 1-D view isn't wired
  // up -- and a pin is dropped when its strip goes away.
  function slicePinPoint(key, j) {
    var st = SLICE_STATE[key], mode = profileMode(key);
    if (!mode) return null;
    var slice = computeSliceByIndex(key, SLICE_ORIENTATION, st.index);
    var pl = slice && companionPlacer(key, slice, mode);
    if (!pl) return null;
    j = Math.max(0, Math.min(slice.xs.length - 1, j));
    var R = pl.strip, isX = SLICE_ORIENTATION === 'x';
    var v = slice.ys[j], finite = isFiniteNum(v);
    var al = pl.along(j), lo = isX ? R.x : R.y, hi = isX ? R.x + R.w : R.y + R.h;
    // Hidden -- not drawn at all -- while there's nothing to point at: the
    // sample has no value right now (NaN under the slider), or it's been
    // panned/zoomed out of the strip's own extent along the shared axis.
    var hidden = !finite || al < lo || al > hi;
    // A value past the strip's range (a fixed colorbar/custom range, while
    // the slider plays) would put the pin outside the strip, where the line
    // itself is clipped away. It stays on the strip's edge instead, its label
    // still carrying the true value -- with the value drawn red (see
    // applySliceVisibility) to say it's off the scale.
    var off = finite ? pl.off(v) : pl.s / 2, edge = 2, past = null;
    if (off > pl.s - edge) { off = pl.s - edge; past = 'hi'; }
    else if (off < edge) { off = edge; past = 'lo'; }
    al = Math.max(lo, Math.min(hi, al));
    var q = isX ? { px: al, py: R.y + R.h - off } : { px: R.x + off, py: al };
    var entry = meshEntryForAxes(key) || {};
    var name = entry.name || 'z';
    var x = isX ? slice.xs[j] : slice.fixedCoord, y = isX ? slice.fixedCoord : slice.xs[j];
    return { px: q.px, py: q.py, index: j, x: x, y: y, z: v, name: name,
             hidden: hidden, past: past,
             // Only the coordinate along the profile: the slice's own fixed
             // coordinate is already shown in the strip's corner (drawCompanion).
             label: (isX ? 'x=' + fmt(x) : 'y=' + fmt(y)) + ', ' + name + '=' + fmt(v) };
  }
  // Per-slice state of a strip pin, applied after every layout: hidden while
  // there is nothing to point at, and the value in its label drawn red while
  // it's clamped to the strip's edge (off the scale). The label is one <text>,
  // so the value is split out into its own red <tspan> here.
  function applySliceVisibility(g) {
    if (g.dataset.kind !== 'slice') return;
    var sp = slicePinPoint(g.dataset.axes, +g.dataset.index);
    // No sp at all -- the whole slice is NaN, so companionPlacer() has no
    // value range to place anything against -- is just as much "nothing to
    // point at" as one missing sample (sp.hidden) is. Treating it as "leave
    // the pin alone" left it sitting over a blank profile, still showing the
    // value from the last row that had one.
    g.style.display = (!sp || sp.hidden) ? 'none' : '';
    var text = g.querySelector('text');
    if (!text) return;
    var plain = text.textContent, m = /^(.*, )([^,=]+=[^,]*)$/.exec(plain);
    text.textContent = plain;
    if (sp && sp.past && m) {
      text.textContent = '';
      text.appendChild(document.createTextNode(m[1]));
      var red = document.createElementNS(SVGNS, 'tspan');
      red.setAttribute('fill', '#dc1f1f'); red.setAttribute('font-weight', 'bold');
      // A darker red needs a light halo to stay legible on the dark, teal and
      // purple label boxes.
      red.setAttribute('stroke', '#fff'); red.setAttribute('stroke-width', 2);
      red.setAttribute('paint-order', 'stroke');
      red.textContent = m[2];
      text.appendChild(red);
    }
  }
  // Pins anchored in an axes' own data space -- every kind but 'slice', plus
  // the un-kinded geometric readout pins -- have nothing left to point at
  // while the replace view stands in for that data: the series they sit on is
  // hidden (see renderMeshOrSlice's dataEls) and the vertical axis now reads
  // in the slice's value, so a label saying "y=0.125, z=1.212" would sit at
  // the y=0.125 pixel of an axis that no longer means y. They are hidden with
  // the same class the series use, which keeps this on its own channel:
  // Hide Points' body class and the inline display applySliceVisibility()
  // writes for 'slice' pins both still compose, and a pin stays hidden while
  // any of the three wants it hidden. Hidden, never removed -- the reader
  // gets their pins back on the way out of the view.
  function setDataPinsHidden(key, hidden) {
    var k = String(key);
    livePins().forEach(function (pin) {
      if (pinAxesKey(pin) !== k || pin.dataset.kind === 'slice') return;
      if (hidden) {
        pin.classList.add('plotpress-slice-hidden');
        // A hidden pin can still be selectedPin -- nothing else clears that
        // on this path -- so an arrow key would silently keep stepping it
        // with no on-screen feedback at all. selectPin(null) deselects it
        // properly (clears .selected, the enlarged dot, the leader line)
        // rather than leaving it selected-but-invisible; the reader gets it
        // back by clicking again once it's showing.
        if (selectedPin === pin) selectPin(null);
      } else {
        pin.classList.remove('plotpress-slice-hidden');
      }
    });
  }
  function sliceStripPick(p) {
    var best = null;
    Object.keys(SLICE_STATE).forEach(function (key) {
      var st = SLICE_STATE[key], mode = profileMode(key);
      if (!mode || (CUR[key] && CUR[key].pickable === false)) return;
      var slice = computeSliceByIndex(key, SLICE_ORIENTATION, st.index);
      var pl = slice && companionPlacer(key, slice, mode);
      if (!pl) return;
      // The profile's own area: the strip, or -- in the replace view, where the
      // heatmap is hidden -- the whole axes, so a click anywhere in it picks the
      // nearest sample of the profile rather than a hidden heatmap cell.
      var R = pl.strip, isX = pl.isX;
      if (!(p.x >= R.x && p.x <= R.x + R.w && p.y >= R.y && p.y <= R.y + R.h)) return;
      var lo = isX ? R.x : R.y, hi = isX ? R.x + R.w : R.y + R.h;
      for (var j = 0; j < slice.xs.length; j++) {
        var q = pl.at(j);
        if (!q) continue;
        var along = isX ? q.px : q.py;
        if (along < lo || along > hi) continue;   // panned/zoomed out of view
        var d = Math.abs(along - (isX ? p.x : p.y));
        if (!best || d < best.d) best = { d: d, ref: { kind: 'slice', axes: key, index: j } };
      }
    });
    return best ? best.ref : null;
  }
  function relayoutSlicePins(keys) {
    var pins = livePins();
    for (var i = 0; i < pins.length; i++) {
      var pin = pins[i];
      if (pin.dataset.kind !== 'slice') continue;
      if (keys.indexOf(String(pin.dataset.axes)) === -1) continue;
      var a = resolve(pinAnchor(pin), +pin.dataset.index);
      // layoutPin() ends in applySliceVisibility(); when there is nothing to
      // resolve to at all there is no layout to do, but the pin still has to
      // be told to hide itself -- so call it directly on that path.
      if (a) layoutPin(pin, a.px, a.py, pinLabel(pin, a.label));
      else applySliceVisibility(pin);
    }
  }
  function removeSlicePins(key) {
    var pins = document.querySelectorAll('.plotpress-pin[data-kind="slice"]');
    for (var i = 0; i < pins.length; i++) {
      if (key === undefined || String(pins[i].dataset.axes) === String(key)) pins[i].remove();
    }
  }
  // "Snap pins to slice" links pins on the heatmap and pins on the profile in
  // both directions while it's on. A Point Picking pin on the heatmap gets a
  // mirror on the profile (same position along the shared axis, dropped onto
  // the shown slice's line); a pin placed on the profile gets a mirror on the
  // heatmap (the cell it points at on the shown row/column). Either way the
  // original stays put and the mirror is a separate pin marked
  // .plotpress-snapped, which follows the slice like any pin. Mirrors are
  // reconciled against their sources on every change to the pins, the view or
  // the slider (see syncSnappedPins), kept out of Extract and Save (the
  // original is what carries the data) and out of right-click delete (it would
  // only be rebuilt). Annotate notes and pins on a different mesh get none.
  // Each pair's two labels share a color -- the only thing marking them as
  // linked (the dots are drawn like any other pin's).
  var SNAP_LINK_COLORS = ['#0f766e', '#6d28d9', '#be185d', '#15803d', '#1d4ed8', '#b91c1c'];
  var SNAP_COLOR_NEXT = 0;
  var snapSyncing = false;   // creating a mirror must not trigger another sync
  function heatmapPinSample(pin) {
    var kind = pin.dataset.kind, key = pin.dataset.axes;
    if ((kind !== 'mesh' && kind !== 'meshframe') || key === undefined) return null;
    var info = SLICE_AXES[key];
    if (!info) return null;
    var mesh;
    if (kind === 'mesh') {
      if (info.meshIndex === undefined || +pin.dataset.mesh !== info.meshIndex) return null;
      mesh = PICK[key].meshes[info.meshIndex];
    } else {
      if (!info.frameEntry || info.frameEntry.id !== pin.dataset.frameId) return null;
      mesh = info.frameEntry;
    }
    var cell = +pin.dataset.index, nx = mesh.shape[1];
    return { key: key, j: SLICE_ORIENTATION === 'x' ? cell % nx : Math.floor(cell / nx) };
  }
  // Marks `mirror` as the linked twin of `source`: same label color, and the
  // color is kept on the source for good so deleting another pin never
  // recolors it.
  function linkPins(source, mirror) {
    mirror.classList.add('plotpress-snapped');
    mirror.dataset.snapped = '1';
    if (source.dataset.linkColor === undefined) {
      source.dataset.linkColor = SNAP_COLOR_NEXT++ % SNAP_LINK_COLORS.length;
    }
    var color = SNAP_LINK_COLORS[+source.dataset.linkColor];
    var srcBox = source.querySelector('rect'), mirrorBox = mirror.querySelector('rect');
    if (srcBox) srcBox.setAttribute('fill', color);
    if (mirrorBox) mirrorBox.setAttribute('fill', color);
  }
  var SNAP_UID_NEXT = 0;
  function snapUid(pin) {
    if (pin.dataset.snapUid === undefined) pin.dataset.snapUid = SNAP_UID_NEXT++;
    return pin.dataset.snapUid;
  }
  function anchorsEqual(a, b) {
    if (!a || !b || a.kind !== b.kind || String(a.axes) !== String(b.axes)) return false;
    if (a.kind === 'mesh') return +a.mesh === +b.mesh;
    if (a.kind === 'meshframe') return a.id === b.id;
    return true;
  }
  // The mirror a source pin should have right now -- {anchor, index} -- or
  // null when it shouldn't have one (nothing there to point at).
  function snapMirrorSpec(pin) {
    if (pin.dataset.kind === 'slice') return stripPinMirrorSpec(pin);
    var at = heatmapPinSample(pin);
    if (!at || !slicePinPoint(at.key, at.j)) return null;
    return { anchor: { kind: 'slice', axes: at.key }, index: at.j };
  }
  // A pin placed on the profile mirrors onto the heatmap cell it points at --
  // the sample it sits on along the shared axis, on the row (X slice) or
  // column (Y slice) the slider is showing.
  function stripPinMirrorSpec(pin) {
    var key = pin.dataset.axes, info = SLICE_AXES[key], st = SLICE_STATE[key];
    if (!info || !st || typeof st.index !== 'number') return null;
    var sp = slicePinPoint(key, +pin.dataset.index);
    if (!sp || !isFiniteNum(sp.z)) return null;   // no value there to point at
    var mesh = info.frameEntry || PICK[key].meshes[info.meshIndex];
    var ny = mesh.shape[0], nx = mesh.shape[1], isX = SLICE_ORIENTATION === 'x';
    var row = Math.min(ny - 1, isX ? st.index : sp.index);
    var col = Math.min(nx - 1, isX ? sp.index : st.index);
    var anchor = info.frameEntry
      ? { kind: 'meshframe', axes: key, id: info.frameEntry.id, unit: info.frameEntry.unit }
      : { kind: 'mesh', axes: key, mesh: info.meshIndex };
    return { anchor: anchor, index: row * nx + col };
  }
  // Reconciles mirrors against their source pins *in place*: an existing
  // mirror is re-pointed (index, position, label) rather than torn down and
  // rebuilt, so what the user did to it -- dragging its label box somewhere
  // -- survives a slider step. Only a mirror whose source is gone, or whose
  // target changed kind, is removed.
  function syncSnappedPins() {
    if (snapSyncing) return;
    snapSyncing = true;
    try {
      var keep = selectedPin;
      var mirrors = {};
      document.querySelectorAll('.plotpress-snapped').forEach(function (m) {
        mirrors[m.dataset.snapOf] = m;
      });
      // Back to the ordinary label color everywhere; linkPins() recolors
      // whichever pins are (still) linked.
      document.querySelectorAll('.plotpress-pin:not(.plotpress-note) rect').forEach(function (r) {
        r.setAttribute('fill', '#111');
      });
      var wanted = {};
      if (SLICE_SNAP && SLICE_ENABLED && SLICE_COMPANION_ON) {
        var pins = document.querySelectorAll(
          '.plotpress-pin:not(.plotpress-note):not(.plotpress-snapped)');
        for (var i = 0; i < pins.length; i++) {
          var pin = pins[i], spec = snapMirrorSpec(pin);
          if (!spec) continue;
          var uid = snapUid(pin), m = mirrors[uid];
          wanted[uid] = true;
          if (m && anchorsEqual(spec.anchor, pinAnchor(m))) {
            m.dataset.index = spec.index;
            var a = resolve(spec.anchor, spec.index);
            if (a) { m.dataset.index = a.index; layoutPin(m, a.px, a.py, pinLabel(m, a.label)); }
            linkPins(pin, m);
          } else {
            if (m) m.remove();
            var g = addAnchoredPin(spec.anchor, spec.index);
            if (g) { g.dataset.snapOf = uid; linkPins(pin, g); }
          }
        }
      }
      Object.keys(mirrors).forEach(function (uid) {
        if (!wanted[uid]) mirrors[uid].remove();
      });
      // Adding a pin selects it; hand the selection back to whatever the user
      // actually had selected (arrow keys must keep stepping *their* pin).
      if (keep && keep.isConnected) selectPin(keep);
      else if (selectedPin && !selectedPin.isConnected) selectedPin = null;
    } finally {
      snapSyncing = false;
    }
  }

  // The one render entry point, called by a slider's own setIndex()/
  // external() and by resyncSlice() on pan/zoom: draws whichever of the two
  // views (pcolormesh+cursor, or the 1-D slice line) SLICE_VIEW_ON selects
  // for this axes at its slider's current `index`. The red cursor line
  // only ever belongs on the pcolormesh -- it marks a position *on* the 2-D
  // image, not on the 1-D profile derived from it -- so it's created only
  // in that branch and torn down in the other, never both at once.
  function renderMeshOrSlice(key, index) {
    var m = CUR[key];
    if (!m) return;
    var st = SLICE_STATE[key] || (SLICE_STATE[key] = {});
    st.orientation = SLICE_ORIENTATION; st.index = index;
    // Everything the axes draws in its own data space: the mesh, and anything
    // overlaid on it (a plot() line, a scatter()). The replace view hides all
    // of it, not just the mesh -- it re-labels the vertical axis in the
    // slice's value, so a line drawn at y=0.5 would otherwise keep the y=0.5
    // *pixel* while the ticks beside it started reading in z, claiming a
    // value it never had. All-or-nothing on purpose: for an X slice the
    // horizontal axis does survive, so a strictly vertical line would still
    // have been readable, but singling those out would hide one series and
    // keep another for reasons the reader cannot see.
    // Both selectors are needed. A QuadMesh/Image artist reaches the page as
    // either a raster <image> (large/uniform grids) or a vectorized <g> of
    // <rect>s (a small non-uniform one, see artists._resolve_mesh_render);
    // .plotpress-mesh is carried by both precisely so Slice can hide
    // whichever one this mesh used, and the vectorized <g> is not itself a
    // .plotpress-series -- matching on that alone missed it entirely, leaving
    // its rects visible underneath the slice line.
    var dataEls = svg.querySelectorAll(
      '#zoom' + key + ' .plotpress-mesh, #zoom' + key + ' .plotpress-series');
    var origTicks = document.getElementById('ticks' + key);

    if (!SLICE_VIEW_ON) {
      dataEls.forEach(function (im) { im.classList.remove('plotpress-slice-hidden'); });
      setDataPinsHidden(key, false);
      if (origTicks) origTicks.style.display = '';
      if (st.sliceEl) {
        st.sliceEl.remove(); st.sliceEl = null;
        if (!SLICE_COMPANION_ON) removeSlicePins(key);   // (the strip, if it's next, keeps them)
      }
      if (st.tickGroup) { st.tickGroup.remove(); st.tickGroup = null; }
      var slice0 = computeSliceByIndex(key, SLICE_ORIENTATION, index);
      // The panel first: it shrinks CUR[key] to the heatmap's share of the
      // rect, which the cursor line below has to be positioned against.
      if (SLICE_COMPANION_ON && slice0 && companionEligible(key)) {
        ensureCompanionLayout(key);
        drawCompanion(key, slice0);
      } else {
        removeCompanion(key);
      }
      if (slice0) drawCursor(key, SLICE_ORIENTATION, slice0.fixedCoord);
      return;
    }
    // The 1-D view replaces the heatmap in the full rect, so any strip
    // (and the shrunken heatmap rect it needed) has to go first.
    removeCompanion(key);
    // Slice view: no cursor line here (see above) -- remove one left over
    // from before the toggle switched.
    if (st.cursorEl) { st.cursorEl.remove(); st.cursorEl = null; }
    var slice = computeSliceByIndex(key, SLICE_ORIENTATION, index);
    if (!slice) return;
    var finiteYs = slice.ys.filter(isFiniteNum);
    if (!finiteYs.length) {
      // Nothing to draw on this row/column -- every value is NaN. Returning
      // here without clearing left the *previous* row's line and value ticks
      // on screen under the new slider position: the reader saw a profile
      // that said row 4 and plotted row 3. Blank the view instead, the same
      // as the companion strip does (drawCompanion's own `if (pl)`), keeping
      // the heatmap hidden since this view is still standing in for it.
      dataEls.forEach(function (im) { im.classList.add('plotpress-slice-hidden'); });
      setDataPinsHidden(key, true);
      if (origTicks) origTicks.style.display = 'none';
      if (st.sliceEl) st.sliceEl.setAttribute('d', '');
      if (st.tickGroup) { st.tickGroup.remove(); st.tickGroup = null; }
      return;
    }
    var range = sliceValueRange(key, finiteYs), vmin = range.vmin, vmax = range.vmax;
    dataEls.forEach(function (im) { im.classList.add('plotpress-slice-hidden'); });
    setDataPinsHidden(key, true);

    var d = '', started = false;
    for (var i = 0; i < slice.xs.length; i++) {
      if (!isFiniteNum(slice.ys[i])) { started = false; continue; }
      var px, py;
      var frac = (slice.ys[i] - vmin) / (vmax - vmin);
      if (SLICE_ORIENTATION === 'x') {
        px = toPixel(m, slice.xs[i], m.ymin).x;
        py = m.y + m.h - frac * m.h;
      } else {
        py = toPixel(m, m.xmin, slice.xs[i]).y;
        px = m.x + frac * m.w;
      }
      d += (started ? 'L' : 'M') + px.toFixed(2) + ',' + py.toFixed(2);
      started = true;
    }
    if (!st.sliceEl) {
      st.sliceEl = document.createElementNS(SVGNS, 'path');
      st.sliceEl.setAttribute('class', 'plotpress-slice-line');
      st.sliceEl.setAttribute('fill', 'none');
      st.sliceEl.setAttribute('stroke', '#1f77b4');
      st.sliceEl.setAttribute('stroke-width', 1.5);
      // The line lives on the outer <svg> (already-final pixel coords), so
      // it doesn't inherit the axes' own clip; a value outside the chosen
      // colorbar/custom range would otherwise run out past the axes box.
      st.sliceEl.setAttribute('clip-path', 'url(#clip' + key + ')');
      svg.appendChild(st.sliceEl);
    }
    st.sliceEl.setAttribute('d', d);

    // The normal tick group draws both axes' ticks as one mixed unit (see
    // rebuildTicks) -- nothing to selectively keep "just the unsliced
    // dimension's" from it, so it's hidden outright and both dimensions'
    // ticks are redrawn here instead: value ticks (axisTicks() over the
    // slice's own min/max -- the same "nice numbers" generator the rest of
    // this file already uses for a real zoomed axis, jsNiceTicks) along
    // whichever edge the sliced dimension occupies, and the *unsliced*
    // dimension's own real, unchanged spatial ticks along its own edge, so
    // the view doesn't lose all axis context while a slice is showing.
    // Rebuilt fresh every call (removed, not diffed).
    if (origTicks) origTicks.style.display = 'none';
    if (st.tickGroup) st.tickGroup.remove();
    st.tickGroup = document.createElementNS(SVGNS, 'g');
    st.tickGroup.setAttribute('class', 'plotpress-slice-ticks');
    var tk = axisTicks(vmin, vmax, 'linear');
    var gridPath = '';   // gridlines share the tick positions computed below
    var gridLine = function (x1, y1, x2, y2) {
      gridPath += 'M' + x1.toFixed(2) + ',' + y1.toFixed(2) + 'L' + x2.toFixed(2) + ',' + y2.toFixed(2);
    };
    for (var j = 0; j < tk.ticks.length; j++) {
      var frac2 = (tk.ticks[j] - vmin) / (vmax - vmin);
      if (SLICE_GRID) {
        if (SLICE_ORIENTATION === 'x') gridLine(m.x, m.y + m.h - frac2 * m.h, m.x + m.w, m.y + m.h - frac2 * m.h);
        else gridLine(m.x + frac2 * m.w, m.y, m.x + frac2 * m.w, m.y + m.h);
      }
      var txt = document.createElementNS(SVGNS, 'text');
      if (SLICE_ORIENTATION === 'x') {
        txt.setAttribute('x', m.x - 6); txt.setAttribute('y', (m.y + m.h - frac2 * m.h + 3).toFixed(2));
        txt.setAttribute('text-anchor', 'end');
      } else {
        txt.setAttribute('x', (m.x + frac2 * m.w).toFixed(2)); txt.setAttribute('y', m.y + m.h + 12);
        txt.setAttribute('text-anchor', 'middle');
      }
      txt.textContent = tk.labels[j];
      st.tickGroup.appendChild(txt);
    }
    // The unsliced dimension keeps its own real ticks -- see spatialTicks(),
    // which resolves them the same way the heatmap's own rebuild does. Empty
    // for a fixed-tick/axis_off axes, whose statically-rendered ticks nothing
    // here can reproduce; that axes keeps the value ticks only.
    var stk = spatialTicks(key, SLICE_ORIENTATION === 'x') || { ticks: [], labels: [] };
    for (var k = 0; k < stk.ticks.length; k++) {
      var sp = (SLICE_ORIENTATION === 'x') ? toPixel(m, stk.ticks[k], m.ymin) : toPixel(m, m.xmin, stk.ticks[k]);
      if (SLICE_GRID) {
        if (SLICE_ORIENTATION === 'x') gridLine(sp.x, m.y, sp.x, m.y + m.h);
        else gridLine(m.x, sp.y, m.x + m.w, sp.y);
      }
      var stxt = document.createElementNS(SVGNS, 'text');
      if (SLICE_ORIENTATION === 'x') {
        stxt.setAttribute('x', sp.x.toFixed(2)); stxt.setAttribute('y', m.y + m.h + 12);
        stxt.setAttribute('text-anchor', 'middle');
      } else {
        stxt.setAttribute('x', m.x - 6); stxt.setAttribute('y', (sp.y + 3).toFixed(2));
        stxt.setAttribute('text-anchor', 'end');
      }
      stxt.textContent = stk.labels[k];
      st.tickGroup.appendChild(stxt);
    }
    if (gridPath) {
      // Clipped to the axes and drawn under the profile line.
      var grid = document.createElementNS(SVGNS, 'path');
      grid.setAttribute('class', 'plotpress-slice-grid');
      grid.setAttribute('d', gridPath); grid.setAttribute('fill', 'none');
      grid.setAttribute('stroke', '#e3e3e3'); grid.setAttribute('stroke-width', 0.8);
      grid.setAttribute('clip-path', 'url(#clip' + key + ')');
      st.tickGroup.insertBefore(grid, st.tickGroup.firstChild);
    }
    svg.insertBefore(st.tickGroup, st.sliceEl);
  }

  // One docked play/step control, modeled directly on buildSlider() (same
  // transport buttons, same range input, same link-checkbox/index-badge
  // shape) but driving a mesh's row/column index instead of an animation
  // frame -- see the section comment above for why these are two separate,
  // parallel functions rather than one generalized over both.
  // `keys` is an array of one or more axes keys this one slider drives at
  // once -- a single-element array for the ordinary "one slider per axes"
  // case, or every member of a compatible group at once for the "Link all
  // matching axes" global-slider case (buildSliceSliders() below), which
  // needs no per-axes link checkbox at all since there's only one slider
  // for the whole group to begin with.
  function buildSliceSlider(keys, n, values, label, opts) {
    var box = document.createElement('div');
    box.className = 'plotpress-slider';
    var api = { index: opts.linkIndex, checkbox: null, external: null, i: 0 };

    if (opts.showLink) {
      var link = document.createElement('label');
      link.className = 'link';
      link.title = 'link all "' + opts.linkIndex + '" slice sliders to scrub together';
      api.checkbox = document.createElement('input');
      api.checkbox.type = 'checkbox';
      var idx = document.createElement('span');
      idx.className = 'idx'; idx.textContent = opts.linkIndex;
      link.appendChild(api.checkbox); link.appendChild(idx);
      box.appendChild(link);
    }

    var input = document.createElement('input');
    input.type = 'range'; input.min = 0; input.max = n - 1; input.step = 1; input.value = 0;
    if (opts.inputWidth) input.style.width = opts.inputWidth + 'px';
    var val = document.createElement('span'); val.className = 'val';

    var timer = null;
    var applyIndex = function (i) {
      api.i = (i % n + n) % n;
      input.value = api.i;
      keys.forEach(function (k) { renderMeshOrSlice(k, api.i); });
      relayoutSlicePins(keys);
      if (SLICE_SNAP) syncSnappedPins();
      val.textContent = label + ' = ' + fmt(values[api.i]);
    };
    api.external = applyIndex;   // set from a linked peer, no re-propagation
    var setIndex = function (i) {
      applyIndex(i);
      if (api.checkbox && api.checkbox.checked) {
        (SLICE_LINKS[api.index] || []).forEach(function (o) {
          if (o !== api && o.checkbox && o.checkbox.checked) o.external(api.i);
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
    var fwdBtn = sbtn('⏭', 'step forward');
    var pause = function () {
      if (timer) { clearInterval(timer); timer = null; }
      playBtn.textContent = '▶'; playBtn.title = 'play';
    };
    var play = function () {
      if (timer) return;
      playBtn.textContent = '⏸'; playBtn.title = 'pause';
      timer = setInterval(function () { setIndex(api.i + 1); }, 300);
    };
    back.addEventListener('click', function () { pause(); setIndex(api.i - 1); });
    fwdBtn.addEventListener('click', function () { pause(); setIndex(api.i + 1); });
    playBtn.addEventListener('click', function () { timer ? pause() : play(); });
    input.addEventListener('input', function () { pause(); setIndex(+input.value); });

    // When linking is switched on, snap to an already-linked peer's index.
    if (api.checkbox) {
      api.checkbox.addEventListener('change', function () {
        if (!api.checkbox.checked) return;
        var peer = (SLICE_LINKS[api.index] || []).find(function (o) {
          return o !== api && o.checkbox && o.checkbox.checked;
        });
        if (peer) setIndex(peer.i);
      });
      (SLICE_LINKS[api.index] = SLICE_LINKS[api.index] || []).push(api);
    }

    box.appendChild(back); box.appendChild(playBtn); box.appendChild(fwdBtn);
    box.appendChild(input); box.appendChild(val);
    applyIndex(0);
    return { box: box, api: api };
  }

  // Ensure the SVG is wrapped for docked-widget positioning -- shared with
  // the frame-slider setup below, since either (or both) may need it and
  // only one should ever actually create it.
  function ensureSvgWrap() {
    if (wrap) return;
    wrap = document.createElement('div');
    wrap.className = 'plotpress-svg-wrap';
    svg.parentNode.insertBefore(wrap, svg);
    wrap.appendChild(svg);
  }

  // Also shared with the frame-slider setup below: both it and Slice's own
  // "Link all matching axes" (sliceGlobalBar, see buildSliceSliders) can put
  // a fixed-position .plotpress-sliders bar at the bottom of the page, and a
  // figure combining an animated pcolormesh_frames() axes with a
  // SLICE_LINK_ALL-coupled group of ordinary ones can have both at once --
  // .plotpress-sliders' own CSS rule is a single fixed bottom:12px spot, so
  // without this they'd draw on top of each other. Called whenever either
  // bar is created or removed; recomputes every surviving bar's own offset
  // from scratch (stacking them, in DOM order, bottom to top) rather than
  // adjusting one in place, so it doesn't matter which of the two exists
  // first -- that depends on whether Slice was ever enabled, the frame
  // slider's own global bar (if any) is always built once at load.
  function reflowGlobalBars() {
    var bars = document.querySelectorAll('.plotpress-sliders');
    var offset = 12, vh = document.documentElement.clientHeight;
    bars.forEach(function (b) {
      b.style.bottom = offset + 'px';
      // Never taller than the room left above this bar's own bottom edge:
      // past that the column grows off the top of the window, where a
      // position:fixed element cannot be scrolled to. Capped, it scrolls
      // inside itself instead (see the CSS above). MARGIN keeps the top
      // slider clear of the toolbar.
      var MARGIN = 46;
      b.style.maxHeight = Math.max(72, vh - offset - MARGIN) + 'px';
      offset += b.getBoundingClientRect().height + 6;
    });
  }
  // A bar sized to the window has to be re-capped when the window changes --
  // positionDocked() is already wired to resize for the docked sliders, so
  // this rides along with it rather than adding a second listener.
  function reflowOnResize() { reflowGlobalBars(); positionDocked(); }

  // (Re)builds every mesh axes' own slice slider from scratch -- torn down
  // and rebuilt rather than adjusted in place, since a changed orientation
  // can change both the row/column count (ny vs. nx) and which axes are
  // even compatible to link, and SLICE_LINK_ALL can change how many
  // sliders there even are. Called once at load (if sliceMenuNeeded), and
  // again from the orientation radio's and "Link all matching axes"
  // toggle's own onchange handlers.
  //
  // Two layouts, chosen by SLICE_LINK_ALL:
  // - Off (default): one *docked* slider per axes, same as a per-axes
  //   frame slider -- a compatible group of 2+ gets its own link
  //   checkbox+badge on each member's slider (buildSliceSlider's own
  //   showLink), opt-in and manual, fine at the scale of a handful of axes.
  // - On: one *global* slider (the fixed bottom bar, same as a global
  //   frame slider) per compatible group of 2+, driving every member at
  //   once with no checkbox to click at all -- this is the answer to "500
  //   meshes, all coupled": one slider instead of 500 individually-checked
  //   ones. A singleton with nothing to link to still gets its own docked
  //   slider either way, since there's no group for it to join.
  // Removes every slider (docked or global) with no rebuild -- shared by
  // buildSliceSliders() (about to replace them) and the "Enable Slice"
  // checkbox's own off handler (which tears down and stops there).
  function teardownSliceSliders() {
    // Deliberately does *not* drop the profile pins. buildSliceSliders() calls
    // this on every rebuild, so doing it here meant changing the scope or
    // toggling "Link all matching axes" deleted every pin a reader had placed
    // on a strip -- neither of which changes what a pin points at. The two
    // cases that do are handled at their own call sites: the "Enable Slice"
    // off handler (nothing left to point at) and the orientation radio (a
    // pin's index means a sample along the *other* axis afterwards). An axes
    // merely leaving the scope still drops its own, via teardownAxesVisuals ->
    // removeCompanion.
    Object.keys(SLICE_SLIDERS).forEach(function (k) {
      var s = SLICE_SLIDERS[k];
      if (s.box.parentNode) s.box.parentNode.removeChild(s.box);
    });
    dockedSliders = dockedSliders.filter(function (d) {
      return !(SLICE_SLIDERS[d.axesKey] && SLICE_SLIDERS[d.axesKey].box === d.box);
    });
    SLICE_SLIDERS = {};
    SLICE_LINKS = {};
    if (sliceGlobalBar) { sliceGlobalBar.remove(); sliceGlobalBar = null; }
    reflowGlobalBars();
  }
  // Restores every mesh axes this ever touched back to a plain, unmodified
  // pcolormesh -- the mesh raster and its own ticks shown again, any
  // cursor/slice-line/value-tick element removed. Paired with
  // teardownSliceSliders() by the "Enable Slice" checkbox's off handler so
  // unchecking it leaves nothing behind at all, the same figure this would
  // have rendered if Slice didn't exist.
  function teardownAxesVisuals(key) {
    removeCompanion(key);
    var st = SLICE_STATE[key];
    if (!st) return;
    // Both selectors -- see renderMeshOrSlice's own comment on them. This has
    // to un-hide everything that view could have hidden, overlaid series
    // included, or switching Slice off in the replace view would leave a
    // line/scatter invisible with nothing left on screen to bring it back.
    var meshEls = svg.querySelectorAll(
      '#zoom' + key + ' .plotpress-mesh, #zoom' + key + ' .plotpress-series');
    meshEls.forEach(function (im) { im.classList.remove('plotpress-slice-hidden'); });
    setDataPinsHidden(key, false);
    var origTicks = document.getElementById('ticks' + key);
    if (origTicks) origTicks.style.display = '';
    if (st.cursorEl) st.cursorEl.remove();
    if (st.sliceEl) st.sliceEl.remove();
    if (st.tickGroup) st.tickGroup.remove();
    delete SLICE_STATE[key];
  }
  function teardownSliceVisuals() {
    Object.keys(SLICE_STATE).forEach(teardownAxesVisuals);
    SLICE_STATE = {};
  }

  function buildSliceSliders() {
    teardownSliceSliders();
    ensureSvgWrap();
    // An axes that has left the scope goes back to a plain heatmap.
    var inScope = {};
    sliceScopeKeys().forEach(function (k) { inScope[k] = true; });
    Object.keys(SLICE_STATE).forEach(function (k) { if (!inScope[k]) teardownAxesVisuals(k); });

    var groups = computeSliceLinkGroups(SLICE_ORIENTATION);
    var linkIndexOf = sliceLinkIndexOf(groups);

    function sliceSpecFor(key) {
      var entry = meshEntryForAxes(key);
      if (!entry) return null;
      var ny = entry.shape[0], nx = entry.shape[1];
      return SLICE_ORIENTATION === 'x'
        ? { n: ny, values: cellMidpoints(entry.yedges), label: 'y' }
        : { n: nx, values: cellMidpoints(entry.xedges), label: 'x' };
    }

    function dockOne(key, opts) {
      var spec = sliceSpecFor(key);
      if (!spec) return;
      var m = META[key] || { x: 0, y: 0, w: home[2], h: home[3] };
      var iw = Math.max(80, Math.min(240, m.w - (opts.showLink ? 210 : 175)));
      var built = buildSliceSlider([key], spec.n, spec.values, spec.label,
        { inputWidth: iw, showLink: opts.showLink, linkIndex: opts.linkIndex });
      built.box.style.position = 'absolute';
      built.box.style.whiteSpace = 'nowrap';
      wrap.appendChild(built.box);
      dockedSliders.push({ box: built.box, axesKey: key });
      SLICE_SLIDERS[key] = built;
    }

    groups.forEach(function (g) {
      if (SLICE_LINK_ALL && g.length >= 2) {
        var spec = sliceSpecFor(g[0]);
        if (!spec) return;
        if (!sliceGlobalBar) {
          sliceGlobalBar = document.createElement('div');
          sliceGlobalBar.className = 'plotpress-sliders';
          document.body.appendChild(sliceGlobalBar);
        }
        var built = buildSliceSlider(g, spec.n, spec.values,
          spec.label + ' (' + g.length + ' axes)', { inputWidth: 240, showLink: false });
        sliceGlobalBar.appendChild(built.box);
        g.forEach(function (key) { SLICE_SLIDERS[key] = built; });
      } else if (g.length >= 2) {
        var linkIndex = linkIndexOf[g[0]];
        g.forEach(function (key) { dockOne(key, { showLink: true, linkIndex: linkIndex }); });
      } else {
        dockOne(g[0], { showLink: false, linkIndex: undefined });
      }
    });
    positionDocked();
    reflowGlobalBars();
    syncSnappedPins();
  }

  // Keeps an already-placed cursor/slice line glued to the right spot
  // after a pan/zoom -- called from refreshAxes, the same single place
  // applyAxesTransform/rebuildTicks/relayoutPins/relayoutTextCounterScale
  // already resync from on every view change.
  function resyncSlice(key) {
    var st = SLICE_STATE[key];
    if (!st || typeof st.index !== 'number') return;
    renderMeshOrSlice(key, st.index);
  }
  // The row/column position a slice sits at doesn't change when an animated
  // pcolormesh_frames() mesh's own frame slider moves, but the z values
  // under it do (see meshEntryForAxes's frameEntry branch) -- called from
  // buildSlider()'s own applyFrame() (below), the one place that already
  // knows a frame slider unit just moved, so any Slice-enabled axes reading
  // that same unit's current frame redraws to match. A no-op for every
  // frame slider unit no SLICE_AXES entry is watching (the common case),
  // and for one Slice was never enabled on (resyncSlice's own guard).
  function resyncSliceForFrameUnit(unit) {
    var moved = [];
    for (var frameSyncKey in SLICE_AXES) {
      var info = SLICE_AXES[frameSyncKey];
      if (info.frameEntry && info.frameEntry.unit === unit) {
        resyncSlice(frameSyncKey);
        moved.push(String(frameSyncKey));
      }
    }
    // The profile under a strip pin changed with the frame, so the pin's value
    // (and any mirror of it) has to be re-read too, not just the line redrawn.
    if (moved.length) {
      relayoutSlicePins(moved);
      if (SLICE_SNAP) syncSnappedPins();
    }
  }
  // Off by default (SLICE_ENABLED) -- nothing is built here at load; the
  // "Enable Slice" checkbox in the menu above is what calls
  // buildSliceSliders() the first time. The resize listener still needs
  // registering unconditionally, though: positionDocked() itself already
  // no-ops with nothing docked, and registering it only from inside the
  // checkbox handler would mean re-registering (and so double-firing after
  // a second toggle) instead of once.
  if (sliceMenuNeeded) {
    window.addEventListener('resize', reflowOnResize);
  }

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

