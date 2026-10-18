"""Runs the analysis: read input -> enabled stages -> output files.

Each stage module is imported only when it is enabled, so a stage can be switched off in
config.toml or deleted outright without touching this file.
"""
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import adapter, geo
from .config import ROOT, enabled, resolve, stage
from .record import FRONTEND_FIELDS, LIST_FIELDS, PUBLIC_EXTRA_FIELDS, as_incident, fill, point
from .reference import Reference


def run(input_path, config, out_dir=None, now=None, offline=False):
    now = now or datetime.now(timezone.utc)
    out = resolve(out_dir or config.get("output", {}).get("dir", "data/analyzed"))
    report = adapter.new_report()
    input_cfg = config.get("input", {})
    records = adapter.adapt(adapter.read_input(input_path, input_cfg.get("records_keys", [])), config, report)
    # Label defaults first: priority scores severity, so an input without one must not score as "None".
    for record in records:
        for field in ("severity", "resolution_status", "verification_status", "source_category"):
            fill(record, field, config.get("values", {}).get(field, {}).get("_default"), "default")

    ref = None
    if enabled(config, "locate"):
        from .stages import locate
        ref = Reference(stage(config, "locate"))
        locate.run(records, stage(config, "locate"), ref, report)
    sightings = _keep_located(records, input_cfg.get("toronto_bbox"), report)

    if enabled(config, "dedupe"):
        from .stages import dedupe
        issues = dedupe.run(sightings, stage(config, "dedupe"), report)
    else:
        issues = [as_incident(r) for r in sightings]

    if enabled(config, "priority"):
        from .stages import priority
        priority.run(issues, stage(config, "priority"), now, report)

    placeholder = bool(ref and ref.placeholder)
    out.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        _finalise(issue, config, now, placeholder)
        _publish_evidence(issue, out, config.get("output", {}), report)
    from .tiger import prepare_sightings
    events = prepare_sightings(issues, sightings)
    for record in sightings + issues:
        for field in ("post_text", "source_post"):  # used to locate and merge, never written
            record.pop(field, None)
            record.get("provenance", {}).pop(field, None)
    issues.sort(key=lambda i: (-(i.get("priority_score") or 0), i["issue_id"]))

    areas = None
    if enabled(config, "stats"):
        from .stages import stats
        areas = stats.run(issues, stage(config, "stats"), now)
        areas["reference_data"] = "placeholder" if placeholder else "configured"
        if enabled(config, "summaries"):
            from .stages import summaries
            summaries.run(areas, stage(config, "summaries"), report, out / ".summary_cache.json", offline, placeholder)
    elif enabled(config, "summaries"):
        report["warnings"].append("Summaries need the stats stage, so they were skipped.")

    public = [public_view(i, config.get("output", {})) for i in issues]
    report = _final_report(report, config, input_path, now, sightings, issues, placeholder)
    outputs = {"issues.public.json": public, "issues.json": issues, "sightings.json": sightings, "report.json": report}
    if areas is not None:
        outputs["areas.json"] = {"generated_at": _iso(now), **areas}
    elif (out / "areas.json").exists():
        (out / "areas.json").unlink()
    for name, data in outputs.items():
        (out / name).write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return {"out": out, "public": public, "issues": issues, "sightings": sightings, "events": events, "areas": areas, "report": report}


def _keep_located(records, bbox, report):
    kept = []
    for record in records:
        p = point(record)
        reason = ("no coordinates and no recognised place name" if p is None
                  else "outside Toronto" if bbox and not geo.in_bbox(bbox, p) else None)
        if reason:
            report["dropped"].append({"issue_id": record["issue_id"], "issue_type": record.get("issue_type"), "reason": reason})
        else:
            kept.append(record)
    return kept


def _finalise(issue, config, now, placeholder):
    """Defaults so every issue has the fields the frontend reads, even with every stage turned off."""
    fill(issue, "neighbourhood_id", "unassigned", "default")
    fill(issue, "neighbourhood_name", "Unassigned", "default")
    fill(issue, "ward_id", "unassigned", "default")
    fill(issue, "ward_name", "Unassigned", "default")
    fill(issue, "sightings_count", 1, "default")
    fill(issue, "location_radius_m", stage(config, "locate").get("default_radius_m", 50), "default")
    issue["location_radius_m"] = round(issue["location_radius_m"])
    fill(issue, "first_seen_at", _iso(now), "default (no timestamp in input)")
    fill(issue, "last_seen_at", issue["first_seen_at"], "default")
    fill(issue, "address", f"Near {issue['asset_name']}" if issue.get("asset_name") else f"{issue['neighbourhood_name']} (approximate)", "default")
    fill(issue, "description", f"{issue['issue_type']} reported near {issue['address']}.", "default")
    fill(issue, "explanation", _explanation(issue, issue["location_radius_m"]), "default")
    for field in FRONTEND_FIELDS:
        issue.setdefault(field, False if field == "is_demo" else [] if field in LIST_FIELDS else None)
    issue["reference_data"] = "placeholder" if placeholder else "configured"


