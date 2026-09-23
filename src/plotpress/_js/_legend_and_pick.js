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
  // PICK itself is parsed earlier (see the comment above DROPDOWN_FOR_MENU)
  // so the Slice menu, built alongside the other menus, already knows
  // whether there's anything to slice.
  var POINT_THRESHOLD = 28;  // px: snap to an embedded point within this radius
  // A much tighter radius for a line/scatter point to win over a mesh cell
  // the click also landed inside (see resolvePickTarget) -- a deliberate,
  // precise click on a small marker should still win, but the loose 28px
  // snap radius above is generous enough that a line merely drawn near or
  // across a mesh (a threshold marker, a boundary trace) would otherwise
  // "steal" clicks plainly aimed at a mesh cell well away from the line
  // itself, just because one of the line's vertices happened to be within
  // 28px of it.
  var MESH_OVERRIDE_THRESHOLD = 10;

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
  // Point Picking and Annotate Point (which resolves through this the same
  // way, see resolvePickTarget/addPointNote) only -- an axes with
  // pickable=false (see Axes.set_pickable) is treated as if the click
  // missed every axes, so a figure can restrict picking to a single panel
  // by disabling the rest. Axis Span, Axis Zoom, Pan/Zoom, Annotate, and
  // Annotate Arrow go through axesAt() directly and ignore this flag.
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
    // start + i * step per tick, and the half-open < hi + step/2 bound, both
    // mirroring ticker.nice_ticks' own np.arange: accumulating v += step
    // drifts by a different last bit than numpy's multiply, and a tick landing
    // one ulp either side of a .5 boundary then rounds to a different label
    // here than the static render already drew.
    var start = Math.ceil(lo / step) * step, out = [];
    for (var i = 0; start + i * step < hi + step * 0.5; i++) {
      var v = start + i * step;
      // nice_ticks' own zero snap: an unlucky step (0.02, say) lands the zero
      // tick at ~1e-17, a real position error, not just a label one.
      if (Math.abs(v) < step * 1e-6) v = 0;
      if (v >= lo - step * 1e-6 && v <= hi + step * 1e-6) out.push(v);
    }
    return { ticks: out, step: step };
  }
  // Match the Python renderer's exponential style: "1e5", "1.2e-4".
  // Number.toFixed() rounds a halfway value away from zero; Python's own
  // %-operator and f-strings -- which every tick label in the static render
  // came from -- round half to *even*. Ordinary "nice" ticks land on halves
  // constantly (a [-1, 1] axis ticks at +-0.5), so under a 0-decimal format
  // the same tick read "0" as rendered and "1" after the first zoom. Only the
  // exactly-halfway case differs, so everything else defers to toFixed, which
  // already rounds the decimal representation correctly.
  // The halfway test runs on the value's *exact* decimal expansion, never on
  // v * 10^d: that product re-rounds, and reports 1.234575 -- a double whose
  // exact value is 1.23457499... -- as halfway at 5 decimals, where Python
  // rounds it down. toFixed(d + 25) spells out enough of the expansion to
  // tell a true "...5000" tail from a "...49999" one at every magnitude a
  // tick label stays in fixed notation for (fmtTick hands anything outside
  // 1e-3..1e5 to expFmt instead).
  function pyFixed(v, d) {
    if (!isFinite(v)) return v.toFixed(d);
    var neg = v < 0, a = Math.abs(v);
    var ext = a.toFixed(Math.min(100, d + 25));
    var dot = ext.indexOf('.');
    var digits = ext.slice(0, dot) + ext.slice(dot + 1), keep = dot + d;
    var out;
    if (/^50*$/.test(digits.slice(keep))) {
      var kept = digits.slice(0, keep).split('');
      if ((kept[keep - 1].charCodeAt(0) - 48) % 2 === 1) {   // odd: step to even
        var i = keep - 1;
        while (i >= 0 && kept[i] === '9') { kept[i] = '0'; i--; }
        if (i < 0) kept.unshift('1'); else kept[i] = String(+kept[i] + 1);
      }
      var s = kept.join('');
      out = d ? (s.slice(0, s.length - d) || '0') + '.' + s.slice(s.length - d) : s;
    } else {
      out = a.toFixed(d);
    }
    // Python keeps the sign of a negative value that rounded to zero ("-0").
    return (neg ? '-' : '') + out;
  }
  function expFmt(v, digits) {
    var p = v.toExponential(digits).split('e');
    return p[0].replace(/\.?0+$/, '') + 'e' + parseInt(p[1], 10);
  }
  // Mirrors ticker.format_tick(), which formats a value on its own: six
  // decimals with the trailing zeros stripped, so 2.5 stays "2.5" and 5.0
  // prints "5". `step` is only the zero guard -- a tick that should be
  // exactly 0 but carries float noise (1e-17 off a 0.1 step) has to read "0",
  // not "1e-17", which Python gets for free from an exact `v == 0`.
  //
  // Deriving the decimal count from `step` instead (step >= 1 -> none) held
  // only while every step was a "nice" 1/2/5x10^n one. resolveAxisTicks()
  // back-fills step = ticks[1] - ticks[0] for *minor* ticks' benefit, which
  // hands this a 2.5 or a pi/2 from set_xlocator({"kind": "multiple", ...})
  // -- and "step >= 1 so no decimals" then rounded the labels themselves:
  // an axis Python rendered 0/2.5/5/7.5/10 came back 0/3/5/8/10 after the
  // first pan, wrong numbers under ticks still in the right places.
  function fmtTick(v, step) {
    // `v === 0` is Python's own rule, and the only one that holds when there
    // is no step to scale a tolerance by: resolveAxisTicks leaves step null
    // for a single-tick set (zoom far enough under a coarse locator and one
    // tick is all that is left), and `0 < null * 1e-6` is `0 < 0` -- false,
    // so a tick at 0 fell through to the small-magnitude branch and rendered
    // "0e0". The step term stays for the other case it was written for: a
    // tick that should be 0 but carries float noise off a real step.
    if (v === 0 || (step > 0 && Math.abs(v) < step * 1e-6)) return '0';
    var a = Math.abs(v);
    if (a >= 1e5 || a < 1e-3) return expFmt(v, 1);
    var out = pyFixed(v, 6);
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
    var mant = pyFixed(v / Math.pow(10, exp), dec);
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

