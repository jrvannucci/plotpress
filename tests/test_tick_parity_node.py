"""Exhaustive JS<->Python tick parity, without a browser.

``test_tick_parity_interactive.py`` proves parity through a real zoom in a
real browser, which is the honest end-to-end check but costs a page load per
case -- so it covers a handful of hand-picked ones. This covers the same
ground by brute force instead: the tick functions in ``_interactive.py`` are
pure, so they are lifted out of the ``_JS_SOURCE`` string by name, run in node
over a few thousand (range x locator x format) combinations, and compared
against what :mod:`plotpress.ticker` computes for the identical inputs.

Tick *positions* only have to agree to well below a pixel. The *labels* have
to agree exactly -- that is where a one-ulp difference becomes visible, since
a tick sitting a hair either side of a .5 boundary rounds to a different
digit. Three real divergences were found this way and are regressed here:

* ``fmtTick`` derived its decimal count from the tick step, so a fractional
  locator base relabelled 0/2.5/5/7.5/10 as 0/3/5/8/10 after the first zoom;
* JS ``toFixed`` rounds a halfway value away from zero while Python rounds
  half to even, so a +-0.5 tick read "0"/"-0" as rendered and "1"/"-1" after;
* both ``nice_ticks`` and ``multiple_ticks`` accumulated their steps by
  repeated addition, landing a tick that should be 5.5 on 5.499999999999998
  (and one that should be 0 on -3.4e-13), which the two sides then rounded
  differently.

Needs node on PATH; skipped otherwise.
"""
import io
import json
import re
import shutil
import subprocess

import numpy as np
import pytest

from plotpress.backends._interactive import _JS_SOURCE as _JS
from plotpress.style.ticker import resolve_axis_tick_labels, resolve_axis_ticks

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="needs node on PATH")

#: Module-level constants the lifted functions close over.
CONSTS = ["MS_PER_DAY", "DATE_TIERS", "DATE_UNIT_DAYS", "SI_PREFIXES"]

#: Every pure function on the tick-resolution path, in dependency order.
FUNCS = [
    "pow10", "jsNiceTicks", "pyFixed", "expFmt", "fmtTick", "fmtNum", "jsLogTicks",
    "allDistinct", "sciShared", "fmtTickSet", "axisTicks", "pickDateTier",
    "truncateDateUTC", "addDateUnitsUTC", "jsDateTicks", "pad2", "fmtDateTick",
    "jsFormatDateTicks", "jsMultipleTicks", "jsApplyLocator", "jsEngTick",
    "gcdInt", "limitDenominator", "jsPiTick", "commaFmt", "_pyStyleG",
    "jsPrintfTick", "jsApplyFormat", "jsCategoryTicks", "resolveAxisTicks",
]


def _lift(pattern, name):
    m = re.search(pattern % re.escape(name), _JS, re.S | re.M)
    assert m, (
        "could not lift %r out of _JS_SOURCE -- if the JS was restructured, "
        "update CONSTS/FUNCS here so this parity check keeps covering it" % name)
    return m.group(0)


def _harness():
    parts = [_lift(r"^  var %s = .*?;$", c) for c in CONSTS]
    parts += [_lift(r"^  function %s\(.*?^  \}", f) for f in FUNCS]
    return "\n".join(parts) + r"""
const cases = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify(cases.map(c => {
  try {
    const om = {
      xcategorical: !!c.categorical, xcategories: c.categories || null,
      xlocator: c.locator || null, xdate: !!c.is_date, xformat: c.fmt || null,
      ycategorical: false, ycategories: null, ylocator: null,
      ydate: false, yformat: null,
    };
    const r = resolveAxisTicks(om, c.lo, c.hi, c.scale || 'linear', true);
    return {ticks: Array.from(r.ticks), labels: r.labels};
  } catch (e) { return {error: String(e)}; }
})));
"""


