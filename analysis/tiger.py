"""Optional Tiger Data storage. Run `python -m analysis.tiger --help` for setup/demo commands."""
import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from .config import setting

UTC = timezone.utc
HOUR = timedelta(hours=1)
DATASETS = ("pipeline", "replay")
CATEGORIES = ("Pothole", "Sidewalk damage", "Graffiti", "Litter", "Flooding", "Other")


class Unavailable(RuntimeError):
    pass


def connection():
    url = setting("TIGER_DATABASE_URL")
    if not url:
        raise Unavailable("Tiger Data is not configured. Add TIGER_DATABASE_URL to .env.")
    try:
        import psycopg
    except ImportError:
        raise Unavailable("Install analysis/requirements-tiger.txt to enable Tiger Data.") from None
    try:
        return psycopg.connect(url, autocommit=True, connect_timeout=5,
                               options="-c statement_timeout=15000")
    except psycopg.Error as error:
        # Driver errors can include connection details; never expose them through the public API.
        message = str(error).lower()
        if "no password supplied" in message:
            raise Unavailable("The Tiger Data URL is missing its password. Copy the full connection URI into TIGER_DATABASE_URL.") from None
        if "password authentication failed" in message:
            raise Unavailable("Tiger Data rejected the credentials. Check the username and password in TIGER_DATABASE_URL.") from None
        raise Unavailable("Tiger Data is unreachable. Check the server's database configuration.") from None


