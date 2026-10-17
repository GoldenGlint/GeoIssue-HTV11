"""Bundle passed images with separately labelled same-post context photos."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from PIL import Image

from .media import (assess_freshness, read_jsonl, source_post_url, write_gallery,
                    write_json, write_jsonl)
from .paths import DATA
from .screen import SHARED_CACHE, decide, load_cache

DETAIL_PROMPT_VERSION = "civic-issue-detail-v1"


def image_path(batch, row):
    digest, local = row.get("sha256"), row.get("local_path")
    if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or local != f"images/{digest}.jpg"):
        raise ValueError(f"{batch.name} has a missing or unsafe image reference.")
    path = (batch / local).resolve()
    if not path.is_relative_to(batch.resolve()) or not path.is_file():
        raise ValueError(f"{batch.name} has a missing or unsafe image file.")
    return path


def group_fingerprint(group):
    """Invalidate descriptions when the photos, captions or screening evidence change."""
    fields = ("key", "sha256", "media_index", "alt_text", "screening_status", "screening")
    payload = {
        "prompt_version": DETAIL_PROMPT_VERSION,
        "platform": group["platform"], "post_id": group["post_id"],
        "caption": group.get("caption"), "posted_at": group.get("posted_at"),
        "passed_images": [{key: row.get(key) for key in fields} for row in group["passed_images"]],
        "supplemental_images": [{key: row.get(key) for key in fields}
                                for row in group["supplemental_images"]],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def attach_details(groups, descriptions):
    """Attach only descriptions matching the exact images and evidence in this group."""
    for group in groups:
        group["detail_status"] = "pending"
        previous_group = group.pop("issue_details", None)
        previous_rows = {row["key"]: row.pop("issue_details", None) for row in group["passed_images"]}
        result = descriptions.get(group_fingerprint(group))
        by_primary = {issue["primary_image_key"]: issue for issue in (result or {}).get("issues", [])}
        if not result or set(by_primary) != {row["key"] for row in group["passed_images"]}:
            if previous_group:
                group["previous_issue_details"] = previous_group
            for row in group["passed_images"]:
                if previous_rows[row["key"]]:
                    row["previous_issue_details"] = previous_rows[row["key"]]
            continue
        group.pop("previous_issue_details", None)
        group.update(detail_status="complete", issue_details=result)
        for row in group["passed_images"]:
            row.pop("previous_issue_details", None)
            row["issue_details"] = {**by_primary[row["key"]], **{
                key: result.get(key) for key in ("model", "prompt_version", "described_at")}}


def companion(row, batch, cached, *, now):
    """Context does not inherit a sibling photo's issue or location approval."""
    assessment = (cached or {}).get("assessment") or {}
    reasons = []
    if row.get("auto_status") != "ready" or not row.get("local_path"):
        reasons.append(row.get("auto_status") or "image_not_ready")
    if assessment.get("sensitive") is True:
        reasons.append("sensitive_content")
    scene = assessment.get("scene_type")
    if assessment and scene != "public_outdoor":
        reasons.append(f"scene_{scene or 'unknown'}")
    if (assessment.get("toronto") or {}).get("verdict") == "unlikely":
        reasons.append("toronto_unlikely")
    freshness = assess_freshness(row, now=now)
    if assessment.get("appears_old") or freshness["status"] in (
            "historical_caption_review", "outside_window", "future_timestamp_review", "posting_time_unknown"):
        reasons.append("not_recent")
    if reasons:
        return None, reasons
    try:
        path = image_path(batch, row)
        with Image.open(path) as image:
            saved_width, saved_height = image.size
    except (ValueError, OSError):
        return None, ["missing_or_invalid_image"]
    screening = None
    if assessment:
        screening = {
            "assessment": assessment, **decide(assessment, row, now=now),
            "model": cached.get("model"), "prompt_version": cached.get("prompt_version"),
            "screened_at": cached.get("screened_at"),
        }
    return {
        **row, "post_url": source_post_url(row), "source_batch": batch.name,
        "saved_width": saved_width, "saved_height": saved_height, "freshness": freshness,
        "screening_status": "not_passed" if assessment else "not_screened",
        "screening": screening, "relation": "same_post_context", "issue_verified": False,
        "blur_before_public_display": True,
    }, []


