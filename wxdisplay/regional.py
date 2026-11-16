"""Regional radar and satellite loops, fetched only for the regions shown now and next."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from . import regions
from .config import Config
from .location import Site
from .radar import MAP_CREDIT, REGIONAL_STYLE, BaseMap, Radar, RadarFrames, Satellite

log = logging.getLogger(__name__)


class RegionalMaps:
    def __init__(self, cfg: Config, site: Site, size: tuple, scale: float, user_agent: str):
        self.cfg, self.site, self.size, self.scale, self.ua = cfg, site, size, scale, user_agent
        self.regions = list(cfg.regional.regions) or regions.default_regions(site.lat, site.lon)
        self.do_radar = "regional_radar" in cfg.display.slides
        self.satellite = Satellite(cfg, user_agent) if "regional_satellite" in cfg.display.slides else None
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.radars: dict = {}       # region -> Radar
        self.sat_maps: dict = {}     # region -> (view, overlay image, labels)
        self.sat_cache: dict = {}    # (region, time) -> reprojected frame
        self.radar_out: dict = {}
        self.sat_out: dict = {}
        self.sat_version = -1

    def cycle_regions(self, cycle: int) -> list:
        """The regions shown on the given pass through the slides."""
        if not self.regions:
            return []
        per = min(self.cfg.regional.per_cycle, len(self.regions))
        start = cycle * per
        return list(dict.fromkeys(self.regions[(start + i) % len(self.regions)] for i in range(per)))

    def update(self, wanted: list) -> tuple:
        """Refresh the wanted regions. Returns (radar dict or None, satellite dict or None); None = unchanged."""
        wanted = [w for w in wanted if w in regions.REGIONS] or self.cycle_regions(0) + self.cycle_regions(1)
        wanted = list(dict.fromkeys(wanted))
        return self._update_radar(wanted), self._update_satellite(wanted)

    def _update_radar(self, wanted: list):
        if not self.do_radar:
            return None
        changed = False
        for name in wanted:
            radar = self.radars.get(name)
            if radar is None:
                view = regions.region_view(name, *self.size)
                radar = Radar(self.cfg, self.site, self.size, self.scale, self.ua, view=view,
                              style=REGIONAL_STYLE, frames=self.cfg.regional.radar_frames, region=name)
                self.radars[name] = radar
            frames = radar.update()
            if frames is not None:
                self.radar_out[name] = frames
                changed = True
        for name in [n for n in self.radars if n not in wanted]:
            del self.radars[name]                      # frees its frames; its map stays cached on disk
            changed |= self.radar_out.pop(name, None) is not None
        return dict(self.radar_out) if changed else None

    def _update_satellite(self, wanted: list):
        if self.satellite is None:
            return None
        try:
            self.satellite.update()
        except Exception as e:
            log.warning("satellite update failed: %s", e)
        if not self.satellite.raw:
            return None
        changed = False
        for name in wanted:
            if name in self.sat_out and self.sat_version == self.satellite.version:
                continue
            self.sat_out[name] = self._satellite_frames(name)
            changed = True
        self.sat_version = self.satellite.version
        for name in [n for n in self.sat_out if n not in wanted]:
            del self.sat_out[name]
            self.sat_maps.pop(name, None)
            changed = True
        self.sat_cache = {k: v for k, v in self.sat_cache.items()
                          if k[0] in wanted and k[1] in self.satellite.raw}
        return dict(self.sat_out) if changed else None

    def _satellite_frames(self, name: str) -> RadarFrames:
        if name not in self.sat_maps:
            view = regions.region_view(name, *self.size)
            base = BaseMap(self.cfg, view, self.scale, REGIONAL_STYLE, self.session,
                           home=(self.site.name, self.site.lat, self.site.lon))
            self.sat_maps[name] = (view, base.outlines(borders=True), base.labels(clear_top_right=True))
        view, overlay, labels = self.sat_maps[name]
        frames = []
        for t in sorted(self.satellite.raw):
            key = (name, t)
            if key not in self.sat_cache:
                self.sat_cache[key] = self.satellite.frame_for(self.satellite.raw[t], view)
            frames.append((t, self.sat_cache[key]))
        return RadarFrames("satellite", frames, None, view, labels,
                           f"Satellite: NOAA GOES via Iowa Environmental Mesonet  ·  {MAP_CREDIT}",
                           overlay=overlay, region=name)


# ----------------------------------------------------------- regional weather map

@dataclass
class RegionalMapData:
    view: object
    basemap: object                # PIL RGB image
    cities: list                   # [(cities.City, x, y, is_home)]
    observations: dict             # city name -> Obs | None
    forecasts: dict                # city name -> Forecast


class RegionalWeatherMap:
    """Towns from your area out to the surrounding region, with current conditions and forecasts."""

    def __init__(self, cfg: Config, site: Site, size: tuple, scale: float, user_agent: str, citywx):
        import math
        from . import geo
        from .radar import MapStyle
        self.cfg, self.site, self.scale, self.citywx = cfg, site, scale, citywx
        session = requests.Session()
        session.headers["User-Agent"] = user_agent
        self.view = geo.MapView(site.lat, site.lon, cfg.regional_map.zoom + math.log2(scale), *size)
        style = MapStyle(counties=False, interstates=False, label_min_pop=10 ** 9)
        self.map = BaseMap(cfg, self.view, scale, style, session)
        self.basemap = None
        self.cities = None
        self.forecasts: dict = {}
        self.forecast_time = 0.0

    def _pick(self) -> list:
        """[(name, lat, lon, is_home)]: home plus well-spread bigger towns that fit on the map."""
        from . import geo
        from .cities import lookup_places
        v, sc = self.view, self.scale
        chosen = [(self.site.name, self.site.lat, self.site.lon, True)]
        if self.cfg.regional_map.cities:
            return chosen + [(n, la, lo, False) for n, la, lo in lookup_places(self.cfg.regional_map.cities)]

        def fits(x, y):
            return 120 * sc < x < v.width - 170 * sc and 80 * sc < y < v.height - 120 * sc

        def clear(x, y, picked):
            for _, la, lo, _ in picked:
                px, py = v.to_px(lo, la)
                if abs(px - x) < 250 * sc and abs(py - y) < 150 * sc:
                    return False
            return True
        # Bigger towns first, but closer ones count for more, so the map fills in around home.
        def score(p):
            miles = geo.miles_between(self.site.lat, self.site.lon, p[2], p[3])
            return p[4] / (1 + (miles / 120) ** 2)
        cands = sorted((p for p in geo.places() if p[4] >= 15000 and "-" not in p[1] and "/" not in p[1]),
                       key=score, reverse=True)
        for st, name, lat, lon, pop in cands:
            if len(chosen) >= self.cfg.regional_map.count:
                break
            x, y = v.to_px(lon, lat)
            if fits(x, y) and clear(x, y, chosen) and all(name != c[0] for c in chosen):
                chosen.append((name, lat, lon, False))
        return chosen

    def update(self):
        import time
        from concurrent.futures import ThreadPoolExecutor
        if self.basemap is None:
            self.basemap = self.map.basemap()
        if self.cities is None:
            picks = self._pick()
            resolved = self.citywx.resolve_many([(n, la, lo) for n, la, lo, _ in picks], want_station=True)
            home_names = {n for n, _, _, h in picks if h}
            self.cities = [(c, *self.view.to_px(c.lon, c.lat), c.name in home_names) for c in resolved]
        cities = [c for c, *_ in self.cities]
        with ThreadPoolExecutor(max_workers=4) as pool:
            obs = list(pool.map(self.citywx.current, cities))
            if time.time() - self.forecast_time > 3600 or not self.forecasts:
                fcs = list(pool.map(self.citywx.forecast, cities))
                for c, fc in zip(cities, fcs):
                    if fc:
                        self.forecasts[c.name] = fc
                self.forecast_time = time.time()
        observations = {c.name: o for c, o in zip(cities, obs)}
        return RegionalMapData(self.view, self.basemap, self.cities, observations, dict(self.forecasts))
