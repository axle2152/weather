"""Named US regions for the regional radar and satellite slides."""

from __future__ import annotations

import math

from . import geo

# name -> (west lon, south lat, east lon, north lat). Roughly the regions a weather
# channel uses; neighbours overlap a little so storms near the edges stay in view.
REGIONS = {
    "Northeast": (-80.5, 39.0, -66.8, 47.6),
    "Mid-Atlantic": (-84.5, 35.0, -72.5, 42.3),
    "Southeast": (-91.0, 24.5, -75.0, 36.8),
    "Ohio Valley": (-92.0, 35.0, -79.5, 42.0),
    "Great Lakes": (-93.5, 40.0, -75.5, 48.6),
    "Upper Midwest": (-104.5, 40.5, -85.5, 49.5),
    "Central Plains": (-104.5, 35.3, -89.0, 43.6),
    "Central Rockies": (-114.5, 36.0, -100.5, 42.5),
    "South Central": (-107.0, 25.6, -88.5, 37.3),
    "Northern Rockies": (-117.5, 40.8, -102.0, 49.5),
    "Southwest": (-118.5, 31.0, -102.5, 38.6),
    "California": (-125.0, 32.3, -113.6, 42.2),
    "Pacific Northwest": (-125.5, 41.5, -110.5, 49.5),
    "United States": (-125.5, 24.0, -66.5, 49.8),
}
NATIONAL = "United States"


def home_region(lat: float, lon: float) -> str | None:
    """The smallest region containing the location (None outside the lower 48)."""
    inside = [(name, b) for name, b in REGIONS.items()
              if name != NATIONAL and b[0] <= lon <= b[2] and b[1] <= lat <= b[3]]
    if not inside:
        return None

    def area(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    # Prefer the region whose center is closest, among the smaller ones that contain the point.
    def score(item):
        name, b = item
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return math.hypot((lon - cx) * math.cos(math.radians(lat)), lat - cy) + area(b) / 400
    return min(inside, key=score)[0]


def default_regions(lat: float, lon: float) -> list:
    """Every region, starting with the home region and then going outward from it."""
    home = home_region(lat, lon)

    def distance(name):
        b = REGIONS[name]
        return geo.miles_between(lat, lon, (b[1] + b[3]) / 2, (b[0] + b[2]) / 2)
    others = sorted((n for n in REGIONS if n not in (home, NATIONAL)), key=distance)
    return ([home] if home else []) + [NATIONAL] + others


def region_view(name: str, width: int, height: int) -> geo.MapView:
    """A map view that fits the whole region into width x height pixels."""
    w_lon, s_lat, e_lon, n_lat = REGIONS[name]
    x0, y0 = geo.lonlat_to_meters(w_lon, s_lat)
    x1, y1 = geo.lonlat_to_meters(e_lon, n_lat)
    world = 2 * math.pi * geo.EARTH_RADIUS
    zoom = min(math.log2(width * world / (256 * (x1 - x0))), math.log2(height * world / (256 * (y1 - y0))))
    clon, clat = geo.MapView.meters_to_lonlat((x0 + x1) / 2, (y0 + y1) / 2)
    return geo.MapView(clat, clon, zoom, width, height)
