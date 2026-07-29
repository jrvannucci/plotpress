"""PNG encoder: structural validity and lossless round-trip."""

import struct
import zlib

import numpy as np
import pytest

from plotpress.png import encode_png, png_data_uri


def _decode_png(data):
    """Minimal decoder for our own output (8-bit RGBA, filter type 0)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = None
    idat = b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        assert crc == (zlib.crc32(tag + chunk) & 0xFFFFFFFF), "bad CRC"
        if tag == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
            assert bit_depth == 8 and color_type == 6
        elif tag == b"IDAT":
            idat += chunk
        pos += 12 + length

    raw = zlib.decompress(idat)
    stride = width * 4
    out = np.empty((height, width, 4), np.uint8)
    for r in range(height):
        row = raw[r * (stride + 1):(r + 1) * (stride + 1)]
        assert row[0] == 0  # filter: none
        out[r] = np.frombuffer(row[1:], np.uint8).reshape(width, 4)
    return out


def test_roundtrip_rgba():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(7, 5, 4), dtype=np.uint8)
    decoded = _decode_png(encode_png(img))
    np.testing.assert_array_equal(decoded, img)


def test_rgb_input_gets_opaque_alpha():
    img = np.array([[[10, 20, 30]]], dtype=np.uint8)
    decoded = _decode_png(encode_png(img))
    assert decoded.shape == (1, 1, 4)
    assert decoded[0, 0, 3] == 255
    np.testing.assert_array_equal(decoded[0, 0, :3], [10, 20, 30])


def test_data_uri_prefix():
    img = np.zeros((2, 2, 4), np.uint8)
    uri = png_data_uri(img)
    assert uri.startswith("data:image/png;base64,")


def test_multiline_title_does_not_break_png_export():
    """A newline in a *title* used to raise ValueError out of Pillow and abort
    the whole PNG export, while every other label merely broke the line -- the
    title is the only one drawn with a bottom anchor, which Pillow refuses for
    multiline text. Text stays single-line by design (see the limitations docs),
    but a stray newline must degrade, not crash."""
    import plotpress
    from plotpress import raster

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.set_title("first line\nsecond line")
    assert raster.figure_to_image(fig, scale=1) is not None


def test_multiline_labels_survive_png_export():
    """The other label slots already coped; keep them that way."""
    import plotpress
    from plotpress import raster

    fig, ax = plotpress.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.set_xlabel("x\nunits")
    ax.set_ylabel("y\nunits")
    ax.text(0.5, 0.5, "a\nb")
    assert raster.figure_to_image(fig, scale=1) is not None


def test_png_clips_artists_to_the_axes():
    """The raster backend must clip like the SVG backend's <clipPath>.

    Without it the two disagree the moment data falls outside the limits, and
    the PNG paints it across the rest of the figure -- over neighbouring
    subplots, the axis labels and the legend.
    """
    pytest.importorskip("PIL")

    import plotpress
    from plotpress.raster import figure_to_image

    fig, ax = plotpress.subplots(figsize=(4, 3))
    x = np.linspace(0, 10, 300)
    ax.plot(x, np.sin(x) * 5.0)          # five times taller than the view
    ax.set_ylim(-1, 1)

    im = np.array(figure_to_image(fig, scale=1).convert("RGB"))
    series = np.abs(im - np.array([31, 119, 180])).max(axis=2) < 60
    rows = np.nonzero(series.any(axis=1))[0]
    assert rows.size, "series not drawn at all"
    # Nothing may reach the top or bottom edge of the canvas.
    assert rows.min() > 2 and rows.max() < im.shape[0] - 3