def _explanation(issue, radius_m):
    confidence = issue.get("detection_confidence")
    flagged = f"“{issue['title']}” ({issue['issue_type'].lower()})" if issue.get("title") else issue["issue_type"].lower()
    parts = [f"Photo analysis flagged {flagged}"
             + (f" with {confidence:.0%} confidence." if confidence is not None else ".")]
    parts.append(f"Location method: {issue.get('geo_method') or 'supplied in the input'}; approximate within {radius_m:g} m.")
    if issue["sightings_count"] > 1:
        parts.append(f"{issue['sightings_count']} sightings were merged into this issue.")
    parts.append("A reviewer should confirm the issue and location before any action.")
    return " ".join(parts)


def _publish_evidence(issue, out, output_cfg, report):
    sources = list(dict.fromkeys(([issue["photo_source"]] if issue.get("photo_source") else []) + (issue.get("evidence_photos") or [])))
    _publish_photo(issue, out, output_cfg, report)
    photos = []
    if issue.get("evidence_thumbnail"):
        photos.append({"url": issue["evidence_thumbnail"], "role": "evidence"})
    if not issue.get("evidence_withheld"):
        for index, source in enumerate(sources):
            if source == issue.get("photo_source"):
                continue
            companion = {"issue_id": f"{issue['issue_id']}-{index + 1}", "photo_source": source}
            _publish_photo(companion, out, output_cfg, report)
            if companion.get("evidence_thumbnail"):
                photos.append({"url": companion["evidence_thumbnail"], "role": "context"})
    issue["evidence_photos"] = photos
    if not issue.get("evidence_thumbnail") and photos:
        issue["evidence_thumbnail"] = photos[0]["url"]


def _publish_photo(issue, out, output_cfg, report):
    source = issue.get("photo_source")
    if not source or issue.get("evidence_thumbnail"):
        return
    if issue.get("photo_needs_blur") and output_cfg.get("photos_needing_blur", "show") == "withhold":
        # Optional deployment override; the default policy allows full photos.
        issue["evidence_withheld"] = "Photo withheld until faces and licence plates are blurred."
        report["counts"]["photos_withheld"] += 1
        return
    copy = output_cfg.get("copy_photos", True)
    if source.startswith(("http://", "https://")):
        issue["evidence_thumbnail"] = source
        return
    path = Path(source)
    if not path.is_file():
        report["warnings"].append(f"{issue['issue_id']}: photo {path.name} not found")
        return
    if copy:
        (out / "photos").mkdir(exist_ok=True)
        path = Path(shutil.copyfile(path, out / "photos" / f"{issue['issue_id']}{path.suffix.lower()}"))
    try:
        issue["evidence_thumbnail"] = "./" + path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        report["warnings"].append(f"{issue['issue_id']}: photo is outside the repository, so the dev server cannot serve it")
        issue["evidence_thumbnail"] = path.resolve().as_uri()


def public_view(issue, output_cfg):
    """What the public map may show: frontend fields only, and coarse locations for unverified issues."""
    private = {f.lower() for f in output_cfg.get("private_fields", [])}
    fields = FRONTEND_FIELDS + PUBLIC_EXTRA_FIELDS + [f for f in output_cfg.get("passthrough", []) if f.lower() not in private]
    view = {field: issue.get(field) for field in fields if field in issue}
    if issue.get("verification_status") != "Verified":
        grid = output_cfg.get("public_grid_m", 250)
        view["geometry"] = {"type": "Point", "coordinates": geo.snap_to_grid(point(issue), grid)}
        # The circle must still contain the true location after snapping moves the point.
        view["location_radius_m"] = max(output_cfg.get("public_min_radius_m", 250), round((issue["location_radius_m"] or 0) + grid * 0.71))
        view["geo_trace"] = list(issue.get("geo_trace") or []) + [
            {"stage": "Privacy rounding", "result": f"Published position snapped to a {grid:g} m grid until verified", "status": "info"}]
        if issue.get("provenance", {}).get("explanation") == "default":
            view["explanation"] = _explanation(issue, view["location_radius_m"])
    return view


def _final_report(report, config, input_path, now, sightings, issues, placeholder):
    sources = defaultdict(Counter)
    for issue in issues:
        for field, source in issue.get("provenance", {}).items():
            sources[field][source] += 1
    counts = report["counts"]
    counts.update(sightings=len(sightings), issues=len(issues), dropped=len(report["dropped"]))
    return {
        "generated_at": _iso(now),
        "input": str(input_path),
        "reference_data": "placeholder" if placeholder else "configured",
        "stages": {name: enabled(config, name) for name in ("locate", "dedupe", "priority", "stats", "summaries")},
        "counts": dict(counts),
        "dropped": report["dropped"],
        "unrecognised_values": {field: dict(c) for field, c in report["unrecognised_values"].items()},
        "unused_input_fields": dict(report["unused_input_fields"].most_common()),
        "private_fields_dropped": report.get("private_fields_dropped", []),
        "field_sources": {field: dict(c) for field, c in sorted(sources.items())},
        "warnings": report["warnings"],
    }


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
