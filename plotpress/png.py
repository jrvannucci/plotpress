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


_SIG = b"\x89PNG\r\n\x1a\n"


def encode_png(rgba: np.ndarray) -> bytes:
    """Encode an ``(H, W, 3|4)`` uint8 array as 8-bit PNG bytes.

    Colormapped output is emitted as **indexed** colour when it fits in 256
    entries, which every mesh does: the colours come from a 256-entry colormap
    LUT, so a field of any size still draws from at most 256 distinct RGBA
    values. That stores one byte per pixel plus a small palette instead of four
    bytes per pixel, and the whole raster travels inside the interactive HTML,
    so the saving lands directly on the file a reader downloads. Anything with
    more colours -- a Gouraud mesh interpolates between nodes, so it does --
    falls back to RGBA.
    """
    arr = np.ascontiguousarray(rgba)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.full((h, w, 1), 255, np.uint8)], axis=2)

    indexed = _encode_indexed(arr, h, w)
    return indexed if indexed is not None else _encode_rgba(arr, h, w)


def _encode_rgba(arr: np.ndarray, h: int, w: int) -> bytes:
    # Prepend a per-scanline filter byte (0 = None).
    raw = np.empty((h, 1 + w * 4), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = arr.reshape(h, w * 4)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)   # 8-bit RGBA
    return (_SIG + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw.tobytes(), level=6))
            + _chunk(b"IEND", b""))


def _encode_indexed(arr: np.ndarray, h: int, w: int):
    """Indexed-colour PNG, or ``None`` if the image needs more than 256 entries."""
    flat = arr.reshape(-1, 4)
    # One uint32 per pixel makes the unique/inverse pass cheap; the byte order
    # only has to be self-consistent, since the palette is rebuilt from it.
    keys = flat.view(np.uint32).reshape(-1) if flat.flags["C_CONTIGUOUS"] \
        else np.ascontiguousarray(flat).view(np.uint32).reshape(-1)
    palette_keys, index = np.unique(keys, return_inverse=True)
    if palette_keys.size > 256:
        return None

    palette = palette_keys.view(np.uint8).reshape(-1, 4)
    raw = np.empty((h, 1 + w), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = index.astype(np.uint8).reshape(h, w)

    chunks = [_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)),
              _chunk(b"PLTE", palette[:, :3].tobytes())]
    alpha = palette[:, 3]
    if np.any(alpha != 255):
        # tRNS for indexed PNG is one alpha byte per palette entry; trailing
        # opaque entries may be omitted, so stop after the last transparent one.
        last = int(np.nonzero(alpha != 255)[0].max())
        chunks.append(_chunk(b"tRNS", alpha[:last + 1].tobytes()))
    chunks.append(_chunk(b"IDAT", zlib.compress(raw.tobytes(), level=6)))
    chunks.append(_chunk(b"IEND", b""))
    return _SIG + b"".join(chunks)


def png_data_uri(rgba: np.ndarray) -> str:
    """Return a ``data:image/png;base64,...`` URI for the given RGBA array."""
    b64 = base64.b64encode(encode_png(rgba)).decode("ascii")
    return "data:image/png;base64," + b64
