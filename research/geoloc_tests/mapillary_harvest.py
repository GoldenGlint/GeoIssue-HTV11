"""Download Mapillary reference images around candidate areas (or one centre point).

Keeps up to --per-area images per area, newest first and spread across headings, at 1024 px
(360 panoramas at 2048 px with --pano-2048).  Writes <out>/<area>/<image_id>.jpg plus
<out>/index.json with each image's area, pose and (when available) sequence id and SfM rotation.

Usage:
  # areas from osm_local_search.py
  python mapillary_harvest.py --candidates results/osm_local_railway-tram__amenity-parking.json
  # everything within 300 m of a point, into its own folder (searched as 100 m tiles)
  python mapillary_harvest.py --center 43.78584,-79.18728 --radius 300 --out data/mly_utsc \
      --area-name utsc --pano-2048
  # re-fetch the panoramas already in <out>/index.json at 2048 px (same paths) and add
  # sequence / computed_rotation / camera_type to every index entry
  python mapillary_harvest.py --pano-2048 [--out data/mly]
"""
import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
API = "https://graph.mapillary.com/images?"
FIELDS = ("id,captured_at,compass_angle,computed_compass_angle,computed_geometry,geometry,is_pano,"
          "sequence,computed_rotation,camera_type,thumb_1024_url,thumb_2048_url")
META_FIELDS = "id,sequence,computed_rotation,camera_type,compass_angle,computed_compass_angle,thumb_2048_url"


def load_env(path):
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def get_json(params, retries=3):
    params = {"access_token": os.environ["MAPILLARY_TOKEN"], **params}
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(API + urllib.parse.urlencode(params), timeout=60) as resp:
                return json.load(resp).get("data", [])
        except Exception as err:  # never echo the URL: it carries the token
            if attempt == retries - 1:
                raise RuntimeError(f"Mapillary request failed: {type(err).__name__}") from None
            time.sleep(2 * (attempt + 1))


