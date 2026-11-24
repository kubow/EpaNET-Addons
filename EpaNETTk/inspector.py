"""Right panel: edit the selected object(s) and see their results."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from epanet_addons import network as netlib
from .mapview import fmt
from .state import RESULT_LABELS, AppState, result_unit
from .widgets import ScrollFrame


class Inspector(ScrollFrame):
    def __init__(self, master, state: AppState, actions):
        super().__init__(master)
        self.state, self.actions = state, actions
        self.title = ttk.Label(self.body, text="Nothing selected", style="Title.TLabel", wraplength=280)
        self.title.pack(anchor="w")
        self.subtitle = ttk.Label(self.body, text="Click an object on the map, Shift+drag to box-select.",
                                  style="Muted.TLabel", wraplength=280)
        self.subtitle.pack(anchor="w", pady=(0, 6))
        self.form = ttk.Frame(self.body); self.form.pack(fill="x")
        self.results = ttk.Frame(self.body); self.results.pack(fill="x", pady=(8, 0))
        self.chart_box = ttk.Frame(self.body); self.chart_box.pack(fill="x", pady=(6, 0))
        self.fig = Figure(figsize=(3.2, 2.0), dpi=90)
        self.fig.subplots_adjust(left=0.18, right=0.97, top=0.9, bottom=0.2)
        self.ax = self.fig.add_subplot(111)
        self.chart = FigureCanvasTkAgg(self.fig, master=self.chart_box)
        self.chart_var = tk.StringVar()
        self.chart_combo = ttk.Combobox(self.chart_box, textvariable=self.chart_var, state="readonly")
        self.chart_combo.bind("<<ComboboxSelected>>", lambda e: self._draw_chart())
        self._entries: dict[str, tk.Variable] = {}
        b = state.bus
        b.on("selection", lambda **_: self.rebuild())
        b.on("model", lambda **_: self.rebuild())
        b.on("results", lambda **_: self.rebuild())
        b.on("properties", lambda **_: self.rebuild())
        b.on("time", lambda **_: self._time_changed())
        self.rebuild()

    def _clear(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def rebuild(self):
        self._clear(self.form); self._clear(self.results)
        self.chart_combo.pack_forget(); self.chart.get_tk_widget().pack_forget()
        st = self.state
        if not st.loaded:
            self.title.configure(text="No model"); self.subtitle.configure(text="Open a model to inspect objects.")
            return
        n, l = len(st.sel_nodes), len(st.sel_links)
        if n + l == 0:
            self._summary(); return
        if n + l == 1:
            kind, i = ("node", next(iter(st.sel_nodes))) if n else ("link", next(iter(st.sel_links)))
            self._single(kind, i)
        else:
            self._multi()

    # ------------------------------------------------------------- summary
    def _summary(self):
        st = self.state
        topo = st.topo
        name = st.project_name or (st.source_path.name if st.source_path else "Model")
        self.title.configure(text=name)
        self.subtitle.configure(text=f"{st.crs.name}\nFlow units {topo.flow_units}"
                                + ("\n⚠ No coordinates in model – schematic layout" if topo.synthetic_layout else ""))
        counts = topo.counts()
        for row, (k, v) in enumerate(sorted(counts.items())):
            ttk.Label(self.form, text=k).grid(row=row, column=0, sticky="w")
            ttk.Label(self.form, text=str(v), style="Value.TLabel").grid(row=row, column=1, sticky="e", padx=8)
        ttk.Label(self.results, text="Tip: right-click objects for actions; use the toolbar to add junctions and pipes.",
                  style="Muted.TLabel", wraplength=280).pack(anchor="w")

    # -------------------------------------------------------------- single
    def _single(self, kind: str, i: int):
        st = self.state
        topo, net = st.topo, st.net
        oid = topo.node_ids[i] if kind == "node" else topo.link_ids[i]
        otype = topo.node_types[i] if kind == "node" else topo.link_types[i]
        self.title.configure(text=f"{otype}  {oid}")
        if kind == "link":
            a, b = topo.node_ids[topo.link_from[i]], topo.node_ids[topo.link_to[i]]
            self.subtitle.configure(text=f"{a}  →  {b}")
        else:
            links = [topo.link_ids[j] for j in range(len(topo.link_ids)) if i in (topo.link_from[j], topo.link_to[j])]
            self.subtitle.configure(text=f"X {topo.x[i]:,.2f}   Y {topo.y[i]:,.2f}\nConnected: "
                                    + (", ".join(links[:8]) + (" …" if len(links) > 8 else "") or "none"))
        self._entries = {}
        us = topo.us_units
        patterns = [""] + netlib.pattern_names(net)
        row = 0
        for f in netlib.applicable(kind, otype):
            try:
                value = netlib.get_property(net, topo, kind, i, f)
            except Exception:
                continue
            ttk.Label(self.form, text=f.label).grid(row=row, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=value if isinstance(value, str) else ("" if np.isnan(value) else f"{value:.6g}"))
            if f.kind == "pattern":
                w = ttk.Combobox(self.form, textvariable=var, values=patterns, width=11)
            elif f.kind == "status":
                w = ttk.Combobox(self.form, textvariable=var, values=["OPEN", "CLOSED"], state="readonly", width=11)
            else:
                w = ttk.Entry(self.form, textvariable=var, width=13)
                w.bind("<Return>", lambda e, k=kind, idx=i: self._apply(k, idx))
            w.grid(row=row, column=1, sticky="ew", padx=4, pady=1)
            unit = f.unit(us).replace("flow", topo.flow_units)
            ttk.Label(self.form, text=unit, style="Muted.TLabel").grid(row=row, column=2, sticky="w")
            if f.help:
                w.bind("<Enter>", lambda e, h=f.help: self.actions.status(h))
            self._entries[f.key] = var
            row += 1
        self.form.columnconfigure(1, weight=1)
        btns = ttk.Frame(self.form); btns.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Apply changes", style="Accent.TButton",
                   command=lambda: self._apply(kind, i)).pack(side="left")
        ttk.Button(btns, text="Zoom", command=self.actions.zoom_selection).pack(side="left", padx=4)
        if kind == "link":
            ttk.Button(btns, text="Ends", command=lambda: st.select([int(topo.link_from[i]), int(topo.link_to[i])],
                                                                    [i], source="inspector")).pack(side="left")
        self._result_rows(kind, [i])
        self._setup_chart(kind)

    def _apply(self, kind: str, i: int):
        st = self.state
        otype = st.topo.node_types[i] if kind == "node" else st.topo.link_types[i]
        changed, errors = 0, []
        for f in netlib.applicable(kind, otype):
            var = self._entries.get(f.key)
            if var is None:
                continue
            new = var.get().strip()
            try:
                old = netlib.get_property(st.net, st.topo, kind, i, f)
                if isinstance(old, str) and new == old:
                    continue
                if not isinstance(old, str):
                    if new == "" and np.isnan(old):
                        continue
                    if not np.isnan(old) and abs(float(new) - old) < 1e-12:
                        continue
                netlib.set_property(st.net, kind, i, f, new)
                changed += 1
            except Exception as exc:
                errors.append(f"{f.label}: {exc}")
        if errors:
            messagebox.showerror("Some values were not applied", "\n".join(errors), parent=self)
        if changed:
            self.actions.status(f"Updated {changed} value(s). Re-run to refresh results.")
            st.properties_changed()

    # --------------------------------------------------------------- multi
    def _multi(self):
        st = self.state
        n, l = len(st.sel_nodes), len(st.sel_links)
        self.title.configure(text=f"{n} nodes, {l} links selected")
        self.subtitle.configure(text="Bulk edit applies to every selected object of a matching type.")
        kinds = (["node"] if n else []) + (["link"] if l else [])
        kind_var = tk.StringVar(value=kinds[0])
        field_var, op_var, val_var = tk.StringVar(), tk.StringVar(value="set"), tk.StringVar()
        ttk.Label(self.form, text="Objects").grid(row=0, column=0, sticky="w")
        kc = ttk.Combobox(self.form, textvariable=kind_var, values=kinds, state="readonly", width=12)
        kc.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(self.form, text="Property").grid(row=1, column=0, sticky="w")
        fc = ttk.Combobox(self.form, textvariable=field_var, state="readonly", width=20)
        fc.grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Label(self.form, text="Operation").grid(row=2, column=0, sticky="w")
        ttk.Combobox(self.form, textvariable=op_var, values=["set", "multiply", "add"], state="readonly",
                     width=12).grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Label(self.form, text="Value").grid(row=3, column=0, sticky="w")
        ttk.Entry(self.form, textvariable=val_var, width=13).grid(row=3, column=1, sticky="ew", padx=4)
        self.form.columnconfigure(1, weight=1)

        def fields_for(kind):
            types = {st.topo.node_types[i] for i in st.sel_nodes} if kind == "node" else \
                {st.topo.link_types[i] for i in st.sel_links}
            return [f for f in netlib.FIELDS[kind] if types & set(f.applies)]

        def refresh_fields(*_):
            fs = fields_for(kind_var.get())
            fc["values"] = [f.label for f in fs]
            if fs:
                field_var.set(fs[0].label)
        kc.bind("<<ComboboxSelected>>", refresh_fields)
        refresh_fields()

        def apply():
            kind = kind_var.get()
            f = next((f for f in fields_for(kind) if f.label == field_var.get()), None)
            if f is None:
                return
            if f.kind != "float" and op_var.get() != "set":
                messagebox.showerror("Bulk edit", "Only 'set' is possible for this property.", parent=self); return
            indices = st.sel_nodes if kind == "node" else st.sel_links
            types = st.topo.node_types if kind == "node" else st.topo.link_types
            idx = [i for i in indices if types[i] in f.applies]
            try:
                value = val_var.get() if f.kind != "float" else float(val_var.get())
            except ValueError:
                messagebox.showerror("Bulk edit", "Value must be numeric.", parent=self); return
            count = netlib.bulk_edit(st.net, kind, idx, f, op_var.get(), value)
            self.actions.status(f"{op_var.get().title()} {f.label} on {count} {kind}s.")
            st.properties_changed()
        ttk.Button(self.form, text="Apply to selection", style="Accent.TButton", command=apply).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(self.form, text="Zoom to selection", command=self.actions.zoom_selection).grid(
            row=5, column=0, columnspan=2, sticky="w")
        # statistics of the coloured variables over the selection
        for kind, sel in (("node", st.sel_nodes), ("link", st.sel_links)):
            key = st.style.node_var if kind == "node" else st.style.link_var
            if not sel or key in ("type", "none"):
                continue
            vals = st.values(kind, key)
            if vals is None:
                continue
            v = vals[sorted(sel)]
            v = v[np.isfinite(v)]
            if v.size:
                ttk.Label(self.results, text=f"{st.label_for(kind, key)} over selected {kind}s",
                          style="Section.TLabel").pack(anchor="w")
                ttk.Label(self.results, text=f"min {fmt(v.min())}   mean {fmt(v.mean())}   max {fmt(v.max())}",
                          style="Value.TLabel").pack(anchor="w")
        kind = "node" if n else "link"
        self._chart_kind = kind
        self._setup_chart(kind)

    # ------------------------------------------------------------- results
    def _result_rows(self, kind: str, idx: list[int]):
        st = self.state
        self._result_labels = {}
        if st.active is None:
            ttk.Label(self.results, text="No results yet – press Run.", style="Muted.TLabel").pack(anchor="w")
            return
        ttk.Label(self.results, text=f"Results · {st.active.name}", style="Section.TLabel").pack(anchor="w")
        grid = ttk.Frame(self.results); grid.pack(fill="x")
        for r, var in enumerate(st.active.results.variables(kind)):
            label = RESULT_LABELS.get(var, var[4:] if var.startswith("msx:") else var)
            unit = result_unit(var, st.topo.us_units, st.topo.flow_units)
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w")
            value = ttk.Label(grid, text="", style="Value.TLabel")
            value.grid(row=r, column=1, sticky="e", padx=6)
            ttk.Label(grid, text=unit, style="Muted.TLabel").grid(row=r, column=2, sticky="w")
            self._result_labels[var] = (value, kind, idx[0])
        grid.columnconfigure(1, weight=1)
        self._update_values()

    def _update_values(self):
        st = self.state
        for var, (label, kind, i) in getattr(self, "_result_labels", {}).items():
            try:
                vals = st.values(kind, f"res:{var}", stat="At time", delta=False)
                text = fmt(vals[i]) if vals is not None else "–"
                if var == "status" and vals is not None and np.isfinite(vals[i]):
                    text = {0: "closed", 1: "open", 2: "open"}.get(int(round(vals[i])), fmt(vals[i]))
                label.configure(text=text)
            except tk.TclError:
                pass

    def _time_changed(self):
        self._update_values()
        if hasattr(self, "_vline") and self._vline is not None:
            try:
                self._vline.set_xdata([self.state.time_s / 3600] * 2)
                self.chart.draw_idle()
            except Exception:
                pass

    def _setup_chart(self, kind: str):
        st = self.state
        self._chart_kind = kind
        self._vline = None
        if st.active is None:
            return
        variables = st.active.results.variables(kind)
        labels = [RESULT_LABELS.get(v, v[4:] + " (MSX)" if v.startswith("msx:") else v) for v in variables]
        self._chart_map = dict(zip(labels, variables))
        self.chart_combo["values"] = labels
        current = (st.style.node_var if kind == "node" else st.style.link_var)
        preferred = current[4:] if current.startswith("res:") else ("pressure" if kind == "node" else "flow")
        if self.chart_var.get() not in labels:
            self.chart_var.set(labels[variables.index(preferred)] if preferred in variables else (labels[0] if labels else ""))
        self.chart_combo.pack(fill="x")
        self.chart.get_tk_widget().pack(fill="x")
        self._draw_chart()

    def _draw_chart(self):
        st = self.state
        kind = self._chart_kind
        var = self._chart_map.get(self.chart_var.get())
        ax = self.ax
        ax.clear()
        sel = sorted(st.sel_nodes if kind == "node" else st.sel_links)[:6]
        ids = st.topo.node_ids if kind == "node" else st.topo.link_ids
        if var is None or not sel:
            self.chart.draw_idle(); return
        scenarios = st.scenarios if len(sel) == 1 else [st.active]
        for scen in scenarios:
            found = scen.results.series(kind, var)
            if found is None:
                continue
            times, data = found
            sid = scen.results.node_ids if kind == "node" else scen.results.link_ids
            for i in sel:
                if ids[i] not in sid:
                    continue
                col = sid.index(ids[i]) if sid is not ids else i
                label = scen.name if len(sel) == 1 else ids[i]
                ax.plot(times / 3600, data[:, col], lw=2.0 if scen is st.active else 1.1,
                        alpha=1 if scen is st.active else 0.6, label=label)
        self._vline = ax.axvline(st.time_s / 3600, color="#ef4444", lw=1, ls="--")
        ax.set_xlabel("h", fontsize=8); ax.tick_params(labelsize=7); ax.grid(alpha=0.3)
        if len(ax.get_lines()) > 2:
            ax.legend(fontsize=6, loc="best")
        self.chart.draw_idle()
