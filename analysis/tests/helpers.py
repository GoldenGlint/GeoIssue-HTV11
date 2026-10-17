import copy
from datetime import datetime, timezone
from pathlib import Path

from analysis import adapter, config as cfg

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "photo_analysis_output.json"


def config(**stage_overrides):
    """The default config with stage settings overridden, e.g. config(dedupe={"enabled": False})."""
    c = copy.deepcopy(cfg.load())
    for name, values in stage_overrides.items():
        c["stages"].setdefault(name, {}).update(values)
    return c


def adapt(raw_records, conf=None):
    report = adapter.new_report()
    records = adapter.adapt([(r, Path(".")) for r in raw_records], conf or config(), report)
    return records, report


def raw(post_id="p1", lat=43.6457, lng=-79.3951, issue_type="pothole", posted_at="2026-10-15T14:22:00Z", **extra):
    record = {"post_id": post_id, "posted_at": posted_at, "issues": [{"type": issue_type, "severity": "high", "certainty": 0.9}]}
    if lat is not None:
        record["location"] = {"lat": lat, "lng": lng}
    record.update(extra)
    return record
