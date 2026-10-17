"""Merge-duplicates stage: groups sightings of the same issue into one incident.

Two sightings join when they have the same issue type, were first seen within window_days of each
other, and either are close together or have near-identical photo hashes (reposts). Joining is
transitive. Records that already carry an incident_id from the input are grouped by it as given.
"""
from collections import defaultdict
from datetime import datetime

from .. import geo
from ..record import as_incident, point

NAME = "dedupe"
SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3}
LOCATION_FIELDS = ("geometry", "location_radius_m", "geo_confidence", "geo_method", "geo_trace", "neighbourhood_id",
                   "neighbourhood_name", "ward_id", "ward_name", "infrastructure_type", "asset_id", "asset_name",
                   "distance_m", "nearby_assets", "address")
EVIDENCE_FIELDS = ("description", "explanation", "detection_confidence", "photo_source", "evidence_credit", "source_category")


def run(records, settings, report):
    groups = defaultdict(list)
    fresh = []
    for record in records:
        if record.get("incident_id"):
            groups[str(record["incident_id"])].append(record)
        else:
            fresh.append(record)
    merged = [_merge(members, incident_id) for incident_id, members in groups.items()]
    merged += [_merge(members) for members in _cluster(fresh, settings)]
    report["counts"]["merged_away"] += len(records) - len(merged)
    return merged


def _cluster(records, settings):
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    max_m = settings.get("max_distance_m", 150)
    order = sorted(range(len(records)), key=lambda i: point(records[i])[1])
    for pos, i in enumerate(order):
        for j in order[pos + 1:]:
            if (point(records[j])[1] - point(records[i])[1]) * geo.METRES_PER_DEGREE > max_m:
                break
            if _same_issue(records[i], records[j], settings, by_distance=True):
                parent[find(i)] = find(j)

    hashed = [i for i, r in enumerate(records) if r.get("image_hash")]
    for pos, i in enumerate(hashed):
        for j in hashed[pos + 1:]:
            if _same_issue(records[i], records[j], settings, by_distance=False):
                parent[find(i)] = find(j)

    clusters = defaultdict(list)
    for i, record in enumerate(records):
        clusters[find(i)].append(record)
    return list(clusters.values())


def _same_issue(a, b, settings, by_distance):
    if a["issue_type"] != b["issue_type"] or not _within_window(a, b, settings.get("window_days", 14)):
        return False
    if by_distance:
        limit = settings.get("distance_m", 30)
        if settings.get("use_location_radius", True):
            limit = max(limit, a.get("location_radius_m") or 0, b.get("location_radius_m") or 0)
        return geo.distance_m(point(a), point(b)) <= min(limit, settings.get("max_distance_m", 150))
    bits = _hash_distance(a["image_hash"], b["image_hash"])
    return bits is not None and bits <= settings.get("image_hash_max_bits", 6)


def _within_window(a, b, days):
    if not a.get("first_seen_at") or not b.get("first_seen_at"):
        return True
    ta, tb = (datetime.fromisoformat(r["first_seen_at"].replace("Z", "+00:00")) for r in (a, b))
    return abs((ta - tb).total_seconds()) <= days * 86400


def _hash_distance(a, b):
    try:
        return (int(str(a), 16) ^ int(str(b), 16)).bit_count()
    except ValueError:
        return None


def _merge(members, incident_id=None):
    members = sorted(members, key=lambda r: (r.get("first_seen_at") or "", r["issue_id"]))
    if len(members) == 1:
        return as_incident(members[0], incident_id)
    issue = as_incident(members[0], incident_id)
    located = min(members, key=lambda r: r.get("location_radius_m") or float("inf"))
    evidence = max(members, key=lambda r: r.get("detection_confidence") or 0)
    for source, fields in ((located, LOCATION_FIELDS), (evidence, EVIDENCE_FIELDS)):
        for field in fields:
            issue["provenance"].pop(field, None)
            if field in source:
                issue[field] = source[field]
                if field in source.get("provenance", {}):
                    issue["provenance"][field] = source["provenance"][field]
            else:
                issue.pop(field, None)

    seen = [r["first_seen_at"] for r in members if r.get("first_seen_at")]
    last = [r.get("last_seen_at") or r.get("first_seen_at") for r in members if r.get("first_seen_at")]
    latest = max(members, key=lambda r: r.get("last_seen_at") or "")
    merged = {
        "first_seen_at": min(seen) if seen else None,
        "last_seen_at": max(last) if last else None,
        "severity": max((r.get("severity") for r in members), key=lambda s: SEVERITY_RANK.get(s, 0)),
        "sightings_count": sum(r.get("sightings_count") or 1 for r in members),
        "resolution_status": latest.get("resolution_status") or issue.get("resolution_status"),
        "verification_status": "Verified" if any(r.get("verification_status") == "Verified" for r in members)
                               else issue.get("verification_status"),
        "sighting_ids": [r["issue_id"] for r in members],
        "evidence_photos": [r["photo_source"] for r in members if r.get("photo_source")],
        "is_demo": any(r.get("is_demo") for r in members),
        "geo_clues": list(dict.fromkeys(c for r in members for c in r.get("geo_clues") or [])) or None,
        "geo_trace": list(located.get("geo_trace") or []) + [
            {"stage": "Duplicate merge", "result": f"{len(members)} sightings merged; the most precise location is kept", "status": "info"}],
    }
    for field, value in merged.items():
        if value is not None:
            issue[field] = value
            issue["provenance"][field] = NAME
    for r in members:
        r["incident_id"] = issue["incident_id"]
    return issue
