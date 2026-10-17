"""Run the standalone collector, process exports, and review images locally."""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil

from .collectors import instagram_apify as apify
from .media import (MediaRecord, assess_freshness, export_reviewed, process_media, read_jsonl,
                    write_gallery, write_json, write_jsonl)

from .paths import DATA


def merge_batches(batches, output):
    """Combine saved batches offline, preserving sources and excluding duplicates."""
    output = Path(output).resolve()
    if not output.is_relative_to(DATA.resolve()) or output.exists():
        raise ValueError("Choose a new output directory inside scraping/data for the combined gallery.")
    indexed, versions, images, pixels = {}, {}, {}, {}
    for batch in dict.fromkeys(Path(path).resolve() for path in batches):
        for original in read_jsonl(batch / "media.jsonl"):
            row = dict(original)
            version = (row.get("sha256"), row["auto_status"])
            if row["key"] in versions:
                if versions[row["key"]] != version:
                    raise ValueError("Batches contain conflicting versions of the same image. Select one version.")
                continue
            versions[row["key"]] = version
            row["freshness"] = assess_freshness(row)
            local = row.get("local_path")
            if local:
                if (not re.fullmatch(r"images/[a-f0-9]{64}\.jpg", local)
                        or Path(local).stem != row.get("sha256")
                        or not (batch / local).resolve().is_relative_to(batch)
                        or not (batch / local).is_file()):
                    raise ValueError("A batch image is missing or has an unsafe local path.")
                digest = row["sha256"]
                if digest in pixels:
                    row.update(auto_status="excluded", reasons=["duplicate_image"],
                               duplicate_of=pixels[digest], local_path=None)
                else:
                    pixels[digest] = row["key"]
                    images[local] = batch / local
            elif row["auto_status"] == "ready":
                raise ValueError("A ready image has no local file.")
            indexed[row["key"]] = row
    if not indexed:
        raise ValueError("The selected batches have no image records.")
    (output / "images").mkdir(parents=True)
    for local, source in images.items():
        shutil.copyfile(source, output / local)
    rows = list(indexed.values())
    write_jsonl(output / "media.jsonl", rows)
    recent = [row for row in rows if row["auto_status"] == "ready" and row["freshness"]["status"]
              in ("capture_time_unknown", "capture_time_recorded")]
    write_jsonl(output / "recent-candidates.jsonl", recent)
    write_gallery(output, rows, {"batch_id": output.name, "mode": "combined",
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "source_batches": [Path(path).name for path in batches],
                  "recent_upload_candidates": len(recent),
                  "review_status": "Unreviewed combined copy; source-gallery labels are not imported."})
    return rows


def finish(records, stats, output, since, metadata, hosts):
    # ponytail: cap this pilot at 100 images; use chunked jobs for sustained collection.
    if len(records) > 100:
        raise ValueError("The local demo accepts at most 100 images per batch.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "source-records.jsonl", [asdict(record) for record in records])
    rows = process_media(records, output, hosts=hosts, since=since)
    metadata = {"batch_id": output.name, "created_at": datetime.now(timezone.utc).isoformat(),
                "normalization": stats, **metadata}
    write_gallery(output, rows, metadata)
    ready = sum(row["auto_status"] == "ready" for row in rows)
    print(f"Prepared {len(rows)} images; {ready} are ready for review.")
    print(f"Gallery: {output.resolve() / 'index.html'}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("collect", "resume", "import-apify", "import-records"):
        command = commands.add_parser(name)
        command.add_argument("--out", type=Path, default=DATA / "live-demo")
        command.add_argument("--days", type=int, choices=range(1, 366), default=7, metavar="1..365")
        if name in ("import-apify", "import-records"):
            command.add_argument("file", type=Path)
        if name == "import-records":
            command.add_argument("--allow-host", action="append", required=True)
        if name == "collect":
            command.add_argument("--url", action="append", required=True)
            command.add_argument("--limit", type=int, choices=range(1, 11), default=10, metavar="1..10")
    serve = commands.add_parser("serve")
    serve.add_argument("--out", type=Path, default=DATA / "live-demo")
    serve.add_argument("--port", type=int, default=8765)
    merge = commands.add_parser("merge", help="Combine saved batches into a new gallery; no network calls.")
    merge.add_argument("--batch", action="append", type=Path, required=True)
    merge.add_argument("--out", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("--out", type=Path, default=DATA / "live-demo")
    export.add_argument("--labels", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "merge":
            rows = merge_batches(args.batch, args.out)
            print(f"Combined {len(rows)} image records. Gallery: {args.out.resolve() / 'index.html'}")
            return
        if args.command == "serve":
            if not (args.out / "index.html").is_file():
                raise ValueError("No gallery exists yet. Collect or import a batch first.")
            root = args.out.resolve()
            if not root.is_relative_to(DATA.resolve()):
                raise ValueError("Serve only an ignored scraping/data batch, never the repository or credentials.")

            class ReviewHandler(SimpleHTTPRequestHandler):
                def do_GET(self):
                    if self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1"):
                        self.send_error(403)
                        return
                    super().do_GET()

                def end_headers(self):
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    super().end_headers()

            print(f"Open http://127.0.0.1:{args.port}", flush=True)
            with ThreadingHTTPServer(("127.0.0.1", args.port), partial(ReviewHandler, directory=str(root))) as server:
                server.serve_forever()
            return
        if args.command == "export":
            labels = json.loads(args.labels.read_text())
            if isinstance(labels, dict):
                report = json.loads((args.out / "report.json").read_text())
                if labels.get("batch_id") != report["batch_id"]:
                    raise ValueError("Labels belong to a different batch.")
                labels = labels["labels"]
            accepted = export_reviewed(read_jsonl(args.out / "media.jsonl"), labels)
            write_jsonl(args.out / "accepted.jsonl", accepted)
            print(f"Exported {len(accepted)} explicitly approved images to {args.out / 'accepted.jsonl'}")
            return
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        metadata = {"mode": "imported", "out_of_pocket_usd": 0}
        hosts = apify.IMAGE_HOSTS
        if args.command == "collect":
            items, budget = apify.collect(apify.load_token(), args.url, args.out, limit=args.limit, since=since)
            records, stats = apify.normalize(items)
            metadata.update(mode="live", budget=budget)
        elif args.command == "resume":
            token = apify.load_token()
            budget = apify.preflight(token)
            state = json.loads((args.out / "apify-run.json").read_text())
            if not state.get("run_id"):
                raise ValueError("No run ID was received. Inspect Apify Console before any new launch.")
            records, stats = apify.normalize(apify.read_run(token, state["run_id"], args.out))
            metadata.update(mode="live", budget=budget)
        elif args.command == "import-apify":
            records, stats = apify.normalize(json.loads(args.file.read_text()))
        else:
            records = [MediaRecord(**row) for row in read_jsonl(args.file)]
            stats = {"source_items": len(records)}
            hosts = tuple(args.allow_host)
        if (args.out / "apify-run.json").exists():
            metadata["run"] = json.loads((args.out / "apify-run.json").read_text())
        finish(records, stats, args.out, since, metadata, hosts)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Stopped: {exc}\n")


if __name__ == "__main__":
    main()
