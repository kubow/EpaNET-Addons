"""MSX studio: compound-centric editor for EPANET-MSX chemistry."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from epanet_addons import msx as msxlib
from epanet_addons import network as netlib
from .state import AppState
from .widgets import ScrollFrame

SECTION_TITLES = [
    ("COMPOUNDS", "Compounds"), ("OPTIONS", "Options"), ("SPECIES", "Species"),
    ("COEFFICIENTS", "Coefficients"), ("TERMS", "Terms"), ("PIPES", "Pipe reactions"),
    ("TANKS", "Tank reactions"), ("QUALITY", "Initial quality"), ("SOURCES", "Sources"),
    ("PARAMETERS", "Pipe/tank parameters"), ("DIFFUSIVITY", "Diffusivity"), ("PATTERNS", "Patterns"),
    ("REPORT", "Report"), ("RAW", "Raw text"),
]
KINETICS = {
    "Conservative (no reaction)": "0",
    "First-order decay  −k·C": "-{k}*{S}",
    "First-order growth  +k·C": "{k}*{S}",
    "Second-order with another species  −k·C·X": "-{k}*{S}*{X}",
    "Saturation (Monod) growth  k·C/(K+C)": "{k}*{S}/({K}+{S})",
    "Wall-limited decay  −(4/D)·k·C": "-(4/D)*{k}*{S}",
    "Custom expression": "",
}
SPECIES_COLORS = ["#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed", "#0891b2", "#dc2626", "#4d7c0f"]


class MsxStudio(ttk.Frame):
    def __init__(self, master, state: AppState, actions):
        super().__init__(master)
        self.state, self.actions = state, actions
        top = ttk.Frame(self, padding=(6, 6)); top.pack(fill="x")
        ttk.Label(top, text="Template").pack(side="left")
        self.tpl = tk.StringVar(value=list(msxlib.TEMPLATES)[1])
        ttk.Combobox(top, textvariable=self.tpl, values=list(msxlib.TEMPLATES), state="readonly",
                     width=36).pack(side="left", padx=4)
        ttk.Button(top, text="Load template", command=self._load_template).pack(side="left")
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top, text="Open .msx…", command=self._open).pack(side="left")
        ttk.Button(top, text="Save .msx…", command=self._save).pack(side="left", padx=4)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top, text="▶ Run MSX", style="Accent.TButton",
                   command=self.actions.run_msx).pack(side="left")

        body = ttk.PanedWindow(self, orient="horizontal"); body.pack(fill="both", expand=True)
        nav = ttk.Frame(body, padding=4); body.add(nav, weight=0)
        self.nav = tk.Listbox(nav, activestyle="none", exportselection=False, width=20, font=("TkDefaultFont", 10))
        for _, title in SECTION_TITLES:
            self.nav.insert("end", title)
        self.nav.pack(fill="y", expand=True)
        self.nav.bind("<<ListboxSelect>>", lambda e: self.show_section())
        self.center = ttk.Frame(body, padding=4); body.add(self.center, weight=4)
        right = ttk.Frame(body, padding=4); body.add(right, weight=1)
        ttk.Label(right, text="Validation", style="Section.TLabel").pack(anchor="w")
        self.badge = ttk.Label(right, text="", font=("TkDefaultFont", 10, "bold")); self.badge.pack(anchor="w")
        self.file_label = ttk.Label(right, text="", style="Muted.TLabel", wraplength=300); self.file_label.pack(anchor="w")
        self.issues = ttk.Treeview(right, columns=("msg",), show="tree", height=12)
        self.issues.column("#0", width=70, stretch=False); self.issues.column("msg", width=260)
        self.issues.tag_configure("error", foreground="#b91c1c")
        self.issues.tag_configure("warning", foreground="#b45309")
        self.issues.pack(fill="both", expand=True)
        ttk.Label(right, text="Species on map", style="Section.TLabel").pack(anchor="w", pady=(8, 0))
        self.map_buttons = ttk.Frame(right); self.map_buttons.pack(fill="x")
        self.nav.selection_set(0)
        state.bus.on("results", lambda **_: self._species_buttons())
        state.bus.on("msx", lambda **_: self.show_section())
        state.bus.on("model", lambda **_: self.validate())
        self.show_section()

    # -------------------------------------------------------------- helpers
    @property
    def model(self) -> msxlib.MsxModel:
        return self.state.msx

    def changed(self, refresh: bool = False):
        self.validate()
        if refresh:
            self.show_section()

    def validate(self):
        st = self.state
        nodes = set(st.topo.node_ids) if st.loaded else None
        links = set(st.topo.link_ids) if st.loaded else None
        patterns = set(netlib.pattern_names(st.net)) if st.loaded else None
        issues = self.model.validate(nodes, links, patterns)
        self.issues.delete(*self.issues.get_children())
        for i in issues:
            self.issues.insert("", "end", text=i.level, values=(f"{i.section}: {i.message}",), tags=(i.level,))
        errors = sum(i.level == "error" for i in issues)
        warnings = len(issues) - errors
        if errors:
            self.badge.configure(text=f"✖ {errors} error(s), {warnings} warning(s)", foreground="#b91c1c")
        elif warnings:
            self.badge.configure(text=f"⚠ {warnings} warning(s)", foreground="#b45309")
        else:
            self.badge.configure(text="✔ chemistry valid", foreground="#15803d")
        self.file_label.configure(text=str(st.msx_path or "(unsaved model)"))
        return issues

    def _clear(self):
        for w in self.center.winfo_children():
            w.destroy()

    def show_section(self):
        sel = self.nav.curselection()
        key = SECTION_TITLES[sel[0] if sel else 0][0]
        self._clear()
        if key == "COMPOUNDS":
            self._sec_compounds()
        elif key == "OPTIONS":
            self._sec_options()
        elif key == "REPORT":
            self._sec_report()
        elif key == "RAW":
            self._sec_raw()
        else:
            TableEditor(self.center, self, key).pack(fill="both", expand=True)
        self.validate()

    def _species_buttons(self):
        for w in self.map_buttons.winfo_children():
            w.destroy()
        st = self.state
        if st.active is None or not st.active.results.msx_node:
            ttk.Label(self.map_buttons, text="Run MSX to map species.", style="Muted.TLabel").pack(anchor="w")
            return
        for k, name in enumerate(st.active.results.msx_node):
            ttk.Button(self.map_buttons, text=f"● {name}", command=lambda n=name: self.actions.map_species(n)).pack(
                fill="x", pady=1)

    # ------------------------------------------------------------ templates
    def _load_template(self):
        if self.model.species() and not messagebox.askyesno(
                "Replace chemistry", "Replace the current MSX model with the template?", parent=self):
            return
        self.state.msx = msxlib.template(self.tpl.get())
        self.state.msx_path = None
        self._apply_network_defaults()
        self.show_section()

    def _apply_network_defaults(self):
        """Point template sources at the first reservoir/tank of the loaded model."""
        st = self.state
        if not st.loaded or self.model.rows["SOURCES"]:
            return
        source = next((nid for nid, t in zip(st.topo.node_ids, st.topo.node_types) if t == "Reservoir"), None) or \
            next((nid for nid, t in zip(st.topo.node_ids, st.topo.node_types) if t == "Tank"), None)
        if not source:
            return
        bulk = [r["name"] for r in self.model.rows["SPECIES"] if r["type"] == "BULK"]
        if bulk:
            self.model.rows["SOURCES"].append({"type": "CONCEN", "node": source, "species": bulk[0],
                                               "strength": "1.0", "pattern": "", "comment": "added for this network"})

    def _open(self):
        path = filedialog.askopenfilename(filetypes=[("EPANET-MSX", "*.msx"), ("All", "*")], parent=self)
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path):
        text = path.read_text(encoding="utf-8", errors="replace")
        self.state.msx = msxlib.parse(text)
        self.state.msx_path = path
        self.show_section()
        self.actions.status(f"Loaded MSX chemistry {path.name} ({len(self.model.species())} species)")

    def _save(self):
        path = filedialog.asksaveasfilename(defaultextension=".msx", filetypes=[("EPANET-MSX", "*.msx")], parent=self,
                                            initialfile=(self.state.msx_path.name if self.state.msx_path else "chemistry.msx"))
        if path:
            Path(path).write_text(msxlib.write(self.model), encoding="utf-8")
            self.state.msx_path = Path(path)
            self.validate()
            self.actions.status(f"Saved {path}")

    # ------------------------------------------------------------ compounds
    def _sec_compounds(self):
        m = self.model
        head = ttk.Frame(self.center); head.pack(fill="x")
        ttk.Label(head, text=m.title.splitlines()[0] if m.title else "Untitled chemistry", style="Title.TLabel").pack(side="left")
        ttk.Button(head, text="＋ Add compound…", style="Accent.TButton",
                   command=lambda: CompoundWizard(self)).pack(side="right")
        ttk.Label(self.center, text="Each card shows one species across all MSX sections. Edit expressions in place "
                                    "and press Apply; use the section tabs for anything else.",
                  style="Muted.TLabel", wraplength=700).pack(anchor="w", pady=(2, 6))
        scroll = ScrollFrame(self.center); scroll.pack(fill="both", expand=True)
        if not m.species():
            ttk.Label(scroll.body, text="No species yet. Load a template or add a compound.").pack(pady=20)
        for k, row in enumerate(m.rows["SPECIES"]):
            self._card(scroll.body, row, SPECIES_COLORS[k % len(SPECIES_COLORS)])
        coeffs = ", ".join(f"{r['name']}={r['value']}" for r in m.rows["COEFFICIENTS"])
        terms = ", ".join(f"{r['name']}" for r in m.rows["TERMS"])
        ttk.Label(scroll.body, text=f"Coefficients: {coeffs or '—'}\nTerms: {terms or '—'}", style="Muted.TLabel",
                  wraplength=700, justify="left").pack(anchor="w", pady=6)

    def _card(self, parent, sp: dict, color: str):
        m = self.model
        name = sp["name"]
        card = tk.Frame(parent, background="white", highlightbackground="#e2e8f0", highlightthickness=1)
        card.pack(fill="x", pady=4)
        stripe = tk.Frame(card, background=color, width=6); stripe.pack(side="left", fill="y")
        inner = ttk.Frame(card, padding=8, style="Card.TFrame"); inner.pack(side="left", fill="both", expand=True)
        head = ttk.Frame(inner, style="Card.TFrame"); head.pack(fill="x")
        tk.Label(head, text=name, font=("TkDefaultFont", 13, "bold"), foreground=color, background="white").pack(side="left")
        badge = "bulk (mass/L)" if sp.get("type") == "BULK" else "wall (mass/area)"
        tk.Label(head, text=f"  {badge} · {sp.get('units', '')}  {sp.get('comment') or ''}", background="white",
                 foreground="#475569").pack(side="left")

        def rule(section):
            return next((r for r in m.rows[section] if r.get("species") == name), None)
        pipe, tank = rule("PIPES"), rule("TANKS")
        init = next((r for r in m.rows["QUALITY"] if r.get("species") == name and r.get("scope") == "GLOBAL"), None)
        sources = [r for r in m.rows["SOURCES"] if r.get("species") == name]
        vars_ = {}
        grid = ttk.Frame(inner, style="Card.TFrame"); grid.pack(fill="x", pady=(4, 0))
        rows = [("Pipes", "PIPES", pipe)]
        if sp.get("type") == "BULK":
            rows.append(("Tanks", "TANKS", tank))
        for r, (label, section, current) in enumerate(rows):
            ttk.Label(grid, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w")
            tvar = tk.StringVar(value=(current or {}).get("type", "RATE"))
            ttk.Combobox(grid, textvariable=tvar, values=msxlib.CHOICES[(section, "type")], state="readonly",
                         width=8).grid(row=r, column=1, padx=4, pady=1)
            evar = tk.StringVar(value=(current or {}).get("expression", ""))
            e = ttk.Entry(grid, textvariable=evar, font=("TkFixedFont", 10))
            e.grid(row=r, column=2, sticky="ew", pady=1)
            vars_[section] = (tvar, evar)
        grid.columnconfigure(2, weight=1)
        r = len(rows)
        ttk.Label(grid, text="Initial", style="Card.TLabel").grid(row=r, column=0, sticky="w")
        ivar = tk.StringVar(value=(init or {}).get("value", "0"))
        ttk.Entry(grid, textvariable=ivar, width=10).grid(row=r, column=1, sticky="w", padx=4)
        src_text = "; ".join(f"{s['type']} {s['strength']} @ {s['node']}" + (f" (pattern {s['pattern']})" if s.get("pattern") else "")
                             for s in sources) or "no sources"
        ttk.Label(grid, text=f"Sources: {src_text}", style="Card.TLabel").grid(row=r, column=2, sticky="w")
        btns = ttk.Frame(inner, style="Card.TFrame"); btns.pack(fill="x", pady=(6, 0))

        def apply():
            for section, (tvar, evar) in vars_.items():
                current = rule(section)
                if evar.get().strip():
                    if current is None:
                        m.rows[section].append({"type": tvar.get(), "species": name, "expression": evar.get().strip(), "comment": ""})
                    else:
                        current.update(type=tvar.get(), expression=evar.get().strip())
                elif current is not None:
                    m.rows[section].remove(current)
            g = next((q for q in m.rows["QUALITY"] if q.get("species") == name and q.get("scope") == "GLOBAL"), None)
            if g is None:
                m.rows["QUALITY"].append({"scope": "GLOBAL", "id": "", "species": name, "value": ivar.get(), "comment": ""})
            else:
                g["value"] = ivar.get()
            self.changed()
            self.actions.status(f"Updated compound {name}")

        def add_source():
            st = self.state
            if not st.sel_nodes:
                messagebox.showinfo("Add source", "Select a node on the map first (it becomes the injection point).", parent=self)
                return
            for i in sorted(st.sel_nodes):
                m.rows["SOURCES"].append({"type": "CONCEN", "node": st.topo.node_ids[i], "species": name,
                                          "strength": "1.0", "pattern": "", "comment": ""})
            self.changed(refresh=True)

        def remove():
            if not messagebox.askyesno("Remove compound", f"Remove {name} and all its rules?", parent=self):
                return
            m.rows["SPECIES"].remove(sp)
            for section in ("PIPES", "TANKS", "QUALITY", "SOURCES", "DIFFUSIVITY"):
                m.rows[section] = [q for q in m.rows[section] if q.get("species") != name]
            self.changed(refresh=True)
        ttk.Button(btns, text="Apply", command=apply).pack(side="left")
        ttk.Button(btns, text="Inject at selected node(s)", command=add_source).pack(side="left", padx=4)
        if self.state.active is not None and name in self.state.active.results.msx_node:
            ttk.Button(btns, text="Show on map", command=lambda: self.actions.map_species(name)).pack(side="left")
        ttk.Button(btns, text="Remove", command=remove).pack(side="right")

    # -------------------------------------------------------------- options
    def _sec_options(self):
        m = self.model
        ttk.Label(self.center, text="Title").pack(anchor="w")
        title = tk.Text(self.center, height=2, font=("TkDefaultFont", 10)); title.insert("1.0", m.title)
        title.pack(fill="x")
        grid = ttk.Frame(self.center); grid.pack(anchor="w", pady=8)
        vars_ = {}
        help_ = {"AREA_UNITS": "units of wall-species surface area", "RATE_UNITS": "time unit of rate expressions",
                 "SOLVER": "EUL fast/explicit · RK5 accurate · ROS2 stiff systems", "COUPLING": "FULL re-solves "
                 "equilibrium each step", "COMPILER": "compile expressions to C (needs compiler)",
                 "TIMESTEP": "water-quality step [s]", "ATOL": "default absolute tolerance",
                 "RTOL": "default relative tolerance", "SEGMENTS": "max pipe segments (MSX 2)",
                 "PECLET": "dispersion Peclet threshold (MSX 2)"}
        for r, (key, choices) in enumerate(msxlib.OPTION_CHOICES.items()):
            ttk.Label(grid, text=key).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=m.options.get(key, ""))
            if choices:
                ttk.Combobox(grid, textvariable=var, values=[""] + choices, state="readonly", width=12).grid(row=r, column=1, padx=6)
            else:
                ttk.Entry(grid, textvariable=var, width=14).grid(row=r, column=1, padx=6)
            ttk.Label(grid, text=help_.get(key, ""), style="Muted.TLabel").grid(row=r, column=2, sticky="w")
            vars_[key] = var

        def apply():
            m.title = title.get("1.0", "end").strip()
            for key, var in vars_.items():
                if var.get().strip():
                    m.options[key] = var.get().strip()
                else:
                    m.options.pop(key, None)
            self.changed()
        ttk.Button(self.center, text="Apply options", style="Accent.TButton", command=apply).pack(anchor="w")

    def _sec_report(self):
        m = self.model
        ttk.Label(self.center, text="[REPORT] lines (e.g. NODES ALL · SPECIES CL2 YES 3 · FILE report.txt)").pack(anchor="w")
        text = tk.Text(self.center, height=12, font=("TkFixedFont", 10)); text.pack(fill="both", expand=True)
        text.insert("1.0", "\n".join(m.report))

        def apply():
            m.report = [ln.strip() for ln in text.get("1.0", "end").splitlines() if ln.strip()]
            self.changed()
        ttk.Button(self.center, text="Apply", command=apply).pack(anchor="w", pady=4)

    def _sec_raw(self):
        bar = ttk.Frame(self.center); bar.pack(fill="x")
        ttk.Label(bar, text="Full .msx text. Edit freely, then apply to update all structured views.",
                  style="Muted.TLabel").pack(side="left")
        text = tk.Text(self.center, font=("TkFixedFont", 10), undo=True, wrap="none")
        text.insert("1.0", msxlib.write(self.model))
        ys = ttk.Scrollbar(self.center, command=text.yview); text.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y"); text.pack(fill="both", expand=True)
        for tag, color in (("section", "#7c3aed"), ("comment", "#64748b")):
            text.tag_configure(tag, foreground=color)

        def highlight(_e=None):
            text.tag_remove("section", "1.0", "end"); text.tag_remove("comment", "1.0", "end")
            for n, line in enumerate(text.get("1.0", "end").splitlines(), start=1):
                if line.strip().startswith("["):
                    text.tag_add("section", f"{n}.0", f"{n}.end")
                if ";" in line:
                    text.tag_add("comment", f"{n}.{line.index(';')}", f"{n}.end")
        highlight()
        text.bind("<KeyRelease>", highlight)

        def apply():
            try:
                self.state.msx = msxlib.parse(text.get("1.0", "end"))
            except Exception as exc:
                messagebox.showerror("MSX", f"Could not parse: {exc}", parent=self); return
            self.validate()
            self.actions.status("Raw MSX text applied.")
        ttk.Button(bar, text="Apply text", style="Accent.TButton", command=apply).pack(side="right")


class TableEditor(ttk.Frame):
    """Generic row editor for a tabular MSX section with an expression palette."""

    def __init__(self, master, studio: MsxStudio, section: str):
        super().__init__(master)
        self.studio, self.section = studio, section
        self.cols = msxlib.COLUMNS[section] + ["comment"]
        title = dict(SECTION_TITLES)[section]
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        self.tree = ttk.Treeview(self, columns=self.cols, show="headings", height=10, selectmode="browse")
        for c in self.cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=320 if c in ("expression", "multipliers") else (160 if c == "comment" else 90))
        self.tree.pack(fill="both", expand=True, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._load_row())
        btns = ttk.Frame(self); btns.pack(fill="x")
        for text, cmd in (("Add", self._add), ("Duplicate", self._dup), ("Delete", self._delete),
                          ("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1))):
            ttk.Button(btns, text=text, command=cmd, width=9 if len(text) > 1 else 3).pack(side="left", padx=1)
        if section in ("SOURCES", "QUALITY", "PARAMETERS"):
            ttk.Button(btns, text="Use selected map object", command=self._use_selection).pack(side="left", padx=8)
        form = ttk.LabelFrame(self, text="Row", padding=6); form.pack(fill="x", pady=6)
        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, tk.Widget] = {}
        for k, c in enumerate(self.cols):
            ttk.Label(form, text=c).grid(row=k, column=0, sticky="w")
            var = tk.StringVar()
            choices = msxlib.CHOICES.get((section, c))
            if c == "species":
                w = ttk.Combobox(form, textvariable=var, values=studio.model.species(), width=14)
            elif choices:
                w = ttk.Combobox(form, textvariable=var, values=choices, width=14)
            else:
                w = ttk.Entry(form, textvariable=var, font=("TkFixedFont", 10) if c == "expression" else None,
                              width=70 if c in ("expression", "multipliers", "comment") else 16)
            w.grid(row=k, column=1, sticky="ew" if c in ("expression", "multipliers", "comment") else "w", pady=1)
            self.vars[c], self.entries[c] = var, w
        form.columnconfigure(1, weight=1)
        ttk.Button(form, text="Update row", style="Accent.TButton", command=self._save_row).grid(
            row=len(self.cols), column=1, sticky="w", pady=4)
        if "expression" in self.cols:
            self._palette(form, len(self.cols) + 1)
        self._fill()

    def _palette(self, form, row):
        m = self.studio.model
        pal = ttk.Frame(form); pal.grid(row=row, column=0, columnspan=2, sticky="ew")
        groups = [("Species", m.species()), ("Coefficients", [r["name"] for r in m.rows["COEFFICIENTS"]]),
                  ("Terms", [r["name"] for r in m.rows["TERMS"]]), ("Hydraulics", list(msxlib.HYDRAULIC_VARS)),
                  ("Functions", ["exp(", "log(", "sqrt(", "abs(", "step(", "^"])]
        for g, (label, names) in enumerate(groups):
            ttk.Label(pal, text=label, style="Muted.TLabel").grid(row=g, column=0, sticky="w")
            line = ttk.Frame(pal); line.grid(row=g, column=1, sticky="w")
            for name in names[:24]:
                b = ttk.Button(line, text=name, style="Chip.TButton", command=lambda n=name: self._insert(n))
                b.pack(side="left", padx=1, pady=1)
                if name in msxlib.HYDRAULIC_VARS:
                    b.bind("<Enter>", lambda e, n=name: self.studio.actions.status(f"{n}: {msxlib.HYDRAULIC_VARS[n]}"))

    def _insert(self, text):
        e = self.entries["expression"]
        e.insert("insert", text)
        e.focus_set()

    def _rows(self) -> list[dict]:
        return self.studio.model.rows[self.section]

    def _fill(self, select: int | None = None):
        self.tree.delete(*self.tree.get_children())
        for k, r in enumerate(self._rows()):
            self.tree.insert("", "end", iid=str(k), values=[r.get(c, "") for c in self.cols])
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select)); self.tree.see(str(select))

    def _current(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _load_row(self):
        k = self._current()
        if k is None:
            return
        row = self._rows()[k]
        for c in self.cols:
            self.vars[c].set(row.get(c, ""))

    def _save_row(self):
        k = self._current()
        if k is None:
            self._add(); k = self._current()
        row = self._rows()[k]
        for c in self.cols:
            row[c] = self.vars[c].get().strip()
        self._fill(k)
        self.studio.changed()

    def _add(self):
        self._rows().append(msxlib.blank_row(self.section, self.studio.model))
        self._fill(len(self._rows()) - 1)
        self._load_row()
        self.studio.changed()

    def _dup(self):
        k = self._current()
        if k is None:
            return
        self._rows().insert(k + 1, dict(self._rows()[k]))
        self._fill(k + 1); self.studio.changed()

    def _delete(self):
        k = self._current()
        if k is None:
            return
        del self._rows()[k]
        self._fill(min(k, len(self._rows()) - 1)); self.studio.changed()

    def _move(self, d):
        k = self._current()
        rows = self._rows()
        if k is None or not 0 <= k + d < len(rows):
            return
        rows[k], rows[k + d] = rows[k + d], rows[k]
        self._fill(k + d)

    def _use_selection(self):
        st = self.studio.state
        if self.section == "SOURCES" and st.sel_nodes:
            self.vars["node"].set(st.topo.node_ids[next(iter(st.sel_nodes))])
        elif self.section == "QUALITY":
            if st.sel_nodes:
                self.vars["scope"].set("NODE"); self.vars["id"].set(st.topo.node_ids[next(iter(st.sel_nodes))])
            elif st.sel_links:
                self.vars["scope"].set("LINK"); self.vars["id"].set(st.topo.link_ids[next(iter(st.sel_links))])
        elif self.section == "PARAMETERS":
            if st.sel_links:
                self.vars["scope"].set("PIPE"); self.vars["id"].set(st.topo.link_ids[next(iter(st.sel_links))])
            elif st.sel_nodes:
                self.vars["scope"].set("TANK"); self.vars["id"].set(st.topo.node_ids[next(iter(st.sel_nodes))])
        else:
            messagebox.showinfo("Selection", "Select a suitable object on the map first.", parent=self)


class CompoundWizard(tk.Toplevel):
    """Create a species with its kinetics, initial condition and source in one step."""

    def __init__(self, studio: MsxStudio):
        super().__init__(studio)
        self.studio = studio
        self.title("Add compound")
        self.transient(studio.winfo_toplevel())
        m = studio.model
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)
        self.v = {k: tk.StringVar(value=v) for k, v in {
            "name": "", "type": "BULK", "units": "MG", "comment": "", "kinetics": list(KINETICS)[1],
            "k": "0.5", "K": "1.0", "X": (m.species() or [""])[0], "custom": "", "init": "0",
            "source": "", "strength": "1.0"}.items()}
        st = studio.state
        default_src = st.topo.node_ids[next(iter(st.sel_nodes))] if st.loaded and st.sel_nodes else \
            next((nid for nid, t in zip(st.topo.node_ids, st.topo.node_types) if t == "Reservoir"), "") if st.loaded else ""
        self.v["source"].set(default_src)
        self.same_tank = tk.BooleanVar(value=True)
        rows = [("Name", ttk.Entry(f, textvariable=self.v["name"], width=16)),
                ("Type", ttk.Combobox(f, textvariable=self.v["type"], values=["BULK", "WALL"], state="readonly", width=8)),
                ("Units", ttk.Combobox(f, textvariable=self.v["units"], values=msxlib.CHOICES[("SPECIES", "units")], width=8)),
                ("Description", ttk.Entry(f, textvariable=self.v["comment"], width=40)),
                ("Kinetics", ttk.Combobox(f, textvariable=self.v["kinetics"], values=list(KINETICS), state="readonly", width=40)),
                ("Rate k", ttk.Entry(f, textvariable=self.v["k"], width=10)),
                ("Half-sat. K", ttk.Entry(f, textvariable=self.v["K"], width=10)),
                ("Partner X", ttk.Combobox(f, textvariable=self.v["X"], values=m.species(), width=10)),
                ("Custom expr.", ttk.Entry(f, textvariable=self.v["custom"], width=40, font=("TkFixedFont", 10))),
                ("Initial (global)", ttk.Entry(f, textvariable=self.v["init"], width=10)),
                ("Inject at node", ttk.Entry(f, textvariable=self.v["source"], width=16)),
                ("Source conc.", ttk.Entry(f, textvariable=self.v["strength"], width=10))]
        for r, (label, w) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=2)
            w.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Checkbutton(f, text="Same reaction in tanks", variable=self.same_tank).grid(row=len(rows), column=1, sticky="w")
        self.preview = ttk.Label(f, text="", style="Muted.TLabel", font=("TkFixedFont", 9))
        self.preview.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=6)
        for var in self.v.values():
            var.trace_add("write", lambda *_: self._preview())
        b = ttk.Frame(f); b.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="e")
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Add compound", style="Accent.TButton", command=self._ok).pack(side="right", padx=4)
        self._preview()

    def _expression(self) -> tuple[str, list[tuple[str, str]]]:
        v = {k: var.get().strip() for k, var in self.v.items()}
        name = v["name"] or "S"
        tpl = KINETICS[v["kinetics"]]
        if not tpl:
            return v["custom"] or "0", []
        kname, Kname = f"k_{name}", f"K_{name}"
        expr = tpl.format(k=kname, K=Kname, S=name, X=v["X"] or "X")
        coeffs = []
        if "{k}" in tpl:
            coeffs.append((kname, v["k"]))
        if "{K}" in tpl:
            coeffs.append((Kname, v["K"]))
        return expr, coeffs

    def _preview(self):
        expr, coeffs = self._expression()
        text = f"RATE {self.v['name'].get() or 'S'}  {expr}"
        if coeffs:
            text += "\n" + "\n".join(f"PARAMETER {n} {val}" for n, val in coeffs)
        self.preview.configure(text=text)

    def _ok(self):
        m = self.studio.model
        name = self.v["name"].get().strip()
        if not name or not name.replace("_", "a").isalnum() or name in m.species():
            messagebox.showerror("Add compound", "Enter a new alphanumeric species name.", parent=self); return
        expr, coeffs = self._expression()
        m.rows["SPECIES"].append({"type": self.v["type"].get(), "name": name, "units": self.v["units"].get(),
                                  "atol": "", "rtol": "", "comment": self.v["comment"].get()})
        for n, val in coeffs:
            m.rows["COEFFICIENTS"].append({"type": "PARAMETER", "name": n, "value": val, "comment": f"{name} kinetics"})
        m.rows["PIPES"].append({"type": "RATE", "species": name, "expression": expr, "comment": ""})
        if self.v["type"].get() == "BULK" and self.same_tank.get():
            m.rows["TANKS"].append({"type": "RATE", "species": name, "expression": expr.replace("-(4/D)*", "-"), "comment": ""})
        init = self.v["init"].get().strip()
        if init and init != "0":
            m.rows["QUALITY"].append({"scope": "GLOBAL", "id": "", "species": name, "value": init, "comment": ""})
        src = self.v["source"].get().strip()
        if src and self.v["type"].get() == "BULK":
            m.rows["SOURCES"].append({"type": "CONCEN", "node": src, "species": name,
                                      "strength": self.v["strength"].get(), "pattern": "", "comment": ""})
        self.destroy()
        self.studio.changed(refresh=True)
