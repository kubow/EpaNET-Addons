"""Modal dialogs: run settings, coordinate system, pattern editor, report viewer."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import numpy as np

from epanet_addons import crs as crslib
from epanet_addons import network as netlib
from .state import AppState


class Dialog(tk.Toplevel):
    def __init__(self, master, title: str):
        super().__init__(master)
        self.title(title)
        self.transient(master.winfo_toplevel())
        self.result = None
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def buttons(self, ok_text="OK"):
        b = ttk.Frame(self.body); b.grid(row=99, column=0, columnspan=4, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text=ok_text, style="Accent.TButton", command=self.ok).pack(side="right", padx=4)

    def run(self):
        self.wait_visibility(); self.grab_set(); self.wait_window()
        return self.result

    def ok(self):
        self.destroy()


class RunSettingsDialog(Dialog):
    def __init__(self, master, state: AppState):
        super().__init__(master, "Simulation settings")
        self.state = state
        s = netlib.RunSettings.from_network(state.net) if state.loaded else state.run_settings
        if state.run_settings.quality != "NONE":
            s.quality, s.chem_name = state.run_settings.quality, state.run_settings.chem_name
            s.chem_units, s.trace_node = state.run_settings.chem_units, state.run_settings.trace_node
        self.v = {
            "duration_h": tk.StringVar(value=f"{s.duration_h:g}"),
            "hydraulic_step_min": tk.StringVar(value=f"{s.hydraulic_step_min:g}"),
            "report_step_min": tk.StringVar(value=f"{s.report_step_min:g}"),
            "quality": tk.StringVar(value=s.quality),
            "chem_name": tk.StringVar(value=s.chem_name), "chem_units": tk.StringVar(value=s.chem_units),
            "trace_node": tk.StringVar(value=s.trace_node or (state.topo.node_ids[next(iter(state.sel_nodes))]
                                                              if state.loaded and state.sel_nodes else "")),
        }
        rows = [("Duration [h]", "duration_h"), ("Hydraulic step [min]", "hydraulic_step_min"),
                ("Report step [min]", "report_step_min")]
        for r, (label, key) in enumerate(rows):
            ttk.Label(self.body, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(self.body, textvariable=self.v[key], width=10).grid(row=r, column=1, sticky="w")
        ttk.Label(self.body, text="Water quality").grid(row=4, column=0, sticky="w", pady=(8, 2))
        q = ttk.Frame(self.body); q.grid(row=4, column=1, columnspan=3, sticky="w", pady=(8, 2))
        for val, label in (("NONE", "None"), ("AGE", "Water age"), ("CHEM", "Chemical"), ("TRACE", "Source trace")):
            ttk.Radiobutton(q, text=label, value=val, variable=self.v["quality"]).pack(side="left")
        ttk.Label(self.body, text="Chemical name / units").grid(row=5, column=0, sticky="w")
        c = ttk.Frame(self.body); c.grid(row=5, column=1, columnspan=3, sticky="w")
        ttk.Entry(c, textvariable=self.v["chem_name"], width=12).pack(side="left")
        ttk.Entry(c, textvariable=self.v["chem_units"], width=8).pack(side="left", padx=4)
        ttk.Label(self.body, text="Trace node").grid(row=6, column=0, sticky="w")
        ttk.Entry(self.body, textvariable=self.v["trace_node"], width=12).grid(row=6, column=1, sticky="w")
        ttk.Label(self.body, text="Standard quality runs with hydraulics. Multi-species chemistry is run from the "
                                  "MSX studio.", style="Muted.TLabel", wraplength=360).grid(row=7, column=0, columnspan=4,
                                                                                           sticky="w", pady=6)
        self.buttons("Save settings")

    def ok(self):
        try:
            s = netlib.RunSettings(float(self.v["duration_h"].get()), float(self.v["hydraulic_step_min"].get()),
                                   float(self.v["report_step_min"].get()), self.v["quality"].get(),
                                   self.v["chem_name"].get(), self.v["chem_units"].get(), self.v["trace_node"].get())
        except ValueError:
            messagebox.showerror("Settings", "Durations must be numbers.", parent=self); return
        if s.quality == "TRACE" and self.state.loaded and s.trace_node not in self.state.topo.node_ids:
            messagebox.showerror("Settings", "Trace node is not in the network.", parent=self); return
        self.result = s
        self.destroy()


class CRSDialog(Dialog):
    def __init__(self, master, state: AppState, suggestion: crslib.ProjectCRS | None = None):
        super().__init__(master, "Coordinate reference system")
        self.state = state
        ttk.Label(self.body, text="EPANET files do not store a CRS. Choose the system the model's X/Y are in;\n"
                                  "coordinates are never changed, only interpreted for the map.",
                  wraplength=460).grid(row=0, column=0, columnspan=3, sticky="w")
        self.code = tk.StringVar(value=state.crs.code)
        labels = [f"{code} — {label}" for code, label in crslib.PRESETS]
        self.combo = ttk.Combobox(self.body, values=labels, width=56)
        self.combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=6)
        self.combo.set(next((l for l in labels if l.startswith(state.crs.code + " ")), state.crs.code))
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._preview())
        self.combo.bind("<KeyRelease>", lambda e: self._preview())
        if suggestion is not None:
            ttk.Label(self.body, text=f"Detected: {suggestion.name}", style="Value.TLabel").grid(row=2, column=0, sticky="w")
        if not crslib.pyproj_available():
            ttk.Label(self.body, text="pyproj is not installed: only LOCAL is available.", foreground="#b91c1c").grid(
                row=3, column=0, sticky="w")
        self.info = ttk.Label(self.body, text="", style="Muted.TLabel", justify="left")
        self.info.grid(row=4, column=0, columnspan=3, sticky="w", pady=6)
        self.buttons("Use this CRS")
        self._preview()

    def _code(self) -> str:
        return self.combo.get().split(" — ")[0].strip()

    def _preview(self):
        try:
            code = crslib.validate_code(self._code())
        except Exception as exc:
            self.info.configure(text=f"Unknown CRS: {exc}"); return
        crs = crslib.ProjectCRS(code)
        lines = [crs.name, f"Axis units: {crs.units}"]
        st = self.state
        if st.loaded and not crs.is_local:
            wx, wy = crs.to_world([float(np.mean(st.topo.x))], [float(np.mean(st.topo.y))])
            ll = crs.world_to_lonlat(float(wx[0]), float(wy[0]))
            if ll and np.isfinite(ll[0]):
                lines.append(f"Network centre → {ll[1]:.5f}° N, {ll[0]:.5f}° E")
                if not (-180 <= ll[0] <= 180 and -85 <= ll[1] <= 85):
                    lines.append("⚠ Outside the world – this CRS is probably wrong.")
            else:
                lines.append("⚠ Coordinates cannot be transformed with this CRS.")
        self.info.configure(text="\n".join(lines))

    def ok(self):
        try:
            self.result = crslib.ProjectCRS(crslib.validate_code(self._code()))
        except Exception as exc:
            messagebox.showerror("CRS", str(exc), parent=self); return
        self.destroy()


class PatternEditor(Dialog):
    """Edit time patterns by dragging bars."""

    def __init__(self, master, state: AppState):
        super().__init__(master, "Time patterns")
        self.state = state
        self.patterns = netlib.get_patterns(state.net)
        left = ttk.Frame(self.body); left.grid(row=0, column=0, sticky="ns")
        self.lb = tk.Listbox(left, height=14, exportselection=False, width=16)
        self.lb.pack(fill="y", expand=True)
        for name in self.patterns:
            self.lb.insert("end", name)
        self.lb.bind("<<ListboxSelect>>", lambda e: self._select())
        ttk.Button(left, text="New…", command=self._new).pack(fill="x", pady=2)
        right = ttk.Frame(self.body); right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.canvas = tk.Canvas(right, width=620, height=260, background="white", highlightthickness=1,
                                highlightbackground="#cbd5e1")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._drag); self.canvas.bind("<B1-Motion>", self._drag)
        self.text = tk.StringVar()
        row = ttk.Frame(right); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Multipliers").pack(side="left")
        e = ttk.Entry(row, textvariable=self.text); e.pack(side="left", fill="x", expand=True, padx=4)
        e.bind("<Return>", lambda ev: self._from_text())
        ttk.Button(row, text="Set", command=self._from_text).pack(side="left")
        tools = ttk.Frame(right); tools.pack(fill="x")
        ttk.Button(tools, text="Normalise to mean 1", command=self._normalise).pack(side="left")
        ttk.Button(tools, text="Scale ×1.1", command=lambda: self._scale(1.1)).pack(side="left", padx=2)
        ttk.Button(tools, text="Scale ×0.9", command=lambda: self._scale(0.9)).pack(side="left")
        ttk.Label(tools, text="Click/drag bars to edit", style="Muted.TLabel").pack(side="right")
        self.body.columnconfigure(1, weight=1); self.body.rowconfigure(0, weight=1)
        self.current = None
        self.dirty: set[str] = set()
        self.buttons("Apply to model")
        if self.patterns:
            self.lb.selection_set(0); self._select()

    def _select(self):
        sel = self.lb.curselection()
        if sel:
            self.current = self.lb.get(sel[0])
            self._draw()

    def _new(self):
        name = simpledialog.askstring("New pattern", "Pattern ID:", parent=self)
        if name and name not in self.patterns:
            self.patterns[name] = [1.0] * 24
            self.dirty.add(name)
            self.lb.insert("end", name); self.lb.selection_clear(0, "end"); self.lb.selection_set("end"); self._select()

    def _vmax(self, vals):
        return max(2.0, max(vals) * 1.15 if vals else 2.0)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        vals = self.patterns.get(self.current, [])
        if not vals:
            return
        w, h = c.winfo_width() or 620, c.winfo_height() or 260
        self._vm = vm = self._vmax(vals)
        bw = (w - 40) / len(vals)
        y1 = c.create_line(30, h - 20 - (h - 40) / vm, w - 10, h - 20 - (h - 40) / vm, fill="#ef4444", dash=(3, 3))
        del y1
        for k, v in enumerate(vals):
            x0 = 30 + k * bw
            y = h - 20 - (h - 40) * v / vm
            c.create_rectangle(x0 + 1, y, x0 + bw - 1, h - 20, fill="#60a5fa" if v >= 1 else "#93c5fd", outline="")
            if bw > 14:
                c.create_text(x0 + bw / 2, h - 10, text=str(k + 1), font=("TkDefaultFont", 7), fill="#475569")
        c.create_text(4, 20, text=f"{vm:.2f}", anchor="w", font=("TkDefaultFont", 7))
        c.create_text(4, h - 20, text="0", anchor="w", font=("TkDefaultFont", 7))
        mean = sum(vals) / len(vals)
        c.create_text(w - 10, 8, text=f"{self.current}: {len(vals)} steps, mean {mean:.3f}", anchor="ne",
                      font=("TkDefaultFont", 9, "bold"))
        self.text.set(" ".join(f"{v:.3g}" for v in vals))
        self._bw, self._h = bw, h

    def _drag(self, e):
        vals = self.patterns.get(self.current)
        if not vals:
            return
        k = int((e.x - 30) // self._bw)
        if 0 <= k < len(vals):
            vals[k] = round(max(0.0, (self._h - 20 - e.y) / (self._h - 40) * self._vm), 3)
            self.dirty.add(self.current)
            self._draw()

    def _from_text(self):
        try:
            vals = [float(x) for x in self.text.get().replace(",", " ").split()]
        except ValueError:
            messagebox.showerror("Pattern", "Multipliers must be numbers.", parent=self); return
        if vals and self.current:
            self.patterns[self.current] = vals; self.dirty.add(self.current); self._draw()

    def _normalise(self):
        vals = self.patterns.get(self.current)
        if vals and sum(vals):
            m = sum(vals) / len(vals)
            self.patterns[self.current] = [v / m for v in vals]; self.dirty.add(self.current); self._draw()

    def _scale(self, f):
        vals = self.patterns.get(self.current)
        if vals:
            self.patterns[self.current] = [v * f for v in vals]; self.dirty.add(self.current); self._draw()

    def ok(self):
        for name in self.dirty:
            netlib.set_pattern(self.state.net, name, self.patterns[name])
        self.result = len(self.dirty)
        self.destroy()


class ReportWindow(tk.Toplevel):
    """Show a nested JSON-like report (e.g. MIKE URBAN conversion) as a tree."""

    def __init__(self, master, title: str, report: dict):
        super().__init__(master)
        self.title(title)
        self.geometry("760x520")
        tree = ttk.Treeview(self, columns=("value",), show="tree headings")
        tree.heading("#0", text="Item"); tree.heading("value", text="Value")
        tree.column("#0", width=300); tree.column("value", width=420)
        ys = ttk.Scrollbar(self, command=tree.yview); tree.configure(yscrollcommand=ys.set)
        tree.pack(side="left", fill="both", expand=True); ys.pack(side="right", fill="y")

        def add(parent, key, value):
            if isinstance(value, dict):
                node = tree.insert(parent, "end", text=f"{key}  ({len(value)})", open=parent == "")
                for k, v in value.items():
                    add(node, k, v)
            elif isinstance(value, list):
                flagged = key.startswith(("omitted", "unknown", "untranslated", "excluded")) and value
                node = tree.insert(parent, "end", text=f"{key}  [{len(value)}]" + ("  ⚠" if flagged else ""))
                for k, v in enumerate(value[:500]):
                    add(node, str(k), v)
            else:
                tree.insert(parent, "end", text=key, values=(json.dumps(value) if not isinstance(value, str) else value,))
        for k, v in report.items():
            add("", k, v)
