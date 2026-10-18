"""Bellingcat-style co-occurrence search over the City of Toronto asset table (data/toronto_assets.duckdb).

The first --require is the anchor; every other --require must have at least one instance within its radius of
the anchor. Spec syntax: type[/subtype][:metres] or osm:key=value[:metres] (OSM nodes and way vertices from
data/Toronto.osm.pbf, densified to 2 m). Types: pole shelter hydrant bike_ring signal bin bench ttc_stop.
Pole subtypes: street_light traffic_signal pedestrian_light miscellaneous (alias hydro/utility) circular_hydro_tower;
ttc_stop subtypes: bus streetcar subway. Hits are merged into candidate points (greedy, --cluster metres).
Temporarily removed street furniture is skipped unless --include-removed. Build the table with assets_load.py.

Usage:
  .venv/Scripts/python asset_search.py --require shelter --require hydrant:15 --require pole/street_light:20
  .venv/Scripts/python asset_search.py --require ttc_stop/streetcar --require osm:amenity=parking:40 --bbox 43.63,-79.47,43.67,-79.40
"""
import argparse
import json
import math
import re
import time
from pathlib import Path

import duckdb
import numpy as np

HERE = Path(__file__).parent
DB = HERE / "data" / "toronto_assets.duckdb"
PBF = HERE / "data" / "Toronto.osm.pbf"
TORONTO_BBOX = (43.58, -79.64, 43.86, -79.11)
TYPES = ("pole", "shelter", "hydrant", "bike_ring", "signal", "bin", "bench", "ttc_stop")
TYPE_ALIASES = {"bike": "bike_ring", "bike_rack": "bike_ring", "bicycle_parking": "bike_ring", "litter": "bin",
                "litter_bin": "bin", "trash": "bin", "garbage": "bin", "receptacle": "bin", "stop": "ttc_stop",
                "bus_stop": "ttc_stop", "streetcar_stop": "ttc_stop/streetcar", "transit_shelter": "shelter",
                "bus_shelter": "shelter", "fire_hydrant": "hydrant", "streetlight": "pole/street_light",
                "street_light": "pole/street_light", "utility_pole": "pole/hydro", "hydro_pole": "pole/hydro",
                "tram": "osm:railway=tram", "streetcar_track": "osm:railway=tram"}
SUBTYPE_ALIASES = {
    "pole": {"street_light": {"street_light", "street_light_and_traffic_signal"},
             "streetlight": {"street_light", "street_light_and_traffic_signal"},
             "light": {"street_light", "street_light_and_traffic_signal", "pedestrian_light"},
             "traffic_signal": {"traffic_signal", "street_light_and_traffic_signal"},
             "signal": {"traffic_signal", "street_light_and_traffic_signal"},
             "traffic_light": {"traffic_signal", "street_light_and_traffic_signal"},
             "pedestrian_light": {"pedestrian_light"},
             "hydro": {"miscellaneous", "circular_hydro_tower"}, "utility": {"miscellaneous", "circular_hydro_tower"},
             "wooden": {"miscellaneous", "circular_hydro_tower"}, "wood": {"miscellaneous", "circular_hydro_tower"},
             "misc": {"miscellaneous"}, "hydro_tower": {"circular_hydro_tower"}},
}
REMOVED_SQL = "coalesce(attrs->>'STATUS', 'Existing') NOT ILIKE '%removed%'"

# ---------------------------------------------------------------- UTM 17N (WGS84) without pyproj (Snyder 1987)
_A, _F, _K0, _LON0 = 6378137.0, 1 / 298.257223563, 0.9996, math.radians(-81.0)
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)
_M1 = 1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256
_M2 = 3 * _E2 / 8 + 3 * _E2 ** 2 / 32 + 45 * _E2 ** 3 / 1024
_M3 = 15 * _E2 ** 2 / 256 + 45 * _E2 ** 3 / 1024
_M4 = 35 * _E2 ** 3 / 3072


