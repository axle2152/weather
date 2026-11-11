"""Settings, loaded from config.toml (falls back to config.example.toml)."""

from __future__ import annotations

import json
import logging
import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

RESOLUTIONS = {"1080p": (1920, 1080), "720p": (1280, 720), "480p": (854, 480)}

ALL_SLIDES = ["bulletins", "current", "local_obs", "forecast_36", "extended", "almanac", "radar"]


@dataclass
class LocationConfig:
    place: str = "Atlanta, GA"   # ZIP code, "City, ST", or "lat, lon"
    name: str = ""               # optional display name override


@dataclass
class NWSConfig:
    contact: str = ""            # email or website, sent to NWS in the User-Agent


@dataclass
class DisplayConfig:
    resolution: str = "1080p"
    fullscreen: bool = False
    borderless: bool = False
    fps: int = 30
    slide_seconds: float = 10.0
    ticker_seconds: float = 6.0
    clock_24h: bool = False
    backgrounds: str = "backgrounds"
    background_seconds: float = 0.0  # 0 = change background once per full cycle of slides
    frosted: bool = True
    panel_color: str = "#001829"
    panel_opacity: float = 0.78
    text_color: str = "#FFFFFF"
    slides: list = field(default_factory=lambda: list(ALL_SLIDES))


@dataclass
class ObservationsConfig:
    primary: str = ""            # station for Current Conditions; blank = closest
    stations: dict = field(default_factory=dict)  # station id -> display name; empty = automatic
    count: int = 8               # cities to show when picking automatically
    radius_miles: float = 110    # how far out automatic picks may go


@dataclass
class RadarConfig:
    source: str = "iem"          # "iem" (Iowa Environmental Mesonet) or "nws" (ready-made NWS loop GIF)
    zoom: float = 8.2            # map zoom at 1080p; bigger = closer in
    center: str = ""             # optional "lat, lon" to center the map somewhere else
    frames: int = 10             # up to 12, five minutes apart
    frame_ms: int = 250
    min_dbz: float = 15.0        # hide returns lighter than this (clear-air clutter)
    counties: bool = True
    interstates: bool = True
    labels: list = field(default_factory=list)  # extra map labels, "City, ST" strings


@dataclass
class AlertsConfig:
    radius_miles: float = 40     # storm-based warnings within this distance count as local
    beep: bool = True
    test_warning: bool = False   # show a test message in the warning crawl
    extra_zones: list = field(default_factory=list)  # more NWS zone/county codes to watch, e.g. "GAC089"


