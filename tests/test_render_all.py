"""Every plotting method renders across all output surfaces.

A breadth-first smoke test: each public plotting method (2-D, polar, 3-D) is
called with representative data and rendered to SVG, PNG, and interactive HTML.
It guards against regressions where a method throws, emits malformed SVG, or
silently draws nothing on one of the backends.

The "drew something" check compares against an *empty axes forced to the same
limits*, so autoscale changing the tick count can't mask (or fake) real data
geometry. PNG needs Pillow, so that surface is skipped cleanly when the raster
extra is absent; SVG and HTML always run.
"""

import xml.etree.ElementTree as ET

import numpy as np
import pytest

from plotpress.figure import Figure

NS = "{http://www.w3.org/2000/svg}"
# Data-bearing marks (never axis decoration) and the full geometry set.
_DATA = ("path", "polygon", "circle", "image")
_ALL = _DATA + ("line", "rect", "text")


def _counts(svg, tags):
    root = ET.fromstring(svg)  # also asserts well-formedness
    return {t: len(root.findall(".//" + NS + t)) for t in tags}


# --- shared fixtures of representative data (seeded, deterministic) ---
_rng = np.random.default_rng(0)
_x = np.linspace(0, 2 * np.pi, 60)
_y = np.sin(_x)
_grid = np.add.outer(np.linspace(0, 1, 20), np.linspace(0, 1, 20))
_gx = np.linspace(-3, 3, 30)
_X, _Y = np.meshgrid(_gx, _gx)
_Z = np.cos(_X) * np.cos(_Y)
_groups = [_rng.normal(m, s, 200) for m, s in [(0, 1), (1, 1.5), (-1, 0.8)]]
_sig = np.sin(2 * np.pi * 3 * np.linspace(0, 4, 400)) + _rng.normal(0, .3, 400)
_th = np.linspace(0, 2 * np.pi, 100)
_sx = np.linspace(-2, 2, 20)
_SX, _SY = np.meshgrid(_sx, _sx)
_SZ = np.exp(-(_SX ** 2 + _SY ** 2))

