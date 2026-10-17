import json
import tempfile
import unittest
from pathlib import Path

from analysis import adapter

from .helpers import adapt, config, raw


class GetPathTest(unittest.TestCase):
    def test_nested_keys_and_list_indexes(self):
        data = {"a": {"b": [{"c": 1}, {"c": 2}]}}
        self.assertEqual(adapter.get_path(data, "a.b[1].c"), 2)
        self.assertIsNone(adapter.get_path(data, "a.b[5].c"))
        self.assertIsNone(adapter.get_path(data, "a.x"))


class AdaptTest(unittest.TestCase):
    def test_first_listed_path_wins(self):
        [record], _ = adapt([raw(lat=None, latitude=43.70, longitude=-79.40, gps={"lat": 43.80, "lng": -79.30})])
        self.assertEqual(record["geometry"]["coordinates"], [-79.40, 43.70])
        self.assertEqual(record["geo_method"], "Coordinates supplied with the photo")

    def test_labels_are_mapped_and_unknown_ones_reported(self):
        records, report = adapt([raw("a", issue_type="Road_Damage"), raw("b", issue_type="broken streetlight")])
        self.assertEqual([r["issue_type"] for r in records], ["Pothole", "Other"])
        self.assertEqual(report["unrecognised_values"]["issue_type"]["broken streetlight"], 1)

    def test_numeric_severity_and_percentage_confidence(self):
        record = raw()
        record["issues"][0].update(severity=0.8, certainty=87)
        [result], _ = adapt([record])
        self.assertEqual(result["severity"], "High")
        self.assertEqual(result["detection_confidence"], 0.87)

    def test_epoch_seconds_and_milliseconds_become_iso(self):
        records, _ = adapt([raw("a", posted_at=1791991800), raw("b", posted_at=1791991800000)])
        self.assertEqual({r["first_seen_at"] for r in records}, {"2026-10-14T15:30:00Z"})

    def test_each_issue_in_a_photo_becomes_a_record(self):
        record = raw(issues=[{"type": "graffiti"}, {"type": "litter"}])
        records, _ = adapt([record])
        self.assertEqual([r["issue_type"] for r in records], ["Graffiti", "Litter"])
        self.assertNotEqual(records[0]["issue_id"], records[1]["issue_id"])

    def test_photos_without_an_issue_are_skipped(self):
        records, report = adapt([raw("a", issues=[]), raw("b", issues=[{"type": "none"}])])
        self.assertEqual(records, [])
        self.assertEqual(report["counts"]["skipped_not_an_issue"], 2)

    def test_ids_are_stable_hashes_of_the_source_id(self):
        first, _ = adapt([raw("abc")])
        again, _ = adapt([raw("abc", lat=43.7)])
        self.assertEqual(first[0]["issue_id"], again[0]["issue_id"])
        self.assertRegex(first[0]["issue_id"], r"^CL-[0-9A-F]{8}$")

    def test_private_and_unmapped_fields_are_not_kept(self):
        [record], report = adapt([raw(author="someone", scene="street", text="king and spadina")])
        self.assertNotIn("author", record)
        self.assertNotIn("scene", record)
        self.assertEqual(record["post_text"], "king and spadina")  # kept only for finding a place; never written
        self.assertIn("author", report["private_fields_dropped"])
        self.assertIn("scene", report["unused_input_fields"])

    def test_passthrough_copies_fields_but_never_private_ones(self):
        conf = config()
        conf["output"]["passthrough"] = ["blur_applied", "author"]
        [record], _ = adapt([raw(blur_applied=True, author="someone")], conf)
        self.assertTrue(record["blur_applied"])
        self.assertNotIn("author", record)

    def test_low_confidence_detections_can_be_skipped(self):
        conf = config()
        conf["input"]["min_detection_confidence"] = 0.95
        records, report = adapt([raw()], conf)
        self.assertEqual(records, [])
        self.assertEqual(report["counts"]["skipped_low_confidence"], 1)


def handoff_group(*supported):
    """A post group in the scraping handoff's shape (scraping/shared/post-groups.jsonl), trimmed."""
    return {
        "post_id": "https://example.org/post/1", "platform": "reddit", "posted_at": "2026-10-16T17:44:29+00:00",
        "caption": "Queen and Dufferin again", "post_url": "https://example.org/post/1",
        "passed_images": [{
            "key": f"reddit:post1:{n}", "local_path": f"images/{n}.jpg", "dhash": "d9583c3e73729043",
            "screening": {"issue_type": "drain", "issue_confidence": "high", "location_guess": "Queen Street West and Dufferin Street, Toronto",
                          "clues": ["Toronto street sign"], "blur_before_public_display": True},
            "issue_details": {"issue_supported": verdict, "confidence": "medium", "description": f"Blocked drain {n}."},
        } for n, verdict in enumerate(supported)],
    }


class ScrapingHandoffTest(unittest.TestCase):
    def test_each_passed_image_becomes_a_record(self):
        records, report = adapt([handoff_group("yes", "uncertain")])
        self.assertEqual([r["issue_type"] for r in records], ["Flooding", "Flooding"])
        self.assertEqual([r["description"] for r in records], ["Blocked drain 0.", "Blocked drain 1."])
        self.assertEqual(records[0]["location_text"], "Queen Street West and Dufferin Street, Toronto")
        self.assertEqual(records[0]["source_category"], "Public social post")
        self.assertEqual(records[0]["detection_confidence"], 0.6)  # "medium" via [values.detection_confidence]
        self.assertTrue(records[0]["photo_needs_blur"])
        self.assertNotIn("post_url", records[0])
        self.assertNotIn("passed_images[].screening.issue_type", report["unused_input_fields"])

    def test_unsupported_claims_are_skipped_and_counted(self):
        records, report = adapt([handoff_group("yes", "no", "no")])
        self.assertEqual(len(records), 1)
        self.assertEqual(report["counts"]["skipped_issue_supported=no"], 2)


class ReadInputTest(unittest.TestCase):
    def test_wrapped_file_jsonl_and_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "wrapped.json").write_text(json.dumps({"results": [raw("a"), raw("b")]}))
            (folder / "single.json").write_text(json.dumps(raw("c")))
            (folder / "more.jsonl").write_text(json.dumps(raw("d")) + "\n\n" + json.dumps(raw("e")) + "\n")
            keys = config()["input"]["records_keys"]
            self.assertEqual(len(adapter.read_input(folder / "wrapped.json", keys)), 2)
            ids = sorted(item["post_id"] for item, _ in adapter.read_input(folder, keys))
            self.assertEqual(ids, ["a", "b", "c", "d", "e"])


if __name__ == "__main__":
    unittest.main()
