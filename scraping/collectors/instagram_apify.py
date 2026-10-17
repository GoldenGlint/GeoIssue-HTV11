"""Apify-only adapter. Other providers need not depend on this module."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
import time

import requests

from ..media import MediaRecord, parse_time, redact_text, write_json
from ..paths import ROOT
from .instagram_urls import target_kind

ACTOR = "apify~instagram-scraper"
IMAGE_HOSTS = ("cdninstagram.com", "fbcdn.net")
MAX_FREE_CREDIT = Decimal("0.05")


def load_token():
    token = os.environ.get("APIFY_TOKEN", "")
    path = ROOT / ".env"
    if not token and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("APIFY_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
    if not token or any(character.isspace() for character in token):
        raise ValueError("Add APIFY_TOKEN to scraping/.env before a live run.")
    return token


def api_request(token, path, *, method="GET", body=None, params=None):
    # No query-string tokens, automatic POST retries, or credential-bearing redirects.
    try:
        response = requests.request(method, "https://api.apify.com/v2/" + path,
                                    headers={"Authorization": "Bearer " + token},
                                    params=params, json=body, timeout=(10, 30), allow_redirects=False)
    except requests.RequestException:
        raise ValueError("Apify connection failed. Run-start requests are never retried automatically.") from None
    if not 200 <= response.status_code < 300:
        try:
            error_body = response.json().get("error", {})
            error = error_body.get("type", "request-failed")
            detail = redact_text(str(error_body.get("message", "")).replace(token, "[token]"))[:250]
        except ValueError:
            error = "request-failed"
            detail = ""
        error = error if re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", str(error)) else "request-failed"
        raise ValueError(f"Apify returned HTTP {response.status_code} ({error}). {detail}")
    return response.json()


def validate_free_budget(user, usage, cap):
    """Fail closed when account type, pricing, or usage cannot be established."""
    cap = Decimal(str(cap))
    plan = user.get("plan", {})
    if (plan.get("tier") != "FREE" or plan.get("isEnabled") is not True
            or user.get("isPaying") is not False
            or plan.get("monthlyBasePriceUsd") != 0):
        raise ValueError("Only an enabled, non-paying Apify Free-plan account is permitted.")
    if not cap.is_finite() or not Decimal("0") < cap <= MAX_FREE_CREDIT:
        raise ValueError("This demo permits at most US$0.05 of free credit per run.")
    try:
        credit = Decimal(str(plan["monthlyUsageCreditsUsd"]))
        used = Decimal(str(usage["totalUsageCreditsUsdAfterVolumeDiscount"]))
        limit = Decimal(str(plan["maxMonthlyUsageUsd"]))
    except (KeyError, InvalidOperation):
        raise ValueError("Could not verify the remaining free credit.") from None
    if not all(value.is_finite() for value in (credit, used, limit)) or used < 0:
        raise ValueError("Invalid account credit information.")
    remaining = min(credit, limit) - used
    if remaining < cap + Decimal("0.10"):
        raise ValueError("Insufficient verified free credit, including a small reserve.")
    return {"plan": "FREE", "remaining_free_credit_usd": float(remaining),
            "run_cap_usd": float(cap), "out_of_pocket_usd": 0}


def active_pricing(actor, now=None):
    now = now or datetime.now(timezone.utc)
    prices = [info for info in actor.get("pricingInfos", [])
              if info.get("startedAt") and parse_time(info["startedAt"]) <= now]
    if not prices:
        raise ValueError("Could not verify the actor's current pricing.")
    return max(prices, key=lambda info: parse_time(info["startedAt"]))


def preflight(token, cap=MAX_FREE_CREDIT):
    user = api_request(token, "users/me")["data"]
    usage = api_request(token, "users/me/usage/monthly")["data"]
    summary = validate_free_budget(user, usage, cap)
    pricing = active_pricing(api_request(token, f"actors/{ACTOR}")["data"])
    if pricing.get("pricingModel") != "PAY_PER_EVENT":
        raise ValueError("Unexpected actor pricing model; refusing to start.")
    minimum = pricing.get("minimalMaxTotalChargeUsd")
    if minimum is None or Decimal(str(minimum)) > Decimal(str(cap)):
        raise ValueError("The actor cannot honor the requested US$0.05 cap.")
    return summary


def normalize(items):
    if not isinstance(items, list):
        raise ValueError("Expected an Apify dataset export containing a JSON list.")
    records = []
    stats = {"source_items": len(items), "video_items_skipped": 0,
             "non_media_items": 0, "source_errors": 0, "invalid_items": 0, "incomplete_carousels": 0}
    for item in items:
        if isinstance(item, dict) and item.get("error"):
            stats["source_errors"] += 1
            continue
        if not isinstance(item, dict) or item.get("type") not in ("Image", "Sidecar", "Video"):
            stats["non_media_items"] += 1
            continue
        post_id = str(item.get("id") or item.get("shortCode") or "")
        if not post_id:
            stats["invalid_items"] += 1
            continue
        children = item.get("childPosts") if item["type"] == "Sidecar" else [item]
        if not children or not isinstance(children, list):
            stats["incomplete_carousels"] += 1
            continue
        name = item.get("locationName") or (item.get("location") or {}).get("name")
        evidence = ([{"kind": "place_tag", "text": redact_text(name),
                      "precision": "place", "camera_location_verified": False}] if name else [])
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                stats["invalid_items"] += 1
                continue
            if child.get("type") == "Video" or child.get("isVideo") is True:
                stats["video_items_skipped"] += 1
                continue
            url = child.get("displayUrl")
            if not isinstance(url, str) or not url:
                stats["invalid_items"] += 1
                continue
            try:
                records.append(MediaRecord(
                    platform="instagram", collector="apify/instagram-scraper", post_id=post_id,
                    media_index=index, media_url=url, posted_at=item.get("timestamp"),
                    caption=redact_text(item.get("caption")), alt_text=redact_text(child.get("alt")),
                    media_id=str(child["id"]) if child.get("id") else None,
                    location_evidence=evidence,
                ))
            except (ValueError, TypeError, AttributeError):
                stats["invalid_items"] += 1
    return records, stats


def collect(token, urls, output, *, limit=10, cap=MAX_FREE_CREDIT, since=None):
    if not 1 <= limit <= 10 or not urls or len(urls) > limit:
        raise ValueError("Use 1–10 posts total and no more URLs than posts.")
    kinds = {target_kind(url) for url in urls}
    if len(kinds) != 1:
        raise ValueError("Test profiles, posts, tags, and locations in separate runs.")
    output = Path(output)
    # Existing launch intent also blocks a blind retry after a lost HTTP response.
    output.mkdir(parents=True, exist_ok=True)
    state = output / "apify-run.json"
    if state.exists():
        raise ValueError("A run is already associated with this directory. Use resume to avoid another charge.")
    summary = preflight(token, cap)
    body = {"directUrls": urls, "resultsType": "posts", "resultsLimit": max(1, limit // len(urls)),
            "addParentData": False}
    if since:
        body["onlyPostsNewerThan"] = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with state.open("x", encoding="utf-8") as handle:
        import json
        handle.write(json.dumps({"status": "launch_requested", "cap_usd": float(cap)}) + "\n")
    run = api_request(token, f"actors/{ACTOR}/runs", method="POST", body=body,
                      params={"maxTotalChargeUsd": str(cap), "timeout": 120,
                              "restartOnError": "false", "waitForFinish": 0})["data"]
    run_id = run["id"]
    if not re.fullmatch(r"[A-Za-z0-9]+", run_id):
        raise ValueError("Apify returned an invalid run identifier.")
    write_json(state, {"run_id": run_id, "status": run["status"], "cap_usd": float(cap)})
    return read_run(token, run_id, output, limit=limit), summary


def read_run(token, run_id, output, *, limit=10):
    if not re.fullmatch(r"[A-Za-z0-9]+", run_id):
        raise ValueError("Invalid Apify run identifier.")
    deadline = time.monotonic() + 150
    while True:
        run = api_request(token, f"actor-runs/{run_id}")["data"]
        write_json(Path(output) / "apify-run.json", {
            "run_id": run_id, "status": run["status"],
            "charged_credit_usd": run.get("usageTotalUsd"),
            "cap_usd": run.get("options", {}).get("maxTotalChargeUsd"),
        })
        if run["status"] not in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
            break
        if time.monotonic() > deadline:
            raise ValueError("Run is still pending. Resume this run rather than starting another.")
        time.sleep(3)
    if run["status"] != "SUCCEEDED":
        raise ValueError(f"Apify run ended with status {run['status']}. Its ID is saved for inspection.")
    dataset = run.get("defaultDatasetId", "")
    if not re.fullmatch(r"[A-Za-z0-9]+", dataset):
        raise ValueError("No valid result dataset was returned.")
    return api_request(token, f"datasets/{dataset}/items", params={"format": "json", "clean": "true", "limit": limit})
