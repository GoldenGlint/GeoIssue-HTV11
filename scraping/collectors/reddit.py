"""Recent Toronto subreddit photo posts via the Arctic Shift archive API (no key)."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time

import requests

from ..media import (MediaRecord, assess_freshness, process_media, redact_text,
                    has_issue_words, write_gallery, write_json, write_jsonl)
from ..paths import CONFIG, DATA, REVIEW_TEMPLATE

DEFAULT_CONFIG = CONFIG / "reddit.json"
DEFAULT_OUTPUT = DATA / "reddit-live"
IMAGE_HOSTS = ("i.redd.it",)
EXTENSIONS = {"image/jpg": "jpg", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def load_config(path=DEFAULT_CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    api = str(data.get("api") or "").rstrip("/")
    if api != "https://arctic-shift.photon-reddit.com/api":
        raise ValueError("reddit.json api must be the Arctic Shift HTTPS API.")
    subs = [str(sub).strip().removeprefix("r/") for sub in data.get("subreddits") or []]
    if not subs or len(subs) > 15 or not all(re.fullmatch(r"[A-Za-z0-9_]{2,21}", sub) for sub in subs):
        raise ValueError("Configure 1–15 valid subreddit names.")
    terms = data.get("required_terms") or []
    if (not isinstance(terms, list) or len(terms) > 50
            or any(not isinstance(term, str) or not term.strip() or len(term) > 80 for term in terms)):
        raise ValueError("Configure at most 50 nonempty local discovery terms.")
    query = data.get("query")
    if query is not None and (not isinstance(query, str) or not query.strip() or len(query) > 100):
        raise ValueError("Use a nonempty subreddit-scoped query of at most 100 characters.")
    return {
        "api": api, "subreddits": subs,
        "days": int(data.get("days") or 7),
        "max_posts_per_subreddit": int(data.get("max_posts_per_subreddit") or 600),
        "max_images_per_post": int(data.get("max_images_per_post") or 6),
        "max_images": int(data.get("max_images") or 300),
        "pool": data.get("pool") or "live",
        "required_terms": terms,
        "query": query,
    }


def clean_text(value):
    text = redact_text(value)
    return re.sub(r"(?<![\w/])/?u/[\w-]{3,20}", "[account]", text)


def collect(session, config, *, since, until, retry_wait=3):
    posts, sources = {}, []
    for sub in config["subreddits"]:
        source = {"kind": "subreddit", "subreddit": sub, "pages": 0, "posts_returned": 0, "errors": []}
        sources.append(source)
        before = int(until.timestamp())
        while source["posts_returned"] < config["max_posts_per_subreddit"]:
            params = {"subreddit": sub, "limit": 100, "sort": "desc",
                      "after": int(since.timestamp()), "before": before}
            if config.get("query"):
                params["query"] = config["query"]
            try:
                for attempt in range(3):
                    response = session.get(config["api"] + "/posts/search", params=params,
                                           timeout=(10, 40), allow_redirects=False)
                    # Arctic Shift intermittently answers 422/429/5xx; a retry usually succeeds.
                    if response.status_code in (422, 429, 500, 502, 503, 504) and attempt < 2:
                        time.sleep(retry_wait * (attempt + 1))
                        continue
                    break
                if response.status_code != 200:
                    raise ValueError(f"Arctic Shift returned HTTP {response.status_code}.")
                payload = response.json()
                entries = payload.get("data")
                if not isinstance(entries, list):
                    raise ValueError(str(payload.get("error") or "Arctic Shift returned no post list.")[:160])
            except (ValueError, requests.RequestException) as exc:
                source["errors"].append(str(exc)[:200])
                break
            source["pages"] += 1
            source["posts_returned"] += len(entries)
            for post in entries:
                if isinstance(post, dict) and isinstance(post.get("id"), str):
                    found = posts.setdefault(post["id"], post).setdefault("_found_by", [])
                    if f"subreddit:{sub}" not in found:
                        found.append(f"subreddit:{sub}")
                    if config.get("query") and f"query:{config['query']}" not in found:
                        found.append(f"query:{config['query']}")
            oldest = min((p.get("created_utc") for p in entries if isinstance(p, dict)
                          and isinstance(p.get("created_utc"), (int, float))), default=None)
            if len(entries) < 100 or oldest is None or int(oldest) >= before:
                break
            before = int(oldest)
    return list(posts.values()), sources


def image_urls(post, limit):
    if post.get("is_gallery"):
        meta = post.get("media_metadata") or {}
        items = (post.get("gallery_data") or {}).get("items") or []
        urls = []
        for index, item in enumerate(items):
            info = meta.get(item.get("media_id")) or {}
            ext = EXTENSIONS.get(info.get("m"))
            media_id = str(info.get("id") or "")
            if (item.get("is_deleted") or info.get("e") != "Image" or info.get("status") != "valid"
                    or not ext or not re.fullmatch(r"[A-Za-z0-9]{5,20}", media_id)):
                continue
            urls.append((index, media_id, f"https://i.redd.it/{media_id}.{ext}"))
        return urls[:limit]
    url = post.get("url") or ""
    match = re.fullmatch(r"https://i\.redd\.it/([A-Za-z0-9]{5,20})\.(?:jpe?g|png|webp)", url)
    if post.get("post_hint") == "image" and match:
        return [(0, match[1], url)]
    return []


def normalize(posts, *, since, now, max_images_per_post=6, required_terms=()):
    records, stats = [], Counter()
    local = re.compile(r"\b(?:" + "|".join(re.escape(term) for term in required_terms) + r")\b", re.I) if required_terms else None
    for post in posts:
        stats["posts_inspected"] += 1
        try:
            if post.get("over_18") or post.get("spoiler"):
                stats["nsfw_or_spoiler_skipped"] += 1
                continue
            if post.get("removed_by_category") or post.get("author") in (None, "[deleted]"):
                stats["removed_posts_skipped"] += 1
                continue
            if post.get("crosspost_parent"):
                stats["crossposts_skipped"] += 1
                continue
            if local and not local.search(f"{post.get('title') or ''} {post.get('selftext') or ''}"):
                stats["outside_discovery_area"] += 1
                continue
            created = datetime.fromtimestamp(int(post["created_utc"]), timezone.utc)
            if created < since:
                stats["older_posts_skipped"] += 1
                continue
            if created > now + timedelta(minutes=5):
                stats["future_posts_skipped"] += 1
                continue
            urls = image_urls(post, max_images_per_post)
            if not urls:
                stats["non_photo_posts_skipped"] += 1
                continue
            permalink = str(post.get("permalink") or "")
            if not re.fullmatch(r"/r/[A-Za-z0-9_]+/comments/[a-z0-9]+/[^?#\s]*", permalink):
                raise ValueError("Invalid permalink")
            caption = clean_text("\n\n".join(x for x in (post.get("title"), post.get("selftext")) if x))
            flair = str(post.get("link_flair_text") or "")
            for index, media_id, url in urls:
                records.append(MediaRecord(
                    platform="reddit", collector="arctic-shift-api",
                    post_id="https://www.reddit.com" + permalink, media_index=index,
                    media_url=url, posted_at=created.isoformat(), caption=caption,
                    alt_text=clean_text(flair), media_id=media_id, location_evidence=[],
                    found_by=list(post.get("_found_by") or []),
                ))
        except (KeyError, ValueError, TypeError, AttributeError):
            stats["invalid_posts"] += 1
    return records, dict(stats)


def run(*, config_path=DEFAULT_CONFIG, output=DEFAULT_OUTPUT):
    config = load_config(config_path)
    if config["pool"] == "live" and not 1 <= config["days"] <= 7:
        raise ValueError("Live Reddit collection uses 1–7 days.")
    if config["pool"] == "training" and not 1 <= config["days"] <= 365:
        raise ValueError("Training Reddit collection uses 1–365 days.")
    if not (1 <= config["max_images"] <= 1000 and 1 <= config["max_images_per_post"] <= 20
            and 1 <= config["max_posts_per_subreddit"] <= 5000):
        raise ValueError("Use 1–1000 images, 1–20 images/post, and 1–5000 posts/subreddit.")
    output = Path(output).resolve()
    if not output.is_relative_to(DATA.resolve()):
        raise ValueError("Write Reddit batches inside scraping/data.")
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    since = started - timedelta(days=config["days"])
    with requests.Session() as session:
        session.headers["User-Agent"] = "GeoIssue-Reddit/0.1"
        posts, sources = collect(session, config, since=since, until=started)
    if not any(source["pages"] for source in sources):
        raise ValueError("All subreddit requests failed. " +
                         " ".join(error for source in sources for error in source["errors"]))
    records, normalization = normalize(posts, since=since, now=started,
                                       max_images_per_post=config["max_images_per_post"],
                                       required_terms=config["required_terms"])
    records.sort(key=lambda record: record.posted_at or "", reverse=True)
    records.sort(key=lambda record: not has_issue_words({"caption": record.caption, "alt_text": record.alt_text}))
    if len(records) > config["max_images"]:
        records = records[:config["max_images"]]
        normalization["images_capped"] = True
    rows = process_media(records, output, hosts=IMAGE_HOSTS, since=since)
    rows = [{**row, "freshness": assess_freshness(row, since=since)} for row in rows]
    report = {
        "platform": "reddit", "collector": "arctic-shift-api", "api": config["api"],
        "pool": config["pool"], "started_at": started.isoformat(), "since": since.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "authenticated": False, "paid_services_used": False,
        "status": "partial" if any(s["errors"] for s in sources) else "ok",
        "sources": sources, "unique_posts_returned": len(posts), "normalization": normalization,
        "stored_images": len(rows),
        "ready_for_review": sum(r["auto_status"] == "ready" for r in rows),
        "download_failed": sum(r["auto_status"] == "download_failed" for r in rows),
        "terms_note": ("Arctic Shift is a third-party Reddit archive. Reddit's terms restrict reuse "
                       "of its data; treat this as hackathon prototype input."),
    }
    write_jsonl(output / "media.jsonl", rows)
    write_json(output / "reddit-report.json", report)
    if REVIEW_TEMPLATE.is_file():
        write_gallery(output, rows, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        report = run(config_path=args.config, output=args.output)
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"Reddit collection stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
