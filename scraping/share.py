"""Share passed images and Gemini results through git without committing image files.

  export  scraping/data -> scraping/shared (text only: passed records + Gemini cache)
  pull    scraping/shared -> scraping/data/handoff (re-downloads passed images, checks sha256)

The repository is public, so images stay out of git until faces are censored downstream.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

import requests
from PIL import Image

from .media import fetch_image, image_derivative, read_jsonl, write_gallery, write_json, write_jsonl
from .paths import DATA, ROOT

SHARED = ROOT / "shared"
CACHE_FIELDS = ("sha256", "model", "prompt_version", "screened_at", "assessment")
IMAGE_HOSTS = {
    "bluesky": ("cdn.bsky.app",),
    "mastodon": ("mastodon.social", "masto.host"),
    "reddit": ("i.redd.it",),
    "flickr": ("staticflickr.com",),
}


def export(handoff=DATA / "handoff", shared=SHARED):
    handoff, shared = Path(handoff), Path(shared)
    if not (handoff / "passed.jsonl").is_file():
        raise ValueError("Build scraping/data/handoff first with python -m scraping.handoff.")
    shared.mkdir(parents=True, exist_ok=True)
    passed = read_jsonl(handoff / "passed.jsonl")
    write_jsonl(shared / "passed.jsonl", passed)
    groups_path = handoff / "post-groups.jsonl"
    groups = read_jsonl(groups_path) if groups_path.is_file() else []
    shared_groups = shared / "post-groups.jsonl"
    if groups:
        write_jsonl(shared_groups, groups)
    else:
        shared_groups.unlink(missing_ok=True)
    cache = {}
    if (shared / "screening-cache.jsonl").is_file():
        cache = {row["sha256"]: row for row in read_jsonl(shared / "screening-cache.jsonl")}
    for path in sorted(DATA.glob("*/screening.jsonl")):
        for row in read_jsonl(path):
            if row.get("sha256") and row.get("assessment"):
                cache[row["sha256"]] = {key: row.get(key) for key in CACHE_FIELDS}
    write_jsonl(shared / "screening-cache.jsonl", sorted(cache.values(), key=lambda r: r["sha256"]))
    report = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "passed": len(passed),
        "by_platform": dict(Counter(row.get("platform") for row in passed)),
        "cached_gemini_results": len(cache),
        "images_committed": False,
    }
    if groups:
        report["post_groups"] = len(groups)
        report["supplemental_images"] = sum(len(group.get("supplemental_images") or []) for group in groups)
    write_json(shared / "report.json", report)
    return report


def _record_key(row):
    return row.get("key") or f"{row.get('platform')}:{row.get('post_id')}:{row.get('media_index')}"


def _restore_image(row, output):
    """Restore a source image to its canonical path, checking original pixels."""
    digest = row.get("sha256")
    hosts = IMAGE_HOSTS.get(row.get("platform"))
    if (not hosts or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or not row.get("media_url") or row.get("local_path") != f"images/{digest}.jpg"):
        return False, "unsupported"
    path = output / f"images/{digest}.jpg"
    if path.is_file():
        return True, None
    try:
        jpeg, _, actual, _ = image_derivative(fetch_image(row["media_url"], hosts))
    except (ValueError, OSError, Image.DecompressionBombError, requests.RequestException):
        return False, "unavailable"
    if actual != digest:
        return False, "changed"
    path.write_bytes(jpeg)
    return True, None


def _annotate_details(details, missing, restored_keys):
    if not isinstance(details, dict):
        return set()
    issues = details.get("issues")
    if not isinstance(issues, list):
        issue = details.get("issue")
        issues = [issue] if isinstance(issue, dict) else [details]
    cited_missing = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        cited = [issue.get("primary_image_key")]
        supporting = issue.get("supporting_image_keys")
        if isinstance(supporting, list):
            cited.extend(supporting)
        unavailable = {key for key in cited if isinstance(key, str) and key not in restored_keys}
        if unavailable:
            issue["unavailable_image_keys"] = sorted(unavailable)
            cited_missing.update(unavailable)
        else:
            issue.pop("unavailable_image_keys", None)
    all_missing = missing | cited_missing
    details["restore_context"] = {
        "unavailable_image_keys": sorted(all_missing),
        "context_incomplete": bool(all_missing),
    }
    return cited_missing


def _restore_context(group, original_keys, restored_keys, primaries):
    """Annotate cached descriptions when their source photos did not return."""
    missing = set(original_keys - restored_keys)
    missing.update(_annotate_details(group.get("issue_details"), missing, restored_keys))
    for row in primaries:
        missing.update(_annotate_details(row.get("issue_details"), missing, restored_keys))
    group["unavailable_image_keys"] = sorted(missing)
    group["context_incomplete"] = bool(missing)


def pull(shared=SHARED, output=DATA / "handoff"):
    shared, output = Path(shared), Path(output).resolve()
    if not output.is_relative_to(DATA.resolve()):
        raise ValueError("Pull into a directory inside scraping/data.")
    rows = read_jsonl(shared / "passed.jsonl")
    if output.exists():
        shutil.rmtree(output)
    (output / "images").mkdir(parents=True)
    stored, missing = [], Counter()
    restored_by_key = {}
    for row in rows:
        restored, reason = _restore_image(row, output)
        if not restored:
            missing[reason] += 1
            continue
        stored.append(row)
        restored_by_key[_record_key(row)] = row
    source_groups_path = shared / "post-groups.jsonl"
    groups = read_jsonl(source_groups_path) if source_groups_path.is_file() else []
    restored_groups, supplemental_missing = [], Counter()
    for source_group in groups:
        if not isinstance(source_group, dict):
            continue
        group = dict(source_group)
        originals = group.get("passed_images")
        if not isinstance(originals, list):
            originals = []
        restored_primaries = []
        for original in originals:
            row = restored_by_key.get(_record_key(original))
            if (row and row.get("sha256") == original.get("sha256")
                    and (not group.get("group_id") or not row.get("post_group_id")
                         or row.get("post_group_id") == group["group_id"])):
                restored_primaries.append(row)
        if not restored_primaries:
            continue
        group["passed_images"] = restored_primaries
        available_keys = {_record_key(row) for row in restored_primaries}
        restored_supplements = []
        supplements = group.get("supplemental_images")
        if not isinstance(supplements, list):
            supplements = []
        for row in supplements:
            if not isinstance(row, dict):
                continue
            restored, reason = _restore_image(row, output)
            key = _record_key(row)
            if restored:
                restored_supplements.append(row)
                available_keys.add(key)
            else:
                supplemental_missing[reason] += 1
        group["supplemental_images"] = restored_supplements
        original_keys = {_record_key(row) for row in originals}
        original_keys.update(_record_key(row) for row in supplements if isinstance(row, dict))
        _restore_context(group, original_keys, available_keys, restored_primaries)
        restored_groups.append(group)
    write_jsonl(output / "passed.jsonl", stored)
    if restored_groups:
        write_jsonl(output / "post-groups.jsonl", restored_groups)
    report = {"pulled_at": datetime.now(timezone.utc).isoformat(), "passed": len(stored),
              "not_restored": dict(missing)}
    if groups:
        report["post_groups"] = len(restored_groups)
        report["supplemental_images"] = sum(len(group["supplemental_images"]) for group in restored_groups)
        report["supplemental_not_restored"] = dict(supplemental_missing)
    write_json(output / "report.json", report)
    metadata = {"mode": "handoff", "batch_id": output.name, **report}
    if restored_groups:
        write_gallery(output, stored, metadata, post_groups=restored_groups)
    else:
        write_gallery(output, stored, metadata)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("export", "pull"))
    args = parser.parse_args()
    try:
        report = export() if args.command == "export" else pull()
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Share stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
