"""Export MIKE URBAN MDB tables to inspection-friendly CSV files."""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from pathlib import Path

from .importer import _mdbtools_executable, _mdbtools_rows


def export_mike_urban_csv(source: Path, destination: Path, prefix: str = "mw_") -> dict[str, int]:
    """Export model tables as CSV, omitting internal spatial-index tables."""
    executable = _mdbtools_executable()
    if executable is None:
        raise RuntimeError("MDBTools is required; run scripts/install-mdbtools.sh first.")
    mdb_tables = Path(executable).with_name("mdb-tables")
    environment = os.environ.copy()
    local_lib = Path(executable).parent.parent / "lib"
    if local_lib.is_dir():
        environment["LD_LIBRARY_PATH"] = str(local_lib) + os.pathsep + environment.get("LD_LIBRARY_PATH", "")
    result = subprocess.run([str(mdb_tables), "-1", str(source)], check=True, text=True, capture_output=True, env=environment)
    tables = [name for name in result.stdout.splitlines() if name.startswith(prefix) and not name.endswith("_SHAPE_Index")]
    destination.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for table in tables:
        rows = _mdbtools_rows(source, table)
        fields = sorted({field for row in rows for field in row})
        with (destination / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for field, value in row.items()})
        counts[table] = len(rows)
    (destination / "manifest.json").write_text(json.dumps({"source": str(source), "tables": counts}, indent=2), encoding="utf-8")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export MIKE URBAN mw_* tables from an MDB to CSV.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(export_mike_urban_csv(args.source, args.destination))
