"""
Combining figures into a Report
================================

``Report`` bundles several already-built figures into one self-contained HTML
file, each with its own title/details annotation and its own independent
toolbar, pan/zoom, and point-picking -- because every figure renders inside
its own ``<iframe>`` rather than being spliced directly into the page (see
``plotpress.Report``'s docstring for why: an interactive figure's JS assumes
it owns the page). Handy for a write-up covering several figures at once --
one file to open, one file to send.
"""
import os
import tempfile

import numpy as np
import plotpress

x = np.linspace(0, 10, 200)
rng = np.random.default_rng(4)

fig_a, ax_a = plotpress.subplots()
ax_a.plot(x, np.sin(x), color="#1f77b4")
ax_a.set_title("batch A")

fig_b, ax_b = plotpress.subplots()
ax_b.plot(x, np.sin(x) + 0.3 * rng.standard_normal(x.size), color="#d62728")
ax_b.set_title("batch B")

report = plotpress.Report(title="Weekly QA sweep",
                          description="Two sensor batches, one figure each.")
report.add(fig_a, title="Batch A", details="Baseline run, no anomalies.")
report.add(fig_b, title="Batch B", details="Elevated noise floor after 14:00.")
path = os.path.join(tempfile.gettempdir(), "plotpress_gallery_report.html")
report.save(path)
