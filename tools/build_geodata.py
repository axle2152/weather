"""Build the bundled geographic data in assets/geo/ from US Census Bureau files.

You only need to run this if you want to refresh the data; the output is
already committed. All source data is public domain (US Government work).

    pip install pyshp requests
    python tools/build_geodata.py

Outputs (all gzip-compressed):
    zcta.csv.gz        ZIP code (ZCTA) -> lat, lon
    places.csv.gz      state, place name -> lat, lon, population (cities, towns, CDPs)
    states.json.gz     state outlines
    counties.json.gz   county outlines
    interstates.json.gz  Interstate highway lines
    neighbors.json.gz  Canada, Mexico, Cuba, Bahamas land (Natural Earth, public domain)
"""

import csv
import gzip
import io
import json
import os
import re
import sys
import zipfile

import requests
import shapefile  # pyshp

BASE = "https://www2.census.gov/geo"
SOURCES = {
    "zcta": f"{BASE}/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip",
    "places": f"{BASE}/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip",
    "popest": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/cities/totals/sub-est2024.csv",
    "states": f"{BASE}/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip",
    "counties": f"{BASE}/tiger/GENZ2024/shp/cb_2024_us_county_5m.zip",
    "interstates": f"{BASE}/tiger/TIGER2024/PRIMARYROADS/tl_2024_us_primaryroads.zip",
    # Natural Earth (public domain) for land in neighboring countries, so the radar
    # map can tell land from water near the Canadian and Mexican borders.
    "neighbors": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
                 "ne_10m_admin_0_countries_lakes.geojson",
}
NEIGHBORS = {"CAN", "MEX", "CUB", "BHS"}
HEADERS = {"User-Agent": "(wxdisplay geodata builder, https://github.com/axle2152/weather)"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "geo")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".download-cache")

SCALE = 10000  # coordinates stored as integers of 1/10000 degree (~11 m)
TOLERANCE = 0.0015  # Douglas-Peucker simplification tolerance in degrees


def download(key):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, os.path.basename(SOURCES[key]))
    if not os.path.exists(path):
        print(f"downloading {SOURCES[key]}")
        r = requests.get(SOURCES[key], headers=HEADERS, timeout=300)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return zipfile.ZipFile(path) if path.endswith(".zip") else path


def ring_area(ring):
    """Signed area (shoelace); positive = counter-clockwise."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])) / 2


def populations():
    """Census population estimates for incorporated places, keyed by GEOID (state + place FIPS)."""
    pops = {}
    with open(download("popest"), encoding="latin-1", newline="") as f:
        for r in csv.DictReader(f):
            if r["PLACE"] != "00000" and r["COUNTY"] == "000":
                geoid = r["STATE"] + r["PLACE"]
                pops[geoid] = max(pops.get(geoid, 0), int(r["POPESTIMATE2024"] or 0))
    return pops


def read_gazetteer(zf):
    name = [n for n in zf.namelist() if n.endswith(".txt")][0]
    text = zf.read(name).decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    header = [h.strip() for h in next(reader)]
    for row in reader:
        yield dict(zip(header, (c.strip() for c in row)))


# Census place names carry a legal suffix ("Atlanta city", "Macon-Bibb County
# consolidated government (balance)"). Strip it so people can type "Atlanta, GA".
CONSOLIDATED = ["unified government", "consolidated government", "metropolitan government",
                "metro government", "urban county", "city and borough"]
SUFFIXES = sorted(CONSOLIDATED + ["city", "town", "village", "CDP", "borough", "municipality",
                                  "comunidad", "zona urbana", "corporation", "plantation"],
                  key=len, reverse=True)


def clean_place(name):
    name = re.sub(r"\s*\(balance\)\s*$", "", name)
    consolidated = False
    for suf in SUFFIXES:
        if name.endswith(" " + suf):
            name = name[: -len(suf) - 1]
            consolidated = suf in CONSOLIDATED
            break
    names = [name]
    if (consolidated or name.endswith(" County")) and re.search(r"[-/]", name):
        names.append(re.split(r"[-/]", name)[0].strip())  # "Athens-Clarke County" -> "Athens"
    if name.startswith("Urban "):
        names.append(name[len("Urban "):])  # "Urban Honolulu" -> "Honolulu"
    return names


def build_zcta():
    rows = []
    for r in read_gazetteer(download("zcta")):
        rows.append((r["GEOID"], round(float(r["INTPTLAT"]), 4), round(float(r["INTPTLONG"]), 4)))
    write_csv("zcta.csv.gz", ["zip", "lat", "lon"], rows)


def build_places():
    pops = populations()
    rows = []
    for r in read_gazetteer(download("places")):
        lat, lon = round(float(r["INTPTLAT"]), 4), round(float(r["INTPTLONG"]), 4)
        pop = pops.get(r["GEOID"], 0)  # unincorporated places (CDPs) have no estimate
        for n in clean_place(r["NAME"]):
            rows.append((r["USPS"], n, lat, lon, pop))
    write_csv("places.csv.gz", ["state", "name", "lat", "lon", "pop"], rows)


def write_csv(fname, header, rows):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, fname)
    with gzip.open(path, "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows, {os.path.getsize(path) // 1024} KB)")


def simplify(points, tol):
    """Iterative Douglas-Peucker line simplification."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    tol2 = tol * tol
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            if seg == 0:
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg))
                d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > best:
                best, idx = d, i
        if best > tol2:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(points, keep) if k]


