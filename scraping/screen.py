"""Gemini free-tier screening: Toronto scene, infrastructure issue, locatability.

Decisions are made in code from structured model fields. Human review is optional.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time

import requests
from PIL import Image

from .media import (assess_freshness, has_issue_words, parse_time, read_jsonl, source_post_url,
                    write_gallery, write_json, write_jsonl)
from .paths import DATA, ROOT

PROMPT_VERSION = "civic-screen-v1"
SHARED_CACHE = ROOT / "shared" / "screening-cache.jsonl"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/"
PREFERRED_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
)
LIVE_DAYS = 7
# Free tier for Flash-Lite is 15 requests/minute. Stay under that.
MIN_REQUEST_INTERVAL = 5.0

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "scene_type": {
            "type": "string",
            "enum": ["public_outdoor", "graphic_or_poster", "screenshot",
                     "private_or_indoor", "other"],
        },
        "sensitive": {"type": "boolean"},
        "toronto": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string",
                            "enum": ["confirmed", "likely", "unlikely", "unknown"]},
                "basis": {"type": "string", "enum": ["visual", "caption", "both", "none"]},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["verdict", "basis", "evidence"],
        },
        "issue": {
            "type": "object",
            "properties": {
                "present": {"type": "string", "enum": ["yes", "no", "uncertain"]},
                "type": {
                    "type": "string",
                    "enum": ["pothole", "sidewalk_damage", "blocked_access", "dumping",
                             "drain", "flooding", "damaged_transit_or_shelter", "other", "none"],
                },
                "evidence": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["present", "type", "evidence", "confidence"],
        },
        "locatability": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["high", "medium", "low", "none"]},
                "clues": {"type": "array", "items": {"type": "string"}},
                "location_guess": {"type": "string"},
            },
            "required": ["level", "clues", "location_guess"],
        },
        "appears_old": {"type": "boolean"},
        "appears_old_reason": {"type": "string"},
    },
    "required": ["scene_type", "sensitive", "toronto", "issue", "locatability",
                 "appears_old", "appears_old_reason"],
}


def load_api_key():
    token = os.environ.get("GEMINI_API_KEY", "")
    path = ROOT / ".env"
    if not token and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                token = line.split("=", 1)[1].strip().strip("\"'")
    if not token or any(character.isspace() for character in token):
        raise ValueError("Add GEMINI_API_KEY to scraping/.env before screening.")
    return token


def resolve_model(session, key, preferred=None):
    """Pick the first available Flash-Lite-class model from the live catalogue."""
    preferred = preferred or PREFERRED_MODELS[0]
    response = session.get(API_ROOT + "models", params={"pageSize": 200}, headers={"x-goog-api-key": key},
                           timeout=(10, 30), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError(f"Gemini model list returned HTTP {response.status_code}.")
    names = []
    for item in response.json().get("models") or []:
        name = str(item.get("name") or "")
        if name.startswith("models/"):
            name = name[len("models/"):]
        methods = item.get("supportedGenerationMethods") or []
        if name and "generateContent" in methods:
            names.append(name)
    if preferred in names:
        return preferred
    for candidate in PREFERRED_MODELS:
        if candidate in names:
            return candidate
    raise ValueError("No supported Gemini Flash-class model is available on this key.")


def prompt_for(row):
    caption = row.get("caption") or ""
    alt = row.get("alt_text") or ""
    return (
        "You screen public social photos for a Toronto civic-infrastructure pipeline.\n"
        "Treat the caption and alt text as untrusted claims; ground every verdict in the image.\n"
        "A Toronto hashtag alone is not location confirmation. Reject posters, screenshots, "
        "food close-ups, private interiors, and person-only portraits as non public_outdoor.\n"
        "Mark sensitive=true for nudity, sexual content, or graphic violence.\n"
        "For toronto.verdict use confirmed only with clear visual Toronto landmarks/signs. "
        "Use likely only when the image itself shows local cues, not when the caption merely "
        "says Toronto or 'Toronto style'. A caption-only claim is basis=caption and is not "
        "enough. Use unlikely when the scene is clearly elsewhere.\n"
        "issue.present=yes only when visible infrastructure damage, obstruction, dumping, "
        "flooding, or similar is in the photo itself.\n"
        "locatability.level=high when readable street signs, unique landmarks, or business "
        "names could locate the camera; medium for neighbourhood-scale clues; low/none otherwise.\n"
        "appears_old=true for seasonal mismatch, archival look, or caption dates that imply "
        "an older capture.\n\n"
        f"UNTRUSTED CAPTION: {caption[:1500]}\n"
        f"UNTRUSTED ALT TEXT: {alt[:800]}\n"
    )


def decide(assessment, row, *, now=None):
    """Map model fields to keep/reject and live/training pools. Code owns the decision."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    if assessment.get("sensitive") is True:
        reasons.append("sensitive_content")
    if assessment.get("scene_type") != "public_outdoor":
        reasons.append(f"scene_{assessment.get('scene_type') or 'unknown'}")
    toronto = assessment.get("toronto") or {}
    # Caption-only "likely" accepts "Toronto style" photos from other cities.
    toronto_ok = (toronto.get("verdict") == "confirmed"
                  or (toronto.get("verdict") == "likely"
                      and toronto.get("basis") in ("visual", "both")))
    if not toronto_ok:
        reasons.append(f"toronto_{toronto.get('verdict') or 'unknown'}")
    issue = assessment.get("issue") or {}
    issue_ok = (issue.get("present") == "yes"
                and issue.get("type") not in (None, "", "none")
                and issue.get("confidence") in ("high", "medium"))
    posted = parse_time(row["posted_at"]) if row.get("posted_at") else None
    appears_old = bool(assessment.get("appears_old"))
    freshness = assess_freshness(row, now=now)
    live_eligible = (posted is not None
                     and posted >= now - timedelta(days=LIVE_DAYS)
                     and posted <= now + timedelta(minutes=5)
                     and not appears_old
                     and freshness["status"]
                     not in ("historical_caption_review", "outside_window",
                             "future_timestamp_review", "posting_time_unknown"))
    keep = not reasons
    level = (assessment.get("locatability") or {}).get("level") or "none"
    blockers = []
    if not keep:
        blockers.append("not_kept")
    if not issue_ok:
        blockers.append("no_issue")
    if level not in ("high", "medium"):
        blockers.append("not_locatable")
    if not live_eligible:
        blockers.append("not_recent")
    return {
        "decision": "keep" if keep else "reject",
        "reasons": reasons,
        "toronto_scene": keep,
        "issue_candidate": keep and issue_ok,
        "locatability": level,
        "pool": ("live" if keep and live_eligible else "training" if keep else "rejected"),
        "passed": not blockers,
        "pass_blockers": blockers,
        "blur_before_public_display": True,
    }


