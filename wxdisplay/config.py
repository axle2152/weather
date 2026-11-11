"""Settings, loaded from config.toml (falls back to config.example.toml)."""

from __future__ import annotations

import logging
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