def encode(points):
    """Delta-encode a line as a flat integer list: x0, y0, dx1, dy1, ..."""
    out, px, py = [], 0, 0
    for i, (x, y) in enumerate(points):
        ix, iy = round(x * SCALE), round(y * SCALE)
        if i == 0:
            out += [ix, iy]
        else:
            out += [ix - px, iy - py]
        px, py = ix, iy
    return out


def shape_parts(shp):
    pts, parts = shp.points, list(shp.parts) + [len(shp.points)]
    return [pts[parts[i]:parts[i + 1]] for i in range(len(parts) - 1)]


def make_item(name, outer, holes, extra):
    """outer/holes: lists of point lists. Returns an encoded item, or None if empty."""
    lines = [encode(p) for p in (simplify(r, TOLERANCE) for r in outer) if len(p) >= 2]
    hole_lines = [encode(p) for p in (simplify(r, TOLERANCE) for r in holes) if len(p) >= 4]
    if not lines:
        return None
    xs = [x for r in outer for x, _ in r]
    ys = [y for r in outer for _, y in r]
    item = {"n": name, "b": [round(min(xs) * SCALE), round(min(ys) * SCALE),
                             round(max(xs) * SCALE), round(max(ys) * SCALE)], "l": lines}
    if hole_lines:
        item["h"] = hole_lines
    item.update(extra)
    return item


def build_shapes(key, fname, name_field, keep=lambda rec: True, extra=lambda rec: {}, polygons=True):
    zf = download(key)
    base = [n[:-4] for n in zf.namelist() if n.endswith(".shp")][0]
    reader = shapefile.Reader(shp=io.BytesIO(zf.read(base + ".shp")),
                              dbf=io.BytesIO(zf.read(base + ".dbf")),
                              shx=io.BytesIO(zf.read(base + ".shx")))
    items = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        if not keep(rec):
            continue
        parts = [[tuple(p) for p in part] for part in shape_parts(sr.shape)]
        # Shapefile polygons: outer rings run clockwise, holes counter-clockwise.
        outer = [p for p in parts if not polygons or ring_area(p) <= 0]
        holes = [p for p in parts if polygons and ring_area(p) > 0]
        item = make_item(rec[name_field], outer, holes, extra(rec))
        if item:
            items.append(item)
    write_items(fname, items)


def build_neighbors():
    with open(download("neighbors"), encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for feat in data["features"]:
        props = feat["properties"]
        if props.get("ADM0_A3") not in NEIGHBORS:
            continue
        geom = feat["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            outer = [[tuple(p) for p in poly[0]]]
            holes = [[tuple(p) for p in ring] for ring in poly[1:]]
            if max(x for x, _ in outer[0]) < -50:  # North America only
                item = make_item(props["NAME"], outer, holes, {"a": props["ADM0_A3"]})
                if item:
                    items.append(item)
    write_items("neighbors.json.gz", items)


def write_items(fname, items):
    path = os.path.join(OUT, fname)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"scale": SCALE, "items": items}, f, separators=(",", ":"))
    print(f"wrote {path} ({len(items)} items, {os.path.getsize(path) // 1024} KB)")


def main():
    steps = sys.argv[1:] or ["zcta", "places", "states", "counties", "interstates", "neighbors"]
    if "zcta" in steps:
        build_zcta()
    if "places" in steps:
        build_places()
    if "states" in steps:
        build_shapes("states", "states.json.gz", "NAME", extra=lambda r: {"a": r["STUSPS"]})
    if "counties" in steps:
        build_shapes("counties", "counties.json.gz", "NAME", extra=lambda r: {"a": r["STUSPS"]})
    if "interstates" in steps:
        build_shapes("interstates", "interstates.json.gz", "FULLNAME",
                     keep=lambda r: r["RTTYP"] == "I", polygons=False)
    if "neighbors" in steps:
        build_neighbors()


if __name__ == "__main__":
    main()
