// Drives the real point-picking UI of an interactive figure.
//
// Runs inside the page against unmodified fig.to_html() output: it selects
// "Point Pick" through the actual toolbar button, dispatches a real click at
// the pixel where the renderer drew a known datum, and reads the resulting
// marker back through the public window.simpleplotGetMarkers() API. Nothing
// here reaches into the picking code's internals.
//
// Takes the target list (see tests/pick_cases.py) and returns one result per
// target, so a failure names the field that disagreed.
(function (targets) {
  var svg = document.getElementById('simpleplot-svg');
  if (!svg) return { error: 'no #simpleplot-svg in the document' };
  if (typeof window.simpleplotGetMarkers !== 'function') {
    return { error: 'window.simpleplotGetMarkers is missing' };
  }

  var pick = null;
  document.querySelectorAll('.simpleplot-toolbar button').forEach(function (b) {
    if (b.textContent === 'Point Pick') pick = b;
  });
  if (!pick) return { error: 'no "Point Pick" button in the toolbar' };
  if (!pick.classList.contains('active')) pick.click();

  function clearPins() {
    document.querySelectorAll('.simpleplot-pin').forEach(function (p) {
      p.remove();
    });
  }

  // SVG user-space pixel -> viewport client coordinates.
  function toClient(ux, uy) {
    var pt = svg.createSVGPoint();
    pt.x = ux;
    pt.y = uy;
    return pt.matrixTransform(svg.getScreenCTM());
  }

  // Marker values are rounded to 6 decimals on the way into the payload, so
  // compare with a tolerance rather than exactly.
  function near(got, want) {
    if (typeof want !== 'number' || typeof got !== 'number') return got === want;
    return Math.abs(got - want) <= 1e-6 + 1e-6 * Math.abs(want);
  }

  var results = [];
  targets.forEach(function (t, ti) {
    clearPins();                       // each target starts from a clean slate
    var c = toClient(t.px[0], t.px[1]);
    var el = document.elementFromPoint(c.x, c.y) || svg;
    el.dispatchEvent(new MouseEvent('click', {
      bubbles: true, cancelable: true, clientX: c.x, clientY: c.y, button: 0
    }));

    var markers = window.simpleplotGetMarkers();
    var got = markers.length ? markers[markers.length - 1] : null;
    var bad = [];
    if (!got) {
      bad.push('no marker was created by the click');
    } else {
      Object.keys(t.expect).forEach(function (k) {
        if (!near(got[k], t.expect[k])) {
          bad.push(k + ': got ' + JSON.stringify(got[k]) +
                   ', want ' + JSON.stringify(t.expect[k]));
        }
      });
    }
    results.push({ target: ti, px: t.px, expect: t.expect, got: got,
                   markers: markers.length, bad: bad });
  });
  clearPins();

  return { results: results };
})
