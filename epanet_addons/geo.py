"""Coordinate reference identification shared by MIKE URBAN import and UIs.

EPANET ``[COORDINATES]`` has no CRS field, while MIKE URBAN Personal GDB
geometry does.  This module keeps the source CRS explicit where possible and
uses conservative value-range detection only when an MDB has no usable CRS
metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CoordinateReference:
    epsg: int | None
    name: str
    reason: str


S_JTSK_KROVAK_EAST_NORTH = CoordinateReference(
    5514, "S-JTSK / Krovak East North (EPSG:5514)",
    "coordinates match the Czech S-JTSK Krovak East-North projected range",
)
UNKNOWN = CoordinateReference(None, "Unknown / local engineering coordinates", "no recognised coordinate range")


def identify_coordinates(points: Iterable[tuple[float, float]]) -> CoordinateReference:
    """Identify a known CRS without silently reprojecting engineering data.

    EPSG:5514 commonly occurs in MIKE URBAN models in Czechia.  Its projected
    values are negative and near x=-0.4..-1.0 million, y=-0.8..-1.4 million.
    The broad test prevents confusing WGS84 degrees or ordinary local grids
    with Krovak coordinates.  Add further rules here as source formats are
    introduced.
    """
    sample = [(float(x), float(y)) for x, y in points]
    if not sample:
        return UNKNOWN
    matching = sum(-1_100_000 <= x <= -300_000 and -1_450_000 <= y <= -700_000 for x, y in sample)
    if matching / len(sample) >= 0.9:
        return S_JTSK_KROVAK_EAST_NORTH
    return UNKNOWN
