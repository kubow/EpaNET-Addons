"""Left panel: basemap, analytics layers, highlight filters and scenarios."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from epanet_addons import network as netlib
from . import tiles as tl
from .mapview import fmt
from .state import AppState
from .widgets import LabeledCombo, ScrollFrame, Section

CMAPS = ["viridis", "plasma", "turbo", "cividis", "magma", "coolwarm", "RdYlBu", "RdYlGn", "Spectral", "Blues", "YlOrRd"]
PRESETS = [
    ("Low pressure (< 20)", "node", "res:pressure", "<", 20.0),
    ("Negative pressure (< 0)", "node", "res:pressure", "<", 0.0),
    ("High velocity (> 1.5)", "link", "res:velocity", ">", 1.5),
    ("Stagnant flow (|v| < 0.05)", "link", "res:velocity", "<", 0.05),
    ("High unit headloss (> 10)", "link", "res:headloss", ">", 10.0),
    ("Old water (age > 24 h)", "node", "res:quality", ">", 24.0),
]


class AnalyticsPanel(ScrollFrame):
    def __init__(self, master, state: AppState, actions):
        super().__init__(master)
        self.state, self.actions = state, actions
        s = state.style
        b = self.body

        sec = Section(b, "Basemap"); sec.pack(fill="x")
        self.basemap = tk.StringVar(value=s.basemap)
        cb = ttk.Combobox(sec.body, textvariable=self.basemap, values=list(tl.PROVIDERS), state="readonly")
        cb.pack(fill="x"); cb.bind("<<ComboboxSelected>>", lambda e: self._style(basemap=self.basemap.get()))
        row = ttk.Frame(sec.body); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Fade").pack(side="left")
        self.fade = tk.DoubleVar(value=s.fade)
        ttk.Scale(row, from_=0, to=0.9, variable=self.fade,
                  command=lambda v: self._debounced_style(fade=round(float(v), 2))).pack(side="left", fill="x", expand=True)
        self.overlay = tk.BooleanVar(value=s.overlay)
        ttk.Checkbutton(sec.body, text="GeoPackage asset overlay", variable=self.overlay,
                        command=lambda: self._style(overlay=self.overlay.get())).pack(anchor="w")

        sec = Section(b, "Node layer"); sec.pack(fill="x")
        self.node_var = LabeledCombo(sec.body, "Colour by", lambda k: self._style(node_var=k)); self.node_var.pack(fill="x")
        self.node_cmap = tk.StringVar(value=s.node_cmap)
        r = ttk.Frame(sec.body); r.pack(fill="x", pady=2)
        ttk.Label(r, text="Ramp").pack(side="left")
        c = ttk.Combobox(r, textvariable=self.node_cmap, values=CMAPS, state="readonly", width=12)
        c.pack(side="left", padx=4); c.bind("<<ComboboxSelected>>", lambda e: self._style(node_cmap=self.node_cmap.get()))
        self.size_by = tk.BooleanVar(value=s.size_by_value)
        ttk.Checkbutton(r, text="size", variable=self.size_by,
                        command=lambda: self._style(size_by_value=self.size_by.get())).pack(side="left")

        sec = Section(b, "Link layer"); sec.pack(fill="x")
        self.link_var = LabeledCombo(sec.body, "Colour by", lambda k: self._style(link_var=k)); self.link_var.pack(fill="x")
        self.link_cmap = tk.StringVar(value=s.link_cmap)
        r = ttk.Frame(sec.body); r.pack(fill="x", pady=2)
        ttk.Label(r, text="Ramp").pack(side="left")
        c = ttk.Combobox(r, textvariable=self.link_cmap, values=CMAPS, state="readonly", width=12)
        c.pack(side="left", padx=4); c.bind("<<ComboboxSelected>>", lambda e: self._style(link_cmap=self.link_cmap.get()))
        self.width_by = tk.BooleanVar(value=s.width_by_value)
        ttk.Checkbutton(r, text="width", variable=self.width_by,
                        command=lambda: self._style(width_by_value=self.width_by.get())).pack(side="left")
        r = ttk.Frame(sec.body); r.pack(fill="x")
        self.arrows = tk.BooleanVar(value=s.arrows)
        ttk.Checkbutton(r, text="Flow direction arrows", variable=self.arrows,
                        command=lambda: self._style(arrows=self.arrows.get())).pack(side="left")
        self.labels = tk.BooleanVar(value=s.labels)
        ttk.Checkbutton(r, text="IDs", variable=self.labels,
                        command=lambda: self._style(labels=self.labels.get())).pack(side="left", padx=6)

        sec = Section(b, "Analytics"); sec.pack(fill="x")
        ttk.Label(sec.body, text="Result statistic").pack(anchor="w")
        self.stat = tk.StringVar(value=s.stat)
        c = ttk.Combobox(sec.body, textvariable=self.stat, values=netlib.STATISTICS, state="readonly")
        c.pack(fill="x"); c.bind("<<ComboboxSelected>>", lambda e: self._style(stat=self.stat.get()))
        self.delta = tk.BooleanVar(value=s.delta)
        self.delta_cb = ttk.Checkbutton(sec.body, text="Difference vs baseline scenario", variable=self.delta,
                                        command=lambda: self._style(delta=self.delta.get()))
        self.delta_cb.pack(anchor="w", pady=2)
        r = ttk.Frame(sec.body); r.pack(fill="x")
        ttk.Label(r, text="Range").pack(side="left")
        self.lo, self.hi = tk.StringVar(), tk.StringVar()
        ttk.Entry(r, textvariable=self.lo, width=7).pack(side="left", padx=2)
        ttk.Entry(r, textvariable=self.hi, width=7).pack(side="left", padx=2)
        ttk.Button(r, text="Fix", width=4, command=self._fix_range).pack(side="left")
        ttk.Button(r, text="Auto", width=5, command=self._auto_range).pack(side="left")
        self.range_kind = tk.StringVar(value="node")
        r = ttk.Frame(sec.body); r.pack(fill="x")
        ttk.Radiobutton(r, text="nodes", value="node", variable=self.range_kind).pack(side="left")
        ttk.Radiobutton(r, text="links", value="link", variable=self.range_kind).pack(side="left")

        sec = Section(b, "Highlight / alerts"); sec.pack(fill="x")
        self.preset = tk.StringVar(value="Presets…")
        c = ttk.Combobox(sec.body, textvariable=self.preset, values=[p[0] for p in PRESETS], state="readonly")
        c.pack(fill="x"); c.bind("<<ComboboxSelected>>", lambda e: self._apply_preset())
        r = ttk.Frame(sec.body); r.pack(fill="x", pady=2)
        self.f_kind = tk.StringVar(value="node")
        ttk.Combobox(r, textvariable=self.f_kind, values=["node", "link"], state="readonly", width=5).pack(side="left")
        ttk.Label(r, text="colour var").pack(side="left", padx=2)
        self.f_op = tk.StringVar(value="<")
        ttk.Combobox(r, textvariable=self.f_op, values=["<", ">"], state="readonly", width=2).pack(side="left")
        self.f_val = tk.StringVar(value="20")
        ttk.Entry(r, textvariable=self.f_val, width=7).pack(side="left", padx=2)
        r = ttk.Frame(sec.body); r.pack(fill="x")
        ttk.Button(r, text="Apply", command=self._apply_filter).pack(side="left")
        ttk.Button(r, text="Clear", command=lambda: self._style(filter_op="")).pack(side="left", padx=2)
        ttk.Button(r, text="Select matches", command=self._select_matches).pack(side="left")

        sec = Section(b, "Scenarios"); sec.pack(fill="x")
        self.scen_list = tk.Listbox(sec.body, height=6, activestyle="none", exportselection=False)
        self.scen_list.pack(fill="x")
        self.scen_list.bind("<Double-Button-1>", lambda e: self._activate())
        r = ttk.Frame(sec.body); r.pack(fill="x", pady=2)
        for text, cmd in (("Show", self._activate), ("Baseline", self._set_baseline),
                          ("Rename", self._rename), ("Delete", self._delete)):
            ttk.Button(r, text=text, command=cmd, width=7).pack(side="left", padx=1)
        self.kpi = tk.Text(sec.body, height=9, width=30, font=("TkFixedFont", 8), relief="flat",
                           background="#f8fafc", state="disabled")
        self.kpi.pack(fill="x", pady=(4, 0))

        state.bus.on("model", lambda **_: self.refresh())
        state.bus.on("results", lambda **_: self.refresh())
        state.bus.on("scenarios", lambda **_: self.refresh())
        self._job = None
        self.refresh()

    # ----------------------------------------------------------------
    def _style(self, **changes):
        for k, v in changes.items():
            setattr(self.state.style, k, v)
        if "basemap" in changes:
            self.actions.basemap_changed()
        self.state.bus.emit("style")

    def _debounced_style(self, **changes):
        for k, v in changes.items():
            setattr(self.state.style, k, v)
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(250, lambda: self.state.bus.emit("style"))

    def refresh(self):
        st = self.state
        self.node_var.set_choices(st.variable_choices("node"), st.style.node_var)
        self.link_var.set_choices(st.variable_choices("link"), st.style.link_var)
        st.style.node_var = self.node_var.get() or "type"
        st.style.link_var = self.link_var.get() or "type"
        self.scen_list.delete(0, "end")
        for scen in st.scenarios:
            mark = ("★ " if scen is st.active else "   ") + ("◆ " if scen is st.baseline else "")
            self.scen_list.insert("end", f"{mark}{scen.name} — {scen.settings}")
        self.delta_cb.configure(text=f"Difference vs baseline ({st.baseline.name})" if st.baseline else
                                "Difference vs baseline scenario")
        self._kpis()

    def _kpis(self):
        st = self.state
        self.kpi.configure(state="normal"); self.kpi.delete("1.0", "end")
        if st.active and st.loaded:
            limit = 20.0 if not st.topo.us_units else 30.0
            vel = 2.0 if not st.topo.us_units else 6.5
            values = netlib.kpis(st.active, st.topo, limit, vel)
            base = netlib.kpis(st.baseline, st.topo, limit, vel) if st.baseline and st.baseline is not st.active else {}
            for k, v in values.items():
                line = f"{k[:24]:<24} {fmt(v):>8}"
                if k in base:
                    d = v - base[k]
                    line += f" {'+' if d >= 0 else ''}{fmt(d)}"
                self.kpi.insert("end", line + "\n")
        else:
            self.kpi.insert("end", "Run a simulation to see indicators.")
        self.kpi.configure(state="disabled")

    def _selected_scenario(self):
        sel = self.scen_list.curselection()
        return self.state.scenarios[sel[0]] if sel else None

    def _activate(self):
        scen = self._selected_scenario()
        if scen:
            self.state.active = scen
            self.state.bus.emit("scenarios"); self.state.bus.emit("results")

    def _set_baseline(self):
        scen = self._selected_scenario()
        if scen:
            self.state.baseline = scen
            self.state.bus.emit("scenarios"); self.state.bus.emit("results")

    def _rename(self):
        scen = self._selected_scenario()
        if scen:
            name = simpledialog.askstring("Rename scenario", "Name:", initialvalue=scen.name, parent=self)
            if name:
                scen.name = name
                self.state.bus.emit("scenarios")

    def _delete(self):
        scen = self._selected_scenario()
        if scen and messagebox.askyesno("Delete scenario", f"Delete {scen.name}?", parent=self):
            st = self.state
            st.scenarios.remove(scen)
            if st.active is scen:
                st.active = st.scenarios[-1] if st.scenarios else None
            if st.baseline is scen:
                st.baseline = None
            st.bus.emit("scenarios"); st.bus.emit("results")

    def _fix_range(self):
        kind = self.range_kind.get()
        key = self.state.style.node_var if kind == "node" else self.state.style.link_var
        try:
            self.state.style.fixed_range[key] = (float(self.lo.get()), float(self.hi.get()))
        except ValueError:
            messagebox.showerror("Range", "Enter numeric minimum and maximum.", parent=self); return
        self.state.bus.emit("style")

    def _auto_range(self):
        self.state.style.fixed_range.clear()
        self.state.bus.emit("style")

    def _apply_filter(self):
        try:
            value = float(self.f_val.get())
        except ValueError:
            messagebox.showerror("Highlight", "Threshold must be numeric.", parent=self); return
        self._style(filter_kind=self.f_kind.get(), filter_op=self.f_op.get(), filter_value=value)

    def _apply_preset(self):
        name = self.preset.get()
        for label, kind, key, op, value in PRESETS:
            if label == name:
                st = self.state
                if st.active is None:
                    messagebox.showinfo("Highlight", "Run a simulation first.", parent=self); return
                if key not in dict(st.variable_choices(kind)):
                    messagebox.showinfo("Highlight", f"{key[4:]} is not in the active results.", parent=self); return
                self.f_kind.set(kind); self.f_op.set(op); self.f_val.set(str(value))
                if kind == "node":
                    st.style.node_var = key; self.node_var.set(key)
                else:
                    st.style.link_var = key; self.link_var.set(key)
                self._style(filter_kind=kind, filter_op=op, filter_value=value)

    def _select_matches(self):
        st = self.state
        s = st.style
        if not s.filter_op or not st.loaded:
            return
        key = s.node_var if s.filter_kind == "node" else s.link_var
        vals = st.values(s.filter_kind, key)
        if vals is None:
            return
        import numpy as np
        with np.errstate(invalid="ignore"):
            idx = np.where(vals < s.filter_value if s.filter_op == "<" else vals > s.filter_value)[0].tolist()
        st.select(nodes=idx if s.filter_kind == "node" else [], links=idx if s.filter_kind == "link" else [],
                  source="panel")
