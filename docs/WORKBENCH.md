# Local Workbench Guide

The Streamlit application is the recommended UI for local EPANET, EPANET-MSX,
and MIKE URBAN work. Start it from the repository root:

```bash
make streamlit
```

All saved projects remain local. No model is uploaded to a cloud service.

## Typical workflow

1. Open an EPANET `.inp` model in the **Workspace** sidebar.
2. Optionally import a matching MIKE URBAN Classic water `.mdb` in **MIKE
   URBAN assets**.
   The converted asset map appears immediately; opening an EPANET file is not
   required to inspect it.
3. Open **Network viewer** to inspect the EPANET network. Run hydraulics to
   colour it by pressure or flow.
4. Use **Parameters** to change node elevation or link diameter, length, and
   roughness. Changes are in memory until the project is saved.
5. Run **EPANET hydraulics**. Optionally select an `.msx` chemistry file and
   run **MSX quality**.
6. Save the workspace with **Save project**.

## Spatial views and calculation results

There are two deliberately separate views:

- **Network viewer** displays the EPANET `.inp` network and its hydraulic
  results (elevation, pressure, or flow).
- **GeoPackage assets** displays the raw geometry converted from MIKE URBAN:
  junctions, pipes, tanks, pumps, and valves. Click **Show asset map** to draw
  it, and inspect the attribute tables beneath it.

The GeoPackage is an asset/spatial model; it does not automatically become an
EPANET scenario. Calculation results are shown on the EPANET network. To
overlay results on the GeoPackage, the EPANET IDs must be matched to the MIKE
`MUID` fields; this remains an explicit mapping task so incorrect results are
not silently attached to assets.

## Coordinate reference systems

An EPANET INP stores X/Y coordinates but has no CRS field.  The MIKE URBAN
importer therefore identifies recognised source ranges before writing a
GeoPackage.  `Model_budejice.mdb` is identified as **S-JTSK / Krovak East
North (EPSG:5514)** and the GeoPackage layers are tagged with that CRS.  The
calculation viewer preserves those projected metre coordinates rather than
treating them as longitude/latitude.

The detector is intentionally conservative.  A source it does not recognise
remains tagged as a local engineering CRS; add a verified rule to
`epanet_addons/geo.py` before assigning another EPSG code.

## MDB-to-EPANET conversion fidelity

The calculation-model importer writes a standard EPANET INP, retaining
junctions and emitters, reservoirs and tanks, pipes (including check valves
and vertices), valves, pumps, native curves, demands/patterns, time and solver
settings, simple controls, global and object reaction coefficients, initial
quality, sources, and energy settings where their MIKE tables are populated.
Its `conversion-report.json` is part of the project record. Review
`omitted_*`, `unknown_*`, and `untranslated_controls` before approving a
converted model for operational use.

The importer emits the four documented EPANET-compatible `mw_Control`
conditions (node below/above, elapsed time, and clock time). It never guesses
unsupported MIKE extensions such as variable-speed drive, water-hammer,
real-time-control, calibration, fire-flow, or reliability analyses. Such
records remain visible in the conversion report rather than being silently
changed into different EPANET behaviour.

For the complete standard-EPANET versus DHI muEPANET capability matrix,
including VSD, real-time control, fire flow, criticality, water hammer and
reliability workflows, see [Calculation-engine capabilities](ENGINE_CAPABILITIES.md).

## Local project layout

Saving a project named `city-water` creates this ignored local directory:

```text
projects/city-water/
├── project.json
├── model.inp
├── chemistry.msx       # only when selected
└── assets.gpkg         # only when an MDB was imported
```

`model.inp` contains the current parameter edits. `assets.gpkg` is a portable
SQLite GeoPackage suitable for QGIS and other GIS software.

## Large MIKE URBAN MDB files

The built-in Python reader works for many small personal geodatabases. Some
large MIKE URBAN archives contain overflow/MEMO records that it cannot parse.
The workbench then switches to MDBTools' streaming `mdb-json` utility.

Install the project-local fallback once:

```bash
bash scripts/install-mdbtools.sh
```

This builds MDBTools below `.tools/` and does not require root access. Restart
the Streamlit app afterwards. If your system already supplies `mdb-json`, it
is detected automatically. A custom executable can be selected with:

```bash
export MDB_JSON=/path/to/mdb-json
```

If import still fails, preserve the original MDB and share the full error plus
the model version; do not overwrite the source archive.

### Export tables for inspection

To inspect the raw MIKE water tables before mapping, export all `mw_*` tables
except spatial-index internals to CSV:

```bash
venv/bin/python -m epanet_addons.mike_urban.exporter Model.mdb /tmp/mike-urban-csv
```

The output includes `manifest.json` with record counts. Geometry BLOB values
are represented as JSON/base64 in the CSVs; use the GeoPackage for spatial
inspection.

## MSX

Select a compatible `.msx` file after opening its corresponding EPANET model,
then click **Run MSX quality**. The results report time steps and species in
the Results tab. MSX requires an EPANET model with compatible object IDs; it
does not run directly from the GeoPackage.

## Reusable translation layer

MDB translation is not tied to Streamlit. Every UI using `EpanetWrapper` can
load either source type:

```python
wrapper.load_file(Path("network.inp"))
report = wrapper.load_mike_urban_mdb(Path("Model.mdb"))
```

`load_mike_urban_mdb()` creates a temporary EPANET INP, loads it through the
same calculation engine, and returns a conversion report. UIs should display
that report before enabling production use. The lower-level reusable modules
are `epanet_addons.mike_urban.importer` (MDB → GeoPackage),
`epanet_addons.mike_urban.inp` (MDB → EPANET INP), and
`epanet_addons.mike_urban.exporter` (MDB → inspection CSV files). The former
top-level scripts remain as compatibility commands.

The conversion report records inferred endpoints, reconstructed MIKE insert
segments, disconnected components excluded from the executable calculation
component, object type/status counters, constant fallback patterns, and any
items that need engineering review.
