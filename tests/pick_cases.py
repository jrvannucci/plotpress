"""Figures + ground truth for the interactive point-picking tests.

Each case pairs an interactive figure with a list of targets. A target says
"a click at this SVG pixel must produce a marker with these values".

The click pixel is computed with the *renderer's* own transform -- built here
exactly as :func:`plotpress.svg._render_axes` builds it -- so it is the pixel
where the datum is actually drawn. The picking JS has to map that pixel back to
the datum through its own independent machinery (the ``plotpress-meta``
payload plus ``toPixel``). The two paths never share code, so agreement is
evidence rather than tautology.

Where a target's values are sourced from ``pick_data`` instead of from the
source arrays (violin, eventplot offsets), the case notes it: those check index
selection and render/pick agreement, not the payload's numbers.
"""

import math

import numpy as np

import plotpress
from plotpress.svg import _effective_rect, _pixel_rect, pick_data
from plotpress.transform import LinearTransform


class Case:
    def __init__(self, name, fig, targets, note=""):
        self.name = name
        self.fig = fig
        self.targets = targets
        self.note = note

    def __repr__(self):
        return "Case(%s)" % self.name


def _transform(fig, i):
    """The exact LinearTransform the renderer uses for axes ``i``."""
    ax = fig.axes[i]
    dpi = fig.style.dpi
    (xmin, xmax), (ymin, ymax) = ax._resolved_limits()
    rect = _effective_rect(ax, *_pixel_rect(ax, fig.figsize[0] * dpi,
                                            fig.figsize[1] * dpi),
                           (xmin, xmax), (ymin, ymax))
    return LinearTransform((xmax, xmin) if ax._xinverted else (xmin, xmax),
                           (ymax, ymin) if ax._yinverted else (ymin, ymax),
                           rect, xscale=ax._xscale, yscale=ax._yscale)


def px(fig, i, dx, dy):
    """SVG pixel where axes ``i`` draws the data point ``(dx, dy)``."""
    tr = _transform(fig, i)
    return [float(tr.x(dx)), float(tr.y(dy))]


def _points(fig, ax_i, xs, ys, indices, extra=None):
    """Targets for a point series: click each datum, expect its own values."""
    out = []
    for j in indices:
        exp = {"kind": "points", "axes": ax_i, "index": j,
               "x": round(float(xs[j]), 6), "y": round(float(ys[j]), 6)}
        if extra:
            exp.update(extra(j))
        out.append({"px": px(fig, ax_i, xs[j], ys[j]), "expect": exp})
    return out


