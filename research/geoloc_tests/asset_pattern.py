"""Asset-pattern matcher: place a camera from the left-to-right list of City assets visible in a photo.

Input JSON (from a vision-LLM call):
  {"fov_deg": 90, "assets": [{"type": "pole", "subtype": "hydro", "order": 1, "approx_distance_m": 10},
                             {"type": "pole", "subtype": "street_light", "order": 2, "approx_distance_m": 15},
                             {"type": "shelter", "order": 3, "approx_distance_m": 8}]}
Types: pole (subtypes street_light, traffic_signal, pedestrian_light, hydro), shelter, hydrant, bike_ring, bin,
bench, ttc_stop, tram (OSM railway=tram). Free-text types ("wooden utility pole", "streetcar tracks") are mapped.

Method: anchor on the rarest observed type; around every instance in the search region, sample camera positions
on rings at the observed distance (x0.65..1.8) and headings that keep the anchor in the FOV. Drop positions more
than ~15 m from an OSM highway/footway centreline. Each pose is scored by an order-preserving alignment (edit-
distance DP) between the observed list and the assets actually in the FOV within 40 m, sorted by bearing:
log-distance error per match, subtype mismatch penalty, 1.0 per observed asset with no counterpart, small penalty
per unexpected visible asset of an observed type (or a shelter). The best poses are refined on a finer local grid,
merged with 15 m non-maximum suppression and explained (matched asset IDs). Scoring is vectorized with torch (CPU).

Usage:
  .venv/Scripts/python asset_pattern.py obs.json [--bbox 43.63,-79.47,43.67,-79.40 | --candidates c.json --radius 150]
  .venv/Scripts/python asset_pattern.py --run-tests          # synthetic recovery, uniqueness, test2.png
"""
import argparse
import json
import math
import re
import time
from pathlib import Path

import cv2
import numpy as np
import torch

import asset_search as AS

HERE = Path(__file__).parent
RESULTS = HERE / "results"
POINT_TYPES = ("pole", "shelter", "hydrant", "bike_ring", "bin", "bench", "ttc_stop")  # physical, point-located
LINE_TYPES = ("tram",)
SALIENT = ("shelter",)  # an unmentioned visible shelter is penalized even if no shelter was observed
ROAD_EXCLUDE = ("raceway", "bus_guideway", "bridleway", "escape", "pastry")
OBS_POLE_SUBTYPE = {"street_light": "street_light", "miscellaneous": "hydro", "traffic_signal": "traffic_signal",
                    "street_light_and_traffic_signal": "traffic_signal", "pedestrian_light": "pedestrian_light",
                    "circular_hydro_tower": "hydro"}
INF = 1e6


def params(**kw):
    p = dict(r_vis=40.0, r_extra=25.0, miss=1.0, extra=0.12, sub_pen=0.4, sigma=0.35, max_ratio=2.5,
             fov_margin=3.0, m_points=64, m_pos=24, m_lines=48, m_vis=12, nms=15.0, ring=(0.65, 0.85, 1.1, 1.4, 1.8),
             ring_default=(4.0, 8.0, 13.0, 20.0, 28.0), spacing=4.0, pos_budget=6e6, chunk_q=40000,
             keep_top=3000, refine_top=150, rescore_top=500, line_spacing=4.0, line_anchor_spacing=10.0)
    p.update(kw)
    return p


def strict_params(**kw):
    """Consistency mode for counting look-alike places: every observed asset must be matched (else cost >= 100),
    subtypes must agree and each distance must be within x/÷1.7 of the observation; no extra penalty."""
    return params(miss=100.0, extra=0.0, sub_pen=INF, max_ratio=1.7, **kw)


def normalize_item(item):
    """Map a free-text observed asset onto (type, subtype)."""
    t = " " + re.sub(r"[^a-z]+", " ", str(item.get("type", "")).lower()) + " "
    sub = item.get("subtype")
    sub = re.sub(r"[^a-z]+", "_", str(sub).lower()).strip("_") if sub else None

    def has(*words):
        return any(f" {w} " in t or (len(w) > 4 and w in t) for w in words)
    if has("hydrant"):
        return "hydrant", None
    if has("shelter"):
        return "shelter", None
    if has("bench"):
        return "bench", None
    if has("bike", "bicycle", "ring"):
        return "bike_ring", None
    if has("bin", "trash", "litter", "garbage", "receptacle", "waste"):
        return "bin", None
    if has("stop"):
        return "ttc_stop", None
    if has("tram", "streetcar", "track", "tracks", "rail"):
        return "tram", None
    if has("signal", "traffic light"):
        return "pole", "traffic_signal"
    if has("pedestrian light"):
        return "pole", "pedestrian_light"
    if has("street light", "streetlight", "lamp", "light pole", "lamppost"):
        return "pole", "street_light"
    if has("utility", "hydro", "wood", "wooden", "telephone"):
        return "pole", "hydro"
    if has("pole"):
        return "pole", sub
    return None, None


class World:
    """Everything shared between queries: asset arrays, OSM tram points, road-proximity raster, sidewalks."""

    def __init__(self, road_buffer=15.0, res=5.0):
        t0 = time.perf_counter()
        con = AS.connect()
        a = AS.load_assets(con)
        keep = np.isin(a["type"], POINT_TYPES)
        self.id, self.type, self.sub = a["id"][keep], a["type"][keep], a["subtype"][keep]
        self.ox, self.oy = AS.utm_forward(43.58, -79.64)  # local origin keeps float32 precise (< 5 mm)
        self.x, self.y = a["x"][keep] - self.ox, a["y"][keep] - self.oy
        tx, ty, tid = AS.osm_points(con, "railway=tram", spacing=params()["line_spacing"])
        self.lines = {"tram": (tx - self.ox, ty - self.oy, tid)}
        ax, ay, _ = AS.osm_points(con, "railway=tram", spacing=params()["line_anchor_spacing"])
        self.line_anchors = {"tram": (ax - self.ox, ay - self.oy)}
        pairs = sorted({(t, s) for t, s in zip(self.type, self.sub)}) + [(lt, lt) for lt in LINE_TYPES]
        self.codes = {ts: i for i, ts in enumerate(pairs)}
        self.code_type = np.array([t for t, _ in pairs], dtype=object)
        self.code_sub = np.array([s for _, s in pairs], dtype=object)
        self.sc = np.array([self.codes[(t, s)] for t, s in zip(self.type, self.sub)], np.int64)
        self.grid_all = AS.Grid(self.x, self.y, cell=40.0)

        # road / footway proximity raster (camera plausibility)
        excl = ", ".join(f"'{v}'" for v in ROAD_EXCLUDE)
        flat = con.execute(f"SELECT osm_id, unnest(xs) AS x, unnest(ys) AS y, value, sub FROM osm_lines "
                           f"WHERE kind = 'highway' AND value NOT IN ({excl})").fetchnumpy()
        x0, y0, x1, y1 = AS.bbox_to_xy((43.57, -79.65, 43.87, -79.10))
        self.res, self.rx0, self.ry1 = res, x0 - self.ox, y1 - self.oy
        w, h = int((x1 - x0) / res) + 1, int((y1 - y0) / res) + 1
        px = np.round((flat["x"] - x0) / res).astype(np.int32)
        py = np.round((y1 - flat["y"]) / res).astype(np.int32)
        cut = np.nonzero(np.diff(flat["osm_id"]))[0] + 1
        polys = [p for p in np.split(np.stack([px, py], 1), cut) if len(p) >= 2]
        self.road = np.zeros((h, w), np.uint8)
        cv2.polylines(self.road, polys, False, 1, thickness=int(round(2 * road_buffer / res)) + 1)
        sw = np.isin(flat["sub"], ["sidewalk"]) & (flat["value"] == "footway")
        ids, xs, ys = flat["osm_id"][sw], flat["x"][sw] - self.ox, flat["y"][sw] - self.oy
        same = ids[1:] == ids[:-1]
        self.sidewalk_segs = np.stack([xs[:-1][same], ys[:-1][same], xs[1:][same], ys[1:][same]], 1)
        con.close()
        self.load_s = time.perf_counter() - t0

    def on_road(self, x, y):
        ix = np.floor((x - self.rx0) / self.res + 0.5).astype(np.int64)
        iy = np.floor((self.ry1 - y) / self.res + 0.5).astype(np.int64)
        ok = (ix >= 0) & (iy >= 0) & (ix < self.road.shape[1]) & (iy < self.road.shape[0])
        out = np.zeros(len(x), bool)
        out[ok] = self.road[iy[ok], ix[ok]] > 0
        return out

    def to_latlon(self, x, y):
        return AS.utm_inverse(np.asarray(x) + self.ox, np.asarray(y) + self.oy)

    def to_xy(self, lat, lon):
        x, y = AS.utm_forward(lat, lon)
        return x - self.ox, y - self.oy

    def true_heading(self, heading_grid, lon):
        """UTM grid bearing -> true bearing (meridian convergence, ~+1.1 deg in Toronto)."""
        lat = 43.7
        gamma = math.degrees(math.atan(math.tan(math.radians(lon + 81.0)) * math.sin(math.radians(lat))))
        return (heading_grid + gamma) % 360


