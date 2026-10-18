"""Download City of Toronto street-asset layers and load them into one DuckDB table for asset search / matching.

Layers (City of Toronto Open Data, CKAN API, EPSG:4326 CSV): topographic-mapping poles (typed, +-30 cm),
transit shelters, fire hydrants, bicycle parking, traffic signals (+ pedestrian crossovers, beacons),
litter receptacles, benches, and TTC stops from the TTC GTFS feed (subtype = modes serving the stop).

Writes data/toronto_assets.duckdb with
  assets(asset_id, type, subtype, lat, lon, x, y, source, attrs JSON)   -- x, y = UTM 17N metres (EPSG:32617)
  osm_lines(osm_id, kind, value, sub, xs, ys)  -- OSM highway centrelines + railway=tram from data/Toronto.osm.pbf
and results/assets_sources.json (dataset URLs, licence, refresh dates, row counts).
Raw downloads are cached in data/assets_raw/ (about 150 MB); pass --refresh to re-download.

Usage:
  .venv/Scripts/python assets_load.py
  .venv/Scripts/python assets_load.py --refresh --skip-osm
"""
import argparse
import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
DATA = HERE / "data"
RAW = DATA / "assets_raw"
DB = DATA / "toronto_assets.duckdb"
PBF = DATA / "Toronto.osm.pbf"
SOURCES = HERE / "results" / "assets_sources.json"
CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/"
UA = {"User-Agent": "htv-geoloc-research/0.1 (assets_load.py)"}
BBOX = (43.58, -79.64, 43.86, -79.11)  # min lat, min lon, max lat, max lon
LICENCE = {"name": "Open Government Licence - Toronto", "url": "https://open.toronto.ca/open-data-license/"}

# type, CKAN package, resource file name, package_search query for when the package id has moved,
# id column (+ prefix), subtype column or constant
LAYERS = [
    dict(type="pole", package="topographic-mapping-poles", resource="poles-4326.csv", query="poles",
         id_col="OBJECTID", id_prefix="POLE-", subtype_col="SUBTYPE_DESC"),
    dict(type="shelter", package="street-furniture-transit-shelter", resource="transit-shelter-data-4326.csv",
         query="transit shelter", id_col="ID", subtype_col="STYLE"),
    dict(type="hydrant", package="fire-hydrants", resource="fire-hydrants-data-4326.csv", query="fire hydrants",
         id_col="FACILITYID", subtype_const="hydrant"),
    dict(type="bike_ring", package="street-furniture-bicycle-parking", resource="street-bicycle-parking-data-4326.csv",
         query="bicycle parking", id_col="ID", subtype_col="ASSETTYPE"),
    dict(type="signal", package="traffic-signals-tabular", resource="traffic-signal-4326.csv", query="traffic signals",
         id_col="PX", id_prefix="PX", subtype_const="traffic_signal"),
    dict(type="signal", package="traffic-signals-tabular", resource="pedestrian-crossover-4326.csv",
         query="traffic signals", id_col="PX", id_prefix="PXO", subtype_const="pedestrian_crossover"),
    dict(type="signal", package="traffic-signals-tabular", resource="traffic-beacon-4326.csv",
         query="traffic signals", id_col="PX", id_prefix="BEACON", subtype_const="traffic_beacon"),
    dict(type="bin", package="street-furniture-litter-receptacle",
         resource="street-furniture-litter-receptacle-data-4326.csv", query="litter receptacle",
         id_col="ID", subtype_col="ASSETTYPE"),
    dict(type="bench", package="street-furniture-bench", resource="street-furniture-bench-data-4326.csv",
         query="street furniture bench", id_col="ID", subtype_col="ASSETTYPE"),
]
TTC = dict(type="ttc_stop", package="ttc-routes-and-schedules", resource="opendata_ttc_schedules.zip",
           query="TTC routes and schedules")
GTFS_MODE = {"0": "streetcar", "1": "subway", "2": "rail", "3": "bus", "4": "ferry"}
# OSM highway values that cannot be a street-level camera position
HIGHWAY_EXCLUDE = ("proposed", "construction", "abandoned", "disused", "platform", "elevator", "corridor", "razed",
                   "bus_stop", "street_lamp", "traffic_signals", "crossing", "stop", "give_way", "rest_area")


def retry(fn, tries=5):
    """CKAN often answers 502/503 under load; retry with backoff."""
    for i in range(tries):
        try:
            return fn()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} after {e}")
            time.sleep(3 * 2 ** i)


