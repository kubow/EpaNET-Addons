# Desktop workbench (Tkinter)

```bash
make tkinter                 # or: venv/bin/python -m EpaNETTk [model.inp]
```

One window with four synchronised areas. A selection, time step or scenario
change in one area updates all the others.

```text
┌ toolbar: open · MIKE URBAN · save │ Run · Run+MSX · ⚙ │ select/junction/pipe/move/delete │ CRS ┐
├──────────────┬───────────────────────────────────────────────┬────────────────┤
│ Layers &     │  Map │ Data browser │ MSX studio              │ Inspector      │
│ analytics    │                                               │ (edit + chart) │
│ Scenarios    │                                               │                │
├──────────────┴───────────────────────────────────────────────┴────────────────┤
│ ▶ ⏮ ⏭  ───────────── time slider ─────────────  t = 06:00 / 24 h   speed     │
└ status · cursor X/Y in the project CRS · lat/lon ─────────────────────────────┘
```

## Coordinate systems and basemaps

Every project has an explicit CRS (toolbar button, or **Network ▸ Coordinate
system**). Coordinates in the model are never changed. They are only
interpreted so the map can transform them to Web Mercator for tiles.

- MIKE URBAN imports take the CRS from the conversion report (S-JTSK/Krovák,
  EPSG:5514, for Czech models).
- INP files are auto-detected only when the coordinates fall in an unambiguous
  range (Krovák or lon/lat). Anything else stays **LOCAL**: the network is
  drawn without a basemap until you assign a CRS. The dialog previews where the
  network centre would land, so a wrong CRS is easy to spot.
- Basemaps: Esri Light/Dark Gray, OpenStreetMap, OpenTopoMap, Esri Topo, Esri
  Imagery, and ČÚZK Ortofoto. Tiles are cached in
  `~/.cache/epanet-workbench/tiles` and work offline once cached. Zooming past
  a provider's native maximum enlarges the deepest available tile. **Fade**
  lightens the basemap so analytics colours stand out.
- A GeoPackage (created automatically for MIKE URBAN imports, or added via
  **File ▸ Add GeoPackage overlay**) is drawn underneath the network in its own
  CRS.

## Analytics on the map

The left panel controls the analytics layers:

| Control | Effect |
|---|---|
| Node / link *Colour by* | Object type, any editable property (elevation, diameter, roughness, …), or any result: pressure, head, demand, quality, flow, velocity, unit headloss, MSX species |
| Ramp, size, width | Colour ramp; node size and link width proportional to the value |
| Flow direction arrows | Arrows follow the flow sign at the current time |
| Result statistic | *At time* (animated with the slider) or min / max / mean / range over the whole run |
| Difference vs baseline | Colours show the active scenario minus the baseline, on a diverging ramp |
| Range Fix / Auto | Lock the legend range, e.g. to compare scenarios on one scale |
| Highlight / alerts | Threshold filter (presets: low or negative pressure, high velocity, stagnation, headloss, water age). Matching objects are emphasised, the rest are dimmed, and **Select matches** turns them into a selection for bulk editing |

Hovering shows a tooltip. Right-click opens actions: copy ID, connected links,
time series, add an MSX source, or trace quality from this node.

## Scenarios and comparison

Every run is stored as a scenario (`Run 1`, `Run 2`, …). The first scenario
becomes the baseline automatically. In the **Scenarios** list you can show,
rename or delete scenarios, or set a different baseline. Below the list, KPIs
(minimum pressure, junctions below the limit, maximum velocity, stagnant links,
peak demand, MSX extremes) are shown with their change versus the baseline.

Typical workflow: run → edit (inspector or bulk edit) → run again → enable
**Difference vs baseline**, or open **Data browser ▸ Scenario compare**.

## Data browser

- A table of nodes or links with result columns (at the current time or
  statistic) followed by all editable properties.
- **Find** by ID, or filter with a **Query** written as a pandas expression,
  e.g. `diameter < 150 and type == 'Pipe'`, `pressure < 25`, or
  `` `msx:CL2` < 0.2 ``. **Select on map** selects the filtered rows; **Export
  CSV** saves them.
- **Time series** plots the selected rows, optionally overlaying all scenarios.
- **Scenario compare**: choose A, B, a variable and a statistic. The per-object
  table is sorted by |Δ|, shown with a summary and an A-vs-B scatter. **Δ on
  map** shows the difference on the map.
- **Distribution**: histogram and cumulative curve of any numeric column.

## Editing the network

- **Inspector** (click one object): every applicable EPANET property with its
  unit. Press Enter or **Apply changes**. Below are the results at the current
  time and a chart of all scenarios for that object.
- **Bulk edit** (several objects, e.g. from a box select with Shift+drag, a
  query, or alert matches): *set*, *multiply* or *add* a value for every
  selected object of a matching type.
- **Junction / Pipe / Move / Delete** tools on the toolbar. A new junction
  copies the elevation of the nearest node. A new pipe gets its length from
  the CRS geometry and median diameter and roughness of the network.
- **Network ▸ Time patterns**: drag the bars to edit multipliers, normalise or
  scale them.
- **Network ▸ Simulation settings**: duration, steps, and quality mode (none,
  age, chemical, or source trace).

After an edit the map is marked *“model edited since run”* until you run
again.

## MSX studio

- **Compounds**: one card per species, covering its pipe and tank kinetics,
  global initial value and sources. Edit in place. **Inject at selected
  node(s)** creates sources from the map selection.
- **＋ Add compound…**: a wizard for name, bulk/wall type, units, kinetics
  (decay, growth, second-order with a partner species, Monod, wall-limited, or
  custom), initial value and injection node. It generates every needed MSX
  row and previews them.
- **Section tables** for every MSX section, with a row form, choice lists and
  an expression palette (species, coefficients, terms, hydraulic variables,
  functions). **Use selected map object** fills node or link IDs.
- **Raw text** with highlighting. Edits there are parsed back into the
  structured views.
- **Live validation**: unknown symbols, unbalanced parentheses, species
  without reactions, sources at nodes missing from the network, and non-ASCII
  characters (typographic dashes that encoding damage leaves in old `.msx`
  files).
- **Templates**: water age, chlorine bulk+wall decay, chlorine–TOC, arsenic
  oxidation/adsorption (from the MSX manual), and bacterial regrowth. These
  are starting points; calibrate the coefficients.
- **▶ Run MSX** (F6) runs hydraulics plus MSX and maps the first species. Use
  the **Species on map** buttons to switch species.

## Projects

**Save** writes `projects/<name>/`: `model.inp` (with edits),
`chemistry.msx`, `assets.gpkg`, `conversion-report.json`, `scenarios/*.npz`
(all results, so comparisons survive restarts) and `project.json` (CRS, run
settings, map style).

## Keyboard and mouse

Wheel zoom · drag/middle-drag pan · click select · Ctrl/Shift+click add ·
Shift+drag box select · right-click menu · Del delete · Esc cancel/clear ·
F5 run · F6 run with MSX · Space play/pause · Ctrl+S save.

## Limits

The engine is OWA EPANET 2.3 through EPyT. DHI-only analyses (water hammer,
VSD/RTC, fire-flow, criticality, flushing) are not computed. See
[ENGINE_CAPABILITIES.md](ENGINE_CAPABILITIES.md). Map drawing uses a Tk
canvas. Above roughly 9,000 objects, only the area around the view is drawn
and the network is redrawn after each pan.
