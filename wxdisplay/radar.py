"""Radar and satellite loops over locally built maps.

Radar: the Iowa Environmental Mesonet (IEM) NEXRAD base reflectivity composite
(N0Q), requested as one image per frame for exactly our map view. Fallback for
the local radar: the NWS's ready-made loop GIF for the nearest radar site.

Satellite: IEM's archive of the GOES infrared composite for the lower 48
(a new image every 15 minutes), cut out and reprojected for each region.

Maps are built once per view and cached in cache/: USGS shaded relief (public
domain), tinted, with land/water, state/county lines and Interstates drawn from
bundled Census and Natural Earth outlines.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import math
import re
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
IEM_SAT_DIR = "https://mesonet.agron.iastate.edu/archive/data/{day:%Y/%m/%d}/GIS/sat/"
NWS_LOOP = "https://radar.weather.gov/ridge/standard/{site}_loop.gif"
RELIEF_TILES = ("https://basemap.nationalmap.gov/arcgis/rest/services/"
                "USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}")
STEP = dt.timedelta(minutes=5)
MAP_VERSION = 5  # bump to rebuild cached basemaps after style changes
MAP_CREDIT = "Map: USGS, US Census Bureau"


def _load_palette() -> list:
    with open(ASSETS / "radar" / "n0q_palette.json") as f:
        return [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in json.load(f)["colors"]]


PALETTE = _load_palette()


def dbz_color(dbz: float) -> tuple:
    return PALETTE[max(1, min(255, int(round((dbz + 32.5) * 2))))]


@dataclass
class RadarFrames:
    source: str                          # "iem", "nws" or "satellite"
    frames: list                         # [(datetime | None, PIL image)], oldest first
    basemap: Image.Image | None = None   # drawn under the frames (radar)
    view: geo.MapView | None = None      # for projecting labels and warning polygons
    labels: list = field(default_factory=list)  # [(name, x, y, is_home)]
    attribution: str = ""
    overlay: Image.Image | None = None   # drawn over the frames (satellite borders)
    region: str = ""                     # region name for regional slides


@dataclass
class MapStyle:
    counties: bool = True
    interstates: bool = True
    label_min_pop: int = 15000
    label_gap: float = 210               # 1080p pixels between labels
    max_labels: int = 14


REGIONAL_STYLE = MapStyle(counties=False, interstates=False, label_min_pop=90000, label_gap=230, max_labels=14)


class BaseMap:
    """Terrain basemap, outlines and city labels for one map view."""

    def __init__(self, cfg: Config, view: geo.MapView, scale: float, style: MapStyle, session,
                 home: tuple | None = None, extra_labels: list = ()):
        self.cfg, self.view, self.scale, self.style, self.session = cfg, view, scale, style, session
        self.home = home                 # (name, lat, lon) highlighted on the map
        self.extra_labels = extra_labels

    def _get(self, url, **kw) -> requests.Response:
        r = self.session.get(url, timeout=(6, 30), **kw)
        r.raise_for_status()
        return r

    def basemap(self) -> Image.Image:
        v, st = self.view, self.style
        path = self.cfg.cache_dir / (f"basemap_v{MAP_VERSION}_{v.key()}_"
                                     f"{int(st.counties)}{int(st.interstates)}.png")
        if path.exists():
            return Image.open(path).convert("RGB")
        log.info("building a map for %s (first time for this view)...", v.key())
        relief = self._stitch_tiles(RELIEF_TILES)
        gray = ImageOps.autocontrast(ImageOps.grayscale(relief), cutoff=1)
        land = ImageOps.colorize(gray, black=(18, 30, 24), mid=(58, 78, 60), white=(104, 124, 96))
        water = Image.new("RGB", land.size, (20, 38, 60))
        base = Image.composite(land, water, self._land_mask()).convert("RGBA")
        base.alpha_composite(self.outlines())
        base = base.convert("RGB")
        base.save(path)
        return base

    def _stitch_tiles(self, template: str, mode: str = "RGB") -> Image.Image:
        v = self.view
        z = max(0, min(13, math.ceil(v.zoom - 1e-6)))
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
                if not 0 <= ty < 2 ** z:
                    continue
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

    def outlines(self, borders: bool = False) -> Image.Image:
        """State/county lines and Interstates, drawn at 2x and scaled down for smooth edges.

        borders=True also draws coastlines and borders of neighboring countries
        (for satellite views, which have no basemap underneath).
        """
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

        if self.style.counties:
            draw("counties", (210, 220, 210, 70), 1.0)
        if self.style.interstates:
            draw("interstates", (196, 120, 96, 170), 1.6)
        if borders:
            draw("neighbors", (10, 16, 12, 150), 3.6)
            draw("neighbors", (236, 220, 140, 200), 1.6)
        draw("states", (10, 16, 12, 150), 4.2)    # dark halo under state lines
        draw("states", (236, 240, 236, 235), 2.0)
        return layer.resize((v.width, v.height), Image.LANCZOS)

    def labels(self, clear_top_right: bool = False) -> list:
        """Home plus the biggest towns in view, spaced so labels don't collide."""
        v, st = self.view, self.style
        labels = []
        if self.home:
            name, lat, lon = self.home
            x, y = v.to_px(lon, lat)
            if 0 <= x <= v.width and 0 <= y <= v.height:
                labels.append((name, x, y, True))
        for text in self.extra_labels:
            try:
                p = geo.lookup_place(text)
                labels.append((p.label.split(",")[0], *v.to_px(p.lon, p.lat), False))
            except LookupError as e:
                log.warning("map label %r: %s", text, e)
        margin = 90 * self.scale
        min_gap = st.label_gap * self.scale
        cands = []
        sc = self.scale
        for _, name, lat, lon, pop in geo.places():
            if pop < st.label_min_pop or "-" in name or "/" in name:
                continue
            x, y = v.to_px(lon, lat)
            if not (margin < x < v.width - margin and 34 * sc < y < v.height - 34 * sc):
                continue
            if (x < 330 * sc and y < 125 * sc) or y > v.height - 75 * sc:
                continue  # keep clear of the time badge and the credits/legend along the bottom
            if clear_top_right and x > v.width - 520 * sc and y < 125 * sc:
                continue
            cands.append((pop, name, x, y))
        for pop, name, x, y in sorted(cands, reverse=True):
            if len(labels) >= st.max_labels:
                break
            if any(n == name or math.hypot(x - lx, (y - ly) * 1.8) < min_gap for n, lx, ly, _ in labels):
                continue
            labels.append((name, x, y, False))
        return labels


