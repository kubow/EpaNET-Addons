"""Application state and a tiny publish/subscribe bus shared by all panels."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from epanet_addons.crs import ProjectCRS
from epanet_addons.engine import EpanetWrapper
from epanet_addons import msx as msxlib
from epanet_addons import network as netlib

RESULT_LABELS = {
    "pressure": "Pressure", "head": "Head", "demand": "Demand", "quality": "Quality",
    "flow": "Flow", "abs_flow": "Flow (absolute)", "velocity": "Velocity", "headloss": "Unit headloss",
    "status": "Status", "setting": "Setting",
}


def result_unit(var: str, us: bool, flow_units: str) -> str:
    if var.startswith("msx:"):
        return ""
    return {
        "pressure": "psi" if us else "m", "head": "ft" if us else "m", "demand": flow_units,
        "flow": flow_units, "abs_flow": flow_units, "velocity": "ft/s" if us else "m/s",
        "headloss": "per 1000",
    }.get(var, "")


@dataclass
class MapStyle:
    basemap: str = "Esri Light Gray"
    fade: float = 0.25
    node_var: str = "type"  # "type", "none", "prop:<key>", "res:<var>"
    link_var: str = "type"
    stat: str = "At time"
    node_cmap: str = "viridis"
    link_cmap: str = "plasma"
    size_by_value: bool = False
    width_by_value: bool = True
    arrows: bool = True
    labels: bool = False
    delta: bool = False
    fixed_range: dict = field(default_factory=dict)  # kind -> (lo, hi)
    filter_kind: str = "node"
    filter_op: str = ""  # "", "<", ">"
    filter_value: float = 0.0
    overlay: bool = True


class Bus:
    def __init__(self):
        self._subs = defaultdict(list)

    def on(self, event: str, fn):
        self._subs[event].append(fn)

    def emit(self, event: str, **kw):
        for fn in list(self._subs[event]):
            fn(**kw)


class AppState:
    """Everything the UI shares.  Engine access goes through ``wrapper``."""

    def __init__(self):
        self.bus = Bus()
        self.wrapper = EpanetWrapper()
        self.topo: netlib.Topology | None = None
        self.crs = ProjectCRS()
        self.style = MapStyle()
        self.scenarios: list[netlib.Scenario] = []
        self.active: netlib.Scenario | None = None
        self.baseline: netlib.Scenario | None = None
        self.sel_nodes: set[int] = set()
        self.sel_links: set[int] = set()
        self.time_s = 0.0
        self.stale = False
        self.run_settings = netlib.RunSettings()
        self.msx = msxlib.template("Chlorine bulk + wall decay")
        self.msx_path: Path | None = None
        self.source_path: Path | None = None
        self.gpkg_path: Path | None = None
        self.project_name: str | None = None
        self._tables: dict[str, pd.DataFrame] = {}
        self.busy = False

    # -- model -----------------------------------------------------------
    @property
    def loaded(self) -> bool:
        return self.wrapper.network is not None and self.topo is not None

    @property
    def net(self):
        return self.wrapper.network

    def refresh_topology(self, keep_selection: bool = False):
        self.topo = netlib.read_topology(self.net)
        self._tables.clear()
        if not keep_selection:
            self.sel_nodes.clear(); self.sel_links.clear()
        self.bus.emit("model")

    def table(self, kind: str) -> pd.DataFrame:
        if kind not in self._tables:
            self._tables[kind] = netlib.property_table(self.net, self.topo, kind)
        return self._tables[kind]

    def properties_changed(self, structural: bool = False):
        self.stale = True
        if structural:
            self.refresh_topology(keep_selection=False)
        else:
            self._tables.clear()
            self.bus.emit("properties")

    # -- selection / time ------------------------------------------------
    def select(self, nodes=(), links=(), add: bool = False, source: str = ""):
        if not add:
            self.sel_nodes, self.sel_links = set(), set()
        self.sel_nodes |= set(nodes); self.sel_links |= set(links)
        self.bus.emit("selection", source=source)

    def set_time(self, seconds: float):
        self.time_s = float(seconds)
        self.bus.emit("time")

    # -- scenarios -------------------------------------------------------
    def add_scenario(self, scenario: netlib.Scenario):
        self.scenarios.append(scenario)
        if self.active is not None and self.baseline is None:
            self.baseline = self.active
        self.active = scenario
        self.stale = False
        self.bus.emit("scenarios")
        self.bus.emit("results")

    def scenario_names(self) -> list[str]:
        return [s.name for s in self.scenarios]

    def next_scenario_name(self) -> str:
        n = len(self.scenarios) + 1
        names = set(self.scenario_names())
        while f"Run {n}" in names:
            n += 1
        return f"Run {n}"

    # -- values for analytics -------------------------------------------
    def variable_choices(self, kind: str) -> list[tuple[str, str]]:
        """(key, label) pairs for map/browser variable pickers."""
        out = [("type", "Object type"), ("none", "Uniform")]
        if not self.loaded:
            return out
        us = self.topo.us_units
        for f in netlib.FIELDS[kind]:
            if f.kind == "float":
                unit = f.unit(us).replace("flow", self.topo.flow_units)
                out.append((f"prop:{f.key}", f"{f.label}" + (f" [{unit}]" if unit else "")))
        if self.active:
            for var in self.active.results.variables(kind):
                if var in ("status", "setting"):
                    continue
                label = RESULT_LABELS.get(var, var[4:] + " (MSX)" if var.startswith("msx:") else var)
                unit = result_unit(var, us, self.topo.flow_units)
                if var == "quality" and self.active.results.meta.get("quality_label"):
                    label, unit = self.active.results.meta["quality_label"], ""
                out.append((f"res:{var}", f"▸ {label}" + (f" [{unit}]" if unit else "")))
        return out

    def values(self, kind: str, key: str, stat: str | None = None, delta: bool | None = None,
               scenario: netlib.Scenario | None = None) -> np.ndarray | None:
        stat = stat or self.style.stat
        delta = self.style.delta if delta is None else delta
        if key.startswith("prop:"):
            col = key[5:]
            df = self.table(kind)
            return pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float) if col in df else None
        if key.startswith("res:"):
            scen = scenario or self.active
            if scen is None:
                return None
            var = key[4:]
            current = self._aligned(scen, kind, var, stat)
            if current is None:
                return None
            if delta and self.baseline is not None and self.baseline is not scen:
                base = self._aligned(self.baseline, kind, var, stat)
                return None if base is None else current - base
            return current
        return None

    def _aligned(self, scen: netlib.Scenario, kind: str, var: str, stat: str) -> np.ndarray | None:
        """Values ordered like the current topology (scenarios may predate edits)."""
        vals = scen.results.values(kind, var, stat, self.time_s)
        if vals is None:
            return None
        ids = scen.results.node_ids if kind == "node" else scen.results.link_ids
        cur = self.topo.node_ids if kind == "node" else self.topo.link_ids
        if ids == cur:
            return np.asarray(vals, dtype=float)
        lookup = dict(zip(ids, vals))
        return np.array([lookup.get(i, np.nan) for i in cur], dtype=float)

    def series_range(self, kind: str, key: str) -> tuple[float, float] | None:
        """Stable colour range over all time steps (so animations do not flicker)."""
        if key in self.style.fixed_range:
            return self.style.fixed_range[key]
        if key.startswith("res:") and self.active and not self.style.delta and self.style.stat == "At time":
            found = self.active.results.series(kind, key[4:])
            if found is not None:
                data = found[1]
                finite = data[np.isfinite(data)]
                if finite.size:
                    lo, hi = np.percentile(finite, [1, 99])
                    return float(lo), float(hi)
        vals = self.values(kind, key)
        if vals is None:
            return None
        finite = vals[np.isfinite(vals)]
        if not finite.size:
            return None
        if self.style.delta and key.startswith("res:"):
            m = float(np.max(np.abs(finite))) or 1.0
            return -m, m
        return float(np.min(finite)), float(np.max(finite))

    def label_for(self, kind: str, key: str) -> str:
        for k, label in self.variable_choices(kind):
            if k == key:
                return label.lstrip("▸ ")
        return key
