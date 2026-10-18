"""Bounded Mastodon hashtag collection using the shared media pipeline."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import requests

from ..media import (MediaRecord, allowed_url, assess_freshness, parse_time, process_media,
                    redact_text, write_gallery, write_json, write_jsonl)
from ..paths import CONFIG, DATA, REVIEW_TEMPLATE

DEFAULT_CONFIG = CONFIG / "mastodon.json"
DEFAULT_OUTPUT = DATA / "mastodon"
# Attachment hosts are allowlisted from observed CDN patterns; expand only after inspection.
IMAGE_HOSTS = ("files.mastodon.social", "cdn.masto.host", "media.mastodon.social")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p") and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")


def html_to_text(value):
    parser = _TextExtractor()
    parser.feed(str(value or ""))
    parser.close()
    return redact_text(re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip())


def load_config(path=DEFAULT_CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    instance = str(data.get("instance") or "").rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+", instance):
        raise ValueError("mastodon.json needs an https instance host.")
    tags = [str(tag).lstrip("#") for tag in data.get("tags") or [] if str(tag).strip()]
    if not tags or len(tags) > 12:
        raise ValueError("Configure 1–12 Mastodon tags.")
    return {
        "instance": instance,
        "tags": tags,
        "max_pages_per_feed": int(data.get("max_pages_per_feed") or 2),
        "posts_per_page": int(data.get("posts_per_page") or 20),
        "max_images": int(data.get("max_images") or 100),
        "days": int(data.get("days") or 7),
        "pool": data.get("pool") or "live",
    }


def api_get(session, url, params=None):
    try:
        response = session.get(url, params=params, timeout=(8, 25), allow_redirects=False)
    except requests.RequestException as exc:
        raise ValueError("Mastodon connection failed.") from exc
    if response.status_code in (401, 403, 429):
        raise ValueError(f"Mastodon access restricted (HTTP {response.status_code}).")
    if response.status_code != 200:
        raise ValueError(f"Mastodon returned HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Mastodon returned non-JSON.") from exc
    return payload, response.headers


def next_page_url(headers):
    link = headers.get("Link") or ""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link)
    return match.group(1) if match else None


def collect(session, config, *, since):
    posts, sources = {}, []
    for tag in config["tags"]:
        source = {"kind": "tag", "tag": tag, "pages": 0, "posts_returned": 0,
                  "sensitive_skipped": 0, "errors": []}
        sources.append(source)
        url = f"{config['instance']}/api/v1/timelines/tag/{tag}"
        params = {"only_media": "true", "limit": min(40, config["posts_per_page"])}
        for _ in range(max(1, config["max_pages_per_feed"])):
            try:
                payload, headers = api_get(session, url, params)
                if not isinstance(payload, list):
                    raise ValueError("Tag timeline did not return a list.")
                source["pages"] += 1
                source["posts_returned"] += len(payload)
                for status in payload:
                    if not isinstance(status, dict):
                        continue
                    if status.get("sensitive") is True or status.get("reblog"):
                        source["sensitive_skipped"] += 1
                        continue
                    uri = status.get("uri") or status.get("url")
                    if isinstance(uri, str) and uri:
                        found = posts.setdefault(uri, status).setdefault("_found_by", [])
                        if f"tag:{tag}" not in found:
                            found.append(f"tag:{tag}")
                nxt = next_page_url(headers)
                if not payload or not nxt:
                    break
                url, params = nxt, None
            except ValueError as exc:
                source["errors"].append(str(exc))
                break
    return list(posts.values()), sources


def attachment_hosts_for(status):
    hosts = set()
    for media in status.get("media_attachments") or []:
        url = media.get("url") or media.get("preview_url")
        if isinstance(url, str):
            host = urlsplit(url).hostname
            if host:
                hosts.add(host)
    return hosts


def normalize(statuses, *, since, now, allowed_hosts=IMAGE_HOSTS):
    records, stats, seen = [], Counter(), set()
    dynamic_hosts = set(allowed_hosts)
    for status in statuses:
        stats["posts_inspected"] += 1
        try:
            if status.get("visibility") not in (None, "public"):
                stats["non_public_skipped"] += 1
                continue
            if status.get("sensitive") is True or status.get("reblog"):
                stats["sensitive_skipped"] += 1
                continue
            created = parse_time(status["created_at"])
            if created < since:
                stats["older_posts_skipped"] += 1
                continue
            if created > now + timedelta(minutes=5):
                stats["future_posts_skipped"] += 1
                continue
            post_id = status.get("uri") or status.get("url")
            if not isinstance(post_id, str) or not post_id.startswith("http"):
                raise ValueError("Missing stable status URI")
            caption = html_to_text(status.get("content"))
            media_items = status.get("media_attachments") or []
            if not isinstance(media_items, list):
                raise ValueError("Invalid media list")
            image_count = 0
            for index, media in enumerate(media_items):
                if not isinstance(media, dict) or media.get("type") != "image":
                    stats["non_image_attachments"] += 1
                    continue
                url = media.get("url") or media.get("preview_url")
                host = urlsplit(url).hostname if isinstance(url, str) else None
                if host and any(host == h or host.endswith("." + h) for h in ("mastodon.social", "masto.host")):
                    dynamic_hosts.add(host)
                if not isinstance(url, str) or not allowed_url(url, tuple(dynamic_hosts)):
                    stats["invalid_images"] += 1
                    continue
                image_count += 1
                record = MediaRecord(
                    platform="mastodon", collector="mastodon-public-api", post_id=post_id,
                    media_index=index, media_url=url, posted_at=created.isoformat(),
                    caption=caption, alt_text=redact_text(media.get("description")),
                    media_id=str(media.get("id") or ""), location_evidence=[],
                    found_by=list(status.get("_found_by") or []),
                )
                if record.key in seen:
                    stats["duplicate_media_keys"] += 1
                    continue
                seen.add(record.key)
                records.append(record)
            if image_count == 0:
                stats["non_photo_posts_skipped"] += 1
        except (KeyError, ValueError, TypeError, AttributeError):
            stats["invalid_posts"] += 1
    return records, dict(stats), tuple(sorted(dynamic_hosts))


def run(*, config_path=DEFAULT_CONFIG, output=DEFAULT_OUTPUT):
    config = load_config(config_path)
    if config["pool"] == "live" and not 1 <= config["days"] <= 7:
        raise ValueError("Live Mastodon collection uses 1–7 days.")
    if config["pool"] == "training" and not 1 <= config["days"] <= 365:
        raise ValueError("Training Mastodon collection uses 1–365 days.")
    if not 1 <= config["max_images"] <= 500:
        raise ValueError("Use 1–500 Mastodon image downloads.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    since = started - timedelta(days=config["days"])
    with requests.Session() as session:
        session.headers["User-Agent"] = "GeoIssue-Mastodon/0.1"
        statuses, sources = collect(session, config, since=since)
    if not any(source["pages"] for source in sources):
        raise ValueError("All Mastodon sources failed. " +
                         " ".join(error for source in sources for error in source["errors"]))
    records, normalization, hosts = normalize(statuses, since=since, now=started)
    if len(records) > config["max_images"]:
        records = records[:config["max_images"]]
        normalization["images_capped"] = True
    rows = process_media(records, output, hosts=hosts, since=since)
    rows = [{**row, "freshness": assess_freshness(row, since=since)} for row in rows]
    report = {
        "platform": "mastodon", "collector": "mastodon-public-api",
        "instance": config["instance"], "pool": config["pool"],
        "started_at": started.isoformat(), "since": since.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "authenticated": False, "paid_services_used": False,
        "status": "partial" if any(s["errors"] for s in sources) else "ok",
        "sources": sources, "normalization": normalization,
        "image_hosts": list(hosts), "stored_images": len(rows),
        "ready_for_review": sum(r["auto_status"] == "ready" for r in rows),
        "review_status": "downloaded only; run scraping.screen for automatic keep/reject",
    }
    write_jsonl(output / "media.jsonl", rows)
    write_json(output / "mastodon-report.json", report)
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
        parser.exit(1, f"Mastodon collection stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
