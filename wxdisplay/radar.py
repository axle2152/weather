"""Radar loop frames over a locally built basemap.

Primary source: the Iowa Environmental Mesonet (IEM) NEXRAD base reflectivity
composite (N0Q), requested as one image per frame for exactly our map view.
Fallback: the NWS's ready-made loop GIF for the nearest radar site.

The basemap is built once per location/size and cached in cache/:
USGS shaded relief (public domain), tinted, with state/county lines and
Interstates drawn from bundled Census outlines.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import math
import time
from dataclasses import dataclass, field

import requests
from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageSequence

from . import geo
from .config import ASSETS, Config
from .location import Site

log = logging.getLogger(__name__)

IEM_WMS = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q.cgi"
IEM_LATEST = "https://mesonet.agron.iastate.edu/data/gis/images/4326/USCOMP/n0q_0.json"
NWS_LOOP = "https://radar.weather.gov/ridge/standard/{site}_loop.gif"
RELIEF_TILES = ("https://basemap.nationalmap.gov/arcgis/rest/services/"
                "USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}")
STEP = dt.timedelta(minutes=5)
MAP_VERSION = 4  # bump to rebuild cached basemaps after style changes


def _load_palette() -> list:
    with open(ASSETS / "radar" / "n0q_palette.json") as f:
        return [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in json.load(f)["colors"]]


PALETTE = _load_palette()


def dbz_color(dbz: float) -> tuple:
    return PALETTE[max(1, min(255, int(round((dbz + 32.5) * 2))))]


@dataclass
class RadarFrames:
    source: str                          # "iem" or "nws"
    frames: list                         # [(datetime | None, PIL RGBA image)], oldest first
    basemap: Image.Image | None = None   # RGB, same size as frames (IEM only)
    view: geo.MapView | None = None      # for projecting labels and warning polygons
    labels: list = field(default_factory=list)  # [(name, x, y, is_home)]
    attribution: str = ""


class Radar:
    def __init__(self, cfg: Config, site: Site, size: tuple, scale: float, user_agent: str):
        self.cfg, self.site, self.scale = cfg, site, scale
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        lat, lon = site.lat, site.lon
        if cfg.radar.center:
            p = geo.lookup_place(cfg.radar.center)
            lat, lon = p.lat, p.lon
        self.view = geo.MapView(lat, lon, cfg.radar.zoom + math.log2(scale), *size)
        self.cache: dict = {}            # frame time -> processed image
        self.last_valid: dt.datetime | None = None
        self.basemap: Image.Image | None = None
        self.labels = self._labels()
        self.iem_failures = 0
        self.gif_checked = 0.0

    # ------------------------------------------------------------- public

    def update(self) -> RadarFrames | None:
        """Called every couple of minutes from the updater thread. None = nothing new."""
        if self.cfg.radar.source == "nws":
            return self._update_gif()
        if self.iem_failures >= 3 and time.time() - self.gif_checked < 1800:
            return self._update_gif()
        try:
            frames = self._update_iem()
            self.iem_failures = 0
            return frames
        except Exception as e:
            self.iem_failures += 1
            log.warning("IEM radar failed (%d in a row): %s", self.iem_failures, e)
            if self.iem_failures >= 3:
                self.gif_checked = time.time()
                return self._update_gif()
            return None

    # ---------------------------------------------------------------- IEM

    def _get(self, url, **kw) -> requests.Response:
        r = self.session.get(url, timeout=(6, 30), **kw)
        r.raise_for_status()
        return r

    def _latest_valid(self) -> dt.datetime:
        meta = self._get(IEM_LATEST).json()["meta"]
        return dt.datetime.fromisoformat(meta["valid"].replace("Z", "+00:00"))

    def _update_iem(self) -> RadarFrames | None:
        if self.basemap is None:
            self.basemap = self._basemap()
        valid = self._latest_valid()
        n = self.cfg.radar.frames
        want = [valid - STEP * k for k in range(n - 1, -1, -1)]
        if valid == self.last_valid and all(t in self.cache for t in want):
            return None
        fetched = {}
        for t in want:
            if t not in self.cache:
                minutes = int((valid - t) / dt.timedelta(minutes=1))
                fetched[t] = self._fetch_frame(minutes)
        # The "N minutes ago" layers shift when a new composite arrives. If that
        # happened while we were downloading, the frames may be mislabeled: retry later.
        if fetched and self._latest_valid() != valid:
            log.info("radar composite advanced during download; retrying next cycle")
            return None
        self.cache.update(fetched)
        self.cache = {t: im for t, im in self.cache.items() if t in want}
        self.last_valid = valid
        frames = [(t, self.cache[t]) for t in want if t in self.cache]
        return RadarFrames("iem", frames, self.basemap, self.view, self.labels,
                           "Radar: Iowa Environmental Mesonet  ·  Map: USGS, US Census Bureau")

    def _fetch_frame(self, minutes_ago: int) -> Image.Image:
        layer = "nexrad-n0q-900913" + (f"-m{minutes_ago:02d}m" if minutes_ago else "")
        x0, y0, x1, y1 = self.view.bbox_meters
        params = dict(SERVICE="WMS", REQUEST="GetMap", VERSION="1.1.1", LAYERS=layer, STYLES="",
                      SRS="EPSG:3857", BBOX=f"{x0},{y0},{x1},{y1}", WIDTH=self.view.width,
                      HEIGHT=self.view.height, FORMAT="image/png", TRANSPARENT="true")
        r = self._get(IEM_WMS, params=params)
        if not r.headers.get("Content-Type", "").startswith("image/"):
            raise RuntimeError(f"radar server sent {r.headers.get('Content-Type')}: {r.text[:200]}")
        return self._clean(Image.open(io.BytesIO(r.content)))

    def _clean(self, img: Image.Image) -> Image.Image:
        """Hide returns weaker than min_dbz (ground clutter, clear-air echoes)."""
        img = img.convert("RGBA")
        alpha = img.getchannel("A")
        pal = Image.new("P", (1, 1))
        pal.putpalette([c for rgb in PALETTE for c in rgb])
        idx = img.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE)
        threshold = self.cfg.radar.min_dbz
        lut = [0] + [235 if i * 0.5 - 32.5 >= threshold else 0 for i in range(1, 256)]
        keep = Image.frombytes("L", idx.size, idx.tobytes()).point(lut)
        out = idx.convert("RGBA")
        out.putalpha(ImageChops.darker(keep, alpha))
        return out

    # ------------------------------------------------------------ basemap

    def _basemap(self) -> Image.Image:
        v = self.view
        path = self.cfg.cache_dir / (f"basemap_v{MAP_VERSION}_{v.key()}_"
                                     f"{int(self.cfg.radar.counties)}{int(self.cfg.radar.interstates)}.png")
        if path.exists():
            return Image.open(path).convert("RGB")
        log.info("building radar basemap (first run for this location/size)...")
        relief = self._stitch_tiles(RELIEF_TILES)
        gray = ImageOps.autocontrast(ImageOps.grayscale(relief), cutoff=1)
        land = ImageOps.colorize(gray, black=(18, 30, 24), mid=(58, 78, 60), white=(104, 124, 96))
        water = Image.new("RGB", land.size, (20, 38, 60))
        base = Image.composite(land, water, self._land_mask()).convert("RGBA")
        base.alpha_composite(self._outlines())
        base = base.convert("RGB")
        base.save(path)
        return base

    def _stitch_tiles(self, template: str, mode: str = "RGB") -> Image.Image:
        v = self.view
        z = min(13, math.ceil(v.zoom - 1e-6))
        ratio = 2 ** (z - v.zoom)               # tile pixels per output pixel
        world = 256 * 2 ** z
        cx = (v.lon + 180) / 360 * world
        cy = (1 - math.asinh(math.tan(math.radians(v.lat))) / math.pi) / 2 * world
        w, h = v.width * ratio, v.height * ratio
        x0, y0 = cx - w / 2, cy - h / 2
        tx0, ty0 = int(x0 // 256), int(y0 // 256)
        tx1, ty1 = int((x0 + w) // 256), int((y0 + h) // 256)
        canvas = Image.new(mode, ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256),
                           (128, 128, 128) if mode == "RGB" else (0, 0, 0, 0))
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                try:
                    r = self._get(template.format(z=z, x=tx % (2 ** z), y=ty))
                    canvas.paste(Image.open(io.BytesIO(r.content)).convert(mode),
                                 ((tx - tx0) * 256, (ty - ty0) * 256))
                except Exception as e:  # a missing tile just stays flat gray
                    log.debug("tile %s/%s/%s failed: %s", z, tx, ty, e)
        box = (x0 - tx0 * 256, y0 - ty0 * 256, x0 - tx0 * 256 + w, y0 - ty0 * 256 + h)
        return canvas.crop(tuple(round(b) for b in box)).resize((v.width, v.height), Image.LANCZOS)

    def _land_mask(self) -> Image.Image:
        """White where there's land: US states (Census) plus Canada/Mexico/Caribbean (Natural Earth)."""
        v, ss = self.view, 2
        mask = Image.new("L", (v.width * ss, v.height * ss), 0)
        d = ImageDraw.Draw(mask)
        bbox = v.bbox_lonlat

        def ring_px(ring):
            return [(x * ss, y * ss) for x, y in (v.to_px(lon, lat) for lon, lat in ring)]

        for kind in ("neighbors", "states"):
            shapes = geo.shapes_in(kind, bbox)
            for shape in shapes:
                for ring in shape.lines:
                    if len(ring) >= 3:
                        d.polygon(ring_px(ring), fill=255)
                        if kind == "neighbors":  # cover slivers where coarse borders meet US states
                            d.line(ring_px(ring), fill=255, width=round(6 * self.scale * ss))
            for shape in shapes:
                for ring in shape.holes:
                    if len(ring) >= 3:
                        d.polygon(ring_px(ring), fill=0)
        return mask.resize((v.width, v.height), Image.LANCZOS)

    def _outlines(self) -> Image.Image:
        """State/county lines and Interstates, drawn at 2x and scaled down for smooth edges."""
        v, ss = self.view, 2
        s = self.scale * ss
        layer = Image.new("RGBA", (v.width * ss, v.height * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        bbox = v.bbox_lonlat

        def draw(kind, fill, width):
            for shape in geo.shapes_in(kind, bbox):
                for line in shape.lines + shape.holes:
                    pts = [(x * ss, y * ss) for x, y in (v.to_px(lon, lat) for lon, lat in line)]
                    if len(pts) >= 2:
                        d.line(pts, fill=fill, width=max(1, round(width * s)), joint="curve")

        if self.cfg.radar.counties:
            draw("counties", (210, 220, 210, 70), 1.0)
        if self.cfg.radar.interstates:
            draw("interstates", (196, 120, 96, 170), 1.6)
        draw("states", (10, 16, 12, 150), 4.2)    # dark halo under state lines
        draw("states", (236, 240, 236, 235), 2.0)
        return layer.resize((v.width, v.height), Image.LANCZOS)

    def _labels(self) -> list:
        """Home plus the biggest towns in view, spaced so labels don't collide."""
        v = self.view
        labels = [(self.site.name, *v.to_px(self.site.lon, self.site.lat), True)]
        extra = []
        for text in self.cfg.radar.labels:
            try:
                p = geo.lookup_place(text)
                extra.append((p.label.split(",")[0], *v.to_px(p.lon, p.lat), False))
            except LookupError as e:
                log.warning("radar label %r: %s", text, e)
        labels += extra
        margin = 90 * self.scale
        min_gap = 210 * self.scale
        cands = []
        for st, name, lat, lon, pop in geo.places():
            if pop < 15000 or "-" in name or "/" in name:
                continue
            x, y = v.to_px(lon, lat)
            if margin < x < v.width - margin and margin * 0.6 < y < v.height - margin * 0.6:
                cands.append((pop, name, x, y))
        for pop, name, x, y in sorted(cands, reverse=True):
            if len(labels) >= 14:
                break
            if any(n == name or math.hypot(x - lx, (y - ly) * 1.8) < min_gap for n, lx, ly, _ in labels):
                continue
            labels.append((name, x, y, False))
        return labels

    # ---------------------------------------------------------------- NWS

    def _update_gif(self) -> RadarFrames | None:
        site = self.site.radar
        if not site:
            return None
        try:
            r = self._get(NWS_LOOP.format(site=site))
            gif = Image.open(io.BytesIO(r.content))
        except Exception as e:
            log.warning("NWS radar loop failed: %s", e)
            return None
        frames = []
        w, h = self.view.width, self.view.height
        for frame in ImageSequence.Iterator(gif):
            im = frame.convert("RGB")
            k = min(w / im.width, h / im.height)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
            frames.append((None, canvas))
        return RadarFrames("nws", frames, None, None, [], f"Radar: National Weather Service {site}")
