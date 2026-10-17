"""Field helpers that keep upstream values and remember where each value came from."""

# The fields the frontend reads for every issue (see src/data.js).
FRONTEND_FIELDS = [
    "issue_id", "incident_id", "issue_type", "severity", "resolution_status", "neighbourhood_id",
    "address", "geometry", "infrastructure_type", "asset_name", "distance_m", "sightings_count",
    "detection_confidence", "location_radius_m", "geo_confidence", "verification_status",
    "first_seen_at", "last_seen_at", "source_category", "evidence_thumbnail", "description",
    "explanation", "ward_id", "is_demo",
]
# Extra fields the analysis adds that are safe to publish.
PUBLIC_EXTRA_FIELDS = ["priority_score", "priority_reasons", "geo_method", "sighting_ids", "nearby_assets", "reference_data"]


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