def _cases():
    rng = np.random.default_rng(7)
    ranges = [
        (0, 1), (0, 10), (-1, 1), (-100, 100), (0, 0.001), (0, 1e6),
        (1, 1.0001), (-0.5, 0.5), (0, 3), (2.5, 7.5), (-1e5, 1e5),
        (0.1, 0.9), (1e-4, 1e-3), (123456, 123460), (-7, -3),
        (0, 2 * np.pi), (0, 1e-6), (5, 5.5), (-1e-3, 1e-3), (0, 99999),
        (-0.25, 0.25), (-2.5, 2.5), (0, 0.5), (-9.5, 9.5), (0.125, 0.875),
        (-1234.5, 1234.5), (99999, 100001), (-1e-9, 1e-9), (7, 7.25),
    ]
    for _ in range(60):                     # fixed seed: the grid is stable
        centre = rng.uniform(-1000, 1000)
        width = 10 ** rng.uniform(-4, 4)
        ranges.append((centre - width / 2, centre + width / 2))

    fmts = ["percent", "comma", "eng", "pi", "%.2f", "%d", "%.0f%%",
            "%.1f", "%.3f", "%.0f", "%g", "$%.2f", "%5.1f", "%+.1f"]
    fmts += [{"kind": k, "decimals": d}
             for k, ds in (("percent", (0, 1, 2)), ("comma", (0, 1, 2)),
                           ("eng", (0, 1, 3)))
             for d in ds]

    out = []
    for lo, hi in ranges:
        out.append({"lo": lo, "hi": hi})
        for base in (0.5, 1, 2.5, np.pi / 2, 100, 0.001):
            # Neither side caps how many multiples it enumerates (matplotlib
            # raises past MAXTICKS); a pairing that would produce millions
            # says nothing about label parity and just hangs node.
            if 0 < (hi - lo) / base <= 500:
                out.append({"lo": lo, "hi": hi,
                            "locator": {"kind": "multiple", "base": base}})
        for fmt in fmts:
            out.append({"lo": lo, "hi": hi, "fmt": fmt})
    # Log axes carry their own label path (fmtNum), so sweep them wider.
    for lo, hi in [(1, 1000), (0.001, 1), (1, 1e6), (2, 9), (1, 10), (1, 100),
                   (1e-6, 1e6), (0.5, 2), (3, 7), (1e-9, 1e-3), (2, 2000),
                   (1, 1e12), (0.001, 0.002)]:
        out.append({"lo": lo, "hi": hi, "scale": "log"})
        for fmt in ("eng", "comma", "%.1f", "percent"):
            out.append({"lo": lo, "hi": hi, "scale": "log", "fmt": fmt})
    # Date axes -- values are day numbers (see plotpress/dates.py). Spans are
    # picked to land in every tier pickDateTier chooses between.
    for start in (0, 19000, 19723.5, -3650, 40000):
        for span in (1, 2, 5, 10, 31, 90, 180, 365, 365 * 3, 365 * 12,
                     0.5, 0.05, 0.001, 1e-5):
            out.append({"lo": start, "hi": start + span, "is_date": True})
    # Categorical axes, including views panned past both ends and one that
    # falls entirely between categories.
    for n in (1, 2, 3, 7, 26):
        cats = ["c%d" % i for i in range(n)]
        for lo, hi in [(-0.5, n - 0.5), (0, n - 1), (-2, n + 2), (0.2, n - 1.2)]:
            out.append({"lo": lo, "hi": hi,
                        "categorical": True, "categories": cats})
    return out


def test_js_tick_labels_match_python_across_the_grid(tmp_path):
    cases = _cases()
    harness = tmp_path / "harness.js"
    harness.write_text(_harness(), encoding="utf-8")
    payload = tmp_path / "cases.json"
    payload.write_text(json.dumps(cases), encoding="utf-8")

    run = subprocess.run(["node", str(harness), str(payload)],
                         capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 0, "node failed:\n" + (run.stderr or "")[:2000]
    got = json.loads(run.stdout)

    problems = []
    for case, js in zip(cases, got):
        if js.get("error"):
            problems.append("%s -- JS threw %s" % (json.dumps(case), js["error"]))
            continue
        py_ticks = resolve_axis_ticks(
            case["lo"], case["hi"], scale=case.get("scale", "linear"),
            locator=case.get("locator"),
            categorical=case.get("categorical", False),
            categories=case.get("categories"),
            is_date=case.get("is_date", False))
        py_labels = list(resolve_axis_tick_labels(
            py_ticks, categorical=case.get("categorical", False),
            categories=case.get("categories"), fmt=case.get("fmt"),
            is_date=case.get("is_date", False)))
        if len(py_ticks) != len(js["ticks"]) or not np.allclose(
                np.asarray(py_ticks, dtype=float),
                np.asarray(js["ticks"], dtype=float), rtol=1e-9, atol=1e-12):
            problems.append("%s\n    positions: python=%r js=%r"
                            % (json.dumps(case), [float(v) for v in py_ticks],
                               js["ticks"]))
        elif py_labels != list(js["labels"]):
            problems.append("%s\n    labels: python=%r js=%r"
                            % (json.dumps(case), py_labels, js["labels"]))

    assert not problems, "%d of %d cases diverge:\n\n%s" % (
        len(problems), len(cases), "\n".join(problems[:15]))
