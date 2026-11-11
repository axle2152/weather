"""Sunrise/sunset, twilight and moon phases for the Almanac slide."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import ephem


@dataclass
class SunDay:
    label: str
    date: dt.date
    sunrise: dt.datetime | None
    sunset: dt.datetime | None
    dawn: dt.datetime | None     # civil twilight begins
    dusk: dt.datetime | None     # civil twilight ends

    @property
    def daylight(self) -> dt.timedelta | None:
        if self.sunrise and self.sunset and self.sunset > self.sunrise:
            return self.sunset - self.sunrise
        return None


@dataclass
class MoonPhase:
    name: str        # "New", "First Quarter", "Full", "Last Quarter"
    key: str         # image name: new, first, full, last
    when: dt.datetime


@dataclass
class Almanac:
    days: list = field(default_factory=list)
    moons: list = field(default_factory=list)


def _local(d: ephem.Date, tz: ZoneInfo) -> dt.datetime:
    return d.datetime().replace(tzinfo=dt.timezone.utc).astimezone(tz)


def _event(obs: ephem.Observer, start: dt.datetime, horizon: str, rising: bool, center: bool, tz):
    obs.horizon = horizon
    obs.date = ephem.Date(start.astimezone(dt.timezone.utc).replace(tzinfo=None))
    try:
        fn = obs.next_rising if rising else obs.next_setting
        when = _local(fn(ephem.Sun(), use_center=center), tz)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        return None
    # Only count it if it happens on the same local day.
    return when if when.date() == start.date() else None


def compute_almanac(lat: float, lon: float, tzname: str, now: dt.datetime | None = None) -> Almanac:
    tz = ZoneInfo(tzname)
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)
    obs = ephem.Observer()
    obs.lat, obs.lon = str(lat), str(lon)
    obs.pressure = 0
    days = []
    for offset, label in ((0, "Today"), (1, "Tomorrow")):
        day = now.date() + dt.timedelta(days=offset)
        midnight = dt.datetime.combine(day, dt.time(0, 0), tzinfo=tz)
        days.append(SunDay(
            label=label, date=day,
            sunrise=_event(obs, midnight, "-0:34", True, False, tz),
            sunset=_event(obs, midnight, "-0:34", False, False, tz),
            dawn=_event(obs, midnight, "-6", True, True, tz),
            dusk=_event(obs, midnight, "-6", False, True, tz),
        ))
    start = ephem.Date(now.astimezone(dt.timezone.utc).replace(tzinfo=None))
    moons = [
        MoonPhase("New", "new", _local(ephem.next_new_moon(start), tz)),
        MoonPhase("First Quarter", "first", _local(ephem.next_first_quarter_moon(start), tz)),
        MoonPhase("Full", "full", _local(ephem.next_full_moon(start), tz)),
        MoonPhase("Last Quarter", "last", _local(ephem.next_last_quarter_moon(start), tz)),
    ]
    moons.sort(key=lambda m: m.when)
    return Almanac(days=days, moons=moons)


def is_daytime(lat: float, lon: float, when: dt.datetime) -> bool:
    """True if the sun is up at this place and time."""
    obs = ephem.Observer()
    obs.lat, obs.lon = str(lat), str(lon)
    obs.date = ephem.Date(when.astimezone(dt.timezone.utc).replace(tzinfo=None))
    return float(ephem.Sun(obs).alt) > -0.0145  # about -0.83 degrees (refraction + sun's radius)
