"""UI-neutral network model: topology, editable properties, results, scenarios.

This module sits between :class:`epanet_addons.engine.EpanetWrapper` (which
owns the EPyT engine) and any interface.  It converts the engine state into
plain NumPy/pandas structures, exposes a declarative list of editable object
properties, and keeps simulation results as comparable *scenarios*.
"""
from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

NODE_TYPES = {0: "Junction", 1: "Reservoir", 2: "Tank"}
LINK_TYPES = {0: "CV Pipe", 1: "Pipe", 2: "Pump", 3: "PRV", 4: "PSV", 5: "PBV",
              6: "FCV", 7: "TCV", 8: "GPV", 9: "PCV"}
VALVE_TYPES = {"PRV", "PSV", "PBV", "FCV", "TCV", "GPV", "PCV"}
US_FLOW_UNITS = {"CFS", "GPM", "MGD", "IMGD", "AFD"}


# --------------------------------------------------------------------------
# Topology
# --------------------------------------------------------------------------
@dataclass
class Topology:
    node_ids: list[str]
    node_types: list[str]
    x: np.ndarray
    y: np.ndarray
    link_ids: list[str]
    link_types: list[str]
    link_from: np.ndarray  # 0-based node index
    link_to: np.ndarray
    vertices: dict[int, list[tuple[float, float]]]  # 0-based link → native vertices
    flow_units: str = "LPS"
    synthetic_layout: bool = False

    @property
    def node_index(self) -> dict[str, int]:
        return {nid: i for i, nid in enumerate(self.node_ids)}

    @property
    def link_index(self) -> dict[str, int]:
        return {lid: i for i, lid in enumerate(self.link_ids)}

    @property
    def us_units(self) -> bool:
        return self.flow_units.upper() in US_FLOW_UNITS

    def link_path(self, i: int) -> list[tuple[float, float]]:
        a, b = int(self.link_from[i]), int(self.link_to[i])
        return [(self.x[a], self.y[a]), *self.vertices.get(i, []), (self.x[b], self.y[b])]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in self.node_types + self.link_types:
            out[t] = out.get(t, 0) + 1
        return out


def read_topology(net) -> Topology:
    n_nodes, n_links = int(net.getNodeCount()), int(net.getLinkCount())
    coords = net.getNodeCoordinates()
    xs = np.array([float(coords["x"].get(i, 0.0)) for i in range(1, n_nodes + 1)])
    ys = np.array([float(coords["y"].get(i, 0.0)) for i in range(1, n_nodes + 1)])
    vertices: dict[int, list[tuple[float, float]]] = {}
    try:
        verts = net.getLinkVertices()
        for i in range(1, n_links + 1):
            vx, vy = verts["x"].get(i) or [], verts["y"].get(i) or []
            if len(vx):
                vertices[i - 1] = [(float(a), float(b)) for a, b in zip(vx, vy)]
    except Exception:
        pass
    ends = np.asarray(net.getLinkNodesIndex(), dtype=int).reshape(-1, 2) - 1 if n_links else np.zeros((0, 2), int)
    synthetic = False
    if n_nodes and np.allclose(xs, 0) and np.allclose(ys, 0):
        import networkx as nx  # coordinates absent: create a readable schematic
        graph = nx.Graph(); graph.add_nodes_from(range(n_nodes)); graph.add_edges_from(map(tuple, ends))
        layout = nx.spring_layout(graph, seed=1, scale=1000)
        xs = np.array([layout[i][0] for i in range(n_nodes)]); ys = np.array([layout[i][1] for i in range(n_nodes)])
        vertices, synthetic = {}, True
    node_type_index = list(net.getNodeTypeIndex()) if n_nodes else []
    link_type_index = list(net.getLinkTypeIndex()) if n_links else []
    return Topology(
        node_ids=list(net.getNodeNameID()) if n_nodes else [],
        node_types=[NODE_TYPES.get(int(t), "Junction") for t in np.atleast_1d(node_type_index)],
        x=xs, y=ys,
        link_ids=list(net.getLinkNameID()) if n_links else [],
        link_types=[LINK_TYPES.get(int(t), "Pipe") for t in np.atleast_1d(link_type_index)],
        link_from=ends[:, 0] if n_links else np.zeros(0, int),
        link_to=ends[:, 1] if n_links else np.zeros(0, int),
        vertices=vertices,
        flow_units=str(net.getFlowUnits()),
        synthetic_layout=synthetic,
    )


