// Drives a REAL "Axis Zoom" drag on the real toolbar of an interactive
// figure, then reads back the resolved view range and the tick labels the
// client-side JS rebuild actually rendered for it.
//
// Nothing here reaches into plotpress's own JS internals (resolveAxisTicks,
// jsPiTick, ...) -- it only uses the same public surface a real user's mouse
// would (real MouseEvents on the real toolbar button and the real <svg>) and
// the same public window.plotpressToData() a custom tool would use (see
// plotpress/_interactive.py's own doc comment on it). That keeps this a
// true end-to-end regression test of the zoom -> tick-rebuild path, not a
// test of a separate test-only hook that could itself drift from the real
// one.
//
// `args`: {x0, y0, x1, y1, axesIndex} -- x0/y0/x1/y1 are SVG user-space
// pixel coordinates for the rubber-band drag (see tests/test_tick_parity_
// interactive.py for how they're derived from the axes' own pixel rect).
(function (args) {
  var svg = document.getElementById('plotpress-svg');
  if (!svg) return { error: 'no #plotpress-svg in the document' };

  function toClient(ux, uy) {
    var pt = svg.createSVGPoint();
    pt.x = ux;
    pt.y = uy;
    return pt.matrixTransform(svg.getScreenCTM());
  }

  var zoomBtn = null;
  document.querySelectorAll('.plotpress-toolbar button').forEach(function (b) {
    if (b.textContent === 'Axis Zoom') zoomBtn = b;
  });
  if (!zoomBtn) return { error: 'no "Axis Zoom" button in the toolbar' };
  if (!zoomBtn.classList.contains('active')) zoomBtn.click();

  var a = toClient(args.x0, args.y0), b = toClient(args.x1, args.y1);
  var opts = { bubbles: true, cancelable: true, button: 0 };
  svg.dispatchEvent(new MouseEvent('mousedown',
    Object.assign({ clientX: a.x, clientY: a.y }, opts)));
  svg.dispatchEvent(new MouseEvent('mousemove',
    Object.assign({ clientX: b.x, clientY: b.y }, opts)));
  svg.dispatchEvent(new MouseEvent('mouseup',
    Object.assign({ clientX: b.x, clientY: b.y }, opts)));

  if (typeof window.plotpressToData !== 'function') {
    return { error: 'window.plotpressToData is missing' };
  }
  // Read back the CURRENT resolved view by asking for the data coordinates
  // at the axes' own full pixel-box corners (inset by 1px so the boundary
  // check in axesAt() -- inclusive, but floating-point-adjacent -- can't
  // miss) -- valid before OR after a zoom, since these always sit at the
  // domain's own edges regardless of what that domain currently is.
  var box = args.box;
  var topLeft = window.plotpressToData({ x: box.x + 1, y: box.y + 1 });
  var bottomRight = window.plotpressToData({
    x: box.x + box.w - 1, y: box.y + box.h - 1,
  });
  if (!topLeft || !bottomRight) return { error: 'plotpressToData missed the axes' };

  var g = document.getElementById('ticks' + args.axesIndex);
  var labels = g ? Array.prototype.map.call(g.querySelectorAll('text'), function (t) {
    return t.textContent;
  }) : [];

  return {
    xrange: [Math.min(topLeft.x, bottomRight.x), Math.max(topLeft.x, bottomRight.x)],
    yrange: [Math.min(topLeft.y, bottomRight.y), Math.max(topLeft.y, bottomRight.y)],
    labels: labels,
  };
})
