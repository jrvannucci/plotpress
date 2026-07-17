"""Measure SVG vs interactive-HTML output for every gallery example.

Runs each ``docs/examples/plot_*.py``, grabs the ``simpleplot.Figure`` it
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

import simpleplot  # noqa: E402

EX_DIR = os.path.join(ROOT, "docs", "examples")
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
    figs = [v for v in ns.values() if isinstance(v, simpleplot.Figure)]
    if len(figs) != 1:
        raise RuntimeError(f"{os.path.basename(path)}: expected 1 Figure, got {len(figs)}")
    return figs[0]


def _kib(s: str) -> float:
    return len(s.encode("utf-8")) / 1024.0


def measure():
    rows = []
    names = sorted(f for f in os.listdir(EX_DIR) if f.startswith("plot_") and f.endswith(".py"))
    for name in names:
        fig = _figure_from(os.path.join(EX_DIR, name))
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
        print(f"{name:28s} axes={n_axes:<4d} "
              f"svg={svg_s*1e3:7.1f}ms/{_kib(svg):8.1f}KiB  "
              f"html={html_s*1e3:7.1f}ms/{_kib(html):8.1f}KiB")
    return rows


def _fmt_kib(kib: float) -> str:
    return f"{kib/1024:.1f} MiB" if kib >= 1024 else f"{kib:.0f} KiB"


def write_rst(rows):
    lines = [
        "Performance",
        "===========",
        "",
        "Every :ref:`gallery example <gallery>` serialized to static SVG and to"
        " self-contained interactive HTML, with output sizes. Interactive HTML"
        " embeds the same SVG **plus** the per-axes data the toolbar needs for"
        " zoom / point-picking (the picked values, and mesh ``z`` grids), so it"
        " is larger and slower than SVG -- most for mesh-heavy figures.",
        "",
        f"Best of {REPEAT} runs, one machine. Regenerate with"
        " ``python benchmarks/example_timings.py``.",
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
        "The ``plot_23_mesh_grid`` row is the deliberate stress case: 500"
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
    rows = measure()
    write_rst(rows)
