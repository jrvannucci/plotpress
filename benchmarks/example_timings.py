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
# The plot-type reference itself now lives one level down, split by chart
# family (pairwise data, distributions, gridded data, multi-axes layout,
# animation) rather than sitting flat in EX_DIR. Its other subsections
# (axes_features, polar, 3-D, ...) are deliberately left out -- they would
# treble the runtime without adding a distinct shape of figure -- while
# "scale" holds the stress cases the table exists for.
EX_SUBDIRS = ["pairwise", "distributions", "gridded_data", "multi_axes", "animation"]
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


def _gallery_ref(gallery, filename):
    """The sphinx-gallery cross-reference target for one example page.

    sphinx-gallery labels every generated page ``sphx_glr_<gallery_dir>_<file>``,
    so the timings table can link each row straight at the figure it measured
    instead of naming a file the reader then has to go and find.
    """
    return f"sphx_glr_auto_{gallery}_{filename}"


def measure():
    rows = []
    def _examples(directory, label, gallery):
        # ``gallery`` is the sphinx-gallery output dir this example lands in,
        # which is what its cross-reference target is built from -- see
        # _gallery_ref below.
        return sorted((label + f, os.path.join(directory, f), gallery)
                      for f in os.listdir(directory)
                      if f.startswith("plot_") and f.endswith(".py"))

    names = []
    for sub in EX_SUBDIRS:
        names += _examples(os.path.join(EX_DIR, sub), f"{sub}/", f"examples_{sub}")
    names += _examples(SCALE_DIR, "scale/", "scale")

    for name, path, gallery in names:
        fig = _figure_from(path)
        # Count real (non-colorbar) axes.
        n_axes = sum(0 if getattr(a, "_is_colorbar", False) else 1 for a in fig.axes)

        svg_s, svg = _best(fig.to_svg)
        html_s, html = _best(lambda: fig.to_html(interactive=True))
        # binary_pick_data=True is the default measured just above; time the
        # opt-out too, so the docs can show the tradeoff on real figures
        # rather than only the synthetic payload the feature was prototyped
        # against.
        json_s, json_html = _best(
            lambda: fig.to_html(interactive=True, binary_pick_data=False))

        rows.append({
            "name": name[:-3],                     # strip .py
            "ref": _gallery_ref(gallery, os.path.basename(path)),
            "axes": n_axes,
            "svg_ms": svg_s * 1e3,
            "svg_kib": _kib(svg),
            "html_ms": html_s * 1e3,
            "html_kib": _kib(html),
            "json_html_ms": json_s * 1e3,
            "json_html_kib": _kib(json_html),
        })
        print(f"{name:34s} axes={n_axes:<4d} "
              f"svg={svg_s*1e3:7.1f}ms/{_kib(svg):8.1f}KiB  "
              f"html(binary)={html_s*1e3:7.1f}ms/{_kib(html):8.1f}KiB  "
              f"html(json)={json_s*1e3:7.1f}ms/{_kib(json_html):8.1f}KiB")
    return rows


def compare(repeat=REPEAT):
    """Time (and size) the shared scenarios on every library present."""
    libs = [("plotpress", True), ("matplotlib", scenarios.has_matplotlib()),
            ("xy", scenarios.has_xy())]
    present = [name for name, ok in libs if ok]
    rows = []
    for scenario, builders in scenarios.SCENARIOS.items():
        row = {"scenario": scenario}
        for name, key in (("plotpress", "plotpress"), ("matplotlib", "mpl"), ("xy", "xy")):
            if name in present and key in builders:
                ms, kib = scenarios.timeit_and_size(builders[key], repeat=repeat)
                row[name], row[f"{name}_kib"] = ms * 1e3, kib
        rows.append(row)
        print("  " + scenario.ljust(22)
              + "  ".join(f"{k} {row[k]:7.1f}ms/{_fmt_kib(row[k + '_kib'])}"
                         for k in present if k in row))
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
        f"   :widths: 24 {' '.join(['19'] * len(present))}",
        "",
        "   * - Scenario",
    ]
    lines += [f"     - {name} (time / size)" for name in present]
    for r in rows:
        lines.append(f"   * - ``{r['scenario']}``")
        for name in present:
            v = r.get(name)
            lines.append(f"     - {v:.1f} ms / {_fmt_kib(r[name + '_kib'])}"
                        if v is not None else "     - --")
    absent = [n for n in ("matplotlib", "xy") if n not in present]
    lines += [""]
    if absent:
        lines += [f"Not installed when this table was generated: "
                  f"{', '.join('``%s``' % a for a in absent)}.", ""]
    return lines


def _fmt_kib(kib: float) -> str:
    return f"{kib/1024:.1f} MiB" if kib >= 1024 else f"{kib:.0f} KiB"


def write_binary_comparison_rst(rows):
    """RST for binary vs. JSON pick-data payload, across every example above.

    ``fig.to_html()``'s ``binary_pick_data`` default (base64 float32 bytes
    instead of JSON number text for long arrays) against the plain-JSON
    payload it replaces, on the same figures the table above already timed --
    not just the synthetic mesh payload the feature was originally prototyped
    and chosen against.
    """
    lines = [
        "Binary vs. JSON pick data",
        "--------------------------",
        "",
        "``fig.to_html()``/``fig.save(...html)`` embed long point-pick arrays"
        " (mesh ``z`` grids, animated line frames) as base64 float32 bytes by"
        " default (``binary_pick_data=True``) rather than JSON number text."
        " Below is every example above, both ways: most are small enough that"
        " neither the array-length threshold nor the file size difference"
        " matters: the JSON version is well under a point-pick array's own"
        " threshold to begin with. It shows up once a mesh or a long series"
        " does most of the work, which is exactly the ``scale/`` rows.",
        "",
        ".. list-table::",
        "   :header-rows: 1",
        "   :widths: 30 11 11 11 11 8 8",
        "",
        "   * - Example",
        "     - Binary",
        "     - Binary size",
        "     - JSON",
        "     - JSON size",
        "     - Size",
        "     - Time",
    ]
    for r in rows:
        size_ratio = (r["json_html_kib"] / r["html_kib"]
                      if r["html_kib"] > 0 else 1.0)
        time_ratio = (r["json_html_ms"] / r["html_ms"]
                      if r["html_ms"] > 0 else 1.0)
        lines += [
            f"   * - :ref:`{r['name']} <{r['ref']}>`",
            f"     - {r['html_ms']:.1f} ms",
            f"     - {_fmt_kib(r['html_kib'])}",
            f"     - {r['json_html_ms']:.1f} ms",
            f"     - {_fmt_kib(r['json_html_kib'])}",
            f"     - {size_ratio:.2f}x",
            f"     - {time_ratio:.2f}x",
        ]
    lines += [
        "",
        "\"Size\"/\"Time\" are JSON relative to binary -- 2.0x under Size means"
        " the JSON payload is twice the binary one's size; under Time means it"
        " took twice as long to build. A ratio near 1.0x on a small figure"
        " means the encoder found nothing worth switching: every array in it"
        " was already under the threshold where a base64 wrapper costs more"
        " than it saves.",
        "",
    ]
    return lines


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
            f"   * - :ref:`{r['name']} <{r['ref']}>`",
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
        " pick_precision=...)``) to trade readout precision for a smaller file,"
        " or cap the total embedded amount directly with ``pick_max_mesh_cells``"
        " / ``pick_max_points`` -- a mesh over the cap is block-averaged down to"
        " it rather than dropped, so a click still answers with a real, if"
        " coarser, value.",
        "",
    ]
    lines += write_binary_comparison_rst(rows)
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
