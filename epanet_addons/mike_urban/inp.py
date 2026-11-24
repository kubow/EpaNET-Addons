"""Generate a reviewable EPANET INP model from MIKE URBAN water tables."""
from __future__ import annotations
import argparse
import json
import struct
from math import hypot
from pathlib import Path
from ..geo import identify_coordinates
from .importer import _mdbtools_rows

TIME_UNITS = {0: "DAYS", 1: "HOURS", 2: "MINUTES", 3: "SECONDS"}
HEADLOSS = {0: "D-W", 1: "H-W", 2: "C-M"}
FLOW_UNITS = {5: "LPS", 4: "LPM", 3: "MLD", 2: "CMH", 1: "CMD", 0: "CFS"}
VALVES = {1: "PRV", 2: "PSV", 3: "PBV", 4: "FCV", 5: "TCV", 6: "GPV"}

def _number(value, default=0.0):
    return default if value in (None, "") else float(value)

def _point(shape):
    if not shape or len(shape) < 20 or struct.unpack_from("<I", shape)[0] != 1:
        return None
    return struct.unpack_from("<dd", shape, 4)

def _line_ends(shape):
    """Return first/last XY from an ESRI Personal GDB polyline."""
    if not shape or len(shape) < 60 or struct.unpack_from("<I", shape)[0] != 3:
        return None
    parts, count = struct.unpack_from("<II", shape, 36)
    offset = 44 + 4 * parts
    if count < 2 or len(shape) < offset + count * 16:
        return None
    values = struct.unpack_from(f"<{count * 2}d", shape, offset)
    return (values[0], values[1]), (values[-2], values[-1])

def _line_points(shape):
    """Return all points from a single/multipart ESRI Personal GDB polyline."""
    if not shape or len(shape) < 60 or struct.unpack_from("<I", shape)[0] != 3:
        return ()
    parts, count = struct.unpack_from("<II", shape, 36)
    offset = 44 + 4 * parts
    if count < 2 or len(shape) < offset + count * 16:
        return ()
    values = struct.unpack_from(f"<{count * 2}d", shape, offset)
    return tuple(zip(values[::2], values[1::2]))

def _largest_component(nodes, edges):
    graph = {node: set() for node in nodes}
    for left, right in edges:
        if left in graph and right in graph:
            graph[left].add(right); graph[right].add(left)
    components = []
    while graph:
        start = next(iter(graph)); stack = [start]; component = set()
        while stack:
            node = stack.pop()
            if node in component: continue
            component.add(node); stack.extend(graph[node] - component)
        for node in component: graph.pop(node, None)
        components.append(component)
    return max(components, key=len), sorted((sorted(c) for c in components if c), key=len, reverse=True)