class Matcher:
    def __init__(self, world, obs, region=None, p=None, n_anchors=1, threads=8):
        self.w, self.p = world, p or params()
        torch.set_num_threads(threads)
        self.fov = float(obs.get("fov_deg") or 90.0)
        self.half = self.fov / 2 + self.p["fov_margin"]
        items, self.ignored = [], []
        for i, it in enumerate(obs.get("assets", [])):
            t, s = normalize_item(it)
            if t is None:
                self.ignored.append(it)
                continue
            d = it.get("approx_distance_m")
            items.append(dict(type=t, sub=s, dist=float(d) if d else None,
                              order=it.get("order", i + 1), raw=it))
        items.sort(key=lambda r: r["order"])
        if not items:
            raise SystemExit("no usable assets in the observation")
        self.items, self.K = items, len(items)
        w = world
        S = len(w.codes)
        tok, sok = np.zeros((self.K, S), bool), np.zeros((self.K, S), bool)
        for k, it in enumerate(items):
            tmask = w.code_type == it["type"]
            tok[k] = tmask
            subs = AS.resolve_subtypes(it["type"], it["sub"], set(w.code_sub[tmask])) if it["sub"] else None
            sok[k] = tmask & (np.isin(w.code_sub, list(subs)) if subs else True)
        self.tab_ok = torch.from_numpy(tok.T.copy())                     # [S, K]
        self.tab_sub = torch.from_numpy(np.where(sok, 0.0, self.p["sub_pen"]).T.astype(np.float32).copy())
        obs_types = {it["type"] for it in items}
        extra = np.isin(w.code_type, list((obs_types | set(SALIENT)) - set(LINE_TYPES)))
        self.extra_ok = torch.from_numpy(extra)
        self.d_obs = torch.tensor([it["dist"] if it["dist"] else float("nan") for it in items], dtype=torch.float32)
        self.has_d = ~torch.isnan(self.d_obs)
        self._build_lut(S)

        # relevant point assets (observed types + salient) and observed line types
        rel = np.isin(w.type, list(obs_types | set(SALIENT)))
        self.ridx = np.nonzero(rel)[0]
        self.rx, self.ry = w.x[self.ridx], w.y[self.ridx]
        self.grid = AS.Grid(self.rx, self.ry, cell=40.0)
        self.RX = torch.from_numpy(np.append(self.rx, 1e7).astype(np.float32))
        self.RY = torch.from_numpy(np.append(self.ry, 1e7).astype(np.float32))
        self.RSC = torch.from_numpy(np.append(w.sc[self.ridx], 0))
        self.line_type = next((t for t in LINE_TYPES if t in obs_types), None)
        if self.line_type:
            lx, ly, self.lid = w.lines[self.line_type]
            self.lgrid = AS.Grid(lx, ly, cell=40.0)
            self.LX = torch.from_numpy(np.append(lx, 1e7).astype(np.float32))
            self.LY = torch.from_numpy(np.append(ly, 1e7).astype(np.float32))
            self.line_code = w.codes[(self.line_type, self.line_type)]

        # region: bbox (x0, y0, x1, y1 local) or candidate points + radius
        self.region = region or {}
        if "points" in self.region:
            cx, cy = self.region["points"]
            self.cgrid = AS.Grid(cx, cy, cell=max(self.region["radius"], 50.0))

        # anchor pools (strict type+subtype), rarest first
        pools = []
        for k, it in enumerate(items):
            if it["type"] in LINE_TYPES:
                axy = w.line_anchors[it["type"]]
            else:
                m = tok[k][w.sc[self.ridx]] & sok[k][w.sc[self.ridx]]
                axy = (self.rx[m], self.ry[m])
            rmax = self._radii(it).max()
            keep = self._in_region(axy[0], axy[1], pad=rmax)
            pools.append((int(keep.sum()), k, axy[0][keep], axy[1][keep]))
        pools.sort(key=lambda r: r[0])
        self.pools = pools
        # rarest non-empty pool, plus further distinct (type, subtype) pools of <= 80k instances if requested
        self.anchor_items, seen = [], set()
        for pl in pools:
            key = (items[pl[1]]["type"], items[pl[1]]["sub"])
            if pl[0] == 0 or key in seen or len(self.anchor_items) >= n_anchors:
                continue
            if self.anchor_items and pl[0] > 80000:
                break
            self.anchor_items.append(pl)
            seen.add(key)
        if not self.anchor_items:
            raise SystemExit("none of the observed asset types occur in the search region")

    # -------------------------------------------------------------- helpers
    def _radii(self, it):
        return np.array([f * it["dist"] for f in self.p["ring"]]) if it["dist"] else np.array(self.p["ring_default"])

    def _in_region(self, x, y, pad=0.0):
        r = self.region
        if "bbox" in r:
            x0, y0, x1, y1 = r["bbox"]
            return (x >= x0 - pad) & (x <= x1 + pad) & (y >= y0 - pad) & (y <= y1 + pad)
        if "points" in r:
            qi, _, _ = self.cgrid.query_pairs(x, y, r["radius"] + pad)
            out = np.zeros(len(x), bool)
            out[qi] = True
            return out
        return np.ones(len(x), bool)

    def _ring(self, it, spacing, thin=False):
        """Camera offsets around an anchor: rings at the candidate radii, ~spacing metres apart along each ring.
        thin=True (huge anchor pools) keeps 3 of the 5 radii and allows 6 positions per ring."""
        offs = []
        radii = self._radii(it)
        for r in (radii[::2] if thin else radii):
            n = int(np.clip(round(2 * math.pi * r / spacing), 6 if thin else 8, 36))
            th = np.arange(n) * 2 * math.pi / n
            offs.append(np.stack([r * np.sin(th), r * np.cos(th)], 1))
        return np.concatenate(offs)

    # -------------------------------------------------------------- vectorized scoring
    def score(self, qx, qy, heads, nbp, nbl=None):
        """qx, qy [Q] (numpy, local metres); heads [Q, H] deg; nbp [Q, M] indices into relevant points (-1 pad);
        nbl [Q, Ml] indices into line points. Returns cost [Q, H] (torch float32)."""
        p = self.p
        d_s, sc_s, v_s, _, _ = self._candidates(qx, qy, heads, nbp, nbl)
        Q, H = heads.shape
        mv = d_s.shape[-1]
        d2, sc2, v2 = (t.reshape(Q * H, mv).t().contiguous() for t in (d_s, sc_s, v_s))     # [mv, B]
        costs = self._pair_cost(d2, sc2, v2)
        extra = torch.where(v2 & self.extra_ok[sc2] & (d2 <= p["r_extra"]),
                            torch.tensor(p["extra"]), torch.tensor(0.0))
        return self._dp(costs, extra).reshape(Q, H)

    def _candidates(self, qx, qy, heads, nbp, nbl=None):
        """Visible candidates per pose, nearest m_vis then sorted left -> right: distance, code, visible flag,
        relative bearing and source index (>= 0: relevant point index, < 0: -(line point index + 1)),
        each [Q, H, m_vis]."""
        p = self.p
        qx = torch.from_numpy(qx.astype(np.float32))
        qy = torch.from_numpy(qy.astype(np.float32))
        heads = torch.from_numpy(heads.astype(np.float32))
        nbp = torch.from_numpy(np.where(nbp < 0, len(self.rx), nbp))
        flat = nbp.reshape(-1)
        dx = self.RX.index_select(0, flat).view(nbp.shape) - qx[:, None]
        dy = self.RY.index_select(0, flat).view(nbp.shape) - qy[:, None]
        dist = torch.hypot(dx, dy)                                            # [Q, M]
        # keep the nearest m_pos assets within r_vis of each position before expanding over headings
        mq = min(p["m_pos"], dist.shape[1])
        dist, ki = torch.topk(torch.where(dist <= p["r_vis"], dist, torch.full_like(dist, INF)), mq, dim=1,
                              largest=False, sorted=False)
        valid = dist < INF
        brg = torch.rad2deg(torch.atan2(torch.gather(dx, 1, ki), torch.gather(dy, 1, ki)))
        sc = torch.gather(self.RSC.index_select(0, flat).view(nbp.shape), 1, ki)
        src = torch.gather(nbp, 1, ki)
        rel = torch.remainder(brg[:, None, :] - heads[:, :, None] + 180.0, 360.0) - 180.0   # [Q, H, mq]
        vis = (rel.abs() <= self.half) & valid[:, None, :]
        dist = dist[:, None, :].expand_as(rel)
        sc = sc[:, None, :].expand_as(rel)
        src = src[:, None, :].expand_as(rel)
        if nbl is not None:
            nbl = torch.from_numpy(np.where(nbl < 0, len(self.LX) - 1, nbl))
            ldx, ldy = self.LX[nbl] - qx[:, None], self.LY[nbl] - qy[:, None]
            ld = torch.hypot(ldx, ldy)
            lrel = torch.remainder(torch.rad2deg(torch.atan2(ldx, ldy))[:, None, :] - heads[:, :, None] + 180.0,
                                   360.0) - 180.0
            lvis = (lrel.abs() <= self.half) & (ld <= p["r_vis"])[:, None, :]
            lkey = torch.where(lvis, ld[:, None, :].expand_as(lrel), torch.full_like(lrel, INF))
            lmin, larg = lkey.min(dim=-1, keepdim=True)
            rel = torch.cat([rel, torch.gather(lrel, -1, larg)], -1)
            vis = torch.cat([vis, lmin < INF], -1)
            dist = torch.cat([dist, lmin], -1)
            sc = torch.cat([sc, torch.full_like(larg, self.line_code)], -1)
            src = torch.cat([src, -(torch.gather(nbl[:, None, :].expand_as(lrel), -1, larg) + 1)], -1)
        mv = min(p["m_vis"], rel.shape[-1])
        key = torch.where(vis, dist, torch.full_like(dist, INF))
        kd, ki = torch.topk(key, mv, dim=-1, largest=False, sorted=False)   # nearest visible
        r_s = torch.where(kd < INF, torch.gather(rel, -1, ki), torch.full_like(kd, 999.0))
        r_s, order = torch.sort(r_s, dim=-1)                                # then left -> right
        ki = torch.gather(ki, -1, order)
        d_s = torch.gather(dist, -1, ki)
        v_s = r_s < 999.0
        return d_s, torch.gather(sc, -1, ki), v_s, r_s, torch.gather(src, -1, ki)

    LOG_MIN, BIN, NBIN = math.log(0.5), 0.02, 250   # log-distance bins: 0.5 m .. 74 m, 2 % steps

    def _build_lut(self, S):
        """Match cost for every (asset code, log-distance bin, observed item): [K, S * NBIN + 1], last row INF."""
        p = self.p
        logd = self.LOG_MIN + (torch.arange(self.NBIN, dtype=torch.float32) + 0.5) * self.BIN
        lr = logd[None, :, None] - torch.log(self.d_obs)[None, None, :]                  # [1, NBIN, K]
        dc = torch.where(self.has_d, 0.25 * (lr / p["sigma"]).square().clamp(max=4.0), torch.zeros(()))
        ok = self.tab_ok[:, None, :] & ~(self.has_d & (lr.abs() > math.log(p["max_ratio"])))
        cost = torch.where(ok, dc + self.tab_sub[:, None, :], torch.tensor(INF)).reshape(S * self.NBIN, self.K)
        self.lut = torch.cat([cost, torch.full((1, self.K), INF)]).t().contiguous()
        self.inf_row = S * self.NBIN

    def _pair_cost(self, d, sc, v):
        """Candidate distance/code/visibility tensors (any shape) -> list of K match-cost tensors (INF = no)."""
        b = ((torch.log(d.clamp(min=0.5)) - self.LOG_MIN) / self.BIN).long().clamp(0, self.NBIN - 1)
        idx = torch.where(v, sc * self.NBIN + b, torch.tensor(self.inf_row))
        return [self.lut[k][idx] for k in range(self.K)]

    def _dp(self, costs, extra):
        """Order-preserving alignment (edit distance) of K observed items to M bearing-sorted candidates.
        costs: K tensors [M, B]; extra: [M, B] penalty for skipping a candidate."""
        miss = self.p["miss"]
        M, B = extra.shape
        K = len(costs)
        E = [torch.full((B,), k * miss) for k in range(K + 1)]
        for j in range(M):
            ex = extra[j]
            new = [E[0] + ex]
            for k in range(1, K + 1):
                v = torch.minimum(E[k] + ex, E[k - 1] + costs[k - 1][j])
                new.append(torch.minimum(v, new[k - 1] + miss))
            E = new
        return E[K]

    # -------------------------------------------------------------- search
    def _neighbours(self, cx, cy, r):
        nbp, _ = self.grid.knn_padded(cx, cy, r, self.p["m_points"])
        nbl = self.lgrid.knn_padded(cx, cy, r, self.p["m_lines"])[0] if self.line_type else None
        return nbp, nbl

    def _eval(self, cx, cy, offs, base_heads, rel_heads, keep_fn):
        """For centres (cx, cy) evaluate positions centre+offs with headings base(+)rel; returns per-position best."""
        p = self.p
        out = []
        r_nb = p["r_vis"] + float(np.hypot(offs[:, 0], offs[:, 1]).max()) + 1.0
        P = len(offs)
        per = max(1, p["chunk_q"] // P)
        for s in range(0, len(cx), per):
            ax, ay = cx[s:s + per], cy[s:s + per]
            nbp, nbl = self._neighbours(ax, ay, r_nb)
            qx = (ax[:, None] + offs[None, :, 0]).ravel()
            qy = (ay[:, None] + offs[None, :, 1]).ravel()
            qa = np.repeat(np.arange(len(ax)), P)
            ok = self.w.on_road(qx, qy) & self._in_region(qx, qy)
            if not ok.any():
                continue
            qx, qy, qa = qx[ok], qy[ok], qa[ok]
            self._n_eval += len(qx)
            base = base_heads(ax, ay, qx, qy, qa + s)
            heads = (base[:, None] + rel_heads[None, :]) % 360
            cost = self.score(qx, qy, heads, nbp[qa], nbl[qa] if nbl is not None else None)
            best, hi = cost.min(dim=1)
            out.append(keep_fn(best.numpy(), qx, qy, np.take_along_axis(heads, hi.numpy()[:, None], 1)[:, 0]))
        if not out:
            return np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0)
        return tuple(np.concatenate(z) for z in zip(*out))

    def _keep_top(self, n):
        def f(c, x, y, h):
            if len(c) > n:
                i = np.argpartition(c, n)[:n]
                return c[i], x[i], y[i], h[i]
            return c, x, y, h
        return f

    def _keep_finite(self, thresh, cell=10.0):
        def f(c, x, y, h):
            i = np.nonzero(c < thresh)[0]
            c, x, y, h = c[i], x[i], y[i], h[i]
            if len(c) == 0:
                return c, x, y, h
            key = np.floor(x / cell).astype(np.int64) * (1 << 24) + np.floor(y / cell).astype(np.int64)
            o = np.lexsort((c, key))
            first = o[np.unique(key[o], return_index=True)[1]]
            return c[first], x[first], y[first], h[first]
        return f

    def search(self, keep_thresh=None, max_out=3000, count_below=None):
        """Coarse ring search + local refinement. Returns NMS'd candidates (best first) and timings.
        keep_thresh: return every 10 m-cell pose with cost < keep_thresh (no NMS/refinement; for counting).
        count_below: also count distinct places (25 m merge) whose best pose costs less than this."""
        t0 = time.perf_counter()
        p = self.p
        H = max(5, int(round(self.fov / 18)))
        rel_set = np.linspace(-0.4 * self.fov, 0.4 * self.fov, H)
        base_keep = self._keep_finite(keep_thresh) if keep_thresh else self._keep_top(p["keep_top"])
        below_keep = self._keep_finite(count_below) if count_below is not None else None
        below = []

        def keep_fn(c, x, y, h):
            if below_keep is not None:
                below.append(below_keep(c, x, y, h))
            return base_keep(c, x, y, h)
        allc, ring_info = [], []
        n_pos = 0
        self._n_eval = 0
        for count, k, ax, ay in self.anchor_items:
            it = self.items[k]
            spacing, thin = p["spacing"], False
            offs = self._ring(it, spacing)
            while count * len(offs) > p["pos_budget"] and spacing < 16:
                spacing *= 1.4
                offs = self._ring(it, spacing)
            if count * len(offs) > p["pos_budget"]:
                thin = True
                offs = self._ring(it, spacing, thin=True)
            n_pos += count * len(offs)
            ring_info.append({"positions_per_anchor": len(offs), "spacing_m": round(spacing, 1), "thinned": thin})

            def base_heads(cx, cy, qx, qy, qa, ax=ax, ay=ay):
                # bearing camera -> anchor; the anchor's offset within the FOV is added by _eval
                return np.degrees(np.arctan2(ax[qa] - qx, ay[qa] - qy))
            res = self._eval(ax, ay, offs, base_heads, -rel_set, keep_fn)
            allc.append(res)
        c, x, y, h = (np.concatenate(z) for z in zip(*allc))
        t_coarse = time.perf_counter() - t0

        # refine the best distinct poses on finer local grids
        if not keep_thresh and len(c):
            for step, dh in ((3.0, 8.0), (1.25, 3.0)):
                best = np.argsort(c, kind="stable")[:20000]
                seeds, _ = AS.greedy_cluster(x[best], y[best], p["nms"], score=-c[best])
                seeds = best[seeds[np.argsort(c[best][seeds], kind="stable")][:p["refine_top"]]]
                g = np.arange(-2, 3) * step
                offs = np.stack(np.meshgrid(g, g), -1).reshape(-1, 2)
                rh = np.arange(-2, 3) * dh
                sh = h[seeds]
                rc, rx, ry, rhh = self._eval(x[seeds], y[seeds], offs,
                                             lambda cx, cy, qx, qy, qa: sh[qa], rh,
                                             lambda *z: (keep_fn(*z), z)[1])
                c, x, y, h = (np.concatenate(z) for z in ((c, rc), (x, rx), (y, ry), (h, rhh)))
        t_refine = time.perf_counter() - t0 - t_coarse

        o = np.argsort(c, kind="stable")
        c, x, y, h = c[o], x[o], y[o], h[o]
        info = {"coarse_s": t_coarse, "refine_s": t_refine, "n_positions": n_pos, "n_evaluated": self._n_eval,
                "rings": ring_info,
                "anchor": [{"item": self.items[k]["raw"], "type": self.items[k]["type"],
                            "sub": self.items[k]["sub"], "pool": cnt} for cnt, k, _, _ in self.anchor_items]}
        t_count = 0.0
        if below_keep is not None:  # test-only bookkeeping, excluded from total_s
            tc0 = time.perf_counter()
            bx = np.concatenate([z[1] for z in below]) if below else np.zeros(0)
            by = np.concatenate([z[2] for z in below]) if below else np.zeros(0)
            bc = np.concatenate([z[0] for z in below]) if below else np.zeros(0)
            info["below"] = self.count_places(bc, bx, by)
            t_count = time.perf_counter() - tc0
            info["count_s"] = t_count
        if keep_thresh:  # raw (10 m-cell deduplicated) poses for counting
            return {"cands": {"cost": c, "x": x, "y": y, "heading": h},
                    "total_s": time.perf_counter() - t0 - t_count, **info}
        c, x, y, h = c[:60000], x[:60000], y[:60000], h[:60000]
        seeds, _ = AS.greedy_cluster(x, y, p["nms"], score=-c)
        seeds = seeds[np.argsort(c[seeds], kind="stable")][:max_out]
        cands = {"cost": c[seeds], "x": x[seeds], "y": y[seeds], "heading": h[seeds]}
        # search used anchor-centred neighbour lists (capped); re-score the head of the list around each pose
        n = min(len(seeds), p["rescore_top"])
        if n:
            nbp, nbl = self._neighbours(cands["x"][:n], cands["y"][:n], p["r_vis"] + 1.0)
            rc = self.score(cands["x"][:n], cands["y"][:n], cands["heading"][:n, None], nbp, nbl)[:, 0].numpy()
            o = np.argsort(rc, kind="stable")
            for key in ("x", "y", "heading"):
                cands[key][:n] = cands[key][:n][o]
            cands["cost"][:n] = rc[o]
        return {"cands": cands, "total_s": time.perf_counter() - t0 - t_count, **info}

    @staticmethod
    def count_places(c, x, y, merge=25.0, exact_max=1_500_000):
        """Distinct places among poses: dedupe to 10 m cells, then greedy-merge seeds closer than `merge` m.
        Above exact_max cells, fall back to counting occupied merge-size grid cells (approximate)."""
        if len(c) == 0:
            return {"n": 0, "x": np.zeros(0), "y": np.zeros(0), "method": "exact"}
        key = np.floor(x / 10).astype(np.int64) * (1 << 24) + np.floor(y / 10).astype(np.int64)
        o = np.lexsort((c, key))
        first = o[np.unique(key[o], return_index=True)[1]]
        c, x, y = c[first], x[first], y[first]
        if len(c) > exact_max:
            gk = np.floor(x / merge).astype(np.int64) * (1 << 24) + np.floor(y / merge).astype(np.int64)
            _, i = np.unique(gk, return_index=True)
            return {"n": int(len(i)), "x": x[i], "y": y[i], "method": f"grid{merge:.0f}m"}
        seeds, _ = AS.greedy_cluster(x, y, merge, score=-c)
        return {"n": int(len(seeds)), "x": x[seeds], "y": y[seeds], "method": "exact"}

    # -------------------------------------------------------------- explanation (single pose, backtracking)
    def explain(self, x, y, heading):
        """Re-score one pose with pose-centred neighbours (same float32 path as the search) and backtrack the
        alignment: returns (cost, matched list in observed order, unexpected asset IDs)."""
        p, w = self.p, self.w
        nbp, nbl = self._neighbours(np.array([x]), np.array([y]), p["r_vis"] + 1.0)
        d_s, sc_s, v_s, r_s, src = (t[0, 0].numpy() for t in self._candidates(
            np.array([x]), np.array([y]), np.array([[heading]]), nbp, nbl))
        cand = []
        for d, sc, v, r, j in zip(d_s, sc_s, v_s, r_s, src):
            if not v:
                continue
            aid = str(w.id[self.ridx[j]]) if j >= 0 else f"osm {self.lid[-j - 1]}"
            cand.append(dict(rel=float(r), dist=float(d), sc=int(sc), id=aid))
        M, K = len(cand), self.K
        cost = np.zeros((K, 0))
        if M:
            cost = torch.stack(self._pair_cost(torch.tensor([c["dist"] for c in cand], dtype=torch.float32),
                                               torch.tensor([c["sc"] for c in cand]),
                                               torch.ones(M, dtype=torch.bool))).numpy()      # [K, M]
        ex = [p["extra"] if self.extra_ok[c["sc"]] and c["dist"] <= p["r_extra"] else 0.0 for c in cand]
        E = np.zeros((K + 1, M + 1))
        E[:, 0] = np.arange(K + 1) * p["miss"]
        for j in range(1, M + 1):
            E[0, j] = E[0, j - 1] + ex[j - 1]
            for k in range(1, K + 1):
                E[k, j] = min(E[k, j - 1] + ex[j - 1], E[k - 1, j - 1] + cost[k - 1, j - 1], E[k - 1, j] + p["miss"])
        k, j, matched, extras = K, M, [], []
        while k > 0 or j > 0:
            if k > 0 and j > 0 and abs(E[k, j] - (E[k - 1, j - 1] + cost[k - 1, j - 1])) < 1e-4:
                c = cand[j - 1]
                matched.append(dict(obs=k - 1, obs_type=self.items[k - 1]["type"], obs_sub=self.items[k - 1]["sub"],
                                    asset_id=c["id"], asset_type=str(w.code_type[c["sc"]]),
                                    asset_sub=str(w.code_sub[c["sc"]]), dist_m=round(float(c["dist"]), 1),
                                    obs_dist_m=self.items[k - 1]["dist"], rel_bearing_deg=round(float(c["rel"]), 1),
                                    cost=round(float(cost[k - 1, j - 1]), 3)))
                k, j = k - 1, j - 1
            elif j > 0 and abs(E[k, j] - (E[k, j - 1] + ex[j - 1])) < 1e-4:
                if ex[j - 1] > 0:
                    extras.append(cand[j - 1]["id"])
                j -= 1
            else:
                matched.append(dict(obs=k - 1, obs_type=self.items[k - 1]["type"], asset_id=None))
                k -= 1
        return float(E[K, M]), matched[::-1], extras

    def describe(self, res, top=10):
        cands, out = res["cands"], []
        lat, lon = self.w.to_latlon(cands["x"][:top], cands["y"][:top])
        for i in range(min(top, len(cands["cost"]))):
            cost, matched, extras = self.explain(cands["x"][i], cands["y"][i], cands["heading"][i])
            out.append(dict(rank=i + 1, lat=round(float(lat[i]), 6), lon=round(float(lon[i]), 6),
                            heading_deg=round(self.w.true_heading(float(cands["heading"][i]), float(lon[i])), 1),
                            cost=round(float(cands["cost"][i]), 3), score=round(max(0.0, 1 - cost / self.K), 3),
                            matched=matched, unexpected=extras))
        return out


