"""Forecasts and current conditions for lists of cities (Travel Cities, the regional map)."""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from . import geo
from .data import Forecast, Obs, Period, parse_forecast, parse_obs, utcnow
from .location import Station
from .nws import NWSClient

log = logging.getLogger(__name__)

POINT_CACHE_DAYS = 30

# Popular US destinations for the Travel Cities slide (any "City, ST" works in settings).
TRAVEL_CITIES = [
    "New York, NY", "Boston, MA", "Washington, DC", "Philadelphia, PA", "Atlanta, GA", "Orlando, FL",
    "Miami, FL", "Charlotte, NC", "Nashville, TN", "New Orleans, LA", "Chicago, IL", "Detroit, MI",
    "Minneapolis, MN", "St. Louis, MO", "Dallas, TX", "Houston, TX", "San Antonio, TX", "Denver, CO",
    "Salt Lake City, UT", "Phoenix, AZ", "Las Vegas, NV", "Los Angeles, CA", "San Diego, CA",
    "San Francisco, CA", "Seattle, WA", "Portland, OR", "Anchorage, AK", "Honolulu, HI",
]


@dataclass
class City:
    name: str
    lat: float
    lon: float
    office: str
    grid_x: int
    grid_y: int
    timezone: str
    station: str = ""          # nearest observation station


@dataclass
class DayForecast:
    """One day's outlook for a city: the daytime period and the night after it."""
    city: City
    day: Period | None
    night: Period | None

    @property
    def high(self):
        return self.day.temp if self.day else None

    @property
    def low(self):
        return self.night.temp if self.night else None

    @property
    def icon(self):
        return (self.day or self.night).icon if (self.day or self.night) else None

    @property
    def short(self):
        return (self.day or self.night).short if (self.day or self.night) else ""


class CityWeather:
    """Resolves cities to NWS forecast grids once (cached on disk) and fetches their weather."""

    def __init__(self, client: NWSClient, cache_dir):
        self.client = client
        self.path = cache_dir / "city_points.json"
        self.lock = threading.Lock()
        try:
            self.points = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.points = {}

    def _save(self) -> None:
        with self.lock:
            try:
                self.path.write_text(json.dumps(self.points))
            except OSError as e:
                log.warning("couldn't save city lookups: %s", e)

    def city(self, name: str, lat: float, lon: float, want_station: bool = False) -> City | None:
        key = f"{lat:.3f},{lon:.3f}"
        entry = self.points.get(key)
        fresh = entry and time.time() - entry.get("t", 0) < POINT_CACHE_DAYS * 86400
        if not fresh or (want_station and not entry.get("station")):
            pts = self.client.points(lat, lon)
            if pts is None:
                if not entry:
                    return None
            else:
                entry = {"t": time.time(), "office": pts["gridId"], "x": pts["gridX"], "y": pts["gridY"],
                         "tz": pts.get("timeZone") or "UTC", "station": (entry or {}).get("station", ""),
                         "stations_url": pts.get("observationStations", "")}
                if want_station and entry["stations_url"]:
                    d = self.client.get(entry["stations_url"], params={"limit": 1}, retries=2)
                    if d and d.get("features"):
                        entry["station"] = d["features"][0]["properties"]["stationIdentifier"]
                with self.lock:
                    self.points[key] = entry
                self._save()
        return City(name, lat, lon, entry["office"], entry["x"], entry["y"], entry["tz"], entry.get("station", ""))

    def forecast(self, city: City) -> Forecast | None:
        props = self.client.forecast(city.office, city.grid_x, city.grid_y)
        return parse_forecast(props) if props else None

    def current(self, city: City) -> Obs | None:
        if not city.station:
            return None
        hist = self.client.observations(city.station, limit=3)
        return parse_obs(Station(city.station, city.name, city.lat, city.lon), hist, utcnow())

    def resolve_many(self, places: list, want_station: bool = False) -> list:
        """[(name, lat, lon)] -> [City] (skipping any NWS can't place), looked up 4 at a time."""
        with ThreadPoolExecutor(max_workers=4) as pool:
            cities = list(pool.map(lambda p: self.city(*p, want_station=want_station), places))
        return [c for c in cities if c is not None]


def day_forecast(city: City, fc: Forecast, tomorrow: bool) -> DayForecast:
    """Today's (or tomorrow's) daytime forecast and the night after it, in the city's own time zone."""
    tz = ZoneInfo(city.timezone)
    target = dt.datetime.now(tz).date() + dt.timedelta(days=1 if tomorrow else 0)
    periods = fc.periods
    for i, p in enumerate(periods):
        if p.is_day and p.start and p.start.astimezone(tz).date() >= target:
            night = periods[i + 1] if i + 1 < len(periods) and not periods[i + 1].is_day else None
            return DayForecast(city, p, night)
    # Evening, today's day period is gone: show tonight
    night = next((p for p in periods if not p.is_day), None)
    return DayForecast(city, None, night)


def lookup_places(names: list) -> list:
    """["City, ST", ...] -> [(display name, lat, lon)], skipping names that can't be found."""
    out = []
    for text in names:
        try:
            p = geo.lookup_place(text)
        except LookupError as e:
            log.warning("city %r: %s", text, e)
            continue
        out.append((p.label.split(",")[0] if "," in p.label else text, p.lat, p.lon))
    return out
