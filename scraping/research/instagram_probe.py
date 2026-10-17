"""Bounded anonymous access probes. Does not save media, cookies, or raw responses."""

import argparse
import contextlib
import importlib.metadata
import io
import itertools
import json
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

from ..collectors.instagram_urls import target_kind
from ..paths import ROOT


def clean_error(message, target):
    message = str(message).replace(target.rstrip("/"), "[target]")
    for part in urlsplit(target).path.strip("/").split("/"):
        if len(part) > 2:
            message = message.replace(part, "[target]")
    message = re.sub(r"https?://\S+", "[url]", message)
    return message[:400]


def gallery_result(messages):
    """DataJob may return exit code zero while emitting an error message."""
    errors = [item[1] for item in messages if item and item[0] == -1]
    images = [item for item in messages if item and item[0] == 3]
    posts = [item for item in messages if item and item[0] == 2]
    unresolved = any(item and item[0] == 6 for item in messages)
    return {
        "status": "partial" if errors and images else
                  "failed" if errors else
                  "ok" if images else
                  "unresolved" if unresolved else "empty",
        "post_count": len(posts),
        "image_url_count": len(images),
        "errors": errors,
    }


def probe_gallery(url, limit):
    command = [
        sys.executable, "-m", "gallery_dl", "--config-ignore",
        "--cache-file", ":memory:", "--no-input", "--no-colors",
        "-R", "0", "--http-timeout", "12", "--resolve-json",
        "--post-range", f"1-{limit}", "--range", f"1-{limit * 20}",
        "-o", "extractor.instagram.user-cache=memory",
        "-o", "extractor.instagram.videos=false",
        "-o", "extractor.instagram.previews=false", url,
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    result = gallery_result(json.loads(process.stdout or "[]"))
    if process.returncode:
        result["status"] = "failed"
        result["errors"].append({"error": "ProcessError", "message": process.stderr})
    result["process_exit_code"] = process.returncode
    return result


def probe_instaloader(url, limit):
    import instaloader

    kind = target_kind(url)
    if kind in {"hashtag", "location"}:
        return {"status": "requires_login", "post_count": 0, "image_url_count": 0,
                "errors": [{"error": "DocumentedRestriction",
                            "message": "Instaloader documents login for this target; skipped."}]}
    with instaloader.Instaloader(
        quiet=True, max_connection_attempts=1, request_timeout=12,
        save_metadata=False, download_comments=False,
    ) as loader:
        path = urlsplit(url).path.strip("/").split("/")
        posts = ([instaloader.Post.from_shortcode(loader.context, path[1])]
                 if kind == "post" else
                 instaloader.Profile.from_username(loader.context, path[0]).get_posts())
        count = images = 0
        for post in itertools.islice(posts, limit):
            count += 1
            images += (sum(not node.is_video for node in post.get_sidecar_nodes())
                       if post.typename == "GraphSidecar" else int(not post.is_video))
        return {"status": "ok" if images else "empty", "post_count": count,
                "image_url_count": images, "errors": []}


def worker(provider, url, limit):
    # Third-party logs may contain handles or URLs; keep them out of the report.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            result = (probe_gallery(url, limit) if provider == "gallery-dl"
                      else probe_instaloader(url, limit))
    except Exception as exc:
        result = {"status": "failed", "post_count": 0, "image_url_count": 0,
                  "errors": [{"error": type(exc).__name__, "message": str(exc)}]}
    result["errors"] = [
        {"type": error.get("error", "UnknownError"),
         "detail": clean_error(error.get("message", ""), url)}
        for error in result["errors"]
    ]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("instaloader", "gallery-dl"))
    parser.add_argument("url")
    parser.add_argument("--limit", type=int, choices=range(1, 11), default=1, metavar="1..10")
    parser.add_argument("--timeout", type=int, choices=range(5, 61), default=45, metavar="5..60")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        kind = target_kind(args.url)
        version = importlib.metadata.version(args.provider)
    except (ValueError, importlib.metadata.PackageNotFoundError) as exc:
        parser.error(str(exc))
    if args.worker:
        print(json.dumps(worker(args.provider, args.url, args.limit)))
        return

    started = time.monotonic()
    # A process group also bounds gallery-dl's child process on POSIX systems.
    command = [sys.executable, "-m", "scraping.research.instagram_probe", args.provider,
               args.url, "--limit", str(args.limit), "--worker"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True, cwd=ROOT.parent)
    try:
        stdout, _ = process.communicate(timeout=args.timeout)
        result = json.loads(stdout)
    except subprocess.TimeoutExpired:
        import os
        import signal
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        result = {"status": "timeout", "post_count": 0, "image_url_count": 0,
                  "errors": [{"type": "Timeout", "detail": "Probe time limit reached."}]}
    except (ValueError, OSError):
        result = {"status": "probe_error", "errors": [
            {"type": "WorkerError", "detail": "Worker did not return a valid report."}]}
    print(json.dumps({"provider": args.provider, "version": version,
                      "target_kind": kind, "anonymous": True, "media_downloaded": False,
                      "elapsed_seconds": round(time.monotonic() - started, 2), **result}, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