# ------------------------------------------------------------------ region parsing
def load_candidates(path):
    d = json.loads(Path(path).read_text())
    if isinstance(d, dict):
        d = d.get("clusters") or d.get("candidates") or d.get("top") or d.get("points") or []
    return [(float(r["lat"]), float(r["lon"])) for r in d]


def make_region(world, bbox=None, candidates=None, radius=150.0):
    if bbox:
        lat0, lon0, lat1, lon1 = bbox
        x0, y0, x1, y1 = AS.bbox_to_xy((lat0, lon0, lat1, lon1))
        return {"bbox": (x0 - world.ox, y0 - world.oy, x1 - world.ox, y1 - world.oy)}
    if candidates:
        x, y = world.to_xy([c[0] for c in candidates], [c[1] for c in candidates])
        return {"points": (np.asarray(x), np.asarray(y)), "radius": radius}
    return None


# ------------------------------------------------------------------ tests
def sample_observation(world, rng, fov=90.0, rmax=30.0, kmax=4, kmin=2, perturb=0.4, drop_p=0.5, exact_k=None):
    """Random sidewalk camera + the observed list it would produce (from the asset table)."""
    segs = world.sidewalk_segs
    seglen = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    cum = np.cumsum(seglen) / seglen.sum()
    tries = 0
    while True:
        tries += 1
        s = segs[min(np.searchsorted(cum, rng.random()), len(segs) - 1)]
        t = rng.random()
        x, y = s[0] + t * (s[2] - s[0]), s[1] + t * (s[3] - s[1])
        heading = rng.random() * 360
        _, pi, d = world.grid_all.query_pairs(np.array([x]), np.array([y]), rmax)
        rel = (np.degrees(np.arctan2(world.x[pi] - x, world.y[pi] - y)) - heading + 180) % 360 - 180
        v = np.abs(rel) <= fov / 2
        pi, d, rel = pi[v], d[v], rel[v]
        need = exact_k or kmin
        if len(pi) < need:
            continue
        o = np.argsort(d)[:exact_k or kmax]
        pi, d, rel = pi[o], d[o], rel[o]
        o = np.argsort(rel)
        pi, d, rel = pi[o], d[o], rel[o]
        assets = []
        for j, (i, dd) in enumerate(zip(pi, d)):
            t_, s_ = world.type[i], world.sub[i]
            a = {"type": t_, "order": j + 1, "approx_distance_m": round(float(dd * rng.uniform(1 - perturb,
                                                                                               1 + perturb)), 1)}
            if t_ == "pole":
                a["subtype"] = OBS_POLE_SUBTYPE.get(s_, s_)
            a["_truth"] = {"id": str(world.id[i]), "dist": round(float(dd), 1), "rel": round(float(rel[j]), 1)}
            assets.append(a)
        if not exact_k and len(assets) >= 2 and rng.random() < drop_p:
            assets.pop(int(rng.integers(len(assets))))
            for j, a in enumerate(assets):
                a["order"] = j + 1
        return {"fov_deg": fov, "assets": assets}, (x, y, heading), tries


