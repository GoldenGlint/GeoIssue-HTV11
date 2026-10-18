import base64
import unittest
from datetime import datetime, timezone

from analysis import submissions

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\0" * 64).decode()
CONFIG = submissions.config()
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def body(**overrides):
    return {"category": "Pothole", "severity": "High", "description": "Deep pothole in the curb lane.",
            "address": "", "coordinates": [-79.3953, 43.6455], "photos": [{"image": JPEG, "mime": "image/jpeg"}], **overrides}


class SubmissionTest(unittest.TestCase):
    def test_a_located_submission_keeps_its_photos_as_sent(self):
        submission, photos = submissions.parse(body(), CONFIG)
        self.assertEqual(submission["location_status"], "provided")
        self.assertEqual(submission["coordinates"], [-79.3953, 43.6455])
        self.assertEqual(photos, [("image/jpeg", base64.b64decode(JPEG))])

    def test_bad_input_is_refused(self):
        png_named_jpeg = {"image": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 8).decode(), "mime": "image/jpeg"}
        for bad in ({"category": "Fire"}, {"severity": "Urgent"}, {"description": "  "}, {"photos": []},
                    {"photos": [{"image": JPEG, "mime": "image/jpeg"}] * 5}, {"photos": [png_named_jpeg]},
                    {"photos": [{"image": "not base64!", "mime": "image/jpeg"}]}, {"photos": [{"image": JPEG, "mime": "image/gif"}]},
                    {"coordinates": [-73.57, 45.5]}, {"coordinates": ["a", "b"]}, {"coordinates": None},
                    {"location_status": "not_found", "coordinates": None}, {"location_status": "teleported"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                submissions.parse(body(**bad), CONFIG)

    def test_a_submission_waiting_for_claude_needs_no_coordinates(self):
        submission, _ = submissions.parse(body(coordinates=None, location_status="locating",
                                               geolocation={"job_id": "20261018-120000-abcdef", "model": "opus"}), CONFIG)
        self.assertIsNone(submission["coordinates"])
        self.assertEqual(submission["geolocation"], {"job_id": "20261018-120000-abcdef", "model": "opus"})

    def test_the_issue_is_placed_scored_and_rounded_like_a_collected_one(self):
        submission, _ = submissions.parse(body(severity=None), CONFIG)
        issue = submissions.build_issue("SUB-0123456789", submission, NOW, 2, CONFIG, NOW)
        self.assertEqual(issue["ward_id"], "10")
        self.assertEqual((issue["verification_status"], issue["source_category"], issue["is_demo"]), ("Needs review", "Community submission", False))
        self.assertGreaterEqual(issue["location_radius_m"], 250)  # unverified locations are rounded for the public map
        self.assertEqual(issue["geo_trace"][-1]["stage"], "Privacy rounding")
        self.assertEqual(issue["evidence_thumbnail"], "./api/submissions/SUB-0123456789/photos/0")
        self.assertEqual(len(issue["evidence_photos"]), 2)
        self.assertIsInstance(issue["priority_score"], (int, float))
        self.assertIn("Severity not given (+0)", issue["priority_reasons"])
        self.assertTrue(issue["nearby_assets"])

    def test_claudes_answer_sets_the_method_and_radius(self):
        submission, _ = submissions.parse(body(location_status="unverified",
                                               geolocation={"job_id": "j", "verified": False, "radius_m": 900}), CONFIG)
        issue = submissions.build_issue("SUB-0123456789", submission, NOW, 1, CONFIG, NOW)
        self.assertEqual(issue["geo_method"], "Located by Claude · not verified")
        self.assertGreaterEqual(issue["location_radius_m"], 900)
        self.assertFalse(issue["nearby_assets"])  # too coarse to measure distances, as in the pipeline

    def test_tokens_are_checked_against_their_hash(self):
        submission_id, token = submissions.new_ids()
        self.assertRegex(submission_id, r"^SUB-[0-9A-F]{10}$")
        stored = submissions.token_hash(token)
        self.assertTrue(submissions.token_matches(token, stored))
        self.assertFalse(submissions.token_matches(token + "x", stored))
        self.assertFalse(submissions.token_matches(None, stored))


if __name__ == "__main__":
    unittest.main()