def utm_forward(lat, lon):
    """WGS84 degrees -> EPSG:32617 metres (matches PROJ to < 1 cm inside Toronto)."""
    p, lam = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    n = _A / np.sqrt(1 - _E2 * np.sin(p) ** 2)
    t, c, a = np.tan(p) ** 2, _EP2 * np.cos(p) ** 2, np.cos(p) * (lam - _LON0)
    m = _A * (_M1 * p - _M2 * np.sin(2 * p) + _M3 * np.sin(4 * p) - _M4 * np.sin(6 * p))
    x = _K0 * n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * _EP2) * a ** 5 / 120) + 5e5
    y = _K0 * (m + n * np.tan(p) * (a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                                    + (61 - 58 * t + t * t + 600 * c - 330 * _EP2) * a ** 6 / 720))
    return x, y


def utm_inverse(x, y):
    """EPSG:32617 metres -> (lat, lon) degrees."""
    x, y = np.asarray(x, float) - 5e5, np.asarray(y, float)
    mu = y / _K0 / (_A * _M1)
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32)
          * np.sin(4 * mu) + 151 * e1 ** 3 / 96 * np.sin(6 * mu) + 1097 * e1 ** 4 / 512 * np.sin(8 * mu))
    c1, t1 = _EP2 * np.cos(p1) ** 2, np.tan(p1) ** 2
    n1 = _A / np.sqrt(1 - _E2 * np.sin(p1) ** 2)
    r1 = _A * (1 - _E2) / (1 - _E2 * np.sin(p1) ** 2) ** 1.5
    d = x / (n1 * _K0)
    lat = p1 - n1 * np.tan(p1) / r1 * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * _EP2) * d ** 4 / 24
                                       + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * _EP2 - 3 * c1 * c1)
                                       * d ** 6 / 720)
    lon = _LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * _EP2
                                                       + 24 * t1 * t1) * d ** 5 / 120) / np.cos(p1)
    return np.degrees(lat), np.degrees(lon)


# ---------------------------------------------------------------- spatial grid index (numpy only)
class Grid:
    """Uniform-grid index over 2-D points; query_pairs returns all (query, point, distance) pairs within r."""

    def __init__(self, x, y, cell=40.0):
        self.x, self.y, self.cell = np.asarray(x, float), np.asarray(y, float), float(cell)
        key = self._key(np.floor(self.x / cell), np.floor(self.y / cell))
        self.order = np.argsort(key, kind="stable")
        self.ukey, self.start, self.count = np.unique(key[self.order], return_index=True, return_counts=True)

    @staticmethod
    def _key(gx, gy):
        return gx.astype(np.int64) * (1 << 24) + gy.astype(np.int64)

    def query_pairs(self, qx, qy, r):
        qx, qy = np.asarray(qx, float), np.asarray(qy, float)
        if len(self.ukey) == 0 or len(qx) == 0:
            return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
        gx, gy = np.floor(qx / self.cell), np.floor(qy / self.cell)
        span = int(math.ceil(r / self.cell))
        qi_all, pi_all = [], []
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                k = self._key(gx + dx, gy + dy)
                pos = np.clip(np.searchsorted(self.ukey, k), 0, len(self.ukey) - 1)
                hit = np.nonzero(self.ukey[pos] == k)[0]
                if len(hit) == 0:
                    continue
                st, ct = self.start[pos[hit]], self.count[pos[hit]]
                tot = int(ct.sum())
                within = np.arange(tot) - np.repeat(np.cumsum(ct) - ct, ct)
                qi_all.append(np.repeat(hit, ct))
                pi_all.append(self.order[np.repeat(st, ct) + within])
        if not qi_all:
            return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
        qi, pi = np.concatenate(qi_all), np.concatenate(pi_all)
        d = np.hypot(self.x[pi] - qx[qi], self.y[pi] - qy[qi])
        keep = d <= r
        return qi[keep], pi[keep], d[keep]

    def knn_padded(self, qx, qy, r, k):
        """Up to k nearest points within r of each query, as [Q, k] index/distance arrays (-1 / inf padded)."""
        qi, pi, d = self.query_pairs(qx, qy, r)
        idx = np.full((len(qx), k), -1, np.int64)
        dist = np.full((len(qx), k), np.inf)
        if len(qi):
            o = np.lexsort((d, qi))
            qi, pi, d = qi[o], pi[o], d[o]
            first = np.searchsorted(qi, qi, side="left")
            rank = np.arange(len(qi)) - first
            keep = rank < k
            idx[qi[keep], rank[keep]] = pi[keep]
            dist[qi[keep], rank[keep]] = d[keep]
        return idx, dist


