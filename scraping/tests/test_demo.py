"""Behavior and spending checks; every request in these tests is mocked."""

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scraping.collectors import instagram_apify as apify
from scraping.media import MediaRecord, allowed_url, export_reviewed, fetch_image, process_media


FREE_USER = {"plan": {"tier": "FREE", "isEnabled": True, "monthlyBasePriceUsd": 0,
                      "monthlyUsageCreditsUsd": 5, "maxMonthlyUsageUsd": 5}, "isPaying": False}
USAGE = {"totalUsageCreditsUsdAfterVolumeDiscount": 0}


class DemoTests(unittest.TestCase):
    def test_budget_requires_free_non_paying_account_and_five_cent_cap(self):
        self.assertEqual(apify.validate_free_budget(FREE_USER, USAGE, "0.05")["out_of_pocket_usd"], 0)
        for cap in ("0.051", "0.25", "0", "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                apify.validate_free_budget(FREE_USER, USAGE, cap)
        for user in ({**FREE_USER, "isPaying": True}, {"plan": {}},
                     {**FREE_USER, "plan": {**FREE_USER["plan"], "tier": "STARTER"}}):
            with self.assertRaises(ValueError):
                apify.validate_free_budget(user, USAGE, "0.05")
        with self.assertRaises(ValueError):
            apify.validate_free_budget(FREE_USER, {"totalUsageCreditsUsdAfterVolumeDiscount": 4.99}, "0.05")

    def test_refuses_launch_before_any_post_when_budget_fails(self):
        def request(token, path, **kwargs):
            self.assertNotEqual(kwargs.get("method"), "POST")
            return {"data": {**FREE_USER, "isPaying": True}}
        with tempfile.TemporaryDirectory() as folder, patch.object(apify, "api_request", side_effect=request):
            with self.assertRaises(ValueError):
                apify.collect("not-a-real-token", ["https://www.instagram.com/example/"], folder)
            self.assertFalse((Path(folder) / "apify-run.json").exists())

    def test_actual_launch_always_sends_cost_limit_and_saves_run_before_polling(self):
        def request(token, path, **kwargs):
            if kwargs.get("method") == "POST":
                self.assertEqual(Decimal(kwargs["params"]["maxTotalChargeUsd"]), Decimal("0.05"))
                self.assertEqual(kwargs["params"]["restartOnError"], "false")
                self.assertLessEqual(kwargs["body"]["resultsLimit"], 10)
                self.assertEqual(kwargs["body"]["onlyPostsNewerThan"], "2026-10-10T10:00:00Z")
                return {"data": {"id": "TestRun123", "status": "READY"}}
            return {"data": {}}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(apify, "preflight", return_value={"plan": "FREE"}), \
                patch.object(apify, "api_request", side_effect=request), \
                patch.object(apify, "read_run", return_value=[]):
            apify.collect("not-a-real-token", ["https://www.instagram.com/example/"], folder,
                          since=datetime(2026, 10, 10, 10, tzinfo=timezone.utc))
            self.assertIn("TestRun123", (Path(folder) / "apify-run.json").read_text())
            with self.assertRaises(ValueError):
                apify.collect("not-a-real-token", ["https://www.instagram.com/example/"], folder)

    def test_carousel_keeps_original_positions_without_video_covers_or_user_fields(self):
        records, stats = apify.normalize([{
            "id": "100", "type": "Sidecar", "timestamp": "2026-10-17T10:00:00Z",
            "caption": "Street photo by @someone", "ownerUsername": "someone", "locationName": "Toronto",
            "childPosts": [{"id": "1", "type": "Image", "displayUrl": "https://a.cdninstagram.com/1.jpg"},
                           {"id": "2", "type": "Video", "displayUrl": "https://a.cdninstagram.com/cover.jpg"},
                           {"id": "3", "type": "Image", "displayUrl": "https://a.cdninstagram.com/3.jpg"}],
        }, {"id": "place", "name": "Toronto"}, {"id": "200", "type": "Sidecar", "childPosts": []}])
        self.assertEqual([row.media_index for row in records], [0, 2])
        self.assertEqual(stats["video_items_skipped"], 1)
        self.assertEqual(stats["non_media_items"], 1)
        self.assertEqual(stats["incomplete_carousels"], 1)
        self.assertNotIn("someone", str([asdict(row) for row in records]))
        self.assertFalse(records[0].location_evidence[0]["camera_location_verified"])

    def test_host_validation_rejects_private_targets_and_lookalikes(self):
        self.assertTrue(allowed_url("https://a.cdninstagram.com/image.jpg", apify.IMAGE_HOSTS))
        for url in ("http://a.cdninstagram.com/image.jpg", "https://localhost/image.jpg",
                    "https://cdninstagram.com.evil.test/image.jpg", "https://a.cdninstagram.com:444/image.jpg",
                    "https://user:password@a.cdninstagram.com/image.jpg"):
            self.assertFalse(allowed_url(url, apify.IMAGE_HOSTS))

    def test_shared_pipeline_processes_other_platform_and_removes_metadata_and_duplicates(self):
        image = Image.new("RGB", (320, 240), color=(70, 120, 80))
        original = BytesIO()
        exif = Image.Exif()
        exif[315] = "private author"
        image.save(original, format="JPEG", exif=exif)
        first = MediaRecord("other_platform", "fixture", "one", 0, "https://cdn.example/1.jpg", None)
        second = MediaRecord("other_platform", "fixture", "two", 0, "https://cdn.example/2.jpg", None)
        with tempfile.TemporaryDirectory() as folder, \
                patch("scraping.media.fetch_image", return_value=original.getvalue()) as fetch:
            rows = process_media([first, second, first], folder, hosts=("cdn.example",))
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["reasons"], ["duplicate_image"])
            with Image.open(Path(folder) / rows[0]["local_path"]) as derivative:
                self.assertFalse(derivative.getexif())
            self.assertEqual(export_reviewed(rows, []), [])
            labels = [{"key": first.key, "scene_label": "useful", "issue_label": "none"}]
            self.assertEqual(len(export_reviewed(rows, labels)), 1)
            self.assertEqual(export_reviewed(rows, [{**labels[0], "draft": True}]), [])
            self.assertFalse(export_reviewed(rows, labels)[0]["blur_required"])
            self.assertTrue(export_reviewed(rows, [{**labels[0], "people": "yes"}])[0]["blur_required"])
            with self.assertRaises(ValueError):
                export_reviewed(rows, [{**labels[0], "people": "maybe"}])

    def test_stale_capture_and_posting_dates_are_screened_before_download(self):
        records = [MediaRecord("example", "test", "capture", 0, "https://cdn.example/a.jpg",
                               "2026-10-17T10:00:00Z", captured_at="2018-01-01T00:00:00Z"),
                   MediaRecord("example", "test", "upload", 0, "https://cdn.example/b.jpg",
                               "2020-01-01T00:00:00Z")]
        with tempfile.TemporaryDirectory() as folder, patch("scraping.media.fetch_image") as fetch:
            rows = process_media(records, folder, hosts=("cdn.example",),
                                 since=datetime(2026, 10, 10, tzinfo=timezone.utc))
            fetch.assert_not_called()
            self.assertEqual([row["auto_status"] for row in rows], ["excluded", "excluded"])
            self.assertEqual(rows[0]["reasons"], ["capture_older_than_window"])

    def test_source_errors_are_not_counted_as_photo_posts(self):
        records, stats = apify.normalize([{"error": "no_items", "url": "private-source"}])
        self.assertEqual(records, [])
        self.assertEqual(stats["source_errors"], 1)

    def test_resume_fetches_existing_results_without_starting_an_actor(self):
        def request(token, path, **kwargs):
            self.assertNotEqual(kwargs.get("method"), "POST")
            if path.startswith("actor-runs/"):
                return {"data": {"status": "SUCCEEDED", "defaultDatasetId": "Dataset123"}}
            return [{"id": "100", "type": "Image"}]
        with tempfile.TemporaryDirectory() as folder, patch.object(apify, "api_request", side_effect=request):
            items = apify.read_run("not-a-real-token", "Run123", folder)
            self.assertEqual(items[0]["id"], "100")

    def test_redirect_cannot_escape_the_source_host_allowlist(self):
        with patch("scraping.media.requests.get") as get:
            response = get.return_value.__enter__.return_value
            response.status_code = 302
            response.headers = {"Location": "http://127.0.0.1/private"}
            with self.assertRaises(ValueError):
                fetch_image("https://a.cdninstagram.com/photo.jpg", apify.IMAGE_HOSTS)
            self.assertEqual(get.call_count, 1)

    def test_tokens_are_headers_only_and_not_echoed_in_server_errors(self):
        with patch("scraping.apify.requests.request") as request:
            response = request.return_value
            response.status_code = 400
            response.json.return_value = {"error": {"type": "invalid-input", "message": "not-a-real-token"}}
            with self.assertRaises(ValueError) as error:
                apify.api_request("not-a-real-token", "users/me")
            self.assertNotIn("not-a-real-token", str(error.exception))
            self.assertNotIn("not-a-real-token", request.call_args.args[1])
            self.assertFalse(request.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
