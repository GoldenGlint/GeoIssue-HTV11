"""One bounded collection → screening → descriptions run. Never schedules itself."""

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

import requests

from . import describe, handoff, screen
from .collectors import bluesky, mastodon, reddit
from .media import assess_freshness, has_issue_words, read_jsonl, write_json, write_jsonl
from .paths import CONFIG, DATA
from .share import export


def rows_if_present(path):
    return read_jsonl(path) if Path(path).is_file() else []


def combine(batches, output):
    """Keep discovery provenance; choose current versions and deduplicate pixels."""
    indexed, files = {}, {}
    for batch in batches:
        batch = Path(batch)
        for original in rows_if_present(batch / "media.jsonl"):
            row = dict(original)
            previous = indexed.get(row["key"])
            found = list(dict.fromkeys((previous or {}).get("found_by", []) + row.get("found_by", [])))
            # Within one snapshot, a duplicate row can reference the same pixels as a ready row.
            if (previous and previous.get("sha256") == row.get("sha256")
                    and previous.get("local_path") and not row.get("local_path")):
                previous["found_by"] = found
                continue
            row.update(found_by=found, source_batch=batch.name, freshness=assess_freshness(row))
            if row.get("local_path"):
                files[row["key"]] = handoff.image_path(batch, row)
            indexed[row["key"]] = row
    if not indexed:
        raise ValueError("No source images are available; previous handoff has been preserved.")
    if output.exists():
        shutil.rmtree(output)
    (output / "images").mkdir(parents=True)
    seen = set()
    buckets = defaultdict(list)
    for row in indexed.values():
        digest = row.get("sha256")
        if row.get("local_path"):
            if digest in seen:
                row.update(auto_status="excluded", reasons=["duplicate_image"], local_path=None)
            else:
                seen.add(digest)
                shutil.copyfile(files[row["key"]], output / row["local_path"])
        buckets[row["platform"]].append(row)
    # Stable round-robin prevents one busy source consuming the whole model budget.
    queues = []
    for platform in sorted(buckets):
        values = sorted(buckets[platform], key=lambda row: row.get("sha256") or row["key"])
        values.sort(key=lambda row: not has_issue_words(row))
        queues.append(deque(values))
    rows = []
    while any(queues):
        for queue in queues:
            if queue:
                rows.append(queue.popleft())
    write_jsonl(output / "media.jsonl", rows)
    return rows


def summarize(rows, baseline_hashes=()):
    baseline_hashes = set(baseline_hashes)
    supported = [row for row in rows if (row.get("issue_details") or {}).get("issue_supported") == "yes"]
    return {
        "passed_images": len(rows),
        "post_groups": len({(row["platform"], row["post_id"]) for row in rows}),
        "supported_images": len(supported),
        "supported_post_groups": len({(row["platform"], row["post_id"]) for row in supported}),
        "new_passed_images": sum(row["sha256"] not in baseline_hashes for row in rows),
        "new_supported_images": sum(row["sha256"] not in baseline_hashes for row in supported),
        "needs_review_images": sum((row.get("issue_details") or {}).get("issue_supported") in ("no", "uncertain") for row in rows),
        "by_platform": dict(Counter(row["platform"] for row in rows)),
    }


