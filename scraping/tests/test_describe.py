"""Checks for grounded, cached multi-image descriptions without live API calls."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scraping import describe, handoff
from scraping.media import read_jsonl, write_jsonl
from scraping.tests.test_post_groups import NOW, save_batch, source_row


def details_for(group):
    return {
        "issues": [{"primary_image_key": row["key"], "issue_supported": "yes",
                    "title": "Damaged public sidewalk", "description": "Broken concrete is visible in the foreground. The affected pavement lies beside the curb. The extent beyond the photo is unknown.",
                    "affected_infrastructure": "sidewalk", "observations": ["Broken concrete"],
                    "supporting_image_keys": [row["key"]], "uncertainties": ["Depth is unknown"],
                    "caption_claims": [], "confidence": "high"} for row in group["passed_images"]],
        "unrelated_image_keys": [],
    }


class DescriptionTests(unittest.TestCase):
    def test_group_descriptions_receive_all_images_and_resume_from_cache(self):
        with tempfile.TemporaryDirectory() as folder, patch("scraping.handoff.DATA", Path(folder)), \
                patch("scraping.describe.DATA", Path(folder)):
            root = Path(folder)
            batch, out = root / "reddit-live", root / "handoff"
            rows = [source_row(0), source_row(1)]
            save_batch(batch, rows, [rows[0]])
            handoff.build([batch], out, now=NOW)
            group = read_jsonl(out / "post-groups.jsonl")[0]
            result = details_for(group)
            with patch("scraping.describe.generate_content", return_value=result) as generate:
                report = describe.run(out, key="test-key", model="test-model", session=MagicMock(), min_interval=0)
                self.assertEqual((report["requests"], report["pending_groups"]), (1, 0))
                parts = generate.call_args.args[3]
                self.assertEqual(sum("inline_data" in part for part in parts), 2)
                self.assertIn("SUPPLEMENTAL", str([part for part in parts if "text" in part]))
                # Cached groups need no API key or network request.
                again = describe.run(out, session=MagicMock(), max_requests=0)
                self.assertEqual((again["cache_hits"], again["requests"], again["status"]), (1, 0, "ok"))
                self.assertEqual(generate.call_count, 1)
            stored = read_jsonl(out / "passed.jsonl")[0]
            self.assertEqual(stored["issue_details"]["description"], result["issues"][0]["description"])
            self.assertTrue(stored["screening"]["passed"])
            companion = read_jsonl(out / "post-groups.jsonl")[0]["supplemental_images"][0]
            self.assertFalse(companion["issue_verified"])
            # Embedded descriptions from shared groups also work without the local cache.
            (root / "issue-details-cache.jsonl").unlink()
            with patch("scraping.describe.generate_content") as generate:
                self.assertEqual(describe.run(out, max_requests=0)["status"], "ok")
                generate.assert_not_called()
            self.assertTrue((root / "issue-details-cache.jsonl").is_file())
            handoff.build([batch], out, now=NOW)
            self.assertIn("issue_details", read_jsonl(out / "passed.jsonl")[0])

    def test_unknown_citations_and_companion_only_claims_are_rejected(self):
        group = {"passed_images": [source_row(0)], "supplemental_images": [source_row(1)]}
        result = details_for(group)
        bad = deepcopy(result)
        bad["issues"][0]["supporting_image_keys"] = ["invented-image"]
        with self.assertRaises(ValueError):
            describe.validate_details(bad, group)
        bad["issues"][0]["supporting_image_keys"] = [source_row(1)["key"]]
        with self.assertRaises(ValueError):
            describe.validate_details(bad, group)
        bad = deepcopy(result)
        bad["unrelated_image_keys"] = [source_row(0)["key"]]
        with self.assertRaises(ValueError):
            describe.validate_details(bad, group)

    def test_request_cap_preserves_a_pending_group(self):
        with tempfile.TemporaryDirectory() as folder, patch("scraping.handoff.DATA", Path(folder)), \
                patch("scraping.describe.DATA", Path(folder)):
            root = Path(folder)
            batch, out = root / "reddit-live", root / "handoff"
            rows = [source_row(0)]
            save_batch(batch, rows, rows)
            handoff.build([batch], out, now=NOW)
            with patch("scraping.describe.generate_content") as generate:
                report = describe.run(out, max_requests=0)
                generate.assert_not_called()
            self.assertEqual((report["status"], report["pending_groups"]), ("partial", 1))
            self.assertTrue(read_jsonl(out / "passed.jsonl")[0]["screening"]["passed"])

    def test_one_invalid_answer_leaves_later_groups_describable(self):
        with tempfile.TemporaryDirectory() as folder, patch("scraping.handoff.DATA", Path(folder)), \
                patch("scraping.describe.DATA", Path(folder)):
            root = Path(folder)
            first, second, out = root / "reddit-one", root / "reddit-two", root / "handoff"
            save_batch(first, [source_row(0)], [source_row(0)])
            other = source_row(1, post_id="https://www.reddit.com/r/toronto/comments/other/title/")
            save_batch(second, [other], [other])
            handoff.build([first, second], out, now=NOW)
            groups = read_jsonl(out / "post-groups.jsonl")
            self.assertEqual(len(groups), 2)
            bad = details_for(groups[0])
            bad["issues"][0]["supporting_image_keys"] = ["invented-image"]
            with patch("scraping.describe.generate_content", side_effect=[bad, details_for(groups[1])]):
                report = describe.run(out, key="test", model="test", session=MagicMock(), min_interval=0)
            self.assertEqual((report["requests"], report["described_groups"], report["pending_groups"]), (2, 1, 1))
            self.assertEqual(len(report["errors"]), 1)

    def test_partial_pull_description_is_preserved_as_previous_when_regeneration_cannot_run(self):
        with tempfile.TemporaryDirectory() as folder, patch("scraping.handoff.DATA", Path(folder)), \
                patch("scraping.describe.DATA", Path(folder)):
            root = Path(folder)
            batch, out = root / "reddit-live", root / "handoff"
            rows = [source_row(0), source_row(1)]
            save_batch(batch, rows, [rows[0]])
            handoff.build([batch], out, now=NOW)
            group = read_jsonl(out / "post-groups.jsonl")[0]
            with patch("scraping.describe.generate_content", return_value=details_for(group)):
                describe.run(out, key="test", model="test", min_interval=0)
            group = read_jsonl(out / "post-groups.jsonl")[0]
            original = deepcopy(group["issue_details"])
            group.update(supplemental_images=[], context_incomplete=True,
                         unavailable_image_keys=[rows[1]["key"]])
            write_jsonl(out / "post-groups.jsonl", [group])
            report = describe.run(out, max_requests=0)
            self.assertEqual(report["pending_groups"], 1)
            after = read_jsonl(out / "post-groups.jsonl")[0]
            self.assertNotIn("issue_details", after)
            self.assertEqual(after["previous_issue_details"], original)
            self.assertIn("previous_issue_details", read_jsonl(out / "passed.jsonl")[0])


if __name__ == "__main__":
    unittest.main()
