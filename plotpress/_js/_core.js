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
  // scales from, and what a pin's own pinScale() compensation (see
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
    centerShrunkFigure();
  });

  // Center a shrunk-below-container figure explicitly, rather than leaning
  // on CSS auto-margin alone. Standalone's body{display:flex} + margin:auto
  // (see Figure.to_html) already centers it correctly on its own -- but an
  // *embedded* figure (an <iframe>, e.g. every application-gallery doc page)
  // has no such rule: its body is plain block flow with the SVG stretching
  // to width:100% by default, so the instant applyZoomSize() below gives it
  // an explicit pixel size smaller than the iframe, a plain block box with
  // no margin just sits flush at the top-left with the rest of the iframe
  // sitting empty. Computing the centering margin here covers both cases
  // uniformly (and is a no-op for standalone, where it just re-derives what
  // the CSS rule there already produces) -- document.documentElement's own
  // client size is "the available space" in either context, since this
  // script runs inside whichever document actually contains the figure.
  function centerShrunkFigure() {
    var target = wrap || svg;
    // Embedded's body reserves real top/bottom padding for the toolbar (see
    // _toolbar_clearance in Figure.to_html) rather than the pure flex slack
    // standalone centers within -- excluding it here keeps a shrunk figure
    // centered in the space actually left *below* the toolbar, not in the
    // full iframe height including the strip the toolbar already occupies.
    var bodyStyle = getComputedStyle(document.body);
    var vPad = parseFloat(bodyStyle.paddingTop) + parseFloat(bodyStyle.paddingBottom);
    var cw = document.documentElement.clientWidth;
    var ch = document.documentElement.clientHeight - vPad;
    // Measure the SVG's own box, not target's: a docked-slider figure's wrap
    // div is display:block with no width of its own (see Figure.to_html), so
    // plain CSS block layout keeps it filling its full container width no
    // matter how small the SVG inside has shrunk -- reading *its* width here
    // is circular (clearing the margin because it "isn't shrunk" is exactly
    // what keeps it un-shrunk next time). The SVG's own rendered size, driven
    // directly by applyZoomSize()'s explicit style.width/height, is always
    // the true figure size, wrapped or not.
    var r = svg.getBoundingClientRect();
    target.style.marginLeft = target.style.marginRight =
      r.width < cw ? ((cw - r.width) / 2) + 'px' : '';
    target.style.marginTop = target.style.marginBottom =
      r.height < ch ? ((ch - r.height) / 2) + 'px' : '';
  }

  function applyZoomSize() {
    sliceScaleCache = null;
    // Zooming *out* (scale < 1) still needs an explicit smaller size applied
    // -- shrinking a figure that overflows the viewport back down to where
    // it fits is exactly the point -- so this checks "not at natural size"
    // rather than "grown past it"; only an exact 1 clears back to the SVG's
    // own natural width/height attributes.
    var sized = zoomScale !== 1;
    // The overflow/scroll CSS switch, though, only makes sense for zooming
    // *in*: a shrunk figure is smaller than its container either way, so
    // body's ordinary flex-centering (with margin:auto on the SVG/wrap --
    // see Figure.to_html) already centers it correctly with no scrollbars
    // needed; switching to block+overflow:auto here too would just drop
    // that centering and leave it pinned to the top-left instead.
    document.body.classList.toggle('plotpress-zoomed', zoomScale > 1);
    if (sized) {
      svg.style.width = (naturalW * zoomScale) + 'px';
      svg.style.height = (naturalH * zoomScale) + 'px';
    } else {
      svg.style.width = ''; svg.style.height = '';
    }
    centerShrunkFigure();
    // Every pin's own pinScale() compensation (see layoutPin) has to be
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
  // 10% (a many-hundred-axes figure at its natural pixel size can be many
  // times larger than any viewport -- "home" is a useful default, not a
  // floor, so zooming out past it has to actually be possible to ever see
  // the whole thing at once) through 20x (beyond that, growing further gains
  // nothing but more scrolling).
  // The compensating scroll below can only re-anchor the cursor's point once
  // there is somewhere to scroll *to* -- while the zoomed-in figure still
  // fits inside the viewport with room to spare, there is no overflow yet
  // for scrollBy() to spend, and the point under the cursor drifts slightly
  // for these first few ticks (layout alone decides where the bigger SVG
  // lands). Self-corrects the moment real overflow exists, which is also
  // the moment "did the point stay under the cursor" starts to matter --
  // nothing is scrolled out of view yet at this stage regardless.
  function zoomTo(clientX, clientY, factor) {
    var newScale = Math.max(0.1, Math.min(20, zoomScale * factor));
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

  // Fit Width: a one-shot snap to whatever scale makes the figure's rendered
  // width match the viewport's current width, right now -- deliberately not
  // a persistent "always fit" mode that keeps re-fitting on every later
  // resize (Home doesn't track resizes after being clicked either; this
  // matches that, rather than introducing a second, different kind of
  // whole-figure reset). Home itself stays "actual size" (zoomScale = 1,
  // i.e. the figure's own figsize/dpi pixel size) and is left alone: most
  // figures are already smaller than the viewport, and folding "fit width"
  // into Home would zoom *those* in past their natural size by default,
  // trading a real regression for the common case to fix the rare
  // wider-than-viewport one. Same clamp as zoomTo() -- a huge multi-hundred-
  // axes figure fitting to a narrow viewport can compute a scale below the
  // 10% floor, and clamping there (rather than letting it go arbitrarily
  // small) keeps every pin/tick/label from shrinking past legibility.
  function fitWidth() {
    var newScale = Math.max(0.1, Math.min(20, document.documentElement.clientWidth / naturalW));
    if (newScale === zoomScale) return;
    zoomScale = newScale;
    applyZoomSize();
  }

  // Map an svg user-space point to pixels within the svg wrapper (honors the
  // current viewBox, so docked sliders track their axes during pan/zoom).
  function positionDocked() {
    if (!wrap || !dockedSliders.length) return;
    var wr = wrap.getBoundingClientRect();
    var ctm = svg.getScreenCTM();
    // All the reads (each box's width) before any write: a style write after
    // every offsetWidth read forced a fresh layout per slider -- seconds, with a
    // thousand docked sliders.
    var widths = dockedSliders.map(function (ds) { return ds.box.offsetWidth; });
    dockedSliders.forEach(function (ds, i) {
      var m = META[ds.axesKey];
      if (!m) return;
      var pt = svg.createSVGPoint();
      pt.x = m.x + m.w / 2; pt.y = m.y + m.h;
      var s = pt.matrixTransform(ctm);
      ds.box.style.left = Math.round(s.x - wr.left - widths[i] / 2) + 'px';
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
  // The layout block is already in the page for the round-trip; Extract reads
  // its figure-level suptitle/supxlabel/supylabel so a picked record from a
  // grid that labels its shared axis once still says what x/y mean.
  var layoutEl = document.getElementById('plotpress-layout');
  var LAYOUT = layoutEl ? JSON.parse(layoutEl.textContent) : {};

  // CUR holds each axes' *current* limits (mutated by per-axes data zoom);
  // META stays the original. All data<->pixel math reads CUR; the artist zoom
  // group is remapped by an affine from META (original) to CUR (current).
  var CUR = {};
  Object.keys(META).forEach(function (k) {
    CUR[k] = {}; for (var f in META[k]) CUR[k][f] = META[k][f];
  });

  var mode = null;             // null => inert (no interaction) by default
  var down = null, moved = false, panV = null, rubber = null, panAxes = null;