# --------------------------------------------------------------------------
# Editable properties (EPANET toolkit parameter codes)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    key: str
    label: str
    code: int
    applies: tuple[str, ...]
    kind: str = "float"  # float | pattern | status | curve
    unit_si: str = ""
    unit_us: str = ""
    help: str = ""

    def unit(self, us: bool) -> str:
        return self.unit_us if us else self.unit_si


_ALL_NODES = ("Junction", "Reservoir", "Tank")
_PIPES = ("Pipe", "CV Pipe")
_VALVES = tuple(sorted(VALVE_TYPES))
NODE_FIELDS: list[Field] = [
    Field("elevation", "Elevation / total head", 0, _ALL_NODES, unit_si="m", unit_us="ft",
          help="Junction/tank bottom elevation; reservoir total head."),
    Field("base_demand", "Base demand", 1, ("Junction",), unit_si="flow", unit_us="flow"),
    Field("pattern", "Demand pattern", 2, ("Junction", "Reservoir"), kind="pattern"),
    Field("emitter", "Emitter coefficient", 3, ("Junction",), help="Leakage/sprinkler flow = C·p^γ."),
    Field("init_quality", "Initial quality", 4, _ALL_NODES),
    Field("source_quality", "Source quality", 5, _ALL_NODES),
    Field("tank_level", "Initial level", 8, ("Tank",), unit_si="m", unit_us="ft"),
    Field("min_level", "Minimum level", 20, ("Tank",), unit_si="m", unit_us="ft"),
    Field("max_level", "Maximum level", 21, ("Tank",), unit_si="m", unit_us="ft"),
    Field("tank_diameter", "Tank diameter", 17, ("Tank",), unit_si="m", unit_us="ft"),
    Field("tank_kbulk", "Tank bulk reaction", 23, ("Tank",), unit_si="1/day", unit_us="1/day"),
]
LINK_FIELDS: list[Field] = [
    Field("diameter", "Diameter", 0, _PIPES + _VALVES, unit_si="mm", unit_us="in"),
    Field("length", "Length", 1, _PIPES, unit_si="m", unit_us="ft"),
    Field("roughness", "Roughness", 2, _PIPES, help="Hazen-Williams C, Darcy-Weisbach mm or Chezy-Manning n."),
    Field("minor_loss", "Minor loss coefficient", 3, _PIPES + _VALVES),
    Field("status", "Initial status", 4, _PIPES + ("Pump",) + _VALVES, kind="status"),
    Field("setting", "Initial setting", 5, ("Pump",) + _VALVES,
          help="Pump relative speed; valve pressure/flow/loss setting."),
    Field("kbulk", "Bulk reaction coefficient", 6, _PIPES, unit_si="1/day", unit_us="1/day"),
    Field("kwall", "Wall reaction coefficient", 7, _PIPES),
    Field("pump_pattern", "Speed pattern", 15, ("Pump",), kind="pattern"),
]
FIELDS = {"node": NODE_FIELDS, "link": LINK_FIELDS}


def field_by_key(kind: str, key: str) -> Field:
    for f in FIELDS[kind]:
        if f.key == key:
            return f
    raise KeyError(key)


def _get(net, kind: str, index1: int, code: int) -> float:
    api = net.api
    value = api.ENgetnodevalue(index1, code) if kind == "node" else api.ENgetlinkvalue(index1, code)
    # EPyT returns None on toolkit errors, e.g. source quality of a node without a source
    return float("nan") if value is None else float(value)


def pattern_names(net) -> list[str]:
    try:
        return list(net.getPatternNameID())
    except Exception:
        return []


def get_property(net, topo: Topology, kind: str, i: int, f: Field):
    """Return a display value (float, pattern ID or status string)."""
    raw = _get(net, kind, i + 1, f.code)
    if f.kind == "pattern":
        names = pattern_names(net)
        idx = int(round(raw))
        return names[idx - 1] if 0 < idx <= len(names) else ""
    if f.kind == "status":
        return "OPEN" if raw >= 0.5 else "CLOSED"
    return raw


def set_property(net, kind: str, i: int, f: Field, value) -> None:
    """Write a value given in display form into the engine."""
    api = net.api
    if f.kind == "pattern":
        if value in ("", None):
            raw = 0.0
        else:
            names = pattern_names(net)
            if str(value) not in names:
                raise ValueError(f"Unknown pattern {value!r}")
            raw = float(names.index(str(value)) + 1)
    elif f.kind == "status":
        text = str(value).strip().upper()
        if text not in {"OPEN", "CLOSED", "1", "0"}:
            raise ValueError("Status must be OPEN or CLOSED")
        raw = 1.0 if text in {"OPEN", "1"} else 0.0
    else:
        raw = float(value)
    if kind == "node":
        api.ENsetnodevalue(i + 1, f.code, raw)
    else:
        api.ENsetlinkvalue(i + 1, f.code, raw)


