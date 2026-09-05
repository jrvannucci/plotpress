"""Shared test helpers.

Previously copy-pasted independently into test_svg_output.py,
test_axes_api_audit.py, and test_render_all.py -- factored out here so a
future change to how SVG is parsed/namespaced happens in one place instead
of three.
"""
import xml.etree.ElementTree as ET

#: The SVG namespace every rendered element lives in -- needed to look up
#: tags by name (``root.findall(".//" + SVG_NS + "path")``) since
#: ElementTree requires the namespace prefix explicitly.
SVG_NS = "{http://www.w3.org/2000/svg}"


def parse_svg(svg):
    """Parse a plotpress SVG string, also asserting it's well-formed."""
    return ET.fromstring(svg)