@dataclass
class Config:
    location: LocationConfig = field(default_factory=LocationConfig)
    nws: NWSConfig = field(default_factory=NWSConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    observations: ObservationsConfig = field(default_factory=ObservationsConfig)
    radar: RadarConfig = field(default_factory=RadarConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    path: Path | None = None

    @property
    def cache_dir(self) -> Path:
        d = ROOT / "cache"
        d.mkdir(exist_ok=True)
        return d

    @property
    def size(self) -> tuple[int, int]:
        res = self.display.resolution.lower().strip()
        if res in RESOLUTIONS:
            return RESOLUTIONS[res]
        try:
            w, h = (int(v) for v in res.split("x"))
            return w, h
        except ValueError:
            log.warning("Unknown resolution %r, using 1080p", self.display.resolution)
            return RESOLUTIONS["1080p"]

    @property
    def background_dir(self) -> Path:
        p = Path(self.display.backgrounds)
        return p if p.is_absolute() else ROOT / p


def _fill(section_cls, data: dict, section_name: str):
    obj = section_cls()
    known = {f.name for f in fields(section_cls)}
    for key, value in (data or {}).items():
        if key not in known:
            log.warning("config: unknown setting [%s] %s (ignored)", section_name, key)
            continue
        default = getattr(obj, key)
        if isinstance(default, bool) and not isinstance(value, bool):
            log.warning("config: [%s] %s should be true or false", section_name, key)
            continue
        if isinstance(default, float) and isinstance(value, int):
            value = float(value)
        setattr(obj, key, value)
    return obj


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        candidates = [ROOT / "config.toml", ROOT / "config.example.toml"]
        path = next((p for p in candidates if p.exists()), None)
    cfg = Config()
    if path is None:
        log.warning("No config.toml found; using built-in defaults")
        return cfg
    path = Path(path)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    log.info("Loaded settings from %s", path)
    cfg = Config(
        location=_fill(LocationConfig, data.get("location"), "location"),
        nws=_fill(NWSConfig, data.get("nws"), "nws"),
        display=_fill(DisplayConfig, data.get("display"), "display"),
        observations=_fill(ObservationsConfig, data.get("observations"), "observations"),
        radar=_fill(RadarConfig, data.get("radar"), "radar"),
        alerts=_fill(AlertsConfig, data.get("alerts"), "alerts"),
        path=path,
    )
    unknown = [s for s in cfg.display.slides if s not in ALL_SLIDES]
    if unknown:
        log.warning("config: unknown slides %s (choices: %s)", unknown, ", ".join(ALL_SLIDES))
        cfg.display.slides = [s for s in cfg.display.slides if s in ALL_SLIDES]
    cfg.radar.frames = max(1, min(12, int(cfg.radar.frames)))
    cfg.display.panel_opacity = max(0.0, min(1.0, cfg.display.panel_opacity))
    return cfg


# ------------------------------------------------------------------ saving

def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(round(value, 4))
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # JSON string escapes are valid TOML
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"can't write {value!r} to TOML")


EXAMPLE_STATIONS = """\
# To choose the Local Observations cities yourself, uncomment this table and
# list station ID = name to show. Leave it out to pick automatically.
# [observations.stations]
# KATL = "Atlanta"
# KAHN = "Athens"
# KMCN = "Macon"
# KCSG = "Columbus"
# KRMG = "Rome"
# KGVL = "Gainesville"
# KCHA = "Chattanooga"
# KAGS = "Augusta"
"""


def render_config(cfg: Config, example: bool = False) -> str:
    """The settings as a commented TOML file (the same layout as config.example.toml)."""
    v = _toml_value
    loc, nws, d, o, r, a = cfg.location, cfg.nws, cfg.display, cfg.observations, cfg.radar, cfg.alerts
    if example:
        intro = """\
# Weather display settings.
#
# Copy this file to config.toml and edit that copy, or press S in the display
# (or run  python weather.py --settings) to change them in a settings window.
# config.toml is ignored by git, so your contact info stays out of the public
# repository. Every setting is optional; anything you leave out uses the default
# shown here."""
    else:
        intro = """\
# Weather display settings, saved by the settings window.
#
# Change these in the settings window (press S in the display, or run
#  python weather.py --settings), or edit this file by hand. The display picks up
# changes a few seconds after the file is saved."""
    if o.stations:
        stations = "[observations.stations]\n" + "".join(
            f"{v(sid)} = {v(name)}\n" for sid, name in o.stations.items())
    else:
        stations = EXAMPLE_STATIONS
    return f"""{intro}
#
# This display is for entertainment only and must not be relied on for weather
# warnings or used to alert the public. See DISCLAIMER.md.

[location]
# Where the forecast is for. Any of these work:
#   ZIP code:         place = "30303"
#   City, State:      place = "Atlanta, GA"
#   Latitude, Lon:    place = "33.749, -84.388"
# Everything else (NWS office, forecast zone, county, radar site, time zone,
# nearby cities) is looked up automatically.
place = {v(loc.place)}
# Name shown on screen. Leave blank to use the name NWS gives the location.
name = {v(loc.name)}

[nws]
# The National Weather Service asks every app to identify itself with a way
# to reach the person running it (email address or website).
contact = {v(nws.contact)}

[display]
resolution = {v(d.resolution):<16}# "1080p", "720p", "480p", or e.g. "1600x900"
fullscreen = {v(d.fullscreen)}
borderless = {v(d.borderless):<16}# window without a title bar
fps = {v(d.fps)}
slide_seconds = {v(d.slide_seconds):<13}# how long each page stays up (radar runs a little longer)
ticker_seconds = {v(d.ticker_seconds):<12}# how long each line in the bottom bar stays up
clock_24h = {v(d.clock_24h)}
backgrounds = {v(d.backgrounds):<15}# folder of photos (.jpg/.png); one is shown per cycle of slides
background_seconds = {v(d.background_seconds):<8}# 0 = change photo after each full cycle; or a number of seconds
frosted = {v(d.frosted):<19}# blur the photo behind the panels (frosted glass)
panel_color = {v(d.panel_color)}
panel_opacity = {v(d.panel_opacity):<13}# 0 = clear, 1 = solid
text_color = {v(d.text_color)}
# Which slides to show, in order. "bulletins" only appears when there's an alert.
# Choices: {", ".join(ALL_SLIDES)}
slides = {v(d.slides)}

[observations]
# Station for Current Conditions and the bottom bar. Blank = nearest NWS station.
# (Find station IDs at https://www.weather.gov - e.g. KATL is Hartsfield-Jackson.)
primary = {v(o.primary)}
# How many cities to show on Local Observations when picked automatically,
# and how far out (miles) automatic picks can be.
count = {v(o.count)}
radius_miles = {v(o.radius_miles)}

{stations}
[radar]
source = {v(r.source):<20}# "iem" = Iowa Environmental Mesonet (default), "nws" = NWS loop GIF
zoom = {v(r.zoom):<22}# bigger = closer in (7 = several states, 9 = metro area)
center = {v(r.center):<20}# optional: center the map elsewhere, e.g. "Macon, GA"
frames = {v(r.frames):<20}# 1-12 frames, five minutes apart
frame_ms = {v(r.frame_ms):<18}# time per frame
min_dbz = {v(r.min_dbz):<19}# hide echoes weaker than this (ground clutter, bugs, etc.)
counties = {v(r.counties)}
interstates = {v(r.interstates)}
labels = {v(r.labels):<20}# extra cities to label, e.g. ["Peachtree City, GA"]

[alerts]
radius_miles = {v(a.radius_miles):<14}# storm warnings within this distance count as local
beep = {v(a.beep):<22}# beep when the warning crawl starts each pass
test_warning = {v(a.test_warning):<14}# show a test message in the crawl (to check the look)
extra_zones = {v(a.extra_zones):<15}# more NWS zone/county codes to watch, e.g. ["GAC089", "GAZ044"]
"""


def save_config(cfg: Config, path: str | Path | None = None) -> Path:
    """Write settings to config.toml (atomically, so the display never reads half a file)."""
    path = Path(path) if path else ROOT / "config.toml"
    text = render_config(cfg)
    tomllib.loads(text)  # never write a file we couldn't read back
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def config_path(explicit: str | Path | None = None) -> Path | None:
    """The settings file load_config() would read."""
    if explicit:
        return Path(explicit)
    return next((p for p in (ROOT / "config.toml", ROOT / "config.example.toml") if p.exists()), None)
