"""Standalone benchmark: plotpress vs matplotlib, plot construction + SVG output.

Run: python benchmarks/benchmark.py [--repeat N]
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running directly (`python benchmarks/benchmark.py`) as well as `-m`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks import scenarios  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()

    have_mpl = scenarios.has_matplotlib()
    print(f"plotpress vs matplotlib -- best of {args.repeat} runs (lower is better)\n")
    header = f"{'scenario':22} {'plotpress (ms)':>12} {'matplotlib (ms)':>16} {'speedup':>9}"
    print(header)
    print("-" * len(header))

    for name, builders in scenarios.SCENARIOS.items():
        et = scenarios.timeit(builders["plotpress"], repeat=args.repeat) * 1e3
        if have_mpl:
            mt = scenarios.timeit(builders["mpl"], repeat=args.repeat) * 1e3
            speed = f"{mt / et:5.1f}x"
            print(f"{name:22} {et:12.1f} {mt:16.1f} {speed:>9}")
        else:
            print(f"{name:22} {et:12.1f} {'(n/a)':>16} {'-':>9}")

    if not have_mpl:
        print("\n(matplotlib not installed -- install with: pip install plotpress[bench])")


if __name__ == "__main__":
    main()
