  // ---- helpers -----------------------------------------------------------
  function toUser(e) {
    var pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }
  // pxPerUser() reads the svg's rendered size, which forces a synchronous layout
  // -- and drawing one Slice cursor per axes after each other's DOM writes turned
  // that into one forced layout *per axes* (seconds, at a thousand). The scale
  // can't change mid-task, so it's read once per task and reused; applyZoomSize()
  // (the only thing that resizes the svg) clears it.
  var sliceScaleCache = null;
  function sliceScale() {
    if (sliceScaleCache === null) {
      sliceScaleCache = pxPerUser();
      Promise.resolve().then(function () { sliceScaleCache = null; });
    }
    return sliceScaleCache;
  }
  function pxPerUser() {
    return svg.getBoundingClientRect().width / view[2];
  }

  // ---- rubber-band box (zoom mode) --------------------------------------
  function startRubber(e) {
    var p = toUser(e);
    var el = document.createElementNS(SVGNS, 'rect');
    el.setAttribute('class', 'plotpress-rubber');
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
  // On window, not the SVG: this is a *whole-page* gesture (zoomTo() only
  // ever reads e.clientX/clientY, never e.target), and the SVG is exactly
  // what shrinks out from under the cursor as soon as a zoom-out drops it
  // below the viewport size -- margin:auto then centers a much smaller box
  // in a sea of page background (see Figure.to_html), so a listener scoped
  // to the SVG itself left every wheel tick over that background silently
  // dead, with no way to zoom back in short of physically relocating the
  // cursor onto the now-tiny figure.
  window.addEventListener('wheel', function (e) {
    // Under Zoom, only Ctrl+wheel (or a trackpad pinch, which the browser
    // reports as a wheel event with ctrlKey already set) zooms -- a plain
    // scroll must fall through to the page's own scrolling untouched, the
    // same as it would over any other content, rather than this figure
    // hijacking it just because Zoom happens to be the active tool. Magnify
    // is the explicit opt-in past that: selecting it says a plain wheel
    // here should zoom, Ctrl or not -- for wherever holding Ctrl is awkward
    // or already claimed by the browser/OS.
    var zooming = mode === 'magnify' || (mode === 'zoom' && e.ctrlKey);
    if (!zooming) return;
    e.preventDefault();
    zoomTo(e.clientX, e.clientY, e.deltaY < 0 ? 1.25 : 0.8);
  }, { passive: false });

  // Whole-figure pan: scrolls the page, exactly what the wheel now does
  // under Magnify (or Ctrl+wheel under Zoom) by growing the SVG's own
  // rendered size -- never an individual axes' own data range/ticks.
  // Shared by Span's "over the margins" drag and Magnify's drag, so a
  // zoomed-in view stays reachable in every direction without leaving the
  // tool that zoomed it.
  function panWholeFigureTo(e) {
    window.scrollTo(panV.x - (e.clientX - down.x), panV.y - (e.clientY - down.y));
  }

  svg.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;   // ignore right/middle button (right = delete pin)
    if (!mode || e.target.closest('.plotpress-pin')) return;
    down = { x: e.clientX, y: e.clientY }; moved = false;
    if (mode === 'span') {
      var pdn = toUser(e), a = axesAt(pdn);
      if (a) {
        // per-axes data pan over a plot (directed edges: honors inverted axes)
        panAxes = { key: a.i, downUser: pdn, start: edges(CUR[a.i]) };
      } else {
        panV = { x: window.scrollX, y: window.scrollY };   // over margins: whole-figure pan
      }
      svg.style.cursor = 'grabbing';
    } else if (mode === 'zoom') { startRubber(e); }
    else if (mode === 'magnify') {
      // Always the whole-figure view, regardless of what's under the
      // cursor -- Magnify never touches axes data, only what part of the
      // rendered figure is currently visible (see the wheel handler above).
      panV = { x: window.scrollX, y: window.scrollY };
      svg.style.cursor = 'grabbing';
    }
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
    } else if (mode === 'span' || mode === 'magnify') {
      panWholeFigureTo(e);
    } else if (mode === 'zoom' && rubber) {
      updateRubber(e);
    }
  });
  window.addEventListener('mouseup', function (e) {
    if (!down) return;
    if (mode === 'span') svg.style.cursor = 'grab';
    else if (mode === 'magnify') svg.style.cursor = 'zoom-in';
    else if (mode === 'zoom' && rubber) finishRubber(e);
    down = null; panAxes = null;
  });

