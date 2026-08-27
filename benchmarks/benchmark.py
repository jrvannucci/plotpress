"""Standalone benchmark: plotpress vs matplotlib/xy (static SVG) and vs
plotly (interactive HTML) -- plot construction + serialization.

Run: python benchmarks/benchmark.py [--repeat N]
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running directly (`python benchmarks/benchmark.py`) as well as `-m`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks import scenarios  # noqa: E402


def _fmt_kib(kib: float) -> str:
    return f"{kib / 1024:.1f}MiB" if kib >= 1024 else f"{kib:.0f}KiB"


def _run(title, scenario_dict, libs, args):
    """Time + size ``libs`` (name, present, key) across every scenario in
    ``scenario_dict`` and print a table; returns the set of absent libs."""
    present = [(name, key) for name, ok, key in libs if ok]
    absent = [name for name, ok, _ in libs if not ok]
    order = ["plotpress"] + [n for n, _ in present if n != "plotpress"]

    print(f"\n{title} -- time: best of {args.repeat} runs; size: one sample "
          "(deterministic input data)\n")
    header = "{:22}".format("scenario") + "".join(f"{lib:>18}" for lib in order)
    print(header)
    print("-" * len(header))

    for name, builders in scenario_dict.items():
        cells = {}
        for lib, key in present:
            if key in builders:
                secs, kib = scenarios.timeit_and_size(builders[key], repeat=args.repeat)
                cells[lib] = f"{secs * 1e3:.1f}ms/{_fmt_kib(kib)}"
        row = "{:22}".format(name)
        row += "".join(f"{cells.get(lib, '--'):>18}" for lib in order)
        print(row)

    return absent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()

    svg_libs = [("plotpress", True, "plotpress"),
                ("matplotlib", scenarios.has_matplotlib(), "mpl"),
                ("xy", scenarios.has_xy(), "xy")]
    absent = _run("Static SVG output (plotpress vs matplotlib vs xy)",
                 scenarios.SCENARIOS, svg_libs, args)

    # plotly has no native static-image path (fig.to_image() always shells
    # out to a real browser via kaleido); it's compared on the interactive
    # HTML it *does* produce natively instead -- see scenarios.py.
    html_libs = [("plotpress", True, "plotpress"),
                ("plotly", scenarios.has_plotly(), "plotly")]
    absent += _run("Interactive HTML output (plotpress vs plotly)",
                   scenarios.HTML_SCENARIOS, html_libs, args)

    if absent:
        installable = [a for a in absent if a != "xy"]
        print(f"\nNot installed, skipped: {', '.join(absent)}")
        if installable:
            print(f"  {', '.join(installable)}: pip install plotpress[bench]")
        if "xy" in absent:
            print("  xy: ships per-platform wheels, simply absent on some machines")


if __name__ == "__main__":
    main()
