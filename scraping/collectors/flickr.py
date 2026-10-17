"""Bounded Flickr geographic photo collection using the shared media pipeline.

Requires FLICKR_API_KEY in scraping/.env. Public photos only. Capture dates are
kept as uncertain evidence because Flickr may default taken-date to upload time.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

import requests

from ..media import (MediaRecord, allowed_url, assess_freshness, process_media,
                    redact_text, write_gallery, write_json, write_jsonl)
from ..paths import CONFIG, DATA, REVIEW_TEMPLATE, ROOT

DEFAULT_CONFIG = CONFIG / "flickr.json"
DEFAULT_OUTPUT = DATA / "flickr"
API = "https://api.flickr.com/services/rest/"
IMAGE_HOSTS = ("staticflickr.com", "live.staticflickr.com")


def load_api_key():
    token = os.environ.get("FLICKR_API_KEY", "")
    path = ROOT / ".env"
    if not token and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("FLICKR_API_KEY="):
                token = line.split("=", 1)[1].strip().strip("\"'")
    if not token or any(character.isspace() for character in token):
        raise ValueError(
            "Add FLICKR_API_KEY to scraping/.env before the Flickr pilot. "
            "No Flickr collection was run without a key.")
    return token


def load_config(path=DEFAULT_CONFIG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    areas = data.get("areas") or []
    if not areas or len(areas) > 6:
        raise ValueError("Configure 1–6 Flickr areas with bbox arrays.")
    for area in areas:
        box = area.get("bbox")
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError("Each Flickr area needs a 4-number bbox.")
    return {
        "areas": areas,
        "terms": [str(term) for term in data.get("terms") or [""]],
        "per_request": int(data.get("per_request") or 25),
        "max_images": int(data.get("max_images") or 50),
        "days": int(data.get("days") or 7),
        "pool": data.get("pool") or "live",
        "require_geo": bool(data.get("require_geo", True)),
        "outdoor_context": bool(data.get("outdoor_context", True)),
    }


def api_get(session, key, method, params):
    query = {"method": method, "api_key": key, "format": "json", "nojsoncallback": 1, **params}
    try:
        response = session.get(API, params=query, timeout=(10, 30), allow_redirects=False)
    except requests.RequestException as exc:
        raise ValueError("Flickr connection failed.") from exc
    if response.status_code != 200:
        raise ValueError(f"Flickr returned HTTP {response.status_code}.")
    payload = response.json()
    if payload.get("stat") != "ok":
        raise ValueError(f"Flickr API error: {payload.get('message') or payload.get('code')}")
    return payload


def collect(session, key, config, *, since):
    photos, sources = {}, []
    min_upload = int(since.timestamp())
    for area in config["areas"]:
        for term in config["terms"]:
            source = {"kind": "bbox", "area": area["name"], "term": term or "(none)",
                      "returned": 0, "errors": []}
            sources.append(source)
            params = {
                "bbox": ",".join(str(value) for value in area["bbox"]),
                "media": "photos",
                "sort": "date-posted-desc",
                "per_page": min(25, config["per_request"]),
                "page": 1,
                "extras": "date_upload,date_taken,owner_name,geo,url_l,url_c,url_o,license,description",
                "min_upload_date": min_upload,
            }
            if config["outdoor_context"]:
                params["geo_context"] = 2
            if term:
                params["text"] = term
            try:
                payload = api_get(session, key, "flickr.photos.search", params)
                items = (((payload.get("photos") or {}).get("photo")) or [])
                source["returned"] = len(items)
                for photo in items:
                    if isinstance(photo, dict) and photo.get("id"):
                        photos.setdefault(str(photo["id"]), photo)
            except ValueError as exc:
                source["errors"].append(str(exc))
    return list(photos.values()), sources


def normalize(photos, *, since, now):
    records, stats, seen = [], Counter(), set()
    for photo in photos:
        stats["photos_inspected"] += 1
        try:
            photo_id = str(photo["id"])
            uploaded = datetime.fromtimestamp(int(photo["dateupload"]), tz=timezone.utc)
            if uploaded < since:
                stats["older_posts_skipped"] += 1
                continue
            if uploaded > now + timedelta(minutes=5):
                stats["future_posts_skipped"] += 1
                continue
            url = photo.get("url_l") or photo.get("url_c") or photo.get("url_o")
            if not isinstance(url, str) or not allowed_url(url, IMAGE_HOSTS):
                stats["invalid_images"] += 1
                continue
            evidence = []
            if photo.get("latitude") and photo.get("longitude"):
                evidence.append({
                    "kind": "flickr_geo",
                    "lat": float(photo["latitude"]),
                    "lon": float(photo["longitude"]),
                    "accuracy": photo.get("accuracy"),
                    "precision": "source_claim",
                    "camera_location_verified": False,
                })
            date_evidence = {
                "datetaken": photo.get("datetaken"),
                "datetakengranularity": photo.get("datetakengranularity"),
                "dateupload": photo.get("dateupload"),
                "note": "Flickr taken date may default to upload time; capture age uncertain.",
            }
            description = photo.get("description")
            if isinstance(description, dict):
                description = description.get("_content")
            caption = redact_text(f"{photo.get('title') or ''}\n{description or ''}".strip())
            record = MediaRecord(
                platform="flickr", collector="flickr-api", post_id=photo_id,
                media_index=0, media_url=url, posted_at=uploaded.isoformat(),
                caption=caption, alt_text="", media_id=photo_id,
                location_evidence=evidence, captured_at=None,
            )
            if record.key in seen:
                stats["duplicate_media_keys"] += 1
                continue
            seen.add(record.key)
            # Attach date evidence after MediaRecord validation via row merge later.
            records.append((record, date_evidence, photo.get("license")))
        except (KeyError, ValueError, TypeError, AttributeError):
            stats["invalid_posts"] += 1
    return records, dict(stats)


def run(*, config_path=DEFAULT_CONFIG, output=DEFAULT_OUTPUT, key=None):
    config = load_config(config_path)
    key = key or load_api_key()
    if config["pool"] == "live" and not 1 <= config["days"] <= 7:
        raise ValueError("Live Flickr collection uses 1–7 days.")
    if config["pool"] == "training" and not 1 <= config["days"] <= 365:
        raise ValueError("Training Flickr collection uses 1–365 days.")
    if not 1 <= config["max_images"] <= 200:
        raise ValueError("Use 1–200 Flickr image downloads.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    since = started - timedelta(days=config["days"])
    with requests.Session() as session:
        session.headers["User-Agent"] = "CivicLens-Flickr/0.1"
        photos, sources = collect(session, key, config, since=since)
    packed, normalization = normalize(photos, since=since, now=started)
    packed = packed[:config["max_images"]]
    records = [item[0] for item in packed]
    rows = process_media(records, output, hosts=IMAGE_HOSTS, since=since)
    by_key = {record.key: (date_evidence, license_) for record, date_evidence, license_ in packed}
    enriched = []
    for row in rows:
        date_evidence, license_ = by_key.get(row["key"], ({}, None))
        enriched.append({
            **row,
            "freshness": assess_freshness(row, since=since),
            "date_evidence": date_evidence,
            "license": license_,
        })
    report = {
        "platform": "flickr", "collector": "flickr-api", "pool": config["pool"],
        "started_at": started.isoformat(), "since": since.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "authenticated": False, "paid_services_used": False,
        "status": "partial" if any(s["errors"] for s in sources) else "ok",
        "sources": sources, "normalization": normalization,
        "stored_images": len(enriched),
        "ready_for_review": sum(r["auto_status"] == "ready" for r in enriched),
        "capture_date_note": "Taken dates are retained as uncertain evidence, never as verified capture time.",
        "review_status": "downloaded only; run scraping.screen for automatic keep/reject",
    }
    write_jsonl(output / "media.jsonl", enriched)
    write_json(output / "flickr-report.json", report)
    if REVIEW_TEMPLATE.is_file():
        write_gallery(output, enriched, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        report = run(config_path=args.config, output=args.output)
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"Flickr collection stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
