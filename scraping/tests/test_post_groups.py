"""Checks that same-post context never inherits approval or bypasses known exclusions."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scraping import handoff
from scraping.media import read_jsonl, write_jsonl
from scraping.tests.test_handoff import passed_row

NOW = datetime(2026, 10, 17, 20, tzinfo=timezone.utc)


def source_row(index, *, post_id="https://www.reddit.com/r/toronto/comments/abcde/title/"):
    digest = f"{index + 100:064x}"
    return {**passed_row(digest, platform="reddit"), "key": f"reddit:{post_id}:{index}",
            "post_id": post_id, "media_index": index, "caption": "Toronto sidewalk damage",
            "media_url": f"https://i.redd.it/photo{index}.jpg"}


def save_batch(batch, rows, passed, screenings=()):
    (batch / "images").mkdir(parents=True)
    for row in rows:
        Image.new("RGB", (32, 24), (row["media_index"] * 20, 0, 0)).save(batch / row["local_path"])
    write_jsonl(batch / "media.jsonl", [{key: value for key, value in row.items() if key != "screening"} for row in rows])
    write_jsonl(batch / "passed.jsonl", passed)
    write_jsonl(batch / "screening.jsonl", screenings)


class PostGroupTests(unittest.TestCase):
    def test_companions_keep_own_status_and_known_exclusions(self):
        rows = [source_row(index) for index in range(9)]
        rows[7]["post_id"] = "https://www.reddit.com/r/toronto/comments/other/title/"
        assessment = {"scene_type": "public_outdoor", "sensitive": False,
                      "toronto": {"verdict": "unknown", "basis": "none"},
                      "issue": {"present": "no", "type": "none", "confidence": "high"},
                      "locatability": {"level": "low"}, "appears_old": False}
        overrides = {1: {}, 3: {"sensitive": True}, 4: {"scene_type": "private_or_indoor"},
                     5: {"toronto": {"verdict": "unlikely"}}, 6: {"appears_old": True},
                     8: {"scene_type": "other"}}
        screening = [{"sha256": rows[index]["sha256"], "assessment": {**assessment, **extra},
                      "model": "test", "prompt_version": "v1"} for index, extra in overrides.items()]
        with tempfile.TemporaryDirectory() as folder, patch("scraping.handoff.DATA", Path(folder)):
            root = Path(folder)
            batch, out = root / "reddit-live", root / "handoff"
            save_batch(batch, rows, [rows[0]], screening)
            report = handoff.build([batch], out, now=NOW)
            self.assertEqual((report["passed"], report["supplemental_images"], report["excluded_supplemental"]), (1, 2, 5))
            group = read_jsonl(out / "post-groups.jsonl")[0]
            companions = {row["media_index"]: row for row in group["supplemental_images"]}
            self.assertEqual(companions[1]["screening_status"], "not_passed")
            self.assertFalse(companions[1]["screening"]["passed"])
            self.assertEqual(companions[2]["screening_status"], "not_screened")
            self.assertIsNone(companions[2]["screening"])
            self.assertTrue(all(not row["issue_verified"] for row in companions.values()))
            self.assertEqual(len(list((out / "images").iterdir())), 3)
            payload = json.loads((out / "data.js").read_text().removeprefix("window.REVIEW_DATA = ").removesuffix(";\n"))
            self.assertEqual(payload["post_groups"], [group])
            self.assertEqual(payload["records"], read_jsonl(out / "passed.jsonl"))

    def test_changed_caption_invalidates_an_existing_description(self):
        group = {"platform": "reddit", "post_id": "post", "caption": "first caption",
                 "passed_images": [source_row(0)], "supplemental_images": []}
        fingerprint = handoff.group_fingerprint(group)
        group["caption"] = "corrected caption"
        self.assertNotEqual(handoff.group_fingerprint(group), fingerprint)


if __name__ == "__main__":
    unittest.main()
