"""Record the README's companion-slicing GIF from the real interactive page.

Matches the other readme_*.gif: 1200x454, 560 ms a frame, looping forever.
"""
import io
import os
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, ".")
import plotpress  # noqa: E402

W, H = 1200, 454
FRAME_MS = 560
OUT = "assets/readme_slice.gif"


def build_figure(path):
    """Two heatmaps whose rows differ strongly, so the profile visibly moves."""
    fig, axs = plotpress.subplots(1, 2, figsize=(12.0, 3.6))
    x = np.linspace(0, 200, 121)
    y = np.linspace(0, 60, 61)
    X, Y = np.meshgrid((x[:-1] + x[1:]) / 2, (y[:-1] + y[1:]) / 2)

    # A layered field with two buried anomalies -- a profile through it changes
    # shape a lot from row to row, which is the point of the animation.
    base = 40 + 55 * np.exp(-((Y - 42) / 16.0) ** 2)
    blob = 38 * np.exp(-(((X - 148) / 17.0) ** 2 + ((Y - 26) / 9.0) ** 2))
    dip = -22 * np.exp(-(((X - 62) / 20.0) ** 2 + ((Y - 30) / 11.0) ** 2))
    z = base + blob + dip

    for ax, (field, title) in zip(axs, [(z, "Apparent resistivity"),
                                        (np.log10(z), "log10 resistivity")]):
        m = ax.pcolormesh(x, y, field, cmap="viridis")
        ax.set_title(title)
        ax.set_xlabel("position (m)")
        ax.invert_yaxis()
        fig.colorbar(m, ax=ax)
    axs[0].set_ylabel("pseudo-depth (m)")
    fig.tight_layout()
    # range="colorbar" holds the profile's value axis at the colour scale's own
    # bounds, so the line sweeps through the field instead of the axis
    # rescaling to each row -- a 0.03-wide auto range makes a tiny ripple look
    # like a canyon.
    fig.save(path, interactive=True,
             options={"slice": {"range": "colorbar"}})


def shot(page):
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def record(url):
    frames = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(url)
        page.wait_for_timeout(400)

        def hold(n=1):
            for _ in range(n):
                frames.append(shot(page))

        hold(2)                                   # the plain heatmaps

        # Open the Slice menu and turn it on.
        page.evaluate("""() => Array.from(document.querySelectorAll(
            '.plotpress-menu-label')).find(
            b => b.textContent.trim().startsWith('Slice')).click()""")
        page.wait_for_timeout(120)
        hold(2)                                   # menu open
        page.evaluate("""() => Array.from(document.querySelectorAll(
            '.plotpress-menu-dropdown label')).find(
            l => l.textContent.includes('Enable Slice')).querySelector('input').click()""")
        page.wait_for_timeout(200)
        hold(2)                                   # strip appears, menu still open
        page.evaluate("() => document.body.click()")   # close the menu
        page.wait_for_timeout(150)
        hold(1)

        # Scrub down through the section: the profile follows the cursor line.
        rows = page.evaluate(
            "() => +document.querySelector('.plotpress-slider input[type=range]').max")
        for r in list(np.linspace(2, rows - 2, 14).astype(int)):
            page.evaluate("""(r) => document.querySelectorAll(
                '.plotpress-slider input[type=range]').forEach(s => {
                  s.value = r; s.dispatchEvent(new Event('input', {bubbles: true})); })""",
                int(r))
            page.wait_for_timeout(60)
            hold(1)
        hold(2)                                   # rest on the last slice
        browser.close()
    return frames


def main():
    os.makedirs(".scratch_gif", exist_ok=True)
    html = os.path.abspath(".scratch_gif/slice_demo.html")
    build_figure(html)
    frames = record("file:///" + html.replace("\\", "/"))
    print(f"captured {len(frames)} frames at {frames[0].size}")

    # Quantize together so the palette is stable across frames.
    pal = [f.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)
           for f in frames]
    pal[0].save(OUT, save_all=True, append_images=pal[1:],
                duration=FRAME_MS, loop=0, optimize=True, disposal=2)
    print(f"wrote {OUT}  ({os.path.getsize(OUT) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