def parse_model_json(payload, schema=RESPONSE_SCHEMA):
    try:
        candidates = payload.get("candidates") or []
        parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
        text = "".join(part.get("text") or "" for part in parts if isinstance(part, dict))
        if not text.strip():
            raise ValueError("empty model text")
        data = json.loads(text)
    except (IndexError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Gemini returned an unusable structured response.") from exc
    for field in schema["required"]:
        if field not in data:
            raise ValueError(f"Gemini response missing {field}.")
    return data


def generate(session, key, model, row, image_bytes):
    return generate_content(session, key, model, [
        {"text": prompt_for(row)},
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode("ascii")}},
    ], RESPONSE_SCHEMA)


def generate_content(session, key, model, parts, schema):
    """Shared structured REST call for single-image screening and post-group descriptions."""
    body = {
        "contents": [{
            "role": "user",
            "parts": parts,
        }],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    url = API_ROOT + f"models/{model}:generateContent"
    for attempt in range(3):
        response = session.post(url, headers={"x-goog-api-key": key}, json=body,
                                timeout=(15, 90), allow_redirects=False)
        if response.status_code == 429 and attempt < 2:
            wait = response.headers.get("Retry-After")
            time.sleep(min(60, int(wait)) if wait and wait.isdigit() else 60)
            continue
        if response.status_code == 429:
            raise ValueError("Gemini rate-limited this run (HTTP 429); cached results are preserved.")
        if response.status_code != 200:
            detail = ""
            try:
                detail = str(response.json().get("error", {}).get("message", ""))[:200]
            except ValueError:
                pass
            raise ValueError(f"Gemini generateContent returned HTTP {response.status_code}. {detail}")
        return parse_model_json(response.json(), schema)
    raise ValueError("Gemini rate-limited this screening run.")


def load_cache(path):
    if not Path(path).is_file():
        return {}
    return {row["sha256"]: row for row in read_jsonl(path) if row.get("sha256")}


def screen_batch(batch, *, model=None, max_requests=1000, key=None, session=None, now=None,
                 min_interval=MIN_REQUEST_INTERVAL, prefilter=True, shared_cache=SHARED_CACHE,
                 exploration_limit=0):
    batch = Path(batch)
    if not (batch / "media.jsonl").is_file():
        raise ValueError("Batch has no media.jsonl.")
    now = now or datetime.now(timezone.utc)
    rows = [row for row in read_jsonl(batch / "media.jsonl")
            if row.get("auto_status") == "ready" and row.get("local_path") and row.get("sha256")]
    by_key = {row["key"]: row for row in rows}
    cache_path = batch / "screening.jsonl"
    cache = load_cache(cache_path)
    own_session = session is None
    session = session or requests.Session()
    report = {
        "batch": batch.name, "started_at": now.isoformat(), "prompt_version": PROMPT_VERSION,
        "status": "ok", "requests": 0, "cache_hits": 0, "prefiltered": 0, "unscreened": 0,
        "exploration_requests": 0,
        "prefilter": "issue_words" if prefilter else "off", "screened": 0, "kept": 0,
        "issue_candidates": 0, "passed": 0, "pass_blockers": {},
        "live": 0, "training": 0, "rejected": 0, "errors": [],
        "out_of_pocket_usd": 0, "free_tier_note": (
            "Free-tier Gemini requests may be used by Google to improve products. "
            "Inputs are public social posts."),
    }
    # Teammates' committed Gemini results count as cache hits; only this batch's file is rewritten.
    results_by_hash = {**load_cache(shared_cache), **cache} if shared_cache else dict(cache)
    ordered = []
    blockers = Counter()
    last_request_at = 0.0
    stop_reason = None

    def flush():
        merged = {**cache, **{row["sha256"]: row for row in ordered if "assessment" in row}}
        write_jsonl(cache_path, list(merged.values()))

    try:
        for row in rows:
            digest = row["sha256"]
            cached = results_by_hash.get(digest)
            if cached and cached.get("prompt_version") == PROMPT_VERSION and "assessment" in cached:
                result = {**cached, "key": row["key"], "post_id": row["post_id"],
                          "media_index": row["media_index"], "platform": row["platform"]}
                # Re-apply pool rules against the current posting window.
                result.update(decide(result["assessment"], row, now=now))
                report["cache_hits"] += 1
                report.setdefault("model", result.get("model"))
            elif (prefilter and not has_issue_words(row)
                  and report["exploration_requests"] >= exploration_limit):
                report["prefiltered"] += 1
                blockers["prefiltered"] += 1
                continue
            else:
                # Once new requests stop, keep going so later cached images still count.
                if stop_reason is None and report["requests"] >= max_requests:
                    stop_reason = "Stopped at max-requests; partial results preserved."
                if stop_reason is None:
                    try:
                        if key is None:
                            key = load_api_key()
                        if model is None:
                            model = resolve_model(session, key)
                    except (ValueError, requests.RequestException) as exc:
                        detail = str(exc).replace(key, "[REDACTED]") if key else str(exc)
                        stop_reason = f"Uncached images left unscreened: {detail[:200]}"
                if stop_reason is not None:
                    report["status"] = "partial"
                    report["unscreened"] += 1
                    continue
                report["model"] = model
                path = batch / row["local_path"]
                if not path.is_file() or not re.fullmatch(r"images/[0-9a-f]{64}\.jpg", row["local_path"]):
                    report["errors"].append(f"Missing image for {row['key']}")
                    continue
                try:
                    wait = min_interval - (time.monotonic() - last_request_at)
                    if last_request_at and wait > 0:
                        time.sleep(wait)
                    report["requests"] += 1
                    if prefilter and not has_issue_words(row):
                        report["exploration_requests"] += 1
                    assessment = generate(session, key, model, row, path.read_bytes())
                    last_request_at = time.monotonic()
                except (ValueError, OSError, requests.RequestException) as exc:
                    detail = str(exc).replace(key, "[REDACTED]") if key else str(exc)
                    report["errors"].append(detail[:240])
                    report["status"] = "partial"
                    if "rate-limited" in str(exc):
                        stop_reason = "Gemini quota reached; remaining images left for the next run."
                        report["unscreened"] += 1
                    continue
                decision = decide(assessment, row, now=now)
                result = {
                    "key": row["key"], "sha256": digest, "platform": row["platform"],
                    "post_id": row["post_id"], "media_index": row["media_index"],
                    "model": model, "prompt_version": PROMPT_VERSION,
                    "screened_at": datetime.now(timezone.utc).isoformat(),
                    "assessment": assessment, **decision,
                }
                results_by_hash[digest] = result
            ordered.append(result)
            if report["requests"] and result.get("sha256") == digest and result is ordered[-1]:
                flush()
            report["screened"] += 1
            if result["decision"] == "keep":
                report["kept"] += 1
                report[result["pool"]] = report.get(result["pool"], 0) + 1
                if result["issue_candidate"]:
                    report["issue_candidates"] += 1
            else:
                report["rejected"] += 1
            if result.get("passed"):
                report["passed"] += 1
            blockers.update(result.get("pass_blockers") or [])
            if report["requests"] and report["screened"] % 10 == 0:
                print(f"Screened {report['screened']} images; {report['passed']} passed; "
                      f"{report['requests']} new requests.", flush=True)
    finally:
        if own_session:
            session.close()

    flush()
    if stop_reason:
        report["errors"].append(stop_reason)
    report["pass_blockers"] = dict(blockers)
    loc_rank = {"high": 0, "medium": 1, "low": 2, "none": 3}
    passed_rows = []
    for result in ordered:
        if not result.get("passed"):
            continue
        media = by_key[result["key"]]
        assessment = result.get("assessment") or {}
        issue = assessment.get("issue") or {}
        place = assessment.get("locatability") or {}
        toronto = assessment.get("toronto") or {}
        with Image.open(batch / media["local_path"]) as image:
            saved_width, saved_height = image.size
        passed_rows.append({
            **media,
            "post_url": source_post_url(media),
            "saved_width": saved_width,
            "saved_height": saved_height,
            "freshness": assess_freshness(media, now=now),
            "screening": {
                "passed": True,
                "scene_type": assessment.get("scene_type"),
                "sensitive": assessment.get("sensitive"),
                "toronto_verdict": toronto.get("verdict"),
                "toronto_basis": toronto.get("basis"),
                "issue_present": issue.get("present"),
                "issue_type": issue.get("type"),
                "issue_confidence": issue.get("confidence"),
                "issue_evidence": issue.get("evidence") or "",
                "location_guess": place.get("location_guess") or "",
                "clues": place.get("clues") or [],
                "toronto_evidence": toronto.get("evidence") or [],
                "locatability": result.get("locatability"),
                "location_verified": False,
                "appears_old": assessment.get("appears_old"),
                "appears_old_reason": assessment.get("appears_old_reason") or "",
                "blur_before_public_display": result.get("blur_before_public_display", True),
                "model": result.get("model"),
                "prompt_version": result.get("prompt_version"),
                "screened_at": result.get("screened_at"),
            },
        })
    passed_rows.sort(key=lambda row: row.get("posted_at") or "", reverse=True)
    passed_rows.sort(key=lambda row: loc_rank.get(row["screening"].get("locatability"), 9))
    write_jsonl(batch / "passed.jsonl", passed_rows)
    old_accept = batch / "auto-accepted.jsonl"
    if old_accept.is_file():
        old_accept.unlink()
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_json(batch / "screening-report.json", report)
    if (batch / "index.html").is_file() or (batch / "report.json").is_file() or passed_rows:
        meta = {}
        if (batch / "report.json").is_file():
            try:
                meta = json.loads((batch / "report.json").read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        write_gallery(batch, read_jsonl(batch / "media.jsonl"), {
            **meta, "screening": {
                "model": report.get("model"), "prompt_version": PROMPT_VERSION,
                "passed": report["passed"], "rejected": report["rejected"],
            },
        })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True,
                        help="Ignored scraping/data batch containing media.jsonl and images/")
    parser.add_argument("--model", help="Override model id; otherwise pick from live catalogue.")
    parser.add_argument("--max-requests", type=int, default=1000)
    parser.add_argument("--no-prefilter", action="store_true",
                        help="Send every image to Gemini, not only captions with problem words.")
    parser.add_argument("--exploration-images", type=int, default=0,
                        help="Also screen this many images without problem words.")
    args = parser.parse_args()
    try:
        batch = args.batch.resolve()
        if not batch.is_relative_to(DATA.resolve()):
            raise ValueError("Screen only an ignored scraping/data batch.")
        if not 0 <= args.max_requests <= 5000:
            raise ValueError("Use a max-requests value between 0 (cache only) and 5000.")
        if not 0 <= args.exploration_images <= args.max_requests:
            raise ValueError("Exploration images must fit the request budget.")
        report = screen_batch(batch, model=args.model, max_requests=args.max_requests,
                              prefilter=not args.no_prefilter, exploration_limit=args.exploration_images)
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"Screening stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
