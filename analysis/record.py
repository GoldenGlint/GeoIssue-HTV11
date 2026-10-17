"""Field helpers that keep upstream values and remember where each value came from."""

# The Issue fields in data-contract.md, which the frontend reads for every issue.
FRONTEND_FIELDS = [
    "issue_id", "incident_id", "issue_type", "severity", "resolution_status", "verification_status",
    "geometry", "location_radius_m", "geo_confidence", "geo_method", "geo_trace", "geo_clues",
    "neighbourhood_id", "neighbourhood_name", "ward_id", "ward_name", "address",
    "infrastructure_type", "asset_id", "asset_name", "distance_m", "nearby_assets",
    "detection_confidence", "sightings_count", "first_seen_at", "last_seen_at", "source_category",
    "description", "explanation", "evidence_thumbnail", "evidence_credit", "is_demo",
]
# Extra fields the analysis adds that are safe to publish. `title` is a short name from the photo analysis,
# e.g. "Storm drain grate misaligned"; the frontend shows it in place of the issue type when present.
PUBLIC_EXTRA_FIELDS = ["title", "priority_score", "priority_reasons", "sighting_ids", "reference_data", "evidence_withheld"]
LIST_FIELDS = ("geo_trace", "geo_clues", "nearby_assets")


def is_missing(value):
    return value is None or value == "" or value == [] or value == {}


def fill(record, field, value, source, overwrite=False):
    """Set record[field] unless it already has a value. Returns True when the value was written."""
    if value is None or (not overwrite and not is_missing(record.get(field))):
        return False
    record[field] = value
    record.setdefault("provenance", {})[field] = source
    return True


def as_incident(record, incident_id=None):
    """A copy of one sighting as a single-sighting incident."""
    issue = dict(record)
    issue["provenance"] = dict(record.get("provenance", {}))
    fill(issue, "incident_id", incident_id or "INC-" + record["issue_id"].removeprefix("CL-"), "analysis")
    fill(issue, "sighting_ids", [record["issue_id"]], "analysis")
    fill(issue, "evidence_photos", [record["photo_source"]] if record.get("photo_source") else None, "analysis")
    record["incident_id"] = issue["incident_id"]
    return issue


def point(record):
    """The record's [lng, lat], or None."""
    geometry = record.get("geometry") or {}
    return geometry.get("coordinates") if geometry.get("type") == "Point" else None
