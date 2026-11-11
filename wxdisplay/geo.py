"""Offline place lookup (ZIP / City, ST / lat,lon) and map math.

The ZIP and place tables come from the US Census Bureau Gazetteer files
(public domain), pre-built into assets/geo by tools/build_geodata.py.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

from .config import ASSETS

GEO = ASSETS / "geo"

STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "PR",
}


@dataclass
class Place:
    lat: float
    lon: float
    label: str


def _norm(name: str) -> str:
    name = name.lower().replace(".", "").replace("'", "")
    name = re.sub(r"\bsaint\b", "st", name)
    name = re.sub(r"\bfort\b", "ft", name)
    return re.sub(r"\s+", " ", name).strip()


@lru_cache(maxsize=1)
def _zips() -> dict:
    with gzip.open(GEO / "zcta.csv.gz", "rt", encoding="utf-8") as f:
        return {r["zip"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def places() -> list:
    """All Census places: (state, name, lat, lon, population). Population is 0 for CDPs."""
    with gzip.open(GEO / "places.csv.gz", "rt", encoding="utf-8") as f:
        return [(r["state"], r["name"], float(r["lat"]), float(r["lon"]), int(r["pop"]))
                for r in csv.DictReader(f)]


@lru_cache(maxsize=1)
def _place_index() -> dict:
    idx: dict = {}
    for st, name, lat, lon, pop in places():
        idx.setdefault(_norm(name), []).append((st, name, lat, lon, pop))
    return idx


def lookup_place(text: str) -> Place:
    """Turn a ZIP code, "City, ST" or "lat, lon" into coordinates. Raises LookupError."""
    text = text.strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise LookupError(f"{text!r} doesn't look like a latitude, longitude")
        return Place(lat, lon, f"{lat:.3f}, {lon:.3f}")

    if re.fullmatch(r"\d{5}(-\d{4})?", text):
        z = text[:5]
        if z not in _zips():
            raise LookupError(f"ZIP code {z} wasn't found. PO-box-only ZIPs have no area; "
                              f"try a nearby ZIP or \"City, ST\" instead.")
        lat, lon = _zips()[z]
        return Place(lat, lon, f"ZIP {z}")

    state = None
    m = re.fullmatch(r"(.+?)[,\s]+([A-Za-z]{2})", text)
    if m and m.group(2).upper() in STATES:
        city, state = m.group(1), m.group(2).upper()
    else:
        city = text
    matches = _place_index().get(_norm(city), [])
    if state:
        matches = [p for p in matches if p[0] == state]
    if not matches:
        hint = " (add the state, like \"Springfield, IL\")" if not state else ""
        raise LookupError(f"Couldn't find a place called {text!r}{hint}")
    states = sorted({p[0] for p in matches})
    if len(states) > 1:
        raise LookupError(f"{city!r} is in several states ({', '.join(states)}); "
                          f"add the state, like \"{city}, {states[0]}\"")
    st, name, lat, lon, _ = max(matches, key=lambda p: p[4])  # biggest if duplicates
    return Place(lat, lon, f"{name}, {st}")


def nearest_place_name(lat: float, lon: float, max_miles: float = 12.0) -> str | None:
    """Name of the most prominent nearby town (bigger and closer wins)."""
    best, best_score = None, 0.0
    dlat = max_miles / 69.0
    for st, name, plat, plon, pop in places():
        if abs(plat - lat) > dlat or abs(plon - lon) > dlat * 1.6:
            continue
        d = miles_between(lat, lon, plat, plon)
        if d > max_miles or "-" in name or "/" in name:
            continue
        score = (pop + 300) / (1.0 + d / 2.0) ** 2
        if score > best_score:
            best, best_score = name, score
    return best


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


# ---- Web Mercator (the projection used by web map tiles and the radar WMS) ----

EARTH_RADIUS = 6378137.0


def lonlat_to_meters(lon: float, lat: float) -> tuple[float, float]:
    lat = max(-85.0, min(85.0, lat))
    x = EARTH_RADIUS * math.radians(lon)
    y = EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


class MapView:
    """A rectangular map of `width` x `height` pixels centered on lat/lon at a (fractional) zoom."""

    def __init__(self, lat: float, lon: float, zoom: float, width: int, height: int):
        self.lat, self.lon, self.zoom = lat, lon, zoom
        self.width, self.height = width, height
        self.res = 2 * math.pi * EARTH_RADIUS / (256 * 2 ** zoom)  # meters per pixel
        self.cx, self.cy = lonlat_to_meters(lon, lat)
        self.x0 = self.cx - width / 2 * self.res
        self.y1 = self.cy + height / 2 * self.res

    @property
    def bbox_meters(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y1 - self.height * self.res, self.x0 + self.width * self.res, self.y1)

    @property
    def bbox_lonlat(self) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = self.bbox_meters
        return (*self.meters_to_lonlat(x0, y0), *self.meters_to_lonlat(x1, y1))

    @staticmethod
    def meters_to_lonlat(x: float, y: float) -> tuple[float, float]:
        lon = math.degrees(x / EARTH_RADIUS)
        lat = math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2)
        return lon, lat

    def to_px(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = lonlat_to_meters(lon, lat)
        return (x - self.x0) / self.res, (self.y1 - y) / self.res

    def key(self) -> str:
        return f"{self.lat:.4f}_{self.lon:.4f}_{self.zoom:.3f}_{self.width}x{self.height}"


# ---- Bundled outlines (states, counties, interstates) ----

class Shape(NamedTuple):
    name: str
    bbox: list          # lon0, lat0, lon1, lat1
    lines: list         # outer rings (or polylines), each a list of (lon, lat)
    abbr: str | None    # state / country code
    holes: list         # inner rings (lakes etc.)


def _decode(enc: list, scale: int) -> list:
    x, y, pts = 0, 0, []
    for i in range(0, len(enc), 2):
        x += enc[i]
        y += enc[i + 1]
        pts.append((x / scale, y / scale))
    return pts


@lru_cache(maxsize=None)
def shapes(name: str) -> list:
    """Load assets/geo/<name>.json.gz (built by tools/build_geodata.py) as a list of Shape."""
    with gzip.open(GEO / f"{name}.json.gz", "rt", encoding="utf-8") as f:
        data = json.load(f)
    scale = data["scale"]
    return [Shape(item["n"], [v / scale for v in item["b"]],
                  [_decode(e, scale) for e in item["l"]], item.get("a"),
                  [_decode(e, scale) for e in item.get("h", [])])
            for item in data["items"]]


def shapes_in(name: str, bbox_lonlat: tuple) -> list:
    lon0, lat0, lon1, lat1 = bbox_lonlat
    return [s for s in shapes(name)
            if not (s.bbox[2] < lon0 or s.bbox[0] > lon1 or s.bbox[3] < lat0 or s.bbox[1] > lat1)]


def point_in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def miles_to_ring(lat: float, lon: float, ring: list) -> float:
    """Approximate distance (miles) from a point to a polygon ring; 0 if inside."""
    if point_in_ring(lon, lat, ring):
        return 0.0
    kx = 69.0 * math.cos(math.radians(lat))
    ky = 69.0
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        ax, ay = (x1 - lon) * kx, (y1 - lat) * ky
        bx, by = (x2 - lon) * kx, (y2 - lat) * ky
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        t = 0.0 if seg == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg))
        px, py = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(px, py))
    return best