def applicable(kind: str, obj_type: str) -> list[Field]:
    return [f for f in FIELDS[kind] if obj_type in f.applies]


def property_table(net, topo: Topology, kind: str) -> pd.DataFrame:
    """All editable properties of nodes or links as a DataFrame (NaN where n/a)."""
    ids = topo.node_ids if kind == "node" else topo.link_ids
    types = topo.node_types if kind == "node" else topo.link_types
    data: dict[str, list] = {"id": ids, "type": types}
    if kind == "link":
        data["from"] = [topo.node_ids[a] for a in topo.link_from]
        data["to"] = [topo.node_ids[b] for b in topo.link_to]
    names = pattern_names(net)
    for f in FIELDS[kind]:
        column: list = []
        for i, t in enumerate(types):
            if t not in f.applies:
                column.append(np.nan if f.kind == "float" else ""); continue
            raw = _get(net, kind, i + 1, f.code)
            if f.kind == "pattern":
                idx = int(round(raw)); column.append(names[idx - 1] if 0 < idx <= len(names) else "")
            elif f.kind == "status":
                column.append("OPEN" if raw >= 0.5 else "CLOSED")
            else:
                column.append(raw)
        data[f.key] = column
    return pd.DataFrame(data)


def bulk_edit(net, kind: str, indices, f: Field, operation: str, value) -> int:
    """Apply ``set``/``multiply``/``add`` to many objects; returns the count changed."""
    changed = 0
    for i in indices:
        if operation == "set":
            new = value
        else:
            try:
                current = _get(net, kind, i + 1, f.code)
            except Exception:
                continue
            new = current * float(value) if operation == "multiply" else current + float(value)
        try:
            set_property(net, kind, i, f, new)
            changed += 1
        except Exception:
            continue
    return changed


# Structural edits ---------------------------------------------------------
def add_junction(net, node_id: str, x: float, y: float, elevation: float = 0.0, demand: float = 0.0) -> None:
    if node_id in net.getNodeNameID():
        raise ValueError(f"Node {node_id} already exists")
    net.addNodeJunction(node_id, [x, y], elevation, demand)


def add_pipe(net, link_id: str, from_id: str, to_id: str, length: float, diameter: float, roughness: float) -> None:
    if link_id in net.getLinkNameID():
        raise ValueError(f"Link {link_id} already exists")
    if from_id == to_id:
        raise ValueError("A pipe needs two different end nodes")
    net.addLinkPipe(link_id, from_id, to_id, length, diameter, roughness)


def delete_objects(net, node_ids=(), link_ids=()) -> None:
    for lid in link_ids:
        net.deleteLink(lid)
    for nid in node_ids:
        net.deleteNode(nid)


def move_node(net, node_index0: int, x: float, y: float) -> None:
    net.api.ENsetcoord(node_index0 + 1, x, y)


def unique_id(existing, prefix: str) -> str:
    taken = set(existing)
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


# --------------------------------------------------------------------------
# Patterns and simulation options
# --------------------------------------------------------------------------
def get_patterns(net) -> dict[str, list[float]]:
    out = {}
    for i, name in enumerate(pattern_names(net), start=1):
        length = int(net.api.ENgetpatternlen(i))
        out[name] = [float(net.api.ENgetpatternvalue(i, p)) for p in range(1, length + 1)]
    return out


def set_pattern(net, name: str, values: list[float]) -> None:
    names = pattern_names(net)
    if name not in names:
        net.addPattern(name)
        names = pattern_names(net)
    net.setPattern(names.index(name) + 1, list(map(float, values)))


@dataclass
class RunSettings:
    duration_h: float = 24.0
    hydraulic_step_min: float = 60.0
    report_step_min: float = 60.0
    quality: str = "NONE"  # NONE | AGE | CHEM | TRACE
    chem_name: str = "Chlorine"
    chem_units: str = "mg/L"
    trace_node: str = ""

    @classmethod
    def from_network(cls, net) -> "RunSettings":
        q = str(net.getQualityType()).upper()
        return cls(
            duration_h=net.getTimeSimulationDuration() / 3600,
            hydraulic_step_min=net.getTimeHydraulicStep() / 60,
            report_step_min=net.getTimeReportingStep() / 60,
            quality={"NONE": "NONE", "AGE": "AGE", "CHEM": "CHEM", "TRACE": "TRACE"}.get(q, "NONE"),
        )

    def apply(self, net) -> None:
        net.setTimeSimulationDuration(int(self.duration_h * 3600))
        net.setTimeHydraulicStep(max(1, int(self.hydraulic_step_min * 60)))
        net.setTimeReportingStep(max(1, int(self.report_step_min * 60)))
        if self.quality == "AGE":
            net.setQualityType("age")
        elif self.quality == "CHEM":
            net.setQualityType("chem", self.chem_name, self.chem_units)
        elif self.quality == "TRACE" and self.trace_node:
            net.setQualityType("trace", self.trace_node)
        else:
            net.setQualityType("none")

    def summary(self) -> str:
        q = {"CHEM": f"chemical {self.chem_name}", "TRACE": f"trace from {self.trace_node}",
             "AGE": "water age", "NONE": "no quality"}[self.quality]
        return f"{self.duration_h:g} h, Δt {self.hydraulic_step_min:g} min, {q}"


