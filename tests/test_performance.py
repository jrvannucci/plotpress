"""Performance tests.

Two kinds:
* Regression guards -- simpleplot must render each scenario under a generous wall
  time, so a future change that tanks performance fails CI.
* Comparative claims -- when matplotlib is installed, simpleplot must be faster
  (that is the whole point of the library). These skip if matplotlib is absent.

Thresholds are deliberately loose to stay stable across machines/CI; the
standalone ``benchmarks/benchmark.py`` is for precise numbers.
"""

import pytest

from benchmarks import scenarios

pytestmark = pytest.mark.perf  # slow; deselect with: pytest -m "not perf"

# Generous upper bounds (seconds) -- guards against pathological regressions.
_MAX_SECONDS = {
    "line_100k_points": 1.5,
    "scatter_5k_points": 1.0,
    "pcolormesh_300x300": 1.5,
    "many_axes_8x8_grid": 2.5,
}


@pytest.mark.parametrize("name", list(scenarios.SCENARIOS))
def test_simpleplot_render_under_threshold(name):
    t = scenarios.timeit(scenarios.SCENARIOS[name]["simpleplot"], repeat=3)
    assert t < _MAX_SECONDS[name], f"{name} took {t:.3f}s (limit {_MAX_SECONDS[name]}s)"


@pytest.mark.skipif(not scenarios.has_matplotlib(), reason="matplotlib not installed")
@pytest.mark.parametrize("name", ["many_axes_8x8_grid", "line_100k_points"])
def test_simpleplot_faster_than_matplotlib(name):
    # For figures with many axes, avoiding matplotlib's per-Artist Python
    # overhead makes simpleplot faster end-to-end. The single huge polyline is
    # also a win thanks to min/max path decimation (see
    # simpleplot.primitives._decimate_minmax) -- all in pure Python.
    et = scenarios.timeit(scenarios.SCENARIOS[name]["simpleplot"], repeat=3)
    mt = scenarios.timeit(scenarios.SCENARIOS[name]["mpl"], repeat=3)
    assert et < mt, f"{name}: simpleplot {et:.3f}s not faster than matplotlib {mt:.3f}s"


@pytest.mark.skipif(not scenarios.has_matplotlib(), reason="matplotlib not installed")
def test_report_speedups(capsys):
    """Print a speedup summary (visible with ``pytest -s``)."""
    with capsys.disabled():
        print()
        for name, b in scenarios.SCENARIOS.items():
            et = scenarios.timeit(b["simpleplot"], repeat=3)
            mt = scenarios.timeit(b["mpl"], repeat=3)
            print(f"  {name:22} simpleplot {et*1e3:7.1f}ms  mpl {mt*1e3:7.1f}ms  "
                  f"({mt/et:.1f}x faster)")
