"""Build the Toronto anchor tables used to turn location clues into geometry.

Outputs (spikes/data/anchors/*.parquet):
  streets.parquet        one row per street name: normalized name, base name, WKB multiline
  intersections.parquet  one row per intersection: point + list of normalized street names
  stops.parquet          TTC stops: name, normalized name, point, is_station
  routes.parquet         TTC routes: short name (e.g. "504"), long name, WKB multiline of shapes
  shelters.parquet       transit shelters: id, streets, point
  places.parquet         Overture places (name, category, point) inside the Toronto bbox

    .venv/Scripts/python -m spikes.geoloc.anchors           # City data
    .venv/Scripts/python -m spikes.geoloc.anchors overture  # Overture places (needs internet)
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile

import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import linemerge

from spikes.common.config import DATA, TORONTO_BBOX, ensure_dirs

OPEN = DATA / "opendata"
OUT = DATA / "anchors"

ABBREV = {
    "st": "street", "ave": "avenue", "av": "avenue", "rd": "road", "blvd": "boulevard",
    "dr": "drive", "cres": "crescent", "crt": "court", "ct": "court", "pl": "place", "pkwy": "parkway",
    "hwy": "highway", "ln": "lane", "sq": "square", "trl": "trail", "terr": "terrace", "gdns": "gardens",
    "e": "east", "w": "west", "n": "north", "s": "south", "mt": "mount", "stn": "station",
}
TYPES = {"street", "avenue", "road", "boulevard", "drive", "crescent", "court", "place", "parkway",
         "highway", "lane", "square", "trail", "terrace", "gardens", "way", "circle", "gate", "grove"}
DIRS = {"east", "west", "north", "south"}


def normalize(name: str) -> str:
    tokens = re.sub(r"[^a-z0-9' ]+", " ", (name or "").lower().replace("'", "")).split()
    return " ".join(ABBREV.get(t, t) for t in tokens)


def base_name(norm: str) -> str:
    tokens = [t for t in norm.split() if t not in TYPES and t not in DIRS]
    return " ".join(tokens) or norm


def _geom(s: str):
    return shape(json.loads(s))


def build_streets() -> None:
    df = pd.read_csv(OPEN / "toronto-centreline-tcl.csv", usecols=["LINEAR_NAME_FULL", "FEATURE_CODE_DESC", "geometry"])
    df = df[df["LINEAR_NAME_FULL"].notna()]
    # Keep roads; drop trails, rivers, rail and boundaries.
    keep = df["FEATURE_CODE_DESC"].str.contains("Road|Street|Expressway|Arterial|Collector|Local|Laneway|Access|Ramp|Highway",
                                                case=False, na=False)
    df = df[keep]
    rows = []
    for name, grp in df.groupby("LINEAR_NAME_FULL"):
        lines = []
        for g in grp["geometry"]:
            geom = _geom(g)
            lines.extend(geom.geoms if isinstance(geom, MultiLineString) else [geom])
        merged = linemerge(lines)
        merged = merged if isinstance(merged, MultiLineString) else MultiLineString([merged])
        norm = normalize(name)
        rows.append({"name": name, "norm": norm, "base": base_name(norm), "wkb": merged.wkb})
    pd.DataFrame(rows).to_parquet(OUT / "streets.parquet")
    print(f"streets: {len(rows)}")


def build_intersections() -> None:
    df = pd.read_csv(OPEN / "intersection-file-city-of-toronto.csv", usecols=["INTERSECTION_ID", "INTERSECTION_DESC", "CLASSIFICATION_DESC", "geometry"])
    rows = []
    for r in df.itertuples():
        names = [normalize(n) for n in str(r.INTERSECTION_DESC).split("/") if n.strip()]
        if len(names) < 2:
            continue
        geom = _geom(r.geometry)
        pt = geom.geoms[0] if hasattr(geom, "geoms") else geom
        rows.append({"id": r.INTERSECTION_ID, "desc": r.INTERSECTION_DESC, "class": r.CLASSIFICATION_DESC,
                     "streets": names, "bases": sorted({base_name(n) for n in names}), "lat": pt.y, "lon": pt.x})
    pd.DataFrame(rows).to_parquet(OUT / "intersections.parquet")
    print(f"intersections: {len(rows)}")


def build_gtfs() -> None:
    z = zipfile.ZipFile(OPEN / "ttc-routes-and-schedules.zip")
    stops = pd.read_csv(io.BytesIO(z.read("stops.txt")))
    stops["norm"] = stops["stop_name"].map(normalize)
    stops["is_station"] = stops["stop_name"].str.contains("Station", case=False, na=False)
    stops[["stop_id", "stop_name", "norm", "is_station", "stop_lat", "stop_lon"]].rename(
        columns={"stop_lat": "lat", "stop_lon": "lon"}).to_parquet(OUT / "stops.parquet")
    routes = pd.read_csv(io.BytesIO(z.read("routes.txt")))
    trips = pd.read_csv(io.BytesIO(z.read("trips.txt")), usecols=["route_id", "shape_id"]).drop_duplicates()
    shapes = pd.read_csv(io.BytesIO(z.read("shapes.txt")))
    shapes = shapes.sort_values(["shape_id", "shape_pt_sequence"])
    shape_lines = {sid: LineString(list(zip(g["shape_pt_lon"], g["shape_pt_lat"])))
                   for sid, g in shapes.groupby("shape_id") if len(g) > 1}
    rows = []
    for r in routes.itertuples():
        sids = trips.loc[trips["route_id"] == r.route_id, "shape_id"].unique()
        lines = [shape_lines[s] for s in sids if s in shape_lines]
        if not lines:
            continue
        rows.append({"short_name": str(r.route_short_name), "long_name": r.route_long_name,
                     "route_type": r.route_type, "wkb": MultiLineString(lines).wkb})
    pd.DataFrame(rows).to_parquet(OUT / "routes.parquet")
    print(f"stops: {len(stops)} routes: {len(rows)}")


def build_shelters() -> None:
    df = pd.read_csv(OPEN / "street-furniture-transit-shelter.csv")
    rows = []
    for r in df.itertuples():
        geom = _geom(r.geometry)
        pt = geom.geoms[0] if hasattr(geom, "geoms") else geom
        streets = [normalize(s) for s in (r.ADDRESSSTREET, r.FRONTINGSTREET, r.FROMSTREET) if isinstance(s, str)]
        rows.append({"id": r.ID, "streets": streets, "lat": pt.y, "lon": pt.x, "status": r.STATUS})
    pd.DataFrame(rows).to_parquet(OUT / "shelters.parquet")
    print(f"shelters: {len(rows)}")


def build_overture(release: str = "2026-09-23.1") -> None:
    import duckdb

    w, s, e, n = TORONTO_BBOX
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    q = f"""
    COPY (
      SELECT p.id, p.names['primary'] AS name, p.basic_category AS category,
             p.brand['names']['primary'] AS brand, p.confidence, p.operating_status,
             ST_Y(p.geometry) AS lat, ST_X(p.geometry) AS lon
      FROM read_parquet('s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*', hive_partitioning=1) AS p
      WHERE p.bbox.xmin BETWEEN {w} AND {e} AND p.bbox.ymin BETWEEN {s} AND {n} AND p.names['primary'] IS NOT NULL
    ) TO '{(OUT / "places.parquet").as_posix()}' (FORMAT parquet)
    """
    con.execute(q)
    cnt = con.execute(f"SELECT count(*) FROM '{(OUT / 'places.parquet').as_posix()}'").fetchone()[0]
    print(f"overture places: {cnt}")


def describe_overture(release: str = "2026-09-23.1") -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    src = f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
    for name, typ, *_ in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{src}', hive_partitioning=1) LIMIT 0").fetchall():
        print(name, "::", typ[:120])


if __name__ == "__main__":
    ensure_dirs(OUT)
    if len(sys.argv) > 1 and sys.argv[1] == "describe":
        describe_overture(*(sys.argv[2:3]))
    elif len(sys.argv) > 1 and sys.argv[1] == "overture":
        build_overture(*(sys.argv[2:3]))
    else:
        build_streets()
        build_intersections()
        build_gtfs()
        build_shelters()
