"""Read MIKE URBAN Personal Geodatabases and write portable GeoPackages.

The importer targets the water-distribution feature classes used by MIKE
URBAN Classic (``mw_*``).  It preserves their engineering attributes and
geometry, but does not pretend that a GeoPackage alone is an EPANET model:
demands, patterns, controls and curves still need an explicit EPANET export.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sqlite3
import struct
import subprocess
from pathlib import Path
from typing import Any, Iterable
from ..geo import CoordinateReference, identify_coordinates


class MikeUrbanImportError(RuntimeError):
    """Raised when an MDB is not a readable MIKE URBAN water model."""


def _mdbtools_executable() -> str | None:
    """Find mdb-json, allowing a user-local MDBTools installation."""
    configured = os.environ.get("MDB_JSON")
    if configured and Path(configured).is_file():
        return configured
    installed = shutil.which("mdb-json")
    if installed:
        return installed
    local = Path(__file__).parents[2] / ".tools" / "mdbtools" / "bin" / "mdb-json"
    return str(local) if local.is_file() else None


def _mdbtools_rows(source: Path, table: str) -> list[dict[str, Any]]:
    executable = _mdbtools_executable()
    if executable is None:
        raise MikeUrbanImportError(
            "MDBTools fallback is unavailable. Run scripts/install-mdbtools.sh once, "
            "install mdbtools system-wide, or set MDB_JSON to its mdb-json executable."
        )
    try:
        environment = os.environ.copy()
        local_lib = Path(executable).parent.parent / "lib"
        if local_lib.is_dir():
            environment["LD_LIBRARY_PATH"] = str(local_lib) + os.pathsep + environment.get("LD_LIBRARY_PATH", "")
        output = subprocess.run([executable, str(source), table], check=True, text=True, capture_output=True, env=environment).stdout
        rows = []
        for line in output.splitlines():
            row = json.loads(line)
            shape = row.get("SHAPE")
            if isinstance(shape, dict) and "$binary" in shape:
                row["SHAPE"] = base64.b64decode(shape["$binary"])
            rows.append(row)
        return rows
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise MikeUrbanImportError(f"MDBTools could not read {table}: {error}") from error


def _columns_to_rows(columns: dict[str, Any]) -> list[dict[str, Any]]:
    lengths = [len(values) for values in columns.values() if isinstance(values, list)]
    return [
        {name: values[index] if isinstance(values, list) and index < len(values) else None
         for name, values in columns.items()}
        for index in range(max(lengths, default=0))
    ]


def _esri_shape_to_wkb(value: bytes | None) -> bytes | None:
    """Decode the Point/Polyline shapes stored in an ESRI Personal GDB.

    MIKE URBAN water nodes are Point (1) and pipes are Polyline (3).  Other
    shape kinds are retained as a null geometry instead of being corrupted.
    """
    if not value or len(value) < 4:
        return None
    shape_type = struct.unpack_from("<I", value)[0]
    if shape_type == 0:
        return None
    if shape_type == 1 and len(value) >= 20:
        x, y = struct.unpack_from("<dd", value, 4)
        return struct.pack("<BI2d", 1, 1, x, y)
    if shape_type != 3 or len(value) < 44:
        return None
    part_count, point_count = struct.unpack_from("<II", value, 36)
    offset = 44
    if len(value) < offset + 4 * part_count + 16 * point_count:
        return None
    parts = struct.unpack_from(f"<{part_count}I", value, offset)
    offset += 4 * part_count
    points = struct.unpack_from(f"<{point_count * 2}d", value, offset)
    lines = []
    for index, start in enumerate(parts):
        end = parts[index + 1] if index + 1 < part_count else point_count
        if end > start:
            lines.append(points[start * 2:end * 2])
    if not lines:
        return None
    if len(lines) == 1:
        return struct.pack("<BII", 1, 2, len(lines[0]) // 2) + struct.pack(f"<{len(lines[0])}d", *lines[0])
    chunks = [struct.pack("<BII", 1, 5, len(lines))]
    for line in lines:
        chunks.extend((struct.pack("<BI", 1, 2), struct.pack("<I", len(line) // 2), struct.pack(f"<{len(line)}d", *line)))
    return b"".join(chunks)


def _gpkg_geometry(wkb: bytes | None, srs_id: int = -1) -> bytes | None:
    if wkb is None:
        return None
    # GeoPackage binary header: GP, version 0, little endian / no envelope.
    return b"GP\x00\x01" + struct.pack("<i", srs_id) + wkb


def _identify_source_crs(data: dict[str, list[dict[str, Any]]]) -> CoordinateReference:
    """Identify CRS from point features, retaining unknown local grids as such."""
    points = []
    for table in ("mw_Junction", "mw_Tank"):
        for row in data.get(table, []):
            wkb = _esri_shape_to_wkb(row.get("SHAPE"))
            if wkb and len(wkb) >= 21 and struct.unpack_from("<I", wkb, 1)[0] == 1:
                points.append(struct.unpack_from("<dd", wkb, 5))
    return identify_coordinates(points)


def _create_gpkg(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        PRAGMA application_id=1196437808;
        PRAGMA user_version=10300;
        CREATE TABLE gpkg_spatial_ref_sys (
          srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
          organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
          definition TEXT NOT NULL, description TEXT
        );
        INSERT INTO gpkg_spatial_ref_sys VALUES
          ('Undefined Cartesian', -1, 'NONE', -1, 'undefined', 'Source CRS is retained in MIKE URBAN metadata'),
          ('Undefined geographic', 0, 'NONE', 0, 'undefined', 'undefined'),
          ('WGS 84 geodetic', 4326, 'EPSG', 4326,
           'GEOGCS["WGS 84",DATUM["World Geodetic System 1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]', ''),
          ('S-JTSK / Krovak East North', 5514, 'EPSG', 5514,
           'EPSG:5514', 'Czech national projected coordinate reference system');
        CREATE TABLE gpkg_contents (
          table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
          identifier TEXT UNIQUE, description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER
        );
        CREATE TABLE gpkg_geometry_columns (
          table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL,
          srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
          PRIMARY KEY (table_name, column_name)
        );
    """)


