"""Figures + ground truth for the interactive point-picking tests.

Each case pairs an interactive figure with a list of targets. A target says
"a click at this SVG pixel must produce a marker with these values".

The click pixel is computed with the *renderer's* own transform -- built here
exactly as :func:`simpleplot.svg._render_axes` builds it -- so it is the pixel
where the datum is actually drawn. The picking JS has to map that pixel back to
the datum through its own independent machinery (the ``simpleplot-meta``
payload plus ``toPixel``). The two paths never share code, so agreement is
evidence rather than tautology.

Where a target's values are sourced from ``pick_data`` instead of from the
source arrays (violin, eventplot offsets), the case notes it: those check index
selection and render/pick agreement, not the payload's numbers.
"""

import math

import numpy as np

import simpleplot
from simpleplot.svg import _effective_rect, _pixel_rect, pick_data
from simpleplot.transform import LinearTransform


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
    fig, ax = simpleplot.subplots()
    ax.plot(x, y)
    cases.append(Case("line", fig, _points(fig, 0, x, y, (0, 3, 7, 10))))

    # -- scatter, with an extra per-point dimension -------------------------
    sx, sy = rng.uniform(0, 10, 25), rng.uniform(0, 5, 25)
    sc = rng.uniform(0, 1, 25)
    fig, ax = simpleplot.subplots()
    ax.scatter(sx, sy, c=sc)
    cases.append(Case("scatter", fig,
                      _points(fig, 0, sx, sy, (0, 5, 17, 24),
                              lambda j: {"c": round(float(sc[j]), 6)}),
                      "the picked point must carry its own c value"))

    # -- bar ----------------------------------------------------------------
    bx = np.arange(5, dtype=float)
    bh = np.array([3.0, 1.5, 4.25, 2.0, 5.5])
    fig, ax = simpleplot.subplots()
    ax.bar(bx, bh)
    cases.append(Case("bar", fig,
                      _points(fig, 0, bx, bh, (0, 2, 4),
                              lambda j: {"value": float(bh[j])}),
                      "click each bar's top edge"))

    # -- stem ---------------------------------------------------------------
    tx = np.arange(8, dtype=float)
    ty = np.array([1.0, -2.0, 3.5, 0.5, -1.25, 2.0, 4.0, -0.75])
    fig, ax = simpleplot.subplots()
    ax.stem(tx, ty)
    cases.append(Case("stem", fig, _points(fig, 0, tx, ty, (1, 6))))

    # -- errorbar -----------------------------------------------------------
    ex = np.arange(6, dtype=float)
    ey = np.array([2.0, 3.0, 2.5, 4.0, 3.5, 5.0])
    eerr = np.array([0.2, 0.3, 0.1, 0.4, 0.25, 0.15])
    fig, ax = simpleplot.subplots()
    ax.errorbar(ex, ey, yerr=eerr)
    cases.append(Case("errorbar", fig,
                      _points(fig, 0, ex, ey, (0, 3, 5),
                              lambda j: {"yerr": float(eerr[j])})))

    # -- quiver -------------------------------------------------------------
    QX, QY = np.meshgrid(np.linspace(0, 4, 5), np.linspace(0, 3, 4))
    QU, QV = np.cos(QX), np.sin(QY)
    fig, ax = simpleplot.subplots()
    ax.quiver(QX, QY, QU, QV)
    qx, qy, qu, qv = QX.ravel(), QY.ravel(), QU.ravel(), QV.ravel()
    cases.append(Case("quiver", fig,
                      _points(fig, 0, qx, qy, (0, 7, 19),
                              lambda j: {"u": round(float(qu[j]), 6),
                                         "v": round(float(qv[j]), 6),
                                         "mag": round(float(math.hypot(qu[j], qv[j])), 6)}),
                      "arrows are picked at their tails (the grid nodes)"))

    # -- eventplot ----------------------------------------------------------
    fig, ax = simpleplot.subplots()
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
    fig, ax = simpleplot.subplots()
    ax.boxplot(bdata)
    cases.append(Case("box", fig, [
        {"px": px(fig, 0, i + 1, float(np.median(bdata[i]))),
         "expect": {"kind": "points", "axes": 0, "index": i, "x": float(i + 1),
                    "y": round(float(np.median(bdata[i])), 6)}}
        for i in (0, 1, 2)], "click each box's median line"))

    # -- violin -------------------------------------------------------------
    fig, ax = simpleplot.subplots()
    ax.violinplot([rng.normal(0, 1, 200), rng.normal(2, 1, 200)])
    vs = pick_data(fig)[0]["series"][1]
    cases.append(Case("violin", fig,
                      _points(fig, 0, vs["x"], vs["y"], (0, 20, 60)),
                      "payload-sourced click points: checks index selection"))

    # -- fill_between: snaps to the band top --------------------------------
    fx = np.linspace(0, 6, 13)
    fig, ax = simpleplot.subplots()
    ax.fill_between(fx, np.sin(fx), np.sin(fx) - 1.0)
    cases.append(Case("fill", fig,
                      _points(fig, 0, fx, np.sin(fx), (0, 6, 12),
                              lambda j: {"lower": round(float(np.sin(fx[j]) - 1.0), 6)}),
                      "picking a band reports the top edge plus 'lower'"))

    # -- pcolormesh ---------------------------------------------------------
    MZ = np.arange(20, dtype=float).reshape(4, 5) * 1.5
    fig, ax = simpleplot.subplots()
    ax.pcolormesh(np.arange(6, dtype=float), np.arange(5, dtype=float), MZ)
    cases.append(Case("pcolormesh", fig, [
        {"px": px(fig, 0, col + 0.5, row + 0.5),
         "expect": {"kind": "mesh", "axes": 0, "index": row * 5 + col,
                    "z": float(MZ[row, col]), "x": col + 0.5, "y": row + 0.5}}
        for row, col in [(0, 0), (2, 3), (3, 4), (1, 1)]],
        "click cell centers; payload row 0 is at ymin"))

    # -- imshow, origin='upper': array row 0 is drawn at the TOP -------------
    IA = np.arange(12, dtype=float).reshape(3, 4) * 2.0
    fig, ax = simpleplot.subplots()
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

    # -- pie ----------------------------------------------------------------
    pvals, plabels = [40.0, 30.0, 20.0, 10.0], ["a", "b", "c", "d"]
    fig, ax = simpleplot.subplots()
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
    fig, ax = simpleplot.subplots()
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
        fig, ax = simpleplot.subplots()
        ax.plot(ix, iy)
        if inv_x:
            ax.invert_xaxis()
        if inv_y:
            ax.invert_yaxis()
        cases.append(Case(label, fig, _points(fig, 0, ix, iy, (0, 3, 5)),
                          "picking must follow the flipped axis"))

    fig, ax = simpleplot.subplots()
    ax.plot(lx, ly)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_yaxis()
    cases.append(Case("inverted_log", fig, _points(fig, 0, lx, ly, (0, 2, 4)),
                      "inversion composed with a log scale"))

    fig, ax = simpleplot.subplots()
    ax.pcolormesh(np.arange(6, dtype=float), np.arange(5, dtype=float), MZ)
    ax.invert_yaxis()
    cases.append(Case("inverted_mesh", fig, [
        {"px": px(fig, 0, col + 0.5, row + 0.5),
         "expect": {"kind": "mesh", "axes": 0, "index": row * 5 + col,
                    "z": float(MZ[row, col]), "x": col + 0.5, "y": row + 0.5}}
        for row, col in [(0, 0), (2, 3), (3, 4)]],
        "mesh cell lookup on an inverted axis"))

    # -- two subplots: each click must resolve to its own axes --------------
    fig, axs = simpleplot.subplots(1, 2)
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
    fig, ax = simpleplot.subplots()
    ax.plot(axx, axy)
    ax.set_aspect(1.0)
    cases.append(Case("aspect", fig, _points(fig, 0, axx, axy, (0, 1, 3)),
                      "picking must use the box-adjusted rect, not the allocation"))

    return cases
