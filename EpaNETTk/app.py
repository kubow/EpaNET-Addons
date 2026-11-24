"""EPANET Workbench – Tkinter desktop application shell."""
from __future__ import annotations

import queue
import tempfile
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np

from epanet_addons import crs as crslib
from epanet_addons import msx as msxlib
from epanet_addons import network as netlib
from epanet_addons.projects import LocalProjectStore
from .browser import DataBrowser
from .dialogs import CRSDialog, PatternEditor, ReportWindow, RunSettingsDialog
from .inspector import Inspector
from .mapview import MapView
from .msx_studio import MsxStudio
from .panels import AnalyticsPanel
from .state import AppState
from . import style

ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = ROOT / "projects"


class Workbench:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("EPANET Workbench")
        root.geometry("1500x920")
        root.minsize(1100, 680)
        style.apply(root)
        self.state = AppState()
        self.store = LocalProjectStore(STORE_DIR)
        self._jobs: queue.Queue = queue.Queue()
        self._play_job = None
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_timebar()
        self._build_statusbar()
        b = self.state.bus
        b.on("results", lambda **_: self._results_changed())
        b.on("scenarios", lambda **_: self._results_changed())
        b.on("model", lambda **_: self._model_changed())
        b.on("properties", lambda **_: self._model_changed())
        b.on("selection", lambda **kw: self._selection_changed(kw.get("source")))
        b.on("time", lambda **_: self._sync_time())
        root.bind("<Control-o>", lambda e: self.open_inp())
        root.bind("<Control-s>", lambda e: self.save_project())
        root.bind("<F5>", lambda e: self.run())
        root.bind("<F6>", lambda e: self.run_msx())
        root.bind("<space>", lambda e: self.toggle_play() if not isinstance(e.widget, (tk.Entry, ttk.Entry, tk.Text)) else None)
        root.after(100, self._poll_jobs)
        self._model_changed()

    # ================================================================ layout
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Open EPANET model…", accelerator="Ctrl+O", command=self.open_inp)
        f.add_command(label="Import MIKE URBAN model (.mdb)…", command=self.import_mdb)
        f.add_separator()
        f.add_command(label="Open project…", command=self.open_project)
        f.add_command(label="Save project", accelerator="Ctrl+S", command=self.save_project)
        f.add_command(label="Save project as…", command=lambda: self.save_project(ask=True))
        f.add_command(label="Export EPANET .inp…", command=self.export_inp)
        f.add_separator()
        f.add_command(label="Add GeoPackage overlay…", command=self.add_overlay)
        f.add_separator()
        f.add_command(label="Quit", command=self.root.destroy)
        m.add_cascade(label="File", menu=f)
        n = tk.Menu(m, tearoff=0)
        n.add_command(label="Coordinate system…", command=self.choose_crs)
        n.add_command(label="Simulation settings…", command=self.edit_settings)
        n.add_command(label="Time patterns…", command=self.edit_patterns)
        n.add_separator()
        n.add_command(label="Conversion report…", command=self.show_report)
        m.add_cascade(label="Network", menu=n)
        r = tk.Menu(m, tearoff=0)
        r.add_command(label="Run hydraulics / quality", accelerator="F5", command=self.run)
        r.add_command(label="Run hydraulics + MSX", accelerator="F6", command=self.run_msx)
        m.add_cascade(label="Run", menu=r)
        v = tk.Menu(m, tearoff=0)
        v.add_command(label="Zoom to network", command=lambda: self.map.zoom_extent())
        v.add_command(label="Zoom to selection", command=self.zoom_selection)
        v.add_command(label="Retry failed basemap tiles", command=self._retry_tiles)
        m.add_cascade(label="View", menu=v)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Engine capabilities", command=self.show_capabilities)
        h.add_command(label="Shortcuts", command=self.show_shortcuts)
        m.add_cascade(label="Help", menu=h)
        self.root.configure(menu=m)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(6, 4), style="Toolbar.TFrame")
        bar.pack(fill="x")
        def btn(text, cmd, tip=None, st="Tool.TButton"):
            b = ttk.Button(bar, text=text, command=cmd, style=st)
            b.pack(side="left", padx=1)
            if tip:
                b.bind("<Enter>", lambda e: self.status(tip))
            return b
        btn("📂 Open", self.open_inp, "Open an EPANET .inp model")
        btn("⇪ MIKE URBAN", self.import_mdb, "Import a MIKE URBAN Classic water .mdb (creates EPANET model + GeoPackage)")
        btn("💾 Save", self.save_project, "Save the local project (model, chemistry, scenarios, CRS)")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.run_btn = btn("▶ Run", self.run, "Run hydraulics and standard quality (F5)", "Accent.TButton")
        btn("⚗ Run + MSX", self.run_msx, "Run hydraulics with the MSX chemistry from the MSX studio (F6)")
        btn("⚙", self.edit_settings, "Simulation settings")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.mode = tk.StringVar(value="select")
        for val, text, tip in (("select", "⬚ Select", "Click to select · Shift+drag box-select · Ctrl+click add"),
                               ("add_junction", "＋ Junction", "Click on the map to add a junction"),
                               ("add_pipe", "╱ Pipe", "Click two nodes to connect them with a pipe"),
                               ("move", "✥ Move", "Drag nodes to new positions")):
            b = ttk.Radiobutton(bar, text=text, value=val, variable=self.mode, style="Toolbutton",
                                command=lambda: self.map.set_mode(self.mode.get()))
            b.pack(side="left", padx=1)
            b.bind("<Enter>", lambda e, t=tip: self.status(t))
        btn("✖ Delete", self.delete_selection, "Delete selected objects (Del)")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        btn("⤢ Extent", lambda: self.map.zoom_extent(), "Zoom to the whole network")
        self.crs_btn = ttk.Button(bar, text="CRS: –", command=self.choose_crs, style="Crs.TButton")
        self.crs_btn.pack(side="right")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.progress.pack(side="right", padx=8)

    def _build_body(self):
        outer = ttk.PanedWindow(self.root, orient="horizontal")
        outer.pack(fill="both", expand=True)
        self.panel = AnalyticsPanel(outer, self.state, self)
        outer.add(self.panel, weight=0)
        self.nb = ttk.Notebook(outer)
        outer.add(self.nb, weight=5)
        self.map = MapView(self.nb, self.state, self)
        self.nb.add(self.map, text="  Map  ")
        self.browser = DataBrowser(self.nb, self.state, self)
        self.nb.add(self.browser, text="  Data browser  ")
        self.msx = MsxStudio(self.nb, self.state, self)
        self.nb.add(self.msx, text="  MSX studio  ")
        self.inspector = Inspector(outer, self.state, self)
        outer.add(self.inspector, weight=0)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        self.root.update_idletasks()
        try:
            outer.sashpos(0, 300)
            outer.sashpos(1, self.root.winfo_width() - 330)
        except tk.TclError:
            pass

    def _build_timebar(self):
        bar = ttk.Frame(self.root, padding=(8, 3), style="Toolbar.TFrame")
        bar.pack(fill="x")
        self.play_btn = ttk.Button(bar, text="▶", width=3, command=self.toggle_play)
        self.play_btn.pack(side="left")
        ttk.Button(bar, text="⏮", width=3, command=lambda: self._step_time(-1)).pack(side="left")
        ttk.Button(bar, text="⏭", width=3, command=lambda: self._step_time(1)).pack(side="left")
        self.time_var = tk.DoubleVar(value=0)
        self.time_scale = ttk.Scale(bar, from_=0, to=1, variable=self.time_var, command=self._time_moved)
        self.time_scale.pack(side="left", fill="x", expand=True, padx=8)
        self.time_label = ttk.Label(bar, text="no results", width=26)
        self.time_label.pack(side="left")
        ttk.Label(bar, text="speed").pack(side="left")
        self.speed = tk.StringVar(value="1×")
        ttk.Combobox(bar, textvariable=self.speed, values=["0.5×", "1×", "2×", "4×", "8×"], width=4,
                     state="readonly").pack(side="left", padx=4)

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, padding=(8, 2), style="Status.TFrame")
        bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.coord_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.coord_var, style="Status.TLabel").pack(side="right")

    # ============================================================ callbacks
    def status(self, text: str):
        self.status_var.set(text)

    def coords(self, text: str):
        self.coord_var.set(text)

    def show_map(self):
        self.nb.select(self.map)

    def show_browser(self, kind: str = "node"):
        self.browser.kind.set(kind)
        self.browser.reload()
        self.nb.select(self.browser)

    def show_series(self, kind: str):
        self.show_browser(kind)

    def zoom_selection(self):
        self.show_map()
        self.map.zoom_selection()

    def basemap_changed(self):
        self.map.zoom_extent() if not self.state.loaded else None

    def _retry_tiles(self):
        self.map.tiles.retry_failed(); self.map.redraw()

    def _tab_changed(self):
        if self.nb.select() == str(self.browser):
            self.browser.reload()

    def _selection_changed(self, source):
        pass

    def _model_changed(self):
        st = self.state
        name = st.project_name or (st.source_path.name if st.source_path else "no model")
        self.root.title(f"EPANET Workbench — {name}" + (" •" if st.stale else ""))
        local = st.crs.is_local
        self.crs_btn.configure(text=("⚠ CRS: local – assign…" if local else f"🌐 {st.crs.code}"))

    def _results_changed(self):
        st = self.state
        if st.active is None:
            self.time_scale.configure(to=1); self.time_label.configure(text="no results"); return
        horizon = st.active.results.horizon
        self.time_scale.configure(to=max(horizon, 1))
        if st.time_s > horizon:
            st.set_time(0)
        self._update_time_label()
        self._model_changed()

    # ================================================================= time
    def _time_step(self) -> float:
        st = self.state
        if st.active is None:
            return 3600
        t = st.active.results.time
        uses_msx = any(k.startswith("res:msx:") for k in (st.style.node_var, st.style.link_var))
        if uses_msx and st.active.results.msx_time is not None and len(st.active.results.msx_time) > 1:
            t = st.active.results.msx_time
            return float(max(np.median(np.diff(t)), 1)) * max(1, len(t) // 200)
        return float(np.median(np.diff(t))) if len(t) > 1 else 3600

    def _sync_time(self):
        if abs(self.time_var.get() - self.state.time_s) >= 1:
            self.time_var.set(self.state.time_s)
        self._update_time_label()

    def _time_moved(self, value):
        st = self.state
        if st.active is None:
            return
        v = float(value)
        step = self._time_step()
        v = round(v / step) * step
        if abs(v - st.time_s) >= 1:
            st.set_time(v)
        self._update_time_label()

    def _update_time_label(self):
        st = self.state
        t = st.time_s
        day, rem = divmod(int(t), 86400)
        self.time_label.configure(text=f"t = {('%dd ' % day) if day else ''}{rem // 3600:02d}:{rem % 3600 // 60:02d}"
                                       f"  / {st.active.results.horizon / 3600:g} h" if st.active else "")

    def _step_time(self, d: int):
        st = self.state
        if st.active is None:
            return
        t = st.time_s + d * self._time_step()
        horizon = st.active.results.horizon
        t = 0 if t > horizon else (horizon if t < 0 else t)
        st.set_time(t)

    def toggle_play(self):
        if self._play_job:
            self.after_cancel_play(); return
        if self.state.active is None:
            return
        self.play_btn.configure(text="⏸")
        self._play_tick()

    def after_cancel_play(self):
        if self._play_job:
            self.root.after_cancel(self._play_job)
        self._play_job = None
        self.play_btn.configure(text="▶")

    def _play_tick(self):
        self._step_time(1)
        speed = float(self.speed.get().rstrip("×"))
        self._play_job = self.root.after(int(600 / speed), self._play_tick)

    # ============================================================ jobs
    def job(self, label: str, work, done):
        if self.state.busy:
            messagebox.showinfo("Busy", "Another task is still running.", parent=self.root); return
        self.state.busy = True
        self.status(label + "…")
        self.progress.start(12)
        self.root.configure(cursor="watch")

        def runner():
            try:
                self._jobs.put((done, work(), None))
            except Exception as exc:
                self._jobs.put((done, None, (exc, traceback.format_exc())))
        threading.Thread(target=runner, daemon=True).start()

    def _poll_jobs(self):
        try:
            while True:
                done, result, error = self._jobs.get_nowait()
                self.state.busy = False
                self.progress.stop()
                self.root.configure(cursor="")
                if error:
                    exc, tb = error
                    self.status(f"Failed: {exc}")
                    messagebox.showerror("Task failed", f"{exc}\n\n{tb[-1500:]}", parent=self.root)
                else:
                    try:
                        done(result)
                    except Exception as exc:
                        messagebox.showerror("Error", f"{exc}\n\n{traceback.format_exc()[-1500:]}", parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_jobs)

    # ============================================================ loading
    def _reset_session(self):
        st = self.state
        self.after_cancel_play()
        st.scenarios.clear(); st.active = st.baseline = None
        st.stale = False; st.time_s = 0
        st.style.node_var = st.style.link_var = "type"
        st.style.delta = False; st.style.filter_op = ""; st.style.fixed_range.clear()
        self.time_var.set(0)

    def open_inp(self, path: Path | None = None):
        path = path or filedialog.askopenfilename(filetypes=[("EPANET input", "*.inp"), ("All", "*")])
        if not path:
            return
        path = Path(path)

        def work():
            self.state.wrapper.load_file(path)
        def done(_):
            st = self.state
            self._reset_session()
            st.source_path, st.project_name, st.gpkg_path = path, None, None
            st.run_settings = netlib.RunSettings.from_network(st.net)
            self._after_load(hint=None)
            sibling = path.with_suffix(".msx")
            if sibling.is_file():
                self.msx.load_file(sibling)
        self.job(f"Opening {path.name}", work, done)

    def import_mdb(self, path: Path | None = None):
        path = path or filedialog.askopenfilename(filetypes=[("MIKE URBAN model", "*.mdb"), ("All", "*")])
        if not path:
            return
        path = Path(path)
        workdir = Path(tempfile.mkdtemp(prefix="epanet-wb-mdb-"))

        def work():
            from epanet_addons.mike_urban.importer import import_mike_urban_mdb
            report = self.state.wrapper.load_mike_urban_mdb(path)
            gpkg = workdir / (path.stem + ".gpkg")
            try:
                import_mike_urban_mdb(path, gpkg)
            except Exception as exc:  # spatial assets are optional for calculations
                report = dict(report, geopackage_error=str(exc)); gpkg = None
            return report, gpkg

        def done(result):
            report, gpkg = result
            st = self.state
            self._reset_session()
            st.source_path, st.project_name, st.gpkg_path = path, None, gpkg
            st.run_settings = netlib.RunSettings.from_network(st.net)
            epsg = (report.get("source_crs") or {}).get("epsg")
            self._after_load(hint=f"EPSG:{epsg}" if epsg else None)
            flagged = [k for k, v in report.items() if k.startswith(("omitted", "unknown", "untranslated", "excluded")) and v]
            msg = f"Imported {path.name}: {len(st.topo.node_ids)} nodes, {len(st.topo.link_ids)} links."
            if flagged:
                msg += "\n\nReview needed: " + ", ".join(flagged) + "\n(Network ▸ Conversion report)"
            messagebox.showinfo("MIKE URBAN import", msg, parent=self.root)
        self.job(f"Translating {path.name} (MIKE URBAN → EPANET)", work, done)

    def _after_load(self, hint: str | None, crs_code: str | None = None):
        st = self.state
        topo = netlib.read_topology(st.net)
        if crs_code:
            try:
                st.crs = crslib.ProjectCRS(crslib.validate_code(crs_code))
            except Exception:
                st.crs = crslib.ProjectCRS()
        else:
            sample = list(zip(topo.x[:2000], topo.y[:2000])) if not topo.synthetic_layout else []
            st.crs = crslib.detect_crs(sample, hint)
        st.refresh_topology()
        self.msx.validate()
        self._model_changed()
        crs_note = "no basemap until a CRS is assigned" if st.crs.is_local else st.crs.name
        self.status(f"Loaded {len(st.topo.node_ids)} nodes, {len(st.topo.link_ids)} links · {crs_note}")

    def add_overlay(self):
        path = filedialog.askopenfilename(filetypes=[("GeoPackage", "*.gpkg")])
        if path:
            self.state.gpkg_path = Path(path)
            self.map.load_overlay(); self.map.redraw()

    def choose_crs(self):
        st = self.state
        suggestion = None
        if st.loaded:
            suggestion = crslib.detect_crs(list(zip(st.topo.x[:2000], st.topo.y[:2000])))
        result = CRSDialog(self.root, st, suggestion).run()
        if result is not None:
            st.crs = result
            st.bus.emit("crs")
            self._model_changed()
            self.status(f"Coordinate system: {result.name}")

    # ============================================================ projects
    def save_project(self, ask: bool = False):
        st = self.state
        if not st.loaded:
            return
        name = st.project_name
        if ask or not name:
            default = name or (st.source_path.stem if st.source_path else "network")
            name = simpledialog.askstring("Save project", f"Project name (stored in {STORE_DIR}):",
                                          initialvalue=default, parent=self.root)
            if not name:
                return
        tmp = Path(tempfile.mkdtemp(prefix="epanet-wb-save-")) / "chemistry.msx"
        tmp.write_text(msxlib.write(st.msx), encoding="utf-8")
        meta = {"crs": st.crs.code, "source": str(st.source_path or ""),
                "run_settings": st.run_settings.__dict__,
                "style": {"basemap": st.style.basemap, "node_var": st.style.node_var, "link_var": st.style.link_var}}
        try:
            folder = self.store.save(name, st.wrapper, tmp if st.msx.species() else None, st.gpkg_path,
                                     metadata=meta, scenarios=st.scenarios)
        except Exception as exc:
            messagebox.showerror("Save project", str(exc), parent=self.root); return
        st.project_name = name
        if st.gpkg_path:
            st.gpkg_path = folder / "assets.gpkg"
        self._model_changed()
        self.status(f"Saved project to {folder}")

    def open_project(self):
        names = self.store.list()
        if not names:
            messagebox.showinfo("Projects", f"No saved projects in {STORE_DIR}.", parent=self.root); return
        win = tk.Toplevel(self.root); win.title("Open project"); win.transient(self.root)
        lb = tk.Listbox(win, width=40, height=12); lb.pack(fill="both", expand=True, padx=10, pady=10)
        for n in names:
            lb.insert("end", n)

        def go():
            sel = lb.curselection()
            if sel:
                win.destroy(); self._load_project(names[sel[0]])
        lb.bind("<Double-Button-1>", lambda e: go())
        ttk.Button(win, text="Open", command=go, style="Accent.TButton").pack(pady=(0, 10))

    def _load_project(self, slug: str):
        project = self.store.load(slug)

        def work():
            self.state.wrapper.load_file(project["inp"])
            scen = []
            for s in project["scenarios"]:
                try:
                    scen.append(netlib.Scenario(s["name"], netlib.Results.load(s["file"]), s.get("settings", ""),
                                                s.get("note", "")))
                except Exception:
                    continue
            return scen

        def done(scenarios):
            st = self.state
            self._reset_session()
            meta = project.get("workbench", {})
            st.project_name, st.source_path = project["name"], project["inp"]
            st.gpkg_path = project.get("geopackage")
            if "run_settings" in meta:
                try:
                    st.run_settings = netlib.RunSettings(**meta["run_settings"])
                except TypeError:
                    st.run_settings = netlib.RunSettings.from_network(st.net)
            if project.get("msx"):
                self.msx.load_file(project["msx"])
            if project.get("conversion_report"):
                import json
                st.wrapper._conversion_report = json.loads(Path(project["conversion_report"]).read_text())
            style_meta = meta.get("style", {})
            st.style.basemap = style_meta.get("basemap", st.style.basemap)
            self._after_load(hint=None, crs_code=meta.get("crs"))
            for s in scenarios:
                st.scenarios.append(s)
            if scenarios:
                st.active = scenarios[-1]
                st.style.node_var = style_meta.get("node_var", "res:pressure")
                st.style.link_var = style_meta.get("link_var", "res:velocity")
                st.bus.emit("scenarios"); st.bus.emit("results"); st.bus.emit("style")
            self.panel.refresh()
        self.job(f"Opening project {project['name']}", work, done)

    def export_inp(self):
        if not self.state.loaded:
            return
        path = filedialog.asksaveasfilename(defaultextension=".inp", filetypes=[("EPANET input", "*.inp")])
        if path:
            self.state.wrapper.save_input_file(Path(path))
            self.status(f"Exported {path}")

    # ============================================================ running
    def edit_settings(self):
        if not self.state.loaded:
            return
        result = RunSettingsDialog(self.root, self.state).run()
        if result:
            self.state.run_settings = result
            self.status(f"Settings: {result.summary()}")

    def run(self, with_msx: bool = False):
        st = self.state
        if not st.loaded:
            messagebox.showinfo("Run", "Open a model first.", parent=self.root); return
        msx_file = None
        if with_msx:
            issues = self.msx.validate()
            errors = [str(i) for i in issues if i.level == "error"]
            if errors:
                self.nb.select(self.msx)
                messagebox.showerror("MSX chemistry has errors", "\n".join(errors[:12]), parent=self.root); return
            msx_file = Path(tempfile.mkdtemp(prefix="epanet-wb-msx-")) / "chemistry.msx"
            msx_file.write_text(msxlib.write(st.msx), encoding="utf-8")
        settings = st.run_settings
        topo = st.topo

        def work():
            settings.apply(st.net)
            st.wrapper.run_simulation()
            computed = st.wrapper.get_computed_time_series()
            msx = st.wrapper.run_msx(msx_file) if msx_file else None
            quality = {"AGE": "Water age [h]", "CHEM": f"{settings.chem_name} [{settings.chem_units}]",
                       "TRACE": f"Trace from {settings.trace_node} [%]"}.get(settings.quality, "Quality")
            return netlib.Results.from_engine(topo, computed, msx, meta={"flow_units": topo.flow_units,
                                                                         "quality_label": quality})

        def done(results):
            label = settings.summary() + (f" + MSX ({', '.join(st.msx.species())})" if msx_file else "")
            scen = netlib.Scenario(st.next_scenario_name(), results, label)
            first = st.active is None
            st.add_scenario(scen)
            if st.style.node_var in ("type", "none") or first:
                if msx_file and results.msx_node:
                    st.style.node_var = f"res:msx:{next(iter(results.msx_node))}"
                elif settings.quality != "NONE":
                    st.style.node_var = "res:quality"
                else:
                    st.style.node_var = "res:pressure"
            if st.style.link_var in ("type", "none") or first:
                st.style.link_var = "res:velocity"
            if msx_file and results.msx_node:
                st.style.node_var = f"res:msx:{next(iter(results.msx_node))}"
            self.panel.refresh()
            st.bus.emit("style")
            self.status(f"{scen.name} finished: {len(results.time)} report steps"
                        + (f", MSX {len(results.msx_time)} steps" if results.msx_time is not None else "")
                        + (f". Baseline: {st.baseline.name}" if st.baseline else ""))
            if msx_file:
                self.show_map()
        self.job("Running EPANET" + (" + MSX" if with_msx else ""), work, done)

    def run_msx(self):
        self.run(with_msx=True)

    def map_species(self, name: str):
        st = self.state
        st.style.node_var = f"res:msx:{name}"
        if name in (st.active.results.msx_link if st.active else {}):
            st.style.link_var = f"res:msx:{name}"
        self.panel.refresh()
        st.bus.emit("style")
        self.show_map()

    def trace_from(self, i: int):
        st = self.state
        st.run_settings.quality = "TRACE"
        st.run_settings.trace_node = st.topo.node_ids[i]
        self.status(f"Quality set to source trace from {st.topo.node_ids[i]} – running…")
        self.run()

    def msx_source(self, i: int):
        st = self.state
        if not st.msx.species():
            messagebox.showinfo("MSX", "Define chemistry in the MSX studio first.", parent=self.root); return
        bulk = [r["name"] for r in st.msx.rows["SPECIES"] if r.get("type") == "BULK"] or st.msx.species()
        species = simpledialog.askstring("MSX source", f"Species to inject at {st.topo.node_ids[i]} ({', '.join(bulk)}):",
                                         initialvalue=bulk[0], parent=self.root)
        if not species:
            return
        strength = simpledialog.askfloat("MSX source", "Concentration:", initialvalue=1.0, parent=self.root)
        if strength is None:
            return
        st.msx.rows["SOURCES"].append({"type": "CONCEN", "node": st.topo.node_ids[i], "species": species,
                                       "strength": f"{strength:g}", "pattern": "", "comment": "added from map"})
        self.msx.show_section()
        self.status(f"MSX source {species}={strength:g} at {st.topo.node_ids[i]}")

    # ============================================================ editing
    def edit_patterns(self):
        if not self.state.loaded:
            return
        changed = PatternEditor(self.root, self.state).run()
        if changed:
            self.state.properties_changed()
            self.status(f"Updated {changed} pattern(s).")

    def _default_link_values(self):
        df = self.state.table("link")
        pipes = df[df["type"] == "Pipe"]
        if len(pipes):
            return float(pipes["diameter"].median()), float(pipes["roughness"].median())
        return (150.0, 100.0) if not self.state.topo.us_units else (8.0, 100.0)

    def add_junction(self, x: float, y: float):
        st = self.state
        nid = netlib.unique_id(st.topo.node_ids, "J")
        d = np.hypot(st.topo.x - x, st.topo.y - y) if len(st.topo.x) else np.array([])
        elev = float(st.table("node")["elevation"].iloc[int(d.argmin())]) if d.size else 0.0
        try:
            netlib.add_junction(st.net, nid, x, y, elevation=elev)
        except Exception as exc:
            messagebox.showerror("Add junction", str(exc), parent=self.root); return
        st.properties_changed(structural=True)
        st.select(nodes=[st.topo.node_index[nid]], source="edit")
        self.status(f"Added junction {nid} (elevation {elev:g} copied from nearest node).")

    def add_pipe(self, a: int, b: int):
        st = self.state
        topo = st.topo
        lid = netlib.unique_id(topo.link_ids, "P")
        if st.crs.is_local or st.crs.units in ("metre", "meter", "US survey foot", "foot"):
            length = float(np.hypot(topo.x[a] - topo.x[b], topo.y[a] - topo.y[b]))
        else:
            length = 100.0
        diameter, rough = self._default_link_values()
        try:
            netlib.add_pipe(st.net, lid, topo.node_ids[a], topo.node_ids[b], max(length, 0.1), diameter, rough)
        except Exception as exc:
            messagebox.showerror("Add pipe", str(exc), parent=self.root); return
        st.properties_changed(structural=True)
        st.select(links=[st.topo.link_index[lid]], source="edit")
        self.status(f"Added pipe {lid}: length {length:.1f}, diameter {diameter:g}, roughness {rough:g}.")

    def move_node(self, i: int, x: float, y: float):
        st = self.state
        netlib.move_node(st.net, i, x, y)
        st.properties_changed(structural=True)
        st.select(nodes=[i], source="edit")

    def delete_selection(self):
        st = self.state
        if not st.loaded or not (st.sel_nodes or st.sel_links):
            return
        nodes = [st.topo.node_ids[i] for i in st.sel_nodes]
        links = {st.topo.link_ids[i] for i in st.sel_links}
        for j in range(len(st.topo.link_ids)):  # links attached to deleted nodes go too
            if st.topo.link_from[j] in st.sel_nodes or st.topo.link_to[j] in st.sel_nodes:
                links.add(st.topo.link_ids[j])
        if not messagebox.askyesno("Delete", f"Delete {len(nodes)} node(s) and {len(links)} link(s)?", parent=self.root):
            return
        try:
            netlib.delete_objects(st.net, nodes, sorted(links))
        except Exception as exc:
            messagebox.showerror("Delete", str(exc), parent=self.root)
        st.properties_changed(structural=True)
        self.status(f"Deleted {len(nodes)} nodes, {len(links)} links. Results of earlier runs remain for comparison.")

    # ============================================================ info
    def show_report(self):
        report = self.state.wrapper.get_conversion_report()
        if not report:
            messagebox.showinfo("Conversion report", "Only MIKE URBAN imports produce a conversion report.", parent=self.root)
            return
        ReportWindow(self.root, "MIKE URBAN → EPANET conversion report", report)

    def show_capabilities(self):
        path = ROOT / "docs" / "ENGINE_CAPABILITIES.md"
        win = tk.Toplevel(self.root); win.title("Engine capabilities"); win.geometry("900x640")
        text = tk.Text(win, wrap="word", font=("TkDefaultFont", 10), padx=12, pady=8)
        text.pack(fill="both", expand=True)
        text.insert("1.0", path.read_text(encoding="utf-8") if path.is_file() else "docs/ENGINE_CAPABILITIES.md missing")
        text.configure(state="disabled")

    def show_shortcuts(self):
        messagebox.showinfo("Shortcuts", "Mouse wheel – zoom · drag – pan · middle-drag – pan\n"
                            "Click – select · Ctrl/Shift+click – add to selection · Shift+drag – box select\n"
                            "Right-click – object menu · Del – delete · Esc – cancel/clear\n"
                            "F5 – run · F6 – run with MSX · Space – play/pause · Ctrl+S – save", parent=self.root)


def main(argv: list[str] | None = None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    root = tk.Tk()
    app = Workbench(root)
    for arg in argv:
        p = Path(arg)
        if p.suffix.lower() == ".inp" and p.is_file():
            root.after(300, lambda p=p: app.open_inp(p))
    root.mainloop()
