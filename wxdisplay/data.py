"""Fetches and parses everything the slides show, on a background thread.

The renderer never makes network calls. It reads the latest values from the
DataStore, which this module's Updater refreshes on a schedule.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import geo, units
from .almanac import Almanac, compute_almanac, is_daytime
from .config import Config
from .location import Site, Station
from .nws import NWSClient

log = logging.getLogger(__name__)

STALE_AFTER = dt.timedelta(hours=2, minutes=30)


def parse_time(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- observations

@dataclass
class Obs:
    station: Station
    time: dt.datetime
    text: str = ""
    icon: str | None = None
    temp_f: int | None = None
    dewpoint_f: int | None = None
    humidity: int | None = None
    wind_dir: str | None = None
    wind_mph: int | None = None
    gust_mph: int | None = None
    pressure_in: float | None = None
    pressure_trend: str | None = None   # "Rising" / "Falling" / "Steady"
    visibility_mi: float | None = None
    heat_index_f: int | None = None
    wind_chill_f: int | None = None

    @property
    def feels_like(self) -> tuple[str, int] | None:
        if self.heat_index_f is not None and self.temp_f is not None and self.heat_index_f > self.temp_f:
            return "Heat Index", self.heat_index_f
        if self.wind_chill_f is not None and self.temp_f is not None and self.wind_chill_f < self.temp_f:
            return "Wind Chill", self.wind_chill_f
        return None


# When a station sends no text description, build one from its weather and cloud codes.
WEATHER_CODES = {
    "thunderstorms": ("Thunderstorm", "tsra"), "freezing_rain": ("Freezing Rain", "fzra"),
    "freezing_drizzle": ("Freezing Drizzle", "fzra"), "ice_pellets": ("Sleet", "sleet"),
    "snow": ("Snow", "snow"), "snow_grains": ("Snow", "snow"), "rain": ("Rain", "rain"),
    "drizzle": ("Drizzle", "rain"), "hail": ("Hail", "sleet"), "fog_mist": ("Fog/Mist", "fog"),
    "haze": ("Haze", "haze"), "smoke": ("Smoke", "smoke"), "dust": ("Dust", "dust"), "sand": ("Blowing Sand", "dust"),
}
CLOUD_CODES = {"CLR": ("Clear", "skc"), "SKC": ("Clear", "skc"), "FEW": ("Mostly Clear", "few"),
               "SCT": ("Partly Cloudy", "sct"), "BKN": ("Mostly Cloudy", "bkn"),
               "OVC": ("Overcast", "ovc"), "VV": ("Overcast", "ovc")}
CLOUD_ORDER = ["CLR", "SKC", "FEW", "SCT", "BKN", "OVC", "VV"]
ICON_URL = "https://api.weather.gov/icons/land/{tod}/{code}?size=medium"


def describe_sky(reports: list, station: Station, when: dt.datetime) -> tuple[str, str | None]:
    """(text, icon URL) from presentWeather / cloudLayers, or ("", None) if there's nothing."""
    tod = "day" if is_daytime(station.lat, station.lon, when) else "night"
    for p in reports:
        for w in p.get("presentWeather") or []:
            if w.get("weather") in WEATHER_CODES:
                text, code = WEATHER_CODES[w["weather"]]
                if w.get("intensity") in ("light", "heavy") and code not in ("fog", "haze", "smoke", "dust"):
                    text = w["intensity"].title() + " " + text
                return text, ICON_URL.format(tod=tod, code=code)
        amounts = [c.get("amount") for c in p.get("cloudLayers") or [] if c.get("amount") in CLOUD_CODES]
        if amounts:
            text, code = CLOUD_CODES[max(amounts, key=CLOUD_ORDER.index)]
            if text == "Clear" and tod == "day":
                text = "Sunny"
            return text, ICON_URL.format(tod=tod, code=code)
    return "", None


def _value(props: dict, key: str):
    v = props.get(key)
    return v.get("value") if isinstance(v, dict) else v


