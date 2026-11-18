# Calculation-engine capabilities

This repository has two distinct responsibilities:

1. translate a MIKE URBAN Classic water-model `.mdb` into a portable
   GeoPackage and a standard EPANET `.inp`; and
2. run the resulting model with the locally installed EPANET engine.

They must not be confused. A successful spatial import does not prove that a
calculation model is complete, and a successful EPANET run does not enable
MIKE-only analyses.

## What works locally today

The default local engine is OWA EPANET through EPyT. The workbench can open an
EPANET INP, edit junction/link parameters, run hydraulic calculations, run
EPANET-MSX chemistry, show result attributes, and save a local project.

The MIKE URBAN calculation import writes standard EPANET constructs when the
corresponding `mw_*` rows exist:

| Model construct | MDB source | Status |
|---|---|---|
| Junctions, elevations, emitters | `mw_Junction` | Translated |
| Reservoirs and tanks, mixing, volume curves | `mw_Tank`, `mw_Curve*` | Translated |
| Pipes, minor loss, check valves, geometry vertices | `mw_Pipe` | Translated |
| PRV, PSV, PBV, FCV, TCV, GPV | `mw_Valve`, `mw_Curve*` | Translated where the EPANET equivalent exists |
| Pumps, Q-H curves, efficiency and energy settings | `mw_Pump`, `mw_Curve*`, `mw_Energy` | Translated where standard EPANET supports them |
| Demands, patterns, times and solver options | `mw_MDemand`, `mw_DPPattern*`, `mw_Time`, `mw_Project` | Translated |
| Reactions, initial quality and sources | `mw_Global`, `mw_Reaction`, `mw_Quality`, `mw_Source` | Translated |
| Simple controls and rules | `mw_Control`, `mw_Rule` | Translated for standard EPANET conditions/rules |
| Coordinates and spatial assets | geometry blobs / `mw_*` features | Preserved in GeoPackage; EPSG:5514 is detected for the supplied Czech model |

Every conversion produces `conversion-report.json`. Treat it as a mandatory
review item: `omitted_*`, `unknown_*`, `untranslated_controls`, inferred
endpoints, virtual junctions, and excluded components describe differences
between the source and executable model. The current importer runs the largest
connected component only, so excluded components require engineering review.

## Capability matrix

| Analysis or feature | Standard local EPANET / EPyT | This workbench | How to overcome the gap |
|---|---|---|---|
| Hydraulic EPS | Yes | Yes | — |
| Standard quality, age, source tracing | Yes | Imported when represented by standard EPANET fields | Review source-specific quality settings in the report |
| EPANET-MSX multi-species chemistry | Yes, via EPyT MSX support | Yes, with an `.msx` file | Supply a validated MSX chemistry file |
| Standard pump speed, patterns, controls and rules | Yes | Yes | — |
| Pressure-dependent demand / leakage | Engine support depends on installed OWA EPANET version | Not exposed in the workbench UI yet | Add a dedicated UI/API workflow after pinning EPANET 2.3+ |
| DHI VSD pump control | No automatic set-point controller | Not run locally | Use licensed DHI muEPANET with `[VSD_PUMPS]` |
| DHI RTC/PID valve and pump control | No | Not run locally | Use licensed DHI muEPANET with `[RTC]` |
| Fire-flow / available-flow analysis | Can be constructed as ordinary scenarios, but no MIKE fire-flow module | Not exposed | Use DHI muEPANET fire-flow API or implement a transparent batch scenario workflow |
| Network capacity and pipe criticality | No built-in equivalent | Not exposed | Use DHI muEPANET capacity/criticality modules; export results back to GeoPackage |
| Flushing / UDF | No | Not exposed | Use DHI muEPANET flushing module |
| Water hammer / transient pressure | No | Not exposed | Run the dedicated MIKE Water Hammer workflow; do not approximate it with EPS results |
| Reliability / outage analysis | No built-in MIKE-equivalent module | Not exposed | Use the MIKE reliability workflow or a separately validated scenario-analysis layer |

OWA EPANET 2.3 adds, among other items, pressure-dependent demand, leakage,
and a positional control valve; it is still not DHI muEPANET. See the
[OWA release notes](https://github.com/OpenWaterAnalytics/EPANET/releases).
DHI documents its VSD, RTC, fire-flow, capacity, criticality and flushing
extensions in the [muEPANET API documentation](https://docs.mikepoweredbydhi.com/engine_libraries/mu_epanet/MU_EPANET_API_Documentation/).

## Recommended operating modes

### Portable, reproducible model

Use the GeoPackage plus standard EPANET INP and MSX file. This is the default
workbench mode and has no DHI runtime dependency. It is the correct choice for
ordinary hydraulic and quality studies.

### DHI-enhanced calculation

Keep the original MDB and use a licensed DHI muEPANET installation for VSD,
RTC, fire-flow, capacity, criticality, and flushing. A future integration
should invoke that engine through a small local adapter and store its settings,
SUM/RES outputs, and result layers in the project directory. It must detect
the engine explicitly; standard EPANET must never be asked to parse DHI-only
INP sections.

### Water hammer or reliability study

Keep the converted EPANET model as the hydraulic baseline, but run the
specialised MIKE workflow for the final analysis. Record the selected scenario,
engine version, and result files alongside the local project so the study can
be reproduced.

## Acceptance checklist

Before approving a converted model:

1. Inspect `conversion-report.json`; resolve every non-empty omission or
   unknown list.
2. Compare node/link/pump/valve/tank counts and total demand against MIKE.
3. Run a comparable steady-state or EPS time step in both engines and compare
   pressure, flow, tank level, pump status, and energy at selected assets.
4. For DHI-only analyses, run the DHI engine and save its native inputs and
   outputs; do not claim equivalence from an ordinary EPANET run.
