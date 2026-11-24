"""Project coordinate reference handling for map views.

Every workbench project carries an explicit CRS.  Network coordinates stay in
that *native* CRS (EPANET has no CRS field); views transform them to Web
Mercator (EPSG:3857) so they can be laid over XYZ tile basemaps.  A project in
``LOCAL`` engineering coordinates is drawn without a basemap and is never
silently treated as longitude/latitude.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .geo import identify_coordinates

try:  # pyproj is optional at import time so conversion-only tools keep working
    from pyproj import CRS as _PyprojCRS, Transformer as _Transformer
except Exception:  # pragma: no cover - exercised when pyproj is absent
    _PyprojCRS = _Transformer = None

LOCAL = "LOCAL"

#: Frequently used CRSs offered in UIs.  Any other EPSG code may be typed.
PRESETS: list[tuple[str, str]] = [
    ("EPSG:5514", "S-JTSK / Krovak East North (CZ, SK)"),
    ("EPSG:4326", "WGS 84 longitude/latitude"),
    ("EPSG:3857", "WGS 84 / Pseudo-Mercator"),
    ("EPSG:32633", "WGS 84 / UTM zone 33N"),
    ("EPSG:32634", "WGS 84 / UTM zone 34N"),
    ("EPSG:25833", "ETRS89 / UTM zone 33N"),
    ("EPSG:2180", "ETRS89 / Poland CS92"),
    ("EPSG:31287", "MGI / Austria Lambert"),
    ("EPSG:2154", "RGF93 / Lambert-93 (FR)"),
    ("EPSG:27700", "OSGB36 / British National Grid"),
    ("EPSG:2263", "NAD83 / New York Long Island (ftUS)"),
    (LOCAL, "Local engineering coordinates (no basemap)"),
]

WEB_MERCATOR_HALF = 20037508.342789244


def pyproj_available() -> bool:
    return _Transformer is not None


@dataclass(frozen=True)
class ProjectCRS:
    """A native CRS plus cached transformers to Web Mercator and WGS 84."""

    code: str = LOCAL

    @property
    def is_local(self) -> bool:
        return self.code == LOCAL or not pyproj_available()

    @property
    def name(self) -> str:
        for code, label in PRESETS:
            if code == self.code:
                return f"{label} ({code})" if code != LOCAL else label
        if self.is_local:
            return "Local engineering coordinates"
        try:
            return f"{_PyprojCRS.from_user_input(self.code).name} ({self.code})"
        except Exception:
            return self.code

    @property
    def units(self) -> str:
        if self.is_local:
            return "model units"
        try:
            axis = _PyprojCRS.from_user_input(self.code).axis_info[0]
            return axis.unit_name
        except Exception:
            return "?"

    def _transformer(self, source: str, target: str):
        return _cached_transformer(source, target)

    # -- conversions -----------------------------------------------------
    def to_world(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        """Native → map world coordinates (EPSG:3857, or native when local)."""
        xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
        if self.is_local or self.code == "EPSG:3857":
            return xs.copy(), ys.copy()
        wx, wy = self._transformer(self.code, "EPSG:3857").transform(xs, ys)
        return np.asarray(wx, dtype=float), np.asarray(wy, dtype=float)

    def from_world(self, wx, wy) -> tuple[np.ndarray, np.ndarray]:
        wx, wy = np.asarray(wx, dtype=float), np.asarray(wy, dtype=float)
        if self.is_local or self.code == "EPSG:3857":
            return wx.copy(), wy.copy()
        x, y = self._transformer("EPSG:3857", self.code).transform(wx, wy)
        return np.asarray(x, dtype=float), np.asarray(y, dtype=float)

    def world_to_lonlat(self, wx: float, wy: float) -> tuple[float, float] | None:
        if self.is_local:
            return None
        lon, lat = self._transformer("EPSG:3857", "EPSG:4326").transform(wx, wy)
        return float(lon), float(lat)

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name}


_TRANSFORMERS: dict[tuple[str, str], object] = {}


def _cached_transformer(source: str, target: str):
    key = (source, target)
    if key not in _TRANSFORMERS:
        _TRANSFORMERS[key] = _Transformer.from_crs(source, target, always_xy=True)
    return _TRANSFORMERS[key]


def validate_code(code: str) -> str:
    """Normalise user input such as ``5514`` or ``epsg:5514``; raise if unknown."""
    code = code.strip()
    if not code or code.upper() == LOCAL:
        return LOCAL
    if code.isdigit():
        code = f"EPSG:{code}"
    code = code.upper()
    if not pyproj_available():
        raise ValueError("pyproj is not installed; only LOCAL coordinates are available.")
    _PyprojCRS.from_user_input(code)  # raises CRSError for unknown codes
    return code


def detect_crs(points: Iterable[tuple[float, float]], hint: str | None = None) -> ProjectCRS:
    """Guess a CRS from coordinates conservatively.

    ``hint`` (for example from a MIKE URBAN conversion report) wins.  Otherwise
    only unambiguous ranges are recognised: S-JTSK/Krovak and lon/lat degrees.
    Anything else stays LOCAL so that engineering grids are never misplaced.
    """
    if hint:
        try:
            return ProjectCRS(validate_code(hint))
        except Exception:
            pass
    sample = [(float(x), float(y)) for x, y in points]
    if not sample:
        return ProjectCRS(LOCAL)
    known = identify_coordinates(sample)
    if known.epsg:
        return ProjectCRS(f"EPSG:{known.epsg}")
    xs = np.array([p[0] for p in sample]); ys = np.array([p[1] for p in sample])
    if (np.abs(xs) <= 180).all() and (np.abs(ys) <= 90).all() and np.ptp(xs) < 5 and np.ptp(ys) < 5 \
            and (np.abs(xs) > 0.01).mean() > 0.9:
        return ProjectCRS("EPSG:4326")
    return ProjectCRS(LOCAL)
