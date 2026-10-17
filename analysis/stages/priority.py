"""Priority stage: a 0-100 score for City staff, with the reasons that produced it.

Points come from severity, extra sightings, days open and closeness to schools and transit. Low
detection confidence scales the total down, and resolved issues score 0. Weights are in config.toml.
"""
from datetime import datetime

NAME = "priority"


def run(issues, settings, now, report):
    for issue in issues:
        if issue.get("priority_score") is not None and not settings.get("overwrite", False):
            issue.setdefault("priority_reasons", ["Priority supplied in the input"])
            continue
        score, reasons = score_issue(issue, settings, now)
        issue["priority_score"] = score
        issue["priority_reasons"] = reasons
        issue.setdefault("provenance", {})["priority_score"] = NAME


def score_issue(issue, settings, now):
    if issue.get("resolution_status") == "Resolved":
        return 0, ["Resolved"]
    reasons = []
    points = settings.get("severity_points", {}).get(issue.get("severity"), 0)
    reasons.append(f"{issue.get('severity')} severity (+{points:g})")

    extra = (issue.get("sightings_count") or 1) - 1
    if extra > 0:
        p = min(extra * settings.get("points_per_extra_sighting", 8), settings.get("max_sighting_points", 24))
        points += p
        reasons.append(f"{extra + 1} sightings (+{p:g})")

    if issue.get("first_seen_at"):
        days = max(0, (now - datetime.fromisoformat(issue["first_seen_at"].replace("Z", "+00:00"))).days)
        p = min(days * settings.get("points_per_open_day", 0.5), settings.get("max_age_points", 15))
        if p:
            points += p
            reasons.append(f"Open {days} {'day' if days == 1 else 'days'} (+{p:g})")

    near_m = settings.get("near_asset_m", 100)
    for kind, bonus in settings.get("near_asset_points", {}).items():
        asset = (issue.get("nearby_assets") or {}).get(kind)
        if asset and asset["distance_m"] <= near_m:
            points += bonus
            reasons.append(f"{asset['distance_m']} m from {asset['name']} (+{bonus:g})")

    confidence = issue.get("detection_confidence")
    if confidence is not None and confidence < settings.get("low_confidence_below", 0.6):
        factor = settings.get("low_confidence_factor", 0.7)
        points *= factor
        reasons.append(f"Low detection confidence {confidence:.0%} (x{factor:g})")
    return round(min(100, points)), reasons