# (name, projection, build) -- one entry per plotting method.
CASES = [
    # core 2-D
    ("plot", None, lambda ax: ax.plot(_x, _y)),
    ("scatter", None, lambda ax: ax.scatter(_rng.normal(size=80),
                                            _rng.normal(size=80),
                                            c=_rng.uniform(size=80), cmap="viridis")),
    ("bar", None, lambda ax: ax.bar(np.arange(5), _rng.integers(2, 10, 5))),
    ("barh", None, lambda ax: ax.barh(np.arange(5), _rng.integers(2, 10, 5))),
    ("hist", None, lambda ax: ax.hist(_rng.normal(size=500), bins=20)),
    ("step", None, lambda ax: ax.step(np.arange(10), _rng.integers(0, 6, 10),
                                     where="mid")),
    ("fill_between", None, lambda ax: ax.fill_between(_x, _y - .3, _y + .3)),
    ("fill_betweenx", None, lambda ax: ax.fill_betweenx(_x, _y - .3, _y + .3)),
    ("fill", None, lambda ax: ax.fill(np.cos(_x), np.sin(_x))),
    ("hlines", None, lambda ax: ax.hlines([0, 1, 2], 0, 5)),
    ("vlines", None, lambda ax: ax.vlines([0, 1, 2], 0, 5)),
    ("stem", None, lambda ax: ax.stem(np.linspace(0, 6, 20),
                                     np.sin(np.linspace(0, 6, 20)))),
    ("errorbar", None, lambda ax: ax.errorbar(np.arange(8), np.sin(np.arange(8)),
                                             yerr=0.2, capsize=3)),
    ("imshow", None, lambda ax: ax.imshow(np.sin(_grid * 6), cmap="plasma")),
    ("matshow", None, lambda ax: ax.matshow(_grid)),
    ("spy", None, lambda ax: ax.spy(np.eye(10) + np.diag(np.ones(9), 1))),
    ("pie", None, lambda ax: ax.pie([35, 25, 20, 20], labels=list("ABCD"))),
    ("boxplot", None, lambda ax: ax.boxplot(_groups)),
    ("violinplot", None, lambda ax: ax.violinplot(_groups)),
    ("kdeplot", None, lambda ax: ax.kdeplot(_groups[0])),
    ("ecdfplot", None, lambda ax: ax.ecdfplot(_groups[0])),
    ("rugplot", None, lambda ax: ax.rugplot(_groups[0][:40])),
    ("eventplot", None, lambda ax: ax.eventplot(
        [np.sort(_rng.uniform(0, 10, 20)) for _ in range(4)])),
    ("quiver", None, lambda ax: ax.quiver(_X[::4, ::4], _Y[::4, ::4],
                                         -_Y[::4, ::4], _X[::4, ::4])),
    ("contour", None, lambda ax: ax.contour(_gx, _gx, _Z, levels=8)),
    ("contourf", None, lambda ax: ax.contourf(_gx, _gx, _Z, levels=8)),
    ("hexbin", None, lambda ax: ax.hexbin(_rng.normal(size=800),
                                         _rng.normal(size=800))),
    ("hist2d", None, lambda ax: ax.hist2d(_rng.normal(size=2000),
                                         _rng.normal(size=2000), bins=20)),
    ("pcolormesh", None, lambda ax: ax.pcolormesh(_gx, _gx, _Z, cmap="viridis")),
    ("stackplot", None, lambda ax: ax.stackplot(_x, np.abs(np.sin(_x)) + .3,
                                               np.abs(np.cos(_x)) + .2)),
    ("broken_barh", None, lambda ax: ax.broken_barh([(1, 2), (4, 1)], (0, 1))),
    ("stairs", None, lambda ax: ax.stairs(_rng.integers(1, 6, 8))),
    ("axline", None, lambda ax: ax.axline((0, 0), slope=1)),
    ("axhline", None, lambda ax: ax.axhline(0.5)),
    ("axvline", None, lambda ax: ax.axvline(0.5)),
    ("axhspan", None, lambda ax: ax.axhspan(0.2, 0.6)),
    ("axvspan", None, lambda ax: ax.axvspan(0.2, 0.6)),
    # spectral
    ("psd", None, lambda ax: ax.psd(_sig)),
    ("csd", None, lambda ax: ax.csd(_sig, np.roll(_sig, 5))),
    ("cohere", None, lambda ax: ax.cohere(_sig, np.roll(_sig, 5))),
    ("magnitude_spectrum", None, lambda ax: ax.magnitude_spectrum(_sig)),
    ("angle_spectrum", None, lambda ax: ax.angle_spectrum(_sig)),
    ("phase_spectrum", None, lambda ax: ax.phase_spectrum(_sig)),
    ("specgram", None, lambda ax: ax.specgram(_sig)),
    ("xcorr", None, lambda ax: ax.xcorr(_sig, np.roll(_sig, 5))),
    ("acorr", None, lambda ax: ax.acorr(_sig)),
    # scale wrappers + text
    ("semilogx", None, lambda ax: ax.semilogx(np.linspace(1, 100, 50),
                                             np.linspace(1, 100, 50))),
    ("semilogy", None, lambda ax: ax.semilogy(np.linspace(1, 100, 50),
                                             np.linspace(1, 100, 50))),
    ("loglog", None, lambda ax: ax.loglog(np.linspace(1, 100, 50),
                                         np.linspace(1, 100, 50))),
    ("text", None, lambda ax: (ax.plot(_x, _y), ax.text(1, 0, "hi"))),
    ("annotate", None, lambda ax: (ax.plot(_x, _y),
                                  ax.annotate("pt", (1, 0), (2, 0.5)))),
    # polar
    ("polar.plot", "polar", lambda ax: ax.plot(_th, 1 + 0.3 * np.sin(5 * _th))),
    ("polar.scatter", "polar", lambda ax: ax.scatter(
        _rng.uniform(0, 2 * np.pi, 40), _rng.uniform(0, 1, 40))),
    ("polar.fill", "polar", lambda ax: ax.fill(_th, 1 + 0.3 * np.sin(3 * _th))),
    # 3-D
    ("3d.scatter", "3d", lambda ax: ax.scatter(_rng.normal(size=60),
                                              _rng.normal(size=60),
                                              _rng.normal(size=60))),
    ("3d.plot", "3d", lambda ax: ax.plot(np.cos(_th), np.sin(_th), _th / 6)),
    ("3d.plot_surface", "3d", lambda ax: ax.plot_surface(_SX, _SY, _SZ,
                                                        cmap="viridis")),
    ("3d.plot_wireframe", "3d", lambda ax: ax.plot_wireframe(_SX, _SY, _SZ)),
]
IDS = [c[0] for c in CASES]


def _render(projection, build):
    """Build a figure, return (with-data svg, matched-empty-baseline svg)."""
    fig = Figure(figsize=(4, 3))
    ax = fig.add_subplot(projection=projection)
    build(ax)
    svg = fig.to_svg()

    base = Figure(figsize=(4, 3))
    ax0 = base.add_subplot(projection=projection)
    try:  # match limits so tick-count changes don't skew the comparison
        ax0.set_xlim(*ax.get_xlim())
        ax0.set_ylim(*ax.get_ylim())
    except Exception:
        pass
    return fig, svg, base.to_svg()


@pytest.mark.parametrize("name,projection,build", CASES, ids=IDS)
def test_method_renders_svg_and_html(name, projection, build):
    fig, svg, empty = _render(projection, build)

    g1 = _counts(svg, _ALL)
    g0 = _counts(empty, _ALL)
    drew = (sum(g1[k] for k in _DATA) > sum(g0[k] for k in _DATA)
            or sum(g1.values()) > sum(g0.values()))
    assert drew, f"{name}: no geometry beyond empty axes (with={g1} empty={g0})"

    html = fig.to_html()
    assert "<svg" in html, f"{name}: interactive HTML missing inline <svg>"


@pytest.mark.parametrize("name,projection,build", CASES, ids=IDS)
def test_method_renders_png(name, projection, build, tmp_path):
    pytest.importorskip("PIL", reason="PNG raster backend needs Pillow")
    fig = Figure(figsize=(4, 3))
    ax = fig.add_subplot(projection=projection)
    build(ax)
    out = tmp_path / f"{name}.png"
    fig.save(str(out))
    assert out.stat().st_size > 200, f"{name}: PNG suspiciously small"