def parse_obs(station: Station, history: list, now: dt.datetime) -> Obs | None:
    """Build one observation from a station's recent reports (newest first).

    Stations often leave fields blank in a single report (KATL regularly sends
    no sky condition), so each field falls back to the most recent report
    within the last two hours that has it. Reports older than 2.5 hours are
    treated as "no report".
    """
    reports = [(parse_time(p.get("timestamp")), p) for p in history]
    reports = [(t, p) for t, p in reports if t]
    if not reports:
        return None
    reports.sort(key=lambda r: r[0], reverse=True)
    newest = reports[0][0]
    if now - newest > STALE_AFTER:
        return None
    recent = [p for t, p in reports if newest - t <= dt.timedelta(hours=2)]

    def first(key):
        for p in recent:
            v = _value(p, key)
            if v not in (None, ""):
                return v
        return None

    wind_kmh = first("windSpeed")
    pressure = first("barometricPressure") or first("seaLevelPressure")
    text, icon = first("textDescription") or "", first("icon")
    if not text or not icon:
        sky_text, sky_icon = describe_sky(recent, station, newest)
        text, icon = text or sky_text, icon or sky_icon
    return Obs(
        station=station, time=newest,
        text=text,
        icon=icon,
        temp_f=units.c_to_f(first("temperature")),
        dewpoint_f=units.c_to_f(first("dewpoint")),
        humidity=None if first("relativeHumidity") is None else round(first("relativeHumidity")),
        wind_dir=units.cardinal(first("windDirection")),
        wind_mph=units.kmh_to_mph(wind_kmh),
        gust_mph=units.kmh_to_mph(_value(recent[0], "windGust")),
        pressure_in=units.pa_to_inhg(pressure),
        visibility_mi=units.m_to_miles(first("visibility")),
        heat_index_f=units.c_to_f(_value(recent[0], "heatIndex")),
        wind_chill_f=units.c_to_f(_value(recent[0], "windChill")),
    )


def pressure_trend(history: list) -> str | None:
    """Compare pressure now with about three hours ago (needs ~12 reports of history)."""
    pts = []
    for p in history:
        t = parse_time(p.get("timestamp"))
        v = _value(p, "barometricPressure") or _value(p, "seaLevelPressure")
        if t and v:
            pts.append((t, units.pa_to_inhg(v)))
    if len(pts) < 2:
        return None
    pts.sort(reverse=True)
    t0, p0 = pts[0]
    target = t0 - dt.timedelta(hours=3)
    t3, p3 = min(pts, key=lambda tp: abs(tp[0] - target))
    if abs(t3 - target) > dt.timedelta(minutes=50):
        return None
    change = p0 - p3
    return "Rising" if change >= 0.02 else "Falling" if change <= -0.02 else "Steady"


# -------------------------------------------------------------------- forecast

@dataclass
class Period:
    name: str
    start: dt.datetime
    is_day: bool
    temp: int | None
    wind_dir: str
    wind_speed: str
    short: str
    detailed: str
    icon: str | None
    pop: int | None


@dataclass
class Forecast:
    updated: dt.datetime | None
    periods: list = field(default_factory=list)

    def next_36_hours(self) -> list:
        return self.periods[:3]

    def extended(self, days: int = 4) -> list:
        """(day period, following night's low) for the days after the 36-hour forecast."""
        out = []
        for i in range(3, len(self.periods)):
            p = self.periods[i]
            if not p.is_day:
                continue
            night = self.periods[i + 1] if i + 1 < len(self.periods) and not self.periods[i + 1].is_day else None
            out.append((p, night))
            if len(out) == days:
                break
        return out


def parse_forecast(props: dict) -> Forecast:
    periods = []
    for p in props.get("periods", []):
        periods.append(Period(
            name=p.get("name", ""), start=parse_time(p.get("startTime")), is_day=bool(p.get("isDaytime")),
            temp=p.get("temperature"), wind_dir=p.get("windDirection") or "",
            wind_speed=p.get("windSpeed") or "", short=p.get("shortForecast") or "",
            detailed=p.get("detailedForecast") or "", icon=p.get("icon"),
            pop=_value(p, "probabilityOfPrecipitation"),
        ))
    return Forecast(updated=parse_time(props.get("updateTime") or props.get("updated")), periods=periods)


# ---------------------------------------------------------------------- alerts

# Rough order of importance for sorting bulletins and picking polygon colors.
ALERT_COLORS = {
    "Tornado Emergency": (255, 0, 255), "Tornado Warning": (255, 0, 0),
    "Severe Thunderstorm Warning": (255, 165, 0), "Flash Flood Emergency": (139, 0, 0),
    "Flash Flood Warning": (0, 200, 60), "Extreme Wind Warning": (255, 140, 0),
    "Special Marine Warning": (255, 165, 0), "Snow Squall Warning": (199, 21, 133),
    "Dust Storm Warning": (255, 228, 196), "Special Weather Statement": (255, 228, 181),
    "Tornado Watch": (255, 255, 0), "Severe Thunderstorm Watch": (219, 112, 147),
}


