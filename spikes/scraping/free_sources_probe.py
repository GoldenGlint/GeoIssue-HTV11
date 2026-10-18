"""S3/S4 and Bluesky public API checks: Mastodon tag timelines, Reddit RSS/JSON,
Bluesky public AppView. No accounts are used. Usernames are never stored.

    .venv/Scripts/python -m spikes.scraping.free_sources_probe
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from spikes.common.config import DATA, RESULTS, USER_AGENT, ensure_dirs
from spikes.scraping.gazetteer import complaint_terms, match

MASTODON_INSTANCES = ["mstdn.ca", "mastodon.social", "socialontario.ca"]
MASTODON_TAGS = ["toronto", "ttc", "topoli", "torontolife", "torontophotography"]
SUBREDDITS = ["toronto", "askTO", "TTC"]
BSKY_HANDLES = ["ttcriders.bsky.social", "ttcalerts.bsky.social"]

_TAG_RE = re.compile(r"<[^>]+>")


def _text(html_str: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", html_str or "")).strip()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def mastodon(client: httpx.Client, out) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    seen: set[str] = set()
    per_source: dict[str, dict] = {}
    for inst in MASTODON_INSTANCES:
        for tag in MASTODON_TAGS:
            key = f"{inst}#{tag}"
            stat = {"status": None, "posts": 0, "with_images": 0, "relevant_with_images": 0, "oldest": None}
            max_id = None
            for _ in range(15):
                params = {"limit": 40}
                if max_id:
                    params["max_id"] = max_id
                try:
                    r = client.get(f"https://{inst}/api/v1/timelines/tag/{tag}", params=params)
                except httpx.HTTPError as exc:
                    stat["status"] = f"error {exc!r}"
                    break
                stat["status"] = r.status_code
                if r.status_code != 200:
                    break
                batch = r.json()
                if not batch:
                    break
                stop = False
                for s in batch:
                    created = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
                    if created < since:
                        stop = True
                        continue
                    stat["oldest"] = s["created_at"]
                    stat["posts"] += 1
                    imgs = [m for m in s.get("media_attachments", []) if m.get("type") == "image"]
                    if not imgs:
                        continue
                    stat["with_images"] += 1
                    text = _text(s.get("content", ""))
                    alt = " ".join(m.get("description") or "" for m in imgs)
                    m = match(f"{text} {alt} #{tag}")
                    if m.relevant:
                        stat["relevant_with_images"] += 1
                    uri = s.get("uri")
                    if uri in seen:
                        continue
                    seen.add(uri)
                    out.write(json.dumps({
                        "platform": "mastodon", "source": key, "uri": uri, "url": s.get("url"),
                        "created_at": s["created_at"], "author_hash": _hash(s["account"]["url"]),
                        "text": text, "alt": alt, "relevant": m.relevant, "strong": m.strong,
                        "complaints": complaint_terms(f"{text} {alt}"),
                        "images": [{"url": i.get("url"), "preview": i.get("preview_url"),
                                    "meta": (i.get("meta") or {}).get("original")} for i in imgs],
                    }) + "\n")
                if stop:
                    break
                max_id = batch[-1]["id"]
            per_source[key] = stat
            print(key, stat, flush=True)
    return {"per_source": per_source, "unique_image_posts_7d": len(seen)}


def reddit(client: httpx.Client, out) -> dict:
    res = {}
    for sub in SUBREDDITS:
        stat = {}
        r = client.get(f"https://www.reddit.com/r/{sub}/new.json", params={"limit": 25})
        stat["json_status"] = r.status_code
        r = client.get(f"https://www.reddit.com/r/{sub}/new/.rss")
        stat["rss_status"] = r.status_code
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            stat["rss_entries"] = len(feed.entries)
            with_img = 0
            for e in feed.entries:
                content = " ".join(c.get("value", "") for c in e.get("content", []))
                img_urls = re.findall(r'https://(?:i\.redd\.it|preview\.redd\.it|external-preview\.redd\.it)/[^"\s]+', content)
                thumbs = [t.get("url") for t in e.get("media_thumbnail", [])]
                if img_urls or thumbs:
                    with_img += 1
                text = f"{e.get('title', '')} {_text(content)}"
                out.write(json.dumps({
                    "platform": "reddit", "source": f"r/{sub}", "url": e.get("link"),
                    "created_at": e.get("updated"), "text": text[:2000],
                    "images": [{"url": html.unescape(u)} for u in img_urls[:4]] + [{"url": t} for t in thumbs[:1]],
                    "complaints": complaint_terms(text), "relevant": True, "strong": [f"r/{sub}"],
                }) + "\n")
            stat["rss_entries_with_images"] = with_img
        res[sub] = stat
        print(f"r/{sub}", stat, flush=True)
    return res


def bluesky_public(client: httpx.Client) -> dict:
    res = {}
    for host in ["public.api.bsky.app", "api.bsky.app"]:
        r = client.get(f"https://{host}/xrpc/app.bsky.feed.searchPosts", params={"q": "toronto", "limit": 25})
        res[f"searchPosts@{host}"] = r.status_code
    for handle in BSKY_HANDLES:
        r = client.get("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
                       params={"actor": handle, "limit": 50, "filter": "posts_with_media"})
        entry = {"status": r.status_code}
        if r.status_code == 200:
            feed = r.json().get("feed", [])
            entry["posts_with_media"] = len(feed)
            entry["newest"] = feed[0]["post"]["indexedAt"] if feed else None
        res[f"getAuthorFeed:{handle}"] = entry
    print("bluesky public", res, flush=True)
    return res


def main() -> None:
    ensure_dirs(DATA / "free", RESULTS / "raw")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    posts_path = DATA / "free" / f"free_posts_{stamp}.jsonl.gz"
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client, \
            gzip.open(posts_path, "wt", encoding="utf-8") as out:
        result = {
            "run_at": stamp,
            "mastodon": mastodon(client, out),
            "reddit": reddit(client, out),
            "bluesky_public": bluesky_public(client),
            "posts_file": str(posts_path),
        }
    path = RESULTS / "raw" / f"free_sources_{stamp}.json"
    path.write_text(json.dumps(result, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