class Radar:
    def __init__(self, cfg: Config, site: Site, size: tuple, scale: float, user_agent: str,
                 view: geo.MapView | None = None, style: MapStyle | None = None, frames: int | None = None,
                 region: str = ""):
        self.cfg, self.site, self.scale = cfg, site, scale
        self.region = region
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        if view is None:
            lat, lon = site.lat, site.lon
            if cfg.radar.center:
                p = geo.lookup_place(cfg.radar.center)
                lat, lon = p.lat, p.lon
            view = geo.MapView(lat, lon, cfg.radar.zoom + math.log2(scale), *size)
            style = style or MapStyle(counties=cfg.radar.counties, interstates=cfg.radar.interstates)
            extra = cfg.radar.labels
        else:
            extra = ()
        self.view = view
        self.n_frames = frames or cfg.radar.frames
        self.map = BaseMap(cfg, view, scale, style or REGIONAL_STYLE, self.session,
                           home=(site.name, site.lat, site.lon), extra_labels=extra)
        self.cache: dict = {}            # frame time -> processed image
        self.last_valid: dt.datetime | None = None
        self.basemap: Image.Image | None = None
        self.labels = self.map.labels()
        self.iem_failures = 0
        self.gif_checked = 0.0

    # ------------------------------------------------------------- public

    def update(self) -> RadarFrames | None:
        """Called every couple of minutes from the updater thread. None = nothing new."""
        if self.region:  # regional maps: IEM only
            try:
                return self._update_iem()
            except Exception as e:
                log.warning("regional radar (%s) failed: %s", self.region, e)
                return None
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
            self.basemap = self.map.basemap()
        valid = self._latest_valid()
        want = [valid - STEP * k for k in range(self.n_frames - 1, -1, -1)]
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
                           f"Radar: Iowa Environmental Mesonet  ·  {MAP_CREDIT}", region=self.region)

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