def rank_of_truth(res, tx, ty, radius):
    c = res["cands"]
    d = np.hypot(c["x"] - tx, c["y"] - ty)
    hit = np.nonzero(d <= radius)[0]
    return int(hit[0]) + 1 if len(hit) else None


def summarize_ranks(ranks, n_cap):
    arr = np.array([r if r is not None else np.inf for r in ranks], float)
    med = float(np.median(arr))
    return {"median": med if np.isfinite(med) else f">{n_cap}", "found": int(np.isfinite(arr).sum()),
            "top1": int((arr == 1).sum()), "top5": int((arr <= 5).sum()), "top20": int((arr <= 20).sum())}


def run_tests(args):
    rng = np.random.default_rng(args.seed)
    world = World()
    print(f"world loaded in {world.load_s:.1f}s: {len(world.x)} point assets, "
          f"{len(world.lines['tram'][0])} tram points, {len(world.sidewalk_segs)} sidewalk segments")
    report = {"world_load_s": round(world.load_s, 1), "seed": args.seed, "params": params()}
    sections = set(args.sections.split(","))
    prev_path = RESULTS / "asset_tests.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else {}  # reuse sections not re-run

    # 1. synthetic recovery
    if "synth" not in sections:
        report["synthetic"] = prev.get("synthetic")
    else:
        trials = []
        for t in range(args.n_synth):
            obs, (tx, ty, th), tries = sample_observation(world, rng)
            clean = {"fov_deg": obs["fov_deg"], "assets": [{k: v for k, v in a.items() if k != "_truth"}
                                                           for a in obs["assets"]]}
            m = Matcher(world, clean, threads=args.threads)
            nbp, nbl = m._neighbours(np.array([tx]), np.array([ty]), m.p["r_vis"] + 1)
            tc = float(m.score(np.array([tx]), np.array([ty]), np.array([[th]]), nbp, nbl)[0, 0])  # true pose cost
            res = m.search(count_below=tc + 1e-3)
            r10, r25 = rank_of_truth(res, tx, ty, 10), rank_of_truth(res, tx, ty, 25)
            c = res["cands"]
            top = {"dist_m": round(float(np.hypot(c["x"][0] - tx, c["y"][0] - ty)), 1),
                   "cost": round(float(c["cost"][0]), 3)} if len(c["cost"]) else None
            b = res["below"]
            better = int((np.hypot(b["x"] - tx, b["y"] - ty) > 25).sum())  # look-alike places scoring <= truth
            hdg_err = None
            if r25:
                dh = abs((c["heading"][r25 - 1] - th + 180) % 360 - 180)
                hdg_err = round(float(dh), 1)
            lat, lon = world.to_latlon(tx, ty)
            rec = {"trial": t, "true": {"lat": round(float(lat), 6), "lon": round(float(lon), 6),
                                        "heading": round(float(th), 1)},
                   "pattern": [(a["type"] + ("/" + a["subtype"] if a.get("subtype") else ""), a["approx_distance_m"],
                                a["_truth"]["dist"]) for a in obs["assets"]],
                   "K": len(obs["assets"]), "anchor": res["anchor"][0]["type"] + (
                       "/" + res["anchor"][0]["sub"] if res["anchor"][0]["sub"] else ""),
                   "anchor_pool": res["anchor"][0]["pool"], "rank_10m": r10, "rank_25m": r25,
                   "top1": top, "truth_cost": round(tc, 3), "n_candidates": len(c["cost"]),
                   "places_scoring_at_least_as_well_as_truth": better, "count_method": b["method"],
                   "heading_err_deg": hdg_err, "runtime_s": round(res["total_s"], 2),
                   "n_positions": int(res["n_positions"]), "n_evaluated": int(res["n_evaluated"]),
                   "sampling_tries": tries}
            trials.append(rec)
            print(f"[synth {t:2d}] K={rec['K']} {[p[0] for p in rec['pattern']]} anchor={rec['anchor']}"
                  f"({rec['anchor_pool']}) rank10={r10} rank25={r25} top1={top} truth_cost={tc:.2f} "
                  f"better_places={better} t={res['total_s']:.1f}s", flush=True)
        n = len(trials)
        r10 = [t["rank_10m"] for t in trials]
        r25 = [t["rank_25m"] for t in trials]
        report["synthetic"] = {
            "n": n, "fov_deg": 90, "visible_radius_m": 30, "max_assets": 4, "distance_noise": "+-40% uniform",
            "drop": "one asset dropped with p=0.5", "camera": "random point on OSM footway=sidewalk, random heading",
            "top1_within_10m": sum(1 for r in r10 if r == 1), "top1_within_25m": sum(1 for r in r25 if r == 1),
            "rank_10m": summarize_ranks(r10, 3000), "rank_25m": summarize_ranks(r25, 3000),
            "estimated_rank_median": float(np.median([t["places_scoring_at_least_as_well_as_truth"] + 1
                                                      for t in trials])),
            "median_runtime_s": round(float(np.median([t["runtime_s"] for t in trials])), 2),
            "max_runtime_s": round(float(np.max([t["runtime_s"] for t in trials])), 2),
            "K_distribution": {str(k): sum(1 for t in trials if t["K"] == k) for k in range(1, 5)},
            "trials": trials}
        by_k = {}
        for t in trials:
            by_k.setdefault(t["K"], []).append(t)
        report["synthetic"]["by_K"] = {str(k): {"n": len(v), "top1_10m": sum(1 for t in v if t["rank_10m"] == 1),
                                                "top1_25m": sum(1 for t in v if t["rank_25m"] == 1),
                                                "median_rank_25m": summarize_ranks([t["rank_25m"] for t in v],
                                                                                   3000)["median"]}
                                       for k, v in sorted(by_k.items())}
        for k, v in report["synthetic"]["by_K"].items():
            v["estimated_rank_median"] = float(np.median([t["places_scoring_at_least_as_well_as_truth"] + 1
                                                          for t in by_k[int(k)]]))
        save(report)

    # 2. uniqueness: distinct consistent camera positions citywide and within 200 m
    if "unique" not in sections:
        report["uniqueness"] = prev.get("uniqueness")
    else:
        rng = np.random.default_rng(args.seed + 1)
        uniq = {}
        for K in (2, 3, 4):
            rows = []
            for t in range(args.n_unique):
                obs, (tx, ty, th), _ = sample_observation(world, rng, exact_k=K)
                clean = {"fov_deg": 90, "assets": [{k: v for k, v in a.items() if k != "_truth"} for a in obs["assets"]]}
                m = Matcher(world, clean, p=strict_params(), threads=args.threads)
                res = m.search(keep_thresh=50.0)
                c = res["cands"]
                pl = m.count_places(c["cost"], c["x"], c["y"])
                d = np.hypot(pl["x"] - tx, pl["y"] - ty)
                rows.append({"pattern": [a["type"] + ("/" + a["subtype"] if a.get("subtype") else "")
                                         for a in obs["assets"]], "count_method": pl["method"],
                             "n_city": int(pl["n"]), "n_200m": int((d <= 200).sum()),
                             "truth_found": bool((d <= 25).any()), "runtime_s": round(res["total_s"], 2)})
                print(f"[unique K={K} {t:2d}] {rows[-1]['pattern']} city={rows[-1]['n_city']} 200m={rows[-1]['n_200m']} "
                      f"truth_found={rows[-1]['truth_found']} t={res['total_s']:.1f}s", flush=True)
            nc = np.array([r["n_city"] for r in rows])
            n2 = np.array([r["n_200m"] for r in rows])
            uniq[str(K)] = {"n": len(rows), "city_median": float(np.median(nc)),
                            "city_p25_p75": [float(np.percentile(nc, 25)), float(np.percentile(nc, 75))],
                            "city_min_max": [int(nc.min()), int(nc.max())],
                            "r200_median": float(np.median(n2)), "r200_min_max": [int(n2.min()), int(n2.max())],
                            "share_unique_city": round(float(np.mean(nc <= 1)), 2),
                            "share_unique_200m": round(float(np.mean(n2 <= 1)), 2),
                            "truth_found": int(sum(r["truth_found"] for r in rows)), "rows": rows}
        report["uniqueness"] = {
            "definition": "distinct camera positions (greedy-merged at 25 m) where some heading sees assets matching "
                          "all K observed types/subtypes in the same left-to-right order, each within x/÷1.7 of the "
                          "observed distance (strict mode, 90 deg FOV, 40 m visibility); patterns are the K nearest "
                          "assets seen from a random sidewalk camera, distances +-40%",
            "by_K": uniq}
        save(report)

    # 3. real photo test2.png
    if "photo" not in sections:
        report["photo_test2"] = prev.get("photo_test2")
    else:
        photo_obs = {"fov_deg": 100, "source": "local VLM (qwen3-vl-8b) description of images/test2.png, unverified",
                     "assets": [{"type": "wooden utility pole", "subtype": "hydro", "order": 1, "approx_distance_m": 10},
                                {"type": "streetlight", "subtype": "street_light", "order": 2, "approx_distance_m": 15},
                                {"type": "tram", "order": 3, "approx_distance_m": None}]}
        cands = load_candidates(RESULTS / "osm_local_railway-tram__amenity-parking.json")
        photo = {"observation": photo_obs}
        for name, region in (("citywide", None), ("near_56_tram_parking_areas_150m", make_region(world, candidates=cands,
                                                                                                radius=150.0))):
            m = Matcher(world, photo_obs, region=region, n_anchors=2, threads=args.threads)
            res = m.search()
            top = m.describe(res, 5)
            photo[name] = {"anchors": res["anchor"], "runtime_s": round(res["total_s"], 2),
                           "n_candidates": len(res["cands"]["cost"]),
                           "n_cost_below_0.5": int((res["cands"]["cost"] < 0.5).sum()), "top5": top}
            if region:
                cx, cy = region["points"]
                for r in top:
                    x, y = world.to_xy(r["lat"], r["lon"])
                    j = int(np.argmin(np.hypot(cx - x, cy - y)))
                    r["nearest_area"] = {"index": j + 1, "dist_m": round(float(np.hypot(cx[j] - x, cy[j] - y)), 0)}
            print(f"[photo {name}] {res['total_s']:.1f}s, {len(res['cands']['cost'])} candidates, "
                  f"{photo[name]['n_cost_below_0.5']} with cost < 0.5")
            for r in top:
                print(f"   {r['rank']}. {r['lat']:.6f},{r['lon']:.6f} hdg {r['heading_deg']:5.1f} cost {r['cost']:.3f} "
                      f"{[(mm['asset_id'], mm.get('dist_m')) for mm in r['matched']]}")
        report["photo_test2"] = photo
        save(report)
    write_md(report)


