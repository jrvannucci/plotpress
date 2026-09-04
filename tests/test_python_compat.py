"""Guards against real regressions in CI's oldest supported Python version.

CI tests 3.9-3.14 (see pyproject.toml's ``requires-python``), but this repo
is developed against whatever's newest locally -- so a construct only the
newer grammar allows can land, pass every local check, and only fail once it
reaches the older interpreters in CI. That happened for real: a nested
f-string in svg.py's multiline-text renderer put a backslash inside an
f-string expression's ``{...}``, which PEP 701 only legalized in 3.12 --
3.9/3.10/3.11 raised ``SyntaxError: f-string expression part cannot include
a backslash`` on import, failing every test in those three CI jobs.

A real Python 3.9 interpreter isn't available in this dev environment to
enforce the old grammar directly, so this pins the specific pattern that bit
us with a source scan, and separately confirms the fixed code still renders
correctly.
"""
import re
from pathlib import Path

import plotpress

_PACKAGE_DIR = Path(plotpress.__file__).parent

# A backslash appearing after an f-string's opening brace on the same
# physical line -- the exact shape of the pattern that broke 3.9-3.11.
# Heuristic (doesn't parse f-string grammar precisely), but it's what
# actually caught the real regression and every plotpress f-string is
# single-line by convention.
_BACKSLASH_IN_FSTRING_BRACE = re.compile(r'f["\'].*\{[^}]*\\')


def test_no_backslash_inside_an_fstring_expression():
    """Pins the exact pattern that broke Tests (py3.9/3.10/3.11) in CI --
    see plotpress/svg.py's git history for the real incident."""
    offenders = []
    for path in _PACKAGE_DIR.rglob("*.py"):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if _BACKSLASH_IN_FSTRING_BRACE.search(line):
                offenders.append(f"{path.relative_to(_PACKAGE_DIR.parent)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "f-string expression part contains a backslash -- needs Python "
        "3.12+ (PEP 701); this project supports 3.9+ (pyproject.toml's "
        "requires-python). Move the nested string literal to a plain "
        "variable before the f-string instead:\n" + "\n".join(offenders)
    )


def test_multiline_text_still_renders_correct_tspan_dy():
    """Behavioral check for the code the above regression touched: each
    line after the first gets its own dy step, the first gets none."""
    fig, ax = plotpress.subplots()
    ax.text(0.5, 0.5, "one\ntwo\nthree")
    svg = fig.to_svg()
    tspans = re.findall(r"<tspan[^>]*>", svg)
    assert len(tspans) == 3
    assert "dy=" not in tspans[0]
    assert 'dy="' in tspans[1] and 'dy="' in tspans[2]