def greedy_cluster(x, y, radius, score=None):
    """Greedy clustering: points (best score first) seed a cluster unless within radius of an existing seed."""
    order = np.argsort(-np.asarray(score)) if score is not None else np.arange(len(x))
    seeds, label, cells = [], np.full(len(x), -1, np.int64), {}
    for i in order:
        cx, cy = int(x[i] // radius), int(y[i] // radius)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for s in cells.get((cx + dx, cy + dy), ()):
                    if math.hypot(x[s] - x[i], y[s] - y[i]) < radius:
                        best = s
                        break
                if best is not None:
                    break
            if best is not None:
                break
        if best is None:
            cells.setdefault((cx, cy), []).append(i)
            label[i] = len(seeds)
            seeds.append(i)
        else:
            label[i] = label[best]
    return np.array(seeds, np.int64), label


# ---------------------------------------------------------------- asset table access
def connect():
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("LOAD spatial;")
    return con


def load_assets(con, include_removed=False):
    """All assets as numpy arrays (x, y in UTM 17N)."""
    where = "" if include_removed else f"WHERE {REMOVED_SQL}"
    rows = con.execute(f"SELECT asset_id, type, subtype, x, y FROM assets {where}").fetchnumpy()
    return {"id": np.asarray(rows["asset_id"], dtype=object), "type": np.asarray(rows["type"], dtype=object),
            "subtype": np.asarray(rows["subtype"], dtype=object),
            "x": np.asarray(rows["x"], float), "y": np.asarray(rows["y"], float)}


def resolve_subtypes(typ, sub, known):
    """Map a requested subtype (or alias) onto the set of source subtypes of that type."""
    if not sub:
        return None
    sub = sub.lower().replace(" ", "_").replace("-", "_")
    alias = SUBTYPE_ALIASES.get(typ, {}).get(sub)
    if alias:
        return set(alias)
    hits = {s for s in known if s == sub or s.startswith(sub) or sub in s.split("+")}
    return hits or {sub}


def parse_spec(spec):
    """'pole/street_light:20' -> {'type': 'pole', 'sub': 'street_light', 'dist': 20.0}; 'osm:k=v:30' -> osm."""
    dist = None
    m = re.match(r"^(.*?):(\d+(?:\.\d+)?)$", spec.strip())
    if m:
        spec, dist = m.group(1), float(m.group(2))
    spec = spec.strip()
    if spec.lower() in TYPE_ALIASES:
        spec = TYPE_ALIASES[spec.lower()]
    if spec.startswith("osm:"):
        return {"type": "osm", "tag": spec[4:], "dist": dist, "label": spec}
    typ, _, sub = spec.partition("/")
    typ = TYPE_ALIASES.get(typ.lower(), typ.lower())
    if "/" in typ:  # alias carried a subtype
        typ, sub = typ.split("/")
    if typ not in TYPES:
        raise SystemExit(f"unknown asset type {typ!r}; expected one of {TYPES} or osm:key=value")
    return {"type": typ, "sub": sub or None, "dist": dist, "label": spec}


def densify(xs, ys, spacing):
    """Polyline vertices -> points every <= spacing metres (vertices kept)."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < 2:
        return xs, ys
    seg = np.hypot(np.diff(xs), np.diff(ys))
    n = np.maximum(1, np.ceil(seg / spacing).astype(int))
    t = np.concatenate([np.arange(k) / k for k in n])
    i = np.repeat(np.arange(len(seg)), n)
    px = np.append(xs[i] + t * (xs[i + 1] - xs[i]), xs[-1])
    py = np.append(ys[i] + t * (ys[i + 1] - ys[i]), ys[-1])
    return px, py


def osm_points(con, tag, spacing=2.0):
    """OSM nodes with key=value plus densified vertices of ways with key=value, in UTM. Uses osm_lines for trams."""
    key, value = tag.split("=", 1)
    if (key, value) == ("railway", "tram"):
        lines = con.execute("SELECT osm_id, xs, ys FROM osm_lines WHERE kind = 'tram'").fetchall()
        node_rows = []
    else:
        pbf = PBF.as_posix()
        cond = f"tags['{key}'] = '{value}'" if value != "*" else f"tags['{key}'] IS NOT NULL"
        mem = duckdb.connect()
        mem.execute("LOAD spatial;")
        node_rows = mem.execute(f"SELECT id, lat, lon FROM ST_ReadOSM('{pbf}') WHERE kind = 'node' AND {cond}"
                                ).fetchall()
        mem.execute(f"CREATE TEMP TABLE w AS SELECT id, refs FROM ST_ReadOSM('{pbf}') WHERE kind = 'way' AND {cond}")
        mem.execute("CREATE TEMP TABLE wn AS SELECT w.id, u.idx, u.ref FROM w, LATERAL (SELECT unnest(w.refs) AS ref, "
                    "generate_subscripts(w.refs, 1) AS idx) u")
        mem.execute(f"CREATE TEMP TABLE n AS SELECT id, lat, lon FROM ST_ReadOSM('{pbf}') WHERE kind = 'node' "
                    "AND id IN (SELECT ref FROM wn)")
        raw = mem.execute("SELECT wn.id, list(n.lat ORDER BY wn.idx), list(n.lon ORDER BY wn.idx) FROM wn "
                          "JOIN n ON n.id = wn.ref GROUP BY wn.id").fetchall()
        lines = []
        for wid, lats, lons in raw:
            lx, ly = utm_forward(lats, lons)
            lines.append((wid, lx, ly))
    px, py, pid = [], [], []
    for wid, lx, ly in lines:
        dx, dy = densify(lx, ly, spacing)
        px.append(dx)
        py.append(dy)
        pid += [f"way/{wid}"] * len(dx)
    if node_rows:
        nx, ny = utm_forward([r[1] for r in node_rows], [r[2] for r in node_rows])
        px.append(nx)
        py.append(ny)
        pid += [f"node/{r[0]}" for r in node_rows]
    if not px:
        return np.zeros(0), np.zeros(0), np.zeros(0, dtype=object)
    return np.concatenate(px), np.concatenate(py), np.asarray(pid, dtype=object)


def select(assets, spec, bbox_xy=None, pad=0.0, con=None):
    """Indices/coords of assets matching a parsed spec (OSM specs return their own point set)."""
    if spec["type"] == "osm":
        x, y, ids = osm_points(con, spec["tag"])
    else:
        m = assets["type"] == spec["type"]
        subs = resolve_subtypes(spec["type"], spec["sub"], set(assets["subtype"][m]))
        if subs:
            m &= np.isin(assets["subtype"], list(subs))
        x, y, ids = assets["x"][m], assets["y"][m], assets["id"][m]
    if bbox_xy is not None:
        x0, y0, x1, y1 = bbox_xy
        k = (x >= x0 - pad) & (x <= x1 + pad) & (y >= y0 - pad) & (y <= y1 + pad)
        x, y, ids = x[k], y[k], ids[k]
    return x, y, ids


def bbox_to_xy(bbox):
    lat0, lon0, lat1, lon1 = bbox
    xs, ys = utm_forward([lat0, lat0, lat1, lat1], [lon0, lon1, lon0, lon1])
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--require", action="append", required=True,
                    help="type[/subtype][:metres] or osm:key=value[:metres]; first one is the anchor")
    ap.add_argument("--bbox", help="min_lat,min_lon,max_lat,max_lon")
    ap.add_argument("--within", type=float, default=25.0, help="default radius when a spec has no :metres")
    ap.add_argument("--cluster", type=float, default=30.0, help="merge hits closer than this (m)")
    ap.add_argument("--include-removed", action="store_true", help="keep 'Temporarily Removed' furniture")
    ap.add_argument("--show", type=int, default=15, help="print this many candidate points")
    args = ap.parse_args()

    t0 = time.perf_counter()
    con = connect()
    assets = load_assets(con, args.include_removed)
    specs = [parse_spec(s) for s in args.require]
    bbox_xy = bbox_to_xy([float(v) for v in args.bbox.split(",")]) if args.bbox else None
    t_load = time.perf_counter() - t0

    ax, ay, aid = select(assets, specs[0], bbox_xy, con=con)
    keep = np.ones(len(ax), bool)
    nearest = {}
    counts = {specs[0]["label"]: len(ax)}
    for s in specs[1:]:
        r = s["dist"] or args.within
        cx, cy, cid = select(assets, s, bbox_xy, pad=r, con=con)
        counts[s["label"]] = len(cx)
        qi, pi, d = Grid(cx, cy, cell=max(r, 10)).query_pairs(ax, ay, r)
        o = np.lexsort((d, qi))
        qi, pi, d = qi[o], pi[o], d[o]
        first = np.unique(qi, return_index=True)[1]
        has = np.zeros(len(ax), bool)
        has[qi[first]] = True
        keep &= has
        nearest[s["label"]] = (dict(zip(qi[first].tolist(), cid[pi[first]].tolist())),
                               dict(zip(qi[first].tolist(), d[first].tolist())))
    hits = np.nonzero(keep)[0]
    seeds, label = greedy_cluster(ax[hits], ay[hits], args.cluster)
    t_total = time.perf_counter() - t0

    lat, lon = utm_inverse(ax[hits], ay[hits])
    out_hits = []
    for j, i in enumerate(hits):
        h = {"anchor": aid[i], "lat": round(float(lat[j]), 6), "lon": round(float(lon[j]), 6),
             "cluster": int(label[j])}
        for s in specs[1:]:
            ids, ds = nearest[s["label"]]
            h[s["label"]] = {"id": ids[i], "dist_m": round(ds[i], 1)}
        out_hits.append(h)
    clusters = []
    for c, sj in enumerate(seeds):
        members = [h for h in out_hits if h["cluster"] == c]
        clusters.append({"lat": out_hits[sj]["lat"], "lon": out_hits[sj]["lon"], "n_hits": len(members),
                         "anchors": [m["anchor"] for m in members][:20]})
    clusters.sort(key=lambda c: -c["n_hits"])

    name = "__".join(re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") for s in args.require)[:120]
    out = HERE / "results" / f"asset_search_{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"args": vars(args), "candidate_counts": counts, "n_hits": len(hits),
                               "n_candidates": len(clusters), "load_s": round(t_load, 2),
                               "total_s": round(t_total, 2), "candidates": clusters, "hits": out_hits}, indent=1))
    print("pool sizes: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"{len(hits)} hits -> {len(clusters)} candidate points (clustered at {args.cluster:.0f} m); "
          f"load {t_load:.2f}s, total {t_total:.2f}s")
    for i, c in enumerate(clusters[:args.show], 1):
        print(f"{i:3d}. {c['lat']:.6f}, {c['lon']:.6f}  hits {c['n_hits']:>3}  e.g. {', '.join(c['anchors'][:3])}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
