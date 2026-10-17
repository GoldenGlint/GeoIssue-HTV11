"""Offline checks for a combined model-input review set and conservative recency."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scraping.demo import merge_batches
from scraping.media import MediaRecord, assess_freshness, read_jsonl, write_jsonl


NOW = datetime(2026, 10, 17, 16, tzinfo=timezone.utc)


class CollectionReviewTests(unittest.TestCase):
    def test_recent_upload_is_not_a_fresh_condition_and_old_evidence_stays_blocked(self):
        row = {"posted_at": NOW.isoformat(), "captured_at": None, "caption": "Toronto sidewalk"}
        self.assertEqual(assess_freshness(row, now=NOW)["status"], "capture_time_unknown")
        for change, status in [
            ({"captured_at": (NOW-timedelta(days=5*365)).isoformat()}, "outside_window"),
            ({"caption": "Throwback to the broken sidewalk"}, "historical_caption_review"),
            ({"caption": "From the album, 125 years ago"}, "historical_caption_review"),
            ({"caption": "One year ago today, the city cleared the site"}, "historical_caption_review"),
            ({"caption": "A year ago this sidewalk flooded"}, "historical_caption_review"),
            ({"caption": "Oct '25\nToronto"}, "historical_caption_review"),
            ({"caption": "Public square, August 2026."}, "historical_caption_review"),
            ({"caption": "Public square, August, 2026."}, "historical_caption_review"),
            ({"caption": "Toronto, October 17, 2026."}, "capture_time_unknown"),
            ({"caption": "Shot in Toronto in 2021."}, "historical_caption_review"),
            ({"captured_at": NOW.isoformat()}, "capture_time_recorded"),
            ({"posted_at": (NOW+timedelta(days=1)).isoformat()}, "future_timestamp_review"),
        ]:
            result = assess_freshness({**row, **change}, now=NOW)
            self.assertEqual(result["status"], status)
            self.assertFalse(result["alert_eligible"])

    def test_merge_preserves_platforms_reuses_saved_images_and_excludes_cross_platform_duplicates(self):
        with tempfile.TemporaryDirectory() as folder, patch("scraping.demo.DATA", Path(folder)), \
                patch("requests.request", side_effect=AssertionError("Merge must remain offline")):
            root = Path(folder)
            batches = []
            for platform in ("instagram", "bluesky"):
                batch = root / platform
                (batch / "images").mkdir(parents=True)
                digest = "a" * 64
                local = f"images/{digest}.jpg"
                (batch / local).write_bytes(b"saved-image-fixture")
                row = asdict(MediaRecord(platform, "fixture", "one", 0, "https://cdn.example/image.jpg",
                                         datetime.now(timezone.utc).isoformat()))
                row.update(key=f"{platform}:one:0", local_path=local, sha256=digest, auto_status="ready", reasons=[])
                write_jsonl(batch / "media.jsonl", [row])
                batches.append(batch)
            rows = merge_batches(batches + [batches[1]], root / "combined")
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["platform"] for row in rows}, {"instagram", "bluesky"})
            self.assertEqual(rows[1]["reasons"], ["duplicate_image"])
            self.assertIsNone(rows[1]["local_path"])
            self.assertFalse(rows[0]["freshness"]["alert_eligible"])
            self.assertEqual((root / "combined" / local).read_bytes(), b"saved-image-fixture")
            self.assertEqual(len(read_jsonl(root / "combined/media.jsonl")), 2)
            self.assertEqual(len(read_jsonl(root / "combined/recent-candidates.jsonl")), 1)
            self.assertTrue((root / "combined/index.html").is_file())
            with self.assertRaises(ValueError):
                merge_batches(batches, root / "combined")
            row["local_path"] = "../../private.txt"
            write_jsonl(batches[0] / "media.jsonl", [row])
            with self.assertRaises(ValueError):
                merge_batches(batches, root / "unsafe")
            self.assertFalse((root / "unsafe").exists())


if __name__ == "__main__":
    unittest.main()
