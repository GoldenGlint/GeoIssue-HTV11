"""Failure boundaries for scripts/ingest.py. No network and no database."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("civiclens_ingest", ROOT / "scripts" / "ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

ISSUE = {
    "issue_id": "CL-1",
    "evidence_thumbnail": "./data/analyzed/photos/CL-1.jpg",
    "evidence_photos": [{"url": "./data/analyzed/photos/CL-1.jpg", "role": "evidence"}],
}


def seed(published, name, issues):
    generation = published / "generations" / name
    generation.mkdir(parents=True, exist_ok=True)
    (generation / "issues.public.json").write_text(json.dumps(issues), encoding="utf-8")
    link = published / "current"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(Path("generations") / name, target_is_directory=True)
    return generation


def ok_workflow(output):
    handoff = Path(output) / "handoff"
    handoff.mkdir(parents=True, exist_ok=True)
    (handoff / "post-groups.jsonl").write_text("", encoding="utf-8")
    return {"status": "ok"}


def write_public(generation, issues):
    generation = Path(generation)
    (generation / "photos").mkdir(parents=True, exist_ok=True)
    (generation / "issues.public.json").write_text(json.dumps(issues), encoding="utf-8")
    for issue in issues:
        for url in [issue.get("evidence_thumbnail")] + [photo.get("url") for photo in issue.get("evidence_photos") or []]:
            if isinstance(url, str) and url.startswith("./data/analyzed/photos/"):
                (generation / "photos" / url.rsplit("/", 1)[1]).write_bytes(b"jpeg")
    return {"events": [{"sighting_id": issue["issue_id"]} for issue in issues], "report": {}, "areas": None}


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.published = Path(self.tmp.name) / "published"
        self.published.mkdir()
        self.workflow_output = Path(self.tmp.name) / "workflow"
        seed(self.published, "initial", [ISSUE])

    def execute(self, **kwargs):
        kwargs.setdefault("workflow_output", self.workflow_output)
        return ingest.execute(self.published, **kwargs)

    def test_a_partial_workflow_does_not_publish(self):
        lock = self.workflow_output / ".workflow.lock"
        lock.parent.mkdir()
        lock.write_text("stale", encoding="utf-8")

        def fake_workflow(**kwargs):
            self.assertFalse(lock.exists())
            self.assertEqual(kwargs["exploration_images"], 0)
            self.assertEqual(kwargs["max_screen_requests"], 20)
            return {"status": "partial"}

        with patch.object(ingest.workflow, "run", fake_workflow), \
             patch.object(ingest.pipeline, "run", side_effect=AssertionError("pipeline")), \
             patch.object(ingest, "setting", return_value="postgresql://example"), \
             patch.object(ingest.tiger, "sync", side_effect=AssertionError("database")):
            with self.assertRaises(ingest.IngestError) as caught:
                self.execute()
        self.assertIn("partial", str(caught.exception))
        self.assertEqual((self.published / "current").resolve().name, "initial")
        self.assertEqual(list((self.published / "generations").iterdir()), [self.published / "generations" / "initial"])

    def test_an_empty_result_does_not_replace_a_non_empty_snapshot(self):
        def analyze(*args, **kwargs):
            return write_public(kwargs["out_dir"], [])

        with patch.object(ingest.workflow, "run", side_effect=lambda **kwargs: ok_workflow(kwargs["output"])), \
             patch.object(ingest.pipeline, "run", analyze), \
             patch.object(ingest, "setting", return_value="postgresql://example"), \
             patch.object(ingest.tiger, "sync", side_effect=AssertionError("database")):
            with self.assertRaises(ingest.IngestError) as caught:
                self.execute()
        self.assertIn("zero issues", str(caught.exception))
        self.assertEqual((self.published / "current").resolve().name, "initial")
        self.assertFalse(any(ingest.GENERATION.fullmatch(path.name) for path in (self.published / "generations").iterdir()))

    def test_allow_empty_publishes_zero_issues(self):
        synced = []

        def analyze(*args, **kwargs):
            return write_public(kwargs["out_dir"], [])

        with patch.object(ingest.workflow, "run", side_effect=lambda **kwargs: ok_workflow(kwargs["output"])), \
             patch.object(ingest.pipeline, "run", analyze), \
             patch.object(ingest, "setting", return_value="postgresql://example"), \
             patch.object(ingest.tiger, "sync", side_effect=lambda *args, **kwargs: synced.append(args[0]) or {"reports": 0}):
            result = self.execute(allow_empty=True)
        self.assertEqual(result["issue_count"], 0)
        self.assertEqual(synced, [[]])
        self.assertEqual((self.published / "current").resolve().name, result["generation"])

    def test_a_database_failure_keeps_the_current_generation(self):
        def analyze(*args, **kwargs):
            return write_public(kwargs["out_dir"], [ISSUE])

        with patch.object(ingest.workflow, "run", side_effect=lambda **kwargs: ok_workflow(kwargs["output"])), \
             patch.object(ingest.pipeline, "run", analyze), \
             patch.object(ingest, "setting", return_value="postgresql://example"), \
             patch.object(ingest.tiger, "sync", side_effect=ingest.tiger.Unavailable("Tiger Data is unreachable.")) :
            with self.assertRaises(ingest.IngestError) as caught:
                self.execute()
        self.assertIn("kept", str(caught.exception))
        self.assertEqual((self.published / "current").resolve().name, "initial")
        self.assertFalse(any(ingest.GENERATION.fullmatch(path.name) for path in (self.published / "generations").iterdir()))

    def test_a_bad_photo_url_is_not_published(self):
        bad = {**ISSUE, "evidence_thumbnail": "file:///tmp/secret.jpg"}

        def analyze(*args, **kwargs):
            return write_public(kwargs["out_dir"], [bad])

        with patch.object(ingest.workflow, "run", side_effect=lambda **kwargs: ok_workflow(kwargs["output"])), \
             patch.object(ingest.pipeline, "run", analyze), \
             patch.object(ingest, "setting", return_value="postgresql://example"), \
             patch.object(ingest.tiger, "sync", side_effect=AssertionError("database")):
            with self.assertRaises(ingest.IngestError):
                self.execute()
        self.assertEqual((self.published / "current").resolve().name, "initial")

    def test_a_successful_run_swaps_current_and_repeats_without_growing(self):
        synced = []

        def analyze(*args, **kwargs):
            return write_public(kwargs["out_dir"], [ISSUE])

        def sync(public, events, report, areas=None, dataset="pipeline"):
            synced.append([issue["issue_id"] for issue in public])
            return {"reports": len(events)}

        with patch.object(ingest.workflow, "run", side_effect=lambda **kwargs: ok_workflow(kwargs["output"])), \
             patch.object(ingest.pipeline, "run", analyze), \
             patch.object(ingest, "setting", return_value="postgresql://example"), \
             patch.object(ingest.tiger, "sync", sync):
            results = [self.execute() for _ in range(4)]
        self.assertEqual(synced, [["CL-1"]] * 4)
        current = (self.published / "current").resolve()
        self.assertEqual(current.name, results[-1]["generation"])
        self.assertEqual(json.loads((current / "issues.public.json").read_text()), [ISSUE])
        status = json.loads((current / "ingest-status.json").read_text())
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["issue_count"], 1)
        stamped = [path for path in (self.published / "generations").iterdir() if ingest.GENERATION.fullmatch(path.name)]
        self.assertEqual(len(stamped), 3)
        self.assertTrue((self.published / "generations" / "initial").is_dir())
        self.assertEqual(json.loads((current / "issues.public.json").read_text())[0]["issue_id"], "CL-1")

    def test_without_a_database_the_files_still_publish(self):
        def analyze(*args, **kwargs):
            return write_public(kwargs["out_dir"], [ISSUE])

        with patch.object(ingest.workflow, "run", side_effect=lambda **kwargs: ok_workflow(kwargs["output"])), \
             patch.object(ingest.pipeline, "run", analyze), \
             patch.object(ingest, "setting", return_value=None), \
             patch.object(ingest.tiger, "sync", side_effect=AssertionError("database")):
            result = self.execute()
        self.assertEqual((self.published / "current").resolve().name, result["generation"])

    def test_republish_only_swaps_and_a_held_lock_refuses_to_start(self):
        seed(self.published, "20261018T010000Z", [ISSUE])
        with patch.object(ingest.workflow, "run", side_effect=AssertionError("workflow")):
            result = self.execute(republish="20261018T010000Z")
        self.assertEqual(result["republished"], True)
        self.assertEqual((self.published / "current").resolve().name, "20261018T010000Z")
        import fcntl
        handle = open(self.published / "ingest.lock", "a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with self.assertRaises(ingest.IngestError) as caught:
                self.execute(republish="initial")
            self.assertIn("already running", str(caught.exception))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        self.assertEqual((self.published / "current").resolve().name, "20261018T010000Z")


if __name__ == "__main__":
    unittest.main()
