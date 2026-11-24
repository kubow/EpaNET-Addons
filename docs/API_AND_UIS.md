# Core API and user interfaces

## Core wrapper

`epanet_addons/engine.py` is the shared boundary between engines and user
interfaces. Keep application-specific UI state outside it.

```text
epanet_addons/
├── engine.py          EPANET and MSX wrapper
├── network.py         topology, editable properties, results, scenarios, KPIs
├── msx.py             structured MSX model: parse, validate, write, templates
├── crs.py             project CRS, detection, transforms to Web Mercator
├── gpkg.py            GeoPackage point/line reader (no GDAL)
├── geo.py             CRS identification rules
├── projects.py        local project persistence (incl. scenario results)
└── mike_urban/
    ├── importer.py    MDB → GeoPackage
    ├── inp.py         MDB → standard EPANET INP
    └── exporter.py    MDB → inspection CSV
```

The former top-level modules are compatibility shims. New code should import
from `epanet_addons` directly.

```python
from pathlib import Path
from epanet_addons.engine import EpanetWrapper

model = EpanetWrapper()
model.load_file(Path("network.inp"))
model.run_simulation()
print(model.get_statistics())
model.save_input_file(Path("edited-network.inp"))
model.close()
```

For multi-species chemistry, provide an EPANET-MSX file after loading the INP:

```python
results = model.run_msx(Path("chemistry.msx"))
```

For a MIKE URBAN Classic water model, use the same source-neutral wrapper
entry point:

```python
report = model.load_mike_urban_mdb(Path("Model.mdb"))
```

The return value is the conversion report. Review it before running or saving
the resulting EPANET model.

### Main methods

| Method | Purpose |
|---|---|
| `load_file(path)` | Load an EPANET INP from a writable staging area |
| `load_mike_urban_mdb(path)` | Translate an MDB and load its standard EPANET model |
| `run_simulation()` | Run hydraulic and standard quality analysis |
| `run_msx(path)` | Run EPANET-MSX chemistry |
| `get_statistics()` | Retrieve node/link IDs, counts, elevations, and coordinates |
| `get_computed_time_series()` | Retrieve hydraulic result arrays |
| `get_msx_results()` | Retrieve MSX result arrays after an MSX run |
| `save_input_file(path)` | Save the current in-memory EPANET model |
| `close()` | Release the engine and temporary files |

For interfaces, `epanet_addons.network` turns the engine state into plain
arrays. It provides `read_topology()`, the `NODE_FIELDS`/`LINK_FIELDS`
property catalogue with `set_property()`/`bulk_edit()`,
`Results.from_engine()` (hydraulics, quality and MSX as `(time, object)`
arrays), and `compare()`/`kpis()` for scenarios. `epanet_addons.msx` edits
`.msx` files as data, and `epanet_addons.crs` handles map projection.

The wrapper also provides Matplotlib-oriented topology, attribute, and time
series plotting helpers. Use them for lightweight interfaces; larger UIs may
render data through their own map/chart components.

## User-interface status

| Interface | Status | Intended use |
|---|---|---|
| `EpaNETTk` | Active (primary) | Desktop workbench: CRS map with basemaps, analytics layers, scenarios and comparison, data browser, MSX studio, editing ([guide](DESKTOP_WORKBENCH.md)) |
| `EpaNETStreamlit` | Prototype | Browser workbench for INP, MDB, GeoPackage, parameters, hydraulic/MSX runs |
| `EpaNETCustomTkinter`, `EpaNETPyQt`, `EpaNETwxPython`, `EpaNETKivy`, `EpaNETFlask`, `EpaNETFlet` | Scaffold | Starting points, not feature-equivalent applications |

Launch an available UI with `make streamlit` or `make tkinter`. The Makefile
also lists scaffold launch targets; their presence does not imply feature
parity.

## Adding an interface

1. Create `EpaNET<Framework>/__main__.py`.
2. Add `requirements/<framework>.in` that includes the base requirements.
3. Import `EpanetWrapper`; do not duplicate input parsing or engine lifecycle
   logic in the UI.
4. Keep saved-project and conversion-report handling explicit.
5. Add a smoke test using a small INP and, when relevant, an MDB fixture.

The requirements layout is:

- `requirements/base.in` — shared runtime dependencies
- `requirements/<framework>.in` — UI-specific dependencies
- `requirements/dev.in` — development tools
