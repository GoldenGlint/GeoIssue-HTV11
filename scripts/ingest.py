"""Publish one bounded Bluesky collection. A failed run leaves the last good snapshot in place.

Usage:  CIVICLENS_PUBLISHED_DIR=/var/lib/civiclens/published python scripts/ingest.py
        python scripts/ingest.py --republish 20261018T041500Z
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis import pipeline, tiger  # noqa: E402
from analysis.config import load, setting  # noqa: E402
from scraping import workflow  # noqa: E402
from scraping.paths import DATA  # noqa: E402

GENERATION = re.compile(r"^\d{8}T\d{6}Z(?:-\d+)?$")
PHOTO_URL = re.compile(r"^\./data/analyzed/photos/([^/]+)$")
VULTR_CONFIG = ROOT / "scraping" / "config" / "workflow-vultr.json"
KEEP_GENERATIONS = 3
SEEDED = "initial"


class IngestError(RuntimeError):
    pass


def execute(published_dir, *, allow_empty=False, republish=None,
            max_screen_requests=20, max_description_requests=20, workflow_output=None):
    """Run collection and publish it, or point the site back at an existing generation."""
    published = Path(published_dir).resolve()
    published.mkdir(parents=True, exist_ok=True)
    with locked(published):
        if republish:
            swap_current(published, generation_dir(published, republish))
            return {"generation": republish, "republished": True}
        if not 0 <= max_screen_requests <= 5000 or not 0 <= max_description_requests <= 5000:
            raise IngestError("Use bounded request budgets (0–5000).")
        output = Path(workflow_output) if workflow_output else DATA / "vultr-workflow"
        (output / ".workflow.lock").unlink(missing_ok=True)
        try:
            report = workflow.run(
                output=output,
                config_path=VULTR_CONFIG,
                max_screen_requests=max_screen_requests,
                max_description_requests=max_description_requests,
                exploration_images=0,
            )
        except IngestError:
            raise
        except Exception as error:
            raise IngestError(
                f"Workflow stopped ({type(error).__name__}). The published snapshot was not changed."
            ) from error
        if report.get("status") != "ok":
            raise IngestError(
                f"Workflow status is {report.get('status', 'unknown')}; the published snapshot was not changed."
            )
        handoff = output / "handoff" / "post-groups.jsonl"
        if not handoff.is_file():
            raise IngestError("Workflow finished without a handoff. The published snapshot was not changed.")
        generation = new_generation(published)
        keep = False
        try:
            copy_summary_cache(published, generation)
            result = pipeline.run(handoff, load(), out_dir=generation, photo_url_prefix="./data/analyzed/")
            public = load_public(generation)
            validate(public, generation, published, allow_empty)
            write_status(generation, len(public))
            if setting("TIGER_DATABASE_URL"):
                tiger.sync(public, result["events"], result["report"], result["areas"])
            keep = True
            swap_current(published, generation)
        except IngestError:
            if not keep:
                shutil.rmtree(generation, ignore_errors=True)
            raise
        except Exception as error:
            if not keep:
                shutil.rmtree(generation, ignore_errors=True)
                raise IngestError(
                    f"Ingest stopped ({type(error).__name__}). The last published snapshot was kept."
                ) from error
            raise IngestError(
                "Database updated but the site was not switched "
                f"({type(error).__name__}). Repair with: python scripts/ingest.py --republish {generation.name}"
            ) from error
        try:
            prune(published)
        except OSError as error:
            raise IngestError(
                f"Published {generation.name}, but old generations could not be removed ({type(error).__name__})."
            ) from error
        return {"generation": generation.name, "issue_count": len(public)}


@contextmanager
def locked(published):
    handle = open(published / "ingest.lock", "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise IngestError("Another ingest is already running.") from None
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def generation_dir(published, name):
    if name != SEEDED and not GENERATION.fullmatch(name):
        raise IngestError("Unknown generation.")
    root = (published / "generations").resolve()
    try:
        path = (root / name).resolve()
    except OSError:
        raise IngestError("Unknown generation.") from None
    if not path.is_relative_to(root) or not path.is_dir() or not (path / "issues.public.json").is_file():
        raise IngestError("Unknown generation.")
    return path


def new_generation(published):
    generations = published / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = generations / stamp
    suffix = 2
    while candidate.exists():
        candidate = generations / f"{stamp}-{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def copy_summary_cache(published, generation):
    link = published / "current"
    if not link.is_symlink() and not link.exists():
        return
    try:
        source = (link / ".summary_cache.json").resolve()
        if source.is_file() and source.is_relative_to(published.resolve()):
            shutil.copyfile(source, generation / ".summary_cache.json")
    except OSError:
        return


def load_public(generation):
    try:
        data = json.loads((generation / "issues.public.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IngestError("issues.public.json is missing or not valid JSON.") from error
    if not isinstance(data, list):
        raise IngestError("issues.public.json must be a list.")
    return data


def previous_issue_count(published):
    link = published / "current"
    if not link.is_symlink() and not link.exists():
        return 0
    try:
        path = (link / "issues.public.json").resolve()
        if not path.is_relative_to(published.resolve()) or not path.is_file():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return len(data) if isinstance(data, list) else 0


def validate(public, generation, published, allow_empty):
    if len(public) == 0 and previous_issue_count(published) > 0 and not allow_empty:
        raise IngestError(
            "Refusing to replace a non-empty snapshot with zero issues. Pass --allow-empty to publish it."
        )
    for issue in public:
        if not isinstance(issue, dict):
            raise IngestError("Public issues must be objects.")
        check_photo(issue.get("evidence_thumbnail"), generation)
        photos = issue.get("evidence_photos") or []
        if isinstance(photos, str):
            photos = [photos]
        for photo in photos:
            check_photo(photo.get("url") if isinstance(photo, dict) else photo, generation)


def check_photo(url, generation):
    if url is None:
        return
    if isinstance(url, str) and url.startswith("https://"):
        return
    match = PHOTO_URL.fullmatch(url) if isinstance(url, str) else None
    if not match:
        raise IngestError("Evidence URL is not a public https URL or ./data/analyzed/photos/<file>.")
    name = match.group(1)
    if name in (".", "..") or name.startswith(".") or "/" in name or "\\" in name:
        raise IngestError("Evidence photo name is not safe to publish.")
    try:
        photos = (generation / "photos").resolve()
        path = (photos / name).resolve()
    except OSError:
        raise IngestError(f"Missing published photo {name}.") from None
    if not path.is_relative_to(photos) or not path.is_file():
        raise IngestError(f"Missing published photo {name}.")


def write_status(generation, count):
    payload = {
        "last_success_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
        "issue_count": count,
    }
    (generation / "ingest-status.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def swap_current(published, generation):
    temporary = published / f".current-next-{os.getpid()}"
    if temporary.is_symlink() or temporary.exists():
        temporary.unlink()
    temporary.symlink_to(Path("generations") / generation.name)
    os.replace(temporary, published / "current")


def prune(published, keep=KEEP_GENERATIONS):
    generations = published / "generations"
    stamped = sorted(path for path in generations.iterdir() if path.is_dir() and GENERATION.fullmatch(path.name))
    current = None
    link = published / "current"
    if link.is_symlink():
        try:
            current = link.resolve()
        except OSError:
            current = None
    for old in stamped[:-keep] if len(stamped) > keep else []:
        if current is not None and old.resolve() == current:
            continue
        shutil.rmtree(old)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published-dir", default=os.environ.get("CIVICLENS_PUBLISHED_DIR"))
    parser.add_argument("--allow-empty", action="store_true",
                        help="Publish a snapshot with zero issues even when the current one has some.")
    parser.add_argument("--republish", help="Point the site at this existing generation and do nothing else.")
    parser.add_argument("--max-screen-requests", type=int, default=20)
    parser.add_argument("--max-description-requests", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.published_dir:
        parser.error("Set CIVICLENS_PUBLISHED_DIR or pass --published-dir.")
    try:
        result = execute(
            args.published_dir,
            allow_empty=args.allow_empty,
            republish=args.republish,
            max_screen_requests=args.max_screen_requests,
            max_description_requests=args.max_description_requests,
        )
    except IngestError as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
