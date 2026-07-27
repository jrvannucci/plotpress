"""Minimal PNG encoder built only on the standard library (``zlib``).

Used to rasterize ``pcolormesh`` / image layers into a single ``<image>``
element embedded in the SVG as a base64 data URI. PNG's container format is
simple enough that no third-party dependency is needed; the heavy lifting is a
single vectorized ``zlib.compress`` call.
"""

from __future__ import annotations

import base64
import struct
import zlib

import numpy as np


def _chunk(tag: bytes, data: bytes) -> bytes:
    out = struct.pack(">I", len(data)) + tag + data
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return out + struct.pack(">I", crc)


def encode_png(rgba: np.ndarray) -> bytes:
    """Encode an ``(H, W, 3|4)`` uint8 array as PNG bytes (RGBA, 8-bit)."""
    arr = np.ascontiguousarray(rgba)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        alpha = np.full((h, w, 1), 255, np.uint8)
        arr = np.concatenate([arr, alpha], axis=2)

    # Prepend a per-scanline filter byte (0 = None).
    raw = np.empty((h, 1 + w * 4), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = arr.reshape(h, w * 4)
    compressed = zlib.compress(raw.tobytes(), level=6)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit, RGBA
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")


def png_data_uri(rgba: np.ndarray) -> str:
    """Return a ``data:image/png;base64,...`` URI for the given RGBA array."""
    b64 = base64.b64encode(encode_png(rgba)).decode("ascii")
    return "data:image/png;base64," + b64
