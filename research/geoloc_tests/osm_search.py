"""Bellingcat-style feature co-occurrence search over OpenStreetMap for Toronto.

Finds every place where a streetcar track runs within N metres of a large surface
parking lot, then clusters the hits into candidate locations.

Usage: python osm_search.py [--within 40] [--min-area 1500]
"""
import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
TORONTO_BBOX = "43.58,-79.64,43.86,-79.11"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "GeoIssue-hackathon-geoloc-test/0.1 (research)"


def overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode()
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=200) as resp:
                return json.load(resp), url
        except Exception as err:  # busy server: try the next mirror
            print(f"  {url} failed: {err}")
    raise RuntimeError("all Overpass endpoints failed")


def polygon_area_m2(geom):
    # equirectangular projection is accurate enough for lot-sized polygons
    lat0 = math.radians(sum(p["lat"] for p in geom) / len(geom))
    pts = [(math.radians(p["lon"]) * 6371000 * math.cos(lat0), math.radians(p["lat"]) * 6371000) for p in geom]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def dist_m(a, b):
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1]) * math.cos(math.radians(a[0]))
    return 6371000 * math.hypot(dlat, dlon)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--within", type=int, default=40, help="max metres between track and lot")
    ap.add_argument("--min-area", type=float, default=1500, help="min lot area in m2")
    args = ap.parse_args()

    query = f"""[out:json][timeout:90];
way["railway"="tram"]({TORONTO_BBOX})->.tram;
(way["amenity"="parking"]["parking"!~"underground|multi-storey|rooftop"](around.tram:{args.within});)->.lots;
.lots out geom tags;"""
    start = time.perf_counter()
    data, used = overpass(query)
    elapsed = time.perf_counter() - start

    lots = []
    for el in data["elements"]:
        geom = el.get("geometry")
        if not geom or len(geom) < 3:
            continue
        area = polygon_area_m2(geom)
        if area < args.min_area:
            continue
        lat = sum(p["lat"] for p in geom) / len(geom)
        lon = sum(p["lon"] for p in geom) / len(geom)
        lots.append({"osm_way": el["id"], "lat": round(lat, 5), "lon": round(lon, 5), "area_m2": round(area),
                     "name": el.get("tags", {}).get("name", ""), "operator": el.get("tags", {}).get("operator", "")})

    # merge lots within 150 m of each other into one candidate area
    clusters = []
    for lot in sorted(lots, key=lambda x: -x["area_m2"]):
        for c in clusters:
            if dist_m((c["lat"], c["lon"]), (lot["lat"], lot["lon"])) < 150:
                c["lots"].append(lot)
                break
        else:
            clusters.append({"lat": lot["lat"], "lon": lot["lon"], "lots": [lot]})

    out = HERE / "results" / "osm_search_tram_parking.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"query": query, "endpoint": used, "seconds": round(elapsed, 1),
                               "lots": len(lots), "clusters": clusters}, indent=2))
    print(f"Overpass {elapsed:.1f}s via {used}: {len(data['elements'])} lots near track, "
          f"{len(lots)} >= {args.min_area:.0f} m2, {len(clusters)} candidate areas")
    for i, c in enumerate(clusters, 1):
        big = max(c["lots"], key=lambda x: x["area_m2"])
        print(f"{i:2d}. {c['lat']:.5f}, {c['lon']:.5f}  lots={len(c['lots'])}  biggest={big['area_m2']} m2  "
              f"{big['name'] or big['operator']}")


if __name__ == "__main__":
    main()
