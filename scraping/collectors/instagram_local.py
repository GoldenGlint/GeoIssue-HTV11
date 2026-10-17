"""Local Instaloader login and bounded public location collection.

Run with ``python -m scraping.collectors.instagram_local`` from the repository root.
"""

import argparse
import contextlib
from dataclasses import asdict
from datetime import datetime, timezone
import io
import itertools
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

import instaloader
import requests

from ..media import MediaRecord, parse_time, process_media, redact_text, write_json, write_jsonl
from ..paths import DATA as DATA_ROOT
from .instagram_urls import target_kind


TORONTO_URL = "https://www.instagram.com/explore/locations/110941395597405/toronto-ontario/"
SESSION_FILE = DATA_ROOT / "instaloader" / "session.json"
IMAGE_HOSTS = ("cdninstagram.com", "fbcdn.net")


def location_id(value):
    if re.fullmatch(r"[0-9]{1,25}", value):
        return value
    if target_kind(value) != "location":
        raise ValueError("Use an Instagram location URL or numeric location ID.")
    return urlsplit(value).path.split("/")[3]


def make_loader(*, quiet=True):
    return instaloader.Instaloader(
        quiet=quiet, max_connection_attempts=1, request_timeout=15,
        download_comments=False, download_geotags=False, save_metadata=False,
        fatal_status_codes=[401, 403, 429],
    )


