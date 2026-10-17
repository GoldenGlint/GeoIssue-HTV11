"""Offline checks for Gemini screening decisions, cache reuse, and exports."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from scraping import screen
from scraping.media import source_post_url


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def assessment(**overrides):
    value = {
        "scene_type": "public_outdoor",
        "sensitive": False,
        "toronto": {"verdict": "likely", "basis": "both", "evidence": ["street sign"]},
        "issue": {"present": "yes", "type": "drain", "evidence": "misaligned grate",
                  "confidence": "high"},
        "locatability": {"level": "high", "clues": ["Queen St"], "location_guess": "Queen/Spadina"},
        "appears_old": False,
        "appears_old_reason": "",
    }
    value.update(overrides)
    return value


def media_row(key="bluesky:post:0", digest="a" * 64, posted_at="2026-10-16T12:00:00Z"):
    return {
        "key": key, "platform": "bluesky", "post_id": "post", "media_index": 0,
        "auto_status": "ready", "local_path": f"images/{digest}.jpg", "sha256": digest,
        "posted_at": posted_at, "caption": "Toronto sidewalk", "alt_text": "",
        "freshness": {"status": "capture_time_unknown"},
    }


class DecisionTests(unittest.TestCase):
    def test_source_post_links_preserve_native_identity(self):
        self.assertEqual(source_post_url({"platform": "bluesky",
            "post_id": "at://did:plc:abc/app.bsky.feed.post/xyz"}),
            "https://bsky.app/profile/did:plc:abc/post/xyz")
        for platform, url in (("reddit", "https://www.reddit.com/r/toronto/comments/abc/title/"),
                              ("mastodon", "https://mastodon.social/users/test/statuses/123")):
            self.assertEqual(source_post_url({"platform": platform, "post_id": url}), url)
        self.assertIsNone(source_post_url({"platform": "reddit", "post_id": "javascript:alert(1)"}))
        self.assertIsNone(source_post_url({"platform": "bluesky", "post_id": "post"}))

    def test_keep_live_issue_candidate(self):
        decision = screen.decide(assessment(), media_row(), now=NOW)
        self.assertEqual(decision["decision"], "keep")
        self.assertTrue(decision["issue_candidate"])
        self.assertTrue(decision["passed"])
        self.assertEqual(decision["pass_blockers"], [])
        self.assertEqual(decision["pool"], "live")

    def test_reject_sensitive_and_non_outdoor(self):
        self.assertEqual(screen.decide(assessment(sensitive=True), media_row(), now=NOW)["decision"],
                         "reject")
        self.assertIn("scene_screenshot",
                      screen.decide(assessment(scene_type="screenshot"), media_row(), now=NOW)["reasons"])

    def test_caption_only_likely_is_not_a_toronto_scene(self):
        decision = screen.decide(
            assessment(toronto={"verdict": "likely", "basis": "caption",
                                "evidence": ["caption says Toronto style"]}),
            media_row(), now=NOW)
        self.assertEqual(decision["decision"], "reject")
        self.assertIn("toronto_likely", decision["reasons"])

    def test_reject_non_toronto_and_keep_training_when_old(self):
        self.assertEqual(
            screen.decide(assessment(toronto={"verdict": "unlikely", "basis": "caption",
                                              "evidence": ["Seattle"]}),
                          media_row(), now=NOW)["decision"],
            "reject")
        decision = screen.decide(assessment(appears_old=True), media_row(), now=NOW)
        self.assertEqual(decision["decision"], "keep")
        self.assertEqual(decision["pool"], "training")
        self.assertFalse(decision["passed"])
        self.assertIn("not_recent", decision["pass_blockers"])

    def test_pass_requires_issue_locatability_and_recency(self):
        no_issue = screen.decide(assessment(issue={"present": "no", "type": "none",
                                                   "evidence": "", "confidence": "high"}),
                                 media_row(), now=NOW)
        self.assertIn("no_issue", no_issue["pass_blockers"])
        unnamed_issue = screen.decide(assessment(issue={"present": "yes", "type": "none",
                                                        "evidence": "", "confidence": "high"}),
                                     media_row(), now=NOW)
        self.assertIn("no_issue", unnamed_issue["pass_blockers"])
        low = screen.decide(assessment(locatability={"level": "low", "clues": [], "location_guess": ""}),
                            media_row(), now=NOW)
        self.assertIn("not_locatable", low["pass_blockers"])
        old = screen.decide(assessment(), media_row(posted_at="2020-01-01T00:00:00Z"), now=NOW)
        self.assertFalse(old["passed"])
        self.assertIn("not_recent", old["pass_blockers"])
        words = screen.decide(assessment(), {**media_row(), "caption": "One year ago today in Toronto"}, now=NOW)
        self.assertIn("not_recent", words["pass_blockers"])


class BatchTests(unittest.TestCase):
    def test_cache_hit_avoids_network_and_writes_auto_accepted(self):
        digest = "b" * 64
        row = media_row(digest=digest)
        cached = {
            "key": row["key"], "sha256": digest, "platform": "bluesky", "post_id": "post",
            "media_index": 0, "model": "gemini-test", "prompt_version": screen.PROMPT_VERSION,
            "assessment": assessment(), **screen.decide(assessment(), row, now=NOW),
        }
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "images").mkdir()
            Image.new("RGB", (32, 32), "red").save(batch / row["local_path"], format="JPEG")
            (batch / "media.jsonl").write_text(json.dumps(row) + "\n")
            (batch / "screening.jsonl").write_text(json.dumps(cached) + "\n")
            session = MagicMock()
            with patch("scraping.screen.load_api_key", return_value="test-key"), \
                 patch("scraping.screen.resolve_model", return_value="gemini-test"), \
                 patch("scraping.screen.generate") as generate:
                report = screen.screen_batch(batch, session=session, now=NOW, max_requests=10,
                                             min_interval=0)
            generate.assert_not_called()
            self.assertEqual(report["cache_hits"], 1)
            self.assertEqual(report["requests"], 0)
            accepted = [json.loads(line) for line in (batch / "passed.jsonl").read_text().splitlines()]
            self.assertEqual(len(accepted), 1)
            self.assertEqual(accepted[0]["screening"]["issue_type"], "drain")
            self.assertTrue(accepted[0]["screening"]["passed"])
            self.assertEqual(accepted[0]["screening"]["scene_type"], "public_outdoor")
            self.assertEqual(accepted[0]["screening"]["toronto_verdict"], "likely")
            self.assertEqual(accepted[0]["screening"]["issue_confidence"], "high")
            self.assertFalse(accepted[0]["screening"]["location_verified"])
            self.assertTrue(accepted[0]["screening"]["blur_before_public_display"])
            self.assertEqual((accepted[0]["saved_width"], accepted[0]["saved_height"]), (32, 32))

    def test_prefilter_skips_gemini_for_captions_without_problem_words(self):
        rows = [media_row(key="bluesky:p0:0", digest="c" * 64),
                {**media_row(key="bluesky:p1:0", digest="d" * 64), "caption": "Lovely sunset"}]
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "images").mkdir()
            for row in rows:
                Image.new("RGB", (32, 32), "green").save(batch / row["local_path"], format="JPEG")
            (batch / "media.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            with patch("scraping.screen.load_api_key", return_value="test-key"), \
                 patch("scraping.screen.resolve_model", return_value="gemini-test"), \
                 patch("scraping.screen.generate", return_value=assessment()) as generate:
                report = screen.screen_batch(batch, session=MagicMock(), now=NOW, min_interval=0)
                self.assertEqual(generate.call_count, 1)
                self.assertEqual(report["prefiltered"], 1)
                cached = (batch / "screening.jsonl").read_text().splitlines()
                self.assertEqual(len(cached), 1)
                screen.screen_batch(batch, session=MagicMock(), now=NOW, min_interval=0,
                                    prefilter=False)
                self.assertEqual(generate.call_count, 2)

    def test_cached_batch_rescreens_without_an_api_key(self):
        row = media_row(digest="e" * 64)
        cached = {"key": row["key"], "sha256": row["sha256"], "model": "gemini-test",
                  "prompt_version": screen.PROMPT_VERSION, "assessment": assessment()}
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "images").mkdir()
            Image.new("RGB", (32, 32), "red").save(batch / row["local_path"], format="JPEG")
            (batch / "media.jsonl").write_text(json.dumps(row) + "\n")
            (batch / "screening.jsonl").write_text(json.dumps(cached) + "\n")
            with patch("scraping.screen.load_api_key", side_effect=ValueError("no key")):
                report = screen.screen_batch(batch, session=MagicMock(), now=NOW, min_interval=0)
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["passed"], 1)

    def test_max_requests_preserves_partial_results(self):
        rows = [media_row(key=f"bluesky:p{i}:0", digest=f"{i:064x}") for i in range(2)]
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "images").mkdir()
            for row in rows:
                Image.new("RGB", (32, 32), "blue").save(batch / row["local_path"], format="JPEG")
            (batch / "media.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            session = MagicMock()
            with patch("scraping.screen.load_api_key", return_value="test-key"), \
                 patch("scraping.screen.resolve_model", return_value="gemini-test"), \
                 patch("scraping.screen.generate", return_value=assessment()) as generate:
                report = screen.screen_batch(batch, session=session, now=NOW, max_requests=1,
                                             min_interval=0)
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["screened"], 1)
            self.assertEqual(report["unscreened"], 1)
            self.assertTrue((batch / "screening.jsonl").is_file())

    def test_api_errors_do_not_save_the_key(self):
        row = media_row()
        key = "private-test-key"
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "media.jsonl").write_text(json.dumps(row) + "\n")
            with patch("scraping.screen.resolve_model", side_effect=ValueError(f"Failed at ?key={key}")):
                report = screen.screen_batch(batch, key=key, session=MagicMock(), shared_cache=None)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["unscreened"], 1)
            self.assertNotIn(key, (batch / "screening-report.json").read_text())
            self.assertIn("[REDACTED]", report["errors"][0])

    def test_cached_images_after_the_request_cap_still_count(self):
        rows = [media_row(key=f"bluesky:q{i}:0", digest=f"{i + 10:064x}") for i in range(2)]
        cached = {"key": rows[1]["key"], "sha256": rows[1]["sha256"], "model": "gemini-test",
                  "prompt_version": screen.PROMPT_VERSION, "assessment": assessment()}
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "images").mkdir()
            for row in rows:
                Image.new("RGB", (32, 32), "blue").save(batch / row["local_path"], format="JPEG")
            (batch / "media.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            (batch / "screening.jsonl").write_text(json.dumps(cached) + "\n")
            with patch("scraping.screen.generate") as generate:
                report = screen.screen_batch(batch, session=MagicMock(), now=NOW, max_requests=0,
                                             min_interval=0)
            generate.assert_not_called()
            self.assertEqual(report["cache_hits"], 1)
            self.assertEqual(report["passed"], 1)
            self.assertEqual(report["unscreened"], 1)


if __name__ == "__main__":
    unittest.main()
