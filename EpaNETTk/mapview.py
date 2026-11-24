"""Slippy map canvas: basemap tiles, network, analytics colouring, editing tools."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib import colormaps

from epanet_addons.crs import ProjectCRS
from . import tiles as tl
from .state import AppState

TYPE_COLORS = {"Junction": "#2563eb", "Tank": "#059669", "Reservoir": "#7c3aed",
               "Pipe": "#334155", "CV Pipe": "#475569", "Pump": "#d97706"}
VALVE_COLOR = "#dc2626"
NAN_COLOR = "#9ca3af"
DIM_COLOR = "#d1d5db"
SEL_NODE = "#ff2d95"
SEL_LINK = "#facc15"
CULL_LIMIT = 9000


def _hex(rgba: np.ndarray) -> list[str]:
    rgb = (np.clip(rgba[:, :3], 0, 1) * 255).astype(int)
    return ["#%02x%02x%02x" % tuple(c) for c in rgb]


def _nice(value: float) -> float:
    if value <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(value))
    for m in (1, 2, 5, 10):
        if m * exp >= value:
            return m * exp
    return 10 * exp


def fmt(v: float) -> str:
    if v is None or not np.isfinite(v):
        return "–"
    a = abs(v)
    if a >= 1e5 or (0 < a < 1e-3):
        return f"{v:.3g}"
    if a >= 100:
        return f"{v:.1f}"
    return f"{v:.3g}" if a < 1 else f"{v:.2f}"


class MapView(ttk.Frame):
    def __init__(self, master, state: AppState, actions):
        super().__init__(master)
        self.state, self.actions = state, actions
        self.canvas = tk.Canvas(self, background="#eef2f7", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.tiles = tl.TileCache()
        self.cx = self.cy = 0.0
        self.res = 1.0
        self.mode = "select"
        self.node_items: dict[int, int] = {}
        self.link_items: dict[int, int] = {}
        self.wnx = self.wny = np.zeros(0)
        self.lpts = np.zeros((0, 2)); self.loff = np.zeros(1, int)
        self.overlay: list[tuple[str, np.ndarray]] = []
        self._tiles_drawn: dict[tuple, int] = {}
        self._culled = False
        self._drag = None
        self._pipe_start: int | None = None
        self._redraw_job = None
        self._hover_job = None
        self.filter_count = None
        self._bind_events()
        b = state.bus
        b.on("model", lambda **_: self.on_model())
        b.on("crs", lambda **_: self.on_model())
        b.on("properties", lambda **_: self.recolor())
        b.on("results", lambda **_: self.recolor())
        b.on("time", lambda **_: self.recolor())
        b.on("style", lambda **_: self.redraw())
        b.on("selection", lambda **kw: self.draw_selection(kw.get("source") != "map"))
        self.after(120, self._poll_tiles)

    # ------------------------------------------------------------------ view
    @property
    def view_size(self) -> tuple[int, int]:
        return max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)

    @property
    def basemap_on(self) -> bool:
        return not self.state.crs.is_local and self.state.style.basemap != "None"

    def to_screen(self, wx, wy):
        w, h = self.view_size
        return (np.asarray(wx) - self.cx) / self.res + w / 2, (self.cy - np.asarray(wy)) / self.res + h / 2

    def to_world(self, sx, sy):
        w, h = self.view_size
        return self.cx + (sx - w / 2) * self.res, self.cy - (sy - h / 2) * self.res

    def _snap(self):
        if self.basemap_on:
            z = int(round(tl.zoom_for_resolution(self.res)))
            z = min(max(z, 2), tl.MAX_VIEW_ZOOM)
            self.res = tl.resolution_for_zoom(z)

    def on_model(self):
        st = self.state
        self._pipe_start = None
        if not st.loaded:
            self.wnx = self.wny = np.zeros(0); self.lpts = np.zeros((0, 2)); self.loff = np.zeros(1, int)
            self.redraw(); return
        topo = st.topo
        self.wnx, self.wny = st.crs.to_world(topo.x, topo.y)
        paths = [topo.link_path(i) for i in range(len(topo.link_ids))]
        lengths = [len(p) for p in paths]
        self.loff = np.concatenate([[0], np.cumsum(lengths)]).astype(int)
        flat = np.array([pt for p in paths for pt in p], dtype=float).reshape(-1, 2)
        if len(flat):
            wx, wy = st.crs.to_world(flat[:, 0], flat[:, 1])
            self.lpts = np.column_stack([wx, wy])
        else:
            self.lpts = np.zeros((0, 2))
        self.load_overlay()
        self.zoom_extent()

    def load_overlay(self):
        self.overlay = []
        path = self.state.gpkg_path
        if not path:
            return
        try:
            from epanet_addons.gpkg import read_features
            for layer in read_features(path):
                crs = ProjectCRS(f"EPSG:{layer['srs']}") if layer["srs"] else self.state.crs
                if crs.is_local != self.state.crs.is_local:
                    continue
                if len(layer["points"]):
                    wx, wy = crs.to_world(layer["points"][:, 0], layer["points"][:, 1])
                    self.overlay.append(("points", np.column_stack([wx, wy])))
                for line in layer["lines"]:
                    wx, wy = crs.to_world(line[:, 0], line[:, 1])
                    self.overlay.append(("line", np.column_stack([wx, wy])))
        except Exception as exc:  # overlay is optional; report but keep working
            self.actions.status(f"GeoPackage overlay not drawn: {exc}")

    def zoom_extent(self, nodes: list[int] | None = None):
        w, h = self.view_size
        if nodes:
            xs, ys = self.wnx[nodes], self.wny[nodes]
        else:
            xs, ys = self.wnx, self.wny
        if not len(xs):
            if not self.state.crs.is_local:
                self.cx, self.cy, self.res = 1_600_000, 6_400_000, tl.resolution_for_zoom(5)
            self.redraw(); return
        self.cx, self.cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        span = max((xs.max() - xs.min()) / max(w - 80, 10), (ys.max() - ys.min()) / max(h - 80, 10))
        if span <= 0:  # a single point: keep a readable street-level scale
            span = tl.resolution_for_zoom(18) if self.basemap_on else max(self.res, 0.05)
        self.res = span
        if self.basemap_on:
            z = math.floor(tl.zoom_for_resolution(self.res))
            self.res = tl.resolution_for_zoom(z)
        self.redraw()

    def zoom_at(self, sx: float, sy: float, steps: int):
        wx, wy = self.to_world(sx, sy)
        if self.basemap_on:
            z = int(round(tl.zoom_for_resolution(self.res))) + steps
            z = min(max(z, 2), tl.MAX_VIEW_ZOOM)
            self.res = tl.resolution_for_zoom(z)
        else:
            self.res *= 1.3 ** (-steps)
        w, h = self.view_size
        self.cx = wx - (sx - w / 2) * self.res
        self.cy = wy + (sy - h / 2) * self.res
        self.redraw()

    # --------------------------------------------------------------- drawing
    def redraw(self):
        self._redraw_job = None
        c = self.canvas
        c.delete("all")
        self._tiles_drawn.clear()
        dark = "Dark" in self.state.style.basemap and self.basemap_on
        c.configure(background="#15171c" if dark else ("#eef2f7" if not self.basemap_on else "#f5f5f3"))
        self._snap()
        self.draw_tiles()
        self.draw_overlay()
        self.draw_network()
        self.recolor()
        self.draw_selection()

    def schedule_redraw(self, delay: int = 60):
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(delay, self.redraw)

    def draw_tiles(self):
        if not self.basemap_on:
            return
        c = self.canvas
        w, h = self.view_size
        z = int(round(tl.zoom_for_resolution(self.res)))
        n = 2 ** z
        size = 2 * tl.HALF / n
        minx, maxy = self.to_world(0, 0)
        maxx, miny = self.to_world(w, h)
        x0, x1 = int((minx + tl.HALF) // size), int((maxx + tl.HALF) // size)
        y0, y1 = int((tl.HALF - maxy) // size), int((tl.HALF - miny) // size)
        wanted = set()
        provider, fade = self.state.style.basemap, self.state.style.fade
        for tx in range(x0, x1 + 1):
            for ty in range(max(y0, 0), min(y1, n - 1) + 1):
                key = (z, tx % n, ty, tx)
                wanted.add(key)
                if key in self._tiles_drawn:
                    continue
                img = self.tiles.get(provider, z, tx % n, ty, fade)
                if img is None:
                    continue
                bx, by, _, top = tl.tile_bounds(z, tx, ty)
                sx, sy = self.to_screen(bx, top)
                item = c.create_image(float(sx), float(sy), image=img, anchor="nw", tags=("world", "tile"))
                c.tag_lower(item)
                self._tiles_drawn[key] = item
        for key in list(self._tiles_drawn):
            if key not in wanted:
                c.delete(self._tiles_drawn.pop(key))

    def _poll_tiles(self):
        if self.tiles.poll() and self.basemap_on:
            self.draw_tiles()
        self.after(120, self._poll_tiles)

    def draw_overlay(self):
        if not self.overlay or not self.state.style.overlay:
            return
        c = self.canvas
        for kind, pts in self.overlay:
            sx, sy = self.to_screen(pts[:, 0], pts[:, 1])
            if kind == "line" and len(pts) > 1:
                c.create_line(*np.column_stack([sx, sy]).ravel().tolist(), fill="#94a3b8", width=1,
                              tags=("world", "overlay"))
            elif kind == "points":
                w, h = self.view_size
                vis = (sx > -5) & (sx < w + 5) & (sy > -5) & (sy < h + 5)
                for x, y in zip(sx[vis][:4000], sy[vis][:4000]):
                    c.create_rectangle(x - 1, y - 1, x + 1, y + 1, outline="#94a3b8", tags=("world", "overlay"))

    def draw_network(self):
        st, c = self.state, self.canvas
        self.node_items.clear(); self.link_items.clear()
        if not st.loaded:
            self._hud_empty(); return
        topo = st.topo
        w, h = self.view_size
        total = len(topo.node_ids) + len(topo.link_ids)
        self._culled = total > CULL_LIMIT
        margin = max(w, h) * 0.6
        sx_all, sy_all = self.to_screen(self.lpts[:, 0], self.lpts[:, 1]) if len(self.lpts) else (np.zeros(0), np.zeros(0))
        for i in range(len(topo.link_ids)):
            a, b = self.loff[i], self.loff[i + 1]
            xs, ys = sx_all[a:b], sy_all[a:b]
            if self._culled and (xs.max() < -margin or xs.min() > w + margin or ys.max() < -margin or ys.min() > h + margin):
                continue
            item = c.create_line(*np.column_stack([xs, ys]).ravel().tolist(), width=2, fill="#334155",
                                 capstyle="round", joinstyle="round", tags=("world", "link", f"L{i}"))
            self.link_items[i] = item
            t = topo.link_types[i]
            if t != "Pipe" and t != "CV Pipe":
                mid = (b - a) // 2 + a
                mx, my = (sx_all[mid - 1] + sx_all[mid]) / 2 if b - a > 1 else sx_all[a], (sy_all[mid - 1] + sy_all[mid]) / 2 if b - a > 1 else sy_all[a]
                if t == "Pump":
                    c.create_oval(mx - 6, my - 6, mx + 6, my + 6, fill="#fbbf24", outline="#92400e", width=1.5,
                                  tags=("world", "linkmark", f"L{i}"))
                    c.create_text(mx, my, text="P", font=("TkDefaultFont", 7, "bold"), fill="#78350f",
                                  tags=("world", "linkmark", f"L{i}"))
                else:
                    c.create_polygon(mx - 6, my - 5, mx + 6, my + 5, mx + 6, my - 5, mx - 6, my + 5,
                                     fill="#fecaca", outline=VALVE_COLOR, width=1.5, tags=("world", "linkmark", f"L{i}"))
        nx_, ny_ = self.to_screen(self.wnx, self.wny)
        small = len(topo.node_ids) > 3000 and self.res > 2
        for i, t in enumerate(topo.node_types):
            x, y = float(nx_[i]), float(ny_[i])
            if self._culled and (x < -margin or x > w + margin or y < -margin or y > h + margin):
                continue
            tags = ("world", "node", f"N{i}")
            if t == "Junction":
                r = 2 if small else 3.5
                item = c.create_oval(x - r, y - r, x + r, y + r, fill=TYPE_COLORS[t], outline="", tags=tags)
            elif t == "Tank":
                item = c.create_rectangle(x - 7, y - 6, x + 7, y + 6, fill=TYPE_COLORS[t], outline="#064e3b",
                                          width=1.5, tags=tags)
            else:
                item = c.create_polygon(x - 8, y - 6, x + 8, y - 6, x + 5, y + 6, x - 5, y + 6,
                                        fill=TYPE_COLORS[t], outline="#3b0764", width=1.5, tags=tags)
            self.node_items[i] = item
        if st.style.labels:
            visible = [i for i in self.node_items if 0 <= nx_[i] <= w and 0 <= ny_[i] <= h]
            if len(visible) <= 600:
                for i in visible:
                    c.create_text(float(nx_[i]) + 6, float(ny_[i]) - 6, text=topo.node_ids[i], anchor="sw",
                                  font=("TkDefaultFont", 8), fill="#0f172a", tags=("world", "label"))

    def _colors(self, kind: str, key: str, cmap_name: str):
        """Return (colors, norm values 0..1 or None, raw values, range)."""
        st = self.state
        topo = st.topo
        types = topo.node_types if kind == "node" else topo.link_types
        if key == "type":
            return [TYPE_COLORS.get(t, VALVE_COLOR) for t in types], None, None, None
        if key == "none":
            return ["#1e40af" if kind == "node" else "#475569"] * len(types), None, None, None
        vals = st.values(kind, key)
        rng = st.series_range(kind, key)
        if vals is None or rng is None:
            return [NAN_COLOR] * len(types), None, vals, None
        lo, hi = rng
        span = (hi - lo) or 1.0
        norm = np.clip((vals - lo) / span, 0, 1)
        cmap = colormaps["RdBu_r" if st.style.delta and key.startswith("res:") else cmap_name]
        rgba = cmap(np.nan_to_num(norm, nan=0.0))
        colors = _hex(rgba)
        for i in np.where(~np.isfinite(vals))[0]:
            colors[i] = NAN_COLOR
        return colors, norm, vals, rng

    def recolor(self):
        st, c = self.state, self.canvas
        c.delete("arrow"); c.delete("hud")
        if not st.loaded:
            self._hud_empty(); return
        s = st.style
        topo = st.topo
        ncol, nnorm, nvals, nrng = self._colors("node", s.node_var, s.node_cmap)
        lcol, lnorm, lvals, lrng = self._colors("link", s.link_var, s.link_cmap)
        node_mask = link_mask = None
        if s.filter_op:
            vals = nvals if s.filter_kind == "node" else lvals
            if vals is not None:
                with np.errstate(invalid="ignore"):
                    mask = vals < s.filter_value if s.filter_op == "<" else vals > s.filter_value
                if s.filter_kind == "node":
                    node_mask = mask
                else:
                    link_mask = mask
                self.filter_count = int(np.nansum(mask))
        else:
            self.filter_count = None
        small = len(topo.node_ids) > 3000 and self.res > 2
        for i, item in self.node_items.items():
            color = ncol[i]
            dim = node_mask is not None and not node_mask[i]
            if topo.node_types[i] == "Junction":
                if s.size_by_value and nnorm is not None and np.isfinite(nnorm[i]):
                    r = 2.5 + 6 * float(nnorm[i])
                elif node_mask is not None and not dim:
                    r = 6
                else:
                    r = 2 if small else 3.5
                if dim:
                    r = 2
                x0, y0, x1, y1 = c.coords(item)
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                c.coords(item, mx - r, my - r, mx + r, my + r)
            c.itemconfigure(item, fill=DIM_COLOR if dim else color)
        for i, item in self.link_items.items():
            dim = link_mask is not None and not link_mask[i]
            width = 2.0
            if s.width_by_value and lnorm is not None and np.isfinite(lnorm[i]):
                v = abs(lvals[i]); m = max(abs(lrng[0]), abs(lrng[1])) or 1
                width = 1.2 + 6 * min(v / m, 1)
            elif link_mask is not None and not dim:
                width = 4.5
            c.itemconfigure(item, fill=DIM_COLOR if dim else lcol[i], width=1 if dim else width)
        if s.arrows:
            self._draw_arrows()
        self._draw_hud(ncol, nrng, lrng)

    def _draw_arrows(self):
        st, c = self.state, self.canvas
        if st.active is None:
            return
        flow = st.values("link", "res:flow", stat="At time", delta=False)
        if flow is None:
            return
        w, h = self.view_size
        sx_all, sy_all = self.to_screen(self.lpts[:, 0], self.lpts[:, 1])
        count = 0
        for i in self.link_items:
            a, b = self.loff[i], self.loff[i + 1]
            if b - a < 2 or not np.isfinite(flow[i]) or abs(flow[i]) < 1e-6:
                continue
            seg = (b - a) // 2 + a - 1 if b - a > 2 else a
            x0, y0, x1, y1 = sx_all[seg], sy_all[seg], sx_all[seg + 1], sy_all[seg + 1]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if not (0 <= mx <= w and 0 <= my <= h):
                continue
            dx, dy = x1 - x0, y1 - y0
            length = math.hypot(dx, dy)
            if length < 28:
                continue
            if flow[i] < 0:
                dx, dy = -dx, -dy
            ux, uy = dx / length, dy / length
            s = 5
            pts = (mx + ux * s, my + uy * s, mx - ux * s - uy * s * 0.8, my - uy * s + ux * s * 0.8,
                   mx - ux * s + uy * s * 0.8, my - uy * s - ux * s * 0.8)
            c.create_polygon(*pts, fill="#0f172a", outline="white", width=0.5, tags=("world", "arrow"))
            count += 1
            if count > 4000:
                break

    # ------------------------------------------------------------------ HUD
    def _hud_empty(self):
        c = self.canvas
        w, h = self.view_size
        c.create_text(w / 2, h / 2, text="Open an EPANET .inp, import a MIKE URBAN .mdb,\nor open a saved project to begin.",
                      font=("TkDefaultFont", 13), fill="#64748b", justify="center", tags=("hud",))

    def _legend_block(self, x: float, y: float, title: str, cmap: str, rng, types: list[str] | None) -> float:
        c = self.canvas
        c.create_text(x, y, text=title, anchor="nw", font=("TkDefaultFont", 9, "bold"), fill="#0f172a", tags="hud")
        y += 17
        if types is not None:
            for t in types:
                color = TYPE_COLORS.get(t, VALVE_COLOR)
                c.create_rectangle(x, y + 2, x + 12, y + 12, fill=color, outline="", tags="hud")
                c.create_text(x + 18, y, text=t, anchor="nw", font=("TkDefaultFont", 8), fill="#1e293b", tags="hud")
                y += 15
            return y + 4
        if rng is None:
            c.create_text(x, y, text="no data", anchor="nw", font=("TkDefaultFont", 8), fill="#64748b", tags="hud")
            return y + 18
        cm = colormaps[cmap]
        steps, width = 40, 170
        for k in range(steps):
            r, g, b, _ = cm(k / (steps - 1))
            c.create_rectangle(x + k * width / steps, y, x + (k + 1) * width / steps + 1, y + 10,
                               fill="#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)), outline="", tags="hud")
        y += 12
        c.create_text(x, y, text=fmt(rng[0]), anchor="nw", font=("TkDefaultFont", 8), fill="#1e293b", tags="hud")
        c.create_text(x + width / 2, y, text=fmt((rng[0] + rng[1]) / 2), anchor="n", font=("TkDefaultFont", 8), fill="#1e293b", tags="hud")
        c.create_text(x + width, y, text=fmt(rng[1]), anchor="ne", font=("TkDefaultFont", 8), fill="#1e293b", tags="hud")
        return y + 18

    def _draw_hud(self, ncol, nrng, lrng):
        st, c = self.state, self.canvas
        s = st.style
        w, h = self.view_size
        x, y = w - 196, 10
        start = y
        delta = s.delta and st.baseline is not None
        suffix = ""
        if s.stat != "At time":
            suffix = f" · {s.stat.lower()}"
        if delta:
            suffix += f" · Δ vs {st.baseline.name}"
        for kind, key, cmap, rng in (("node", s.node_var, s.node_cmap, nrng), ("link", s.link_var, s.link_cmap, lrng)):
            types = None
            if key == "type":
                present = st.topo.node_types if kind == "node" else st.topo.link_types
                types = [t for t in (["Junction", "Tank", "Reservoir"] if kind == "node" else
                                     ["Pipe", "CV Pipe", "Pump", "Valve"]) if t in present or
                         (t == "Valve" and any(p in present for p in ("PRV", "PSV", "PBV", "FCV", "TCV", "GPV", "PCV")))]
            elif key == "none":
                continue
            label = ("Nodes: " if kind == "node" else "Links: ") + (st.label_for(kind, key) if key != "type" else "type")
            if key.startswith("res:"):
                label += suffix
            y = self._legend_block(x, y, label[:40], "RdBu_r" if delta and key.startswith("res:") else cmap, rng, types)
        if self.filter_count is not None:
            c.create_text(x, y, text=f"Filter {s.filter_kind}s {s.filter_op} {fmt(s.filter_value)}: {self.filter_count} match",
                          anchor="nw", font=("TkDefaultFont", 8, "bold"), fill="#b91c1c", tags="hud")
            y += 16
        bg = c.create_rectangle(x - 8, start - 6, w - 8, y + 2, fill="white", outline="#cbd5e1", stipple="", tags="hud")
        c.tag_lower(bg, "hud")
        c.tag_raise("hud")
        # time stamp
        if st.active is not None and s.stat == "At time":
            hrs = st.time_s / 3600
            stamp = f"{st.active.name} · t = {int(hrs):d}:{int(round((hrs % 1) * 60)):02d} h"
            if st.stale:
                stamp += "  (model edited since run)"
            t = c.create_text(12, 12, text=stamp, anchor="nw", font=("TkDefaultFont", 10, "bold"),
                              fill="#b45309" if st.stale else "#0f172a", tags="hud")
            x0, y0, x1, y1 = c.bbox(t)
            c.tag_lower(c.create_rectangle(x0 - 5, y0 - 3, x1 + 5, y1 + 3, fill="white", outline="#cbd5e1", tags="hud"), t)
        # scale bar
        lat_scale = 1.0
        unit = "m"
        if not st.crs.is_local:
            lonlat = st.crs.world_to_lonlat(self.cx, self.cy)
            if lonlat:
                lat_scale = math.cos(math.radians(lonlat[1]))
        else:
            unit = "units"
        ground = self.res * lat_scale * 120
        nice = _nice(ground)
        px = nice / (self.res * lat_scale)
        c.create_rectangle(10, h - 30, 18 + px, h - 10, fill="white", outline="", tags="hud")
        c.create_line(14, h - 14, 14 + px, h - 14, width=3, fill="#0f172a", tags="hud")
        label = f"{nice / 1000:g} km" if unit == "m" and nice >= 1000 else f"{nice:g} {unit}"
        c.create_text(14 + px / 2, h - 17, text=label, anchor="s", font=("TkDefaultFont", 8), fill="#0f172a", tags="hud")
        if self.basemap_on:
            attr = tl.PROVIDERS.get(st.style.basemap, {}).get("attribution", "")
            if self.tiles.offline_errors:
                attr = f"{self.tiles.offline_errors} tiles unavailable (offline?) · " + attr
            c.create_text(w - 4, h - 3, text=attr, anchor="se", font=("TkDefaultFont", 7), fill="#334155", tags="hud")
        elif st.crs.is_local:
            c.create_text(w - 4, h - 3, text="Local coordinates – assign a CRS (Network ▸ Coordinate system) to show a basemap",
                          anchor="se", font=("TkDefaultFont", 8), fill="#64748b", tags="hud")
        hint = {"add_junction": "Click to place a junction", "add_pipe": "Click start node, then end node",
                "move": "Drag a node to move it"}.get(self.mode)
        if hint:
            if self.mode == "add_pipe" and self._pipe_start is not None:
                hint = f"From {st.topo.node_ids[self._pipe_start]} → click end node (Esc cancels)"
            c.create_text(w / 2, 12, text=hint, anchor="n", font=("TkDefaultFont", 10, "bold"),
                          fill="#7c2d12", tags="hud")

    def draw_selection(self, center: bool = False):
        st, c = self.state, self.canvas
        c.delete("sel")
        if not st.loaded:
            return
        for i in st.sel_links:
            item = self.link_items.get(i)
            if item is None:
                continue
            hl = c.create_line(*c.coords(item), fill=SEL_LINK, width=float(c.itemcget(item, "width")) + 7,
                               capstyle="round", joinstyle="round", tags=("world", "sel"))
            c.tag_lower(hl, item)
        for i in st.sel_nodes:
            item = self.node_items.get(i)
            if item is None:
                continue
            bbox = c.bbox(item)
            if bbox:
                x0, y0, x1, y1 = bbox
                c.create_oval(x0 - 5, y0 - 5, x1 + 5, y1 + 5, outline=SEL_NODE, width=2.5, tags=("world", "sel"))
        if self._pipe_start is not None and self._pipe_start in self.node_items:
            x0, y0, x1, y1 = c.bbox(self.node_items[self._pipe_start])
            c.create_oval(x0 - 7, y0 - 7, x1 + 7, y1 + 7, outline="#16a34a", width=3, tags=("world", "sel"))
        c.tag_raise("hud")
        if center and (st.sel_nodes or st.sel_links):
            self.center_on_selection()

    def center_on_selection(self):
        st = self.state
        idx = list(st.sel_nodes)
        for i in st.sel_links:
            idx += [int(st.topo.link_from[i]), int(st.topo.link_to[i])]
        if not idx:
            return
        w, h = self.view_size
        sx, sy = self.to_screen(self.wnx[idx], self.wny[idx])
        if (sx.min() < 0 or sx.max() > w or sy.min() < 0 or sy.max() > h):
            self.cx, self.cy = float(self.wnx[idx].mean()), float(self.wny[idx].mean())
            self.redraw()

    # ---------------------------------------------------------------- input
    def _bind_events(self):
        c = self.canvas
        c.bind("<Configure>", lambda e: self.schedule_redraw(80))
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion_drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<ButtonPress-2>", lambda e: self._press(e, pan=True))
        c.bind("<B2-Motion>", self._motion_drag)
        c.bind("<ButtonRelease-2>", self._release)
        c.bind("<Motion>", self._hover)
        c.bind("<MouseWheel>", lambda e: self.zoom_at(e.x, e.y, 1 if e.delta > 0 else -1))
        c.bind("<Button-4>", lambda e: self.zoom_at(e.x, e.y, 1))
        c.bind("<Button-5>", lambda e: self.zoom_at(e.x, e.y, -1))
        c.bind("<Button-3>", self._context)
        c.bind("<Escape>", lambda e: self.cancel_tool())
        c.bind("<Delete>", lambda e: self.actions.delete_selection())
        c.bind("<Enter>", lambda e: c.focus_set())

    def hit(self, x: float, y: float, kinds=("node", "link")):
        """Nearest node within tolerance, else the topmost link under the cursor."""
        c = self.canvas
        nodes, link = [], None
        for item in reversed(c.find_overlapping(x - 7, y - 7, x + 7, y + 7)):
            for tag in c.gettags(item):
                if tag[0] in "NL" and tag[1:].isdigit():
                    if tag[0] == "N" and "node" in kinds:
                        nodes.append(int(tag[1:]))
                    elif tag[0] == "L" and "link" in kinds and link is None:
                        link = int(tag[1:])
        if nodes:
            sx, sy = self.to_screen(self.wnx[nodes], self.wny[nodes])
            return "node", nodes[int(np.argmin((sx - x) ** 2 + (sy - y) ** 2))]
        return ("link", link) if link is not None else None

    def _press(self, e, pan: bool = False):
        self.canvas.focus_set()
        shift = bool(e.state & 0x0001)
        self._drag = {"x": e.x, "y": e.y, "x0": e.x, "y0": e.y, "moved": False, "box": None, "pan": pan,
                      "shift": shift, "ctrl": bool(e.state & 0x0004), "grab": None}
        if self.mode == "select" and shift and not pan:
            self._drag["box"] = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#0ea5e9", dash=(4, 2),
                                                             width=1.5, tags="hud")
        if self.mode == "move" and not pan:
            hit = self.hit(e.x, e.y, kinds=("node",))
            if hit:
                self._drag["grab"] = hit[1]

    def _motion_drag(self, e):
        d = self._drag
        if not d:
            return
        dx, dy = e.x - d["x"], e.y - d["y"]
        if abs(e.x - d["x0"]) + abs(e.y - d["y0"]) > 3:
            d["moved"] = True
        if d["box"]:
            self.canvas.coords(d["box"], d["x0"], d["y0"], e.x, e.y)
        elif d["grab"] is not None:
            item = self.node_items.get(d["grab"])
            if item:
                self.canvas.move(item, dx, dy)
        else:
            self.canvas.move("world", dx, dy)
            self.cx -= dx * self.res
            self.cy += dy * self.res
        d["x"], d["y"] = e.x, e.y

    def _release(self, e):
        d, self._drag = self._drag, None
        if not d:
            return
        if d["box"]:
            self.canvas.delete(d["box"])
            self._box_select(d["x0"], d["y0"], e.x, e.y, add=d["ctrl"])
            return
        if d["grab"] is not None:
            if d["moved"]:
                wx, wy = self.to_world(e.x, e.y)
                x, y = self.state.crs.from_world(wx, wy)
                self.actions.move_node(d["grab"], float(x), float(y))
            return
        if d["moved"]:
            if self._culled:
                self.redraw()
            else:
                self.draw_tiles()
                self.canvas.delete("hud"); self.recolor()
            return
        self._click(e, add=d["ctrl"] or d["shift"])

    def _click(self, e, add: bool):
        st = self.state
        if not st.loaded:
            return
        if self.mode == "add_junction":
            wx, wy = self.to_world(e.x, e.y)
            x, y = st.crs.from_world(wx, wy)
            self.actions.add_junction(float(x), float(y))
            return
        hit = self.hit(e.x, e.y)
        if self.mode == "add_pipe":
            if not hit or hit[0] != "node":
                self.actions.status("Click on a node.")
                return
            if self._pipe_start is None:
                self._pipe_start = hit[1]
                self.draw_selection(); self.canvas.delete("hud"); self.recolor()
            elif hit[1] != self._pipe_start:
                start, self._pipe_start = self._pipe_start, None
                self.actions.add_pipe(start, hit[1])
            return
        if hit is None:
            if not add:
                st.select(source="map")
            return
        kind, i = hit
        if add:
            target = st.sel_nodes if kind == "node" else st.sel_links
            if i in target:
                target.discard(i); st.select(st.sel_nodes, st.sel_links, source="map")
                return
        st.select(nodes=[i] if kind == "node" else [], links=[i] if kind == "link" else [], add=add, source="map")

    def _box_select(self, x0, y0, x1, y1, add: bool):
        st = self.state
        if not st.loaded:
            return
        lo_x, hi_x = sorted((x0, x1)); lo_y, hi_y = sorted((y0, y1))
        sx, sy = self.to_screen(self.wnx, self.wny)
        inside = (sx >= lo_x) & (sx <= hi_x) & (sy >= lo_y) & (sy <= hi_y)
        nodes = np.where(inside)[0].tolist()
        links = [i for i in range(len(st.topo.link_ids)) if inside[st.topo.link_from[i]] and inside[st.topo.link_to[i]]]
        st.select(nodes, links, add=add, source="map")
        self.actions.status(f"Selected {len(nodes)} nodes and {len(links)} links.")

    def _hover(self, e):
        if self._hover_job:
            self.after_cancel(self._hover_job)
        self._hover_job = self.after(25, lambda: self._do_hover(e.x, e.y))

    def _do_hover(self, x, y):
        self._hover_job = None
        st, c = self.state, self.canvas
        c.delete("tip")
        wx, wy = self.to_world(x, y)
        nx_, ny_ = st.crs.from_world(wx, wy)
        coord = f"X {float(nx_):,.2f}  Y {float(ny_):,.2f}"
        ll = st.crs.world_to_lonlat(wx, wy)
        if ll:
            coord += f"   ·   {ll[1]:.5f}°N {ll[0]:.5f}°E"
        self.actions.coords(coord)
        if not st.loaded or self._drag:
            return
        hit = self.hit(x, y)
        if not hit:
            return
        kind, i = hit
        topo = st.topo
        oid = topo.node_ids[i] if kind == "node" else topo.link_ids[i]
        otype = topo.node_types[i] if kind == "node" else topo.link_types[i]
        lines = [f"{otype} {oid}"]
        key = st.style.node_var if kind == "node" else st.style.link_var
        if key not in ("type", "none"):
            vals = st.values(kind, key)
            if vals is not None:
                lines.append(f"{st.label_for(kind, key)}: {fmt(vals[i])}")
        if kind == "link" and st.active is not None:
            flow = st.values(kind, "res:flow", stat="At time", delta=False)
            if flow is not None and key != "res:flow":
                lines.append(f"Flow: {fmt(flow[i])} {topo.flow_units}")
        if kind == "node" and st.active is not None and key != "res:pressure":
            p = st.values(kind, "res:pressure", stat="At time", delta=False)
            if p is not None:
                lines.append(f"Pressure: {fmt(p[i])}")
        text = "\n".join(lines)
        t = c.create_text(x + 14, y + 12, text=text, anchor="nw", font=("TkDefaultFont", 9), fill="#0f172a",
                          tags=("tip", "hud"))
        x0, y0, x1, y1 = c.bbox(t)
        bg = c.create_rectangle(x0 - 5, y0 - 3, x1 + 5, y1 + 3, fill="#fffbeb", outline="#f59e0b", tags=("tip", "hud"))
        c.tag_lower(bg, t)

    def _context(self, e):
        st = self.state
        if not st.loaded:
            return
        hit = self.hit(e.x, e.y)
        menu = tk.Menu(self, tearoff=0)
        if hit:
            kind, i = hit
            if (kind == "node" and i not in st.sel_nodes) or (kind == "link" and i not in st.sel_links):
                st.select(nodes=[i] if kind == "node" else [], links=[i] if kind == "link" else [], source="map")
            oid = st.topo.node_ids[i] if kind == "node" else st.topo.link_ids[i]
            menu.add_command(label=f"{kind.title()} {oid}", state="disabled")
            menu.add_command(label="Copy ID", command=lambda: (self.clipboard_clear(), self.clipboard_append(oid)))
            menu.add_command(label="Show in data browser", command=lambda: self.actions.show_browser(kind))
            menu.add_command(label="Time series…", command=lambda: self.actions.show_series(kind))
            if kind == "node":
                menu.add_command(label="Select connected links", command=lambda: st.select(
                    [i], [j for j in range(len(st.topo.link_ids)) if i in (st.topo.link_from[j], st.topo.link_to[j])],
                    source="map"))
                menu.add_command(label="Add as MSX source…", command=lambda: self.actions.msx_source(i))
                menu.add_command(label="Trace quality from here", command=lambda: self.actions.trace_from(i))
            menu.add_separator()
            menu.add_command(label="Delete", command=self.actions.delete_selection)
            menu.add_separator()
        menu.add_command(label="Zoom to network", command=self.zoom_extent)
        if st.sel_nodes or st.sel_links:
            menu.add_command(label="Zoom to selection", command=self.zoom_selection)
        menu.tk_popup(e.x_root, e.y_root)

    def zoom_selection(self):
        st = self.state
        idx = list(st.sel_nodes)
        for i in st.sel_links:
            idx += [int(st.topo.link_from[i]), int(st.topo.link_to[i])]
        if idx:
            self.zoom_extent(sorted(set(idx)))

    def set_mode(self, mode: str):
        self.mode = mode
        self._pipe_start = None
        self.canvas.configure(cursor={"select": "crosshair", "add_junction": "plus", "add_pipe": "pencil",
                                      "move": "fleur"}.get(mode, "crosshair"))
        self.canvas.delete("hud"); self.canvas.delete("sel")
        if self.state.loaded:
            self.recolor(); self.draw_selection()

    def cancel_tool(self):
        if self._pipe_start is not None:
            self._pipe_start = None
            self.draw_selection(); self.canvas.delete("hud"); self.recolor()
        else:
            self.state.select(source="map")