def search(lat, lon, radius, limit=2000):
    dlat = radius / 111320
    dlon = radius / (111320 * math.cos(math.radians(lat)))
    return get_json({"fields": FIELDS, "limit": limit,
                     "bbox": f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"})


def lookup(ids, fields=META_FIELDS, batch=100):
    """Metadata for many image ids (100 per request, 8 requests in flight)."""
    chunks = [ids[i:i + batch] for i in range(0, len(ids), batch)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        parts = pool.map(lambda c: get_json({"image_ids": ",".join(c), "fields": fields}), chunks)
    return {d["id"]: d for part in parts for d in part}


def heading(d):
    for key in ("computed_compass_angle", "compass_angle"):
        if d.get(key) is not None:
            return d[key]
    return None


def pick(images, n):
    images = sorted(images, key=lambda d: -d["captured_at"])
    chosen, buckets = [], {}
    # round-robin over 30-degree heading buckets so every view direction is represented
    for d in images:
        h = int(((heading(d) or 0) % 360) // 30)
        buckets.setdefault((h, bool(d.get("is_pano"))), []).append(d)
    while len(chosen) < n and any(buckets.values()):
        for key in list(buckets):
            if buckets[key] and len(chosen) < n:
                chosen.append(buckets[key].pop(0))
    return chosen


def download(item):
    """Fetch url to path atomically (tmp + replace) so concurrent readers never see half a file."""
    path, url, overwrite = item
    if path.exists() and not overwrite:
        return 0
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return len(data)
    except Exception:
        return -1


def entry(area, d):
    geom = (d.get("computed_geometry") or d.get("geometry") or {}).get("coordinates", [None, None])
    return {"area": area, "id": d["id"], "lat": geom[1], "lon": geom[0], "heading": heading(d),
            "captured_at": d["captured_at"], "is_pano": bool(d.get("is_pano")),
            "sequence": d.get("sequence"), "computed_rotation": d.get("computed_rotation"),
            "camera_type": d.get("camera_type"), "compass_angle": d.get("compass_angle"),
            "computed_compass_angle": d.get("computed_compass_angle")}


def write_index(out_root, index):
    tmp = out_root / "index.json.part"
    tmp.write_text(json.dumps(index))
    os.replace(tmp, out_root / "index.json")


def dir_bytes(root, only_ids=None):
    return sum(p.stat().st_size for p in root.glob("*/*.jpg") if only_ids is None or p.stem in only_ids)


def refetch_panos(out_root):
    """Re-download every pano already in out_root/index.json at 2048 px and enrich all entries."""
    index = json.loads((out_root / "index.json").read_text())
    start = time.perf_counter()
    meta = lookup(sorted({r["id"] for r in index}))
    t_meta = time.perf_counter() - start
    pano_ids = {r["id"] for r in index if r["is_pano"]}
    before = dir_bytes(out_root, pano_ids)
    jobs = []
    for r in index:
        m = meta.get(r["id"], {})
        for key in ("sequence", "computed_rotation", "camera_type", "compass_angle", "computed_compass_angle"):
            if m.get(key) is not None:
                r[key] = m[key]
        path = out_root / r["area"] / f"{r['id']}.jpg"
        if r["is_pano"] and m.get("thumb_2048_url") and path.exists():
            jobs.append((path, m["thumb_2048_url"], True))
    with ThreadPoolExecutor(max_workers=16) as pool:
        sizes = list(pool.map(download, jobs))
    write_index(out_root, index)
    after = dir_bytes(out_root, pano_ids)
    total = time.perf_counter() - start
    ok = sum(s >= 0 for s in sizes)
    print(f"metadata for {len(meta)}/{len(index)} entries in {t_meta:.0f}s; re-fetched {ok}/{len(jobs)} panos "
          f"at 2048 px in {total:.0f}s total; pano bytes {before / 1e6:.0f} MB -> {after / 1e6:.0f} MB "
          f"(+{(after - before) / 1e6:.0f} MB)")


def tiles(lat, lon, radius, tile=100.0):
    """Centres of tile x tile m squares covering a circle (bbox searches stay small and complete)."""
    n = math.ceil(radius / tile)
    out = []
    for i in range(-n, n):
        for j in range(-n, n):
            cy, cx = (i + 0.5) * tile, (j + 0.5) * tile
            if math.hypot(max(abs(cy) - tile / 2, 0), max(abs(cx) - tile / 2, 0)) <= radius:
                out.append((lat + cy / 111320, lon + cx / (111320 * math.cos(math.radians(lat)))))
    return out


def dist_m(lat1, lon1, lat2, lon2):
    return math.hypot((lat1 - lat2) * 111320, (lon1 - lon2) * 111320 * math.cos(math.radians(lat1)))


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--candidates", help="osm_local_search.py JSON with 'clusters'")
    src.add_argument("--center", help="LAT,LON: harvest one circle of --radius metres instead")
    ap.add_argument("--radius", type=float, default=100)
    ap.add_argument("--per-area", type=int, default=120, help="images kept per area (per 100 m tile with --center)")
    ap.add_argument("--out", default=str(HERE / "data" / "mly"))
    ap.add_argument("--area-name", default="center", help="area label for --center")
    ap.add_argument("--pano-2048", action="store_true",
                    help="panoramas at 2048 px; without --candidates/--center: re-fetch existing panos in --out")
    args = ap.parse_args()
    load_env(HERE / ".env")
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    if not args.candidates and not args.center:
        if not args.pano_2048:
            ap.error("give --candidates, --center, or --pano-2048 (re-fetch)")
        refetch_panos(out_root)
        return

    if args.candidates:
        clusters = json.loads(Path(args.candidates).read_text())["clusters"]
        areas = [(f"area{i:02d}", [(c["lat"], c["lon"], args.radius)], None) for i, c in enumerate(clusters, 1)]
    else:
        lat0, lon0 = map(float, args.center.split(","))
        areas = [(args.area_name, [(la, lo, 50.0) for la, lo in tiles(lat0, lon0, args.radius)], (lat0, lon0))]

    start = time.perf_counter()
    index, jobs = [], []
    for area, boxes, centre in areas:
        (out_root / area).mkdir(exist_ok=True)
        found, chosen, failed = {}, [], 0
        for lat, lon, r in boxes:
            try:
                # 500 for candidate areas keeps the original harvest reproducible; tiles take all
                got = [d for d in search(lat, lon, r, 2000 if centre else 500) if d.get("thumb_1024_url")]
            except RuntimeError as err:
                failed += 1
                print(f"{area}: search failed ({err})")
                continue
            if centre:  # tile of a circle: keep what is inside the circle, pick per tile
                got = [d for d in got if d["id"] not in found and dist_m(
                    centre[0], centre[1], *(d.get("computed_geometry") or d["geometry"])["coordinates"][::-1])
                    <= args.radius]
            for d in got:
                found[d["id"]] = d
            chosen += pick(got, args.per_area)
        for d in chosen:
            index.append(entry(area, d))
            url = d.get("thumb_2048_url") if args.pano_2048 and d.get("is_pano") else None
            jobs.append((out_root / area / f"{d['id']}.jpg", url or d["thumb_1024_url"], False))
        n_pano = sum(bool(d.get("is_pano")) for d in chosen)
        print(f"{area}: {len(found)} images in {len(boxes)} boxes, keeping {len(chosen)} ({n_pano} panos)"
              + (f", {failed} searches failed" if failed else ""))
    t_search = time.perf_counter() - start

    with ThreadPoolExecutor(max_workers=16) as pool:
        sizes = list(pool.map(download, jobs))
    ok = sum(s >= 0 for s in sizes)
    t_total = time.perf_counter() - start
    write_index(out_root, index)
    print(f"searched {len(areas)} areas in {t_search:.0f}s; downloaded {ok}/{len(jobs)} images "
          f"({sum(s for s in sizes if s > 0) / 1e6:.0f} MB new); total {t_total:.0f}s")


if __name__ == "__main__":
    main()
