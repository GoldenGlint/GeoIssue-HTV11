"""Offline checks for sharing grouped post context."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import requests

from scraping import share
from scraping.media import image_derivative


def image_bytes(color):
    buffer = BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="PNG")
    return buffer.getvalue()


def record(key, data, *, index=0, status=None):
    _, _, digest, _ = image_derivative(data)
    row = {
        "key": key,
        "platform": "reddit",
        "collector": "test",
        "post_id": "post",
        "media_index": index,
        "media_url": f"https://i.redd.it/{index}.png",
        "posted_at": "2026-10-16T12:00:00Z",
        "caption": "Toronto road work",
        "sha256": digest,
        "local_path": f"images/{digest}.jpg",
    }
    if status:
        row["screening_status"] = status
    return row


class ShareGroupTests(unittest.TestCase):
    def test_export_copies_group_text_without_images(self):
        primary = record("reddit:post:0", image_bytes("blue"))
        companion = record("reddit:post:1", image_bytes("green"), index=1,
                          status="not_screened")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff, shared = root / "handoff", root / "shared"
            (handoff / "images").mkdir(parents=True)
            (handoff / primary["local_path"]).write_bytes(b"local primary photo")
            (handoff / companion["local_path"]).write_bytes(b"local companion photo")
            primary["post_group_id"] = "reddit:post"
            group = {
                "group_id": "reddit:post",
                "platform": "reddit",
                "collector": "test",
                "post_id": "post",
                "post_url": "https://www.reddit.com/r/test/comments/post/",
                "posted_at": primary["posted_at"],
                "caption": primary["caption"],
                "passed_images": [primary],
                "supplemental_images": [{
                    **companion,
                    "saved_width": 40,
                    "saved_height": 30,
                    "screening_status": "not_screened",
                    "relation": "same_post_context",
                    "issue_verified": False,
                    "blur_before_public_display": True,
                }],
                "excluded_supplemental": [],
                "detail_status": "pending",
            }
            (handoff / "passed.jsonl").write_text(json.dumps(primary) + "\n")
            (handoff / "post-groups.jsonl").write_text(json.dumps(group) + "\n")

            with patch("scraping.share.DATA", root):
                report = share.export(handoff, shared)

            self.assertEqual(report["post_groups"], 1)
            self.assertEqual(json.loads((shared / "post-groups.jsonl").read_text()), group)
            self.assertEqual(json.loads((shared / "passed.jsonl").read_text()), primary)
            self.assertFalse((shared / "images").exists())

    def test_pull_keeps_good_primary_when_companions_are_changed_or_missing(self):
        primary_data, companion_data, changed_data, missing_data = (
            image_bytes("blue"), image_bytes("green"), image_bytes("purple"), image_bytes("red"))
        primary = record("reddit:post:0", primary_data)
        primary["post_group_id"] = "reddit:post"
        primary.update(auto_status="ready", fetched_at="2026-10-16T12:00:00Z", location_evidence=[],
                       screening={"passed": True, "issue_type": "blocked_access"},
                       issue_details={"issue": {
                           "primary_image_key": primary["key"],
                           "supporting_image_keys": ["reddit:post:2", "reddit:post:3"],
                       }, "model": "test"})
        kept = record("reddit:post:1", companion_data, index=1, status="not_screened")
        changed = record("reddit:post:2", changed_data, index=2, status="not_passed")
        missing = record("reddit:post:3", missing_data, index=3, status="not_screened")
        for row in (kept, changed, missing):
            row.update(relation="same_post_context", issue_verified=False,
                       blur_before_public_display=True)
        group = {
            "group_id": "reddit:post",
            "platform": "reddit",
            "collector": "test",
            "post_id": "post",
            "caption": primary["caption"],
            "passed_images": [primary],
            "supplemental_images": [kept, changed, missing],
            "excluded_supplemental": [],
            "detail_status": "complete",
            "issue_details": {
                "issues": [{
                    "primary_image_key": primary["key"],
                    "supporting_image_keys": [changed["key"], missing["key"]],
                    "description": "The work area blocks the sidewalk.",
                }],
            },
        }

        def fetch(url, _hosts):
            if url == primary["media_url"]:
                return primary_data
            if url == kept["media_url"]:
                return companion_data
            if url == changed["media_url"]:
                return image_bytes("yellow")
            if url == missing["media_url"]:
                raise requests.RequestException("offline")
            self.fail(f"Unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = root / "shared"
            shared.mkdir()
            (shared / "passed.jsonl").write_text(json.dumps(primary) + "\n")
            (shared / "post-groups.jsonl").write_text(json.dumps(group) + "\n")
            with patch("scraping.share.DATA", root), patch("scraping.share.fetch_image", side_effect=fetch):
                report = share.pull(shared, root / "restored")

            restored = root / "restored"
            stored_passed = json.loads((restored / "passed.jsonl").read_text())
            stored_group = json.loads((restored / "post-groups.jsonl").read_text())
            self.assertEqual(report["passed"], 1)
            self.assertEqual(report["supplemental_not_restored"], {"changed": 1, "unavailable": 1})
            self.assertEqual(stored_passed["key"], primary["key"])
            self.assertTrue((restored / primary["local_path"]).is_file())
            self.assertEqual(stored_group["passed_images"], [stored_passed])
            self.assertEqual(stored_group["supplemental_images"], [kept])
            self.assertEqual(set(stored_group["unavailable_image_keys"]),
                             {changed["key"], missing["key"]})
            issue = stored_group["issue_details"]["issues"][0]
            self.assertEqual(set(issue["unavailable_image_keys"]), {changed["key"], missing["key"]})
            self.assertEqual(set(stored_passed["issue_details"]["issue"]["unavailable_image_keys"]),
                             {changed["key"], missing["key"]})
            self.assertTrue(stored_group["context_incomplete"])
            self.assertEqual(stored_group["supplemental_images"][0]["screening_status"], "not_screened")
            self.assertNotIn("passed", stored_group["supplemental_images"][0])
            gallery = (restored / "data.js").read_text().removeprefix("window.REVIEW_DATA = ").removesuffix(";\n")
            self.assertEqual(json.loads(gallery)["post_groups"], [stored_group])


if __name__ == "__main__":
    unittest.main()