# --------------------------------------------------------------------------
# Results and scenarios
# --------------------------------------------------------------------------
NODE_RESULT_VARS = {"pressure": "Pressure", "head": "Head", "demand": "Demand", "quality": "NodeQuality"}
LINK_RESULT_VARS = {"flow": "Flow", "velocity": "Velocity", "headloss": "HeadLoss",
                    "quality": "LinkQuality", "status": "Status", "setting": "Setting"}
STATISTICS = ("At time", "Minimum", "Maximum", "Mean", "Range")


@dataclass
class Results:
    node_ids: list[str]
    link_ids: list[str]
    time: np.ndarray
    node: dict[str, np.ndarray] = field(default_factory=dict)  # each (T, N)
    link: dict[str, np.ndarray] = field(default_factory=dict)  # each (T, L)
    msx_time: np.ndarray | None = None
    msx_node: dict[str, np.ndarray] = field(default_factory=dict)
    msx_link: dict[str, np.ndarray] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_engine(cls, topo: Topology, computed, msx: dict | None = None, meta: dict | None = None) -> "Results":
        res = cls(list(topo.node_ids), list(topo.link_ids), np.asarray(computed.Time, dtype=float), meta=meta or {})
        for key, attr in NODE_RESULT_VARS.items():
            arr = getattr(computed, attr, None)
            if arr is not None and np.size(arr):
                res.node[key] = np.asarray(arr, dtype=float).reshape(len(res.time), -1)
        for key, attr in LINK_RESULT_VARS.items():
            arr = getattr(computed, attr, None)
            if arr is not None and np.size(arr):
                res.link[key] = np.asarray(arr, dtype=float).reshape(len(res.time), -1)
        if "flow" in res.link:
            res.link["abs_flow"] = np.abs(res.link["flow"])
        if msx:
            res.attach_msx(msx)
        return res

    def attach_msx(self, msx: dict) -> None:
        self.msx_time = np.asarray(msx["time"], dtype=float)
        self.msx_node, self.msx_link = {}, {}
        nq, lq = np.asarray(msx["node_quality"], dtype=float), np.asarray(msx["link_quality"], dtype=float)
        for s, name in enumerate(msx["species"]):
            if nq.ndim == 3:
                self.msx_node[name] = nq[:, :, s].T  # (N, T, S) → (T, N)
            if lq.ndim == 3:
                self.msx_link[name] = lq[:, :, s].T

    # -- access ------------------------------------------------------------
    def variables(self, kind: str) -> list[str]:
        base = list((self.node if kind == "node" else self.link).keys())
        species = self.msx_node if kind == "node" else self.msx_link
        return base + [f"msx:{s}" for s in species]

    def series(self, kind: str, var: str) -> tuple[np.ndarray, np.ndarray] | None:
        if var.startswith("msx:"):
            data = (self.msx_node if kind == "node" else self.msx_link).get(var[4:])
            return (self.msx_time, data) if data is not None else None
        data = (self.node if kind == "node" else self.link).get(var)
        return (self.time, data) if data is not None else None

    def values(self, kind: str, var: str, stat: str = "At time", t_seconds: float = 0.0) -> np.ndarray | None:
        found = self.series(kind, var)
        if found is None:
            return None
        times, data = found
        return reduce_series(times, data, stat, t_seconds)

    @property
    def horizon(self) -> float:
        ends = [self.time[-1] if len(self.time) else 0.0]
        if self.msx_time is not None and len(self.msx_time):
            ends.append(self.msx_time[-1])
        return float(max(ends))

    # -- persistence -------------------------------------------------------
    def save(self, path: Path) -> None:
        arrays = {"time": self.time}
        arrays.update({f"node__{k}": v for k, v in self.node.items()})
        arrays.update({f"link__{k}": v for k, v in self.link.items()})
        if self.msx_time is not None:
            arrays["msx_time"] = self.msx_time
            arrays.update({f"msxnode__{k}": v for k, v in self.msx_node.items()})
            arrays.update({f"msxlink__{k}": v for k, v in self.msx_link.items()})
        np.savez_compressed(path, **arrays,
                            _ids=np.array(json.dumps({"node": self.node_ids, "link": self.link_ids, "meta": self.meta})))

    @classmethod
    def load(cls, path: Path) -> "Results":
        with np.load(path, allow_pickle=False) as data:
            ids = json.loads(str(data["_ids"]))
            res = cls(ids["node"], ids["link"], data["time"], meta=ids.get("meta", {}))
            for key in data.files:
                prefix, _, name = key.partition("__")
                target = {"node": res.node, "link": res.link, "msxnode": res.msx_node, "msxlink": res.msx_link}.get(prefix)
                if target is not None and name:
                    target[name] = data[key]
            if "msx_time" in data.files:
                res.msx_time = data["msx_time"]
        return res


