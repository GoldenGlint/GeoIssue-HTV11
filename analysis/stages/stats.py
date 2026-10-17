"""Area stats stage: counts and trends for the whole city and for each neighbourhood and ward."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median

NAME = "stats"


def run(issues, settings, now):
    trend_days = settings.get("trend_days", 7)
    by_area = {}
    for level in settings.get("levels", ["neighbourhood_id", "ward_id"]):
        groups = defaultdict(list)
        for issue in issues:
            groups[issue.get(level) or "Unassigned"].append(issue)
        by_area[level] = sorted((summarise(name, members, settings, now) for name, members in groups.items()),
                                key=lambda a: (-a["open"], a["name"]))
    return {"trend_days": trend_days, "city": summarise("Toronto", issues, settings, now), "by_area": by_area}


def summarise(name, issues, settings, now):
    trend = timedelta(days=settings.get("trend_days", 7))
    seen = [(i, _time(i.get("first_seen_at"))) for i in issues]
    open_issues = [(i, t) for i, t in seen if i.get("resolution_status") != "Resolved"]
    open_ages = [(now - t).days for _, t in open_issues if t]
    ranked = sorted((i for i, _ in open_issues if i.get("priority_score") is not None), key=lambda i: -i["priority_score"])
    return {
        "name": name,
        "total": len(issues),
        "open": len(open_issues),
        "verified": sum(i.get("verification_status") == "Verified" for i in issues),
        "sightings": sum(i.get("sightings_count") or 1 for i in issues),
        "by_type": dict(Counter(i.get("issue_type") for i in issues).most_common()),
        "by_severity": dict(Counter(i.get("severity") for i in issues).most_common()),
        "by_status": dict(Counter(i.get("resolution_status") for i in issues).most_common()),
        "new_recent": sum(1 for _, t in seen if t and now - t <= trend),
        "new_previous": sum(1 for _, t in seen if t and trend < now - t <= 2 * trend),
        "median_open_age_days": median(open_ages) if open_ages else None,
        "top_priority": [{"issue_id": i["issue_id"], "issue_type": i.get("issue_type"), "address": i.get("address"),
                          "priority_score": i["priority_score"]} for i in ranked[: settings.get("top_n", 3)]],
    }


def _time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