# --------------------------------------------------------------------- satellite

class Satellite:
    """GOES infrared loop frames for the lower 48, shared by every regional view.

    IEM archives a 4 km infrared composite every 15 minutes as an 8-bit GeoTIFF in
    plain latitude/longitude (west edge -130, north edge 52, 0.04 degrees per pixel).
    """

    LON0, LAT0, RES = -130.0, 52.0, 0.04
    FILE_RE = re.compile(r"conus_goes_ir4km_(\d{4})\.tif")

    def __init__(self, cfg: Config, user_agent: str):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.raw: dict = {}              # time -> L image (whole lower 48)
        self.version = 0
        self._luts = self._make_luts()

    def _get(self, url) -> requests.Response:
        r = self.session.get(url, timeout=(6, 60))
        r.raise_for_status()
        return r

    def _listing(self, day: dt.date) -> list:
        try:
            html = self._get(IEM_SAT_DIR.format(day=day)).text
        except requests.HTTPError:
            return []
        times = []
        for hhmm in sorted(set(self.FILE_RE.findall(html))):
            times.append(dt.datetime(day.year, day.month, day.day, int(hhmm[:2]), int(hhmm[2:]),
                                     tzinfo=dt.timezone.utc))
        return times

    def update(self) -> bool:
        """Download any new frames. True if the set of frames changed."""
        now = dt.datetime.now(dt.timezone.utc)
        times = self._listing(now.date())
        if len(times) < self.cfg.regional.satellite_frames:
            times = self._listing((now - dt.timedelta(days=1)).date()) + times
        want = times[-self.cfg.regional.satellite_frames:]
        changed = False
        for t in want:
            if t in self.raw:
                continue
            url = IEM_SAT_DIR.format(day=t) + f"conus_goes_ir4km_{t:%H%M}.tif"
            try:
                self.raw[t] = Image.open(io.BytesIO(self._get(url).content)).convert("L")
                changed = True
            except Exception as e:
                log.warning("satellite frame %s failed: %s", t, e)
        for t in [t for t in self.raw if t not in want]:
            del self.raw[t]
            changed = True
        if changed:
            self.version += 1
        return changed

    @staticmethod
    def _make_luts():
        """Infrared counts -> a classic look: dark land, bright white cloud tops."""
        gray = []
        for v in range(256):
            if v == 0:
                gray.append(14)                      # no data
                continue
            t = max(0.0, min(1.0, (v - 90) / 120))
            gray.append(round(22 + 233 * t ** 1.25))
        r = [round(g * 0.90) for g in gray]
        g = [round(x * 0.95) for x in gray]
        b = [min(255, x + 14) for x in gray]
        return r, g, b

    def frame_for(self, img: Image.Image, view: geo.MapView) -> Image.Image:
        """Cut the view out of the lower-48 image and reproject it (lat/lon -> Web Mercator)."""
        w, h = view.width, view.height
        lon0, _, lon1, _ = view.bbox_lonlat
        x0 = (lon0 - self.LON0) / self.RES
        x1 = (lon1 - self.LON0) / self.RES
        mesh = []
        strip = 6
        for y in range(0, h, strip):
            y2 = min(h, y + strip)
            lat_top = view.meters_to_lonlat(0, view.y1 - y * view.res)[1]
            lat_bot = view.meters_to_lonlat(0, view.y1 - y2 * view.res)[1]
            sy0 = (self.LAT0 - lat_top) / self.RES
            sy1 = (self.LAT0 - lat_bot) / self.RES
            mesh.append(((0, y, w, y2), (x0, sy0, x0, sy1, x1, sy1, x1, sy0)))
        out = img.transform((w, h), Image.Transform.MESH, mesh, Image.Resampling.BILINEAR)
        r, g, b = self._luts
        return Image.merge("RGB", (out.point(r), out.point(g), out.point(b)))
