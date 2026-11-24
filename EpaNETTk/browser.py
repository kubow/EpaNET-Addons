"""Data browser: attribute/result tables, queries, time-series and scenario comparison."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from epanet_addons import network as netlib
from .mapview import fmt
from .state import RESULT_LABELS, AppState
from .widgets import sortable_tree

MAX_ROWS = 20000


class DataBrowser(ttk.Frame):
    def __init__(self, master, state: AppState, actions):
        super().__init__(master)
        self.state, self.actions = state, actions
        self.kind = tk.StringVar(value="node")
        self.search = tk.StringVar()
        self.query = tk.StringVar()
        self._df: pd.DataFrame | None = None
        self._syncing = False

        bar = ttk.Frame(self, padding=(6, 6, 6, 2)); bar.pack(fill="x")
        ttk.Radiobutton(bar, text="Nodes", value="node", variable=self.kind, command=self.reload,
                        style="Toolbutton").pack(side="left")
        ttk.Radiobutton(bar, text="Links", value="link", variable=self.kind, command=self.reload,
                        style="Toolbutton").pack(side="left", padx=(0, 10))
        ttk.Label(bar, text="Find").pack(side="left")
        e = ttk.Entry(bar, textvariable=self.search, width=14); e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda ev: self._fill())
        ttk.Label(bar, text="Query").pack(side="left", padx=(8, 0))
        q = ttk.Entry(bar, textvariable=self.query, width=38); q.pack(side="left", padx=4, fill="x", expand=True)
        q.bind("<Return>", lambda ev: self._fill())
        ttk.Button(bar, text="Filter", command=self._fill).pack(side="left")
        ttk.Button(bar, text="Select on map", command=self._select_all_rows).pack(side="left", padx=4)
        ttk.Button(bar, text="Export CSV…", command=self._export).pack(side="left")
        self.count = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 0))
        self.count.pack(anchor="w")
        ttk.Label(self, text="Query examples:  diameter < 150 and type == 'Pipe'   ·   pressure < 25   ·   "
                             "`msx:CL2` < 0.2   ·   id.str.startswith('J')", style="Muted.TLabel",
                  padding=(8, 0)).pack(anchor="w")

        pane = ttk.PanedWindow(self, orient="vertical"); pane.pack(fill="both", expand=True, pady=(4, 0))
        top = ttk.Frame(pane); pane.add(top, weight=3)
        self.tree = ttk.Treeview(top, show="headings", selectmode="extended")
        ys = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(top, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); ys.grid(row=0, column=1, sticky="ns"); xs.grid(row=1, column=0, sticky="ew")
        top.rowconfigure(0, weight=1); top.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)
        self.tree.bind("<Double-Button-1>", lambda e: self.actions.zoom_selection())

        bottom = ttk.Notebook(pane); pane.add(bottom, weight=2)
        self._build_series(bottom)
        self._build_compare(bottom)
        self._build_distribution(bottom)

        b = state.bus
        b.on("model", lambda **_: self.reload())
        b.on("properties", lambda **_: self.reload())
        b.on("results", lambda **_: (self.reload(), self._refresh_compare_choices()))
        b.on("scenarios", lambda **_: self._refresh_compare_choices())
        b.on("selection", lambda **kw: self._sync_selection(kw.get("source")))
        self._time_job = None
        b.on("time", lambda **_: self._schedule_time_refresh())

    # ---------------------------------------------------------------- table
    def frame(self) -> pd.DataFrame | None:
        st = self.state
        if not st.loaded:
            return None
        kind = self.kind.get()
        props = st.table(kind)
        lead = ["id", "type"] + (["from", "to"] if kind == "link" else [])
        df = props[lead].copy()
        if st.active is not None:
            for var in st.active.results.variables(kind):
                if var in ("status", "setting"):
                    continue
                vals = st.values(kind, f"res:{var}", stat=st.style.stat, delta=False)
                if vals is not None:
                    df[var] = vals
                if st.style.delta and st.baseline is not None and st.baseline is not st.active:
                    d = st.values(kind, f"res:{var}", stat=st.style.stat, delta=True)
                    if d is not None:
                        df[f"Δ{var}"] = d
        for col in props.columns:
            if col not in lead:
                df[col] = props[col]
        return df

    def reload(self):
        self._df = self.frame()
        self._fill()
        self._refresh_series_choices()

    def _filtered(self) -> pd.DataFrame | None:
        df = self._df
        if df is None:
            return None
        text = self.search.get().strip().lower()
        if text:
            df = df[df["id"].astype(str).str.lower().str.contains(text, regex=False)]
        q = self.query.get().strip()
        self._query_error = None
        if q:
            try:
                df = df.query(q, engine="python")
            except Exception as exc:
                self._query_error = str(exc)
        return df

    def _fill(self):
        tree = self.tree
        tree.delete(*tree.get_children())
        df = self._filtered()
        if df is None:
            tree["columns"] = (); self.count.configure(text="No model loaded."); return
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            label = RESULT_LABELS.get(c, c)
            tree.heading(c, text=label)
            tree.column(c, width=90 if c not in ("id",) else 110, anchor="e" if c not in ("id", "type", "from", "to", "pattern", "status") else "w",
                        stretch=False)
        sortable_tree(tree)
        values = df.to_numpy(dtype=object)
        for pos, (idx, row) in enumerate(zip(df.index, values)):
            if pos >= MAX_ROWS:
                break
            tree.insert("", "end", iid=str(idx), values=[fmt(v) if isinstance(v, (float, np.floating)) else v for v in row])
        shown = min(len(df), MAX_ROWS)
        total = len(self._df)
        if self._query_error:
            self.count.configure(text=f"Query error: {self._query_error}", foreground="#b91c1c")
        else:
            self.count.configure(text=f"{shown} of {total} {self.kind.get()}s" +
                                 (f" (first {MAX_ROWS} shown)" if len(df) > MAX_ROWS else ""), foreground="")
        self._sync_selection("")

    def _schedule_time_refresh(self):
        if self.state.style.stat != "At time" or not self.winfo_ismapped():
            return
        if self._time_job:
            self.after_cancel(self._time_job)
        self._time_job = self.after(300, self.reload)

    def _tree_selected(self, _e=None):
        if self._syncing:
            return
        idx = [int(i) for i in self.tree.selection()]
        current = self.state.sel_nodes if self.kind.get() == "node" else self.state.sel_links
        if set(idx) == current:  # echo of a programmatic sync – keep the other kind's selection
            return
        if self.kind.get() == "node":
            self.state.select(nodes=idx, source="browser")
        else:
            self.state.select(links=idx, source="browser")
        self._draw_series()

    def _sync_selection(self, source):
        if source == "browser":
            return
        st = self.state
        sel = st.sel_nodes if self.kind.get() == "node" else st.sel_links
        items = [str(i) for i in sel if self.tree.exists(str(i))]
        self._syncing = True
        try:
            self.tree.selection_set(items)
            if items:
                self.tree.see(items[0])
        finally:
            self._syncing = False
        self._draw_series()

    def _select_all_rows(self):
        df = self._filtered()
        if df is None:
            return
        idx = df.index.tolist()
        if self.kind.get() == "node":
            self.state.select(nodes=idx, source="browser-all")
        else:
            self.state.select(links=idx, source="browser-all")
        self.actions.status(f"Selected {len(idx)} {self.kind.get()}s on the map.")

    def _export(self):
        df = self._filtered()
        if df is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], parent=self)
        if path:
            df.to_csv(path, index=False)
            self.actions.status(f"Exported {len(df)} rows to {path}")

    # ---------------------------------------------------------- time series
    def _build_series(self, nb):
        frame = ttk.Frame(nb, padding=4); nb.add(frame, text="Time series")
        bar = ttk.Frame(frame); bar.pack(fill="x")
        ttk.Label(bar, text="Variable").pack(side="left")
        self.series_var = tk.StringVar()
        self.series_combo = ttk.Combobox(bar, textvariable=self.series_var, state="readonly", width=24)
        self.series_combo.pack(side="left", padx=4)
        self.series_combo.bind("<<ComboboxSelected>>", lambda e: self._draw_series())
        self.all_scen = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="overlay all scenarios", variable=self.all_scen,
                        command=self._draw_series).pack(side="left", padx=6)
        ttk.Label(bar, text="Selected rows are plotted (max 12).", style="Muted.TLabel").pack(side="left", padx=8)
        self.s_fig = Figure(figsize=(6, 2.4), dpi=90)
        self.s_ax = self.s_fig.add_subplot(111)
        self.s_canvas = FigureCanvasTkAgg(self.s_fig, master=frame)
        NavigationToolbar2Tk(self.s_canvas, frame, pack_toolbar=False).pack(side="bottom", fill="x")
        self.s_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _refresh_series_choices(self):
        st = self.state
        if st.active is None:
            self.series_combo["values"] = []; return
        variables = st.active.results.variables(self.kind.get())
        labels = [RESULT_LABELS.get(v, v[4:] + " (MSX)" if v.startswith("msx:") else v) for v in variables]
        self._series_map = dict(zip(labels, variables))
        self.series_combo["values"] = labels
        if self.series_var.get() not in labels and labels:
            self.series_var.set(labels[0])

    def _draw_series(self):
        st = self.state
        ax = self.s_ax
        ax.clear()
        var = getattr(self, "_series_map", {}).get(self.series_var.get())
        kind = self.kind.get()
        sel = sorted(st.sel_nodes if kind == "node" else st.sel_links)[:12]
        if st.active is None or var is None or not sel:
            ax.text(0.5, 0.5, "Select rows (or objects on the map) to plot", ha="center", va="center",
                    transform=ax.transAxes, color="#64748b")
            self.s_canvas.draw_idle(); return
        ids = st.topo.node_ids if kind == "node" else st.topo.link_ids
        scenarios = st.scenarios if self.all_scen.get() else [st.active]
        styles = ["-", "--", ":", "-."]
        for si, scen in enumerate(scenarios):
            found = scen.results.series(kind, var)
            if found is None:
                continue
            times, data = found
            sid = {v: k for k, v in enumerate(scen.results.node_ids if kind == "node" else scen.results.link_ids)}
            for n, i in enumerate(sel):
                col = sid.get(ids[i])
                if col is None:
                    continue
                label = ids[i] + (f" · {scen.name}" if len(scenarios) > 1 else "")
                ax.plot(times / 3600, data[:, col], ls=styles[si % 4], color=f"C{n % 10}", lw=1.6, label=label)
        ax.axvline(st.time_s / 3600, color="#ef4444", lw=1, ls="--")
        ax.set_xlabel("time [h]"); ax.set_ylabel(self.series_var.get()); ax.grid(alpha=0.3)
        ax.legend(fontsize=7, ncol=3, loc="best")
        self.s_fig.tight_layout()
        self.s_canvas.draw_idle()

    # -------------------------------------------------------------- compare
    def _build_compare(self, nb):
        frame = ttk.Frame(nb, padding=4); nb.add(frame, text="Scenario compare")
        bar = ttk.Frame(frame); bar.pack(fill="x")
        self.cmp_a, self.cmp_b = tk.StringVar(), tk.StringVar()
        self.cmp_var, self.cmp_stat = tk.StringVar(), tk.StringVar(value="Maximum")
        ttk.Label(bar, text="A").pack(side="left")
        self.cmp_a_combo = ttk.Combobox(bar, textvariable=self.cmp_a, state="readonly", width=12)
        self.cmp_a_combo.pack(side="left", padx=2)
        ttk.Label(bar, text="B").pack(side="left")
        self.cmp_b_combo = ttk.Combobox(bar, textvariable=self.cmp_b, state="readonly", width=12)
        self.cmp_b_combo.pack(side="left", padx=2)
        self.cmp_var_combo = ttk.Combobox(bar, textvariable=self.cmp_var, state="readonly", width=18)
        self.cmp_var_combo.pack(side="left", padx=6)
        ttk.Combobox(bar, textvariable=self.cmp_stat, values=netlib.STATISTICS, state="readonly", width=9).pack(side="left")
        ttk.Button(bar, text="Compare", command=self._compare).pack(side="left", padx=4)
        ttk.Button(bar, text="Δ on map", command=self._delta_on_map).pack(side="left")
        body = ttk.PanedWindow(frame, orient="horizontal"); body.pack(fill="both", expand=True, pady=4)
        left = ttk.Frame(body); body.add(left, weight=3)
        self.cmp_tree = ttk.Treeview(left, show="headings", columns=("id", "A", "B", "delta", "delta_pct"))
        for c, w in (("id", 100), ("A", 80), ("B", 80), ("delta", 80), ("delta_pct", 70)):
            self.cmp_tree.heading(c, text={"delta": "Δ", "delta_pct": "Δ %"}.get(c, c)); self.cmp_tree.column(c, width=w, anchor="e")
        ys = ttk.Scrollbar(left, command=self.cmp_tree.yview); self.cmp_tree.configure(yscrollcommand=ys.set)
        self.cmp_tree.pack(side="left", fill="both", expand=True); ys.pack(side="left", fill="y")
        self.cmp_tree.bind("<<TreeviewSelect>>", self._cmp_selected)
        sortable_tree(self.cmp_tree)
        right = ttk.Frame(body); body.add(right, weight=2)
        self.cmp_summary = tk.Text(right, height=6, font=("TkFixedFont", 9), relief="flat", background="#f8fafc")
        self.cmp_summary.pack(fill="x")
        self.c_fig = Figure(figsize=(3, 2), dpi=90)
        self.c_ax = self.c_fig.add_subplot(111)
        self.c_canvas = FigureCanvasTkAgg(self.c_fig, master=right)
        self.c_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._cmp_kind = "node"

    def _refresh_compare_choices(self):
        st = self.state
        names = st.scenario_names()
        self.cmp_a_combo["values"] = names; self.cmp_b_combo["values"] = names
        if names:
            if self.cmp_a.get() not in names:
                self.cmp_a.set(st.baseline.name if st.baseline else names[0])
            if self.cmp_b.get() not in names:
                self.cmp_b.set(st.active.name if st.active else names[-1])
        choices = []
        if st.active is not None:
            for kind in ("node", "link"):
                for var in st.active.results.variables(kind):
                    if var not in ("status", "setting"):
                        choices.append(f"{kind}: {RESULT_LABELS.get(var, var)}")
        self._cmp_choices = choices
        self.cmp_var_combo["values"] = choices
        if self.cmp_var.get() not in choices and choices:
            self.cmp_var.set(choices[0])

    def _cmp_parse(self):
        text = self.cmp_var.get()
        kind, _, label = text.partition(": ")
        inv = {v: k for k, v in RESULT_LABELS.items()}
        return kind, inv.get(label, label)

    def _compare(self):
        st = self.state
        try:
            a = next(s for s in st.scenarios if s.name == self.cmp_a.get())
            b = next(s for s in st.scenarios if s.name == self.cmp_b.get())
        except StopIteration:
            messagebox.showinfo("Compare", "Run at least two scenarios (edit the model between runs).", parent=self)
            return
        kind, var = self._cmp_parse()
        try:
            df = netlib.compare(a, b, kind, var, self.cmp_stat.get(), st.time_s)
        except ValueError as exc:
            messagebox.showerror("Compare", str(exc), parent=self); return
        self._cmp_kind = kind
        df = df.reindex(df["delta"].abs().sort_values(ascending=False).index)
        tree = self.cmp_tree
        tree.delete(*tree.get_children())
        for _, row in df.head(MAX_ROWS).iterrows():
            tree.insert("", "end", values=(row["id"], fmt(row["A"]), fmt(row["B"]), fmt(row["delta"]), fmt(row["delta_pct"])))
        d = df["delta"].to_numpy()
        changed = int((np.abs(d) > 1e-9).sum())
        txt = (f"{a.name} → {b.name}  ({self.cmp_stat.get().lower()} {var})\n"
               f"objects compared  {len(df)}\nchanged           {changed}\n"
               f"mean Δ            {fmt(np.nanmean(d))}\nlargest increase  {fmt(np.nanmax(d))}\n"
               f"largest decrease  {fmt(np.nanmin(d))}")
        self.cmp_summary.delete("1.0", "end"); self.cmp_summary.insert("end", txt)
        ax = self.c_ax; ax.clear()
        ax.scatter(df["A"], df["B"], s=6, alpha=0.6)
        lo = np.nanmin([df["A"].min(), df["B"].min()]); hi = np.nanmax([df["A"].max(), df["B"].max()])
        ax.plot([lo, hi], [lo, hi], color="#94a3b8", lw=1)
        ax.set_xlabel(a.name, fontsize=8); ax.set_ylabel(b.name, fontsize=8); ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3); self.c_fig.tight_layout(); self.c_canvas.draw_idle()

    def _cmp_selected(self, _e=None):
        st = self.state
        ids = [self.cmp_tree.set(i, "id") for i in self.cmp_tree.selection()]
        lookup = st.topo.node_index if self._cmp_kind == "node" else st.topo.link_index
        idx = [lookup[i] for i in ids if i in lookup]
        if self._cmp_kind == "node":
            st.select(nodes=idx, source="compare")
        else:
            st.select(links=idx, source="compare")

    def _delta_on_map(self):
        st = self.state
        try:
            a = next(s for s in st.scenarios if s.name == self.cmp_a.get())
            b = next(s for s in st.scenarios if s.name == self.cmp_b.get())
        except StopIteration:
            return
        kind, var = self._cmp_parse()
        st.baseline, st.active = a, b
        st.style.delta = True
        st.style.stat = self.cmp_stat.get()
        if kind == "node":
            st.style.node_var = f"res:{var}"
        else:
            st.style.link_var = f"res:{var}"
        st.bus.emit("scenarios"); st.bus.emit("results"); st.bus.emit("style")
        self.actions.show_map()

    # --------------------------------------------------------- distribution
    def _build_distribution(self, nb):
        frame = ttk.Frame(nb, padding=4); nb.add(frame, text="Distribution")
        bar = ttk.Frame(frame); bar.pack(fill="x")
        ttk.Label(bar, text="Column").pack(side="left")
        self.dist_col = tk.StringVar()
        self.dist_combo = ttk.Combobox(bar, textvariable=self.dist_col, state="readonly", width=20)
        self.dist_combo.pack(side="left", padx=4)
        self.dist_combo.bind("<<ComboboxSelected>>", lambda e: self._draw_dist())
        self.dist_combo.bind("<Button-1>", lambda e: self._dist_choices())
        ttk.Label(bar, text="Histogram + cumulative share of the filtered rows", style="Muted.TLabel").pack(side="left", padx=6)
        self.d_fig = Figure(figsize=(6, 2.4), dpi=90)
        self.d_ax = self.d_fig.add_subplot(111)
        self.d_ax2 = self.d_ax.twinx()
        self.d_canvas = FigureCanvasTkAgg(self.d_fig, master=frame)
        self.d_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _dist_choices(self):
        df = self._filtered()
        if df is None:
            return
        cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        self.dist_combo["values"] = cols

    def _draw_dist(self):
        df = self._filtered()
        col = self.dist_col.get()
        ax, ax2 = self.d_ax, self.d_ax2
        ax.clear(); ax2.clear()
        if df is None or col not in df:
            self.d_canvas.draw_idle(); return
        v = pd.to_numeric(df[col], errors="coerce").dropna().to_numpy()
        if v.size:
            ax.hist(v, bins=min(40, max(5, int(np.sqrt(v.size)))), color="#60a5fa", edgecolor="white")
            s = np.sort(v)
            ax2.plot(s, np.arange(1, s.size + 1) / s.size * 100, color="#dc2626", lw=1.5)
            ax2.set_ylabel("cumulative %", fontsize=8); ax2.set_ylim(0, 100)
            ax.set_title(f"{col}: n={v.size}, median {fmt(np.median(v))}, p5 {fmt(np.percentile(v, 5))}, "
                         f"p95 {fmt(np.percentile(v, 95))}", fontsize=9)
        ax.set_xlabel(col); ax.set_ylabel("count"); ax.grid(alpha=0.3)
        self.d_fig.tight_layout(); self.d_canvas.draw_idle()
