"""
Slice on a thousand meshes
============================

The interactive **Slice** tool stays responsive at the size this gallery is about:
1000 heatmaps on one figure (a 40 x 25 grid), each with its own profile strip and
all driven by one shared slider. The page below opens as its own tab because 1000
panels are too many to embed at a fixed size.

Measured in headless Chromium on the machine that built these docs, with Link all
on, a slider step redraws all 1000 strips in about 0.1 s; enabling the tool, or
switching the strip to the "profile replaces heatmap" view or to a Y slice, takes
under a second. Choosing a few axes of the thousand
(**Axes to slice** > *Selected axes*) costs tens of milliseconds per step. What
made this possible was avoiding the two things that scale badly on a page this
large -- measuring the layout between every write to the DOM, and scanning the
whole document once per axes.

Each panel is a different plane wave plus a bump, so profiles differ from one panel
to the next. Try the slider, its play button, the Slice menu's views, and
**Selected axes**.
"""
import numpy as np
import plotpress

ROWS, COLS = 40, 25
x, y = np.linspace(0, 10, 25), np.linspace(0, 8, 21)
X, Y = np.meshgrid((x[:-1] + x[1:]) / 2, (y[:-1] + y[1:]) / 2)
rng = np.random.default_rng(7)

fig, axs = plotpress.subplots(ROWS, COLS, figsize=(COLS * 1.1, ROWS * 0.9))
for i, ax in enumerate(np.ravel(axs)):
    kx, ky = 0.3 + 0.9 * (i % COLS) / COLS, 0.3 + 0.9 * (i // COLS) / ROWS
    z = (np.sin(kx * X * 2) * np.cos(ky * Y * 2)
         + np.exp(-((X - 5) ** 2 + (Y - 4) ** 2) / (1 + i % 7))
         + 0.05 * rng.normal(size=X.shape))
    ax.pcolormesh(x, y, z, cmap="viridis", vmin=-1.5, vmax=2)
    ax.set_xticks([])
    ax.set_yticks([])
fig.tight_layout()

_gallery_interactive_options = {"slice": {"enabled": True, "link_all": True}}