def ckan(action, **params):
    url = CKAN + action + "?" + urllib.parse.urlencode(params)

    def go():
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return json.load(r)
    return retry(go)


def resolve(layer):
    """Find the current download URL for a layer via package_show, falling back to package_search."""
    pkgs = []
    try:
        res = ckan("package_show", id=layer["package"])
        if res.get("success"):
            pkgs = [res["result"]]
    except Exception as e:  # noqa: BLE001 - any network/HTTP failure -> try search
        print(f"  package_show {layer['package']} failed ({e}); trying package_search")
    if not pkgs:
        pkgs = ckan("package_search", q=layer["query"], rows=20)["result"]["results"]
    for pkg in pkgs:
        for r in pkg["resources"]:
            if r.get("url", "").lower().endswith(layer["resource"].lower()):
                return pkg, r
    raise RuntimeError(f"no resource '{layer['resource']}' in CKAN results for {layer['package']!r}")


def download(url, dest, refresh):
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    def go():
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, \
                open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    retry(go)
    tmp.replace(dest)
    return True


def slug(text):
    """'Street Light + Signal' -> 'street_light+signal', 'Street Light Pole' -> 'street_light'."""
    s = re.sub(r"\s*\+\s*", "+", str(text).strip().lower())
    s = re.sub(r"\s+pole$", "", s)
    return re.sub(r"[^a-z0-9+]+", "_", s).strip("_") or "unknown"