# Alerts issued as storm-based polygons, fetched for the whole radar area.
STORM_EVENTS = ["Tornado Warning", "Severe Thunderstorm Warning", "Flash Flood Warning",
                "Extreme Wind Warning", "Snow Squall Warning", "Special Marine Warning",
                "Dust Storm Warning", "Special Weather Statement", "Flood Warning"]


@dataclass
class Alert:
    id: str
    event: str
    headline: str
    description: str
    instruction: str
    severity: str
    area: str
    expires: dt.datetime | None
    ugc: list
    polygons: list           # list of rings of (lon, lat)
    affects_home: bool = False
    distance_mi: float | None = None

    @property
    def is_warning(self) -> bool:
        return ("Warning" in self.event or "Emergency" in self.event) and "Test" not in self.event

    @property
    def rank(self) -> int:
        e = self.event
        if "Emergency" in e:
            return 0
        if "Warning" in e:
            return 1 if e in ALERT_COLORS else 2
        if "Watch" in e:
            return 3
        if "Advisory" in e:
            return 4
        return 5

    @property
    def color(self) -> tuple:
        if self.event in ALERT_COLORS:
            return ALERT_COLORS[self.event]
        return (255, 80, 80) if self.is_warning else (255, 210, 90)

    def crawl_text(self, tz) -> str:
        until = ""
        if self.expires:
            until = " until " + self.expires.astimezone(tz).strftime("%I:%M %p").lstrip("0")
        body = re.sub(r"\s+", " ", self.description).strip()
        if len(body) > 700:
            body = body[:700].rsplit(" ", 1)[0] + "..."
        return f"{self.event.upper()}{until} for {self.area}.   {body}"


def _rings(geometry: dict | None) -> list:
    if not geometry:
        return []
    if geometry["type"] == "Polygon":
        return [[tuple(c) for c in geometry["coordinates"][0]]]
    if geometry["type"] == "MultiPolygon":
        return [[tuple(c) for c in poly[0]] for poly in geometry["coordinates"]]
    return []


def parse_alerts(features: list, site: Site, cfg: Config) -> list:
    watch = {site.forecast_zone, site.county, *[z.upper() for z in cfg.alerts.extra_zones]}
    alerts = []
    for f in features:
        p = f["properties"]
        if p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        a = Alert(
            id=p.get("id", ""), event=p.get("event", ""), headline=p.get("headline") or p.get("event", ""),
            description=p.get("description") or "", instruction=p.get("instruction") or "",
            severity=p.get("severity", ""), area=p.get("areaDesc", ""),
            expires=parse_time(p.get("ends") or p.get("expires")),
            ugc=(p.get("geocode") or {}).get("UGC", []), polygons=_rings(f.get("geometry")),
        )
        a.affects_home = bool(watch.intersection(a.ugc))
        if a.polygons:
            a.distance_mi = min(geo.miles_to_ring(site.lat, site.lon, r) for r in a.polygons)
            if a.distance_mi == 0:
                a.affects_home = True
        alerts.append(a)
    alerts.sort(key=lambda a: (a.rank, a.distance_mi if a.distance_mi is not None else 0))
    return alerts


def test_alert(site: Site) -> Alert:
    return Alert(
        id="test", event="Test Message", headline="This is a test of the warning crawl",
        description=("This is a test of the warning crawl. There is no weather warning in effect. "
                     "This display is for entertainment and should not be your source for weather "
                     "warnings. Use NOAA Weather Radio or local media for warnings."),
        instruction="", severity="Minor", area=f"{site.name}, {site.state}", expires=None,
        ugc=[site.county], polygons=[], affects_home=True)


# ------------------------------------------------------------------ data store

class DataStore:
    """Latest data for the renderer. Each field has a version number that bumps on change."""

    def __init__(self, site: Site):
        self.site = site
        self.lock = threading.Lock()
        self.current: Obs | None = None
        self.observations: list = []        # list of (Station, Obs | None)
        self.forecast: Forecast | None = None
        self.alerts: list = []
        self.almanac: Almanac | None = None
        self.radar = None                   # radar.RadarFrames
        self.versions: dict = {}
        self.updated: dict = {}

    def put(self, name: str, value) -> None:
        with self.lock:
            setattr(self, name, value)
            self.versions[name] = self.versions.get(name, 0) + 1
            self.updated[name] = utcnow()

    def version(self, name: str) -> int:
        return self.versions.get(name, 0)

    def local_alerts(self, radius: float) -> list:
        return [a for a in self.alerts if a.affects_home
                or (a.distance_mi is not None and a.distance_mi <= radius)]


