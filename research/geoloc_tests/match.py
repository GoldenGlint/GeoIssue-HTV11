"""Rank candidate locations for a query photo by image retrieval (MegaLoc) + local-feature
verification (ALIKED + LightGlue + MAGSAC), against references from mapillary_harvest.py.

References
  * perspective images: as they are (one view, or three ~4:3 crops if wider than 4:3);
  * 360 panoramas (method "persp", default): 8 gravity-levelled perspective views each
    (FOV 90, yaw every 45 deg, pitch 0, see pano.py), each with its absolute compass heading;
    method "strips" is the old behaviour (4 flat 135-deg strips of the horizon band).
Descriptors are cached per reference folder in <root>/megaloc_<method>.pt (invalidated when the
image list or any file size changes).  JPEG decoding + reprojection run in a thread pool so the
GPU is the critical path.  Verification uses the matched perspective view of a pano (640x480),
not the whole equirect.

Usage:
  .venv/Scripts/python match.py --query images/test2.png
  .venv/Scripts/python match.py --query images/test1_utsc.png --refs data/mly data/mly_utsc \
      --truth 43.78584,-79.18728
  .venv/Scripts/python match.py --query q.jpg --exclude-ids 123,456 --exclude-radius-m 5
  .venv/Scripts/python match.py --eval-pseudo 40          # held-out Mapillary pseudo-queries, both methods
"""
import argparse
import json
import math
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from lightglue import ALIKED, LightGlue
from lightglue.utils import rbd

from pano import absolute_heading, level_rotation, perspective

HERE = Path(__file__).parent
RESULTS = HERE / "results"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
EMB_W, EMB_H = 434, 322           # MegaLoc input size (multiples of its 14-px patch)
PANO_YAWS = tuple(range(0, 360, 45))
PANO_FOV = 90.0
VERIFY_W, VERIFY_H = 640, 480     # pano view handed to LightGlue (2048-px equirect ~ 5.7 px/deg)
LG_MAX_SIDE = 1024
CACHE_VERSION = {"persp": "persp8-levelled-fov90-434x322-v1", "strips": "strips4-135deg-434x322-v1"}
ACCEPT_INLIERS = 75               # top-1 accept threshold from the pseudo-query validation


# ----------------------------------------------------------------------------------------------
# references
# ----------------------------------------------------------------------------------------------

def load_refs(roots):
    """All references under the given folders, de-duplicated by image id (first folder wins)."""
    refs, by_id = [], {}
    for root in roots:
        for r in json.loads((root / "index.json").read_text()):
            path = root / r["area"] / f"{r['id']}.jpg"
            if r["id"] in by_id:
                if r["area"] not in by_id[r["id"]]["areas"]:
                    by_id[r["id"]]["areas"].append(r["area"])
                continue
            if not path.exists():
                continue
            r = {**r, "path": str(path), "root": str(root), "areas": [r["area"]]}
            by_id[r["id"]] = r
            refs.append(r)
    return refs


