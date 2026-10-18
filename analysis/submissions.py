"""Issues people submit in the app: checked here, placed and scored with the pipeline's own reference data and
rules, and stored in Tiger Data (analysis/tiger.py) with their photos exactly as submitted.

A submission with a location is published at once. One sent while Claude is still finding where the photo was
taken waits: when the run ends, the browser that started it sends Claude's answer with the submission's secret
token, and the issue appears then. Submissions are community reports, so they join the collected dataset as
"Needs review", rounded like every other unverified issue.
"""
import base64
import binascii
import hashlib
import hmac
import secrets
from collections import Counter
from datetime import datetime, timezone

from .config import load, stage
from .geo import in_bbox
from .pipeline import _finalise, public_view
from .reference import Reference
from .stages import locate, priority
from .tiger import CATEGORIES, iso

SEVERITIES = ("High", "Medium", "Low")
MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 3 * 1024 * 1024
SIGNATURES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}
STATUSES = ("provided", "locating", "located", "unverified", "not_found")
_reference = None


def config():
    return load()


def reference(cfg):
    global _reference
    if _reference is None:  # the reference files are large; load them once per server
        _reference = Reference(stage(cfg, "locate"))
    return _reference


def new_ids():
    """A public submission ID, and the secret token that lets its browser add Claude's location later."""
    return f"SUB-{secrets.token_hex(5).upper()}", secrets.token_urlsafe(24)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token, stored):
    return isinstance(token, str) and hmac.compare_digest(token_hash(token), stored)


def photo_url(submission_id, position):
    return f"./api/submissions/{submission_id}/photos/{position}"


