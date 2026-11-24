# EPANET Add-ons

Local tools for EPANET hydraulic and MSX calculations, with a reusable Python
wrapper and a Streamlit workbench for MIKE URBAN Classic water-model imports.

## Start here

```bash
make tkinter
```

This opens the desktop workbench. It has a CRS-aware map over online basemaps,
analytics layers with a time slider, a data browser with scenario comparison,
an MSX compound studio, and an object inspector with bulk editing. It opens
EPANET `.inp` files, imports MIKE URBAN `.mdb` models, runs hydraulics,
quality and MSX, and saves local projects together with their results. See
the [desktop workbench guide](docs/DESKTOP_WORKBENCH.md).

The earlier browser prototype is still available with `make streamlit`.

The first command creates `venv` and installs the relevant dependencies.
Use `make help` to list launch and installation targets. Choose another
environment directory with `VENV=.venv`, or pass Streamlit options with, for
example, `make streamlit ARGS="--server.port 8502"`.

## What is included

- EPANET hydraulic and standard quality calculations through EPyT
- EPANET-MSX multi-species calculations
- Reusable `EpanetWrapper` API for any GUI
- MIKE URBAN Classic `.mdb` to GeoPackage and standard EPANET INP translation
- Tkinter desktop workbench (map, analytics, scenarios, MSX studio) and a
  Streamlit prototype

## Documentation

- [Desktop workbench guide](docs/DESKTOP_WORKBENCH.md): map and CRS,
  analytics, scenarios, data browser, editing, and the MSX studio.
- [Local workbench guide](docs/WORKBENCH.md): MDB import and recovery,
  projects, and the Streamlit prototype.
- [Calculation-engine capabilities](docs/ENGINE_CAPABILITIES.md) — what the
  standard engine, DHI muEPANET, water-hammer, and reliability workflows do or
  do not support.
- [Core API and GUI variants](docs/API_AND_UIS.md) — wrapper examples, GUI
  status, and guidance for adding another interface.

## MIKE URBAN import

Open an MDB as a calculation model in the Streamlit sidebar, or export its
spatial assets directly:

```bash
venv/bin/python -m epanet_addons.mike_urban.importer Model.mdb Model.gpkg
```

The converter preserves the original geometry and identifies recognised CRS
values conservatively; the supplied Czech model is recognised as S-JTSK /
Krovak East North (EPSG:5514). Review `conversion-report.json` before relying
on a converted calculation model.

Some large Personal Geodatabases require MDBTools. Run
`bash scripts/install-mdbtools.sh` once, or set `MDB_JSON` to an existing
`mdb-json` executable. Details are in the workbench guide.

## Development

Install the dependency set for the UI you are changing. Keep shared behaviour
in `epanet_addons/`: the engine, `network.py` (topology, properties, results,
scenarios), `msx.py` (MSX model), and `crs.py`. Use the API/UI guide when
adding a new frontend. Run the core tests with
`venv/bin/python -m pytest tests`. The Tkinter workbench is the primary UI,
Streamlit is a prototype, and the other GUI folders are scaffolds.

## License

See [LICENSE](LICENSE).