class Updater(threading.Thread):
    """Refreshes the DataStore on a schedule. Network calls only ever happen here."""

    def __init__(self, cfg: Config, client: NWSClient, store: DataStore, radar=None):
        super().__init__(name="updater", daemon=True)
        self.cfg, self.client, self.store, self.radar = cfg, client, store, radar
        self.site = store.site
        self.stop_event = threading.Event()
        self.alert_states = self._alert_states()
        self.jobs = [  # name, function, seconds between runs
            ("alerts", self.update_alerts, lambda: 60 if self._warning_active() else 120),
            ("current", self.update_current, lambda: 300),
            ("forecast", self.update_forecast, lambda: 1800),
            ("observations", self.update_observations, lambda: 600),
            ("almanac", self.update_almanac, lambda: 1800),
        ]
        if radar is not None:
            self.jobs.append(("radar", self.update_radar, lambda: 120))
        self.next_run = {name: 0.0 for name, _, _ in self.jobs}

    def _warning_active(self) -> bool:
        return any(a.is_warning for a in self.store.local_alerts(self.cfg.alerts.radius_miles))

    def _alert_states(self) -> str:
        """Alerts query: the home state plus any state the radar map shows."""
        states = {self.site.state} if self.site.state else set()
        lon0, lat0 = self.site.lon - 4.5, self.site.lat - 3.0
        for shape in geo.shapes_in("states", (lon0, lat0, self.site.lon + 4.5, self.site.lat + 3.0)):
            if shape.abbr:
                states.add(shape.abbr)
        return ",".join(sorted(states))

    def run_once(self) -> None:
        for name, fn, _ in self.jobs:
            self._run(name, fn)

    def _run(self, name, fn):
        t0 = time.time()
        try:
            fn()
            log.info("updated %s in %.1fs", name, time.time() - t0)
        except Exception:
            log.exception("updating %s failed", name)

    def run(self) -> None:
        while not self.stop_event.is_set():
            now = time.time()
            for name, fn, interval in self.jobs:
                if now >= self.next_run[name]:
                    self._run(name, fn)
                    self.next_run[name] = time.time() + interval()
            self.stop_event.wait(1.0)

    def stop(self) -> None:
        self.stop_event.set()

    # ---- jobs ----

    def update_alerts(self) -> None:
        # Two small queries instead of every alert in the region:
        #  1. everything for the home forecast zone and county (plus any extra zones), and
        #  2. storm-based warnings (the ones with polygons) anywhere the radar map can show.
        zones = sorted({self.site.forecast_zone, self.site.county,
                        *[z.upper() for z in self.cfg.alerts.extra_zones]} - {""})
        home = self.client.alerts(zone=",".join(zones), status="actual")
        storms = self.client.alerts(area=self.alert_states, status="actual", event=",".join(STORM_EVENTS))
        if home is None and storms is None:
            return  # keep showing what we had until NWS answers again
        merged = {f["properties"].get("id"): f for f in (home or []) + (storms or [])}
        alerts = parse_alerts(list(merged.values()), self.site, self.cfg)
        if self.cfg.alerts.test_warning:
            alerts.insert(0, test_alert(self.site))
        self.store.put("alerts", alerts)

    def update_current(self) -> None:
        hist = self.client.observations(self.site.primary.id, limit=14)
        obs = parse_obs(self.site.primary, hist, utcnow())
        if obs:
            obs.pressure_trend = pressure_trend(hist)
            self.client.icon_path(obs.icon)
        self.store.put("current", obs)

    def update_observations(self) -> None:
        stations = self.site.stations
        with ThreadPoolExecutor(max_workers=4) as pool:
            histories = list(pool.map(lambda s: self.client.observations(s.id, limit=4), stations))
        now = utcnow()
        rows = [(s, parse_obs(s, h, now)) for s, h in zip(stations, histories)]
        if self.site.auto_stations:  # drop offline stations, keep the configured count
            rows = [r for r in rows if r[1] is not None]
        rows = rows[: self.cfg.observations.count if self.site.auto_stations else len(rows)]
        for _, o in rows:
            if o:
                self.client.icon_path(o.icon, size="medium")
        self.store.put("observations", rows)

    def update_forecast(self) -> None:
        props = self.client.forecast(self.site.office, self.site.grid_x, self.site.grid_y)
        if props is None:
            return
        fc = parse_forecast(props)
        for p in fc.periods:
            self.client.icon_path(p.icon)
        self.store.put("forecast", fc)

    def update_almanac(self) -> None:
        self.store.put("almanac", compute_almanac(self.site.lat, self.site.lon, self.site.timezone))

    def update_radar(self) -> None:
        frames = self.radar.update()
        if frames is not None:
            self.store.put("radar", frames)
