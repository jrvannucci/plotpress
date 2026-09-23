  // ---- Datetime axis ticks/labels -- mirrors plotpress/dates.py exactly ----
  var MS_PER_DAY = 86400000;
  // (step_days, round_unit, strftime-style format) -- same tiers/order as
  // dates._TIERS, so the same span picks the same calendar granularity here
  // as it would re-rendering in Python.
  var DATE_TIERS = [
    [10 * 365.25, 'Y', '%Y'], [5 * 365.25, 'Y', '%Y'], [2 * 365.25, 'Y', '%Y'],
    [365.25, 'Y', '%Y'],
    [6 * 30.44, 'M', '%Y-%m'], [3 * 30.44, 'M', '%Y-%m'], [30.44, 'M', '%Y-%m'],
    [14, 'D', '%m-%d'], [7, 'D', '%m-%d'], [2, 'D', '%m-%d'], [1, 'D', '%m-%d'],
    [0.5, 'h', '%m-%d %H:%M'], [0.25, 'h', '%H:%M'],
    [1 / 24, 'h', '%H:%M'], [1 / 48, 'm', '%H:%M'],
    [10 / 1440, 'm', '%H:%M:%S'], [1 / 1440, 'm', '%H:%M:%S'],
    [10 / 86400, 's', '%H:%M:%S'], [1 / 86400, 's', '%H:%M:%S'],
  ];
  var DATE_UNIT_DAYS = { Y: 365.25, M: 30.44, D: 1, h: 1 / 24, m: 1 / 1440, s: 1 / 86400 };
  function pickDateTier(spanDays) {
    if (!isFinite(spanDays) || spanDays <= 0) return DATE_TIERS[DATE_TIERS.length - 1];
    var target = spanDays / 5.0;
    for (var i = DATE_TIERS.length - 1; i >= 0; i--) {
      if (DATE_TIERS[i][0] >= target) return DATE_TIERS[i];
    }
    return DATE_TIERS[0];
  }
  // Round a UTC Date down to a calendar boundary of `unit` (year/month start,
  // midnight, top of the hour/minute/second) -- mirrors the datetime64 unit
  // cast dates.date_ticks() uses so ticks land on round boundaries, not on
  // whatever fractional day the view happens to start at.
  function truncateDateUTC(d, unit) {
    var t = new Date(d.getTime());
    if (unit === 'Y') { t.setUTCMonth(0, 1); t.setUTCHours(0, 0, 0, 0); }
    else if (unit === 'M') { t.setUTCDate(1); t.setUTCHours(0, 0, 0, 0); }
    else if (unit === 'D') { t.setUTCHours(0, 0, 0, 0); }
    else if (unit === 'h') { t.setUTCMinutes(0, 0, 0); }
    else if (unit === 'm') { t.setUTCSeconds(0, 0); }
    else { t.setUTCMilliseconds(0); }
    return t;
  }
  function addDateUnitsUTC(d, n, unit) {
    var t = new Date(d.getTime());
    if (unit === 'Y') t.setUTCFullYear(t.getUTCFullYear() + n);
    else if (unit === 'M') t.setUTCMonth(t.getUTCMonth() + n);
    else t.setTime(t.getTime() + n * { D: MS_PER_DAY, h: 3600000, m: 60000, s: 1000 }[unit]);
    return t;
  }
  // Mirrors dates.date_ticks(): walk calendar-boundary candidates from one
  // tier-step before `lo` to one past `hi` (so the first/last in-range tick
  // is never missed to rounding), then keep only those inside [lo, hi].
  function jsDateTicks(lo, hi) {
    if (lo > hi) { var t0 = lo; lo = hi; hi = t0; }
    if (lo === hi) { lo -= 1; hi += 1; }
    if (!isFinite(lo) || !isFinite(hi)) return [lo, hi];
    var tier = pickDateTier(hi - lo), step = tier[0], unit = tier[1];
    var stepUnits = Math.max(1, Math.round(step / DATE_UNIT_DAYS[unit]));
    var loD = truncateDateUTC(new Date(Math.round(lo * MS_PER_DAY)), unit);
    var hiD = truncateDateUTC(new Date(Math.round(hi * MS_PER_DAY)), unit);
    var cur = addDateUnitsUTC(loD, -stepUnits, unit);
    var candidates = [];
    for (var guard = 0; guard < 2000; guard++) {
      candidates.push(cur.getTime() / MS_PER_DAY);
      if (cur.getTime() > hiD.getTime()) break;
      cur = addDateUnitsUTC(cur, stepUnits, unit);
    }
    var kept = candidates.filter(function (v) { return v >= lo - 1e-9 && v <= hi + 1e-9; });
    return kept.length ? kept : [lo, hi];
  }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function fmtDateTick(days, fmt) {
    var d = new Date(Math.round(days * MS_PER_DAY));
    var Y = d.getUTCFullYear(), M = pad2(d.getUTCMonth() + 1), D = pad2(d.getUTCDate());
    var h = pad2(d.getUTCHours()), mi = pad2(d.getUTCMinutes()), s = pad2(d.getUTCSeconds());
    if (fmt === '%Y') return String(Y);
    if (fmt === '%Y-%m') return Y + '-' + M;
    if (fmt === '%m-%d') return M + '-' + D;
    if (fmt === '%m-%d %H:%M') return M + '-' + D + ' ' + h + ':' + mi;
    if (fmt === '%H:%M') return h + ':' + mi;
    return h + ':' + mi + ':' + s;   // '%H:%M:%S'
  }
  // Mirrors dates.format_date_ticks(): one calendar tier for the whole set,
  // chosen from the set's own span.
  function jsFormatDateTicks(values) {
    if (!values.length) return [];
    var span = 1.0;
    if (values.length > 1) span = Math.max.apply(null, values) - Math.min.apply(null, values);
    var fmt = pickDateTier(span > 0 ? span : 1.0)[2];
    return values.map(function (v) { return fmtDateTick(v, fmt); });
  }

  // ---- Declarative locator/formatter specs -- mirrors ticker.py exactly,
  // minus a callable formatter (Python-only; see Axes.set_xformat) ----
  function jsMultipleTicks(lo, hi, base, offset) {
    offset = offset || 0;
    if (!(base > 0)) return null;
    // n * base per tick, not a running v += base -- mirrors
    // ticker.multiple_ticks()'s own integer-multiple form, which it uses so
    // the multiple that should land on 0 lands there exactly instead of on
    // accumulated rounding noise.
    var n0 = Math.ceil((lo - offset) / base);
    var n1 = Math.floor((hi + base * 1e-9 - offset) / base);
    var out = [];
    for (var n = n0; n <= n1; n++) out.push(n * base + offset);
    var kept = out.filter(function (v) { return v >= lo - base * 1e-6 && v <= hi + base * 1e-6; });
    // Mirrors ticker.multiple_ticks()'s own fallback: a view with no
    // multiple of base inside it gets the bare range instead of no ticks.
    return kept.length ? kept : [lo, hi];
  }
  function jsApplyLocator(spec, lo, hi) {
    var kind = (spec && typeof spec === 'object') ? spec.kind : spec;
    if (kind === 'multiple') return jsMultipleTicks(lo, hi, spec.base, spec.offset);
    return null;   // unknown kind -- caller falls back to the default scheme
  }
  var SI_PREFIXES = { '-8': 'y', '-7': 'z', '-6': 'a', '-5': 'f', '-4': 'p', '-3': 'n',
    '-2': 'u', '-1': 'm', '0': '', '1': 'k', '2': 'M', '3': 'G', '4': 'T', '5': 'P',
    '6': 'E', '7': 'Z', '8': 'Y' };
  function jsEngTick(v, decimals) {
    if (v === 0) return '0';
    var exp3 = Math.max(-8, Math.min(8, Math.floor(Math.log10(Math.abs(v)) / 3)));
    var mant = pyFixed(v / Math.pow(10, exp3 * 3), decimals);
    if (mant.indexOf('.') >= 0) mant = mant.replace(/0+$/, '').replace(/\.$/, '');
    return mant + SI_PREFIXES[String(exp3)];
  }
  function gcdInt(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { var t = b; b = a % b; a = t; } return a || 1; }
  // Continued-fraction search for the best num/den with den <= maxDenominator
  // approximating x -- the same algorithm Python's Fraction.limit_denominator
  // uses (successive convergents, then a semiconvergent check against the
  // last one that still fits). A fixed round(x*maxDen)/maxDen grid (this
  // function's first version) gets the wrong fraction for any x that isn't
  // already a multiple of 1/maxDenominator -- e.g. pi/5 at maxDenominator=12
  // rounded to pi/6 instead. This matches Python bit-for-bit on every value
  // reachable from a "multiple of pi/k" locator.
  function limitDenominator(x, maxDen) {
    var sign = x < 0 ? -1 : 1;
    x = Math.abs(x);
    var p0 = 0, q0 = 1, p1 = 1, q1 = 0, b = x;
    for (var iter = 0; iter < 64; iter++) {
      var a = Math.floor(b);
      var q2 = q0 + a * q1;
      if (q2 > maxDen) break;
      var p2 = p0 + a * p1;
      p0 = p1; q0 = q1; p1 = p2; q1 = q2;
      var frac = b - a;
      if (frac < 1e-13) break;
      b = 1 / frac;
    }
    if (q1 === 0) return [sign * p0, q0];
    var k = Math.floor((maxDen - q0) / q1);
    var p0k = p0 + k * p1, q0k = q0 + k * q1;
    var candSemi = q0k > 0 ? p0k / q0k : Infinity;
    var candLast = p1 / q1;
    return Math.abs(candLast - x) <= Math.abs(candSemi - x)
      ? [sign * p1, q1] : [sign * p0k, q0k];
  }
  function jsPiTick(v, maxDenominator) {
    if (Math.abs(v) < 1e-12) return '0';
    var frac = limitDenominator(v / Math.PI, maxDenominator);
    var num = frac[0], den = frac[1];
    var g = gcdInt(num, den);
    num /= g; den /= g;
    if (num === 0) return '0';
    var sign = num < 0 ? '-' : '';
    num = Math.abs(num);
    var numStr = num === 1 ? '' : String(num);
    return den === 1 ? (sign + numStr + 'π') : (sign + numStr + 'π/' + den);
  }
  function commaFmt(v, decimals) {
    var s = pyFixed(v, decimals), neg = s.charAt(0) === '-';
    if (neg) s = s.slice(1);
    var parts = s.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (neg ? '-' : '') + parts.join('.');
  }
  // Python-style %g/%G: fixed-point if the exponent is in [-4, sig), else
  // scientific with sig-1 mantissa digits -- either way trimmed of trailing
  // zeros, mirroring what "%g" % v actually does (not just str(v)).
  function _pyStyleG(v, sig, upper) {
    if (v === 0) return '0';
    var exp = Math.floor(Math.log10(Math.abs(v)));
    var s;
    if (exp < -4 || exp >= sig) {
      s = v.toExponential(Math.max(0, sig - 1));
      s = s.replace(/(\.\d*?)0+e/, '$1e').replace(/\.e/, 'e');
      s = s.replace(/e([+-])(\d)$/, 'e$10$2');   // Python zero-pads to 2 exponent digits
    } else {
      s = pyFixed(v, Math.max(0, sig - 1 - exp));
      if (s.indexOf('.') >= 0) s = s.replace(/0+$/, '').replace(/\.$/, '');
    }
    return upper ? s.toUpperCase() : s;
  }
  // A single-conversion %-format mirror (%.2f, %d, $%.0f, "%05.2f", "%.3g",
  // "%.0f%%", ...) -- covers the one-value-per-tick case apply_tick_format()
  // actually needs, matching real Python %-formatting rather than a plain
  // String(v): %d truncates toward zero (not round), 0/space/+ flags and
  // zero-padded width are honored, %g/%G get real significant-digit
  // formatting, %e/%E zero-pad the exponent and case it correctly, and a
  // literal %% next to a real conversion (e.g. "%.0f%%") collapses to one
  // "%" instead of being left untouched by the single regex match.
  function jsPrintfTick(fmt, v) {
    var m = fmt.match(/%([#0+\- ]*)(\d*)(?:\.(\d+))?([sdfeEgG%])/);
    if (!m) return String(v);
    var flags = m[1], width = m[2] ? parseInt(m[2], 10) : 0;
    var prec = m[3] !== undefined ? parseInt(m[3], 10) : null, conv = m[4];
    var out;
    if (conv === '%') {
      out = '%';
    } else if (conv === 'd') {
      out = String(Math.trunc(v));
    } else if (conv === 'f') {
      out = pyFixed(v, prec != null ? prec : 6);
    } else if (conv === 'e' || conv === 'E') {
      out = v.toExponential(prec != null ? prec : 6).replace(/e([+-])(\d)$/, 'e$10$2');
      if (conv === 'E') out = out.toUpperCase();
    } else if (conv === 'g' || conv === 'G') {
      out = _pyStyleG(v, prec != null && prec > 0 ? prec : 6, conv === 'G');
    } else if (conv === 's') {
      out = prec != null ? String(v).slice(0, prec) : String(v);
    } else {
      out = String(v);
    }
    if (conv !== '%' && conv !== 's') {
      if (flags.indexOf('+') >= 0 && v >= 0) out = '+' + out;
      else if (flags.indexOf(' ') >= 0 && v >= 0) out = ' ' + out;
    }
    var zeroPad = flags.indexOf('0') >= 0 && flags.indexOf('-') < 0 && conv !== 's' && conv !== '%';
    while (out.length < width) {
      if (flags.indexOf('-') >= 0) out = out + ' ';
      else if (zeroPad && "+- ".indexOf(out[0]) >= 0) out = out[0] + '0' + out.slice(1);
      else out = (zeroPad ? '0' : ' ') + out;
    }
    // The regex above matches only the first conversion; a literal "%%"
    // elsewhere in the string (a percent suffix is the common case: "%.0f%%")
    // is untouched by that single replace, so collapse it here too.
    return fmt.replace(m[0], out).replace(/%%/g, '%');
  }
  // Mirrors ticker.apply_tick_format(); returns null for a spec it can't
  // apply (an unknown kind, or the None a callable formatter serializes to)
  // so the caller falls back to this axis' default formatting.
  function jsApplyFormat(spec, values) {
    var kind, opts;
    if (spec && typeof spec === 'object') { kind = spec.kind; opts = spec; }
    else { kind = spec; opts = {}; }
    if (kind === 'percent') {
      var decP = opts.decimals != null ? opts.decimals : 0;
      return values.map(function (v) { return pyFixed(v * 100, decP) + '%'; });
    }
    if (kind === 'comma' || kind === 'thousands') {
      var decC = opts.decimals != null ? opts.decimals : 0;
      return values.map(function (v) { return commaFmt(v, decC); });
    }
    if (kind === 'eng' || kind === 'engineering') {
      var decE = opts.decimals != null ? opts.decimals : 1;
      return values.map(function (v) { return jsEngTick(v, decE); });
    }
    if (kind === 'pi' || kind === 'multiple_of_pi') {
      var maxDen = opts.max_denominator != null ? opts.max_denominator : 12;
      return values.map(function (v) { return jsPiTick(v, maxDen); });
    }
    if (typeof kind === 'string' && kind.indexOf('%') >= 0) {
      return values.map(function (v) { return jsPrintfTick(kind, v); });
    }
    return null;
  }
  // One category position per index, filtered to the current view (falling
  // back to the full set if a zoom/pan pushed every category out of range) --
  // mirrors ticker.resolve_axis_ticks()'s categorical branch.
  function jsCategoryTicks(lo, hi, nCategories) {
    var cats = [];
    for (var i = 0; i < nCategories; i++) cats.push(i);
    var kept = cats.filter(function (v) { return v >= lo - 1e-9 && v <= hi + 1e-9; });
    return kept.length ? kept : cats;
  }
  // The full per-axis tick + label resolution, at the same priority
  // ticker.resolve_axis_ticks()/resolve_axis_tick_labels() apply in Python:
  // categorical > locator (ticks) / format (labels) > date > log/default.
  // `om` is this axes' own axes_metadata() entry; `isX` picks the x or y half.
  function resolveAxisTicks(om, lo, hi, scale, isX) {
    var categorical = isX ? om.xcategorical : om.ycategorical;
    var categories = isX ? om.xcategories : om.ycategories;
    var locator = isX ? om.xlocator : om.ylocator;
    var isDate = isX ? om.xdate : om.ydate;
    var fmt = isX ? om.xformat : om.yformat;

    var ticks, step = null, labels;
    if (categorical) {
      ticks = jsCategoryTicks(lo, hi, (categories || []).length);
    } else if (locator) {
      ticks = jsApplyLocator(locator, lo, hi);
      if (ticks === null) { var rl = jsNiceTicks(lo, hi, 5); ticks = rl.ticks; step = rl.step; }
    } else if (isDate) {
      ticks = jsDateTicks(lo, hi);
    } else if (scale === 'log') {
      ticks = jsLogTicks(lo, hi);
    } else {
      var r = jsNiceTicks(lo, hi, 5);
      ticks = r.ticks; step = r.step;
    }
    // jsMinorTicks() (like ticker.minor_ticks()) derives its own subdivision
    // step from ticks[1]-ticks[0] regardless of flavor -- fill it in here too
    // so a date/categorical/locator axis with minor ticks on doesn't lose
    // them on the first zoom/pan just because this branch never computed one.
    if (step === null && ticks.length >= 2) step = ticks[1] - ticks[0];

    if (categorical) {
      labels = ticks.map(function (v) {
        var i = Math.round(v);
        return (categories && categories[i] != null) ? categories[i] : '';
      });
    } else if (fmt) {
      labels = jsApplyFormat(fmt, ticks);
      if (labels === null) {
        labels = isDate ? jsFormatDateTicks(ticks)
               : scale === 'log' ? ticks.map(function (v) { return fmtNum(v); })
               : fmtTickSet(ticks, step);
      }
    } else if (isDate) {
      labels = jsFormatDateTicks(ticks);
    } else if (scale === 'log') {
      labels = ticks.map(function (v) { return fmtNum(v); });
    } else {
      labels = fmtTickSet(ticks, step);
    }
    return { ticks: ticks, labels: labels, step: step };
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
      rot: ov.tick_label_rotation !== undefined ? ov.tick_label_rotation : (base.rot || 0),
    };
  }

  // Rebuild an axes' grid + ticks + numeric labels from its current limits.
  function rebuildTicks(key) {
    var om = META[key];
    if (!om || om.axis_off || om.xfixed || om.yfixed) return;  // leave as rendered
    var g = document.getElementById('ticks' + key);
    if (!g) return;
    var m = CUR[key];
    var xr = resolveAxisTicks(om, m.xmin, m.xmax, m.xscale, true);
    var yr = resolveAxisTicks(om, m.ymin, m.ymax, m.yscale, false);
    // A twinx draws only its y-axis (on the right), a twiny only its x-axis (on
    // top) -- the other axis is the parent's, which draws it. Rebuilding both
    // doubled the parent's labels and, for the y-axis, drew them on the wrong edge.
    var twinOnlyY = om.twin_of != null && om.yside === 'right';
    var twinOnlyX = om.twin_of != null && om.xside === 'top';
    if (twinOnlyY) xr = { ticks: [], labels: [], step: xr.step };
    if (twinOnlyX) yr = { ticks: [], labels: [], step: yr.step };
    var parts = [];
    var xTop = om.xside === 'top', yRight = om.yside === 'right';
    var xAxis = xTop ? m.y : m.y + m.h, xSign = xTop ? -1 : 1;
    var yAxis = yRight ? m.x + m.w : (m.tickAnchorX != null ? m.tickAnchorX : m.x);
    var ySign = yRight ? 1 : -1;

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
      // om.grid_alpha is null unless grid(alpha=...) actually overrode the
      // figure default -- a plain `||` would also treat a real alpha=0
      // override as falsy and silently revert to the figure default.
      var gridAlpha = (om.grid_alpha == null) ? STYLE.grid_alpha : om.grid_alpha;
      var gAxis = om.grid_axis || 'both', gWhich = om.grid_which || 'major';
      var buildGridLines = function (xs, ys) {
        var gl = [];
        if (gAxis !== 'y') xs.forEach(function (xt) { var px = toPixel(m, xt, m.ymin).x;
          gl.push('<line x1="' + px.toFixed(2) + '" y1="' + m.y.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + (m.y + m.h).toFixed(2) + '"/>'); });
        if (gAxis !== 'x') ys.forEach(function (yt) { var py = toPixel(m, m.xmin, yt).y;
          gl.push('<line x1="' + m.x.toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + (m.x + m.w).toFixed(2) + '" y2="' + py.toFixed(2) + '"/>'); });
        return gl;
      };
      if (gWhich === 'major' || gWhich === 'both') {
        var majorGl = buildGridLines(xr.ticks, yr.ticks);
        parts.push('<g stroke="' + STYLE.grid_color + '" stroke-width="' + STYLE.grid_width + '" stroke-opacity="' + gridAlpha + '">' + majorGl.join('') + '</g>');
      }
      if (gWhich === 'minor' || gWhich === 'both') {
        var xMinorG = jsMinorTicks(xr.ticks, xr.step, m.xmin, m.xmax, m.xscale);
        var yMinorG = jsMinorTicks(yr.ticks, yr.step, m.ymin, m.ymax, m.yscale);
        var minorGl = buildGridLines(xMinorG, yMinorG);
        parts.push('<g stroke="' + STYLE.grid_color + '" stroke-width="' + (STYLE.grid_width * 0.6) + '" stroke-opacity="' + (gridAlpha * 0.6) + '">' + minorGl.join('') + '</g>');
      }
    }
    var xmarks = [], ymarks = [], labels = [];
    xr.ticks.forEach(function (xt, i) {
      var px = toPixel(m, xt, m.ymin).x;
      var ly = xAxis + xSign * xStyle.ts + (xTop ? -3 : xStyle.fs);
      xmarks.push('<line x1="' + px.toFixed(2) + '" y1="' + xAxis.toFixed(2) + '" x2="' + px.toFixed(2) + '" y2="' + (xAxis + xSign * xStyle.ts).toFixed(2) + '"/>');
      // Mirrors svg._render_ticks: a rotated label anchors at its own end
      // (against the tick), not centered, or it would straddle the tick
      // edge-on instead of tilting away from it.
      var xAnchor = xStyle.rot ? 'end' : 'middle';
      var xRot = xStyle.rot ? ' transform="rotate(' + (-xStyle.rot) + ' ' + px.toFixed(2) + ' ' + ly.toFixed(2) + ')"' : '';
      labels.push('<text x="' + px.toFixed(2) + '" y="' + ly.toFixed(2) + '" text-anchor="' + xAnchor + '" font-size="' + xStyle.fs + '" fill="' + xStyle.text + '"' + xRot + '>' + xr.labels[i] + '</text>');
    });
    yr.ticks.forEach(function (yt, i) {
      var py = toPixel(m, m.xmin, yt).y;
      var lx = yAxis + ySign * yStyle.ts + (yRight ? 2 : -2);
      var ly2 = py + yStyle.fs * 0.35;
      ymarks.push('<line x1="' + yAxis.toFixed(2) + '" y1="' + py.toFixed(2) + '" x2="' + (yAxis + ySign * yStyle.ts).toFixed(2) + '" y2="' + py.toFixed(2) + '"/>');
      var yRotAttr = yStyle.rot ? ' transform="rotate(' + (-yStyle.rot) + ' ' + lx.toFixed(2) + ' ' + ly2.toFixed(2) + ')"' : '';
      labels.push('<text x="' + lx.toFixed(2) + '" y="' + ly2.toFixed(2) + '" text-anchor="' + (yRight ? 'start' : 'end') + '" font-size="' + yStyle.fs + '" fill="' + yStyle.text + '"' + yRotAttr + '>' + yr.labels[i] + '</text>');
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
    // c's pixel rect is normally o's, but the Slice companion panel shrinks
    // it to the heatmap's share of the axes, so the remap has to carry the
    // rect change too -- with equal rects this reduces to the plain
    // limits-only remap.
    var sx = (ofx1 - ofx0) / (cfx1 - cfx0) * (c.w / o.w);
    var sy = (ofy1 - ofy0) / (cfy1 - cfy0) * (c.h / o.h);
    var tx = c.x + (ofx0 - cfx0) / (cfx1 - cfx0) * c.w - sx * o.x;
    var ty = c.y + (cfy1 - ofy1) / (cfy1 - cfy0) * c.h - sy * o.y;
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
  // Every pin ever added (see addPin), so relayoutPins() -- run once per axes, and
  // the Slice layout runs it for a thousand at a time -- walks the handful of pins
  // there are instead of scanning the whole document for them each time. Removed
  // pins are dropped lazily, by their isConnected flag.
  var PIN_REGISTRY = [];
  function livePins() {
    if (PIN_REGISTRY.length) {
      var live = PIN_REGISTRY.filter(function (p) { return p.isConnected; });
      if (live.length !== PIN_REGISTRY.length) PIN_REGISTRY = live;
    }
    return PIN_REGISTRY;
  }
  function relayoutPins(key) {
    livePins().forEach(function (pin) {
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
  // The data-anchored text groups are part of the static render and never come or
  // go, so they're indexed by axes once instead of being searched for per call.
  var CSCALE_BY_AXES = null;
  function relayoutTextCounterScale(key) {
    if (CSCALE_BY_AXES === null) {
      CSCALE_BY_AXES = {};
      document.querySelectorAll('.plotpress-cscale').forEach(function (g) {
        (CSCALE_BY_AXES[g.dataset.axes] = CSCALE_BY_AXES[g.dataset.axes] || []).push(g);
      });
    }
    var groups = CSCALE_BY_AXES[String(key)];
    if (!groups) return;
    var t = zoomAffine(key);
    groups.forEach(function (g) {
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
    syncLinked(key); resyncSlice(key);
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
    syncLinked(key); resyncSlice(key);
    // Copying META's rect back above also undid any Slice companion layout:
    // an axes under a strip belongs in the heatmap's *share* of that rect,
    // not the whole thing. resyncSlice() just re-applied it for a sliced
    // axes itself; a twin/secondary has no slice of its own, so ask the
    // parent that owns the split to re-apply it (for both of them).
    var om = META[key], owner = om.twin_of != null ? om.twin_of : om.secondary_of;
    if (owner != null) resyncSlice(String(owner));
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
  // pinScale()) instead of baking px/py straight into each child. Whole-
  // figure zoom (see applyZoomSize) grows or shrinks the *entire* SVG's
  // rendered CSS size uniformly, which would otherwise carry a pin's fixed
  // viewBox-unit radius up right along with the data -- readable as "8px" at
  // rest and a 50px+ blob covering the very mesh cell it points at eight
  // ticks of Magnify later. pinScale() cancels that on the way *in* (a pin
  // stays constant on-screen size), and deliberately does not on the way
  // *out* (a pin shrinks with the figure it belongs to, rather than swelling
  // to cover several panels) -- see pinScale's own comment. updatePinTransform()
  // (called from applyZoomSize() for every existing pin, not just the one
  // being laid out here) keeps that current as zoomScale changes after the
  // pin already exists.
  function layoutPin(g, px, py, label) {
    var fs = 11, padx = 5, pady = 3;
    var bw = label.length * fs * 0.55 + padx * 2, bh = fs + pady * 2;
    var dot = g.querySelector('circle'), rect = g.querySelector('rect'),
        text = g.querySelector('text'), arrow = g.querySelector('.plotpress-pin-arrow');
    // A plain Annotate box (no dot, see addPin's own plain param) has no
    // "point at the dot" to offset from -- its default position centers the
    // box directly on the anchor instead of floating it up and to the right
    // of a dot that doesn't exist. A user-dragged box (see startBoxDrag)
    // keeps its own chosen offset across every later re-layout (pan, zoom,
    // arrow-key step) regardless of which default it started from.
    var bx = g.dataset.boxDx !== undefined ? +g.dataset.boxDx : (dot ? 8 : -bw / 2);
    var by = g.dataset.boxDy !== undefined ? +g.dataset.boxDy : (dot ? -bh - 4 : -bh / 2);
    if (dot) { dot.setAttribute('cx', 0); dot.setAttribute('cy', 0); }
    rect.setAttribute('x', bx); rect.setAttribute('y', by);
    rect.setAttribute('width', bw); rect.setAttribute('height', bh);
    text.setAttribute('x', bx + padx); text.setAttribute('y', by + fs + pady - 2);
    text.textContent = label;
    syncPinArrow(g);
    g.dataset.anchorX = px; g.dataset.anchorY = py;
    updatePinTransform(g);
    applySliceVisibility(g);
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

  // A pin/note group's own scale factor under whole-figure zoom. Zooming
  // *in* (zoomScale > 1) counter-scales by 1/zoomScale so a pin stays a
  // constant on-screen size instead of ballooning into a blob over the very
  // cell it points at. Zooming *out* (zoomScale < 1) does NOT counter-scale:
  // there the whole figure is shrinking to fit, and a pin/label frozen at
  // constant screen size would instead swell to cover multiple panels --
  // it should shrink right along with the figure it belongs to. Clamping
  // the denominator at 1 gives constant-screen-size on the way in and
  // sized-to-the-figure on the way out.
  function pinScale() { return 1 / Math.max(1, zoomScale); }

  function updatePinTransform(g) {
    g.setAttribute('transform', 'translate(' + g.dataset.anchorX + ',' +
      g.dataset.anchorY + ') scale(' + pinScale() + ')');
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

  function addPin(px, py, label, axesKey, plain) {
    var g = document.createElementNS(SVGNS, 'g');
    PIN_REGISTRY.push(g);
    g.setAttribute('class', 'plotpress-pin'); g.style.cursor = 'pointer';
    var r = pinRadius(axesKey);
    g.dataset.pinR = r;
    // A plain Annotate box (see addPlainNote) skips the dot and leader arrow
    // entirely -- it's a caption sitting at its own position, not a callout
    // pointing at something else. layoutPin/syncPinArrow/selectPin all
    // already tolerate a missing dot/arrow (querySelector returns null).
    if (!plain) {
      var dot = document.createElementNS(SVGNS, 'circle');
      dot.setAttribute('r', r); dot.setAttribute('fill', '#111');
      dot.setAttribute('stroke', '#fff'); dot.setAttribute('stroke-width', 1);
      var arrow = document.createElementNS(SVGNS, 'line');
      arrow.setAttribute('class', 'plotpress-pin-arrow');
      arrow.setAttribute('stroke', '#666'); arrow.setAttribute('stroke-width', 1);
      arrow.setAttribute('marker-end', 'url(#plotpress-pin-arrow)');
      g.appendChild(dot); g.appendChild(arrow);
    }
    var rect = document.createElementNS(SVGNS, 'rect');
    rect.setAttribute('rx', 3); rect.setAttribute('fill', '#111');
    rect.setAttribute('fill-opacity', 0.85);
    var text = document.createElementNS(SVGNS, 'text');
    text.setAttribute('font-size', 11); text.setAttribute('fill', '#fff');
    g.appendChild(rect); g.appendChild(text);
    layoutPin(g, px, py, label);
    // Left-click selects (arrow keys then step it); right-click deletes;
    // a left-click/drag specifically on the box (not the dot) repositions
    // its label -- see startBoxDrag -- while the mode that would have
    // created this kind of pin is the active one (boxDraggableNow).
    g.addEventListener('click', function (ev) { ev.stopPropagation(); selectPin(g); });
    g.addEventListener('contextmenu', function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      if (g.classList.contains('plotpress-snapped')) return;   // rebuilt from its heatmap pin
      if (selectedPin === g) selectedPin = null;
      g.remove();
      if (SLICE_SNAP) syncSnappedPins();
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

  // A Point Picking pin is draggable exactly under 'pick', its own creating
  // mode -- but any annotation note is draggable under *any* of the three
  // Annotate modes, not just its own matching one: repositioning a note you
  // dropped earlier is routine housekeeping while annotating a figure, and
  // making that depend on first reselecting that note's own exact flavor
  // (plain vs. arrow vs. point) would be a pointless extra step with no
  // upside -- nothing about *dragging* a box needs to know which flavor it
  // is, only *creating* one does (see the click dispatch below) or
  // *restoring* one (dataset.noteStyle still has to survive a save/reload
  // for that, and for addPin's own dot/arrow decision -- see restorePins).
  // The same annotation/point split Clear Points/Clear Annotations already
  // use (see isAnnotationPin above).
  function boxDraggableNow(g) {
    return isAnnotationPin(g) ? isAnnotateMode(mode) : mode === 'pick';
  }

  // 'note-plain'/'note-free'/'note-point' -- the three Annotate menu tools,
  // as a group, wherever code needs "is some Annotate tool active" without
  // caring which. Kept in one place so this and the cursor-style switch
  // above can't quietly drift apart from each other or from TOOLS itself.
  function isAnnotateMode(m) {
    return m === 'note-plain' || m === 'note-free' || m === 'note-point';
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
  // pinScale() user-space units (the group's own scale(pinScale()) transform),
  // and a user-space unit is 1/pxPerUser() screen pixels -- so a screen delta
  // needs dividing by pinScale() and by pxPerUser() to land in local units,
  // the exact inverse of what rendering does to local coordinates to put them
  // on screen.
  function startBoxDrag(g, ev) {
    ev.stopPropagation(); ev.preventDefault();
    selectPin(g);
    var startX = ev.clientX, startY = ev.clientY;
    var rect = g.querySelector('rect');
    var bx0 = +rect.getAttribute('x'), by0 = +rect.getAttribute('y');
    var text = g.querySelector('text');
    function onMove(e) {
      var k = 1 / (pinScale() * pxPerUser());
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
    if (anchor.kind === 'slice') return slicePinPoint(anchor.axes, index);
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
    if (anchor.kind === 'slice') {
      // Along the profile only: one step per sample in the direction the
      // shared axis runs; the other arrows have nothing to step to.
      var isXs = SLICE_ORIENTATION === 'x';
      var alongKeys = isXs ? (dir === 'right' || dir === 'left') : (dir === 'up' || dir === 'down');
      if (!alongKeys) return index;
      var am2 = META[anchor.axes] || {};
      var flipped = isXs ? am2.xinv : am2.yinv;
      var forward = isXs ? dir === 'right' : dir === 'up';
      return index + ((forward ? 1 : -1) * (flipped ? -1 : 1));
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
    if (k === 'slice') return { kind: 'slice', axes: pin.dataset.axes };
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
    } else if (anchor.kind === 'slice') {
      g.dataset.axes = anchor.axes;
    } else {
      g.dataset.axes = anchor.axes; g.dataset.series = anchor.series;
      g.dataset.ptype = anchor.ptype;
    }
    // addPin() already refreshed drag-readiness once, before the
    // .plotpress-note class above (set for an Annotate Point pin, or one
    // restored from a saved file) was applied -- that class is what
    // boxDraggableNow() itself keys its point-picking-vs-annotation split
    // on, so it has to run again now that it's actually set.
    if (text !== undefined) refreshOneDragReady(g);
    // Needs dataset.axes (set above), which layoutPin's own call in addPin
    // ran too early to see.
    applySliceVisibility(g);
    if (SLICE_SNAP && (anchor.kind === 'mesh' || anchor.kind === 'meshframe' || anchor.kind === 'slice')) {
      syncSnappedPins();
    }
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
    if (SLICE_SNAP && (anchor.kind === 'mesh' || anchor.kind === 'meshframe' || anchor.kind === 'slice')) {
      syncSnappedPins();
    }
  }

