"""Exercise the local adapter using fake posts; no login or network requests."""

from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scraping.collectors import instagram_local as local


def photo(post_id, day=17, *, private=False, sidecar=False):
    post = SimpleNamespace(
        mediaid=post_id, date_utc=datetime(2026, 10, day),
        owner_profile=SimpleNamespace(is_private=private),
        typename="GraphSidecar" if sidecar else "GraphImage", is_video=False,
        caption="Street scene by @someone", url="https://a.cdninstagram.com/photo.jpg",
    )
    if sidecar:
        post.get_sidecar_nodes = lambda: iter([
            SimpleNamespace(is_video=False, display_url="https://a.cdninstagram.com/1.jpg"),
            SimpleNamespace(is_video=True, display_url="https://a.cdninstagram.com/cover.jpg"),
            SimpleNamespace(is_video=False, display_url="https://a.cdninstagram.com/3.jpg"),
        ])
    return post


class LocalTests(unittest.TestCase):
    def test_user_toronto_url_and_id_have_same_identity(self):
        expected = "110941395597405"
        self.assertEqual(local.location_id(local.TORONTO_URL), expected)
        self.assertEqual(local.location_id(expected), expected)
        for value in ("https://instagram.com.evil.test/explore/locations/123/",
                      "https://www.instagram.com/example/", "not-a-location"):
            with self.assertRaises(ValueError):
                local.location_id(value)

    def test_private_and_unknown_privacy_posts_never_reach_output(self):
        for private in (True, None):
            rows, reason = local.normalize_post(photo(1, private=private), "123")
            self.assertEqual(rows, [])
            self.assertEqual(reason, "not_known_public")

    def test_carousel_excludes_video_covers_and_preserves_slide_positions(self):
        rows, _ = local.normalize_post(photo(1, sidecar=True), "123")
        self.assertEqual([row.media_index for row in rows], [0, 2])
        self.assertNotIn("someone", rows[0].caption)
        self.assertEqual(rows[0].posted_at, "2026-10-17T00:00:00+00:00")
        self.assertFalse(rows[0].location_evidence[0]["camera_location_verified"])

    def test_date_filter_does_not_stop_at_first_old_post_and_limit_is_scanned_posts(self):
        loader = Mock()
        loader.get_location_posts.return_value = iter([photo(1, 10), photo(2, 17), photo(3, 16)])
        rows, report = local.collect_records(loader, "123", limit=2,
            since=datetime(2026, 10, 15, tzinfo=timezone.utc))
        self.assertEqual([row.post_id for row in rows], ["2"])
        self.assertEqual(report["posts_scanned"], 2)
        self.assertFalse(report["fetched_sample_in_descending_order"])

    def test_results_sort_locally_and_deduplicate_without_inventing_chronological_source(self):
        loader = Mock()
        loader.get_location_posts.return_value = iter([photo(1, 16), photo(2, 17), photo(1, 16)])
        rows, report = local.collect_records(loader, "123")
        self.assertEqual([row.post_id for row in rows], ["2", "1"])
        self.assertFalse(report["fetched_sample_in_descending_order"])

    def test_endpoint_failure_preserves_earlier_rows_and_reports_partial_without_raw_response(self):
        def posts():
            yield photo(1)
            raise local.instaloader.exceptions.ConnectionException("201 Created at https://example/?secret=value")
        loader = Mock()
        loader.get_location_posts.return_value = posts()
        rows, report = local.collect_records(loader, "123")
        self.assertEqual(len(rows), 1)
        self.assertEqual(report["status"], "partial")
        self.assertNotIn("secret", json.dumps(report))
        self.assertIn("incompatible", report["errors"][0]["detail"])

    def test_session_roundtrip_is_private_json_and_missing_session_does_not_trigger_login(self):
        loader = Mock()
        loader.save_session.return_value = {"sessionid": "fixture-session", "csrftoken": "fixture-csrf"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            with self.assertRaises(ValueError):
                local.load_session(loader, path)
            loader.load_session.assert_not_called()
            local.save_session(loader, "example", path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn("password", path.read_text())
            local.load_session(loader, path)
            loader.load_session.assert_called_once_with("example", loader.save_session.return_value)

    def test_metadata_mode_uses_shared_records_and_never_downloads_or_exports_session_data(self):
        loader = Mock()
        loader.get_location_posts.return_value = iter([photo(1, sidecar=True)])
        context = Mock()
        context.__enter__ = Mock(return_value=loader)
        context.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(local, "make_loader", return_value=context), \
                patch.object(local, "load_session"), \
                patch.object(local, "process_media") as download:
            report = local.collect(metadata_only=True, output=folder)
            download.assert_not_called()
            loader.get_location_posts.assert_called_once_with("110941395597405")
            self.assertEqual(report["image_candidates"], 2)
            payload = (Path(folder) / "candidates.jsonl").read_text()
            rows = [json.loads(line) for line in payload.splitlines()]
            self.assertEqual([row["media_index"] for row in rows], [0, 2])
            self.assertNotIn("cookies", payload)
            self.assertNotIn("owner_profile", payload)
            self.assertEqual(json.loads((Path(folder) / "report.json").read_text())["status"], "ok")


if __name__ == "__main__":
    unittest.main()