def load_csv_layer(con, layer, path):
    con.execute(f"CREATE OR REPLACE TEMP TABLE raw AS SELECT * FROM read_csv('{path.as_posix()}', "
                "all_varchar = true, header = true)")
    cols = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
    attr_cols = [c for c in cols if c not in ("_id", "geometry")]
    attrs = "json_object(" + ", ".join(f"'{c}', nullif(\"{c}\", 'None')" for c in attr_cols) + ")"
    id_expr = f"'{layer.get('id_prefix', '')}' || trim(\"{layer['id_col']}\")"
    subtype = f"'{layer['subtype_const']}'" if "subtype_const" in layer else \
        f"coalesce(nullif(trim(\"{layer['subtype_col']}\"), 'None'), 'unknown')"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE parsed AS
        SELECT {id_expr} AS asset_id, {subtype} AS subtype_raw, {attrs} AS attrs,
               CASE json_extract_string(geometry, '$.type') WHEN 'Point'
                    THEN json_extract(geometry, '$.coordinates') ELSE json_extract(geometry, '$.coordinates[0]')
               END AS c
        FROM raw""")
    con.execute("CREATE OR REPLACE TEMP TABLE parsed2 AS SELECT asset_id, subtype_raw, attrs, "
                "TRY_CAST(json_extract_string(c, '$[1]') AS DOUBLE) AS lat, "
                "TRY_CAST(json_extract_string(c, '$[0]') AS DOUBLE) AS lon FROM parsed")
    subtypes = con.execute("SELECT DISTINCT subtype_raw FROM parsed2").fetchall()
    con.execute("CREATE OR REPLACE TEMP TABLE submap (raw VARCHAR, s VARCHAR)")
    con.executemany("INSERT INTO submap VALUES (?, ?)", [(s, slug(s)) for (s,) in subtypes])
    n_raw = con.execute("SELECT count(*) FROM parsed2").fetchone()[0]
    con.execute(f"""
        INSERT INTO assets
        SELECT p.asset_id, '{layer['type']}', m.s, p.lat, p.lon,
               ST_X(g), ST_Y(g), '{layer['package']}/{layer['resource']}', p.attrs
        FROM (SELECT *, ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:32617', always_xy := true) AS g
              FROM parsed2 WHERE lat IS NOT NULL AND lon IS NOT NULL AND NOT (lat = 0 AND lon = 0)) p
        JOIN submap m ON m.raw = p.subtype_raw""")
    return n_raw


def load_ttc(con, path):
    """TTC GTFS stops.txt -> ttc_stop rows; subtype = modes serving the stop (via trips/routes/stop_times)."""
    with zipfile.ZipFile(path) as z:
        names = {Path(n).name: n for n in z.namelist()}

        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(names[name]), encoding="utf-8-sig"))

        route = {r["route_id"]: (GTFS_MODE.get(r["route_type"], r["route_type"]), r["route_short_name"])
                 for r in rows("routes.txt")}
        trip_route = {r["trip_id"]: r["route_id"] for r in rows("trips.txt")}
        stop_routes = defaultdict(set)
        with z.open(names["stop_times.txt"]) as f:
            rdr = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            hdr = next(rdr)
            i_trip, i_stop = hdr.index("trip_id"), hdr.index("stop_id")
            last = None
            for rec in rdr:
                key = (rec[i_trip], rec[i_stop])
                if key != last:
                    stop_routes[rec[i_stop]].add(trip_route.get(rec[i_trip]))
                    last = key
        stops = list(rows("stops.txt"))
    out = []
    for s in stops:
        rids = {r for r in stop_routes.get(s["stop_id"], ()) if r in route}
        modes = sorted({route[r][0] for r in rids})
        subtype = "+".join(modes) if modes else ("station" if s.get("location_type") == "1" else "unserved")
        attrs = {k: v for k, v in s.items() if v not in ("", None)}
        attrs["routes"] = sorted({route[r][1] for r in rids}, key=lambda x: (len(x), x))
        out.append((f"TTC{s['stop_id']}", subtype, float(s["stop_lat"]), float(s["stop_lon"]), json.dumps(attrs)))
    con.execute("CREATE OR REPLACE TEMP TABLE ttc (asset_id VARCHAR, subtype VARCHAR, lat DOUBLE, lon DOUBLE, "
                "attrs VARCHAR)")
    con.executemany("INSERT INTO ttc VALUES (?, ?, ?, ?, ?)", out)
    con.execute(f"""
        INSERT INTO assets
        SELECT asset_id, 'ttc_stop', subtype, lat, lon, ST_X(g), ST_Y(g),
               '{TTC['package']}/{TTC['resource']}:stops.txt', attrs::JSON
        FROM (SELECT *, ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:32617', always_xy := true) AS g
              FROM ttc WHERE NOT (lat = 0 AND lon = 0))""")
    return len(out)


def load_osm_lines(con):
    """OSM highway centrelines and railway=tram as UTM vertex lists (for camera plausibility and tram 'assets')."""
    excl = ", ".join(f"'{v}'" for v in HIGHWAY_EXCLUDE)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ways AS
        SELECT id, refs,
               CASE WHEN tags['railway'] = 'tram' THEN 'tram' ELSE 'highway' END AS kind,
               CASE WHEN tags['railway'] = 'tram' THEN 'tram' ELSE tags['highway'] END AS value,
               coalesce(tags['footway'], tags['sidewalk'], '') AS sub
        FROM ST_ReadOSM('{PBF.as_posix()}')
        WHERE kind = 'way' AND (tags['railway'] = 'tram'
              OR (tags['highway'] IS NOT NULL AND tags['highway'] NOT IN ({excl})
                  AND coalesce(tags['area'], 'no') <> 'yes'))""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE way_nodes AS
        SELECT w.id, u.idx, u.ref FROM ways w,
        LATERAL (SELECT unnest(w.refs) AS ref, generate_subscripts(w.refs, 1) AS idx) u""")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE nodes AS
        SELECT id, ST_Transform(ST_Point(lon, lat), 'EPSG:4326', 'EPSG:32617', always_xy := true) AS g
        FROM ST_ReadOSM('{PBF.as_posix()}')
        WHERE kind = 'node' AND id IN (SELECT ref FROM way_nodes)""")
    con.execute("DROP TABLE IF EXISTS osm_lines")
    con.execute("""
        CREATE TABLE osm_lines AS
        SELECT w.id AS osm_id, w.kind, w.value, w.sub, l.xs, l.ys
        FROM ways w JOIN (
            SELECT wn.id, list(ST_X(n.g) ORDER BY wn.idx) AS xs, list(ST_Y(n.g) ORDER BY wn.idx) AS ys
            FROM way_nodes wn JOIN nodes n ON n.id = wn.ref GROUP BY wn.id HAVING count(*) >= 2) l
        ON l.id = w.id""")
    return con.execute("SELECT kind, count(*) FROM osm_lines GROUP BY kind ORDER BY kind").fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download raw files even if cached")
    ap.add_argument("--skip-osm", action="store_true", help="do not rebuild the osm_lines table")
    args = ap.parse_args()
    t0 = time.perf_counter()

    con = duckdb.connect(str(DB))
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("DROP TABLE IF EXISTS assets")
    con.execute("CREATE TABLE assets (asset_id VARCHAR, type VARCHAR, subtype VARCHAR, lat DOUBLE, lon DOUBLE, "
                "x DOUBLE, y DOUBLE, source VARCHAR, attrs JSON)")

    sources, failed = [], []
    for layer in LAYERS + [TTC]:
        label = f"{layer['type']}:{layer['resource']}"
        try:
            pkg, res = resolve(layer)
            dest = RAW / Path(urllib.parse.urlparse(res["url"]).path).name
            fresh = download(res["url"], dest, args.refresh)
            n_raw = load_ttc(con, dest) if layer is TTC else load_csv_layer(con, layer, dest)
            print(f"{label:<60} {'downloaded' if fresh else 'cached':>10} {dest.stat().st_size / 1e6:6.1f} MB "
                  f"{n_raw:>8} rows")
            sources.append({
                "type": layer["type"], "package": pkg["name"], "title": pkg.get("title"),
                "dataset_page": f"https://open.toronto.ca/dataset/{pkg['name']}/",
                "package_show": f"{CKAN}package_show?id={pkg['name']}",
                "resource_name": res.get("name"), "resource_url": res["url"],
                "ckan_license_field": pkg.get("license_title") or pkg.get("license_id"),
                "last_refreshed": pkg.get("last_refreshed"), "refresh_rate": pkg.get("refresh_rate"),
                "rows_in_file": n_raw})
        except Exception as e:  # noqa: BLE001 - report and continue with the other layers
            print(f"{label:<60} FAILED: {e}")
            failed.append({"layer": label, "error": str(e)})

    osm = None
    if not args.skip_osm:
        t_osm = time.perf_counter()
        osm = load_osm_lines(con)
        print(f"osm_lines from {PBF.name}: {dict(osm)} ({time.perf_counter() - t_osm:.0f}s)")

    con.execute("CREATE INDEX IF NOT EXISTS assets_type ON assets(type)")
    lat0, lon0, lat1, lon1 = BBOX
    print("\ntype       subtype                         count   outside_bbox  at_0_0")
    stats = con.execute(f"""
        SELECT type, subtype, count(*),
               count(*) FILTER (WHERE NOT (lat BETWEEN {lat0} AND {lat1} AND lon BETWEEN {lon0} AND {lon1})),
               count(*) FILTER (WHERE abs(lat) < 1e-6 AND abs(lon) < 1e-6)
        FROM assets GROUP BY ALL ORDER BY type, count(*) DESC""").fetchall()
    for t, s, n, out, zero in stats:
        print(f"{t:<10} {s[:30]:<30} {n:>8} {out:>14} {zero:>7}")
    per_type = con.execute(f"""
        SELECT type, count(*), count(DISTINCT asset_id),
               count(*) FILTER (WHERE NOT (lat BETWEEN {lat0} AND {lat1} AND lon BETWEEN {lon0} AND {lon1})),
               min(lat), max(lat), min(lon), max(lon)
        FROM assets GROUP BY type ORDER BY count(*) DESC""").fetchall()
    print("\ntype          count  distinct_ids  outside_bbox   lat range           lon range")
    for t, n, nid, out, a, b, c, d in per_type:
        print(f"{t:<10} {n:>8} {nid:>12} {out:>12}   {a:.4f}..{b:.4f}   {c:.4f}..{d:.4f}")
    sample = con.execute("SELECT type, asset_id, subtype, round(lat, 6), round(lon, 6), round(x, 1), round(y, 1) "
                         "FROM assets USING SAMPLE 8 ROWS").fetchall()
    print("\nrandom spot-check rows:")
    for r in sample:
        print("  ", r)
    con.close()

    SOURCES.parent.mkdir(exist_ok=True)
    SOURCES.write_text(json.dumps({
        "generated_by": "assets_load.py", "database": DB.relative_to(HERE).as_posix(),
        "licence": LICENCE,
        "licence_note": "City of Toronto Open Data is published under the Open Government Licence - Toronto; "
                        "ckan_license_field is the per-package CKAN metadata value, which is blank for some packages.",
        "osm": {"file": PBF.relative_to(HERE).as_posix(), "licence": "ODbL 1.0 (c) OpenStreetMap contributors",
                "osm_lines": dict(osm) if osm else "not rebuilt"},
        "layers": sources, "failed": failed,
        "counts": {t: n for t, n, *_ in per_type},
        "bbox_check": {t: {"outside_bbox": out} for t, n, nid, out, *_ in per_type},
    }, indent=2))
    print(f"\nwrote {DB} and {SOURCES} in {time.perf_counter() - t0:.0f}s; failed layers: {len(failed)}")


if __name__ == "__main__":
    main()