def mdb_to_inp(source: Path, destination: Path) -> dict:
    """Write an executable first-pass INP and a JSON conversion report.

    Unsupported pump curves are omitted rather than replaced with fabricated
    hydraulics. The report lists every omission for engineer review.
    """
    tables = {name: _mdbtools_rows(source, name) for name in (
        "mw_Junction", "mw_Tank", "mw_Pipe", "mw_Valve", "mw_Pump",
        "mw_MDemand", "mw_DPPattern", "mw_DPPatternD", "mw_Time",
        "mw_Project", "mw_Global", "mw_Energy", "mw_Report", "mw_Rule", "mw_Loss",
        "mw_Curve", "mw_CurveD", "mw_Control", "mw_Quality", "mw_Reaction", "mw_Source")}
    nodes = {r["MUID"] for n in ("mw_Junction", "mw_Tank") for r in tables[n] if r.get("MUID")}
    node_points = {r["MUID"]: _point(r.get("SHAPE")) for n in ("mw_Junction", "mw_Tank") for r in tables[n] if r.get("MUID") and _point(r.get("SHAPE"))}
    virtual_nodes = {}
    # MIKE creates InsertSegment_* junctions while splitting a link for a pump
    # or valve. Some MDB backups omit their feature rows, but retain link ends.
    for table in ("mw_Pipe", "mw_Pump", "mw_Valve"):
        for row in tables[table]:
            ends = _line_ends(row.get("SHAPE"))
            if not ends: continue
            for endpoint, xy in zip((row.get("FROMNODE"), row.get("TONODE")), ends):
                if endpoint and endpoint not in nodes:
                    virtual_nodes.setdefault(endpoint, xy)
    nodes.update(virtual_nodes)
    node_points.update(virtual_nodes)
    inferred_pipe_ends = {}
    for row in tables["mw_Pipe"]:
        if row.get("FROMNODE") and row.get("TONODE"): continue
        ends = _line_ends(row.get("SHAPE"))
        if not ends: continue
        inferred = []
        for point in ends:
            distance, node = min((hypot(point[0] - xy[0], point[1] - xy[1]), node_id) for node_id, xy in node_points.items())
            inferred.append(node if distance <= 0.05 else None)
        if all(inferred): inferred_pipe_ends[row.get("MUID")] = tuple(inferred)
    edges = []
    for table in ("mw_Pipe", "mw_Pump", "mw_Valve"):
        for row in tables[table]:
            left, right = row.get("FROMNODE"), row.get("TONODE")
            if table == "mw_Pipe" and (not left or not right): left, right = inferred_pipe_ends.get(row.get("MUID"), (left, right))
            if left and right: edges.append((left, right))
    calculation_nodes, components = _largest_component(nodes, edges)
    excluded_nodes = nodes - calculation_nodes
    source_crs = identify_coordinates(node_points.values())
    report = {"source": str(source), "source_crs": {"epsg": source_crs.epsg, "name": source_crs.name, "reason": source_crs.reason}, "omitted_pumps": [], "omitted_links": [], "inferred_pipe_endpoints": inferred_pipe_ends, "excluded_components": components[1:], "zero_length_pipes": [], "virtual_junctions": sorted(virtual_nodes), "omitted_rules": [], "untranslated_controls": [], "constant_patterns": [], "unknown_valves": [], "unknown_sources": [], "loss_catalog_entries": len(tables["mw_Loss"]), "type_counts": {}}
    time, project = tables["mw_Time"][0], tables["mw_Project"][0]
    curve_points = {}
    for row in sorted(tables["mw_CurveD"], key=lambda item: (str(item.get("CurveID")), _number(item.get("Sqn")))):
        if row.get("CurveID") and row.get("Val1") is not None and row.get("Val2") is not None:
            curve_points.setdefault(row["CurveID"], []).append((_number(row["Val1"]), _number(row["Val2"])))
    lines = ["[TITLE]", f"; Generated from {source.name}; review conversion-report.json", "", "[JUNCTIONS]"]
    for r in tables["mw_Junction"]:
        if r.get("MUID") in calculation_nodes and r.get("Enabled", 1): lines.append(f"{r['MUID']} {_number(r.get('Elev')):.6f}")
    for node_id in virtual_nodes:
        # Elevation cannot be recovered safely from link geometry alone.
        lines.append(f"{node_id} 0.000000 ; reconstructed MIKE insert segment")
    # Only patterns that actually have multipliers can be referenced; others become constant (1.0).
    valued_patterns = {r["PatternID"] for r in tables["mw_DPPatternD"] if r.get("PatternID")}
    lines += ["", "[RESERVOIRS]"]
    for r in tables["mw_Tank"]:
        if r.get("MUID") in calculation_nodes and r.get("Enabled", 1) and int(_number(r.get("HGLTypeNo"), 1)) == 0:
            head_pattern = f" {r['PatternID']}" if r.get("PatternID") else ""
            if r.get("PatternID") and r["PatternID"] not in valued_patterns:
                report["constant_patterns"].append(r["PatternID"])
            lines.append(f"{r['MUID']} {_number(r.get('HGL', r.get('Elev'))):.6f}{head_pattern}")
    lines += ["", "[TANKS]"]
    for r in tables["mw_Tank"]:
        if r.get("MUID") in calculation_nodes and r.get("Enabled", 1) and int(_number(r.get("HGLTypeNo"), 1)) != 0:
            volume_curve = r.get("VolCurveID") if r.get("VolCurveID") in curve_points else None
            lines.append(f"{r['MUID']} {_number(r.get('Elev')):.6f} {_number(r.get('InitLevel')):.6f} {_number(r.get('MinLevel')):.6f} {_number(r.get('MaxLevel')):.6f} {_number(r.get('Diameter')):.6f} {_number(r.get('MinVol')):.6f}" + (f" {volume_curve}" if volume_curve else ""))
    lines += ["", "[PIPES]"]
    for r in tables["mw_Pipe"]:
        if not r.get("Enabled", 1): continue
        a, b = r.get("FROMNODE"), r.get("TONODE")
        if not a or not b:
            a, b = inferred_pipe_ends.get(r.get("MUID"), (a, b))
        if not r.get("MUID") or a not in calculation_nodes or b not in calculation_nodes:
            report["omitted_links"].append({"id": r.get("MUID"), "reason": "endpoint missing", "from": a, "to": b}); continue
        length = _number(r.get("L")) or _number(r.get("SHAPE_Length"))
        if length <= 0:
            report["zero_length_pipes"].append(r["MUID"])
            length = 0.001
        status = "CV" if int(_number(r.get("CVNo"))) else ("CLOSED" if int(_number(r.get("StatusNo"))) else "OPEN")
        lines.append(f"{r['MUID']} {a} {b} {length:.6f} {_number(r.get('Diameter')):.6f} {_number(r.get('RCoeff'), 1):.6f} {_number(r.get('LCoeff')):.6f} {status}")
    lines += ["", "[VALVES]"]
    for r in tables["mw_Valve"]:
        a, b, kind = r.get("FROMNODE"), r.get("TONODE"), VALVES.get(int(_number(r.get("TypeNo"), -1)))
        if a not in calculation_nodes or b not in calculation_nodes: report["omitted_links"].append({"id": r.get("MUID"), "reason": "valve endpoint missing"}); continue
        if not kind: report["unknown_valves"].append({"id": r.get("MUID"), "type": r.get("TypeNo")}); continue
        setting = r.get("ValveCurveID") if kind == "GPV" and r.get("ValveCurveID") in curve_points else _number(r.get("Setting"))
        lines.append(f"{r['MUID']} {a} {b} {_number(r.get('Diameter')):.6f} {kind} {setting} {_number(r.get('LossCoeff', r.get('LCoeff'))):.6f}")
    lines += ["", "[PUMPS]"]
    pump_curves = []
    for r in tables["mw_Pump"]:
        a, b, pump_id = r.get("FROMNODE"), r.get("TONODE"), r.get("MUID")
        if not pump_id or a not in calculation_nodes or b not in calculation_nodes:
            report["omitted_pumps"].append({"id": pump_id, "reason": "endpoint missing"}); continue
        curve = r.get("QHCurveID")
        if curve in curve_points:
            speed = _number(r.get("P_Speed"), 1)
            lines.append(f"{pump_id} {a} {b} HEAD {curve} SPEED {speed:.6g}")
            continue
        # MIKE's common 1-point Q-H representation stores design head/flow in
        # Par2/Par3. EPANET derives the remaining curve from this design point.
        flow, head = _number(r.get("Par3")), _number(r.get("Par2"))
        if flow <= 0 or head <= 0:
            report["omitted_pumps"].append({"id": pump_id, "reason": "missing positive Q-H point", "type": r.get("TypeNo")}); continue
        curve = f"QH_{pump_id}"
        speed = _number(r.get("P_Speed"), 1)
        lines.append(f"{pump_id} {a} {b} HEAD {curve} SPEED {speed:.6g}")
        pump_curves.append((curve, flow, head))
    patterns = {r.get("MUID") for r in tables["mw_DPPattern"]} & valued_patterns
    lines += ["", "[DEMANDS]"]
    for r in tables["mw_MDemand"]:
        node, pattern = r.get("JunctionID"), r.get("PatternID")
        if node not in calculation_nodes: continue
        if pattern and pattern not in patterns:
            report["constant_patterns"].append(pattern)
        lines.append(f"{node} {_number(r.get('Demand')):.6f}" + (f" {pattern}" if pattern else ""))
    lines += ["", "[PATTERNS]"]
    # Orphan pattern values (no PatternID) occur in older MIKE URBAN archives; skip and report them.
    orphan_values = [r for r in tables["mw_DPPatternD"] if not r.get("PatternID")]
    if orphan_values:
        report["orphan_pattern_values"] = len(orphan_values)
    for r in sorted((r for r in tables["mw_DPPatternD"] if r.get("PatternID")),
                    key=lambda x: (str(x["PatternID"]), _number(x.get("Sqn")))):
        lines.append(f"{r['PatternID']} {_number(r.get('DPValue')):.9g}")
    for pattern in sorted(set(report["constant_patterns"])):
        lines.append(f"{pattern} 1")
    lines += ["", "[CURVES]"]
    for curve, points in curve_points.items():
        for x, y in points:
            lines.append(f"{curve} {x:.9g} {y:.9g}")
    for curve, flow, head in pump_curves:
        lines.append(f"{curve} {flow:.9g} {head:.9g}")
    lines += ["", "[MIXING]"]
    mixing = {0: "MIXED", 1: "2COMP", 2: "FIFO", 3: "LIFO"}
    for tank in tables["mw_Tank"]:
        if tank.get("MUID") in calculation_nodes and int(_number(tank.get("HGLTypeNo"), 1)) != 0:
            lines.append(f"{tank['MUID']} {mixing.get(int(_number(tank.get('MixModelNo'))), 'MIXED')}")
    lines += ["", "[REACTIONS]", f"ORDER BULK {_number(tables['mw_Global'][0].get('OrderBulk'), 1):.6f}", f"ORDER WALL {_number(tables['mw_Global'][0].get('OrderWall'), 1):.6f}", f"GLOBAL BULK {_number(tables['mw_Global'][0].get('BulkCoeff')):.6f}", f"GLOBAL WALL {_number(tables['mw_Global'][0].get('WallCoeff')):.6f}"]
    for pipe in tables["mw_Pipe"]:
        if pipe.get("FROMNODE") not in calculation_nodes or pipe.get("TONODE") not in calculation_nodes: continue
        if pipe.get("MUID") and _number(pipe.get("Bulk_Coeff")):
            lines.append(f"BULK {pipe['MUID']} {_number(pipe['Bulk_Coeff']):.6f}")
        if pipe.get("MUID") and _number(pipe.get("Wall_Coeff")):
            lines.append(f"WALL {pipe['MUID']} {_number(pipe['Wall_Coeff']):.6f}")
    for tank in tables["mw_Tank"]:
        if tank.get("MUID") in calculation_nodes and int(_number(tank.get("HGLTypeNo"), 1)) != 0 and _number(tank.get("ReactionCoefficient")):
            lines.append(f"TANK {tank['MUID']} {_number(tank['ReactionCoefficient']):.6f}")
    reaction_kinds = {0: "BULK", 1: "WALL", 2: "TANK"}
    emitted_reactions = set()
    for reaction in tables["mw_Reaction"]:
        kind = reaction_kinds.get(int(_number(reaction.get("RTypeNo"), -1)))
        if kind is None:
            continue
        identifiers = (reaction.get("Node1ID"), reaction.get("Node2ID")) if kind == "TANK" else (reaction.get("Pipe1ID"), reaction.get("Pipe2ID"))
        for identifier in identifiers:
            key = (kind, identifier)
            if identifier and key not in emitted_reactions:
                lines.append(f"{kind} {identifier} {_number(reaction.get('Coeff')):.6f}")
                emitted_reactions.add(key)
    lines += ["", "[ENERGY]", f"GLOBAL EFFIC {_number(tables['mw_Energy'][0].get('Effic'), 75):.6f}"]
    energy = tables["mw_Energy"][0]
    if energy.get("Price") is not None: lines.append(f"GLOBAL PRICE {_number(energy['Price']):.6f}")
    if energy.get("PricePatID"): lines.append(f"GLOBAL PATTERN {energy['PricePatID']}")
    if energy.get("DemandCharge") is not None: lines.append(f"DEMAND CHARGE {_number(energy['DemandCharge']):.6f}")
    emitted_pumps = {row.get("MUID") for row in tables["mw_Pump"] if row.get("FROMNODE") in calculation_nodes and row.get("TONODE") in calculation_nodes and (row.get("QHCurveID") in curve_points or (_number(row.get("Par3")) > 0 and _number(row.get("Par2")) > 0))}
    for pump in tables["mw_Pump"]:
        if pump.get("MUID") not in emitted_pumps: continue
        if pump.get("EfCurveID") in curve_points: lines.append(f"PUMP {pump['MUID']} EFFIC {pump['EfCurveID']}")
        if pump.get("EPrice") is not None: lines.append(f"PUMP {pump['MUID']} PRICE {_number(pump['EPrice']):.6f}")
        if pump.get("EPatternID"): lines.append(f"PUMP {pump['MUID']} PATTERN {pump['EPatternID']}")
    lines += ["", "[TIMES]"]
    for field, label, unit in (("Duration", "DURATION", "Dur_Units"), ("Hydr_Timestep", "HYDRAULIC TIMESTEP", "Hyd_Units"), ("Qual_Timestep", "QUALITY TIMESTEP", "Qua_Units"), ("Pattern_Timestep", "PATTERN TIMESTEP", "Pat_Units"), ("Report_Timestep", "REPORT TIMESTEP", "Res_Units"), ("Report_Start", "REPORT START", "Res_Units")):
        lines.append(f"{label} {_number(time.get(field)):.6g} {TIME_UNITS.get(int(_number(time.get(unit))), 'HOURS')}")
    statistics = {0: "NONE", 1: "MINIMUM", 2: "MAXIMUM", 3: "AVERAGE"}.get(int(_number(time.get("StatisticsNo"))), "NONE")
    lines += [f"START CLOCKTIME {int(_number(time.get('ClockHRS')))}:{int(_number(time.get('ClockMIN'))):02d} AM", f"STATISTIC {statistics}", "", "[REPORT]"]
    lines += [r["Condition"] for r in tables["mw_Report"] if r.get("Condition")]
    quality_rows = [row for row in tables["mw_Quality"] if row.get("Node1ID") in calculation_nodes]
    source_rows = [row for row in tables["mw_Source"] if row.get("NodeID") in calculation_nodes]
    quality_modes = {0: "NONE", 1: "CHEMICAL Quality", 2: "AGE", 3: f"TRACE {project['TraceNode']}" if project.get("TraceNode") else "NONE"}
    quality_mode = quality_modes.get(int(_number(project.get("QualityNo"))), "NONE")
    if source_rows and quality_mode == "NONE": quality_mode = "CHEMICAL Quality"
    lines += ["", "[OPTIONS]", f"UNITS {FLOW_UNITS.get(int(_number(project.get('UnitsNo'))), 'LPS')}", f"HEADLOSS {HEADLOSS.get(int(_number(project.get('HeadlossNo'))), 'D-W')}", f"TRIALS {int(_number(project.get('Trials'), 40))}", f"TOLERANCE {_number(project.get('Tolerance'), .01):.9g}", f"ACCURACY {_number(project.get('Accuracy'), .001):.9g}", f"EMITTER EXPONENT {_number(project.get('Emitter'), .5):.9g}", f"VISCOSITY {_number(project.get('Viscosity'), 1):.9g}", f"DIFFUSIVITY {_number(project.get('Diffusivity'), 1):.9g}", f"SPECIFIC GRAVITY {_number(project.get('Gravity'), 1):.9g}", f"UNBALANCED {'CONTINUE' if int(_number(project.get('UnbalancedNo'))) else 'STOP'}", f"QUALITY {quality_mode}", "", "[EMITTERS]"]
    for junction in tables["mw_Junction"]:
        coefficient = _number(junction.get("EM_FlowCoeff"))
        if junction.get("MUID") in calculation_nodes and coefficient:
            lines.append(f"{junction['MUID']} {coefficient:.9g}")
    lines += ["", "[QUALITY]"]
    for row in quality_rows:
        lines.append(f"{row['Node1ID']} {_number(row.get('Quality')):.9g}")
    lines += ["", "[SOURCES]"]
    source_types = {0: "CONCEN", 1: "MASS", 2: "FLOWPACED", 3: "SETPOINT"}
    for row in source_rows:
        source_type = source_types.get(int(_number(row.get("SrcTypeNo"), -1)))
        if source_type is None:
            report["unknown_sources"].append({"node": row.get("NodeID"), "type": row.get("SrcTypeNo")})
            continue
        pattern = f" {row['PatternID']}" if row.get("PatternID") else ""
        lines.append(f"{row['NodeID']} {source_type} {_number(row.get('Conc')):.9g}{pattern}")
    lines += ["", "[RULES]"]
    for rule in tables["mw_Rule"]:
        if rule.get("Condition"):
            if any(node in rule["Condition"] for node in excluded_nodes):
                report["omitted_rules"].append({"id": rule.get("MUID"), "reason": "references excluded component"})
            else:
                lines += [f"RULE {rule.get('MUID')}", rule["Condition"]]
    lines += ["", "[STATUS]"]
    for table in ("mw_Pump", "mw_Valve"):
        for row in tables[table]:
            if row.get("FROMNODE") in calculation_nodes and row.get("TONODE") in calculation_nodes and row.get("MUID") and int(_number(row.get("StatusNo"))):
                lines.append(f"{row['MUID']} CLOSED")
    lines += ["", "[CONTROLS]"]
    for control in tables["mw_Control"]:
        link_id = control.get("PipeID")
        setting = {0: "OPEN", 1: "CLOSED"}.get(int(_number(control.get("SettingNo"), -1)))
        if int(_number(control.get("SettingNo"), -1)) == 2:
            setting = f"{_number(control.get('SetValue')):.9g}"
        condition = int(_number(control.get("ConditionNo"), -1))
        if not link_id or setting is None:
            report["untranslated_controls"].append({key: value for key, value in control.items() if key != "SHAPE"})
            continue
        if condition in (0, 1) and control.get("ControlJunctionID"):
            direction = "BELOW" if condition == 0 else "ABOVE"
            lines.append(f"LINK {link_id} {setting} IF NODE {control['ControlJunctionID']} {direction} {_number(control.get('CLevel')):.9g}")
        elif condition == 2:
            factor = {0: 1 / 3600, 1: 1 / 60, 2: 1, 3: 24}.get(int(_number(control.get("TimeUnitsNo"))), None)
            if factor is None:
                report["untranslated_controls"].append({key: value for key, value in control.items() if key != "SHAPE"})
            else:
                lines.append(f"LINK {link_id} {setting} AT TIME {_number(control.get('TValue')) * factor:.9g}")
        elif condition == 3:
            suffix = "PM" if int(_number(control.get("ClockTimeUnitsNo"))) else "AM"
            lines.append(f"LINK {link_id} {setting} AT CLOCKTIME {int(_number(control.get('ClockTimeHrs')))}:{int(_number(control.get('ClockTimeMin'))):02d} {suffix}")
        else:
            report["untranslated_controls"].append({key: value for key, value in control.items() if key != "SHAPE"})
    lines += ["", "[COORDINATES]"]
    for table in ("mw_Junction", "mw_Tank"):
        for row in tables[table]:
            point = _point(row.get("SHAPE"))
            if row.get("MUID") in calculation_nodes and point:
                lines.append(f"{row['MUID']} {point[0]:.6f} {point[1]:.6f}")
    for node_id, point in virtual_nodes.items():
        lines.append(f"{node_id} {point[0]:.6f} {point[1]:.6f}")
    lines += ["", "[VERTICES]"]
    for table in ("mw_Pipe", "mw_Pump", "mw_Valve"):
        for row in tables[table]:
            link_id = row.get("MUID")
            if not link_id or row.get("FROMNODE") not in calculation_nodes or row.get("TONODE") not in calculation_nodes:
                continue
            for x, y in _line_points(row.get("SHAPE"))[1:-1]:
                lines.append(f"{link_id} {x:.6f} {y:.6f}")
    lines += ["", "[END]"]
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["constant_patterns"] = sorted(set(report["constant_patterns"])); report["counts"] = {name: len(rows) for name, rows in tables.items()}
    for table in ("mw_Tank", "mw_Valve", "mw_Pump", "mw_Pipe"):
        report["type_counts"][table] = {field: sorted({str(row.get(field)) for row in tables[table] if field in row}) for field in ("TypeNo", "StatusNo", "StateNo", "MixModelNo", "CVNo")}
    destination.with_name("conversion-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("source", type=Path); parser.add_argument("destination", type=Path); args = parser.parse_args()
    print(mdb_to_inp(args.source, args.destination))
