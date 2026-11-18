# EPANET Add-ons

Local tools for EPANET hydraulic and MSX calculations, with a reusable Python
wrapper and a Streamlit workbench for MIKE URBAN Classic water-model imports.

## Start here

```bash
make streamlit
```

Open the local address printed by Streamlit. The workbench can open an EPANET
`.inp`, import a MIKE URBAN `.mdb`, create a GeoPackage, edit selected
parameters, run hydraulics or MSX, and save a local project.

For the desktop interface, run:

```bash
make tkinter
```

The first command creates `venv` and installs the relevant dependencies.
Use `make help` to list launch and installation targets. Choose another
environment directory with `VENV=.venv`, or pass Streamlit options with, for
example, `make streamlit ARGS="--server.port 8502"`.

## What is included

- EPANET hydraulic and standard quality calculations through EPyT
- EPANET-MSX multi-species calculations
- Reusable `EpanetWrapper` API for any GUI
- MIKE URBAN Classic `.mdb` to GeoPackage and standard EPANET INP translation
- Local Streamlit project workspace and a Tkinter desktop interface

## Documentation

- [Local workbench guide](docs/WORKBENCH.md) — import, maps, local projects,
  coordinate systems, and MDB recovery.
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

Install the dependency set for the UI you are changing, keep shared behavior
in `epanet_addons/engine.py`, and use the API/UI guide when adding a new frontend.
The Streamlit and Tkinter variants are functional; other GUI folders are
scaffolds rather than equivalent applications.

## License

See [LICENSE](LICENSE).
