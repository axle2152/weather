"""Work out everything NWS-specific from a single place setting.

One /points lookup gives the forecast office and grid, the zone and county
codes used for alerts, the nearest radar, the time zone and the list of
nearby observation stations, so none of it has to be typed in by hand.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field

from . import geo
from .config import Config
from .nws import NWSClient

log = logging.getLogger(__name__)

CACHE_DAYS = 7


@dataclass
class Station:
    id: str
    name: str
    lat: float
    lon: float


@dataclass
class Site:
    lat: float
    lon: float
    name: str               # display name, e.g. "Atlanta"
    state: str
    office: str             # forecast office, e.g. "FFC"
    grid_x: int
    grid_y: int
    forecast_zone: str      # e.g. "GAZ033"
    county: str             # e.g. "GAC121"
    radar: str              # e.g. "KFFC"
    timezone: str           # e.g. "America/New_York"
    primary: Station
    stations: list = field(default_factory=list)   # Local Observations candidates, in display order
    auto_stations: bool = True

    def describe(self) -> str:
        return (f"{self.name}, {self.state} ({self.lat:.4f}, {self.lon:.4f})\n"
                f"  NWS office {self.office}, grid {self.grid_x},{self.grid_y}\n"
                f"  forecast zone {self.forecast_zone}, county {self.county}\n"
                f"  radar {self.radar}, time zone {self.timezone}\n"
                f"  current conditions from {self.primary.id} ({self.primary.name})\n"
                f"  local observations: " + ", ".join(f"{s.name} ({s.id})" for s in self.stations))


def _code(url: str | None) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else ""


def station_city(name: str, lat: float, lon: float) -> str:
    """Turn an NWS station name into a short city name for the screen."""
    if "," in name:
        return name.split(",")[0].strip()
    if " / " in name:
        return name.split(" / ")[0].strip()
    words = re.split(r"[\s\-]+", name)
    near = {p[1] for p in geo.places() if abs(p[2] - lat) < 0.25 and abs(p[3] - lon) < 0.3}
    for n in (3, 2, 1):
        candidate = " ".join(words[:n])
        if candidate in near:
            return candidate
    return geo.nearest_place_name(lat, lon) or name.split(" Airport")[0].strip()


def _station_from_feature(f: dict) -> Station:
    p = f["properties"]
    lon, lat = f["geometry"]["coordinates"][:2]
    return Station(p["stationIdentifier"], station_city(p["name"], lat, lon), lat, lon)


def _auto_pick(home: Station, features: list, cfg: Config) -> list:
    """Pick well-spread, recognisable towns around home for Local Observations."""
    cands = []
    for f in features:
        sid = f["properties"]["stationIdentifier"]
        if not re.fullmatch(r"[KPT][A-Z0-9]{3}", sid):
            continue
        st = _station_from_feature(f)
        dist = geo.miles_between(home.lat, home.lon, st.lat, st.lon)
        if dist > cfg.observations.radius_miles:
            continue
        pop = max((p[4] for p in geo.places() if p[1] == st.name
                   and abs(p[2] - st.lat) < 0.3 and abs(p[3] - st.lon) < 0.35), default=0)
        cands.append((pop, -dist, st))
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    picked = [home]
    min_gap = max(15.0, cfg.observations.radius_miles / 4.5)
    for _, _, st in cands:
        if any(s.name == st.name or s.id == st.id for s in picked):
            continue
        if all(geo.miles_between(s.lat, s.lon, st.lat, st.lon) >= min_gap for s in picked):
            picked.append(st)
    # Keep a few spares: stations that are offline get skipped at display time.
    return picked[: cfg.observations.count + 4]


def resolve_site(cfg: Config, client: NWSClient) -> Site:
    place = geo.lookup_place(cfg.location.place)
    cache = cfg.cache_dir / f"site_{place.lat:.4f}_{place.lon:.4f}.json"
    raw = None
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_DAYS * 86400:
        raw = json.loads(cache.read_text())
    if raw is None:
        pts = client.points(place.lat, place.lon)
        if pts is None:
            if cache.exists():
                log.warning("NWS unreachable; using saved location info from %s", cache.name)
                raw = json.loads(cache.read_text())
            else:
                raise RuntimeError(f"NWS has no forecast data for {place.label}. "
                                   "Locations must be in the US (or its territories).")
        else:
            raw = {"points": pts, "stations": client.grid_stations(pts["gridId"], pts["gridX"], pts["gridY"])}
            cache.write_text(json.dumps(raw))
    pts, features = raw["points"], raw["stations"]
    rel = pts.get("relativeLocation", {}).get("properties", {})
    name = cfg.location.name or (rel.get("city") if "," not in place.label or place.label.startswith("ZIP")
                                 else place.label.split(",")[0]) or place.label
    state = rel.get("state", "")

    by_id = {f["properties"]["stationIdentifier"]: f for f in features}
    if cfg.observations.primary:
        pid = cfg.observations.primary.upper()
        f = by_id.get(pid) or client.station(pid)
        if f is None:
            raise RuntimeError(f"Observation station {pid} wasn't found")
        primary = _station_from_feature(f)
    elif features:
        primary = _station_from_feature(features[0])
    else:
        raise RuntimeError("NWS lists no observation stations near this location")
    primary.name = name if geo.miles_between(primary.lat, primary.lon, place.lat, place.lon) < 15 else primary.name

    if cfg.observations.stations:
        stations = []
        for sid, label in cfg.observations.stations.items():
            sid = sid.upper()
            f = by_id.get(sid) or client.station(sid)
            if f is None:
                log.warning("Observation station %s wasn't found; skipping", sid)
                continue
            st = _station_from_feature(f)
            st.name = label or st.name
            stations.append(st)
        auto = False
    else:
        stations = _auto_pick(primary, features, cfg)
        auto = True

    return Site(lat=place.lat, lon=place.lon, name=name, state=state, office=pts["gridId"],
                grid_x=pts["gridX"], grid_y=pts["gridY"], forecast_zone=_code(pts.get("forecastZone")),
                county=_code(pts.get("county")), radar=pts.get("radarStation") or "",
                timezone=pts.get("timeZone") or "America/New_York", primary=primary,
                stations=stations, auto_stations=auto)


def site_to_json(site: Site) -> str:
    return json.dumps(asdict(site), indent=2)
