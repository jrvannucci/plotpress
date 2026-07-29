"""PNG encoder: structural validity and lossless round-trip."""

import struct
import zlib

import numpy as np
import pytest

from plotpress.png import _encode_rgba, encode_png, png_data_uri


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
    """The RGBA path, exercised directly.

    encode_png now prefers indexed colour for images that fit in 256 entries,
    which a 7x5 test image does -- so go at the truecolour encoder itself,
    which is what _decode_png here understands and what >256-colour images
    still take.
    """
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, size=(7, 5, 4), dtype=np.uint8)
    decoded = _decode_png(_encode_rgba(np.ascontiguousarray(img), 7, 5))
    np.testing.assert_array_equal(decoded, img)


def test_rgb_input_gets_opaque_alpha():
    img = np.array([[[10, 20, 30]]], dtype=np.uint8)
    rgba = np.concatenate([img, np.full((1, 1, 1), 255, np.uint8)], axis=2)
    decoded = _decode_png(_encode_rgba(np.ascontiguousarray(rgba), 1, 1))
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


# -- indexed colour ---------------------------------------------------------

def _pillow_decode(data):
    """Decode with Pillow, which understands palettes and tRNS."""
    import io

    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))


def _color_type(data):
    """The IHDR colour-type byte: 3 = indexed, 6 = RGBA."""
    return data[8 + 4 + 4 + 9]


def test_colormapped_image_is_stored_indexed():
    """Mesh colours come from a 256-entry LUT, so any mesh fits a palette.

    One byte per pixel plus a small palette instead of four bytes per pixel,
    and the raster travels inside the interactive HTML -- so this lands on the
    file size a reader actually downloads.
    """
    rng = np.random.default_rng(0)
    lut = rng.integers(0, 256, (256, 3), dtype=np.uint8)
    idx = rng.integers(0, 256, (60, 80))
    rgba = np.concatenate([lut[idx], np.full((60, 80, 1), 255, np.uint8)], axis=2)

    encoded = encode_png(rgba)
    assert _color_type(encoded) == 3
    np.testing.assert_array_equal(_pillow_decode(encoded), rgba)
    assert len(encoded) < len(_encode_rgba(np.ascontiguousarray(rgba), 60, 80))


def test_indexed_preserves_transparency():
    """nan cells are transparent, so the palette needs a tRNS chunk."""
    rng = np.random.default_rng(1)
    lut = rng.integers(0, 256, (64, 3), dtype=np.uint8)
    idx = rng.integers(0, 64, (30, 40))
    rgba = np.concatenate([lut[idx], np.full((30, 40, 1), 255, np.uint8)], axis=2)
    rgba[:8, :, 3] = 0

    encoded = encode_png(rgba)
    assert _color_type(encoded) == 3
    assert b"tRNS" in encoded
    np.testing.assert_array_equal(_pillow_decode(encoded), rgba)


def test_too_many_colours_falls_back_to_rgba():
    """A Gouraud mesh interpolates between nodes, so it blows the palette."""
    rng = np.random.default_rng(2)
    rgba = rng.integers(0, 256, (40, 40, 4), dtype=np.uint8)

    encoded = encode_png(rgba)
    assert _color_type(encoded) == 6
    np.testing.assert_array_equal(_pillow_decode(encoded), rgba)
