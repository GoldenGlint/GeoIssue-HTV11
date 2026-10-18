"""Local place-name gazetteer for Toronto from the OSM extract: fuzzy name search and street intersections.

Builds data/places.duckdb once (named nodes and ways with a representative point, plus street node lists),
then answers in milliseconds. Used as a tool by geoloc_agent.py.

Usage:
  .venv/Scripts/python places.py --build
  .venv/Scripts/python places.py --search "Highland Hall"
  .venv/Scripts/python places.py --intersection "Bathurst Street" "Dundas Street West"
"""
import argparse
import json
import math
import time
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
PBF = HERE / "data" / "Toronto.osm.pbf"
DB = HERE / "data" / "places.duckdb"
KIND_KEYS = ["amenity", "shop", "building", "highway", "railway", "public_transport", "leisure", "tourism",
             "office", "landuse", "university", "parking", "station"]


def build():
    t0 = time.perf_counter()
    DB.unlink(missing_ok=True)
    con = duckdb.connect(str(DB))
    con.sql("INSTALL spatial; LOAD spatial;")
    src = f"ST_ReadOSM('{PBF.as_posix()}')"
    # named "category" (not "kind"): ST_ReadOSM already has a "kind" column (node/way/relation)
    category = "coalesce(" + ", ".join(f"CASE WHEN tags['{k}'] IS NOT NULL THEN '{k}=' || tags['{k}'] END"
                                       for k in KIND_KEYS) + ", '')"
    con.sql(f"""CREATE TEMP TABLE named_ways AS SELECT id, tags['name'] AS name, {category} AS category, refs,
                tags['highway'] IS NOT NULL AS is_street FROM {src} WHERE kind = 'way' AND tags['name'] IS NOT NULL""")
    con.sql("CREATE TEMP TABLE wref AS SELECT id, unnest(refs) AS ref, generate_subscripts(refs, 1) AS i FROM named_ways")
    con.sql(f"""CREATE TEMP TABLE nodes AS SELECT id, lat, lon FROM {src}
                WHERE kind = 'node' AND id IN (SELECT ref FROM wref)""")
    con.sql(f"""CREATE TABLE places AS
        SELECT tags['name'] AS name, {category} AS category, lat, lon, 'node' AS src FROM {src}
        WHERE kind = 'node' AND tags['name'] IS NOT NULL
        UNION ALL
        SELECT w.name, w.category, avg(n.lat), avg(n.lon), 'way' FROM named_ways w
        JOIN wref r ON r.id = w.id JOIN nodes n ON n.id = r.ref GROUP BY w.id, w.name, w.category""")
    con.sql("""CREATE TABLE street_nodes AS SELECT DISTINCT w.name, r.ref, n.lat, n.lon FROM named_ways w
               JOIN wref r ON r.id = w.id JOIN nodes n ON n.id = r.ref WHERE w.is_street""")
    counts = con.sql("SELECT (SELECT count(*) FROM places), (SELECT count(DISTINCT name) FROM street_nodes)").fetchone()
    con.close()
    print(f"built {DB.name}: {counts[0]} named places, {counts[1]} street names in {time.perf_counter() - t0:.1f}s")


def connect():
    if not DB.exists():
        build()
    return duckdb.connect(str(DB), read_only=True)


def search(text, limit=10, con=None):
    con = con or connect()
    q = text.lower().strip()
    rows = con.execute("""
        SELECT name, category, lat, lon,
               greatest(jaro_winkler_similarity(lower(name), ?),
                        CASE WHEN lower(name) LIKE '%' || ? || '%' THEN 0.97 ELSE 0 END) AS score
        FROM places ORDER BY score DESC LIMIT ?""", [q, q, limit * 4]).fetchall()
    out, seen = [], []
    for name, category, lat, lon, score in rows:
        # drop repeats of the same name within 150 m (one building split into several ways, etc.)
        if any(n == name and abs(la - lat) * 111320 < 150 and abs(lo - lon) * 80000 < 150 for n, la, lo in seen):
            continue
        seen.append((name, lat, lon))
        out.append({"name": name, "category": category, "lat": round(lat, 6), "lon": round(lon, 6),
                    "score": round(score, 3)})
        if len(out) >= limit:
            break
    return out


def nearby(lat, lon, radius_m=500, category=None, limit=10, con=None):
    """Named places within radius_m of a point, nearest first; category filters e.g. 'parking' or 'university'."""
    con = con or connect()
    dlat = radius_m / 111320
    dlon = radius_m / (111320 * math.cos(math.radians(lat)))
    rows = con.execute("""
        SELECT name, category, lat, lon FROM places
        WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND (? IS NULL OR lower(category) LIKE '%' || ? || '%')""",
                       [lat - dlat, lat + dlat, lon - dlon, lon + dlon, category, (category or "").lower()]).fetchall()
    out = []
    for name, cat, la, lo in rows:
        d = math.hypot((la - lat) * 111320, (lo - lon) * 111320 * math.cos(math.radians(lat)))
        if d <= radius_m:
            out.append({"name": name, "category": cat, "lat": round(la, 6), "lon": round(lo, 6), "dist_m": round(d)})
    return sorted(out, key=lambda r: r["dist_m"])[:limit]


def intersection(street_a, street_b, limit=10, con=None):
    con = con or connect()
    rows = con.execute("""
        SELECT DISTINCT a.name, b.name, a.lat, a.lon FROM street_nodes a JOIN street_nodes b ON a.ref = b.ref
        WHERE a.name <> b.name AND lower(a.name) LIKE '%' || ? || '%' AND lower(b.name) LIKE '%' || ? || '%'
        LIMIT 200""", [street_a.lower().strip(), street_b.lower().strip()]).fetchall()
    clusters = []
    for na, nb, lat, lon in rows:
        for c in clusters:
            if math.hypot((lat - c["lat"]) * 111320, (lon - c["lon"]) * 80000) < 60:
                break
        else:
            clusters.append({"streets": f"{na} & {nb}", "lat": round(lat, 6), "lon": round(lon, 6)})
    return clusters[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--search")
    ap.add_argument("--intersection", nargs=2)
    args = ap.parse_args()
    if args.build:
        build()
    if args.search:
        print(json.dumps(search(args.search), indent=1))
    if args.intersection:
        print(json.dumps(intersection(*args.intersection), indent=1))


if __name__ == "__main__":
    main()
