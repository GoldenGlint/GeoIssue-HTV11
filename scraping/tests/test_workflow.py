"""Offline boundaries for expansion, provenance, budgets and manual-only automation."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scraping import screen, workflow
from scraping.collectors import reddit, social_apify
from scraping.media import read_jsonl, source_post_url, write_jsonl
from scraping.tests.test_demo import FREE_USER, USAGE
from scraping.tests.test_screen import assessment, media_row, NOW


class ExpansionTests(unittest.TestCase):
    def test_interrupted_manifest_replacement_preserves_the_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "media.jsonl"
            write_jsonl(path, [{"previous": True}])
            with patch.object(Path, "replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    write_jsonl(path, [{"new": True}])
            self.assertEqual(json.loads(path.read_text()), {"previous": True})
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_unicode_line_separators_in_captions_stay_inside_one_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "media.jsonl"
            rows = [{"caption": "Bloor\u2028sidewalk\x85closed"}, {"caption": "second"}]
            write_jsonl(path, rows)
            self.assertEqual(read_jsonl(path), rows)

    def test_global_reddit_filter_and_original_gallery_positions(self):
        from scraping.tests.test_reddit import post, SINCE
        gallery = post("gallery", title="Toronto sidewalk", is_gallery=True,
            gallery_data={"items": [{"media_id": "video01"}, {"media_id": "photo02"}]},
            media_metadata={"video01": {"e": "AnimatedImage", "id": "video01", "m": "image/gif", "status": "valid"},
                            "photo02": {"e": "Image", "id": "photo02", "m": "image/jpg", "status": "valid"}})
        rows, stats = reddit.normalize([post(title="London sidewalk"), gallery],
            since=SINCE, now=NOW, required_terms=["Toronto"])
        self.assertEqual([row.media_index for row in rows], [1])
        self.assertEqual(stats["outside_discovery_area"], 1)

    def test_new_source_links_require_their_own_https_host(self):
        for platform, link in (("instagram", "https://www.instagram.com/p/abc/"),
                               ("facebook", "https://www.facebook.com/page/posts/123"),
                               ("threads", "https://www.threads.com/@example/post/abc")):
            self.assertEqual(source_post_url({"platform": platform, "post_url": link}), link)
            self.assertIsNone(source_post_url({"platform": platform, "post_url": "https://evil.test/photo"}))

    def test_reddit_keyword_search_remains_scoped_to_a_community(self):
        from scraping.tests.test_reddit import Session, Response, post, SINCE
        session = Session([Response(200, {"data": [post()]})])
        config = {"api": "https://arctic-shift.photon-reddit.com/api", "subreddits": ["bicycling"],
                  "query": "Toronto", "max_posts_per_subreddit": 100}
        posts, _ = reddit.collect(session, config, since=SINCE, until=NOW)
        self.assertEqual(session.calls[0]["query"], "Toronto")
        self.assertEqual(session.calls[0]["subreddit"], "bicycling")
        self.assertIn("query:Toronto", posts[0]["_found_by"])

    def test_bounded_exploration_keeps_cached_images_and_counts_new_attempts(self):
        rows = [{**media_row(key=f"reddit:post{i}:0", digest=str(i)*64), "caption": "A street scene"}
                for i in range(1, 4)]
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder)
            (batch / "images").mkdir()
            for row in rows:
                Image.new("RGB", (32, 32), "red").save(batch / row["local_path"])
            write_jsonl(batch / "media.jsonl", rows)
            with patch.object(screen, "generate", return_value=assessment()) as generate:
                report = screen.screen_batch(batch, max_requests=2, exploration_limit=1,
                    model="test", key="test", now=NOW, min_interval=0, shared_cache=None)
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(report["exploration_requests"], 1)
            self.assertEqual(report["prefiltered"], 2)
            with patch.object(screen, "generate") as generate:
                cached = screen.screen_batch(batch, max_requests=0, model="test", key="test",
                    now=NOW, min_interval=0, shared_cache=None)
            generate.assert_not_called()
            self.assertEqual(cached["passed"], 1)

    def test_combination_merges_provenance_and_deduplicates_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            batches = [root / "one", root / "two"]
            for index, batch in enumerate(batches):
                (batch / "images").mkdir(parents=True)
                row = {**media_row(digest="a"*64), "found_by": [f"query:{index}"]}
                Image.new("RGB", (32, 32), "red").save(batch / row["local_path"])
                write_jsonl(batch / "media.jsonl", [row])
            rows = workflow.combine(batches, root / "combined")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["found_by"], ["query:0", "query:1"])

    def test_summary_does_not_count_context_or_disagreements_as_supported(self):
        rows = [{**media_row(digest="a"*64), "issue_details": {"issue_supported": "yes"}},
                {**media_row(key="reddit:two:0", digest="b"*64), "issue_details": {"issue_supported": "no"}}]
        result = workflow.summarize(rows, ["a"*64])
        self.assertEqual(result["passed_images"], 2)
        self.assertEqual(result["supported_images"], 1)
        self.assertEqual(result["new_supported_images"], 0)
        self.assertEqual(result["needs_review_images"], 1)

    def test_actions_has_only_a_manual_trigger_and_no_image_artifacts(self):
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/collect-images.yml").read_text()
        uncommented = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        self.assertIn("workflow_dispatch:", uncommented)
        self.assertNotIn("schedule:", uncommented)
        self.assertNotIn("pull_request", uncommented)
        self.assertNotIn("contents: write", uncommented)
        self.assertNotIn("handoff/images", uncommented)


class PilotTests(unittest.TestCase):
    def test_lost_launch_is_never_retried_and_cap_is_sent(self):
        def request(token, path, **kwargs):
            self.assertEqual(kwargs["params"]["maxTotalChargeUsd"], "0.05")
            self.assertEqual(kwargs["params"]["restartOnError"], "false")
            raise ValueError("Lost response")
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(social_apify, "preflight", return_value={}), \
                patch.object(social_apify.apify, "api_request", side_effect=request) as api:
            with self.assertRaises(ValueError):
                social_apify.fetch_items("test", "actor", {}, folder)
            with self.assertRaises(ValueError):
                social_apify.fetch_items("test", "actor", {}, folder)
            self.assertEqual(api.call_count, 1)

    def test_preflight_blocks_paid_accounts_and_actor_minimum(self):
        for user, minimum in (({**FREE_USER, "isPaying": True}, 0), (FREE_USER, 0.1)):
            replies = [{"data": user}, {"data": USAGE}, {"data": {"pricingInfos": [{
                "startedAt": "2026-01-01T00:00:00Z", "pricingModel": "PAY_PER_EVENT",
                "minimalMaxTotalChargeUsd": minimum, "pricingPerEvent": {"actorChargeEvents": {"post": {
                    "eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.003}}}}}}]}}]
            with patch.object(social_apify.apify, "api_request", side_effect=replies):
                with self.assertRaises(ValueError):
                    social_apify.preflight("test", "actor")

    def test_response_shapes_keep_only_own_photos_and_original_indices(self):
        since = NOW - timedelta(days=7)
        facebook = {"postId": "123", "url": "https://www.facebook.com/page/posts/123", "time": NOW.isoformat(),
                    "text": "Toronto sidewalk by @someone", "media": [
                        {"__typename": "Video", "thumbnail": "https://a.fbcdn.net/cover.jpg"},
                        {"__typename": "Photo", "photo_image": {"uri": "https://a.fbcdn.net/photo.jpg"}},
                        {"__typename": "Photo", "photo_image": {"uri": "https://evil.test/photo.jpg"}}]}
        records, stats = social_apify.normalize([facebook, {**facebook, "sharedPost": {"id": "other"}}],
                                               "facebook", since=since, now=NOW)
        self.assertEqual([record.media_index for record in records], [1])
        self.assertNotIn("someone", records[0].caption)
        self.assertEqual(stats["invalid_image_hosts"], 1)
        threads = {"type": "post", "postId": "456", "date": NOW.isoformat(),
                   "url": "https://www.threads.com/@example/post/456", "media": [
                       {"type": "video", "url": "https://a.fbcdn.net/cover.jpg"},
                       {"type": "image", "url": "https://a.fbcdn.net/photo.jpg"}]}
        records, _ = social_apify.normalize([threads], "threads", since=since, now=NOW)
        self.assertEqual([record.media_index for record in records], [1])


if __name__ == "__main__":
    unittest.main()
