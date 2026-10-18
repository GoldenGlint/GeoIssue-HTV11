"""Small opt-in social-photo pilots using verified free credit and server charge caps."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import re

import requests

from . import instagram_apify as apify
from ..media import (MediaRecord, allowed_url, parse_time, process_media, redact_text,
                     write_json, write_jsonl)

IMAGE_HOSTS = ("fbcdn.net", "cdninstagram.com")
ACTORS = {"instagram": apify.ACTOR, "facebook": "apify~facebook-posts-scraper",
          "threads": "webdata_labs~threads-scraper"}


def preflight(token, actor, cap=Decimal("0.05")):
    user = apify.api_request(token, "users/me")["data"]
    usage = apify.api_request(token, "users/me/usage/monthly")["data"]
    budget = apify.validate_free_budget(user, usage, cap)
    pricing = apify.active_pricing(apify.api_request(token, f"actors/{actor}")["data"])
    events = (pricing.get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
    if pricing.get("pricingModel") != "PAY_PER_EVENT" or not events:
        raise ValueError("Actor pricing cannot be verified for a bounded free-credit pilot.")
    minimum = pricing.get("minimalMaxTotalChargeUsd")
    if minimum is not None and Decimal(str(minimum)) > cap:
        raise ValueError("Actor minimum charge exceeds the pilot cap.")
    for event in events.values():
        price = ((event.get("eventTieredPricingUsd") or {}).get("FREE") or {}).get("tieredEventPriceUsd")
        if price is None or not Decimal(str(price)).is_finite() or not Decimal("0") <= Decimal(str(price)) <= cap:
            raise ValueError("Actor event pricing does not fit the pilot cap.")
    return budget


def fetch_items(token, actor, body, output, *, cap=Decimal("0.05")):
    """Persist launch intent before POST; a retry can only resume a known run."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "apify-run.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        run_id = state.get("run_id")
        if not run_id:
            raise ValueError("A previous launch has an unknown outcome; inspect Apify before another run.")
    else:
        budget = preflight(token, actor, cap)
        with state_path.open("x") as handle:
            json.dump({"status": "launch_requested", "actor": actor, "cap_usd": float(cap)}, handle)
        run = apify.api_request(token, f"actors/{actor}/runs", method="POST", body=body,
            params={"maxTotalChargeUsd": str(cap), "timeout": 120,
                    "restartOnError": "false", "waitForFinish": 0})["data"]
        run_id = run.get("id")
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9]+", run_id):
            raise ValueError("Apify did not return a valid run ID; do not relaunch blindly.")
        write_json(state_path, {"run_id": run_id, "status": run["status"], "cap_usd": float(cap),
                               "actor": actor, "budget": budget})
    return apify.read_run(token, run_id, output, limit=10)


def normalize(items, platform, *, since, now):
    records, stats = [], Counter()
    for item in items:
        stats["source_items"] += 1
        if not isinstance(item, dict) or item.get("error"):
            stats["source_errors"] += 1
            continue
        try:
            if (item.get("isVideo") or item.get("isRepost") or item.get("sharedPost")
                    or item.get("isSensitive") or item.get("sensitive")):
                stats["video_shared_sensitive_skipped"] += 1
                continue
            if platform == "threads" and item.get("type") != "post":
                stats["non_posts_skipped"] += 1
                continue
            url = item.get("url")
            post_hosts = ("facebook.com",) if platform == "facebook" else ("threads.com", "threads.net")
            if not isinstance(url, str) or not allowed_url(url, post_hosts):
                raise ValueError("Missing canonical public post URL.")
            posted = parse_time(item.get("time") if platform == "facebook" else item.get("date"))
            if not since <= posted <= now + timedelta(minutes=5):
                stats["outside_posting_window"] += 1
                continue
            post_id = item.get("postId") or item.get("id") or url
            found = [f"query:{redact_text(item['searchQuery'])}"] if item.get("searchQuery") else ["curated_public_feed"]
            for index, media in enumerate(item.get("media") or []):
                if not isinstance(media, dict):
                    continue
                if platform == "facebook":
                    if media.get("__typename") != "Photo":
                        stats["non_photo_media"] += 1
                        continue
                    image = (media.get("photo_image") or {}).get("uri") or media.get("thumbnail")
                    alt = media.get("ocrText") or ""
                else:
                    if media.get("type") not in ("image", "photo"):
                        stats["non_photo_media"] += 1
                        continue
                    image, alt = media.get("url"), media.get("altText") or ""
                if not isinstance(image, str) or not allowed_url(image, IMAGE_HOSTS):
                    stats["invalid_image_hosts"] += 1
                    continue
                records.append(MediaRecord(platform=platform, collector=f"apify/{ACTORS[platform]}",
                    post_id=str(post_id), media_index=index, media_url=image,
                    posted_at=posted.isoformat(), caption=redact_text(item.get("text")),
                    alt_text=redact_text(alt), media_id=str(media.get("id") or f"{post_id}-{index}"),
                    found_by=found, post_url=url))
        except (ValueError, TypeError, KeyError, AttributeError):
            stats["invalid_posts"] += 1
    return records, dict(stats)


def run_pilots(root):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    after = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    inputs = {
        "instagram": {"directUrls": ["https://www.instagram.com/cycletoronto/",
                                     "https://www.instagram.com/thebikinglawyer/"],
                      "resultsType": "posts", "resultsLimit": 5,
                      "addParentData": False, "onlyPostsNewerThan": after},
        "facebook": {"startUrls": [{"url": "https://www.facebook.com/cycletoronto"}],
                     "resultsLimit": 5, "onlyPostsNewerThan": after, "captionText": False},
        "threads": {"mode": "search", "searchQueries": ["Toronto sidewalk", "Bloor bike lane", "Toronto garbage"],
                    "maxPosts": 3, "includeProfile": False, "postedAfter": after},
    }
    reports = []
    for platform, body in inputs.items():
        output = Path(root) / platform
        result = {"platform": platform, "actor": ACTORS[platform], "cap_usd": 0.05,
                  "out_of_pocket_usd": 0, "status": "pending"}
        try:
            token = apify.load_token()
            items = fetch_items(token, ACTORS[platform], body, output)
            # Raw actor output remains in ignored local storage for response-shape inspection.
            write_json(output / "items.json", items)
            records, stats = apify.normalize(items) if platform == "instagram" else normalize(items, platform, since=since, now=now)
            if platform == "instagram":
                for record in records:
                    record.found_by = ["curated_public_feed"]
            rows = process_media(records, output, hosts=IMAGE_HOSTS, since=since)
            state = json.loads((output / "apify-run.json").read_text())
            result.update(status="ok", normalization=stats, images=len(rows),
                          ready_images=sum(row["auto_status"] == "ready" for row in rows),
                          charged_credit_usd=state.get("charged_credit_usd"))
            if rows:
                result["batch"] = str(output.resolve())
        except (ValueError, OSError, requests.RequestException) as error:
            result.update(status="unavailable", error=str(error).replace(locals().get("token", "") or "<no-token>", "[token]")[:240])
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "pilot-report.json", result)
        reports.append(result)
        print(f"{platform} pilot: {result['status']}; {result.get('ready_images', 0)} photos.", flush=True)
    return reports
