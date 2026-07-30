"""Measure SVG vs interactive-HTML output for every gallery example.

Runs each ``docs/examples/plot_*.py``, grabs the ``plotpress.Figure`` it
builds, and times serialization to static SVG and to self-contained interactive
HTML (best of N), recording the output sizes. Writes the results as an RST
table to ``docs/performance.rst`` so the docs carry an up-to-date, reproducible
timing table.

Run: python benchmarks/example_timings.py
"""

from __future__ import annotations

import os
import runpy
import sys
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import plotpress  # noqa: E402

from benchmarks import scenarios  # noqa: E402

EX_DIR = os.path.join(ROOT, "docs", "examples")
# The timings cover the plot-type reference plus the large-scale gallery, which
# now lives in its own tree. The reference's other subsections (signal, polar,
# 3-D, ...) are deliberately left out -- they would treble the runtime without
# adding a distinct shape of figure -- while "scale" holds the stress cases the
# table exists for.
SCALE_DIR = os.path.join(ROOT, "docs", "scale")
OUT_RST = os.path.join(ROOT, "docs", "performance.rst")
REPEAT = 5


def _best(fn, repeat=REPEAT):
    """Return (best_seconds, last_result) over ``repeat`` runs."""
    best = float("inf")
    result = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - t0)
    return best, result


def _figure_from(path):
    """Execute an example and return the single Figure it created."""
    ns = runpy.run_path(path)
    figs = [v for v in ns.values() if isinstance(v, plotpress.Figure)]
    if len(figs) != 1:
        raise RuntimeError(f"{os.path.basename(path)}: expected 1 Figure, got {len(figs)}")
    return figs[0]


def _kib(s: str) -> float:
    return len(s.encode("utf-8")) / 1024.0


def measure():
    rows = []
    def _examples(directory, label):
        return sorted((label + f, os.path.join(directory, f))
                      for f in os.listdir(directory)
                      if f.startswith("plot_") and f.endswith(".py"))

    names = _examples(EX_DIR, "")
    names += _examples(SCALE_DIR, "scale/")

    for name, path in names:
        fig = _figure_from(path)
        # Count real (non-colorbar) axes.
        n_axes = sum(0 if getattr(a, "_is_colorbar", False) else 1 for a in fig.axes)

        svg_s, svg = _best(fig.to_svg)
        html_s, html = _best(lambda: fig.to_html(interactive=True))

        rows.append({
            "name": name[:-3],                     # strip .py
            "axes": n_axes,
            "svg_ms": svg_s * 1e3,
            "svg_kib": _kib(svg),
            "html_ms": html_s * 1e3,
            "html_kib": _kib(html),
        })
        print(f"{name:34s} axes={n_axes:<4d} "
              f"svg={svg_s*1e3:7.1f}ms/{_kib(svg):8.1f}KiB  "
              f"html={html_s*1e3:7.1f}ms/{_kib(html):8.1f}KiB")
    return rows


def compare(repeat=REPEAT):
    """Time the shared scenarios on every library present."""
    libs = [("plotpress", True), ("matplotlib", scenarios.has_matplotlib()),
            ("xy", scenarios.has_xy())]
    present = [name for name, ok in libs if ok]
    rows = []
    for scenario, builders in scenarios.SCENARIOS.items():
        row = {"scenario": scenario}
        for name, key in (("plotpress", "plotpress"), ("matplotlib", "mpl"), ("xy", "xy")):
            if name in present and key in builders:
                row[name] = scenarios.timeit(builders[key], repeat=repeat) * 1e3
        rows.append(row)
        print("  " + scenario.ljust(22)
              + "  ".join(f"{k} {row[k]:8.1f}ms" for k in present if k in row))
    return present, rows


def write_comparison(present, rows):
    """RST for the cross-library table."""
    lines = [
        "Against other libraries",
        "-----------------------",
        "",
        "The same four figures built and serialized to SVG by each library, using"
        " its own idiomatic API and no global state on any side. matplotlib goes"
        " through the object-oriented ``FigureCanvasSVG`` rather than ``pyplot``;"
        " xy renders headlessly through ``Chart.to_svg()``. xy facets by a data"
        " column rather than by an arbitrary grid, so its 8x8 case is 64 groups of"
        " one long-form table -- the idiomatic equivalent, not a handicap.",
        "",
        "These measure **time to produce a static file**, which is the axis"
        " plotpress optimizes. It is not the axis xy optimizes: its Rust core"
        " decimates by screen resolution for *interactive* exploration of large"
        " data, and a single static render does not exercise that.",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        f"   :widths: 30 {' '.join(['16'] * len(present))}",
        "",
        "   * - Scenario",
    ]
    lines += [f"     - {name}" for name in present]
    for r in rows:
        lines.append(f"   * - ``{r['scenario']}``")
        for name in present:
            v = r.get(name)
            lines.append(f"     - {v:.1f} ms" if v is not None else "     - --")
    absent = [n for n in ("matplotlib", "xy") if n not in present]
    lines += [""]
    if absent:
        lines += [f"Not installed when this table was generated: "
                  f"{', '.join('``%s``' % a for a in absent)}.", ""]
    return lines


def _fmt_kib(kib: float) -> str:
    return f"{kib/1024:.1f} MiB" if kib >= 1024 else f"{kib:.0f} KiB"


def write_rst(rows, comparison=None):
    lines = [
        "Performance",
        "===========",
        "",
        "Every example in the plot-type :ref:`reference gallery <gallery>`"
        " serialized to static SVG and to self-contained interactive HTML, with"
        " output sizes. (The :ref:`real applications <applications>` gallery is"
        " not timed here: its figures are variations on the same shapes, and"
        " timing another hundred of them would treble the runtime without"
        " adding a row that says anything new.) Interactive HTML"
        " embeds the same SVG **plus** the per-axes data the toolbar needs for"
        " zoom / point-picking (the picked values, and mesh ``z`` grids), so it"
        " is larger and slower than SVG -- most for mesh-heavy figures.",
        "",
        f"Best of {REPEAT} runs, one machine. Regenerate with"
        " ``python benchmarks/example_timings.py``.",
        "",
    ]
    if comparison:
        lines += comparison
    lines += [
        "Per-example output",
        "------------------",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        "   :widths: 34 8 12 12 12 12",
        "",
        "   * - Example",
        "     - Axes",
        "     - SVG",
        "     - SVG size",
        "     - HTML",
        "     - HTML size",
    ]
    for r in rows:
        lines += [
            f"   * - ``{r['name']}``",
            f"     - {r['axes']}",
            f"     - {r['svg_ms']:.1f} ms",
            f"     - {_fmt_kib(r['svg_kib'])}",
            f"     - {r['html_ms']:.1f} ms",
            f"     - {_fmt_kib(r['html_kib'])}",
        ]
    lines += [
        "",
        "The ``scale/plot_01_many_axes`` row is the deliberate stress case: 500"
        " independent pcolormesh axes on one figure. Its interactive HTML is"
        " dominated by the 500 embedded mesh ``z`` grids; lower"
        " ``fig.to_html(pick_precision=...)`` (or ``fig.save(...,"
        " pick_precision=...)``) to trade readout precision for a smaller file.",
        "",
    ]
    with open(OUT_RST, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {OUT_RST}")


if __name__ == "__main__":
    warnings.simplefilter("ignore")   # ignore Pillow size warnings (not raised here)
    print("cross-library comparison:")
    present, comp_rows = compare()
    print("\nper-example output:")
    rows = measure()
    write_rst(rows, comparison=write_comparison(present, comp_rows))