def iso(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def moment(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def dataset_name(value):
    if value not in DATASETS:
        raise ValueError("dataset must be pipeline or replay")
    return value


def prepare_sightings(issues, sightings):
    """Strip source identities and count companion photos once per post/incident."""
    incidents = {issue["incident_id"]: issue for issue in issues}
    groups = defaultdict(list)
    for record in sightings:
        groups[(record["incident_id"], record.get("source_post") or record["issue_id"])].append(record)
    events = []
    for (incident_id, _), members in groups.items():
        issue = incidents[incident_id]
        # Pipeline record IDs are stable for repeated imports of the same complete handoff.
        source_key = min(r["issue_id"] for r in members)
        dates = [r["first_seen_at"] for r in members if r.get("first_seen_at")
                 and r.get("provenance", {}).get("first_seen_at") == "input"]
        events.append({
            "sighting_id": hashlib.sha256(source_key.encode()).hexdigest(),
            "issue_id": issue["issue_id"], "ward_id": str(issue["ward_id"]),
            "issue_type": issue["issue_type"], "reported_at": min(dates) if dates else None,
            "timestamp_basis": "source" if dates else "ingestion",
        })
    return events


def initialize():
    with connection() as conn, conn.transaction():
        conn.execute(Path(__file__).with_name("tiger-schema.sql").read_text())


def sync(public, events, report, areas=None, dataset="pipeline"):
    """Atomically synchronize a complete handoff; never reconstruct events from a count."""
    dataset_name(dataset)
    now = datetime.now(UTC)
    with connection() as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("geoissue:" + dataset,))
            previous = {row[0]: row[1:] for row in conn.execute(
                "SELECT sighting_id, reported_at, ingested_at FROM geoissue.sightings WHERE dataset = %s",
                (dataset,)).fetchall()}
            rows = []
            for event in events:
                old = previous.get(event["sighting_id"])
                reported = moment(event["reported_at"]) if event["reported_at"] else old[0] if old else now
                if reported > now + timedelta(minutes=5):
                    raise ValueError("A sighting has a future report timestamp; check the handoff dates.")
                rows.append((reported, dataset, event["sighting_id"], event["issue_id"],
                             event["ward_id"], event["issue_type"], event["timestamp_basis"], old[1] if old else now))
            if len({row[2] for row in rows}) != len(rows):
                raise ValueError("Duplicate sighting keys in the handoff")
            # ponytail: complete snapshots keep reconciliation small; use incremental CDC for large live feeds.
            conn.execute("DELETE FROM geoissue.sightings WHERE dataset = %s", (dataset,))
            with conn.cursor() as cursor:
                cursor.executemany("""INSERT INTO geoissue.issues VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (dataset, issue_id) DO UPDATE SET public_issue = EXCLUDED.public_issue""",
                    [(dataset, issue["issue_id"], json.dumps(issue)) for issue in public])
                cursor.executemany("""INSERT INTO geoissue.sightings
                    (reported_at, dataset, sighting_id, issue_id, ward_id, issue_type, timestamp_basis, ingested_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", rows)
            conn.execute("DELETE FROM geoissue.issues WHERE dataset = %s AND NOT (issue_id = ANY(%s::text[]))",
                         (dataset, [issue["issue_id"] for issue in public]))
            metadata = {"report": report, "areas": areas, "imported_at": iso(now),
                        "dataset": dataset, "simulated": dataset == "replay" or any(i.get("is_demo") for i in public),
                        "reports": len(rows), "coverage_start": iso(min(row[0] for row in rows)) if rows else None}
            conn.execute("""INSERT INTO geoissue.pipeline_state VALUES (%s, %s::jsonb)
                ON CONFLICT (dataset) DO UPDATE SET metadata = EXCLUDED.metadata""", (dataset, json.dumps(metadata)))
        # Refresh removed/changed historical buckets too, including data outside the policy's 90-day window.
        times = [row[0] for row in rows] + [value[0] for value in previous.values()]
        if times:
            start = min(times).replace(minute=0, second=0, microsecond=0)
            end = min(max(times).replace(minute=0, second=0, microsecond=0) + HOUR,
                      now.replace(minute=0, second=0, microsecond=0))
            if start < end:
                conn.execute("CALL refresh_continuous_aggregate('geoissue.ward_activity_hourly', %s, %s)", (start, end))
    return metadata


def issues(dataset="pipeline"):
    with connection() as conn:
        return [row[0] for row in conn.execute("""SELECT public_issue FROM geoissue.issues
            WHERE dataset = %s ORDER BY (public_issue->>'priority_score')::integer DESC NULLS LAST, issue_id""",
            (dataset_name(dataset),)).fetchall()]


def pipeline(dataset="pipeline"):
    with connection() as conn:
        row = conn.execute("SELECT metadata FROM geoissue.pipeline_state WHERE dataset = %s",
                           (dataset_name(dataset),)).fetchone()
        return row[0] if row else {"dataset": dataset, "report": None, "areas": None, "reports": 0}


def activity_options(query):
    """Bounded, allowlisted filters; never accept arbitrary SQL or client-supplied dates."""
    if set(query) - {"dataset", "days", "ward", "type"} or any(len(v) != 1 for v in query.values()):
        raise ValueError("Unsupported or repeated activity filter")
    dataset = dataset_name(query.get("dataset", ["pipeline"])[0])
    days = query.get("days", ["30"])[0]
    ward = query.get("ward", [""])[0]
    category = query.get("type", [""])[0]
    if days not in ("7", "30", "90"):
        raise ValueError("days must be 7, 30 or 90")
    if ward and ward not in {str(n) for n in range(1, 26)}:
        raise ValueError("ward must be a Toronto ward number (1–25)")
    if category and category not in CATEGORIES:
        raise ValueError("Unknown issue type")
    return {"dataset": dataset, "days": int(days), "ward": ward, "category": category}


def summarize_activity(rows, days, now, coverage_start=None):
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    recent_start, baseline_start = end - timedelta(days=1), end - timedelta(days=8)
    series = {start + n * HOUR: 0 for n in range(days * 24 + 1)}
    wards = defaultdict(lambda: {"recent": 0, "baseline": 0})
    undated = 0
    for bucket, ward, reports, unknown in rows:
        if bucket in series:
            series[bucket] += int(reports)
            undated += int(unknown)
        if recent_start <= bucket < end:
            wards[ward]["recent"] += int(reports)
        elif baseline_start <= bucket < recent_start:
            wards[ward]["baseline"] += int(reports)
    baseline_available = bool(coverage_start and moment(coverage_start) <= baseline_start)
    ranked = []
    for ward, counts in wards.items():
        average = counts["baseline"] / 7
        ratio = counts["recent"] / average if average else None
        emerging = bool(baseline_available and counts["recent"] >= 5 and counts["baseline"] >= 7 and ratio >= 2)
        ranked.append({"ward_id": ward, **counts, "daily_average": round(average, 2),
                       "ratio": round(ratio, 2) if ratio is not None else None, "emerging": emerging})
    ranked.sort(key=lambda item: (-item["emerging"], -item["recent"], item["ward_id"]))
    return {"series": [{"bucket": iso(bucket), "reports": count} for bucket, count in series.items()],
            "reports": sum(series.values()), "undated_reports": undated, "wards": ranked,
            "baseline_available": baseline_available, "comparison_end": iso(end)}


def activity(dataset="pipeline", days=30, ward="", category=""):
    now = datetime.now(UTC)
    with connection() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        metadata = conn.execute("SELECT metadata FROM geoissue.pipeline_state WHERE dataset = %s", (dataset,)).fetchone()
        rows = conn.execute("""SELECT bucket, ward_id, sum(reports), sum(undated_reports)
            FROM geoissue.ward_activity_hourly
            WHERE dataset = %s AND bucket >= %s AND bucket < %s
              AND (%s = '' OR ward_id = %s) AND (%s = '' OR issue_type = %s)
            GROUP BY bucket, ward_id ORDER BY bucket, ward_id""",
            (dataset_name(dataset), now.replace(minute=0, second=0, microsecond=0) - timedelta(days=max(days, 8)),
             now, ward, ward, category, category)).fetchall()
    meta = metadata[0] if metadata else {}
    return {"backend": "tiger", "dataset": dataset, "simulated": meta.get("simulated", False),
            "as_of": iso(now), "imported_at": meta.get("imported_at"), "days": days, "ward": ward, "type": category,
            **summarize_activity(rows, days, now, meta.get("coverage_start"))}


def columnstore_stats(conn):
    chunks, compressed, before, after = conn.execute("""SELECT total_chunks, number_compressed_chunks,
        before_compression_total_bytes, after_compression_total_bytes
        FROM hypertable_columnstore_stats('geoissue.sightings')""").fetchone()
    return {"total_chunks": chunks, "compressed_chunks": compressed, "before_bytes": before, "after_bytes": after,
            "storage_reduction_percent": round((1 - after / before) * 100, 2) if before and after is not None else None}


def database_stats():
    """Public, read-only proof of the integration; no connection details or source records."""
    with connection() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        counts = dict(conn.execute("SELECT dataset, (metadata->>'reports')::bigint FROM geoissue.pipeline_state").fetchall())
        storage = columnstore_stats(conn)
    return {"backend": "tiger", "as_of": iso(datetime.now(UTC)),
            "reports_by_dataset": counts, "shared_columnstore": storage}


def replay(events=10000):
    """Deterministic history + a flooding surge, isolated from collected evidence."""
    if not 100 <= events <= 100000:
        raise ValueError("replay events must be between 100 and 100000")
    existing = pipeline("replay")
    anchor = moment(existing["report"]["generated_at"]) if existing.get("report") else datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    public, sightings = {}, []
    for n in range(events):
        surge = n % 5 == 0
        ward = "10" if surge else str(n % 25 + 1)
        category = "Flooding" if surge else CATEGORIES[n % len(CATEGORIES)]
        issue_id = f"REPLAY-{ward}-{CATEGORIES.index(category)}"
        reported = anchor - timedelta(minutes=1 + n % 1440) if surge else anchor - timedelta(minutes=1 + n * 137 % (10 * 1440))
        if issue_id not in public:
            public[issue_id] = {"issue_id": issue_id, "incident_id": issue_id, "issue_type": category,
                "severity": "Medium", "resolution_status": "Open", "verification_status": "Needs review",
                "ward_id": ward, "ward_name": "Simulated ward", "neighbourhood_id": "unassigned",
                "neighbourhood_name": "Simulated location", "address": "Simulated Toronto report",
                "geometry": {"type": "Point", "coordinates": [-79.59 + int(ward) * 0.016, 43.68]},
                "location_radius_m": 1000, "geo_confidence": 0, "geo_method": "Fictional replay",
                "geo_trace": [], "geo_clues": [], "nearby_assets": [], "infrastructure_type": None,
                "asset_id": None, "asset_name": None, "distance_m": None, "detection_confidence": 0,
                "sightings_count": 0, "priority_score": 25, "priority_reasons": ["Fictional replay"],
                "source_category": "Community submission", "description": "Simulated data for the Tiger Data demonstration.",
                "explanation": "This record does not describe a real civic issue.", "evidence_thumbnail": None,
                "evidence_credit": None, "is_demo": True, "first_seen_at": iso(reported), "last_seen_at": iso(reported)}
        issue = public[issue_id]
        issue["sightings_count"] += 1
        issue["first_seen_at"] = min(issue["first_seen_at"], iso(reported))
        issue["last_seen_at"] = max(issue["last_seen_at"], iso(reported))
        sightings.append({"sighting_id": f"replay-{n}", "issue_id": issue_id, "ward_id": ward,
                          "issue_type": category, "reported_at": iso(reported), "timestamp_basis": "source"})
    report = {"generated_at": iso(anchor), "counts": {"input_records": events, "records": events,
              "sightings": events, "issues": len(public), "dropped": 0}, "simulated": True}
    return sync(list(public.values()), sightings, report, dataset="replay")


def benchmark(dataset="replay"):
    params = (dataset_name(dataset), datetime.now(UTC) - timedelta(days=90))
    raw = """SELECT time_bucket('1 hour', reported_at) AS bucket, ward_id, issue_type, count(*)
        FROM geoissue.sightings WHERE dataset = %s AND reported_at >= time_bucket('1 hour', %s::timestamptz)
        GROUP BY bucket, ward_id, issue_type ORDER BY bucket, ward_id, issue_type"""
    aggregate = """SELECT bucket, ward_id, issue_type, sum(reports)
        FROM geoissue.ward_activity_hourly WHERE dataset = %s AND bucket >= time_bucket('1 hour', %s::timestamptz)
        GROUP BY bucket, ward_id, issue_type ORDER BY bucket, ward_id, issue_type"""
    timings = {"raw": [], "aggregate": []}
    with connection() as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for _ in range(5):
            results = []
            for label, sql in (("raw", raw), ("aggregate", aggregate)):
                start = perf_counter()
                results.append(conn.execute(sql, params).fetchall())
                timings[label].append((perf_counter() - start) * 1000)
            if results[0] != results[1]:
                raise ValueError("Raw and aggregate counts differ; refresh the continuous aggregate before benchmarking.")
        size = conn.execute("SELECT hypertable_size('geoissue.sightings')").fetchone()[0]
        storage = columnstore_stats(conn)
    return {"dataset": dataset, "results_match": True, "buckets": len(results[0]),
            "median_ms": {label: round(statistics.median(times), 3) for label, times in timings.items()},
            "shared_hypertable_bytes": size, "runs": 5,
            "shared_columnstore": storage}


def compress_history():
    """Run columnstore conversion now for chunks older than one day; data remains queryable."""
    with connection() as conn:
        chunks = conn.execute("SELECT show_chunks('geoissue.sightings', older_than => INTERVAL '1 day')").fetchall()
        for (chunk,) in chunks:
            conn.execute("CALL convert_to_columnstore(%s::regclass)", (chunk,))
    return {"converted_or_already_columnstore_chunks": len(chunks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "replay", "benchmark", "compress"))
    parser.add_argument("--events", type=int, default=10000)
    parser.add_argument("--dataset", choices=DATASETS, default="replay")
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize()
            print("Tiger Data schema ready.")
        elif args.command == "replay":
            print(json.dumps(replay(args.events), indent=2))
        elif args.command == "compress":
            print(json.dumps(compress_history(), indent=2))
        else:
            print(json.dumps(benchmark(args.dataset), indent=2))
    except (Unavailable, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    except Exception:
        parser.exit(1, "Tiger Data operation failed. Check schema initialization, service version and database permissions.\n")


if __name__ == "__main__":
    main()
