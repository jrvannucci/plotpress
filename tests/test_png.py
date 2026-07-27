"""PNG encoder: structural validity and lossless round-trip."""

import struct
import zlib

import numpy as np

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
