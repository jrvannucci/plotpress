"""The `Report` multi-figure aggregator.
"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import time
import warnings
from numbers import Integral

import numpy as np

from ..core.artists import normalize_bbox, normalize_linestyle
from ..axes import Axes
from ..polar import PolarAxes
from ..style import Style
from ..backends.svg import figure_to_svg

from ._core import Figure
from ._html_options import _toolbar_clearance

_REPORT_MAX_WIDTH = 1600   # .plotpress-report's own max-width, below --


_REPORT_STYLE = (
    "<style>"
    "body{margin:0;padding:24px 16px;background:#f5f5f5;"
    "font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1a1a1a}"
    f".plotpress-report{{max-width:{_REPORT_MAX_WIDTH}px;margin:0 auto}}"
    ".plotpress-report>h1{font-size:24px;margin:0 0 6px}"
    ".plotpress-report-description{color:#555;margin:0 0 20px;max-width:70ch}"
    # Sits between the description and the first entry regardless of whether
    # a description was actually given -- margin-bottom on the button itself
    # (not a wrapping div) collapses to nothing extra when it directly
    # follows the description's own margin-bottom, so the gap above the
    # first entry stays the same either way.
    ".plotpress-report-toggle-all{margin:0 0 32px;padding:6px 14px;"
    "border:1px solid #ccc;border-radius:6px;background:#fff;color:#333;"
    "font:inherit;font-weight:600;cursor:pointer}"
    ".plotpress-report-toggle-all:hover{background:#f0f0f0}"
    ".plotpress-report-entry{margin-bottom:44px}"
    ".plotpress-report-toggle{display:flex;align-items:center;gap:6px;"
    "cursor:pointer;-webkit-user-select:none;user-select:none}"
    ".plotpress-report-chevron{display:inline-block;font-size:10px;color:#888;"
    "transition:transform .15s;flex:none}"
    ".plotpress-report-entry.plotpress-collapsed .plotpress-report-chevron{"
    "transform:rotate(-90deg)}"
    ".plotpress-report-heading{min-width:0}"
    ".plotpress-report-label{font-size:11px;font-weight:600;letter-spacing:.04em;"
    "text-transform:uppercase;color:#888;margin-bottom:4px}"
    ".plotpress-report-entry h2{font-size:18px;margin:0 0 4px}"
    ".plotpress-report-details{color:#555;margin:8px 0 14px;max-width:70ch;"
    "white-space:pre-wrap}"
    # Collapsed hides only the iframe -- the label/title/details above stay
    # visible, so a fully collapsed report still reads as a scannable outline
    # of what each figure is, not a bare list of "Figure N" headings.
    ".plotpress-report-entry.plotpress-collapsed iframe{display:none}"
    # width:100% (not max-width) -- this is what actually stretches each
    # figure to fill the report's own width instead of sitting at whatever
    # fixed pixel size the figure happened to be created at.
    ".plotpress-report-entry iframe{border:1px solid #ddd;border-radius:6px;"
    "background:#fff;display:block;width:100%}"
    "</style>"
)


_REPORT_SCRIPT = (
    "<script>(function(){"
    "function fit(f){"
    "var d=f.contentDocument;if(!d||!d.body||!f.dataset.loaded)return;"
    "var w=f.clientWidth;if(f.dataset.fitWidth===String(w))return;"
    "f.dataset.fitWidth=String(w);"
    "f.style.height=d.body.scrollHeight+'px';}"
    "var frames=document.querySelectorAll('.plotpress-report-entry iframe');"
    "frames.forEach(function(f){f.addEventListener('load',function(){"
    "f.dataset.loaded='1';fit(f);});});"
    "var t;window.addEventListener('resize',function(){"
    "clearTimeout(t);t=setTimeout(function(){frames.forEach(fit);},120);});"
    "function setCollapsed(entry,collapsed){"
    "entry.classList.toggle('plotpress-collapsed',collapsed);"
    "var h=entry.querySelector('.plotpress-report-toggle');"
    "if(h)h.setAttribute('aria-expanded',collapsed?'false':'true');"
    "if(!collapsed){var f=entry.querySelector('iframe');if(f){"
    "if(f.dataset.lazyDoc!==undefined){"
    "f.srcdoc=f.dataset.lazyDoc;delete f.dataset.lazyDoc;}"
    "fit(f);}}}"
    "document.querySelectorAll('.plotpress-report-toggle').forEach(function(h){"
    "h.addEventListener('click',function(){"
    "var entry=h.closest('.plotpress-report-entry');"
    "setCollapsed(entry,!entry.classList.contains('plotpress-collapsed'));});"
    "h.addEventListener('keydown',function(e){"
    "if(e.key==='Enter'||e.key===' '){e.preventDefault();h.click();}});});"
    "var allBtn=document.getElementById('plotpress-report-toggle-all');"
    "if(allBtn)allBtn.addEventListener('click',function(){"
    "var entries=document.querySelectorAll('.plotpress-report-entry');"
    "var anyExpanded=Array.prototype.some.call(entries,function(e){"
    "return!e.classList.contains('plotpress-collapsed');});"
    "entries.forEach(function(e){setCollapsed(e,anyExpanded);});"
    "allBtn.textContent=anyExpanded?'Expand All':'Collapse All';});"
    "})();</script>"
)


class Report:
    """An ordered collection of figures combined into one self-contained HTML file.

    Each figure keeps its own independent interactivity -- its own toolbar,
    pan/zoom, point-picking, annotations -- because it is embedded in its own
    ``<iframe>`` rather than spliced directly into the page. An interactive
    figure's JS (:mod:`plotpress._interactive`) assumes it owns the page: fixed
    element ids (``plotpress-svg``, ``plotpress-meta``, ...) and a
    document-level toolbar, so several figures sharing one page directly would
    collide -- the same reason the docs gallery embeds every live figure this
    way (see ``docs/conf.py``'s ``_interactive_embed``). An iframe gives each
    figure its own document instead, at no real cost to "one file": each
    figure's already-self-contained HTML (see :meth:`Figure.to_html`) is
    inlined via the iframe's ``srcdoc`` attribute rather than referenced as a
    separate file, so the report is still a single, self-contained HTML
    document with no external requests.

    Add figures with :meth:`add`, in the order they should appear, then write
    the combined file with :meth:`save`::

        report = plotpress.Report(title="Weekly QA sweep",
                                  description="Four sensor batches, one figure each.")
        report.add(fig_a, title="Batch A", details="Baseline run, no anomalies.")
        report.add(fig_b, title="Batch B", details="Elevated noise floor after 14:00.")
        report.save("qa_sweep.html")
    """

    def __init__(self, title: str = None, description: str = None):
        self.title = title
        self.description = description
        self._entries = []   # [(figure, title, details)], in add() order

    def add(self, figure: "Figure", title: str = None, details: str = None) -> "Report":
        """Append ``figure`` to the report; returns ``self`` so calls can chain.

        ``title`` (a short heading) and ``details`` (a longer description) are
        optional per-figure annotations rendered above the embedded figure.
        Figures appear in the HTML in the order they were added -- there is no
        separate ordering mechanism to keep in sync.
        """
        if not isinstance(figure, Figure):
            raise TypeError("Report.add() expects a Figure, got %r" % (figure,))
        self._entries.append((figure, title, details))
        return self

    def save(self, path: str, interactive: bool = True,
             pick_precision: int = 6, pick_max_mesh_cells: int = 250000,
             pick_max_points: int = 20000, binary_pick_data: bool = True,
             collapsed: bool = False, options=None) -> str:
        """Write every added figure, in order, to one self-contained HTML file.

        ``interactive`` and the ``pick_*``/``binary_pick_data`` arguments are
        forwarded to each figure's own :meth:`Figure.to_html` -- see there for
        what they mean. Every figure in the report shares the same settings;
        call :meth:`Figure.to_html` directly (and write the file yourself) for
        a mix of interactive and static figures on one page.

        Every entry is collapsible: a click anywhere on its "Figure N"/title
        header hides just that entry's figure, leaving its title and details
        visible -- a long report reads as a scannable outline instead of a
        wall of figures. A **Collapse All**/**Expand All** button above the
        first entry does the same for every one at once.

        ``collapsed=True`` starts every entry collapsed instead of open, and
        genuinely defers each one: rather than embed it as a live ``srcdoc``
        that just sits hidden, the escaped document is parked in a plain data
        attribute and only ever assigned to the iframe -- triggering the real
        parse/render -- the first time a reader actually expands that entry.
        A collapsed figure's own toolbar/pan-zoom/pick-data JS never runs
        until then, so a report with many (or heavy) figures opens instantly
        regardless of how many it holds, at the cost of a brief render on
        each entry's first expand instead.
        """
        if not self._entries:
            raise ValueError("Report has no figures -- call add() at least once")
        parts = [
            "<!doctype html><html><head><meta charset='utf-8'>",
            f"<title>{html.escape(self.title)}</title>" if self.title else "",
            _REPORT_STYLE,
            "</head><body><div class='plotpress-report'>",
        ]
        if self.title:
            parts.append(f"<h1>{html.escape(self.title)}</h1>")
        if self.description:
            parts.append('<p class="plotpress-report-description">'
                         f'{html.escape(self.description)}</p>')
        toggle_all_label = "Expand All" if collapsed else "Collapse All"
        parts.append(
            f'<button type="button" id="plotpress-report-toggle-all" '
            f'class="plotpress-report-toggle-all">{toggle_all_label}</button>')
        for n, (figure, title, details) in enumerate(self._entries, start=1):
            doc = figure.to_html(interactive=interactive,
                                 pick_precision=pick_precision,
                                 pick_max_mesh_cells=pick_max_mesh_cells,
                                 pick_max_points=pick_max_points,
                                 binary_pick_data=binary_pick_data,
                                 standalone=False, options=options)
            dpi = figure.style.dpi
            natural_w = figure.figsize[0] * dpi
            natural_h = figure.figsize[1] * dpi
            top_pad, bottom_pad = _toolbar_clearance(interactive, len(figure._sliders or {}))
            # A starting guess only -- the resize script (_REPORT_SCRIPT)
            # corrects this to the real rendered height right after the
            # iframe loads, once it knows how wide the reader's own browser
            # actually made it. Guessing at .plotpress-report's own max
            # rendered width (rather than the figure's own pixel size, often
            # much narrower) keeps that first correction small; toolbar/slider
            # clearance is exact, not guessed, since it's baked into the
            # embedded document's own body padding either way (Figure.to_html,
            # standalone=False) -- scrollHeight will already include it.
            guess_w = _REPORT_MAX_WIDTH - 2 * 16 - 2 * 1   # body padding, iframe border
            h = round(guess_w * natural_h / natural_w) + top_pad + bottom_pad
            iframe_title = html.escape(title) if title else "Figure %d" % n
            entry_class = "plotpress-report-entry plotpress-collapsed" if collapsed \
                else "plotpress-report-entry"
            parts.append(f'<div class="{entry_class}">')
            parts.append(
                '<div class="plotpress-report-toggle" role="button" tabindex="0" '
                f'aria-expanded="{"false" if collapsed else "true"}">'
                '<span class="plotpress-report-chevron">&#9662;</span>'
                '<div class="plotpress-report-heading">'
                f'<div class="plotpress-report-label">Figure {n}</div>')
            if title:
                parts.append(f"<h2>{html.escape(title)}</h2>")
            parts.append('</div></div>')
            if details:
                parts.append('<p class="plotpress-report-details">'
                             f'{html.escape(details)}</p>')
            if collapsed:
                # Not srcdoc=: a display:none iframe's own loading="lazy"
                # turned out not to defer anything in practice (see
                # _REPORT_SCRIPT's own comment on setCollapsed) -- real
                # engines have a viewport-*distance* heuristic to judge
                # "near enough to load", which a never-laid-out element has
                # no geometry for, so several just load it immediately
                # regardless. Parking the same escaped doc in a data
                # attribute instead means nothing is even parsed as HTML
                # until setCollapsed()'s own JS deliberately assigns it to
                # a real .srcdoc on that entry's first expand.
                parts.append(
                    f'<iframe data-lazy-doc="{html.escape(doc)}" '
                    f'height="{h}" title="{iframe_title}"></iframe>')
            else:
                parts.append(
                    f'<iframe srcdoc="{html.escape(doc)}" height="{h}" '
                    f'loading="lazy" title="{iframe_title}"></iframe>')
            parts.append("</div>")
        parts.append(_REPORT_SCRIPT)
        parts.append("</div></body></html>")
        content = "".join(parts)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path