def build(batches, output, *, detail_cache=None, now=None):
    now = now or datetime.now(timezone.utc)
    batches = list(dict.fromkeys(Path(path).resolve() for path in batches))
    output = Path(output).resolve()
    if not output.is_relative_to(DATA.resolve()):
        raise ValueError("Choose an output directory inside scraping/data.")
    if output.exists() and not output.is_dir():
        raise ValueError("Handoff output must be a directory.")
    rows, seen, files, groups = [], set(), {}, {}
    sources = Counter()
    issues = Counter()
    for batch in batches:
        if batch == output:
            raise ValueError("Handoff output must be separate from its source batches.")
        passed_path = batch / "passed.jsonl"
        if not passed_path.is_file():
            raise ValueError(f"{batch.name} has no passed.jsonl. Screen that batch first.")
        batch_passed = read_jsonl(passed_path)
        batch_passed_keys = {row["key"] for row in batch_passed if (row.get("screening") or {}).get("passed")}
        for row in batch_passed:
            if not (row.get("screening") or {}).get("passed"):
                continue
            path = image_path(batch, row)
            digest = row["sha256"]
            if digest in seen:
                continue
            seen.add(digest)
            identity = (row["platform"], row["post_id"])
            group_id = "post-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            stored = {**row, "source_batch": batch.name, "post_group_id": group_id}
            stored.pop("issue_details", None)
            rows.append(stored)
            files[row["local_path"]] = path
            group = groups.setdefault(identity, {
                "group_id": group_id, "platform": row["platform"], "collector": row.get("collector"),
                "post_id": row["post_id"], "post_url": row.get("post_url") or source_post_url(row),
                "posted_at": row.get("posted_at"), "caption": row.get("caption") or "",
                "passed_images": [], "supplemental_images": [], "excluded_supplemental": [],
                "detail_status": "pending",
            })
            group["passed_images"].append(stored)
            sources[row.get("platform") or "unknown"] += 1
            issues[(row.get("screening") or {}).get("issue_type") or "unknown"] += 1
        media_path = batch / "media.jsonl"
        cached = {**load_cache(SHARED_CACHE), **load_cache(batch / "screening.jsonl")}
        for row in read_jsonl(media_path) if media_path.is_file() else []:
            group = groups.get((row["platform"], row["post_id"]))
            if group is None or row["key"] in batch_passed_keys:
                continue
            extra, reasons = companion(row, batch, cached.get(row.get("sha256")), now=now)
            if extra is None:
                group["excluded_supplemental"].append({
                    "key": row["key"], "media_index": row["media_index"], "reasons": reasons,
                })
                continue
            # Exact duplicate pixels add no context, but sibling identities remain auditable.
            if extra["sha256"] in {image["sha256"] for image in
                    group["passed_images"] + group["supplemental_images"]}:
                group["excluded_supplemental"].append({
                    "key": row["key"], "media_index": row["media_index"], "reasons": ["duplicate_image"],
                })
                continue
            group["supplemental_images"].append(extra)
            files[extra["local_path"]] = image_path(batch, extra)
    grouped = list(groups.values())
    descriptions_path = Path(detail_cache) if detail_cache is not None else DATA / "issue-details-cache.jsonl"
    descriptions = {row["fingerprint"]: row for row in read_jsonl(descriptions_path)} if descriptions_path.is_file() else {}
    for group in grouped:
        group["passed_images"].sort(key=lambda row: row["media_index"])
        group["supplemental_images"].sort(key=lambda row: row["media_index"])
    attach_details(grouped, descriptions)
    if output.exists():
        shutil.rmtree(output)
    (output / "images").mkdir(parents=True)
    for local, path in files.items():
        shutil.copyfile(path, output / local)
    write_jsonl(output / "passed.jsonl", rows)
    write_jsonl(output / "post-groups.jsonl", grouped)
    report = {
        "built_at": now.isoformat(),
        "passed": len(rows), "post_groups": len(grouped),
        "supplemental_images": sum(len(group["supplemental_images"]) for group in grouped),
        "excluded_supplemental": sum(len(group["excluded_supplemental"]) for group in grouped),
        "image_files": len(files),
        "described_groups": sum(group["detail_status"] == "complete" for group in grouped),
        "by_platform": dict(sources),
        "by_issue_type": dict(issues),
        "source_batches": [Path(path).name for path in batches],
        "note": "Passed images remain independently screened; supplemental photos are same-post context only.",
    }
    write_json(output / "report.json", report)
    write_gallery(output, rows, {"mode": "handoff", "batch_id": output.name, **report}, post_groups=grouped)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build(args.batch, args.out)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Handoff stopped: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