def time_index(times: np.ndarray, t_seconds: float) -> int:
    if times is None or not len(times):
        return 0
    idx = int(np.searchsorted(times, t_seconds, side="right") - 1)
    return min(max(idx, 0), len(times) - 1)


def reduce_series(times: np.ndarray, data: np.ndarray, stat: str, t_seconds: float) -> np.ndarray:
    if stat == "At time":
        return data[time_index(times, t_seconds)]
    if stat == "Minimum":
        return data.min(axis=0)
    if stat == "Maximum":
        return data.max(axis=0)
    if stat == "Mean":
        return data.mean(axis=0)
    if stat == "Range":
        return data.max(axis=0) - data.min(axis=0)
    raise ValueError(stat)


@dataclass
class Scenario:
    name: str
    results: Results
    settings: str = ""
    note: str = ""
    created: float = field(default_factory=_time.time)


def compare(a: Scenario, b: Scenario, kind: str, var: str, stat: str, t_seconds: float) -> pd.DataFrame:
    """Per-object comparison of two scenarios (aligned by object ID)."""
    va, vb = a.results.values(kind, var, stat, t_seconds), b.results.values(kind, var, stat, t_seconds)
    if va is None or vb is None:
        raise ValueError(f"Variable {var} is not available in both scenarios")
    ids_a = a.results.node_ids if kind == "node" else a.results.link_ids
    ids_b = b.results.node_ids if kind == "node" else b.results.link_ids
    fa = pd.Series(va, index=ids_a, name=a.name); fb = pd.Series(vb, index=ids_b, name=b.name)
    df = pd.concat([fa, fb], axis=1, join="inner")
    df.columns = ["A", "B"]
    df["delta"] = df["B"] - df["A"]
    with np.errstate(divide="ignore", invalid="ignore"):
        df["delta_pct"] = np.where(np.abs(df["A"]) > 1e-12, df["delta"] / np.abs(df["A"]) * 100, np.nan)
    return df.reset_index(names="id")


def kpis(scenario: Scenario, topo: Topology, pressure_limit: float = 20.0, velocity_limit: float = 2.0) -> dict[str, float]:
    """Headline indicators used by dashboards and scenario comparison."""
    r = scenario.results
    out: dict[str, float] = {}
    junction = np.array([t == "Junction" for t in topo.node_types])
    if "pressure" in r.node and junction.any() and r.node["pressure"].shape[1] == len(junction):
        p = r.node["pressure"][:, junction]
        out["Min pressure"] = float(p.min())
        out["Mean pressure"] = float(p.mean())
        out[f"Junctions < {pressure_limit:g} (worst step)"] = float((p < pressure_limit).sum(axis=1).max())
        out["Negative-pressure junctions"] = float((p.min(axis=0) < 0).sum())
    if "velocity" in r.link:
        v = np.abs(r.link["velocity"])
        out["Max velocity"] = float(v.max())
        out[f"Links > {velocity_limit:g} velocity"] = float((v.max(axis=0) > velocity_limit).sum())
        out["Stagnant links (<0.01 always)"] = float((v.max(axis=0) < 0.01).sum())
    if "demand" in r.node and junction.any() and r.node["demand"].shape[1] == len(junction):
        out["Peak total demand"] = float(r.node["demand"][:, junction].sum(axis=1).max())
    if "quality" in r.node and np.nanmax(np.abs(r.node["quality"])) > 0:
        out["Max node quality"] = float(r.node["quality"].max())
    for name, data in r.msx_node.items():
        out[f"MSX {name} max"] = float(np.nanmax(data))
        out[f"MSX {name} min (end)"] = float(np.nanmin(data[-1]))
    return out


Listener = Callable[..., None]