def run(*, output=DATA / "workflow", config_path=CONFIG / "workflow.json",
        max_screen_requests=300, max_description_requests=100, exploration_images=50,
        skip_collect=False, include_batches=(), apify_pilots=False):
    output = Path(output).resolve()
    if not output.is_relative_to(DATA.resolve()) or output == DATA.resolve():
        raise ValueError("Workflow output must be a subdirectory inside scraping/data.")
    if not 0 <= exploration_images <= max_screen_requests <= 5000 or not 0 <= max_description_requests <= 5000:
        raise ValueError("Use bounded request budgets; exploration must fit screening.")
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".workflow.lock"
    with lock.open("x"):
        pass
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "sources": [], "errors": [], "scheduled": False, "apify_pilots": apify_pilots}
    report_path = output / "workflow-report.json"

    def save():
        write_json(report_path, report)

    try:
        baseline_path = output / "baseline.json"
        if not baseline_path.exists():
            baseline = rows_if_present(output / "handoff" / "passed.jsonl") or rows_if_present(DATA / "handoff" / "passed.jsonl")
            write_json(baseline_path, {**summarize(baseline), "hashes": [row["sha256"] for row in baseline]})
        baseline = json.loads(baseline_path.read_text())
        previous_path = output / "previous-run.json"
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else baseline
        batches = []
        recipe = json.loads(Path(config_path).read_text())
        for source in recipe["sources"]:
            name, platform = source["name"], source["platform"]
            if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
                raise ValueError("Invalid source batch name.")
            batch = DATA / name
            result = {"name": name, "platform": platform}
            try:
                if not skip_collect:
                    print(f"Collecting {name}...", flush=True)
                    if platform == "bluesky":
                        source_report = bluesky.run(queries=bluesky.load_queries(CONFIG / source["queries"]),
                            output=batch, days=7, max_posts=source.get("max_posts", 100), max_pages=1,
                            max_images=source.get("max_images", 200), pool="live")
                    elif platform in ("reddit", "mastodon"):
                        collector = reddit if platform == "reddit" else mastodon
                        source_report = collector.run(config_path=CONFIG / source["config"], output=batch)
                    else:
                        raise ValueError("Unsupported workflow source.")
                    result["status"] = source_report.get("status", "ok")
                else:
                    result["status"] = "saved_batch"
                if not (batch / "media.jsonl").is_file():
                    raise ValueError("Source batch is not available.")
                batches.append(batch)
                result["images"] = len(rows_if_present(batch / "media.jsonl"))
            except (ValueError, OSError, requests.RequestException) as error:
                result.update(status="failed", error=str(error)[:240])
                report["errors"].append(f"{name}: {type(error).__name__}")
            report["sources"].append(result)
            save()
        if apify_pilots:
            from .collectors.social_apify import run_pilots
            pilots = run_pilots(output / "pilots")
            report["pilots"] = pilots
            batches.extend(Path(item["batch"]) for item in pilots if item.get("batch"))
            save()
        for batch in include_batches:
            batch = Path(batch).resolve()
            if not batch.is_relative_to(DATA.resolve()) or not (batch / "media.jsonl").is_file():
                raise ValueError("Include only existing source batches inside scraping/data.")
            batches.insert(0, batch)
        cache = screen.load_cache(screen.SHARED_CACHE)
        for path in sorted(DATA.rglob("screening.jsonl")):
            cache.update(screen.load_cache(path))
        cache_path = output / "screening-cache.jsonl"
        cache.update(screen.load_cache(cache_path))
        write_jsonl(cache_path, list(cache.values()))
        combined = output / "combined"
        if combined in batches or any(combined in batch.parents for batch in batches):
            raise ValueError("Combined output cannot be an input batch.")
        rows = combine(batches, combined)
        report["collected_images"] = len(rows)
        report["distinct_ready_images"] = len({row["sha256"] for row in rows if row.get("auto_status") == "ready"})
        print(f"Screening {report['distinct_ready_images']} distinct images...", flush=True)
        report["screening"] = screen.screen_batch(combined, max_requests=max_screen_requests,
            exploration_limit=exploration_images, shared_cache=cache_path)
        save()
        cache.update(screen.load_cache(combined / "screening.jsonl"))
        write_jsonl(cache_path, list(cache.values()))
        handoff.build([combined], output / "handoff")
        report["descriptions"] = describe.run(output / "handoff", max_requests=max_description_requests)
        passed = rows_if_present(output / "handoff" / "passed.jsonl")
        report.update(summarize(passed, baseline["hashes"]))
        report["new_since_previous_run"] = summarize(passed, previous["hashes"])["new_passed_images"]
        report["baseline"] = {key: value for key, value in baseline.items() if key != "hashes"}
        report["context_images"] = sum(len(group["supplemental_images"]) for group in rows_if_present(output / "handoff" / "post-groups.jsonl"))
        discoveries = defaultdict(lambda: {"passed_images": 0, "supported_images": 0})
        for row in passed:
            for found in row.get("found_by") or [row["platform"]]:
                discoveries[found]["passed_images"] += 1
                discoveries[found]["supported_images"] += (row.get("issue_details") or {}).get("issue_supported") == "yes"
        report["discovery_yield_overlapping"] = dict(sorted(discoveries.items(), key=lambda item: -item[1]["supported_images"]))
        # Text-only exports can be downloaded in Actions; unblurred images remain local/ephemeral.
        export(output / "handoff", output / "export")
        shutil.copyfile(cache_path, output / "export" / "screening-cache.jsonl")
        report["status"] = "partial" if (report["errors"] or report["screening"]["status"] != "ok"
            or report["descriptions"]["status"] != "ok"
            or any(pilot["status"] != "ok" for pilot in report.get("pilots", []))) else "ok"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        save()
        write_json(previous_path, {**summarize(passed), "hashes": [row["sha256"] for row in passed]})
        return report
    except Exception as error:
        report.update(status="failed", completed_at=datetime.now(timezone.utc).isoformat())
        report["fatal_error"] = f"{type(error).__name__}: {str(error)[:240]}"
        save()
        raise
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DATA / "workflow")
    parser.add_argument("--config", type=Path, default=CONFIG / "workflow.json")
    parser.add_argument("--max-screen-requests", type=int, default=300)
    parser.add_argument("--max-description-requests", type=int, default=100)
    parser.add_argument("--exploration-images", type=int, default=50)
    parser.add_argument("--skip-collect", action="store_true", help="Resume processing saved source batches.")
    parser.add_argument("--include-batch", action="append", type=Path, default=[])
    parser.add_argument("--apify-pilots", action="store_true", help="Opt in to one capped pilot per configured actor.")
    args = parser.parse_args()
    try:
        report = run(output=args.output, config_path=args.config,
            max_screen_requests=args.max_screen_requests, max_description_requests=args.max_description_requests,
            exploration_images=args.exploration_images, skip_collect=args.skip_collect,
            include_batches=args.include_batch, apify_pilots=args.apify_pilots)
    except (ValueError, OSError, requests.RequestException) as error:
        parser.exit(1, f"Workflow stopped: {type(error).__name__}. Inspect the saved workflow report.\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