def load_rgb(path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def flat_crops(img):
    """Wide perspective images -> 3 overlapping ~4:3 crops (compare like-for-like with phone frames)."""
    h, w = img.shape[:2]
    cw = min(w, int(h * 4 / 3))
    if cw >= w * 0.9:
        return [img]
    return [img[:, x:x + cw] for x in np.linspace(0, w - cw, 3).astype(int)]


def pano_strips(img):
    """OLD method: horizon band of the equirect, 4 flat crops of ~135 deg; returns (crop, yaw)."""
    h, w = img.shape[:2]
    band = img[h // 5: h - h // 5]
    cw = int(w * 135 / 360)
    return [(band[:, x:x + cw], (x + cw / 2) / w * 360 - 180) for x in np.linspace(0, w - cw, 4).astype(int)]


def to_emb(img):
    return cv2.resize(img, (EMB_W, EMB_H), interpolation=cv2.INTER_AREA)


def ref_views(r, method):
    """[(uint8 EMB_HxEMB_Wx3 RGB view, yaw_deg or nan)] for one reference (runs in worker threads)."""
    img = load_rgb(r["path"])
    if r["is_pano"]:
        if method == "persp":
            level = level_rotation(r)
            return [(perspective(img, yaw, 0, PANO_FOV, EMB_W, EMB_H, level=level)[0], float(yaw))
                    for yaw in PANO_YAWS]
        return [(to_emb(c), float(y)) for c, y in pano_strips(img)]
    return [(to_emb(c), float("nan")) for c in flat_crops(img)]


def view_heading(r, yaw, method="persp"):
    if not r["is_pano"] or yaw is None or math.isnan(yaw):
        return None if r.get("heading") is None else round(r["heading"], 1)
    return round(absolute_heading(r, yaw, leveled=(method == "persp")), 1)


def prefetch(items, fn, workers, ahead=64):
    """Ordered map with a bounded number of results in flight (keeps RAM flat)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        it = iter(items)
        queue = deque(pool.submit(fn, x) for x in islice(it, ahead))
        while queue:
            fut = queue.popleft()
            for x in islice(it, 1):
                queue.append(pool.submit(fn, x))
            yield fut.result()


class Embedder:
    def __init__(self):
        self.model = torch.hub.load("gmberton/MegaLoc", "get_trained_model", trust_repo=True,
                                    verbose=False).eval().to(DEVICE)
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=DEVICE).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225], device=DEVICE).view(1, 3, 1, 1)

    @torch.inference_mode()
    def __call__(self, arrays):
        """list of uint8 EMB_HxEMB_Wx3 RGB arrays -> L2-normalised fp16 descriptors on DEVICE."""
        x = torch.from_numpy(np.stack(arrays)).to(DEVICE, non_blocking=True)
        x = (x.permute(0, 3, 1, 2).float() / 255 - self.mean) / self.std
        with torch.autocast(DEVICE, dtype=torch.float16, enabled=DEVICE == "cuda"):
            d = self.model(x)
        return F.normalize(d.float(), dim=-1).half()


def build_root(emb, refs, method, workers, batch):
    """Embed every view of `refs` (one folder).  Returns cpu tensors + timing breakdown."""
    descs, owner, yaws, buf = [], [], [], []
    t0, t_gpu, t_wait = time.perf_counter(), 0.0, 0.0
    cv2.setNumThreads(1)  # parallelism comes from the thread pool
    views_iter = prefetch(refs, lambda r: ref_views(r, method), workers)

    def flush():
        nonlocal t_gpu
        t = time.perf_counter()
        descs.append(emb(buf).cpu())
        t_gpu += time.perf_counter() - t
        buf.clear()

    for i in range(len(refs)):
        t = time.perf_counter()
        views = next(views_iter)
        t_wait += time.perf_counter() - t
        for arr, yaw in views:
            buf.append(arr)
            owner.append(i)
            yaws.append(yaw)
            if len(buf) == batch:
                flush()
        if (i + 1) % 1000 == 0:
            print(f"    {i + 1}/{len(refs)} refs, {len(owner)} views, {time.perf_counter() - t0:.0f}s")
    if buf:
        flush()
    cv2.setNumThreads(-1)
    total = time.perf_counter() - t0
    return (torch.cat(descs), torch.tensor(owner, dtype=torch.int32), torch.tensor(yaws, dtype=torch.float32),
            {"build_s": round(total, 1), "gpu_embed_s": round(t_gpu, 1), "waiting_for_decode_s": round(t_wait, 1),
             "views": len(owner), "refs": len(refs), "views_per_s": round(len(owner) / total, 1)})


def build_index(emb, refs, method, workers=12, batch=32, rebuild=False):
    """Per-folder cached descriptors, concatenated.  Returns dict with GPU tensors + stats."""
    descs, owners, yaws, stats = [], [], [], []
    by_root = defaultdict(list)
    for i, r in enumerate(refs):
        by_root[r["root"]].append(i)
    for root, idxs in by_root.items():
        sub = [refs[i] for i in idxs]
        key = [(r["id"], Path(r["path"]).stat().st_size) for r in sub]
        cache = Path(root) / f"megaloc_{method}.pt"
        saved = torch.load(cache, weights_only=False) if cache.exists() and not rebuild else None
        if saved and saved.get("version") == CACHE_VERSION[method] and saved.get("key") == key:
            d, o, y, st = saved["desc"], saved["owner"], saved["yaw"], {**saved["stats"], "cached": True}
        else:
            print(f"  building {method} index for {root} ({len(sub)} refs)...")
            d, o, y, st = build_root(emb, sub, method, workers, batch)
            torch.save({"version": CACHE_VERSION[method], "key": key, "desc": d, "owner": o, "yaw": y,
                        "stats": st}, cache)
            st = {**st, "cached": False}
        descs.append(d)
        owners.append(torch.tensor(idxs, dtype=torch.long)[o.long()])
        yaws.append(y)
        stats.append({"root": str(root), **st})
    return {"method": method, "refs": refs, "desc": torch.cat(descs).to(DEVICE),
            "owner": torch.cat(owners).to(DEVICE), "yaw": torch.cat(yaws).numpy(), "stats": stats}


# ----------------------------------------------------------------------------------------------
# query: retrieval + verification
# ----------------------------------------------------------------------------------------------

def dist_m(lat1, lon1, lat2, lon2):
    return math.hypot((lat1 - lat2) * 111320, (lon1 - lon2) * 111320 * math.cos(math.radians(lat1)))


def exclusion_mask(refs, ids=(), radius_m=0.0, centres=()):
    """True for refs to drop: the given ids, and anything within radius_m of those ids' locations
    (or of explicit (lat, lon) centres)."""
    ids = set(ids)
    pts = list(centres) + [(r["lat"], r["lon"]) for r in refs if r["id"] in ids]
    mask = np.array([r["id"] in ids for r in refs])
    if radius_m > 0 and pts:
        lat = np.array([r["lat"] for r in refs])
        lon = np.array([r["lon"] for r in refs])
        for la, lo in pts:
            d = np.hypot((lat - la) * 111320, (lon - lo) * 111320 * math.cos(math.radians(la)))
            mask |= d <= radius_m
    return mask


def retrieve(index, q_desc, top, ref_mask=None):
    """Top `top` references by best (query view x reference view) cosine similarity."""
    sim = (q_desc @ index["desc"].T).float()                 # (query views, ref views)
    best, best_q = sim.max(0)
    if ref_mask is not None and ref_mask.any():
        best[torch.from_numpy(ref_mask).to(DEVICE)[index["owner"]]] = -9.0
    order = torch.argsort(best, descending=True).cpu().numpy()
    owner = index["owner"].cpu().numpy()
    best, best_q = best.cpu().numpy(), best_q.cpu().numpy()
    out, seen = [], set()
    for v in order:
        i = int(owner[v])
        if i in seen or best[v] <= -9:
            continue
        seen.add(i)
        out.append({"ref": i, "view": int(v), "sim": float(best[v]), "query_view": int(best_q[v])})
        if len(out) == top:
            break
    return out


def resize_max(img, side=LG_MAX_SIDE):
    h, w = img.shape[:2]
    s = side / max(h, w)
    return img if s >= 1 else cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


class Verifier:
    def __init__(self):
        self.extractor = ALIKED(max_num_keypoints=2048).eval().to(DEVICE)
        self.matcher = LightGlue(features="aliked").eval().to(DEVICE)

    @torch.inference_mode()
    def feats(self, rgb):
        t = torch.from_numpy(np.ascontiguousarray(rgb)).to(DEVICE).permute(2, 0, 1).float() / 255
        return self.extractor.extract(t)

    @torch.inference_mode()
    def match(self, f0, f1):
        m = rbd(self.matcher({"image0": f0, "image1": f1}))["matches"].cpu().numpy()
        if len(m) < 8:
            return 0, len(m), None, None
        p0 = rbd(f0)["keypoints"].cpu().numpy()[m[:, 0]]
        p1 = rbd(f1)["keypoints"].cpu().numpy()[m[:, 1]]
        _, mask = cv2.findFundamentalMat(p0, p1, cv2.USAC_MAGSAC, 2.0, 0.999, 10000)
        if mask is None:
            return 0, len(m), None, None
        keep = mask.ravel().astype(bool)
        return int(keep.sum()), len(m), p0[keep], p1[keep]


def ref_verify_image(r, yaw, method):
    """The image LightGlue sees for a reference: the matched levelled pano view (method persp),
    the whole pano (method strips, old behaviour) or the perspective photo itself."""
    img = load_rgb(r["path"])
    if r["is_pano"] and method == "persp":
        return perspective(img, yaw, 0, PANO_FOV, VERIFY_W, VERIFY_H, level=level_rotation(r))[0]
    return resize_max(img)


def draw_pair(q_img, r_img, p0, p1, path, title=""):
    h = max(q_img.shape[0], r_img.shape[0])
    canvas = np.zeros((h + 28, q_img.shape[1] + r_img.shape[1], 3), np.uint8)
    canvas[28:28 + q_img.shape[0], :q_img.shape[1]] = q_img
    canvas[28:28 + r_img.shape[0], q_img.shape[1]:] = r_img
    if p0 is not None:
        for (x0, y0), (x1, y1) in zip(p0[:300], p1[:300]):
            cv2.line(canvas, (int(x0), int(y0) + 28), (int(x1) + q_img.shape[1], int(y1) + 28), (0, 255, 0), 1,
                     cv2.LINE_AA)
    cv2.putText(canvas, title, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])


def verify(verifier, index, q_crops, hits):
    """LightGlue-verify retrieval hits.  Query-crop features are extracted once per crop."""
    method, refs = index["method"], index["refs"]
    q_imgs = [resize_max(c) for c in q_crops]
    q_feats = {}
    out = []
    prefetched = prefetch(hits, lambda h: ref_verify_image(refs[h["ref"]], index["yaw"][h["view"]], method), 4, 8)
    for rank, (h, r_img) in enumerate(zip(hits, prefetched), 1):
        r = refs[h["ref"]]
        qv = h["query_view"]
        if qv not in q_feats:
            q_feats[qv] = verifier.feats(q_imgs[qv])
        inl, n, p0, p1 = verifier.match(q_feats[qv], verifier.feats(r_img))
        yaw = float(index["yaw"][h["view"]])
        out.append({"id": r["id"], "area": r["area"], "areas": r["areas"], "lat": r["lat"], "lon": r["lon"],
                    "is_pano": r["is_pano"], "captured_at": r["captured_at"], "sequence": r.get("sequence"),
                    "retrieval_rank": rank, "megaloc_sim": round(h["sim"], 4),
                    "view_yaw": None if math.isnan(yaw) else yaw, "view_heading": view_heading(r, yaw, method),
                    "query_view": qv, "matches": n, "inliers": inl,
                    "_vis": (q_imgs[qv], r_img, p0, p1)})
    out.sort(key=lambda x: (-x["inliers"], -x["megaloc_sim"]))
    return out


def estimate(results, cluster_m=100.0, min_frac=0.2):
    """Inlier-weighted location of the best area.  Best area = the area of the top-inlier result
    (ties broken by summed inliers); members = its results within cluster_m of that top result
    with >= min_frac of its inliers.  Spread = inlier-weighted RMS distance to the estimate."""
    if not results or results[0]["inliers"] == 0:
        return None
    by_area = defaultdict(list)
    for r in results:
        by_area[r["area"]].append(r)
    best_area = max(by_area, key=lambda a: (max(x["inliers"] for x in by_area[a]),
                                            sum(x["inliers"] for x in by_area[a])))
    top = max(by_area[best_area], key=lambda x: x["inliers"])
    members = [x for x in by_area[best_area] if x["inliers"] >= min_frac * top["inliers"]
               and dist_m(top["lat"], top["lon"], x["lat"], x["lon"]) <= cluster_m]
    w = np.array([x["inliers"] for x in members], float)
    lat = float(np.average([x["lat"] for x in members], weights=w))
    lon = float(np.average([x["lon"] for x in members], weights=w))
    d = np.array([dist_m(lat, lon, x["lat"], x["lon"]) for x in members])
    return {"area": best_area, "lat": round(lat, 7), "lon": round(lon, 7), "n_members": len(members),
            "inliers_total": int(w.sum()), "best_inliers": int(top["inliers"]),
            "spread_m": round(float(np.sqrt(np.average(d ** 2, weights=w))), 1),
            "max_dist_m": round(float(d.max()), 1),
            "area_summary": sorted(({"area": a, "best_inliers": max(x["inliers"] for x in v),
                                     "sum_inliers": sum(x["inliers"] for x in v), "hits": len(v)}
                                    for a, v in by_area.items()), key=lambda s: -s["best_inliers"])}


def run_query(ctx, q_img, top=20, ref_mask=None):
    """Full per-photo pipeline on an RGB array.  Returns (verified results, timings)."""
    t0 = time.perf_counter()
    crops = flat_crops(q_img)
    q_desc = ctx["emb"]([to_emb(c) for c in crops])
    hits = retrieve(ctx["index"], q_desc, top, ref_mask)
    t1 = time.perf_counter()
    results = verify(ctx["verifier"], ctx["index"], crops, hits)
    t2 = time.perf_counter()
    return results, {"retrieval_s": round(t1 - t0, 3), "verify_s": round(t2 - t1, 3),
                     "per_photo_total_s": round(t2 - t0, 3)}


def public(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


def setup(roots, method, rebuild=False, workers=12, batch=32):
    if DEVICE == "cuda":
        torch.cuda.set_per_process_memory_fraction(3.0 / 8.0)  # GPU is shared: stay under ~3 GB
    t = time.perf_counter()
    emb, verifier = Embedder(), Verifier()
    t_models = time.perf_counter() - t
    refs = load_refs(roots)
    t = time.perf_counter()
    index = build_index(emb, refs, method, workers, batch, rebuild)
    return {"emb": emb, "verifier": verifier, "index": index,
            "times": {"load_models_s": round(t_models, 2), "index_refs_s": round(time.perf_counter() - t, 2)}}


# ----------------------------------------------------------------------------------------------
# validation with held-out Mapillary pseudo-queries
# ----------------------------------------------------------------------------------------------

def pick_pseudo_queries(refs, n, seed=0, excl_m=5.0, max_true_m=25.0, need_pano=False):
    """n perspective photos spread round-robin over areas, each with at least one other
    reference (a pano if need_pano) between excl_m and max_true_m away, so it is answerable."""
    rng = np.random.default_rng(seed)
    lat = np.array([r["lat"] for r in refs])
    lon = np.array([r["lon"] for r in refs])
    is_pano = np.array([r["is_pano"] for r in refs])
    by_area = defaultdict(list)
    for i, r in enumerate(refs):
        if not r["is_pano"] and r.get("camera_type") == "perspective":
            d = np.hypot((lat - lat[i]) * 111320, (lon - lon[i]) * 111320 * math.cos(math.radians(lat[i])))
            ok = (d > excl_m) & (d <= max_true_m) & (is_pano if need_pano else True)
            if ok.any():
                by_area[r["area"]].append(i)
    areas = sorted(by_area)
    rng.shuffle(areas)
    for a in areas:
        rng.shuffle(by_area[a])
    chosen = []
    while len(chosen) < n and any(by_area[a] for a in areas):
        for a in areas:  # one per area per round
            if by_area[a] and len(chosen) < n:
                chosen.append(by_area[a].pop())
    return chosen


def recall(ranked_lists, truths, ks=(1, 5), radii=(10, 25, 100)):
    out = {}
    for rad in radii:
        for k in ks:
            hit = [any(dist_m(t[0], t[1], r["lat"], r["lon"]) <= rad for r in lst[:k])
                   for lst, t in zip(ranked_lists, truths)]
            out[f"R@{k}_{rad}m"] = round(float(np.mean(hit)), 3)
    return out


def summarize_inliers(rows, radius=25):
    """Top-1 inlier counts for correct (<= radius) vs wrong top-1, and an accept-threshold sweep.
    'precision_100m' counts a top-1 within 100 m (same candidate area) as right; 'far_fp' counts
    accepted top-1s more than 1 km away (a wrong area altogether)."""
    correct = [r["top1_inliers"] for r in rows if r["top1_dist_m"] <= radius]
    wrong = [r["top1_inliers"] for r in rows if r["top1_dist_m"] > radius]
    far = [r["top1_inliers"] for r in rows if r["top1_dist_m"] > 1000]

    def stats(v):
        if not v:
            return {"n": 0}
        return {"n": len(v), "min": int(min(v)), "p10": float(np.percentile(v, 10)),
                "median": float(np.median(v)), "p90": float(np.percentile(v, 90)), "max": int(max(v)),
                "values": sorted(int(x) for x in v)}

    sweep = []
    for t in (20, 30, 40, 50, 60, 75, 100, 125, 150, 200):
        acc = [r for r in rows if r["top1_inliers"] >= t]
        good = [r for r in acc if r["top1_dist_m"] <= radius]
        near = [r for r in acc if r["top1_dist_m"] <= 100]
        sweep.append({"threshold": t, "accepted": len(acc), f"correct_{radius}m": len(good),
                      f"precision_{radius}m": round(len(good) / len(acc), 3) if acc else None,
                      "precision_100m": round(len(near) / len(acc), 3) if acc else None,
                      "far_fp": sum(r["top1_dist_m"] > 1000 for r in acc),
                      f"recall_{radius}m_all_queries": round(len(good) / len(rows), 3)})
    return {f"correct_top1_{radius}m": stats(correct), f"wrong_top1_{radius}m": stats(wrong),
            "wrong_top1_over_1km": stats(far), "threshold_sweep": sweep}


def eval_pseudo(args):
    """Held-out Mapillary perspective photos as queries.  pool 'all': all references, minus the
    query and everything within --exclude-radius-m (variant excl5m), and additionally minus the
    query's own sequence (excl5m_and_same_sequence).  pool 'panos': perspective references are
    removed too, so only panoramas can answer: this isolates the pano view change."""
    roots = [Path(p) for p in args.refs]
    refs = load_refs(roots)
    excl_m = args.exclude_radius_m or 5.0
    need_pano = args.pool == "panos"
    q_idx = pick_pseudo_queries(refs, args.eval_pseudo, args.seed, excl_m, 25.0, need_pano)
    print(f"{len(q_idx)} pseudo-queries from {len({refs[i]['area'] for i in q_idx})} areas (pool {args.pool})")
    report = {"pool": args.pool, "n_queries": len(q_idx), "n_query_areas": len({refs[i]["area"] for i in q_idx}),
              "exclude_radius_m": excl_m,
              "queries": [{k: refs[i][k] for k in ("id", "area", "lat", "lon", "heading", "sequence")}
                          for i in q_idx], "methods": {}}
    variants = ("panos_only_excl5m",) if need_pano else ("excl5m", "excl5m_and_same_sequence")
    is_pano = np.array([r["is_pano"] for r in refs])
    vis_dir = RESULTS / "pano_val_vis"
    vis_dir.mkdir(exist_ok=True)
    methods = args.methods.split(",")
    emb, verifier = None, None
    for method in methods:
        if DEVICE == "cuda":
            torch.cuda.set_per_process_memory_fraction(3.0 / 8.0)
        if emb is None:
            emb, verifier = Embedder(), Verifier()
        index = build_index(emb, refs, method, args.workers, args.batch, args.rebuild)
        ctx = {"emb": emb, "verifier": verifier, "index": index}
        report["methods"][method] = {"index": index["stats"]}
        for variant in variants:
            rows, retr_lists, ver_lists, truths, t_q = [], [], [], [], []
            for n, qi in enumerate(q_idx):
                q = refs[qi]
                mask = exclusion_mask(refs, [q["id"]], excl_m)
                if variant == "excl5m_and_same_sequence" and q.get("sequence"):
                    mask |= np.array([r.get("sequence") == q["sequence"] for r in refs])
                if variant.startswith("panos_only"):
                    mask |= ~is_pano
                pool = ~mask
                d_all = np.array([dist_m(q["lat"], q["lon"], r["lat"], r["lon"]) for r in refs])
                results, times = run_query(ctx, load_rgb(q["path"]), args.top, mask)
                t_q.append(times)
                by_retr = sorted(results, key=lambda x: x["retrieval_rank"])
                retr_lists.append(by_retr)
                ver_lists.append(results)
                truths.append((q["lat"], q["lon"]))
                top1 = results[0]
                td = dist_m(q["lat"], q["lon"], top1["lat"], top1["lon"])
                herr = None
                if top1["is_pano"] and top1["view_heading"] is not None and q.get("heading") is not None:
                    herr = round((top1["view_heading"] - q["heading"] + 180) % 360 - 180, 1)
                rows.append({"query": q["id"], "area": q["area"],
                             "positives_25m": int(((d_all <= 25) & pool).sum()),
                             "pano_positives_25m": int(((d_all <= 25) & pool & is_pano).sum()),
                             "top1_id": top1["id"], "top1_is_pano": top1["is_pano"],
                             "top1_inliers": top1["inliers"], "top1_sim": top1["megaloc_sim"],
                             "top1_dist_m": round(td, 1), "top1_view_heading": top1["view_heading"],
                             "query_heading": q.get("heading"), "top1_heading_err_deg": herr,
                             "retrieval_top1_dist_m": round(dist_m(q["lat"], q["lon"], by_retr[0]["lat"],
                                                                   by_retr[0]["lon"]), 1),
                             "retrieval_top1_sim": by_retr[0]["megaloc_sim"]})
                if variant == variants[0] and method == methods[-1]:
                    qv, rv, p0, p1 = top1["_vis"]
                    draw_pair(qv, rv, p0, p1, vis_dir / f"{args.pool}_q{n:02d}_{q['id']}_{method}.jpg",
                              f"query {q['id']} | top-1 {top1['id']} ({'pano view' if top1['is_pano'] else 'photo'}) "
                              f"{top1['inliers']} inliers, sim {top1['megaloc_sim']:.3f}, {td:.1f} m from truth")
                print(f"  [{method}/{variant}] q{n:02d} {q['area']}: top1 {td:7.1f} m, inliers "
                      f"{top1['inliers']:4d} {'pano' if top1['is_pano'] else 'img '}, retrieval-top1 "
                      f"{rows[-1]['retrieval_top1_dist_m']:7.1f} m sim {rows[-1]['retrieval_top1_sim']:.3f} "
                      f"({times['per_photo_total_s']:.2f}s)", flush=True)
            herrs = [abs(r["top1_heading_err_deg"]) for r in rows
                     if r["top1_heading_err_deg"] is not None and r["top1_dist_m"] <= 25]
            res = {"retrieval_only": recall(retr_lists, truths), "after_inlier_rerank": recall(ver_lists, truths),
                   "inliers": summarize_inliers(rows),
                   "top1_correct_25m_and_pano": sum(1 for r in rows if r["top1_is_pano"] and r["top1_dist_m"] <= 25),
                   "pano_top1_heading_abs_err_deg_median": float(np.median(herrs)) if herrs else None,
                   "pano_top1_heading_n": len(herrs),
                   "median_retrieval_top1_sim": float(np.median([r["retrieval_top1_sim"] for r in rows])),
                   "per_photo_s_median": float(np.median([t["per_photo_total_s"] for t in t_q])),
                   "retrieval_s_median": float(np.median([t["retrieval_s"] for t in t_q])),
                   "verify_s_median": float(np.median([t["verify_s"] for t in t_q])),
                   "rows": rows}
            report["methods"][method][variant] = res
            print(f"  {method}/{variant}: retrieval {res['retrieval_only']} | reranked {res['after_inlier_rerank']}")
        del ctx, index
        torch.cuda.empty_cache()
    out = RESULTS / ("pano_validation_pseudo.json" if args.pool == "all" else f"pano_validation_pseudo_{args.pool}.json")
    out.write_text(json.dumps(report, indent=2))
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query")
    ap.add_argument("--refs", nargs="+", default=[str(HERE / "data" / "mly")])
    ap.add_argument("--method", default="persp", choices=["persp", "strips"])
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--exclude-ids", default="", help="comma-separated reference ids to drop")
    ap.add_argument("--exclude-radius-m", type=float, default=0.0,
                    help="also drop references within this distance of the excluded ids")
    ap.add_argument("--truth", help="LAT,LON of the query, for reporting errors")
    ap.add_argument("--accept-inliers", type=int, default=ACCEPT_INLIERS)
    ap.add_argument("--out", help="output JSON (default results/match_<query stem>.json)")
    ap.add_argument("--rebuild", action="store_true", help="ignore descriptor caches")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--eval-pseudo", type=int, default=0, help="run the held-out pseudo-query validation")
    ap.add_argument("--methods", default="strips,persp", help="methods compared by --eval-pseudo")
    ap.add_argument("--pool", default="all", choices=["all", "panos"],
                    help="--eval-pseudo reference pool: everything, or panoramas only")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.eval_pseudo:
        eval_pseudo(args)
        return
    if not args.query:
        ap.error("--query or --eval-pseudo is required")

    ctx = setup([Path(p) for p in args.refs], args.method, args.rebuild, args.workers, args.batch)
    refs, index = ctx["index"]["refs"], ctx["index"]
    excl = [x for x in args.exclude_ids.split(",") if x]
    mask = exclusion_mask(refs, excl, args.exclude_radius_m) if excl else None
    q_img = load_rgb(args.query)
    results, times = run_query(ctx, q_img, args.top, mask)
    times = {**ctx["times"], **times}
    est = estimate(results)
    stem = Path(args.query).stem
    if results:
        best = results[0]
        qv, rv, p0, p1 = best["_vis"]
        draw_pair(qv, rv, p0, p1, RESULTS / f"match_{stem}_best.jpg",
                  f"{stem} | best {best['id']} ({best['area']}, {'pano view yaw %.0f' % best['view_yaw'] if best['is_pano'] else 'photo'}, "
                  f"heading {best['view_heading']}) {best['inliers']} inliers, sim {best['megaloc_sim']:.3f}")
    out = {"query": args.query, "method": args.method, "refs": args.refs, "times": times,
           "index": index["stats"], "n_refs": len(refs), "n_ref_views": int(index["desc"].shape[0]),
           "excluded_refs": int(mask.sum()) if mask is not None else 0,
           "accept_inliers": args.accept_inliers,
           "accepted": bool(results and results[0]["inliers"] >= args.accept_inliers),
           "estimate": est, "top": [public(r) for r in results]}
    if args.truth:
        tlat, tlon = map(float, args.truth.split(","))
        out["truth"] = {"lat": tlat, "lon": tlon,
                        "top1_error_m": round(dist_m(tlat, tlon, results[0]["lat"], results[0]["lon"]), 1) if results else None,
                        "estimate_error_m": round(dist_m(tlat, tlon, est["lat"], est["lon"]), 1) if est else None,
                        "nearest_ref_m": round(min(dist_m(tlat, tlon, r["lat"], r["lon"]) for r in refs), 1),
                        "refs_within_50m": sum(dist_m(tlat, tlon, r["lat"], r["lon"]) <= 50 for r in refs)}
        for r in out["top"]:
            r["error_m"] = round(dist_m(tlat, tlon, r["lat"], r["lon"]), 1)
    out_path = Path(args.out) if args.out else RESULTS / f"match_{stem}.json"
    out_path.write_text(json.dumps(out, indent=2))

    print(f"{len(refs)} refs ({out['n_ref_views']} views, method {args.method}) | "
          + " | ".join(f"{k} {v:.2f}" for k, v in times.items()))
    print("verified ranking (by inliers):")
    for i, r in enumerate(out["top"], 1):
        print(f"  #{i:2d} {r['area']:8s} {'pano' if r['is_pano'] else 'img '} sim {r['megaloc_sim']:.3f} "
              f"(retr #{r['retrieval_rank']:2d}) inliers {r['inliers']:4d}/{r['matches']:4d}  "
              f"({r['lat']:.5f}, {r['lon']:.5f}) heading {r['view_heading']}"
              + (f"  err {r['error_m']} m" if "error_m" in r else ""))
    if est:
        print(f"estimate: {est['area']} ({est['lat']:.6f}, {est['lon']:.6f}) spread {est['spread_m']} m from "
              f"{est['n_members']} refs; best inliers {est['best_inliers']} -> "
              f"{'ACCEPT' if out['accepted'] else 'reject'} (threshold {args.accept_inliers})")
    if args.truth:
        print(f"truth: top-1 error {out['truth']['top1_error_m']} m, estimate error {out['truth']['estimate_error_m']} m, "
              f"nearest reference {out['truth']['nearest_ref_m']} m, {out['truth']['refs_within_50m']} refs within 50 m")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
