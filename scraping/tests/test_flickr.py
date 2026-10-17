"""Offline Flickr normalization and capture-date uncertainty handling."""

from datetime import datetime, timedelta, timezone
import unittest

from scraping.collectors import flickr


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=7)


def photo(photo_id="1", *, uploaded=None, url=None):
    uploaded = uploaded or NOW
    return {
        "id": photo_id,
        "dateupload": str(int(uploaded.timestamp())),
        "datetaken": "2026-10-16 12:00:00",
        "datetakengranularity": "0",
        "latitude": "43.648",
        "longitude": "-79.396",
        "accuracy": "16",
        "title": "Toronto sidewalk",
        "description": {"_content": "Near Spadina"},
        "license": "4",
        "url_l": url or f"https://live.staticflickr.com/65535/{photo_id}_abc_b.jpg",
    }


class FlickrTests(unittest.TestCase):
    def test_normalize_keeps_geo_claim_and_null_capture_time(self):
        packed, stats = flickr.normalize([photo()], since=SINCE, now=NOW)
        self.assertEqual(len(packed), 1)
        record, date_evidence, license_ = packed[0]
        self.assertIsNone(record.captured_at)
        self.assertEqual(record.location_evidence[0]["kind"], "flickr_geo")
        self.assertIn("uncertain", date_evidence["note"])
        self.assertEqual(license_, "4")
        self.assertEqual(stats["photos_inspected"], 1)

    def test_old_uploads_are_skipped(self):
        packed, stats = flickr.normalize(
            [photo(uploaded=SINCE - timedelta(days=1))], since=SINCE, now=NOW)
        self.assertEqual(packed, [])
        self.assertEqual(stats["older_posts_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
