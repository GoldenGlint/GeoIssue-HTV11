"""Turns the photo-analysis output into canonical records, driven by [input], [fields] and [values].

Only fields listed in [fields] are kept, so anything else in the input (authors, handles, raw
model output) never reaches the output. Unused input fields are counted in the report instead.
"""
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_PATH_PART = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def get_path(obj, path):
    """Value at a path like "analysis.issues[0].type", or None."""
    for name, index in _PATH_PART.findall(path):
        if index:
            if not isinstance(obj, list) or int(index) >= len(obj):
                return None
            obj = obj[int(index)]
        else:
            if not isinstance(obj, dict) or name not in obj:
                return None
            obj = obj[name]
    return obj


def _leaf_paths(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaf_paths(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list) and obj and isinstance(obj[0], (dict, list)):
        for item in obj:
            yield from _leaf_paths(item, f"{prefix}[]")
    elif obj not in (None, "", []):
        yield prefix


def read_input(path, records_keys):
    """[(raw record, folder its relative photo paths start from)] from a JSON/JSONL file or a folder of them."""
    path = Path(path)
    files = sorted(p for p in path.rglob("*") if p.suffix in (".json", ".jsonl")) if path.is_dir() else [path]
    items = []
    for file in files:
        text = file.read_text(encoding="utf-8-sig")
        if file.suffix == ".jsonl":
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            data = json.loads(text)
        if isinstance(data, dict):
            data = next((data[k] for k in records_keys if isinstance(data.get(k), list)), [data])
        items.extend((item, file.parent) for item in data if isinstance(item, dict))
    return items


class Normaliser:
    """Maps free-form labels onto the frontend's values using [values.<field>] tables."""

    def __init__(self, values, report):
        self.report = report
        self.tables = {}
        for field, table in values.items():
            lookup = {}
            for canonical, labels in table.items():
                if not canonical.startswith("_"):
                    for label in [canonical, *labels]:
                        lookup[self._key(label)] = canonical
            self.tables[field] = (lookup, table)

    @staticmethod
    def _key(label):
        return re.sub(r"[\s_\-]+", " ", str(label).strip().lower())

    def is_skipped(self, field, value):
        _, table = self.tables.get(field, ({}, {}))
        return self._key(value) in {self._key(v) for v in table.get("_skip", [])}

    def __call__(self, field, value):
        if field not in self.tables or value is None:
            return value
        lookup, table = self.tables[field]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and "_high" in table and 0 <= value <= 1:
            return "High" if value >= table["_high"] else "Medium" if value >= table["_medium"] else "Low"
        found = lookup.get(self._key(value))
        if found is None:
            self.report["unrecognised_values"][field][str(value)] += 1
            return table.get("_default", value)
        return found


def _number(value):
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _fraction(value):
    """Confidence as 0-1; percentages like 87 become 0.87."""
    n = _number(value)
    if n is None:
        return None
    return round(min(1.0, max(0.0, n / 100 if n > 1 else n)), 3)


def _timestamp(value):
    if value is None or value == "":
        return None
    n = _number(value)
    if n is not None:
        moment = datetime.fromtimestamp(n / 1000 if n > 1e11 else n, timezone.utc)
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _issue_id(source_id, raw, index):
    basis = str(source_id) if source_id not in (None, "") else json.dumps(raw, sort_keys=True, default=str)
    if index is not None:
        basis += f"#{index}"
    return "CL-" + hashlib.sha1(basis.encode()).hexdigest()[:8].upper()


def _explode(raw, paths):
    """([(view, index)], path used): one view per element of the first list found at any of the paths."""
    for path in [paths] if isinstance(paths, str) else paths or []:
        issues = get_path(raw, path)
        if isinstance(issues, list) and issues:
            views = []
            for index, issue in enumerate(issues):
                view = copy.copy(raw)
                view["issue"] = issue
                views.append((view, index))
            return views, path
    return [(raw, None)], None


def _skip_reason(record, rules):
    """The first [input] skip_when rule the record matches, as "field=value", or None."""
    for field, values in rules.items():
        value = record.get(field)
        if value is not None and str(value).strip().lower() in {str(v).lower() for v in values}:
            return f"{field}={value}"
    return None


def new_report():
    return {
        "counts": Counter(),
        "dropped": [],
        "unrecognised_values": defaultdict(Counter),
        "unused_input_fields": Counter(),
        "warnings": [],
    }


def adapt(items, config, report):
    fields = config["fields"]
    settings = config.get("input", {})
    private = {f.lower() for f in config.get("output", {}).get("private_fields", [])}
    passthrough = [f for f in config.get("output", {}).get("passthrough", []) if f.lower() not in private]
    normalise = Normaliser(config.get("values", {}), report)
    min_confidence = settings.get("min_detection_confidence", 0.0)
    records = []

    for raw, base_dir in items:
        report["counts"]["input_records"] += 1
        used = set()
        views, explode_path = _explode(raw, settings.get("explode"))
        for view, index in views:
            report["counts"]["records"] += 1  # after splitting, e.g. one per photo
            record = {"provenance": {}}
            for field, candidates in fields.items():
                for candidate in candidates:
                    value = get_path(view, candidate)
                    if value not in (None, "", []):
                        record[field] = value
                        record["provenance"][field] = "input"
                        used.add(_input_path(candidate, explode_path))
                        break
            for field in passthrough:
                value = get_path(raw, field)
                if value is not None:
                    record[field] = value
                    used.add(_input_path(field, None))

            record["issue_id"] = _issue_id(record.pop("source_id", None), raw, index)
            record["provenance"].pop("source_id", None)
            if record.get("issue_type") is None or normalise.is_skipped("issue_type", record["issue_type"]):
                report["counts"]["skipped_not_an_issue"] += 1
                continue
            reason = _skip_reason(record, settings.get("skip_when", {}))
            if reason:
                report["counts"][f"skipped_{reason}"] += 1
                continue
            for field in ("issue_type", "severity", "resolution_status", "verification_status", "source_category"):
                if field in record:
                    record[field] = normalise(field, record[field])

            for field in ("detection_confidence", "geo_confidence"):
                if field in record:
                    # Words such as "high" go through [values.<field>] first, e.g. "0.85" = ["high"].
                    if isinstance(record[field], str) and _number(record[field]) is None:
                        record[field] = normalise(field, record[field])
                    record[field] = _fraction(record[field])
            confidence = record.get("detection_confidence")
            if confidence is not None and confidence < min_confidence:
                report["counts"]["skipped_low_confidence"] += 1
                continue
            for field in ("location_radius_m", "distance_m", "priority_score", "sightings_count"):
                if field in record:
                    record[field] = _number(record[field])
                    if record[field] is None:
                        report["warnings"].append(f"{record['issue_id']}: {field} is not a number, ignored")
                        del record[field]
                        del record["provenance"][field]
            if "sightings_count" in record:
                record["sightings_count"] = int(record["sightings_count"])

            _location(record)
            observed = _timestamp(record.pop("observed_at", None))
            record["provenance"].pop("observed_at", None)
            if observed:
                record["first_seen_at"] = record["last_seen_at"] = observed
                record["provenance"]["first_seen_at"] = record["provenance"]["last_seen_at"] = "input"
            for flag in ("is_demo", "photo_needs_blur"):
                if flag in record:
                    record[flag] = bool(record[flag])
            if "photo" in record:
                photo = str(record.pop("photo"))
                record["provenance"]["photo_source"] = record["provenance"].pop("photo")
                record["photo_source"] = photo if re.match(r"https?://", photo) else str((base_dir / photo).resolve())
            clues = record.get("location_clues")
            if clues is not None:
                record["geo_clues"] = [_flatten_text(c) for c in clues] if isinstance(clues, list) else [_flatten_text(clues)]
                record["location_clues"] = " ; ".join(record["geo_clues"])
            records.append(record)

        for leaf in _leaf_paths(raw):
            if not any(leaf == u or leaf.startswith(u + ".") or leaf.startswith(u + "[") for u in used):
                report["unused_input_fields"][leaf] += 1

    report["private_fields_dropped"] = sorted(
        {leaf for leaf in report["unused_input_fields"] if any(part.strip("[]") in private for part in re.split(r"[.\[]", leaf))}
    )
    return records


def _input_path(candidate, explode):
    """A [fields] path as it appears in the raw record, with list indexes written as [].
    `explode` is the list path this record was split on, or None."""
    if explode and candidate.startswith("issue."):
        candidate = f"{explode}[]." + candidate[len("issue."):]
    return re.sub(r"\[\d+\]", "[]", candidate)


def _location(record):
    lat, lng = _number(record.pop("lat", None)), _number(record.pop("lng", None))
    record["provenance"].pop("lat", None)
    record["provenance"].pop("lng", None)
    geometry = record.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        record.setdefault("geo_method", "Coordinates supplied with the photo")
    elif lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        record["geometry"] = {"type": "Point", "coordinates": [round(lng, 6), round(lat, 6)]}
        record["provenance"]["geometry"] = "input"
        record.setdefault("geo_method", "Coordinates supplied with the photo")
    else:
        record.pop("geometry", None)
        record["provenance"].pop("geometry", None)


def _flatten_text(value):
    if isinstance(value, dict):
        return " ; ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ; ".join(_flatten_text(v) for v in value)
    return str(value)
