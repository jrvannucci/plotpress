"""Record the README's "at scale" GIF from the real interactive page.

The figure is docs/figure_layout/grouping/plot_13_full_scale_demo.py -- 500
pcolormesh panels in 250 groups, each with its own colorbar. The recording
zooms from the whole grid into a handful of panels, pans, pins a value with
Point Picking, then picks *one* of those 500 axes to slice and reads its
profile in a companion strip.

Matches the existing readme_scale_demo.gif: 600x504, 360 ms a frame, looping.
"""
import io
import os
import runpy
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, ".")

W, H = 600, 504
FRAME_MS = 360
OUT = "assets/readme_scale_demo.gif"
DEMO = "docs/figure_layout/grouping/plot_13_full_scale_demo.py"


def build_figure(path):
    """Run the gallery example itself, so the GIF shows the real figure."""
    ns = runpy.run_path(DEMO)
    fig = ns["fig"]
    fig.save(path, interactive=True, options=["slice"])
    return fig


def shot(page):
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def panels_in_view(page):
    """Axes fully inside the viewport right now, widest first.

    Colorbars are axes too, so the caller wants the wide ones -- a panel, not
    the narrow strip beside it.
    """
    return page.evaluate(r"""() => {
      const svg = document.getElementById('plotpress-svg');
      const c = svg.getScreenCTM(), out = [];
      document.querySelectorAll('clipPath').forEach(cp => {
        const m = /^clip(\d+)$/.exec(cp.id);
        if (!m) return;
        const r = cp.firstChild;
        const x = +r.getAttribute('x'), y = +r.getAttribute('y');
        const w = +r.getAttribute('width'), h = +r.getAttribute('height');
        const L = x * c.a + c.e, T = y * c.d + c.f, W = w * c.a, H = h * c.d;
        if (L > 6 && T > 46 && L + W < innerWidth - 6 && T + H < innerHeight - 10)
          out.push({i: +m[1], left: L, top: T, w: W, h: H,
                    cx: L + W / 2, cy: T + H / 2});
      });
      return out.sort((a, b) => b.w - a.w); }""")


def axes_click_point(page, index):
    """A clickable spot inside axes `index`, measured now.

    Two things make a cached centre wrong. Docking a slider under every one of
    500 axes changes the page's own layout, so screen coordinates move; and the
    click handler ignores anything landing on a pin, whose label box is offset
    from its dot and can easily cover the middle of a small panel. So this
    re-measures, then walks a few spots until one is not over a pin.
    """
    return page.evaluate(r"""(i) => {
      const svg = document.getElementById('plotpress-svg');
      const c = svg.getScreenCTM();
      const r = document.querySelector('#clip' + i + ' rect');
      if (!r) return null;
      const x = +r.getAttribute('x'), y = +r.getAttribute('y');
      const w = +r.getAttribute('width'), h = +r.getAttribute('height');
      const L = x * c.a + c.e, T = y * c.d + c.f, W = w * c.a, H = h * c.d;
      if (L < 0 || T < 44 || L + W > innerWidth || T + H > innerHeight) return null;
      const spots = [[0.80, 0.22], [0.22, 0.22], [0.80, 0.80],
                     [0.50, 0.50], [0.22, 0.80]];
      for (const [fx, fy] of spots) {
        const px = L + W * fx, py = T + H * fy;
        const el = document.elementFromPoint(px, py);
        if (el && !el.closest('.plotpress-pin')) return {cx: px, cy: py};
      }
      return null; }""", index)


def pin_label(page):
    """The text of the first Point Picking pin, or None if nothing is pinned."""
    return page.evaluate("""() => { const p = document.querySelector(
        '.plotpress-pin:not(.plotpress-snapped)');
        return p ? p.textContent.trim() : null; }""")


def click_toolbar(page, label):
    page.evaluate("""(l) => { const b = Array.from(
        document.querySelectorAll('.plotpress-menubar button')).find(
        b => b.textContent.trim() === l);
        if (!b) throw new Error('no toolbar button ' + l); b.click(); }""", label)


def open_menu(page, label):
    page.evaluate("""(l) => Array.from(document.querySelectorAll(
        '.plotpress-menu-label')).find(
        b => b.textContent.trim().startsWith(l)).click()""", label)


def menu_item(page, text):
    page.evaluate("""(t) => { const b = Array.from(document.querySelectorAll(
        '.plotpress-menu-dropdown button')).find(b => b.textContent.includes(t));
        if (!b) throw new Error('no menu item ' + t); b.click(); }""", text)


def menu_radio(page, group, text):
    page.evaluate("""(a) => Array.from(document.querySelectorAll(
        'input[name="plotpress-slice-' + a[0] + '"]')).find(
        r => r.parentNode.textContent.includes(a[1])).click()""", [group, text])


def menu_checkbox(page, text):
    page.evaluate("""(t) => Array.from(document.querySelectorAll(
        '.plotpress-menu-dropdown label')).find(
        l => l.textContent.includes(t)).querySelector('input').click()""", text)


