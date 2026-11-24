"""Minimal GeoPackage feature reader (points and lines) without GDAL."""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import numpy as np

_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def _wkb_geometries(wkb: bytes, offset: int = 0):
    """Yield ("point"|"line", ndarray Nx2) from WKB (2D/Z/M variants)."""
    endian = "<" if wkb[offset] == 1 else ">"
    gtype = struct.unpack_from(endian + "I", wkb, offset + 1)[0]
    base = gtype % 1000
    dims = 2 + (1 if gtype // 1000 in (1, 2) else 0) + (1 if gtype // 1000 == 3 else 0)
    if gtype & 0x80000000:  # EWKB-style Z flag
        base, dims = gtype & 0xFF, 3
    pos = offset + 5
    if base == 1:
        pt = struct.unpack_from(endian + "d" * dims, wkb, pos)
        yield "point", np.array([[pt[0], pt[1]]]); return pos + 8 * dims
    if base == 2:
        n = struct.unpack_from(endian + "I", wkb, pos)[0]
        vals = np.array(struct.unpack_from(endian + "d" * (n * dims), wkb, pos + 4)).reshape(n, dims)
        yield "line", vals[:, :2]; return pos + 4 + 8 * n * dims
    if base in (4, 5, 6, 7):
        n = struct.unpack_from(endian + "I", wkb, pos)[0]
        pos += 4
        for _ in range(n):
            gen = _wkb_geometries(wkb, pos)
            while True:
                try:
                    yield next(gen)
                except StopIteration as stop:
                    pos = stop.value or pos
                    break
        return pos
    return pos


def read_features(path: Path) -> list[dict]:
    """Return layers as ``{"name", "srs", "points": Nx2, "lines": [Nx2...]}``."""
    layers = []
    with sqlite3.connect(Path(path)) as con:
        rows = con.execute("SELECT c.table_name, c.srs_id, g.column_name FROM gpkg_contents c "
                           "JOIN gpkg_geometry_columns g ON g.table_name = c.table_name "
                           "WHERE c.data_type = 'features'").fetchall()
        for table, srs, column in rows:
            points, lines = [], []
            for (blob,) in con.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'):
                if not blob or blob[:2] != b"GP":
                    continue
                flags = blob[3]
                start = 8 + _ENVELOPE_BYTES.get((flags >> 1) & 7, 0)
                try:
                    for kind, coords in _wkb_geometries(bytes(blob), start):
                        (points if kind == "point" else lines).append(coords)
                except (struct.error, IndexError):
                    continue
            layers.append({"name": table, "srs": int(srs) if srs and int(srs) > 0 else None,
                           "points": np.vstack(points) if points else np.zeros((0, 2)), "lines": lines})
    return layers
