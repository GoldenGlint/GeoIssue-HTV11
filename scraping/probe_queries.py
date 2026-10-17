"""Rank searches by recent photos with problem words. No image downloads, no Gemini."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import requests

from .collectors import bluesky, mastodon, reddit
from .media import has_issue_words, write_json
from .paths import CONFIG, ROOT

RESULTS = ROOT / "research" / "results" / "query-probe-results.json"


def score(records):
    rows = [asdict(record) for record in records]
    return {
        "photo_posts": len({row["post_id"] for row in rows}),
        "images": len(rows),
        "issue_word_images": sum(has_issue_words(row) for row in rows),
        "issue_word_posts": len({row["post_id"] for row in rows if has_issue_words(row)}),
    }


def probe_bluesky(queries, *, since, now):
    results = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "CivicLens-Probe/0.1"
        for query in queries:
            posts, sources = bluesky.collect(session, [query], [], since=since, until=now,
                                             max_posts=100, max_pages=1)
            records, _ = bluesky.normalize(posts, since=since, now=now)
            results.append({"source": query, "posts": len(posts),
                            "errors": sources[0]["errors"], **score(records)})
    return results


def probe_mastodon(config, *, since, now):
    results = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "CivicLens-Probe/0.1"
        for tag in config["tags"]:
            statuses, sources = mastodon.collect(session, {**config, "tags": [tag]}, since=since)
            records, _, _ = mastodon.normalize(statuses, since=since, now=now)
            results.append({"source": f"#{tag}", "posts": len(statuses),
                            "errors": sources[0]["errors"], **score(records)})
    return results


def probe_reddit(config, *, since, now):
    results = []
    with requests.Session() as session:
        session.headers["User-Agent"] = "CivicLens-Probe/0.1"
        for sub in config["subreddits"]:
            posts, sources = reddit.collect(session, {**config, "subreddits": [sub]},
                                            since=since, until=now)
            records, _ = reddit.normalize(posts, since=since, now=now,
                                          max_images_per_post=config["max_images_per_post"])
            results.append({"source": f"r/{sub}", "posts": len(posts),
                            "errors": sources[0]["errors"], **score(records)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("bluesky", "mastodon", "reddit"))
    parser.add_argument("--query", action="append", default=[], help="Bluesky search to test.")
    parser.add_argument("--query-file", type=Path, default=CONFIG / "bluesky-queries.txt")
    parser.add_argument("--config", type=Path, help="Mastodon or Reddit config JSON.")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if not 1 <= args.days <= 30:
        parser.exit(1, "Use 1–30 days.\n")
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.days)
    try:
        if args.platform == "bluesky":
            queries = args.query or bluesky.load_queries(args.query_file)
            if not 1 <= len(queries) <= 100:
                raise ValueError("Probe 1–100 queries at a time.")
            results = probe_bluesky(queries, since=since, now=now)
        elif args.platform == "mastodon":
            results = probe_mastodon(mastodon.load_config(args.config or mastodon.DEFAULT_CONFIG),
                                     since=since, now=now)
        else:
            results = probe_reddit(reddit.load_config(args.config or reddit.DEFAULT_CONFIG),
                                   since=since, now=now)
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"Probe stopped: {exc}\n")
    results.sort(key=lambda row: (-row["issue_word_images"], -row["images"]))
    previous = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.is_file() else {}
    previous[args.platform] = {"probed_at": now.isoformat(), "days": args.days, "results": results}
    write_json(RESULTS, previous)
    print(f"{'source':45} {'posts':>5} {'photos':>6} {'images':>6} {'issue imgs':>10}")
    for row in results:
        flag = "  ERROR" if row["errors"] else ""
        print(f"{row['source'][:45]:45} {row['posts']:5} {row['photo_posts']:6} {row['images']:6} "
              f"{row['issue_word_images']:10}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
