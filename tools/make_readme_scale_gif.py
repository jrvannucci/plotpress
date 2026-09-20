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
        hold(3, 500)

        # --- zoom in on it ------------------------------------------------
        # 12 wheel steps is the useful depth here: it leaves about three whole
        # panels in view at ~160px each, wide enough for a pin label to read.
        # Much past that and no panel is fully on screen any more.
        click_toolbar(page, "Pan/Zoom")
        page.mouse.move(W * 0.44, H * 0.46)
        for _ in range(7):
            page.mouse.wheel(0, -260)
            hold(1, 90)

        # Pan here rather than at full zoom: with only about three whole panels
        # on screen at the end, any drag at that depth leaves none of them
        # fully in view for the pick below to aim at.
        page.mouse.move(W * 0.62, H * 0.58)
        page.mouse.down()
        for t in (0.34, 0.67, 1.0):
            page.mouse.move(W * (0.62 - 0.20 * t), H * (0.58 - 0.13 * t))
            hold(1, 70)
        page.mouse.up()
        hold(1, 180)

        for _ in range(5):
            page.mouse.move(W * 0.46, H * 0.48)
            page.mouse.wheel(0, -260)
            hold(1, 90)
        hold(2, 250)

        panels = panels_in_view(page)
        if not panels:
            raise SystemExit("no panel fully in view after the zoom/pan")
        target = panels[0]
        print(f"  working panel: axes {target['i']} at {target['w']:.0f}px wide")

        # --- pick a value, and let the pin sit long enough to read ---------
        click_toolbar(page, "Point Picking")
        hold(2, 150)                       # mode selected, nothing picked yet
        page.mouse.click(target["left"] + target["w"] * 0.32,
                         target["top"] + target["h"] * 0.58)
        hold(6, 260)                       # <- the pin itself
        pins = page.evaluate("() => document.querySelectorAll('.plotpress-pin').length")
        print(f"  pins on the figure: {pins} (expect 1)")
        if not pins:
            raise SystemExit("the pick landed nothing -- the GIF would lie")

        # --- turn Slice on: every mesh in view sprouts a strip -------------
        # The scope radios are deliberately disabled until Slice is enabled,
        # so this has to come first -- and it makes the narrowing below read.
        open_menu(page, "Slice")
        hold(2, 200)
        menu_checkbox(page, "Enable Slice")
        hold(3, 700)

        # --- narrow it to ONE of the 500 axes ------------------------------
        menu_radio(page, "scope", "Selected axes")   # enters choose-axes mode
        hold(3, 450)                       # strips gone, every candidate dashed
        here = axes_click_point(page, target["i"])
        if not here:
            raise SystemExit(f"no clickable spot left in axes {target['i']}")
        page.mouse.click(here["cx"], here["cy"])
        hold(4, 450)                       # only the chosen axes carries a strip

        n = page.evaluate("() => document.querySelectorAll("
                          "'.plotpress-slice-companion').length")
        print(f"  companion strips after choosing: {n} (expect 1)")
        if n != 1:
            raise SystemExit(f"chose {n} axes, not 1 -- the click missed")

        # --- scrub that one panel's slice ----------------------------------
        rows = page.evaluate(
            "() => +document.querySelector('.plotpress-slider input[type=range]').max")
        for r in np.linspace(1, rows - 1, 8).astype(int):
            page.evaluate("""(r) => { const s = document.querySelector(
                '.plotpress-slider input[type=range]');
                s.value = r; s.dispatchEvent(new Event('input', {bubbles: true})); }""",
                int(r))
            hold(1, 90)
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
