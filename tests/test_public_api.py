"""The top-level ``plotpress`` namespace: lazy at runtime, resolvable statically.

Every public name is loaded lazily through ``plotpress.__getattr__`` (keeps a
bare ``import plotpress`` from pulling in NumPy), and re-declared in a
``TYPE_CHECKING`` block plus a ``py.typed`` marker so a static checker
(Pylance/pyright, mypy) still resolves ``plotpress.subplots`` & co. These
tests keep the three lists -- ``_LAZY_ATTRS``, ``__all__``, and the
``TYPE_CHECKING`` imports -- from drifting apart.
"""
import ast
import pathlib
import subprocess
import sys

import plotpress

_INIT = pathlib.Path(plotpress.__file__)


def _type_checking_imports():
    """Names imported inside ``if TYPE_CHECKING:`` in plotpress/__init__.py."""
    tree = ast.parse(_INIT.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"):
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.ImportFrom):
                    names.update(a.asname or a.name for a in stmt.names)
    return names


def test_all_matches_lazy_attrs():
    assert set(plotpress.__all__) - {"__version__"} == set(plotpress._LAZY_ATTRS)


def test_type_checking_block_matches_lazy_attrs():
    # If this fails, a name was added to _LAZY_ATTRS without a matching static
    # import (Pylance would stop resolving it) or vice versa.
    assert _type_checking_imports() == set(plotpress._LAZY_ATTRS)


def test_every_public_name_actually_resolves():
    for name in plotpress.__all__:
        assert getattr(plotpress, name) is not None


def test_py_typed_marker_ships():
    assert (_INIT.parent / "py.typed").is_file()


def test_bare_import_does_not_pull_in_numpy():
    """The whole reason the namespace is lazy -- `import plotpress` on its own
    must not import NumPy (or the figure/colors stack that needs it)."""
    code = "import sys, plotpress; print('numpy' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False", out.stdout
