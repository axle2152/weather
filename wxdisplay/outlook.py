"""30-day outlook from NOAA's Climate Prediction Center (CPC).

CPC publishes its monthly outlook as KML: one polygon per probability band
("40% chance of above normal temperature"). We find the band that covers the
location, and draw the bands on a US map for the slide.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests
from PIL import Image, ImageDraw

from . import geo, regions
from .config import Config
from .location import Site
from .radar import BaseMap, MapStyle

log = logging.getLogger(__name__)

KML_URL = "https://www.cpc.ncep.noaa.gov/products/predictions/30day/lead14_{kind}.kml"
NS = {"k": "http://www.opengis.net/kml/2.2"}
NAME_RE = re.compile(r"([\d.]+)%\s*Chance of (Above|Below|Near|EC)", re.I)

# Shades by probability (33, 40, 50, 60, 70+), close to CPC's own maps.
COLORS = {
    ("temp", "Above"): [(254, 217, 166), (253, 174, 97), (244, 109, 67), (215, 48, 39), (165, 0, 38)],
    ("temp", "Below"): [(198, 219, 239), (158, 202, 225), (107, 174, 214), (49, 130, 189), (8, 81, 156)],
    ("prcp", "Above"): [(199, 233, 192), (161, 217, 155), (116, 196, 118), (49, 163, 84), (0, 109, 44)],
    ("prcp", "Below"): [(246, 232, 195), (223, 194, 125), (191, 129, 45), (140, 81, 10), (84, 48, 5)],
}
NEAR = (190, 190, 190)
WORDS = {
    ("temp", "Above"): "Warmer than normal", ("temp", "Below"): "Colder than normal",
    ("temp", "Near"): "Near normal temperatures",
    ("temp", "EC"): "Equal chances of warmer, colder or near normal",
    ("prcp", "Above"): "Wetter than normal", ("prcp", "Below"): "Drier than normal",
    ("prcp", "Near"): "Near normal precipitation",
    ("prcp", "EC"): "Equal chances of wetter, drier or near normal",
}


def band_color(kind: str, category: str, prob: float):
    if category == "Near":
        return NEAR
    shades = COLORS.get((kind, category))
    if not shades:
        return None
    i = 0 if prob < 40 else 1 if prob < 50 else 2 if prob < 60 else 3 if prob < 70 else 4
    return shades[i]


@dataclass
class OutlookPart:
    kind: str            # "temp" or "prcp"
    category: str        # Above / Below / Near / EC
    prob: int
    valid: str           # e.g. "November 2026"
    map: Image.Image     # US map with the bands drawn on it
    view: object         # geo.MapView of the map, for placing the home marker

    @property
    def words(self) -> str:
        return WORDS.get((self.kind, self.category), "")


def parse_kml(text: bytes) -> tuple:
    """-> (valid month text, [(category, prob, [(outer ring, [holes])])])."""
    root = ET.fromstring(text)
    doc_name = root.findtext(".//k:Document/k:name", default="", namespaces=NS)
    m = re.search(r"Valid\s+([A-Za-z]{3,9})\s+(\d{4})", doc_name)
    valid = ""
    if m:
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"]
        valid = next((f"{full} {m.group(2)}" for full in months if full.lower().startswith(m.group(1).lower())),
                     f"{m.group(1)} {m.group(2)}")
    bands = []
    for pm in root.iter(f"{{{NS['k']}}}Placemark"):
        nm = NAME_RE.search(pm.findtext("k:name", default="", namespaces=NS))
        if not nm:
            continue
        polys = []
        for poly in pm.iter(f"{{{NS['k']}}}Polygon"):
            outer = poly.findtext("k:outerBoundaryIs/k:LinearRing/k:coordinates", default="", namespaces=NS)
            holes = [h.text or "" for h in poly.findall("k:innerBoundaryIs/k:LinearRing/k:coordinates", NS)]
            polys.append((_coords(outer), [_coords(h) for h in holes]))
        cat = nm.group(2).capitalize() if nm.group(2).upper() != "EC" else "EC"
        bands.append((cat, round(float(nm.group(1))), polys))
    return valid, bands


def _coords(text: str) -> list:
    pts = []
    for tok in text.split():
        parts = tok.split(",")
        if len(parts) >= 2:
            pts.append((float(parts[0]), float(parts[1])))
    return pts


def band_at(bands: list, lat: float, lon: float) -> tuple:
    """(category, prob) of the strongest band covering the point; ("EC", 33) if none."""
    best = ("EC", 33)
    for cat, prob, polys in bands:
        for outer, holes in polys:
            if len(outer) >= 3 and geo.point_in_ring(lon, lat, outer) and \
                    not any(len(h) >= 3 and geo.point_in_ring(lon, lat, h) for h in holes):
                if cat != "EC" and (best[0] == "EC" or prob > best[1]):
                    best = (cat, prob)
    return best


class Outlook:
    def __init__(self, cfg: Config, site: Site, map_size: tuple, scale: float, user_agent: str):
        self.cfg, self.site, self.scale = cfg, site, scale
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.view = regions.region_view(regions.NATIONAL, *map_size)
        self.map = BaseMap(cfg, self.view, scale, MapStyle(counties=False, interstates=False), self.session)
        self.base = None
        self.lines = None

    def update(self) -> dict | None:
        if self.base is None:
            self.base = self.map.basemap()
            self.lines = self.map.outlines(borders=True)
        parts = {}
        for kind in ("temp", "prcp"):
            try:
                r = self.session.get(KML_URL.format(kind=kind), timeout=(6, 60))
                r.raise_for_status()
                valid, bands = parse_kml(r.content)
            except Exception as e:
                log.warning("30-day outlook (%s) failed: %s", kind, e)
                continue
            cat, prob = band_at(bands, self.site.lat, self.site.lon)
            parts[kind] = OutlookPart(kind, cat, prob, valid, self._draw(kind, bands), self.view)
        return parts or None

    def _draw(self, kind: str, bands: list) -> Image.Image:
        v, ss = self.view, 2
        layer = Image.new("RGBA", (v.width * ss, v.height * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for cat, prob, polys in sorted(bands, key=lambda b: b[1]):   # strongest drawn last
            color = band_color(kind, cat, prob)
            if color is None:
                continue
            for outer, holes in polys:
                if len(outer) >= 3:
                    d.polygon([(x * ss, y * ss) for x, y in (v.to_px(lo, la) for lo, la in outer)],
                              fill=(*color, 190))
                for h in holes:
                    if len(h) >= 3:
                        d.polygon([(x * ss, y * ss) for x, y in (v.to_px(lo, la) for lo, la in h)],
                                  fill=(0, 0, 0, 0))
        layer = layer.resize((v.width, v.height), Image.LANCZOS)
        img = self.base.convert("RGBA")
        img.alpha_composite(layer)
        img.alpha_composite(self.lines)
        return img.convert("RGB")