def save(report):
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "asset_tests.json").write_text(json.dumps(report, indent=1, default=str))


def write_md(rep):
    s = rep["synthetic"]
    L = ["# Asset-pattern matcher tests", "",
         f"Generated by `asset_pattern.py --run-tests` (seed {rep['seed']}). Full data: `asset_tests.json`.", "",
         "## 1. Synthetic recovery (citywide search)", "",
         f"{s['n']} random sidewalk cameras (OSM footway=sidewalk), random heading, 90 deg FOV. Observed list = "
         "up to 4 nearest City assets in the FOV within 30 m, distances x U(0.6, 1.4), one asset dropped with "
         f"p = 0.5. K distribution: {s['K_distribution']}.", "",
         "| metric | value |", "|---|---|",
         f"| top-1 within 10 m | {s['top1_within_10m']}/{s['n']} |",
         f"| top-1 within 25 m | {s['top1_within_25m']}/{s['n']} |",
         f"| median rank of truth (10 m) | {s['rank_10m']['median']} (found in list: {s['rank_10m']['found']}/{s['n']}) |",
         f"| median rank of truth (25 m) | {s['rank_25m']['median']} (found in list: {s['rank_25m']['found']}/{s['n']}) |",
         f"| truth in top-5 / top-20 (25 m) | {s['rank_25m']['top5']} / {s['rank_25m']['top20']} |",
         f"| median / max runtime | {s['median_runtime_s']} s / {s['max_runtime_s']} s |", "",
         "By number of observed assets K:", "", "| K | n | top-1 10 m | top-1 25 m | median rank (25 m) |",
         "|---|---|---|---|---|"]
    for k, v in s["by_K"].items():
        L.append(f"| {k} | {v['n']} | {v['top1_10m']} | {v['top1_25m']} | {v['median_rank_25m']} |")
    u = rep["uniqueness"]
    L += ["", "## 2. Uniqueness of asset patterns", "", u["definition"] + ".", "",
          "| K | n patterns | median distinct places citywide (IQR) | min..max | median within 200 m | "
          "unique citywide | unique within 200 m | truth recovered |", "|---|---|---|---|---|---|---|---|"]
    for k, v in u["by_K"].items():
        L.append(f"| {k} | {v['n']} | {v['city_median']:.0f} ({v['city_p25_p75'][0]:.0f}-{v['city_p25_p75'][1]:.0f})"
                 f" | {v['city_min_max'][0]}..{v['city_min_max'][1]} | {v['r200_median']:.0f} | "
                 f"{v['share_unique_city']:.0%} | {v['share_unique_200m']:.0%} | {v['truth_found']}/{v['n']} |")
    ph = rep["photo_test2"]
    L += ["", "## 3. Real photo images/test2.png", "",
          "Observation (local VLM, unverified): " + "; ".join(
              f"{a['order']}. {a['type']}" + (f" ~{a['approx_distance_m']} m" if a.get("approx_distance_m")
                                                else " (no distance)") for a in ph["observation"]["assets"])
          + f"; FOV assumed {ph['observation']['fov_deg']} deg. True location unknown.", ""]
    for name in ("citywide", "near_56_tram_parking_areas_150m"):
        r = ph[name]
        L += [f"### {name}", "", f"Anchors: " + ", ".join(f"{a['type']}/{a['sub']} (pool {a['pool']})"
                                                          for a in r["anchors"])
              + f"; runtime {r['runtime_s']} s; {r['n_candidates']} distinct candidates, "
              f"{r['n_cost_below_0.5']} with cost < 0.5.", "",
              "| rank | lat, lon | heading | cost | matched |", "|---|---|---|---|---|"]
        for c in r["top5"]:
            mt = ", ".join(f"{m['asset_id']} ({m['dist_m']} m)" if m.get("asset_id") else f"{m['obs_type']}: none"
                           for m in c["matched"])
            L.append(f"| {c['rank']} | {c['lat']}, {c['lon']} | {c['heading_deg']} | {c['cost']} | {mt} |")
        L.append("")
    uk = u["by_K"]
    n_city = ph["citywide"]["n_cost_below_0.5"]
    n_area = ph["near_56_tram_parking_areas_150m"]["n_cost_below_0.5"]
    L += ["## Findings", "",
          f"- An asset pattern alone does not pin a location citywide. In the synthetic test the true camera was "
          f"never top-1 ({s['top1_within_25m']}/{s['n']} within 25 m); the median number of distinct places scoring "
          f"at least as well as the true pose was {s['estimated_rank_median']:.0f}. Random sidewalk views mostly see "
          f"1-2 common assets (K=1: {s['K_distribution'].get('1', 0)}, K=2: {s['K_distribution'].get('2', 0)} of "
          f"{s['n']}).",
          f"- Uniqueness: none of the {sum(v['n'] for v in uk.values())} test patterns was unique citywide. Median "
          f"consistent places: K=2 {uk['2']['city_median']:.0f}, K=3 {uk['3']['city_median']:.0f}, K=4 "
          f"{uk['4']['city_median']:.0f}. Within 200 m of the truth the medians drop to {uk['2']['r200_median']:.0f}, "
          f"{uk['3']['r200_median']:.0f} and {uk['4']['r200_median']:.1f}, and the pattern is unique within 200 m in "
          f"{uk['2']['share_unique_200m']:.0%} (K=2) / {uk['3']['share_unique_200m']:.0%} (K=3) / "
          f"{uk['4']['share_unique_200m']:.0%} (K=4) of cases. Use the matcher as a local verifier/refiner after "
          "another tool (VPR, OCR, street names) narrows the area to a few hundred metres, not as a citywide locator.",
          "- K=4 patterns can only be drawn where 4+ assets are within 30 m (dense, downtown-like streets with many "
          "look-alikes), which is why K=4 is not much more unique than K=3 citywide.",
          f"- Strict-mode counts are lower bounds: the coarse pose grid missed the truth's own consistent region in "
          f"{uk['3']['n'] - uk['3']['truth_found']}/{uk['3']['n']} (K=3) and {uk['4']['n'] - uk['4']['truth_found']}/"
          f"{uk['4']['n']} (K=4) patterns.",
          f"- test2.png: two poles at ~10/15 m plus a streetcar track on the right fits well (cost < 0.5) at "
          f"{n_city} of the {ph['citywide']['n_candidates']} retained distinct places citywide and {n_area} within "
          "150 m of the 56 tram+parking areas, so this observation carries almost no location information; the "
          "top-5 lists are arbitrary among equals.",
          ""]
    (RESULTS / "asset_tests.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Asset-pattern camera-pose matcher")
    ap.add_argument("obs", nargs="?", help="observation JSON file")
    ap.add_argument("--bbox", help="min_lat,min_lon,max_lat,max_lon")
    ap.add_argument("--candidates", help="JSON with lat/lon points (list, or {'clusters': [...]})")
    ap.add_argument("--radius", type=float, default=150.0, help="metres around each candidate point")
    ap.add_argument("--fov", type=float, help="override fov_deg from the observation")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--anchors", type=int, default=2, help="anchor on up to this many rarest observed types")
    ap.add_argument("--threads", type=int, default=8, help="torch CPU threads")
    ap.add_argument("--out", help="output JSON (default results/asset_pattern_<obs>.json)")
    ap.add_argument("--run-tests", action="store_true", help="run synthetic/uniqueness/photo tests")
    ap.add_argument("--n-synth", type=int, default=30)
    ap.add_argument("--n-unique", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sections", default="synth,unique,photo", help="test sections to (re)run; others are "
                    "taken from the existing results/asset_tests.json")
    args = ap.parse_args()
    if args.run_tests:
        return run_tests(args)
    if not args.obs:
        ap.error("give an observation JSON or --run-tests")
    obs = json.loads(Path(args.obs).read_text())
    if args.fov:
        obs["fov_deg"] = args.fov
    world = World()
    bbox = [float(v) for v in args.bbox.split(",")] if args.bbox else None
    cands = load_candidates(args.candidates) if args.candidates else None
    m = Matcher(world, obs, region=make_region(world, bbox, cands, args.radius), n_anchors=args.anchors,
                threads=args.threads)
    res = m.search()
    top = m.describe(res, args.top)
    print(f"world load {world.load_s:.1f}s; anchors: " + ", ".join(f"{a['type']}/{a['sub']} x{a['pool']}"
                                                                  for a in res["anchor"])
          + f"; {res['n_positions']} ring positions; search {res['total_s']:.1f}s "
          f"(coarse {res['coarse_s']:.1f}s, refine {res['refine_s']:.1f}s); {len(res['cands']['cost'])} candidates")
    if m.ignored:
        print(f"ignored observed items: {m.ignored}")
    for r in top:
        print(f"{r['rank']:3d}. {r['lat']:.6f}, {r['lon']:.6f}  heading {r['heading_deg']:5.1f}  cost {r['cost']:.3f}"
              f"  score {r['score']:.2f}  " + ", ".join(
                  f"{mm['asset_id']}@{mm['dist_m']}m" if mm.get("asset_id") else f"[{mm['obs_type']} missing]"
                  for mm in r["matched"]) + (f"  unexpected {r['unexpected']}" if r["unexpected"] else ""))
    out = Path(args.out) if args.out else RESULTS / f"asset_pattern_{Path(args.obs).stem}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"obs": obs, "args": vars(args), "anchors": res["anchor"],
                               "timing_s": {"world": round(world.load_s, 2), "search": round(res["total_s"], 2)},
                               "top": top}, indent=1, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
