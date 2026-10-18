"""Bounded, account-free Bluesky collection using the shared media pipeline."""

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

import requests

from ..media import (MediaRecord, allowed_url, assess_freshness, parse_time, process_media, read_jsonl,
                    redact_text, write_gallery, write_json, write_jsonl)
from ..paths import DATA, REVIEW_TEMPLATE


# Public search returned 403 at public.api.bsky.app, but works here without auth.
API = "https://api.bsky.app/xrpc/"
IMAGE_HOSTS = ("cdn.bsky.app",)
DEFAULT_OUTPUT = DATA / "bluesky"
# Prefer dropping the whole post when any of these known adult/graphic labels appear.
SAFETY_LABELS = frozenset({"porn", "sexual", "nudity", "graphic-media", "gore", "nsfl"})


def safety_label_values(post):
    """Collect moderation, self, and author label values without retaining the objects."""
    values = []
    for label in post.get("labels") or []:
        if isinstance(label, dict) and isinstance(label.get("val"), str):
            values.append(label["val"].lower())
    record_labels = (post.get("record") or {}).get("labels") or {}
    for label in record_labels.get("values") or []:
        if isinstance(label, dict) and isinstance(label.get("val"), str):
            values.append(label["val"].lower())
    for label in (post.get("author") or {}).get("labels") or []:
        if isinstance(label, dict) and isinstance(label.get("val"), str):
            values.append(label["val"].lower())
    return values


def has_safety_label(post):
    return bool(SAFETY_LABELS.intersection(safety_label_values(post)))


def load_lines(path, *, kind="query"):
    """One value per line; '# ' comments preserve standalone hashtag queries."""
    values = list(dict.fromkeys(line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines()
                                if line.strip() and not line.strip().startswith(("# ", "#\t"))
                                and line.strip() != "#"))
    if not values:
        raise ValueError(f"The {kind} file has no enabled entries.")
    return values


def load_queries(path):
    return load_lines(path, kind="query")


def load_authors(path):
    return load_lines(path, kind="author")


def clean_text(value):
    # Bluesky handles can contain hyphens, unlike Instagram handles.
    return redact_text(re.sub(r"(?<!\w)@[\w.-]+", "[account]", str(value or "")))


