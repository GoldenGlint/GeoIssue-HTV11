"""Bellingcat-style OSM feature co-occurrence search over a local Toronto extract (DuckDB spatial).

Finds every B feature within N metres of an A feature, e.g. surface parking lots next to streetcar track,
then merges nearby hits into candidate areas. Runs in seconds with no public Overpass server.

Usage:
  .venv/Scripts/python osm_local_search.py --a railway=tram --b amenity=parking --within 40 --b-min-area 1500
"""
import argparse
import json
import math
import time
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
PBF = HERE / "data" / "Toronto.osm.pbf"
SURFACE_ONLY = "coalesce(tags['parking'], '') NOT IN ('underground', 'multi-storey', 'rooftop')"


def tag_filter(spec):
    if "=" not in spec:  # bare key, e.g. "building": any value
        return f"tags['{spec}'] IS NOT NULL"
    key, value = spec.split("=", 1)
    return f"tags['{key}'] = '{value}'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="railway=tram", help="anchor feature tag, key=value")
    ap.add_argument("--b", default="amenity=parking", help="feature that must be near the anchor")
    ap.add_argument("--within", type=float, default=40, help="max metres between A and B")
    ap.add_argument("--b-min-area", type=float, default=0, help="min area of B polygons in m2 (0 = any)")
    args = ap.parse_args()

    con = duckdb.connect()
    con.sql("INSTALL spatial; LOAD spatial;")
    t0 = time.perf_counter()

    b_extra = f" AND {SURFACE_ONLY}" if args.b == "amenity=parking" else ""
    con.sql(f"""
        CREATE TEMP TABLE ways AS
        SELECT id, refs, tags, 'a' AS role FROM ST_ReadOSM('{PBF.as_posix()}')
        WHERE kind = 'way' AND {tag_filter(args.a)}
        UNION ALL
        SELECT id, refs, tags, 'b' AS role FROM ST_ReadOSM('{PBF.as_posix()}')
        WHERE kind = 'way' AND {tag_filter(args.b)}{b_extra}""")
    con.sql("""
        CREATE TEMP TABLE way_nodes AS
        SELECT w.id, w.role, u.idx, u.ref FROM ways w,
        LATERAL (SELECT unnest(w.refs) AS ref, generate_subscripts(w.refs, 1) AS idx) u""")
    con.sql(f"""
        CREATE TEMP TABLE nodes AS
        SELECT id, lat, lon FROM ST_ReadOSM('{PBF.as_posix()}')
        WHERE kind = 'node' AND id IN (SELECT ref FROM way_nodes)""")
    con.sql("""
        CREATE TEMP TABLE geoms AS
        SELECT wn.id, wn.role,
               ST_Transform(ST_MakeLine(list(ST_Point(n.lon, n.lat) ORDER BY wn.idx)),
                            'EPSG:4326', 'EPSG:32617', always_xy := true) AS line
        FROM way_nodes wn JOIN nodes n ON n.id = wn.ref
        GROUP BY wn.id, wn.role HAVING count(*) >= 2""")
    t_build = time.perf_counter() - t0

    rows = con.sql(f"""
        WITH a AS (SELECT ST_Union_Agg(line) AS g FROM geoms WHERE role = 'a'),
        b AS (
            SELECT g.id, w.tags,
                   CASE WHEN ST_IsClosed(g.line) AND ST_NPoints(g.line) >= 4
                        THEN ST_MakePolygon(g.line) ELSE g.line END AS geom
            FROM geoms g JOIN ways w ON w.id = g.id AND w.role = 'b' WHERE g.role = 'b')
        SELECT b.id, ST_Area(b.geom) AS area_m2, ST_Distance(b.geom, a.g) AS dist_m,
               ST_Y(ST_Transform(ST_Centroid(b.geom), 'EPSG:32617', 'EPSG:4326', always_xy := true)) AS lat,
               ST_X(ST_Transform(ST_Centroid(b.geom), 'EPSG:32617', 'EPSG:4326', always_xy := true)) AS lon,
               coalesce(b.tags['name'], b.tags['operator'], '') AS label
        FROM b, a
        WHERE ST_DWithin(b.geom, a.g, {args.within}) AND ST_Area(b.geom) >= {args.b_min_area}
        ORDER BY area_m2 DESC""").fetchall()
    t_total = time.perf_counter() - t0

    # merge hits within 150 m into one candidate area
    clusters = []
    for way_id, area, dist, lat, lon, label in rows:
        hit = {"osm_way": way_id, "area_m2": round(area), "dist_m": round(dist, 1),
               "lat": round(lat, 5), "lon": round(lon, 5), "label": label}
        for c in clusters:
            dy = (lat - c["lat"]) * 111320
            dx = (lon - c["lon"]) * 111320 * math.cos(math.radians(lat))
            if math.hypot(dx, dy) < 150:
                c["hits"].append(hit)
                break
        else:
            clusters.append({"lat": hit["lat"], "lon": hit["lon"], "hits": [hit]})

    n_a = con.sql("SELECT count(*) FROM geoms WHERE role = 'a'").fetchone()[0]
    n_b = con.sql("SELECT count(*) FROM geoms WHERE role = 'b'").fetchone()[0]
    out = HERE / "results" / f"osm_local_{args.a.replace('=', '-')}__{args.b.replace('=', '-')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"args": vars(args), "a_ways": n_a, "b_ways": n_b, "build_s": round(t_build, 1),
                               "total_s": round(t_total, 1), "clusters": clusters}, indent=2))
    print(f"{n_a} '{args.a}' ways, {n_b} '{args.b}' ways; build {t_build:.1f}s, total {t_total:.1f}s")
    print(f"{len(rows)} '{args.b}' within {args.within:.0f} m of '{args.a}' -> {len(clusters)} candidate areas")
    for i, c in enumerate(clusters, 1):
        big = max(c["hits"], key=lambda h: h["area_m2"])
        print(f"{i:2d}. {c['lat']:.5f}, {c['lon']:.5f}  biggest {big['area_m2']:>6} m2 at {big['dist_m']:>5} m  "
              f"{big['label']}")


if __name__ == "__main__":
    main()