def _add_layer(connection: sqlite3.Connection, name: str, geometry: str, rows: Iterable[dict[str, Any]], fields: tuple[str, ...], srs_id: int = -1) -> int:
    numeric = {"Elev", "Diameter", "L", "RCoeff", "InitLevel", "MinLevel", "MaxLevel", "MinVol", "Setting"}
    connection.execute(f'CREATE TABLE "{name}" (fid INTEGER PRIMARY KEY, geom BLOB, ' + ", ".join(f'"{field}"' + (" REAL" if field in numeric else " TEXT") for field in fields) + ")")
    connection.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES (?, 'features', ?, ?)", (name, name, srs_id))
    connection.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)", (name, geometry, srs_id))
    count = 0
    for row in rows:
        connection.execute(f'INSERT INTO "{name}" (geom, ' + ", ".join(f'"{field}"' for field in fields) + ") VALUES (" + ", ".join("?" for _ in range(len(fields) + 1)) + ")", [_gpkg_geometry(_esri_shape_to_wkb(row.pop("SHAPE", None)), srs_id)] + [row.get(field) for field in fields])
        count += 1
    return count


def import_mike_urban_mdb(source: Path, destination: Path, overwrite: bool = False) -> dict[str, int]:
    """Convert a MIKE URBAN water-distribution MDB into a GeoPackage."""
    AccessParser = None
    try:
        from access_parser import AccessParser
    except ImportError:
        # MDBTools is also a supported reader. It is especially useful for
        # overflow/MEMO records in older MIKE URBAN Personal GDB archives.
        pass
    source, destination = Path(source), Path(destination)
    if source.suffix.lower() != ".mdb" or not source.is_file():
        raise MikeUrbanImportError(f"Not a readable .mdb file: {source}")
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
        destination.unlink()
    names = ("mw_Junction", "mw_Tank", "mw_Pipe", "mw_Pump", "mw_Valve")
    try:
        if AccessParser is None:
            raise ImportError("access-parser is not installed")
        database = AccessParser(str(source))
        missing = {"mw_Junction", "mw_Pipe"} - set(database.catalog)
        if missing:
            raise MikeUrbanImportError(f"Not a MIKE URBAN water model; missing {', '.join(sorted(missing))}")
        data = {name: _columns_to_rows(database.parse_table(name)) for name in names if name in database.catalog}
    except Exception as parser_error:
        # access-parser has known limits with overflow/MEMO records in large MDBs.
        # MDBTools streams rows and handles this MIKE URBAN archive successfully.
        try:
            data = {name: _mdbtools_rows(source, name) for name in names}
        except MikeUrbanImportError as fallback_error:
            raise MikeUrbanImportError(
                f"The built-in Access reader failed ({parser_error}). {fallback_error}"
            ) from fallback_error
    source_crs = _identify_source_crs(data)
    srs_id = source_crs.epsg if source_crs.epsg is not None else -1
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination) as connection:
        _create_gpkg(connection)
        counts = {
            "junctions": _add_layer(connection, "junctions", "POINT", data.get("mw_Junction", []), ("MUID", "Elev", "PZoneID", "Description"), srs_id),
            "tanks": _add_layer(connection, "tanks", "POINT", data.get("mw_Tank", []), ("MUID", "Elev", "Diameter", "InitLevel", "MinLevel", "MaxLevel", "MinVol", "Description"), srs_id),
            "pipes": _add_layer(connection, "pipes", "LINESTRING", data.get("mw_Pipe", []), ("MUID", "FROMNODE", "TONODE", "Diameter", "L", "RCoeff", "Material", "Description"), srs_id),
            "pumps": _add_layer(connection, "pumps", "LINESTRING", data.get("mw_Pump", []), ("MUID", "FROMNODE", "TONODE", "QHCurveID", "Description"), srs_id),
            "valves": _add_layer(connection, "valves", "LINESTRING", data.get("mw_Valve", []), ("MUID", "FROMNODE", "TONODE", "Diameter", "Setting", "Description"), srs_id),
        }
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a MIKE URBAN water MDB to a GeoPackage.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(import_mike_urban_mdb(args.source, args.destination, args.overwrite))


if __name__ == "__main__":
    main()