def api_get(session, method, params):
    """Only public reads, with bounded retries; never echo response bodies."""
    for attempt in range(2):
        try:
            response = session.get(API + method, params=params, timeout=(5, 20),
                                   allow_redirects=False)
        except requests.RequestException:
            raise ValueError(f"Bluesky connection failed for {method}.") from None
        if response.status_code in (429, 502, 503, 504) and attempt == 0:
            time.sleep(1)
            continue
        if response.status_code != 200:
            raise ValueError(f"{method} returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            raise ValueError(f"{method} returned a non-JSON response.") from None
        if not isinstance(payload, dict) or payload.get("error"):
            raise ValueError(f"{method} returned an invalid API response.")
        return payload


def collect(session, queries, authors, *, since, until, max_posts=100, max_pages=5):
    """Page each explicitly chosen source; limits apply per source."""
    posts, sources = {}, []
    for kind, value in [("query", q) for q in queries] + [("author", a) for a in authors]:
        source = {"kind": kind, "source_hash": hashlib.sha256(value.encode()).hexdigest()[:16],
                  "posts_returned": 0, "pages": 0, "reposts_skipped": 0, "errors": []}
        if kind == "query":
            source["query"] = clean_text(value)
        sources.append(source)
        cursor, cursors = None, set()
        for _ in range(max_pages):
            limit = min(100, max_posts - source["posts_returned"])
            if limit <= 0:
                break
            params = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            if kind == "query":
                method = "app.bsky.feed.searchPosts"
                params.update(q=value, sort="latest")
                # searchPosts returns HTTP 400 for hashtag queries with since/until; normalize() filters dates.
                if not value.lstrip().startswith("#"):
                    params.update(since=since.isoformat(), until=until.isoformat())
            else:
                method = "app.bsky.feed.getAuthorFeed"
                params.update(actor=value, filter="posts_with_media")
            try:
                payload = api_get(session, method, params)
                entries = payload.get("posts" if kind == "query" else "feed")
                if not isinstance(entries, list):
                    raise ValueError(f"{method} did not return a post list.")
                source["pages"] += 1
                source["posts_returned"] += len(entries)
                for entry in entries[:limit]:
                    if not isinstance(entry, dict):
                        continue
                    if kind == "author":
                        if entry.get("reason", {}).get("$type") == "app.bsky.feed.defs#reasonRepost":
                            source["reposts_skipped"] += 1
                            continue
                        entry = entry.get("post", {})
                    if isinstance(entry, dict) and isinstance(entry.get("uri"), str):
                        post = posts.setdefault(entry["uri"], entry)
                        label = f"{kind}:{clean_text(value)}"
                        found = post.setdefault("_found_by", [])
                        if label not in found:
                            found.append(label)
                next_cursor = payload.get("cursor")
                if not entries or not next_cursor:
                    break
                if next_cursor in cursors:
                    raise ValueError("Bluesky repeated a pagination cursor; stopped this source.")
                cursors.add(next_cursor)
                cursor = next_cursor
            except ValueError as exc:
                # Unauthenticated search answers later pages with 403; keep the pages already read.
                if source["pages"] and "HTTP 403" in str(exc):
                    source["paging_stopped"] = "HTTP 403 after first page"
                else:
                    source["errors"].append(str(exc))
                break
    return list(posts.values()), sources


def refresh_posts(session, rows):
    """Recheck retained post IDs: omitted/deleted posts are removed on this run."""
    uris = list(dict.fromkeys(row["post_id"] for row in rows))
    refreshed = []
    for offset in range(0, len(uris), 25):
        payload = api_get(session, "app.bsky.feed.getPosts", {"uris": uris[offset:offset + 25]})
        if not isinstance(payload.get("posts"), list):
            raise ValueError("Post refresh failed; existing output has been preserved.")
        refreshed.extend(payload["posts"])
    return refreshed


def normalize(posts, *, since, now):
    """Extract only a post's own photos, preserving original image positions."""
    records, stats, seen = [], Counter(), set()
    for post in posts:
        stats["posts_inspected"] += 1
        try:
            uri = post["uri"]
            if not re.fullmatch(r"at://did:[^/]+/app\.bsky\.feed\.post/[^/?#]+", uri):
                raise ValueError("Invalid post URI")
            if has_safety_label(post):
                stats["safety_labeled_posts_skipped"] += 1
                continue
            record = post["record"]
            created = parse_time(record["createdAt"])
            if created < since:
                stats["older_posts_skipped"] += 1
                continue
            if created > now + timedelta(minutes=5):
                stats["future_posts_skipped"] += 1
                continue
            embed = post.get("embed") or {}
            raw_embed = record.get("embed") or {}
            if embed.get("$type") == "app.bsky.embed.recordWithMedia#view":
                embed = embed.get("media") or {}
                raw_embed = raw_embed.get("media") or {}
            if embed.get("$type") != "app.bsky.embed.images#view":
                stats["non_photo_posts_skipped"] += 1
                continue
            images = embed.get("images")
            if not isinstance(images, list) or len(images) > 4:
                raise ValueError("Invalid image list")
            for index, image in enumerate(images):
                try:
                    url = image.get("fullsize") or image.get("thumb")
                    if not isinstance(url, str) or not allowed_url(url, IMAGE_HOSTS):
                        raise ValueError("Invalid image URL")
                    original_images = raw_embed.get("images") or []
                    original = original_images[index] if index < len(original_images) else {}
                    cid = original.get("image", {}).get("ref", {}).get("$link")
                    if not cid:
                        cid = url.split("?")[0].rsplit("/", 1)[-1].split("@")[0]
                    media = MediaRecord(
                        platform="bluesky", collector="bluesky-public-api", post_id=uri,
                        media_index=index, media_url=url, posted_at=created.isoformat(),
                        caption=clean_text(record.get("text")), alt_text=clean_text(image.get("alt")),
                        media_id=str(cid), location_evidence=[],
                        found_by=list(post.get("_found_by") or []),
                    )
                    if media.key in seen:
                        stats["duplicate_media_keys"] += 1
                        continue
                    seen.add(media.key)
                    records.append(media)
                    if not image.get("fullsize"):
                        stats["thumbnail_fallbacks"] += 1
                except (ValueError, TypeError, AttributeError):
                    stats["invalid_images"] += 1
        except (KeyError, ValueError, TypeError, AttributeError):
            stats["invalid_posts"] += 1
    return records, dict(stats)


def local_image(output, row):
    value = row.get("local_path")
    if isinstance(value, str) and re.fullmatch(r"images/[0-9a-f]{64}\.jpg", value):
        return Path(output) / value
    return None


def save(records, existing, output, *, max_images=30, since=None):
    """Reuse current media; stage downloads so failures cannot truncate old JSONL."""
    output = Path(output)
    previous = {row["key"]: row for row in existing}
    desired = {record.key: record for record in records}
    kept, pending, stats = {}, [], Counter()
    for record in records:
        old = previous.get(record.key)
        image = local_image(output, old or {})
        anchor = previous.get((old or {}).get("duplicate_of"), {})
        anchor_image = local_image(output, anchor)
        anchor_record = desired.get(anchor.get("key"))
        anchor_current = (anchor_record and anchor.get("media_id") == anchor_record.media_id
                          and anchor_image and anchor_image.is_file())
        current = (old and old.get("media_id") == record.media_id and
                   ((image and image.is_file()) or anchor_current))
        if current:
            kept[record.key] = {**old, **asdict(record)}
            stats["media_reused"] += 1
        elif len(pending) < max_images:
            pending.append(record)
        else:
            stats["images_deferred"] += 1

    with tempfile.TemporaryDirectory(prefix=".bluesky-stage-", dir=output) as temporary:
        stage = Path(temporary)
        downloaded = process_media(pending, stage, hosts=IMAGE_HOSTS, since=since) if pending else []
        pixels = {row["sha256"]: key for key, row in kept.items()
                  if row.get("sha256") and row.get("local_path")}
        for row in downloaded:
            digest = row.get("sha256")
            if digest and digest in pixels:
                row.update(auto_status="excluded", reasons=["duplicate_image"],
                           duplicate_of=pixels[digest], local_path=None)
            elif digest and row.get("local_path"):
                pixels[digest] = row["key"]
            kept[row["key"]] = row
        rows = [{**row, "freshness": assess_freshness(row, since=since)} for row in kept.values()]
        live_paths = {path for row in rows if (path := local_image(output, row))}
        (output / "images").mkdir(exist_ok=True)
        for path in live_paths:
            staged = stage / "images" / path.name
            if staged.exists():
                staged.replace(path)
        write_jsonl(stage / "media.jsonl", rows)
        (stage / "media.jsonl").replace(output / "media.jsonl")
        # Delete only paths referenced by our previous rows, never unrelated files.
        for path in {path for row in existing if (path := local_image(output, row))} - live_paths:
            path.unlink(missing_ok=True)
    stats.update(images_attempted=len(pending), images_removed=len(previous.keys() - kept.keys()))
    stats["download_failed"] = sum(row["auto_status"] == "download_failed" for row in downloaded)
    stats["images_downloaded"] = sum(bool(row.get("fetched_at")) for row in downloaded)
    return rows, dict(stats)


def run(*, queries=(), authors=(), output=DEFAULT_OUTPUT, days=7,
        max_posts=100, max_pages=5, max_images=30, pool="live"):
    if pool not in ("live", "training"):
        raise ValueError("pool must be live or training.")
    max_sources = 50
    max_days = 7 if pool == "live" else 365
    max_images_cap = 200 if pool == "live" else 1000
    if (not queries and not authors) or len(queries) + len(authors) > max_sources:
        raise ValueError(f"Choose 1–{max_sources} queries or author feeds.")
    if not (1 <= days <= max_days and 1 <= max_posts <= 500 and 1 <= max_pages <= 20
            and 1 <= max_images <= max_images_cap):
        raise ValueError(
            f"Use 1–{max_days} days for {pool}, 1–500 posts/source, 1–20 pages/source, "
            f"and 1–{max_images_cap} images/run.")
    if any(not value.strip() or len(value) > 500 for value in [*queries, *authors]):
        raise ValueError("Source values must be nonempty and at most 500 characters.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".bluesky.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise ValueError("Another collector owns this output directory, or a stale lock needs removing.") from None
    handle.close()
    try:
        existing = read_jsonl(output / "media.jsonl") if (output / "media.jsonl").exists() else []
        if any(row.get("platform") != "bluesky" for row in existing):
            raise ValueError("This output directory contains another platform. Choose a Bluesky-only directory.")
        started = datetime.now(timezone.utc)
        since = started - timedelta(days=days)
        with requests.Session() as session:
            session.headers["User-Agent"] = "GeoIssue-Bluesky/0.1"
            refreshed = refresh_posts(session, existing)
            posts, sources = collect(session, queries, authors, since=since, until=started,
                                     max_posts=max_posts, max_pages=max_pages)
        if not any(source["pages"] for source in sources):
            raise ValueError("All sources failed; existing output has been preserved. " +
                             " ".join(error for source in sources for error in source["errors"]))
        # The explicit refresh is authoritative for existing posts, including edits/deletions.
        old_uris = {row["post_id"] for row in existing}
        found_by = {}
        for row in existing:
            found_by.setdefault(row["post_id"], [])
            found_by[row["post_id"]] += [x for x in row.get("found_by") or [] if x not in found_by[row["post_id"]]]
        for post in posts:
            found = found_by.setdefault(post["uri"], [])
            found += [x for x in post.get("_found_by") or [] if x not in found]
        combined = {post["uri"]: post for post in posts if post.get("uri") not in old_uris}
        combined.update({post["uri"]: post for post in refreshed if post.get("uri")})
        for uri, post in combined.items():
            post["_found_by"] = found_by.get(uri, [])
        records, normalization = normalize(combined.values(), since=since, now=started)
        rows, persistence = save(records, existing, output, max_images=max_images, since=since)
        report = {
            "platform": "bluesky", "collector": "bluesky-public-api", "api_base": API,
            "pool": pool, "started_at": started.isoformat(), "since": since.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(), "authenticated": False,
            "paid_services_used": False, "status": "partial" if any(s["errors"] for s in sources) else "ok",
            "sources": sources, "unique_posts_returned": len(posts),
            "retained_posts_rechecked": len(old_uris),
            "posts_unavailable_on_refresh": len(old_uris - {p.get("uri") for p in refreshed}),
            "normalization": normalization, "persistence": persistence,
            "stored_images": len(rows), "ready_for_review": sum(r["auto_status"] == "ready" for r in rows),
            "review_status": ("downloaded only; run scraping.screen for automatic keep/reject. "
                              "Human review is optional."),
        }
        write_json(output / "bluesky-report.json", report)
        if REVIEW_TEMPLATE.is_file():
            write_gallery(output, rows, report)
        return report
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", default=[], help="Repeat for multiple text searches.")
    parser.add_argument("--query-file", type=Path, help="Editable UTF-8 file: one query per line, '# ' comments.")
    parser.add_argument("--author", action="append", default=[], help="Public handle or DID; not saved in reports.")
    parser.add_argument("--author-file", type=Path, help="Editable UTF-8 file of public handles or DIDs.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--pool", choices=("live", "training"), default="live",
                        help="live: 1–7 day window; training: up to 365 days, larger image cap.")
    parser.add_argument("--max-posts", type=int, default=100, help="Maximum posts inspected per source.")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum pages per source.")
    parser.add_argument("--max-images", type=int, default=30, help="Maximum new/replacement image downloads.")
    args = parser.parse_args()
    try:
        if args.query_file:
            args.query = list(dict.fromkeys(args.query + load_queries(args.query_file)))
        if args.author_file:
            args.author = list(dict.fromkeys(args.author + load_authors(args.author_file)))
        if not args.query and not args.author:
            args.query = ["toronto"]
        report = run(queries=args.query, authors=args.author, output=args.output, days=args.days,
                     max_posts=args.max_posts, max_pages=args.max_pages, max_images=args.max_images,
                     pool=args.pool)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Bluesky collection stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