def save_session(loader, username, path=SESSION_FILE):
    """Use Instaloader's cookie-dict API; no password or pickle is stored."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump({"username": username, "cookies": loader.save_session()}, handle)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def load_session(loader, path=SESSION_FILE):
    path = Path(path)
    if not path.is_file():
        raise ValueError("No local session. Run: python -m scraping.instagram_local login")
    try:
        data = json.loads(path.read_text())
        username, cookies = data["username"], data["cookies"]
        if (not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username)
                or not isinstance(cookies, dict)
                or not cookies.get("sessionid") or not cookies.get("csrftoken")
                or not all(isinstance(key, str) and isinstance(value, str)
                           for key, value in cookies.items())):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ValueError("Invalid local session file. Run local login again.") from None
    os.chmod(path, 0o600)
    loader.load_session(username, cookies)


def login():
    if not sys.stdin.isatty():
        raise ValueError("Run login in your own interactive terminal; never paste a password into chat.")
    username = input("Instagram username: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", username):
        raise ValueError("Enter a valid Instagram username.")
    with make_loader(quiet=False) as loader:
        # Instaloader handles the hidden password prompt and optional 2FA.
        loader.interactive_login(username)
        save_session(loader, username)
    return {"status": "session_saved", "session_file": str(SESSION_FILE),
            "password_saved": False, "out_of_pocket_usd": 0}


def normalize_post(post, queried_location):
    """Return only known-public image posts; preserve original carousel indices."""
    if post.owner_profile.is_private is not False:
        return [], "not_known_public"
    if post.typename == "GraphVideo":
        return [], "video"
    if post.typename not in ("GraphImage", "GraphSidecar"):
        return [], "unsupported_media"
    posted = post.date_utc
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    posted_at = posted.astimezone(timezone.utc).isoformat()
    evidence = [{"kind": "location_query", "location_id": queried_location,
                 "precision": "place", "camera_location_verified": False}]
    caption = redact_text(post.caption)
    records = []
    nodes = (enumerate(post.get_sidecar_nodes()) if post.typename == "GraphSidecar"
             else [(0, post)])
    for index, node in nodes:
        if node.is_video:
            continue
        records.append(MediaRecord(
            platform="instagram", collector="instaloader", post_id=str(post.mediaid),
            media_index=index, media_url=(node.display_url if post.typename == "GraphSidecar"
                                         else post.url), posted_at=posted_at,
            caption=caption, location_evidence=evidence,
        ))
    return records, None


def error_message(exc):
    """Actionable errors without echoing cookies, handles, or request URLs."""
    text = str(exc).lower()
    if any(word in text for word in ("429", "please wait", "feedback_required")):
        return "Instagram limited the requests. Stop and wait before trying again."
    if any(word in text for word in ("checkpoint", "challenge", "401", "403", "login page")):
        return "Instagram requires a sign-in check. Resolve it in Instagram, then run local login again."
    if "201" in text or "native_location_data" in text:
        return "Instagram's location endpoint returned an incompatible response. Collection stopped."
    if isinstance(exc, instaloader.exceptions.InstaloaderException):
        return "Instaloader could not complete the request. Collection stopped without retrying."
    if isinstance(exc, requests.RequestException):
        return "Instagram connection failed. Collection stopped without retrying."
    return "Collection could not read the expected Instagram data. No raw response was saved."


def collect_records(loader, queried_location, *, limit=10, since=None):
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Use a post limit between 1 and 50.")
    records, seen, dates = [], set(), []
    report = {"status": "ok", "location_id": queried_location, "post_limit": limit,
              "posts_scanned": 0, "posts_skipped": {}, "errors": [],
              "ordering": "newest_first_among_fetched", "out_of_pocket_usd": 0}
    try:
        for post in itertools.islice(loader.get_location_posts(queried_location), limit):
            report["posts_scanned"] += 1
            normalized, reason = normalize_post(post, queried_location)
            if normalized:
                date = parse_time(normalized[0].posted_at)
                dates.append(date)
                if since and date < since:
                    normalized, reason = [], "older_than_posting_window"
            if reason:
                counts = report["posts_skipped"]
                counts[reason] = counts.get(reason, 0) + 1
            for record in normalized:
                if record.key not in seen:
                    seen.add(record.key)
                    records.append(record)
    except (instaloader.exceptions.InstaloaderException, requests.RequestException,
            ValueError, KeyError, TypeError, AttributeError) as exc:
        report["errors"].append({"type": type(exc).__name__, "detail": error_message(exc)})
        report["status"] = "partial" if records else "failed"
    records.sort(key=lambda record: parse_time(record.posted_at), reverse=True)
    report.update(image_candidates=len(records),
                  fetched_sample_in_descending_order=(all(a >= b for a, b in zip(dates, dates[1:]))
                                                      if len(dates) > 1 else None))
    if not records and not report["errors"]:
        report["status"] = "empty"
    return records, report


def collect(target=TORONTO_URL, *, limit=10, since=None, metadata_only=False, output=None):
    queried_location = location_id(target)
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Use a post limit between 1 and 50.")
    output = (Path(output) if output else DATA_ROOT / "instaloader" / "collections" /
              datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Choose a new or empty output directory to preserve previous results.")
    # Keep raw SDK logs in memory; only the sanitized report is written below.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured), make_loader() as loader:
        load_session(loader)
        records, report = collect_records(loader, queried_location, limit=limit, since=since)
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "candidates.jsonl", [asdict(record) for record in records])
    if not metadata_only and records and not report["errors"]:
        rows = process_media(records, output, hosts=IMAGE_HOSTS, since=since)
        report.update(downloaded_images=sum(row["local_path"] is not None for row in rows),
                      download_failed=sum(row["auto_status"] == "download_failed" for row in rows))
        if report["download_failed"]:
            report["status"] = "partial" if report["downloaded_images"] else "failed"
    else:
        report["downloaded_images"] = 0
    report.update(collector_version=instaloader.__version__, metadata_only=metadata_only,
                  output_dir=str(output.resolve()), review_status="unreviewed",
                  captured_at=None)
    write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="Sign in locally and save an ignored session file.")
    collector = commands.add_parser("collect", help="Collect a bounded sample of public location posts.")
    collector.add_argument("location", nargs="?", default=TORONTO_URL)
    collector.add_argument("--limit", type=int, default=10)
    collector.add_argument("--since", help="ISO timestamp with timezone, e.g. 2026-10-10T00:00:00Z")
    collector.add_argument("--metadata-only", action="store_true")
    collector.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = (login() if args.command == "login" else collect(
            args.location, limit=args.limit, since=parse_time(args.since) if args.since else None,
            metadata_only=args.metadata_only, output=args.output))
    except (ValueError, OSError) as exc:
        # Local validation messages contain no third-party response data.
        if args.command == "login" and not isinstance(exc, ValueError):
            detail = "Could not save the local session. Check the data-directory permissions."
        else:
            detail = str(exc) if isinstance(exc, ValueError) else "Could not read or write the local collection."
        print(json.dumps({"status": "failed", "detail": detail}), file=sys.stderr)
        return 1
    except (instaloader.exceptions.InstaloaderException, requests.RequestException,
            KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "detail": error_message(exc)}), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Local operation cancelled.", file=sys.stderr)
        return 130
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("ok", "session_saved") else 1


if __name__ == "__main__":
    sys.exit(main())