def _text(value, limit, name, required=False):
    value = "" if value is None else value
    if not isinstance(value, str):
        raise ValueError(f"The {name} must be text")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Add a {name}")
    if len(value) > limit:
        raise ValueError(f"The {name} is longer than {limit} characters")
    return value


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _photo(item):
    if not isinstance(item, dict) or item.get("mime") not in SIGNATURES:
        raise ValueError("Photos must be JPEG, PNG or WebP")
    try:
        data = base64.b64decode(item.get("image") or "", validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise ValueError("A photo is not valid base64") from None
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise ValueError(f"Each photo must be under {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    if not data.startswith(SIGNATURES[item["mime"]]) or (item["mime"] == "image/webp" and data[8:12] != b"WEBP"):
        raise ValueError("A photo's contents don't match its type")
    return item["mime"], data


def _claude(value):
    """What the browser reports about a Claude run: the job, and how sure its answer was."""
    if not isinstance(value, dict):
        return None
    out = {"job_id": _text(value.get("job_id"), 80, "job id") or None, "model": _text(value.get("model"), 40, "model") or None,
           "place_description": _text(value.get("place_description"), 300, "place description") or None}
    if isinstance(value.get("verified"), bool):
        out["verified"] = value["verified"]
    if _number(value.get("radius_m")) and 0 < value["radius_m"] <= 50000:
        out["radius_m"] = round(value["radius_m"])
    return {k: v for k, v in out.items() if v is not None} or None


def location(body, cfg):
    """(status, [lng, lat] or None, Claude run) from a submission or a later location update."""
    status = body.get("location_status") or "provided"
    if status not in STATUSES:
        raise ValueError("Unknown location status")
    claude = _claude(body.get("geolocation"))
    if status in ("locating", "not_found"):
        return status, None, claude
    value = body.get("coordinates")
    if not (isinstance(value, list) and len(value) == 2 and all(_number(v) for v in value)):
        raise ValueError("Coordinates must be [longitude, latitude]")
    bbox = cfg.get("input", {}).get("toronto_bbox")
    if bbox and not in_bbox(bbox, value):
        raise ValueError("The location must be in Toronto")
    return status, [round(float(value[0]), 6), round(float(value[1]), 6)], claude


def parse(body, cfg):
    """The checked submission, and its photos as [(mime, bytes)]."""
    if not isinstance(body, dict):
        raise ValueError("Send the submission as a JSON object")
    if body.get("category") not in CATEGORIES:
        raise ValueError("Choose an issue category")
    severity = body.get("severity") or None
    if severity is not None and severity not in SEVERITIES:
        raise ValueError("Severity must be High, Medium or Low")
    photos = body.get("photos")
    if not isinstance(photos, list) or not 1 <= len(photos) <= MAX_PHOTOS:
        raise ValueError(f"Add between 1 and {MAX_PHOTOS} photos")
    status, coordinates, claude = location(body, cfg)
    if status == "not_found":
        raise ValueError("A submission needs a location, or a Claude run that is still finding it")
    blurred = body.get("blurred_areas") or 0
    if not isinstance(blurred, int) or isinstance(blurred, bool) or not 0 <= blurred <= 1000:
        raise ValueError("blurred_areas must be a count")
    ai = body.get("ai_suggestion")
    ai = {k: ai.get(k) for k in ("category", "severity", "confidence", "model") if isinstance(ai.get(k), (str, int, float))} if isinstance(ai, dict) else None
    submission = {"category": body["category"], "severity": severity,
                  "description": _text(body.get("description"), 2000, "description", required=True),
                  "address": _text(body.get("address"), 200, "address"), "location_status": status,
                  "coordinates": coordinates, "geolocation": claude, "blurred_areas": blurred, "ai_suggestion": ai or None}
    return submission, [_photo(p) for p in photos]


def build_issue(submission_id, submission, created_at, photo_count, cfg, now=None):
    """The public issue for a located submission, made the way the pipeline makes collected issues."""
    now = now or datetime.now(timezone.utc)
    claude = submission.get("geolocation") or {}
    confirmed = submission["location_status"] == "provided"
    if confirmed and not claude.get("radius_m"):
        method, radius, confidence = "Reporter pin", stage(cfg, "locate").get("default_radius_m", 50), 0.9
        trace = [{"stage": "Reporter pin", "result": "Placed on the upload map and confirmed by the reporter", "status": "match"}]
    else:
        verified = bool(claude.get("verified"))
        method = f"Located by Claude · {'verified by street-level imagery' if verified else 'not verified'}"
        radius, confidence = claude.get("radius_m") or 1000, 0.9 if verified else 0.5
        trace = [{"stage": "Claude", "result": f"{claude.get('place_description') or 'Located from the photo'} (±{radius:,} m)",
                  "status": "match" if verified else "info"}]
        if confirmed:
            trace.append({"stage": "Reporter", "result": "Checked Claude's pin on the upload map and confirmed it", "status": "match"})
    created = iso(created_at)
    issue = {
        "issue_id": submission_id, "incident_id": submission_id, "issue_type": submission["category"],
        "severity": submission["severity"], "resolution_status": "Open", "verification_status": "Needs review",
        "geometry": {"type": "Point", "coordinates": submission["coordinates"]}, "location_radius_m": radius,
        "geo_confidence": confidence, "geo_method": method, "geo_trace": trace, "geo_clues": [],
        "address": submission["address"] or None, "sightings_count": 1, "first_seen_at": created, "last_seen_at": created,
        "source_category": "Community submission", "description": submission["description"], "is_demo": False,
        "explanation": f"Submitted in the app by a member of the public. Location method: {method.lower()}. "
                       "A reviewer should confirm the issue and location before any action.",
        "evidence_thumbnail": photo_url(submission_id, 0), "evidence_credit": None,
        "evidence_photos": [{"url": photo_url(submission_id, n), "role": "evidence"} for n in range(photo_count)],
    }
    locate.run([issue], stage(cfg, "locate"), reference(cfg), {"counts": Counter()})
    priority.run([issue], stage(cfg, "priority"), now, {"counts": Counter()})
    if issue["severity"] is None:
        issue["priority_reasons"] = ["Severity not given (+0)" if r.startswith("None severity") else r for r in issue["priority_reasons"]]
    _finalise(issue, cfg, now, reference(cfg).placeholder)
    return public_view(issue, cfg.get("output", {}))
