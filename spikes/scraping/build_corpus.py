"""Merge all free-source captures into one deduplicated Toronto image-post corpus,
then download the first image of each post (resized, EXIF recorded then stripped).

Output: spikes/data/corpus/posts.parquet and spikes/data/corpus/img/<post_key>.jpg

    .venv/Scripts/python -m spikes.scraping.build_corpus --max-posts 1000
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import glob
import gzip
import hashlib
import io
import json
import random

import httpx
import pandas as pd
from PIL import ExifTags, Image

from spikes.common.config import DATA, USER_AGENT, ensure_dirs

CORPUS = DATA / "corpus"
IMG_DIR = CORPUS / "img"
MAX_SIDE = 1024
GPS_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")


def _key(uri: str) -> str:
    return hashlib.sha1(uri.encode()).hexdigest()[:16]


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in glob.glob(str(DATA / "bsky" / "jetstream_replay_*.jsonl.gz")):
        for line in gzip.open(path, "rt", encoding="utf-8"):
            r = json.loads(line)
            imgs = [i for i in r["images"] if i.get("mime") != "video"]
            if not r["relevant"] or not imgs:
                continue
            uri = f"at://{r['did']}/app.bsky.feed.post/{r['rkey']}"
            rows.append({
                "uri": uri, "platform": "bluesky", "source": "jetstream", "arm": "passive",
                "created_at": r["created_at"], "text": r["text"], "alt": " ".join(i["alt"] for i in imgs),
                "complaints": r["complaints"], "strong": r["strong"],
                "image_url": f"https://cdn.bsky.app/img/feed_fullsize/plain/{r['did']}/{imgs[0]['cid']}@jpeg",
                "n_images": len(imgs),
            })
    for path in glob.glob(str(DATA / "free" / "*.jsonl.gz")):
        for line in gzip.open(path, "rt", encoding="utf-8"):
            r = json.loads(line)
            imgs = [i for i in r.get("images", []) if i.get("url")]
            if not imgs or not r.get("relevant", True):
                continue
            arm = r.get("arm") or "passive"
            rows.append({
                "uri": r.get("uri") or r.get("url"), "platform": r["platform"], "source": r["source"], "arm": arm,
                "created_at": r.get("created_at"), "text": r.get("text", ""), "alt": r.get("alt", ""),
                "complaints": r.get("complaints", []), "strong": r.get("strong", []),
                "image_url": imgs[0]["url"], "n_images": len(imgs),
            })
    return rows


def fetch(client: httpx.Client, row: dict) -> dict:
    out = {"key": row["key"], "fetch_ok": False, "bytes": None, "exif_any": None, "exif_gps": None,
           "width": None, "height": None, "fetch_error": None}
    try:
        r = client.get(row["image_url"])
        if r.status_code != 200:
            out["fetch_error"] = f"http {r.status_code}"
            return out
        out["bytes"] = len(r.content)
        im = Image.open(io.BytesIO(r.content))
        exif = im.getexif()
        out["exif_any"] = len(exif) > 0
        out["exif_gps"] = GPS_TAG in exif and bool(exif.get_ifd(GPS_TAG))
        im = im.convert("RGB")
        out["width"], out["height"] = im.size
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        im.save(IMG_DIR / f"{row['key']}.jpg", quality=88)  # re-encode: EXIF is not carried over
        out["fetch_ok"] = True
    except Exception as exc:  # noqa: BLE001 - record every failure mode for the report
        out["fetch_error"] = repr(exc)[:200]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-posts", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    ensure_dirs(IMG_DIR)
    df = pd.DataFrame(load_rows())
    df["key"] = df["uri"].map(_key)
    df = df.drop_duplicates("key")
    df = df.drop_duplicates("image_url")
    print("unique relevant image posts by platform/arm:")
    print(df.groupby(["platform", "arm"]).size().to_string())
    # Keep every targeted/Reddit/Mastodon post, fill the rest with a random sample of Bluesky passive.
    keep = df[(df["arm"] == "targeted") | (df["platform"] != "bluesky")]
    rest = df.drop(keep.index)
    n_fill = max(0, a.max_posts - len(keep))
    sample = pd.concat([keep, rest.sample(n=min(n_fill, len(rest)), random_state=a.seed)])
    print(f"sampled {len(sample)} posts for the yield test")
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client, \
            cf.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda r: fetch(client, r), sample.to_dict("records")))
    sample = sample.merge(pd.DataFrame(results), on="key")
    sample.to_parquet(CORPUS / "posts.parquet")
    df.drop(columns=["text", "alt"]).to_parquet(CORPUS / "all_candidates_meta.parquet")
    ok = sample["fetch_ok"].mean()
    print(f"fetch ok: {ok:.1%}  exif_any: {sample['exif_any'].mean():.1%}  exif_gps: {sample['exif_gps'].mean():.1%}")
    print(sample.groupby("platform")["fetch_ok"].mean().to_string())


if __name__ == "__main__":
    main()