def record(url):
    frames = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(url)
        page.wait_for_timeout(900)

        def hold(n=1, wait=0):
            if wait:
                page.wait_for_timeout(wait)
            for _ in range(n):
                frames.append(shot(page))

        # --- the whole 500-panel grid -------------------------------------
        click_toolbar(page, "Fit Width")
        hold(2, 450)

        # --- zoom and pan, briskly ----------------------------------------
        # Every frame costs the same 360 ms on screen, so the getting-there
        # part is captured sparsely: the wheel still turns twelve steps, but
        # only every fourth one is photographed. Otherwise the opening runs
        # twice as long as any other GIF in the README before anything is
        # actually demonstrated.
        click_toolbar(page, "Pan/Zoom")
        page.mouse.move(W * 0.44, H * 0.46)
        for step in range(7):
            page.mouse.wheel(0, -260)
            page.wait_for_timeout(55)
            if step % 3 == 2:
                hold(1)

        page.mouse.move(W * 0.62, H * 0.58)
        page.mouse.down()
        for t in (0.5, 1.0):
            page.mouse.move(W * (0.62 - 0.20 * t), H * (0.58 - 0.13 * t))
            hold(1, 55)
        page.mouse.up()

        for step in range(5):
            page.mouse.move(W * 0.46, H * 0.48)
            page.mouse.wheel(0, -260)
            page.wait_for_timeout(55)
            if step % 2 == 1:
                hold(1)
        hold(1, 220)

        panels = panels_in_view(page)
        if not panels:
            raise SystemExit("no panel fully in view after the zoom/pan")
        target = panels[0]
        print(f"  working panel: axes {target['i']} at {target['w']:.0f}px wide")

        # --- pick a value, and let the pin sit long enough to read ---------
        click_toolbar(page, "Point Picking")
        page.mouse.click(target["left"] + target["w"] * 0.30,
                         target["top"] + target["h"] * 0.62)
        hold(4, 260)                       # <- the pin itself
        label = pin_label(page)
        print(f"  picked: {label!r}")
        if not label:
            raise SystemExit("the pick landed nothing -- the GIF would lie")

        # --- move it: arrow keys walk the pin cell by cell -----------------
        for _ in range(5):
            page.keyboard.press("ArrowRight")
            hold(1, 110)
        for _ in range(3):
            page.keyboard.press("ArrowUp")
            hold(1, 110)
        moved = pin_label(page)
        print(f"  stepped to: {moved!r}")
        if moved == label:
            raise SystemExit("arrow keys did not move the pin")
        hold(2, 200)

        # --- turn Slice on, then narrow it to this one axes ----------------
        # The scope radios stay disabled until Slice is enabled, so this order
        # is forced -- and it reads better anyway: every mesh slices, then all
        # but the chosen one drops away.
        open_menu(page, "Slice")
        hold(1, 180)
        menu_checkbox(page, "Enable Slice")
        hold(2, 700)
        menu_radio(page, "scope", "Selected axes")
        hold(2, 420)                       # strips gone, candidates dashed
        here = axes_click_point(page, target["i"])
        if not here:
            raise SystemExit(f"no clickable spot left in axes {target['i']}")
        page.mouse.click(here["cx"], here["cy"])
        hold(3, 420)                       # only the chosen axes carries a strip

        n = page.evaluate("() => document.querySelectorAll("
                          "'.plotpress-slice-companion').length")
        print(f"  companion strips after choosing: {n} (expect 1)")
        if n != 1:
            raise SystemExit(f"chose {n} axes, not 1 -- the click missed")

        # --- project the pin onto the profile ------------------------------
        open_menu(page, "Slice")
        hold(1, 180)
        menu_checkbox(page, "Snap pins to slice")
        hold(1, 150)
        page.evaluate("() => document.body.click()")     # get the menu out of the way
        hold(3, 450)                       # the mirror, sharing the pin's colour
        mirrors = page.evaluate(
            "() => document.querySelectorAll('.plotpress-snapped').length")
        print(f"  mirrored pins on the profile: {mirrors} (expect 1)")
        if not mirrors:
            raise SystemExit("the pin was not projected onto the slice")

        # --- scrub: the slice moves, the mirror rides along ----------------
        rows = page.evaluate(
            "() => +document.querySelector('.plotpress-slider input[type=range]').max")
        for r in np.linspace(1, rows - 1, 7).astype(int):
            page.evaluate("""(r) => { const s = document.querySelector(
                '.plotpress-slider input[type=range]');
                s.value = r; s.dispatchEvent(new Event('input', {bubbles: true})); }""",
                int(r))
            hold(1, 85)
        hold(3, 200)
        browser.close()
    return frames


def main():
    os.makedirs(".scratch_gif", exist_ok=True)
    html = os.path.abspath(".scratch_gif/scale_demo.html")
    build_figure(html)
    frames = record("file:///" + html.replace("\\", "/"))
    print(f"captured {len(frames)} frames at {frames[0].size}")
    pal = [f.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)
           for f in frames]
    pal[0].save(OUT, save_all=True, append_images=pal[1:],
                duration=FRAME_MS, loop=0, optimize=True, disposal=2)
    print(f"wrote {OUT}  ({os.path.getsize(OUT) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