def build_cases():
    """All picking cases. Figures are built fresh on each call."""
    cases = []
    rng = np.random.default_rng(0)

    # -- line ---------------------------------------------------------------
    x = np.linspace(0, 10, 11)
    y = np.sin(x)
    fig, ax = plotpress.subplots()
    ax.plot(x, y)
    cases.append(Case("line", fig, _points(fig, 0, x, y, (0, 3, 7, 10))))

    # -- scatter, with an extra per-point dimension -------------------------
    sx, sy = rng.uniform(0, 10, 25), rng.uniform(0, 5, 25)
    sc = rng.uniform(0, 1, 25)
    fig, ax = plotpress.subplots()
    ax.scatter(sx, sy, c=sc)
    cases.append(Case("scatter", fig,
                      _points(fig, 0, sx, sy, (0, 5, 17, 24),
                              lambda j: {"c": round(float(sc[j]), 6)}),
                      "the picked point must carry its own c value"))

    # -- bar ----------------------------------------------------------------
    bx = np.arange(5, dtype=float)
    bh = np.array([3.0, 1.5, 4.25, 2.0, 5.5])
    fig, ax = plotpress.subplots()
    ax.bar(bx, bh)
    cases.append(Case("bar", fig,
                      _points(fig, 0, bx, bh, (0, 2, 4),
                              lambda j: {"value": float(bh[j])}),
                      "click each bar's top edge"))

    # -- stem ---------------------------------------------------------------
    tx = np.arange(8, dtype=float)
    ty = np.array([1.0, -2.0, 3.5, 0.5, -1.25, 2.0, 4.0, -0.75])
    fig, ax = plotpress.subplots()
    ax.stem(tx, ty)
    cases.append(Case("stem", fig, _points(fig, 0, tx, ty, (1, 6))))

    # -- errorbar -----------------------------------------------------------
    ex = np.arange(6, dtype=float)
    ey = np.array([2.0, 3.0, 2.5, 4.0, 3.5, 5.0])
    eerr = np.array([0.2, 0.3, 0.1, 0.4, 0.25, 0.15])
    fig, ax = plotpress.subplots()
    ax.errorbar(ex, ey, yerr=eerr)
    cases.append(Case("errorbar", fig,
                      _points(fig, 0, ex, ey, (0, 3, 5),
                              lambda j: {"yerr": float(eerr[j])})))

    # -- quiver -------------------------------------------------------------
    QX, QY = np.meshgrid(np.linspace(0, 4, 5), np.linspace(0, 3, 4))
    QU, QV = np.cos(QX), np.sin(QY)
    fig, ax = plotpress.subplots()
    ax.quiver(QX, QY, QU, QV)
    qx, qy, qu, qv = QX.ravel(), QY.ravel(), QU.ravel(), QV.ravel()
    cases.append(Case("quiver", fig,
                      _points(fig, 0, qx, qy, (0, 7, 19),
                              lambda j: {"u": round(float(qu[j]), 6),
                                         "v": round(float(qv[j]), 6),
                                         "mag": round(float(math.hypot(qu[j], qv[j])), 6)}),
                      "arrows are picked at their tails (the grid nodes)"))

    # -- eventplot ----------------------------------------------------------
    fig, ax = plotpress.subplots()
    ax.eventplot([np.array([1.0, 2.0, 5.0]), np.array([0.5, 3.5])])
    ev = pick_data(fig)[0]["series"][0]
    ev_x = [1.0, 2.0, 5.0, 0.5, 3.5]       # independent ground truth
    cases.append(Case("event", fig, [
        {"px": px(fig, 0, ev["x"][j], ev["y"][j]),
         "expect": {"kind": "points", "axes": 0, "index": j,
                    "x": ev_x[j], "y": ev["y"][j]}}
        for j in (0, 2, 4)], "row offsets come from the payload; x values do not"))

    # -- boxplot: the median is independent ground truth ---------------------
    bdata = [rng.normal(0, 1, 200), rng.normal(3, 2, 200), rng.normal(-2, 0.5, 200)]
    fig, ax = plotpress.subplots()
    ax.boxplot(bdata)
    cases.append(Case("box", fig, [
        {"px": px(fig, 0, i + 1, float(np.median(bdata[i]))),
         "expect": {"kind": "points", "axes": 0, "index": i, "x": float(i + 1),
                    "y": round(float(np.median(bdata[i])), 6)}}
        for i in (0, 1, 2)], "click each box's median line"))

    # -- violin -------------------------------------------------------------
    fig, ax = plotpress.subplots()
    ax.violinplot([rng.normal(0, 1, 200), rng.normal(2, 1, 200)])
    vs = pick_data(fig)[0]["series"][1]
    cases.append(Case("violin", fig,
                      _points(fig, 0, vs["x"], vs["y"], (0, 20, 60)),
                      "payload-sourced click points: checks index selection"))

    # -- fill_between: snaps to the band top --------------------------------
    fx = np.linspace(0, 6, 13)
    fig, ax = plotpress.subplots()
    ax.fill_between(fx, np.sin(fx), np.sin(fx) - 1.0)
    cases.append(Case("fill", fig,
                      _points(fig, 0, fx, np.sin(fx), (0, 6, 12),
                              lambda j: {"lower": round(float(np.sin(fx[j]) - 1.0), 6)}),
                      "picking a band reports the top edge plus 'lower'"))

    # -- pcolormesh ---------------------------------------------------------
    MZ = np.arange(20, dtype=float).reshape(4, 5) * 1.5
    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(6, dtype=float), np.arange(5, dtype=float), MZ)
    cases.append(Case("pcolormesh", fig, [
        {"px": px(fig, 0, col + 0.5, row + 0.5),
         "expect": {"kind": "mesh", "axes": 0, "index": row * 5 + col,
                    "z": float(MZ[row, col]), "x": col + 0.5, "y": row + 0.5}}
        for row, col in [(0, 0), (2, 3), (3, 4), (1, 1)]],
        "click cell centers; payload row 0 is at ymin"))

    # -- imshow, origin='upper': array row 0 is drawn at the TOP -------------
    IA = np.arange(12, dtype=float).reshape(3, 4) * 2.0
    fig, ax = plotpress.subplots()
    ax.imshow(IA, extent=(0, 4, 0, 3), origin="upper")
    img = []
    for arow, acol in [(0, 0), (2, 3), (1, 2)]:
        prow = 3 - 1 - arow                       # payload row (row 0 = ymin)
        img.append({"px": px(fig, 0, acol + 0.5, prow + 0.5),
                    "expect": {"kind": "mesh", "axes": 0, "index": prow * 4 + acol,
                               "z": float(IA[arow, acol]),
                               "x": acol + 0.5, "y": prow + 0.5}})
    cases.append(Case("imshow", fig, img,
                      "A[0, 0] must read at the top-left cell, not bottom-left"))

    # -- pcolormesh, non-uniform rectilinear spacing -------------------------
    # Regression: picking bucketed a click into an evenly-divided extent,
    # which only agreed with the real cell boundaries for a uniform grid.
    NX = np.array([0.0, 1.0, 2.0, 3.0, 50.0])    # last column much wider
    NY = np.array([0.0, 1.0, 2.0, 30.0])          # last row much taller
    NZ = np.arange(12.0).reshape(3, 4)
    fig, ax = plotpress.subplots(figsize=(6, 5))
    ax.pcolormesh(NX, NY, NZ)
    nonuni = []
    for row, col in [(0, 0), (2, 3), (1, 2)]:
        ccx = (NX[col] + NX[col + 1]) / 2.0
        ccy = (NY[row] + NY[row + 1]) / 2.0
        nonuni.append({"px": px(fig, 0, ccx, ccy),
                       "expect": {"kind": "mesh", "axes": 0, "index": row * 4 + col,
                                  "z": float(NZ[row, col]),
                                  "x": round(ccx, 6), "y": round(ccy, 6)}})
    cases.append(Case("pcolormesh_nonuniform", fig, nonuni,
                      "non-uniform cell widths must use the real edges, not "
                      "an evenly divided extent"))

    # -- pcolormesh, curvilinear (warped) grid -------------------------------
    n = 10
    r = np.linspace(0.3, 1, n)
    th = np.linspace(0, 1.5 * math.pi, n)
    R, TH = np.meshgrid(r, th)
    CX, CY = R * np.cos(TH), R * np.sin(TH)
    CZ = np.arange((n - 1) * (n - 1), dtype=float).reshape(n - 1, n - 1)
    fig, ax = plotpress.subplots(figsize=(6, 5))
    m = ax.pcolormesh(CX, CY, CZ, cmap="plasma")
    assert m.curvilinear
    curvi = []
    for i, j in [(2, 2), (5, 5), (7, 3)]:
        ccx = float((CX[i, j] + CX[i, j + 1] + CX[i + 1, j] + CX[i + 1, j + 1]) / 4.0)
        ccy = float((CY[i, j] + CY[i, j + 1] + CY[i + 1, j] + CY[i + 1, j + 1]) / 4.0)
        curvi.append({"px": px(fig, 0, ccx, ccy),
                      "expect": {"kind": "mesh", "axes": 0, "index": i * (n - 1) + j,
                                 "z": float(CZ[i, j]),
                                 "x": round(ccx, 6), "y": round(ccy, 6)}})
    cases.append(Case("pcolormesh_curvilinear", fig, curvi,
                      "a warped grid must pick via nearest cell center, not "
                      "a rectangular extent division"))

    # -- pcolormesh, curvilinear with X/Y the same shape as C -----------------
    # Regression: a warped X/Y sized like a *center* per cell (matching C
    # exactly, via np.meshgrid) rather than one-more-than-C per axis (node
    # corners) is a common, valid pattern -- the renderer already clamps to
    # however many whole cells the two arrays provide (see
    # QuadMesh._rgba_curvilinear). Picking didn't replicate that clamp, so
    # building cell centers indexed one column past X's actual width raised
    # a numpy shape-mismatch error on every figure using this pattern (e.g.
    # a polar radar/sonar scan built from meshgrid(range, azimuth)).
    n_az, n_rng = 8, 6
    az = np.radians(np.linspace(0.0, 315.0, n_az))
    rr = np.linspace(1.0, 6.0, n_rng)
    RR, AZ2 = np.meshgrid(rr, az)
    SX, SY = RR * np.cos(AZ2), RR * np.sin(AZ2)
    SZ = np.arange(n_az * n_rng, dtype=float).reshape(n_az, n_rng)
    fig, ax = plotpress.subplots(figsize=(6, 5))
    m = ax.pcolormesh(SX, SY, SZ, cmap="plasma")
    assert m.curvilinear and SX.shape == SZ.shape
    ny0 = min(SZ.shape[0], SX.shape[0] - 1)
    nx0 = min(SZ.shape[1], SX.shape[1] - 1)
    same_shape = []
    for i, j in [(0, 0), (3, 2), (6, 4)]:
        ccx = float((SX[i, j] + SX[i, j + 1] + SX[i + 1, j] + SX[i + 1, j + 1]) / 4.0)
        ccy = float((SY[i, j] + SY[i, j + 1] + SY[i + 1, j] + SY[i + 1, j + 1]) / 4.0)
        same_shape.append({"px": px(fig, 0, ccx, ccy),
                           "expect": {"kind": "mesh", "axes": 0, "index": i * nx0 + j,
                                      "z": float(SZ[i, j]),
                                      "x": round(ccx, 6), "y": round(ccy, 6)}})
    cases.append(Case("pcolormesh_curvilinear_same_shape_xy", fig, same_shape,
                      "X/Y the same shape as C (centers, not +1-sized node "
                      "corners) must not crash pick_data with a shape "
                      "mismatch, and must clamp exactly like the renderer"))

    # -- contour, non-uniform sample spacing ---------------------------------
    # A contour's "cells" are point samples, not spans -- the reported x/y
    # must be the exact sample coordinate, not the midpoint of its implied
    # (edges-based) span, which only coincides for uniform spacing.
    cx_ = np.array([0.0, 1.0, 2.0, 3.0, 50.0])
    cy_ = np.array([0.0, 1.0, 2.0, 30.0])
    CZg = np.arange(20.0).reshape(4, 5)
    fig, ax = plotpress.subplots(figsize=(6, 5))
    ax.contour(cx_, cy_, CZg)
    cnonuni = []
    for row, col in [(0, 0), (2, 3), (3, 4)]:
        cnonuni.append({"px": px(fig, 0, cx_[col], cy_[row]),
                        "expect": {"kind": "mesh", "axes": 0, "index": row * 5 + col,
                                   "z": float(CZg[row, col]),
                                   "x": float(cx_[col]), "y": float(cy_[row])}})
    cases.append(Case("contour_nonuniform", fig, cnonuni,
                      "a non-uniformly-sampled contour must report the exact "
                      "sample coordinate, not a derived edge midpoint"))

    # -- pie ----------------------------------------------------------------
    pvals, plabels = [40.0, 30.0, 20.0, 10.0], ["a", "b", "c", "d"]
    fig, ax = plotpress.subplots()
    ax.pie(pvals, labels=plabels)
    tr = _transform(fig, 0)
    cx, cy = tr.px_left + tr.px_w / 2, tr.px_top + tr.px_h / 2
    R = 0.42 * min(tr.px_w, tr.px_h)
    fracs = [v / sum(pvals) for v in pvals]
    wedges, ang = [], math.radians(90.0)
    for i, f in enumerate(fracs):
        a1 = ang - f * 2 * math.pi
        mid = (ang + a1) / 2
        wedges.append({"px": [cx + 0.6 * R * math.cos(mid),
                              cy - 0.6 * R * math.sin(mid)],
                       "expect": {"kind": "pie", "axes": 0, "index": i,
                                  "value": pvals[i], "label": plabels[i],
                                  "fraction": round(fracs[i], 6)}})
        ang = a1
    cases.append(Case("pie", fig, wedges,
                      "click each wedge at 0.6R along its bisector"))

    # -- log/log axes -------------------------------------------------------
    lx = np.array([1.0, 10.0, 100.0, 1000.0, 10000.0])
    ly = np.array([2.0, 20.0, 5.0, 500.0, 50.0])
    fig, ax = plotpress.subplots()
    ax.plot(lx, ly)
    ax.set_xscale("log")
    ax.set_yscale("log")
    cases.append(Case("log", fig, _points(fig, 0, lx, ly, (0, 2, 4))))

    # -- inverted axes ------------------------------------------------------
    # Regression: axes_metadata used to omit the inversion flags, so every pick
    # on an inverted axis landed mirrored (picked the wrong point entirely).
    ix = np.linspace(0, 5, 6)
    iy = np.array([1.0, 4.0, 2.0, 5.0, 3.0, 0.5])
    for label, inv_x, inv_y in [("inverted_y", False, True),
                                ("inverted_x", True, False),
                                ("inverted_both", True, True)]:
        fig, ax = plotpress.subplots()
        ax.plot(ix, iy)
        if inv_x:
            ax.invert_xaxis()
        if inv_y:
            ax.invert_yaxis()
        cases.append(Case(label, fig, _points(fig, 0, ix, iy, (0, 3, 5)),
                          "picking must follow the flipped axis"))

    fig, ax = plotpress.subplots()
    ax.plot(lx, ly)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_yaxis()
    cases.append(Case("inverted_log", fig, _points(fig, 0, lx, ly, (0, 2, 4)),
                      "inversion composed with a log scale"))

    fig, ax = plotpress.subplots()
    ax.pcolormesh(np.arange(6, dtype=float), np.arange(5, dtype=float), MZ)
    ax.invert_yaxis()
    cases.append(Case("inverted_mesh", fig, [
        {"px": px(fig, 0, col + 0.5, row + 0.5),
         "expect": {"kind": "mesh", "axes": 0, "index": row * 5 + col,
                    "z": float(MZ[row, col]), "x": col + 0.5, "y": row + 0.5}}
        for row, col in [(0, 0), (2, 3), (3, 4)]],
        "mesh cell lookup on an inverted axis"))

    # -- two subplots: each click must resolve to its own axes --------------
    fig, axs = plotpress.subplots(1, 2)
    axs[0].plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
    axs[1].plot([0.0, 1.0, 2.0], [5.0, 3.0, 7.0])
    cases.append(Case("multi_axes", fig, [
        {"px": px(fig, 0, 1.0, 1.0),
         "expect": {"kind": "points", "axes": 0, "index": 1, "x": 1.0, "y": 1.0}},
        {"px": px(fig, 1, 2.0, 7.0),
         "expect": {"kind": "points", "axes": 1, "index": 2, "x": 2.0, "y": 7.0}},
    ], "a click must not be claimed by the neighbouring subplot"))

    # -- set_aspect shrinks the drawn box inside its allocation -------------
    axx = np.array([0.0, 1.0, 2.0, 3.0])
    axy = np.array([0.0, 2.0, 1.0, 3.0])
    fig, ax = plotpress.subplots()
    ax.plot(axx, axy)
    ax.set_aspect(1.0)
    cases.append(Case("aspect", fig, _points(fig, 0, axx, axy, (0, 1, 3)),
                      "picking must use the box-adjusted rect, not the allocation"))

    # -- inset axes: nested inside its parent's box, but a distinct axes ----
    fig, ax = plotpress.subplots()
    ax.plot([0.0, 10.0], [0.0, 10.0])              # outer data spans the box
    inset = ax.inset_axes([0.5, 0.5, 0.4, 0.4])    # sits inside the parent
    ix, iy = np.array([0.0, 1.0, 2.0]), np.array([0.0, 1.0, 0.0])
    inset.plot(ix, iy)
    inset_i = fig.axes.index(inset)
    cases.append(Case("inset_axes", fig, _points(fig, inset_i, ix, iy, (0, 1, 2)),
                      "a click inside an inset must resolve to the inset, not the "
                      "enclosing parent axes underneath it"))

    # -- fill(): a plain filled polygon had no pick data at all --------------
    fpx = np.array([0.0, 2.0, 2.0, 0.0])
    fpy = np.array([0.0, 0.0, 1.0, 1.0])
    fig, ax = plotpress.subplots()
    ax.fill(fpx, fpy, color="gold")
    cases.append(Case("fill_polygon", fig, _points(fig, 0, fpx, fpy, (0, 1, 2, 3)),
                      "fill() must be pickable at its own vertices"))

    # -- hlines/vlines: a LineCollection had no pick data at all -------------
    fig, ax = plotpress.subplots()
    hy = np.array([1.0, 2.0, 3.0])
    ax.hlines(hy, 0.0, 4.0)
    hcases = [{"px": px(fig, 0, 2.0, hy[j]),
              "expect": {"kind": "points", "axes": 0, "index": j,
                         "x": 2.0, "y": float(hy[j]),
                         "x0": 0.0, "x1": 4.0, "y0": float(hy[j]), "y1": float(hy[j])}}
             for j in (0, 1, 2)]
    cases.append(Case("hlines", fig, hcases,
                      "each hline must report its own x0/x1 span, not just "
                      "the midpoint it was clicked at"))

    fig, ax = plotpress.subplots()
    vx = np.array([1.0, 3.0])
    ax.vlines(vx, 0.0, 4.0)
    vcases = [{"px": px(fig, 0, vx[j], 2.0),
              "expect": {"kind": "points", "axes": 0, "index": j,
                         "x": float(vx[j]), "y": 2.0,
                         "x0": float(vx[j]), "x1": float(vx[j]), "y0": 0.0, "y1": 4.0}}
             for j in (0, 1)]
    cases.append(Case("vlines", fig, vcases,
                      "each vline must report its own y0/y1 span"))

    # -- broken_barh: a PolyCollection had no pick data at all ---------------
    fig, ax = plotpress.subplots()
    ax.broken_barh([(1.0, 2.0), (5.0, 1.0)], (3.0, 1.0))
    cases.append(Case("broken_barh", fig, [
        {"px": px(fig, 0, 2.0, 3.5),
         "expect": {"kind": "points", "axes": 0, "index": 0, "x": 2.0, "y": 3.5,
                    "xmin": 1.0, "xmax": 3.0, "ymin": 3.0, "ymax": 4.0}},
        {"px": px(fig, 0, 5.5, 3.5),
         "expect": {"kind": "points", "axes": 0, "index": 1, "x": 5.5, "y": 3.5,
                    "xmin": 5.0, "xmax": 6.0, "ymin": 3.0, "ymax": 4.0}},
    ], "each rectangle must report its own bounding box"))

    # -- hexbin: a PolyCollection whose per-polygon value (count) the -------
    # facecolors array alone had already thrown away ------------------------
    rng2 = np.random.RandomState(3)
    hx = rng2.normal(size=3000)
    hyv = rng2.normal(size=3000)
    fig, ax = plotpress.subplots()
    hb = ax.hexbin(hx, hyv, gridsize=12)
    busiest = int(np.argmax(hb.counts))
    cx, cy = hb.verts[busiest][:, 0].mean(), hb.verts[busiest][:, 1].mean()
    cases.append(Case("hexbin", fig, [
        {"px": px(fig, 0, cx, cy),
         "expect": {"kind": "points", "axes": 0, "index": busiest,
                    "count": float(hb.counts[busiest])}},
    ], "a hexagon must report its raw count, not just its mapped color"))

    return cases
