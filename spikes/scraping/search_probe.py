"""Backfill probes that need no account:
- Bluesky `searchPosts` on api.bsky.app (passive arm "toronto" + targeted complaint queries)
- Reddit RSS for r/askTO and r/TTC, paced to avoid 429s

    .venv/Scripts/python -m spikes.scraping.search_probe --days 7
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from spikes.common.config import DATA, RESULTS, USER_AGENT, ensure_dirs
from spikes.scraping.gazetteer import complaint_terms, match

PASSIVE_QUERIES = ["toronto", "ttc", "scarborough", "etobicoke", "north york"]
TARGETED_QUERIES = [
    "toronto pothole", "toronto potholes", "ttc elevator", "ttc escalator", "toronto flooding",
    "toronto graffiti", "toronto garbage", "toronto construction", "toronto sidewalk",
    "toronto broken", "toronto streetlight", "311 toronto", "toronto road closed",
    "toronto bike lane", "toronto bus shelter", "toronto fallen tree", "toronto water main",
]
REDDIT_SUBS = ["TTC", "toronto"]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def bluesky_search(client: httpx.Client, out, days: int, max_pages: int) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen: set[str] = set()
    stats = {}
    for arm, queries in (("passive", PASSIVE_QUERIES), ("targeted", TARGETED_QUERIES)):
        for q in queries:
            st = {"status": None, "posts": 0, "with_images": 0, "relevant_with_images": 0, "new_unique": 0}
            until = None
            for _ in range(max_pages):
                # Cursor paging returns 403 without auth, so page backwards with `until`.
                params = {"q": q, "limit": 100, "sort": "latest", "since": since}
                if until:
                    params["until"] = until
                r = client.get("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts", params=params)
                st["status"] = r.status_code
                if r.status_code != 200:
                    break
                body = r.json()
                posts = body.get("posts", [])
                for p in posts:
                    st["posts"] += 1
                    embed = p.get("embed") or {}
                    if embed.get("$type") == "app.bsky.embed.recordWithMedia#view":
                        embed = embed.get("media") or {}
                    if embed.get("$type") != "app.bsky.embed.images#view":
                        continue
                    st["with_images"] += 1
                    rec = p.get("record") or {}
                    text = rec.get("text", "")
                    alt = " ".join(i.get("alt", "") for i in embed.get("images", []))
                    m = match(f"{text} {alt}")
                    if m.relevant:
                        st["relevant_with_images"] += 1
                    if p["uri"] in seen:
                        continue
                    seen.add(p["uri"])
                    st["new_unique"] += 1
                    out.write(json.dumps({
                        "platform": "bluesky", "source": f"search:{q}", "arm": arm, "uri": p["uri"],
                        "created_at": rec.get("createdAt"), "indexed_at": p.get("indexedAt"),
                        "author_hash": _hash(p["author"]["did"]), "text": text, "alt": alt,
                        "relevant": m.relevant, "strong": m.strong,
                        "complaints": complaint_terms(f"{text} {alt}"),
                        "images": [{"url": i.get("fullsize"), "thumb": i.get("thumb"),
                                    "aspect": i.get("aspectRatio")} for i in embed.get("images", [])],
                    }) + "\n")
                if len(posts) < 50:
                    break
                oldest = min(p.get("indexedAt") or "" for p in posts)
                if not oldest or oldest == until:
                    break
                until = oldest
                time.sleep(1.0)
            stats[f"{arm}:{q}"] = st
            print(arm, q, st, flush=True)
    return {"per_query": stats, "unique_image_posts": len(seen)}


def reddit_rss(client: httpx.Client, out) -> dict:
    res = {}
    for sub in REDDIT_SUBS:
        time.sleep(90)
        r = client.get(f"https://www.reddit.com/r/{sub}/new/.rss", params={"limit": 100})
        st = {"status": r.status_code, "retry_after": r.headers.get("retry-after")}
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            st["entries"] = len(feed.entries)
            st["with_images"] = 0
            for e in feed.entries:
                content = " ".join(c.get("value", "") for c in e.get("content", []))
                img_urls = re.findall(r'https://(?:i\.redd\.it|preview\.redd\.it)/[^"\s<]+', content)
                thumbs = [t.get("url") for t in e.get("media_thumbnail", []) if t.get("url")]
                if not (img_urls or thumbs):
                    continue
                st["with_images"] += 1
                text = f"{e.get('title', '')} {html.unescape(re.sub(r'<[^>]+>', ' ', content))}"
                out.write(json.dumps({
                    "platform": "reddit", "source": f"r/{sub}", "arm": "passive", "uri": e.get("link"),
                    "created_at": e.get("updated"), "text": text[:2000], "alt": "",
                    "relevant": True, "strong": [f"r/{sub}"], "complaints": complaint_terms(text),
                    "images": [{"url": html.unescape(u)} for u in img_urls[:4]] or [{"url": t} for t in thumbs[:1]],
                }) + "\n")
            if feed.entries:
                st["newest"] = feed.entries[0].get("updated")
                st["oldest"] = feed.entries[-1].get("updated")
        res[sub] = st
        print(f"r/{sub}", st, flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max-pages", type=int, default=10)
    a = ap.parse_args()
    ensure_dirs(DATA / "free", RESULTS / "raw")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    posts_path = DATA / "free" / f"bsky_search_{stamp}.jsonl.gz"
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as client, \
            gzip.open(posts_path, "wt", encoding="utf-8") as out:
        result = {"run_at": stamp, "bluesky_search": bluesky_search(client, out, a.days, a.max_pages),
                  "reddit_rss_paced": reddit_rss(client, out), "posts_file": str(posts_path)}
    path = RESULTS / "raw" / f"search_probe_{stamp}.json"
    path.write_text(json.dumps(result, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
