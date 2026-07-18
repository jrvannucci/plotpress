"""Vanilla-JS interactivity injected into interactive HTML/pop-up output.

Fully self-contained (no external requests) so it works under strict CSPs such
as Jupyter and sandboxed webviews.

A floating toolbar in the corner selects one **mode** at a time; nothing is
interactive until a mode is chosen (single selection -- picking one cancels the
others):

* **Span**  -- drag to pan (grab cursor).
* **Zoom**  -- drag a rubber-band box to zoom into it; wheel to zoom in/out
  (crosshair cursor).
* **Point Pick** -- click a plot to pin an annotation of the value there; snaps
  to the nearest data point, else a free coordinate readout (arrow cursor).
  Click a pin to remove it; Escape clears all.
* **Reset** -- restore *all* plots' views and deselect (back to inert default).
  In Span/Zoom mode, double-clicking a single plot resets only that plot.

Legend entries remain clickable to toggle series regardless of mode.
"""

INTERACTIVE_JS = r"""
(function () {
  var svg = document.getElementById('simpleplot-svg');
  if (!svg) return;
  var SVGNS = 'http://www.w3.org/2000/svg';
  var vb = svg.getAttribute('viewBox').split(/\s+/).map(Number);
  var home = vb.slice();
  var view = vb.slice();
  var wrap = null;              // container holding the svg (for docked sliders)
  var dockedSliders = [];       // [{box, axesKey}] repositioned on pan/zoom
  var CURRENT_FRAME = {};       // slider unit -> current frame index
  var FRAME_INDEX = {};         // frame series id -> {entry, axesKey}
  var selectedPin = null;       // pin currently selected for arrow-key movement
  function apply() {
    svg.setAttribute('viewBox', view.join(' '));
    positionDocked();
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

  var metaEl = document.getElementById('simpleplot-meta');
  var META = metaEl ? JSON.parse(metaEl.textContent) : {};
  var styleEl = document.getElementById('simpleplot-style');
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
  var style = document.createElement('style');
  style.textContent =
    '.simpleplot-toolbar{position:fixed;top:10px;right:10px;display:flex;gap:4px;' +
    'font:12px system-ui,sans-serif;z-index:1000}' +
    '.simpleplot-toolbar button{padding:6px 11px;border:1px solid #b8b8b8;' +
    'background:#fff;color:#222;border-radius:6px;cursor:pointer;' +
    'box-shadow:0 1px 3px rgba(0,0,0,.18)}' +
    '.simpleplot-toolbar button:hover{background:#f1f1f1}' +
    '.simpleplot-toolbar button.active{background:#2b8cff;color:#fff;' +
    'border-color:#2b8cff}' +
    '.simpleplot-sliders{position:fixed;bottom:12px;left:50%;' +
    'transform:translateX(-50%);display:flex;flex-direction:column;' +
    'gap:6px;z-index:1000}' +
    '.simpleplot-slider{display:flex;align-items:center;gap:12px;' +
    'background:#fff;padding:8px 16px;border:1px solid #b8b8b8;' +
    'border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.2);' +
    'font:12px system-ui,sans-serif}' +
    '.simpleplot-slider input[type=range]{width:240px}' +
    '.simpleplot-slider .val{min-width:90px;font-variant-numeric:tabular-nums}' +
    '.simpleplot-slider button{padding:3px 8px;border:1px solid #b8b8b8;' +
    'background:#fff;border-radius:5px;cursor:pointer;font-size:13px;' +
    'line-height:1.1}' +
    '.simpleplot-slider button:hover{background:#f1f1f1}' +
    '.simpleplot-slider .link{display:flex;align-items:center;gap:4px;' +
    'font-size:11px;color:#555;cursor:pointer;user-select:none}' +
    '.simpleplot-slider .idx{background:#e8eeff;border:1px solid #b9c6ef;' +
    'border-radius:4px;padding:0 5px;font-weight:600;color:#2b5bd7}' +
    '.simpleplot-pin.selected circle{fill:#2b8cff;r:5}' +
    '.simpleplot-pin.simpleplot-note rect{fill:#b45309}' +   /* user notes: amber */
    '.simpleplot-zoom line,.simpleplot-zoom path{vector-effect:non-scaling-stroke}' +
    '.simpleplot-extract{position:fixed;top:56px;right:10px;width:360px;' +
    'max-height:72vh;overflow:auto;background:#fff;border:1px solid #b8b8b8;' +
    'border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);padding:10px;' +
    'z-index:2000;font:12px system-ui,sans-serif}' +
    '.simpleplot-extract textarea{width:100%;height:180px;box-sizing:border-box;' +
    'font:11px ui-monospace,monospace;resize:vertical}' +
    '.simpleplot-extract button{padding:4px 8px;border:1px solid #b8b8b8;' +
    'background:#fff;border-radius:5px;cursor:pointer}';
  document.head.appendChild(style);

  var bar = document.createElement('div');
  bar.className = 'simpleplot-toolbar';
  var TOOLS = [
    { mode: 'span', label: 'Span' },
    { mode: 'zoom', label: 'Zoom' },
    { mode: 'pick', label: 'Point Pick' },
    { mode: 'note', label: 'Annotate' },
    { mode: 'reset', label: 'Reset' },
    { action: 'extract', label: 'Extract' },
  ];
  var buttons = TOOLS.map(function (t) {
    var b = document.createElement('button');
    b.textContent = t.label;
    if (t.mode) b.dataset.mode = t.mode;
    b.addEventListener('click', function () {
      if (t.action === 'extract') doExtract(); else setMode(t.mode);
    });
    bar.appendChild(b);
    return b;
  });
  document.body.appendChild(bar);

  function setMode(m) {
    // Cancel anything in progress and clear transient state.
    down = null; removeRubber();
    if (m === 'reset') {
      view = home.slice(); apply();
      resetAxes();                               // restore every axes' data limits
      mode = null;
      selectedPin = null;                        // clear all markers too
      document.querySelectorAll('.simpleplot-pin').forEach(function (p) { p.remove(); });
    } else {
      mode = (mode === m) ? null : m;  // clicking the active tool turns it off
    }
    buttons.forEach(function (b) {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    svg.style.cursor =
      mode === 'span' ? 'grab' :
      mode === 'zoom' ? 'crosshair' :
      mode === 'note' ? 'text' : 'default';   // pick / none => arrow
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
    el.setAttribute('class', 'simpleplot-rubber');
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
    if (mode !== 'zoom') return;
    e.preventDefault();
    var p = toUser(e), a = axesAt(p);
    if (!a) return;                          // only zoom the axes under the cursor
    zoomAxesAt(a.i, p.x, p.y, e.deltaY < 0 ? 0.8 : 1.25);
  }, { passive: false });

  svg.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;   // ignore right/middle button (right = delete pin)
    if (!mode || e.target.closest('.simpleplot-pin')) return;
    down = { x: e.clientX, y: e.clientY }; moved = false;
    if (mode === 'span') {
      var pdn = toUser(e), a = axesAt(pdn);
      if (a) {
        // per-axes data pan over a plot (directed edges: honors inverted axes)
        panAxes = { key: a.i, downUser: pdn, start: edges(CUR[a.i]) };
      } else {
        panV = view.slice();            // over margins: whole-figure pan
      }
      svg.style.cursor = 'grabbing';
    } else if (mode === 'zoom') { startRubber(e); }
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
    } else if (mode === 'span') {
      var r = svg.getBoundingClientRect();
      view[0] = panV[0] - (e.clientX - down.x) / r.width * view[2];
      view[1] = panV[1] - (e.clientY - down.y) / r.height * view[3];
      apply();
    } else if (mode === 'zoom' && rubber) {
      updateRubber(e);
    }
  });
  window.addEventListener('mouseup', function (e) {
    if (!down) return;
    if (mode === 'span') svg.style.cursor = 'grab';
    else if (mode === 'zoom' && rubber) finishRubber(e);
    down = null; panAxes = null;
  });

  // Double-click a plot (while panning/zooming) resets just that plot's view.
  svg.addEventListener('dblclick', function (e) {
    if (mode !== 'span' && mode !== 'zoom') return;
    e.preventDefault();
    var a = axesAt(toUser(e));
    if (a) resetAxesOne(a.i);
  });

  // ---- legend toggle (always available) ---------------------------------
  document.querySelectorAll('.simpleplot-legend text').forEach(function (t) {
    var label = t.textContent;
    t.style.cursor = 'pointer';
    t.addEventListener('click', function (e) {
      e.stopPropagation();
      document.querySelectorAll('.simpleplot-series').forEach(function (s) {
        if (s.getAttribute('data-label') === label) {
          var hidden = s.style.display === 'none';
          s.style.display = hidden ? '' : 'none';
          t.style.opacity = hidden ? '1' : '0.4';
        }
      });
    });
  });

  // ---- point picking (pick mode) ----------------------------------------
  var pickEl = document.getElementById('simpleplot-pick');
  var PICK = pickEl ? JSON.parse(pickEl.textContent) : {};
  var POINT_THRESHOLD = 28;  // px: snap to an embedded point within this radius

  function axesAt(p) {
    for (var k in CUR) {
      var m = CUR[k];
      if (p.x >= m.x && p.x <= m.x + m.w && p.y >= m.y && p.y <= m.y + m.h) {
        return { i: k, m: m };
      }
    }
    return null;
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
  function jsLogTicks(lo, hi) {
    if (lo <= 0) lo = hi > 0 ? hi / 1000 : 1e-3;
    var out = [];
    for (var e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++)
      out.push(Math.pow(10, e));
    return out;
  }
  // Ticks + a formatter for one axis, respecting its scale.
  function axisTicks(lo, hi, scale) {
    if (scale === 'log') return { ticks: jsLogTicks(lo, hi), fmt: fmtNum };
    var r = jsNiceTicks(lo, hi, 5);
    return { ticks: r.ticks, fmt: function (v) { return fmtTick(v, r.step); } };
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
    var ts = STYLE.tick_size, fs = STYLE.tick_label_size, yb = m.y + m.h, parts = [];
    if (om.grid) {
      var gl = [];
      xr.ticks.forEach(function (xt) { var px = toPixel(m, xt, m.ymin).x;
        gl.push('<line x1="' + px.toFixed(2) + '" y1="' + m.y.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + yb.toFixed(2) + '"/>'); });
      yr.ticks.forEach(function (yt) { var py = toPixel(m, m.xmin, yt).y;
        gl.push('<line x1="' + m.x.toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + (m.x + m.w).toFixed(2) + '" y2="' + py.toFixed(2) + '"/>'); });
      parts.push('<g stroke="' + STYLE.grid_color + '" stroke-width="' + STYLE.grid_width + '" stroke-opacity="' + STYLE.grid_alpha + '">' + gl.join('') + '</g>');
    }
    var marks = [], labels = [];
    xr.ticks.forEach(function (xt) {
      var px = toPixel(m, xt, m.ymin).x;
      marks.push('<line x1="' + px.toFixed(2) + '" y1="' + yb.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + (yb + ts).toFixed(2) + '"/>');
      labels.push('<text x="' + px.toFixed(2) + '" y="' + (yb + ts + fs).toFixed(2) + '" text-anchor="middle" font-size="' + fs + '" fill="' + STYLE.text + '">' + xr.fmt(xt) + '</text>');
    });
    yr.ticks.forEach(function (yt) {
      var py = toPixel(m, m.xmin, yt).y;
      marks.push('<line x1="' + (m.x - ts).toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + m.x.toFixed(2) + '" y2="' + py.toFixed(2) + '"/>');
      labels.push('<text x="' + (m.x - ts - 2).toFixed(2) + '" y="' + (py + fs * 0.35).toFixed(2) + '" text-anchor="end" font-size="' + fs + '" fill="' + STYLE.text + '">' + yr.fmt(yt) + '</text>');
    });
    parts.push('<g stroke="' + STYLE.spine + '" stroke-width="' + STYLE.tick_width + '">' + marks.join('') + '</g>');
    parts.push(labels.join(''));
    g.innerHTML = parts.join('');
  }

  // Remap the artist group from original limits (META) to current (CUR).
  function applyAxesTransform(key) {
    var o = META[key], c = CUR[key];
    var g = document.getElementById('zoom' + key);
    if (!g) return;
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
    if (Math.abs(sx - 1) < 1e-9 && Math.abs(sy - 1) < 1e-9 &&
        Math.abs(tx) < 1e-6 && Math.abs(ty) < 1e-6) {
      g.removeAttribute('transform');
    } else {
      g.setAttribute('transform', 'matrix(' + sx + ',0,0,' + sy + ',' + tx + ',' + ty + ')');
    }
  }

  function pinAxesKey(pin) {
    if (pin.dataset.axes !== undefined) return pin.dataset.axes;
    if (pin.dataset.frameId && FRAME_INDEX[pin.dataset.frameId])
      return String(FRAME_INDEX[pin.dataset.frameId].axesKey);
    return null;
  }
  function relayoutPins(key) {
    document.querySelectorAll('.simpleplot-pin').forEach(function (pin) {
      if (pinAxesKey(pin) !== String(key)) return;
      var anchor = pinAnchor(pin);
      if (anchor) {
        var a = resolve(anchor, +pin.dataset.index);
        if (a) layoutPin(pin, a.px, a.py, a.label);
      } else if (pin.dataset.x !== undefined && CUR[key]) {
        var q = toPixel(CUR[key], +pin.dataset.x, +pin.dataset.y);
        layoutPin(pin, q.x, q.y, pin.querySelector('text').textContent);
      }
    });
  }

  function refreshAxes(key) {
    applyAxesTransform(key); rebuildTicks(key); relayoutPins(key);
  }
  function zoomAxesAt(key, px, py, factor) {
    var c = CUR[key], e = edges(c);
    // Zoom in transformed space (linear for 'linear', decades for 'log').
    var cxf = e.fx0 + (px - c.x) / c.w * (e.fx1 - e.fx0);
    var cyf = e.fy1 - (py - c.y) / c.h * (e.fy1 - e.fy0);
    setXLim(c, cxf - (cxf - e.fx0) * factor, cxf + (e.fx1 - cxf) * factor);
    setYLim(c, cyf - (cyf - e.fy0) * factor, cyf + (e.fy1 - cyf) * factor);
    refreshAxes(key);
  }
  function resetAxesOne(key) {
    for (var f in META[key]) CUR[key][f] = META[key][f];
    var g = document.getElementById('zoom' + key);
    if (g) g.removeAttribute('transform');
    rebuildTicks(key);
    relayoutPins(key);
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

  // Mesh cell under a data coordinate -> anchor ref (steppable by cell).
  function meshAt(key, dx, dy) {
    var pd = PICK[key];
    if (!pd) return null;
    for (var t = 0; t < pd.meshes.length; t++) {
      var mesh = pd.meshes[t], e = mesh.extent;
      if (dx >= e[0] && dx <= e[1] && dy >= e[2] && dy <= e[3]) {
        var nx = mesh.shape[1], ny = mesh.shape[0];
        var col = Math.min(nx - 1, Math.max(0, Math.floor((dx - e[0]) / (e[1] - e[0]) * nx)));
        var row = Math.min(ny - 1, Math.max(0, Math.floor((dy - e[2]) / (e[3] - e[2]) * ny)));
        return { kind: 'mesh', axes: key, mesh: t, index: row * nx + col };
      }
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

  // Geometry fallback for series too large to embed (x/y only).
  function nearestVertex(i, p) {
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
        var d = (pts[q].x - p.x) * (pts[q].x - p.x) + (pts[q].y - p.y) * (pts[q].y - p.y);
        if (d < bd) { bd = d; best = pts[q]; }
      }
    });
    return best;
  }

  function fmt(v) {
    var a = Math.abs(v);
    if (a !== 0 && (a < 1e-3 || a >= 1e5)) return v.toExponential(2);
    return (Math.round(v * 1000) / 1000).toString();
  }

  function layoutPin(g, px, py, label) {
    var fs = 11, padx = 5, pady = 3;
    var bw = label.length * fs * 0.55 + padx * 2, bh = fs + pady * 2;
    var bx = px + 8, by = py - bh - 4;
    var dot = g.querySelector('circle'), rect = g.querySelector('rect'),
        text = g.querySelector('text');
    dot.setAttribute('cx', px); dot.setAttribute('cy', py);
    rect.setAttribute('x', bx); rect.setAttribute('y', by);
    rect.setAttribute('width', bw); rect.setAttribute('height', bh);
    text.setAttribute('x', bx + padx); text.setAttribute('y', by + fs + pady - 2);
    text.textContent = label;
  }

  function selectPin(g) {
    if (selectedPin && selectedPin !== g) selectedPin.classList.remove('selected');
    selectedPin = g;
    if (g) g.classList.add('selected');
  }

  function addPin(px, py, label) {
    var g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', 'simpleplot-pin'); g.style.cursor = 'pointer';
    var dot = document.createElementNS(SVGNS, 'circle');
    dot.setAttribute('r', 3.5); dot.setAttribute('fill', '#111');
    dot.setAttribute('stroke', '#fff'); dot.setAttribute('stroke-width', 1);
    var rect = document.createElementNS(SVGNS, 'rect');
    rect.setAttribute('rx', 3); rect.setAttribute('fill', '#111');
    rect.setAttribute('fill-opacity', 0.85);
    var text = document.createElementNS(SVGNS, 'text');
    text.setAttribute('font-size', 11); text.setAttribute('fill', '#fff');
    g.appendChild(dot); g.appendChild(rect); g.appendChild(text);
    layoutPin(g, px, py, label);
    // Left-click selects (arrow keys then step it); right-click deletes.
    g.addEventListener('click', function (ev) { ev.stopPropagation(); selectPin(g); });
    g.addEventListener('contextmenu', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      if (selectedPin === g) selectedPin = null;
      g.remove();
    });
    svg.appendChild(g);
    selectPin(g);   // a freshly dropped marker starts selected
    return g;
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
      var e = mesh.extent, nx = mesh.shape[1], ny = mesh.shape[0];
      var idx = Math.max(0, Math.min(nx * ny - 1, index));
      var row = Math.floor(idx / nx), col = idx % nx;
      var xc = e[0] + (col + 0.5) / nx * (e[1] - e[0]);
      var yc = e[2] + (row + 0.5) / ny * (e[3] - e[2]);
      var q = toPixel(CUR[anchor.axes], xc, yc);
      return { px: q.x, py: q.y, index: idx, label: 'x=' + fmt(xc) + ', y=' +
               fmt(yc) + ', ' + (mesh.name || 'z') + '=' + fmt(mesh.z[idx]) };
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
    if (anchor.kind === 'mesh') {
      var mesh = PICK[anchor.axes].meshes[anchor.mesh];
      var nx = mesh.shape[1], ny = mesh.shape[0];
      var row = Math.floor(index / nx), col = index % nx;
      if (dir === 'right') col = Math.min(nx - 1, col + 1);
      else if (dir === 'left') col = Math.max(0, col - 1);
      else if (dir === 'up') row = Math.min(ny - 1, row + 1);   // higher y
      else row = Math.max(0, row - 1);
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
    if (k === 'mesh') return { kind: 'mesh', axes: pin.dataset.axes, mesh: +pin.dataset.mesh };
    if (k === 'pie') return { kind: 'pie', axes: pin.dataset.axes, pie: +pin.dataset.pie };
    return { kind: 'points', axes: pin.dataset.axes, series: +pin.dataset.series,
             ptype: pin.dataset.ptype };
  }

  function addAnchoredPin(anchor, index) {
    var a = resolve(anchor, index);
    if (!a) return;
    var g = addPin(a.px, a.py, a.label);
    g.dataset.kind = anchor.kind;
    g.dataset.index = a.index;
    if (anchor.kind === 'frame') {
      g.dataset.frameId = anchor.id; g.dataset.frameUnit = anchor.unit;
    } else if (anchor.kind === 'mesh') {
      g.dataset.axes = anchor.axes; g.dataset.mesh = anchor.mesh;
    } else if (anchor.kind === 'pie') {
      g.dataset.axes = anchor.axes; g.dataset.pie = anchor.pie;
    } else {
      g.dataset.axes = anchor.axes; g.dataset.series = anchor.series;
      g.dataset.ptype = anchor.ptype;
    }
  }

  // Move a marker to a neighbouring point/cell (arrow keys).
  function stepPin(pin, dir) {
    var anchor = pinAnchor(pin);
    if (!anchor) return;
    var a = resolve(anchor, neighbor(anchor, +pin.dataset.index, dir));
    if (!a) return;
    pin.dataset.index = a.index;
    layoutPin(pin, a.px, a.py, a.label);
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
      return rec;
    }
    if (anchor && anchor.kind === 'mesh') {
      var mesh = PICK[anchor.axes].meshes[anchor.mesh];
      var idx = +pin.dataset.index, nx = mesh.shape[1], ny = mesh.shape[0], e = mesh.extent;
      var row = Math.floor(idx / nx), col = idx % nx;
      rec.axes = +anchor.axes; rec.kind = 'mesh'; rec.index = idx;
      rec.x = e[0] + (col + 0.5) / nx * (e[1] - e[0]);
      rec.y = e[2] + (row + 0.5) / ny * (e[3] - e[2]);
      rec[mesh.name || 'z'] = mesh.z[idx];
    } else if (anchor) {
      var s = seriesOf(anchor), j = +pin.dataset.index;
      rec.axes = +s.axes; rec.kind = anchor.kind; rec.index = j;
      rec.x = s.x[j]; rec.y = s.y[j];
      if (s.vals) for (var k in s.vals) rec[k] = s.vals[k][j];
    } else if (pin.dataset.annotation) {
      rec.kind = 'annotation';
      rec.text = pin.querySelector('text').textContent;
      if (pin.dataset.axes !== undefined) rec.axes = +pin.dataset.axes;
      rec.x = +pin.dataset.x; rec.y = +pin.dataset.y;
    } else {
      rec.kind = 'free';
      if (pin.dataset.axes !== undefined) rec.axes = +pin.dataset.axes;
      rec.x = +pin.dataset.x; rec.y = +pin.dataset.y;
    }
    return rec;
  }

  function getMarkers() {
    return Array.prototype.map.call(
      document.querySelectorAll('.simpleplot-pin'), markerRecord);
  }
  window.simpleplotGetMarkers = getMarkers;   // programmatic access

  function toCSV(recs) {
    if (!recs.length) return '';
    var keys = [];
    recs.forEach(function (r) {
      for (var k in r) if (keys.indexOf(k) < 0) keys.push(k);
    });
    var lines = [keys.join(',')];
    recs.forEach(function (r) {
      lines.push(keys.map(function (k) {
        return r[k] === undefined ? '' : r[k];
      }).join(','));
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
    var old = document.querySelector('.simpleplot-extract');
    if (old) old.remove();
    var panel = document.createElement('div');
    panel.className = 'simpleplot-extract';
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

  function doExtract() {
    var records = getMarkers();
    // Hand off to Python when running inside the native (pywebview) window.
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.extract) {
        window.pywebview.api.extract(records);
      }
    } catch (e) {}
    // In wait-for-extract mode the kernel closes the window on receipt, so skip
    // the panel; otherwise show it for copy/download.
    if (!window.SIMPLEPLOT_WAIT_EXTRACT) {
      showExtractPanel(records, toCSV(records), JSON.stringify(records, null, 2));
    }
  }
  window.simpleplotExtract = doExtract;

  // Nearest vertex of an animated (frame) series at its current frame.
  function nearestFrameVertex(axesKey, m, p) {
    if (!FRAMES || !FRAMES[axesKey]) return null;
    var best = null;
    FRAMES[axesKey].forEach(function (e) {
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

  // Annotate mode: click to drop a user-typed text note anchored to the data.
  function addNote(e) {
    var p = toUser(e), a = axesAt(p);
    if (!a) return;
    var text = window.prompt('Annotation text:');
    if (!text) return;
    var d = toData(a.m, p.x, p.y);
    var g = addPin(p.x, p.y, text);
    g.classList.add('simpleplot-note');
    g.dataset.x = d.x; g.dataset.y = d.y; g.dataset.axes = a.i;
    g.dataset.annotation = '1';
  }

  svg.addEventListener('click', function (e) {
    if (moved) return;
    if (e.target.closest('.simpleplot-legend') || e.target.closest('.simpleplot-pin')) return;
    if (mode === 'note') { addNote(e); return; }
    if (mode !== 'pick') return;
    var p = toUser(e), a = axesAt(p);
    if (!a) return;
    var m = a.m;
    var np = nearestPoint(a.i, m, p);
    var fp = nearestFrameVertex(a.i, m, p);
    var d = toData(m, p.x, p.y);
    var mesh = meshAt(a.i, d.x, d.y);
    var pieHit = pieAt(a.i, p);

    // Nearest of embedded static points vs animated frame vertices.
    var cand = null;
    if (np) cand = { d: np.d, ref: np.ref };
    if (fp && (!cand || fp.d < cand.d)) cand = { d: fp.d, ref: fp.ref };

    // On a pie axes only the wedges are pickable: a click that misses them (and
    // has nothing else nearby) makes no marker.
    var pd = PICK[a.i];
    if (pd && pd.pies && pd.pies.length && !pieHit && !mesh &&
        (!cand || Math.sqrt(cand.d) > POINT_THRESHOLD)) {
      return;
    }

    if (cand && Math.sqrt(cand.d) <= POINT_THRESHOLD) {
      addAnchoredPin(cand.ref, cand.ref.index);
    } else if (mesh) {
      addAnchoredPin(mesh, mesh.index);          // mesh cell (steppable by cell)
    } else if (pieHit) {
      addAnchoredPin(pieHit, pieHit.index);      // pie wedge (steppable by wedge)
    } else if (cand) {
      addAnchoredPin(cand.ref, cand.ref.index);
    } else {
      var v = nearestVertex(a.i, p) || p;              // large-series fallback
      var dd = toData(m, v.x, v.y);
      var g = addPin(v.x, v.y, 'x=' + fmt(dd.x) + ', y=' + fmt(dd.y));
      g.dataset.x = dd.x; g.dataset.y = dd.y; g.dataset.axes = a.i;
    }
  });

  // ---- slider(s) over extra data dimensions -----------------------------
  // Each "unit" is one control bar. The global unit ("main") is a single bar
  // driving all shared series; a docked unit sits under its axes. Docked units
  // that share a connection index show an index badge + a checkbox to link them
  // so they scrub together on demand.
  var framesEl = document.getElementById('simpleplot-frames');
  var unitsEl = document.getElementById('simpleplot-sliders');
  var FRAMES = framesEl ? JSON.parse(framesEl.textContent) : null;
  var UNITS = unitsEl ? JSON.parse(unitsEl.textContent) : null;
  var LINKS = {};  // connection index -> [slider api]
  if (FRAMES) {
    for (var fk in FRAMES) {
      FRAMES[fk].forEach(function (e) { FRAME_INDEX[e.id] = { entry: e, axesKey: fk }; });
    }
  }

  // Move any pins attached to this unit's series to the new frame's vertex.
  function updateFramePins(unit, f) {
    var pins = document.querySelectorAll('.simpleplot-pin[data-frame-unit="' + unit + '"]');
    for (var i = 0; i < pins.length; i++) {
      var pin = pins[i];
      var a = resolve(pinAnchor(pin), +pin.dataset.index);  // uses current frame
      if (a) layoutPin(pin, a.px, a.py, a.label);
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
    box.className = 'simpleplot-slider';
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
    // Wrap the SVG so docked sliders can be positioned over it.
    wrap = document.createElement('div');
    wrap.style.position = 'relative';
    wrap.style.display = 'inline-block';
    wrap.style.lineHeight = '0';
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
          globalBar.className = 'simpleplot-sliders';
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

  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      selectedPin = null;
      document.querySelectorAll('.simpleplot-pin').forEach(function (p) { p.remove(); });
      return;
    }
    if (!selectedPin) return;
    var dir = e.key === 'ArrowRight' ? 'right' : e.key === 'ArrowLeft' ? 'left' :
              e.key === 'ArrowUp' ? 'up' : e.key === 'ArrowDown' ? 'down' : null;
    if (dir) { e.preventDefault(); stepPin(selectedPin, dir); }
  });
})();
"""
