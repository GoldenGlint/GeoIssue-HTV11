"""Offline checks for the passed-image handoff."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scraping.handoff import build


def passed_row(digest, *, platform="mastodon", issue="blocked_access"):
    return {
        "key": f"{platform}:post:0", "platform": platform, "post_id": "post", "media_index": 0,
        "auto_status": "ready", "sha256": digest, "local_path": f"images/{digest}.jpg",
        "posted_at": "2026-10-16T12:00:00Z", "caption": "Toronto",
        "screening": {"passed": True, "issue_type": issue, "issue_evidence": "blocked lane",
                      "location_guess": "Bloor", "clues": ["Bloor"], "locatability": "high",
                      "toronto_evidence": ["sign"], "model": "test", "prompt_version": "v"},
    }


class HandoffTests(unittest.TestCase):
    def test_copies_only_passed_images_and_drops_duplicates(self):
        digest = "a" * 64
        other = "b" * 64
        with tempfile.TemporaryDirectory() as folder, patch("scraping.handoff.DATA", Path(folder)):
            root = Path(folder)
            first, second = root / "mastodon-live", root / "bluesky-live"
            for batch, rows in (
                (first, [passed_row(digest), {**passed_row(other), "key": "mastodon:other:0",
                                              "screening": {**passed_row(other)["screening"], "passed": False}}]),
                (second, [passed_row(digest, platform="bluesky")]),
            ):
                (batch / "images").mkdir(parents=True)
                for row in rows:
                    if row["screening"]["passed"]:
                        Image.new("RGB", (8, 8), "red").save(batch / row["local_path"], format="JPEG")
                (batch / "passed.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            out = root / "handoff"
            report = build([first, second], out)
            self.assertEqual(report["passed"], 1)
            stored = [json.loads(line) for line in (out / "passed.jsonl").read_text().splitlines()]
            self.assertEqual(len(stored), 1)
            self.assertTrue((out / stored[0]["local_path"]).is_file())
            self.assertTrue((out / "index.html").is_file())
            payload = (out / "data.js").read_text().removeprefix("window.REVIEW_DATA = ").removesuffix(";\n")
            self.assertEqual(json.loads(payload)["records"], stored)
            build([first], out)
            self.assertEqual(len(list((out / "images").iterdir())), 1)


class ShareTests(unittest.TestCase):
    def test_export_is_text_only_and_pull_verifies_pixels(self):
        from io import BytesIO
        from scraping import share
        from scraping.media import image_derivative

        buffer = BytesIO()
        Image.new("RGB", (40, 40), "blue").save(buffer, format="PNG")
        _, _, digest, _ = image_derivative(buffer.getvalue())
        with tempfile.TemporaryDirectory() as folder, patch("scraping.share.DATA", Path(folder)):
            root = Path(folder)
            handoff, shared = root / "handoff", root / "shared"
            (handoff / "images").mkdir(parents=True)
            row = {**passed_row(digest, platform="reddit"), "media_url": "https://i.redd.it/abcde.png"}
            changed = {**passed_row("c" * 64, platform="reddit"), "key": "reddit:other:0",
                       "media_url": "https://i.redd.it/other.png"}
            (handoff / "passed.jsonl").write_text(json.dumps(row) + "\n" + json.dumps(changed) + "\n")
            (root / "batch").mkdir()
            (root / "batch" / "screening.jsonl").write_text(json.dumps(
                {"sha256": digest, "model": "m", "prompt_version": "v", "assessment": {"x": 1},
                 "key": "reddit:post:0"}) + "\n")
            report = share.export(handoff, shared)
            self.assertFalse(report["images_committed"])
            self.assertFalse((shared / "images").exists())
            cache = json.loads((shared / "screening-cache.jsonl").read_text())
            self.assertNotIn("key", cache)
            with patch("scraping.share.fetch_image", return_value=buffer.getvalue()):
                pulled = share.pull(shared, root / "restored")
            self.assertEqual(pulled["passed"], 1)
            self.assertEqual(pulled["not_restored"], {"changed": 1})
            self.assertTrue((root / "restored" / row["local_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
