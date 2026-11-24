"""XYZ basemap tiles: providers, a disk cache, and background downloading.

Downloads happen in worker threads; Tk images are only created on the main
thread by :meth:`TileCache.poll`.  Tiles are cached on disk so a session can
continue offline and public tile servers are not hit repeatedly (their usage
policies require caching and an identifying User-Agent).
"""
from __future__ import annotations

import io
import math
import queue
import threading
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageTk

HALF = 20037508.342789244
TILE = 256
USER_AGENT = "EPANET-Addons-Workbench/1.0 (desktop hydraulic model viewer)"

PROVIDERS: dict[str, dict] = {
    "None": {},
    "Esri Light Gray": {"url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
                        "max_zoom": 16, "attribution": "Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors"},
    "Esri Dark Gray": {"url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
                       "max_zoom": 16, "attribution": "Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors"},
    "OpenStreetMap": {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "max_zoom": 19,
                      "attribution": "© OpenStreetMap contributors"},
    "OpenTopoMap": {"url": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "subdomains": "abc", "max_zoom": 17,
                    "attribution": "© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)"},
    "Esri World Topo": {"url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
                        "max_zoom": 19, "attribution": "Tiles © Esri — Esri, HERE, Garmin, USGS, © OpenStreetMap contributors"},
    "Esri World Imagery": {"url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                           "max_zoom": 19, "attribution": "Imagery © Esri, Maxar, Earthstar Geographics"},
    "ČÚZK Ortofoto (CZ)": {"url": "https://ags.cuzk.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}",
                           "max_zoom": 20, "attribution": "© ČÚZK"},
}


MAX_VIEW_ZOOM = 21


def resolution_for_zoom(z: int) -> float:
    return 2 * HALF / (TILE * 2 ** z)


def zoom_for_resolution(res: float) -> float:
    return math.log2(2 * HALF / (TILE * res))


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """World (EPSG:3857) bounds: minx, miny, maxx, maxy."""
    size = 2 * HALF / 2 ** z
    minx = -HALF + x * size
    maxy = HALF - y * size
    return minx, maxy - size, minx + size, maxy


class TileCache:
    def __init__(self, root: Path | None = None, on_ready=None, memory: int = 600):
        self.root = root or Path.home() / ".cache" / "epanet-workbench" / "tiles"
        self.on_ready = on_ready
        self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="tiles")
        self._done: queue.Queue = queue.Queue()
        self._inflight: set = set()
        self._failed: set = set()
        self._raw: OrderedDict = OrderedDict()   # (prov,z,x,y) -> PIL image
        self._photo: OrderedDict = OrderedDict()  # (prov,z,x,y,fade,dark) -> PhotoImage
        self._memory = memory
        self._lock = threading.Lock()
        self.offline_errors = 0

    def _path(self, provider: str, z: int, x: int, y: int) -> Path:
        safe = "".join(c if c.isalnum() else "_" for c in provider)
        return self.root / safe / str(z) / str(x) / f"{y}.tile"

    def get(self, provider: str, z: int, x: int, y: int, fade: float):
        """Return a PhotoImage, or None and schedule a download."""
        pkey = (provider, z, x, y, round(fade, 2))
        if pkey in self._photo:
            self._photo.move_to_end(pkey)
            return self._photo[pkey]
        # Beyond the provider's native zoom, crop and enlarge the ancestor tile.
        zmax = (PROVIDERS.get(provider) or {}).get("max_zoom", 19)
        k = max(0, z - zmax)
        key = (provider, z - k, x >> k, y >> k)
        raw = self._raw.get(key)
        if raw is None:
            if key not in self._inflight and key not in self._failed:
                self._inflight.add(key)
                self._pool.submit(self._fetch, key)
            return None
        img = raw
        if k:
            part = TILE / 2 ** k
            ox, oy = (x % 2 ** k) * part, (y % 2 ** k) * part
            img = raw.crop((int(ox), int(oy), int(ox + part), int(oy + part))).resize((TILE, TILE), Image.BILINEAR)
        if fade > 0:
            base = "#111318" if "Dark" in provider else "#ffffff"
            img = Image.blend(img, Image.new("RGB", img.size, base), min(fade, 0.95))
        photo = ImageTk.PhotoImage(img)
        self._photo[pkey] = photo
        while len(self._photo) > self._memory:
            self._photo.popitem(last=False)
        return photo

    def _fetch(self, key):
        provider, z, x, y = key
        spec = PROVIDERS.get(provider) or {}
        path = self._path(*key)
        data = None
        try:
            if path.is_file():
                data = path.read_bytes()
            else:
                subs = spec.get("subdomains", "")
                url = spec["url"].format(z=z, x=x, y=y, s=subs[(x + y) % len(subs)] if subs else "")
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            img = Image.open(io.BytesIO(data)).convert("RGB")
            self._done.put((key, img))
        except Exception:
            self._done.put((key, None))

    def poll(self) -> bool:
        """Move finished downloads into memory; return True if any arrived."""
        arrived = False
        while True:
            try:
                key, img = self._done.get_nowait()
            except queue.Empty:
                break
            self._inflight.discard(key)
            if img is None:
                self._failed.add(key)
                self.offline_errors += 1
                continue
            self._raw[key] = img
            while len(self._raw) > self._memory * 2:
                self._raw.popitem(last=False)
            arrived = True
        return arrived

    def retry_failed(self):
        self._failed.clear()
        self.offline_errors = 0
