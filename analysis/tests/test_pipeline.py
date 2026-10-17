import json
import tempfile
import unittest
from pathlib import Path

from analysis import geo
from analysis.pipeline import run
from analysis.record import FRONTEND_FIELDS

from .helpers import NOW, SAMPLE, config, raw


class PipelineTest(unittest.TestCase):
    def run_sample(self, conf=None, input_path=SAMPLE):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        return run(input_path, conf or config(), self.tmp.name, NOW, offline=True)

    def test_sample_end_to_end(self):
        result = self.run_sample()
        counts = result["report"]["counts"]
        self.assertEqual((counts["input_records"], counts["sightings"], counts["issues"]), (19, 16, 13))
        self.assertEqual({d["reason"] for d in result["report"]["dropped"]}, {"outside Toronto", "no coordinates and no recognised place name"})
        for name in ("issues.public.json", "issues.json", "sightings.json", "areas.json", "report.json"):
            self.assertTrue((Path(self.tmp.name) / name).is_file(), name)
        scores = [i["priority_score"] for i in result["issues"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_every_public_issue_has_the_frontend_fields(self):
        for issue in self.run_sample()["public"]:
            self.assertFalse(set(FRONTEND_FIELDS) - issue.keys(), issue["issue_id"])
            self.assertEqual(issue["geometry"]["type"], "Point")
            self.assertIsInstance(issue["nearby_assets"], list)
            self.assertIsInstance(issue["location_radius_m"], int)
            self.assertEqual(issue["geo_trace"][-1]["stage"], "Privacy rounding")

    def test_unverified_public_locations_are_coarse_but_still_covered(self):
        result = self.run_sample()
        precise = {i["issue_id"]: i for i in result["issues"]}
        for issue in result["public"]:
            original = precise[issue["issue_id"]]
            self.assertGreaterEqual(issue["location_radius_m"], 250)
            moved = geo.distance_m(issue["geometry"]["coordinates"], original["geometry"]["coordinates"])
            self.assertLessEqual(moved + original["location_radius_m"], issue["location_radius_m"])

    def test_no_private_text_reaches_any_output_file(self):
        self.run_sample()
        for path in Path(self.tmp.name).glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for secret in ("sample-author", "sample-volunteer", "Best ramen", "my poor tires", "post_text"):
                self.assertNotIn(secret.lower(), text.lower(), f"{secret} in {path.name}")

    def test_output_is_still_valid_with_every_stage_off(self):
        off = {"enabled": False}
        result = self.run_sample(config(locate=off, dedupe=off, priority=off, stats=off, summaries=off))
        self.assertEqual(result["report"]["counts"]["issues"], 12)  # only records with coordinates in Toronto
        self.assertFalse((Path(self.tmp.name) / "areas.json").exists())
        for issue in result["public"]:
            self.assertFalse(set(FRONTEND_FIELDS) - issue.keys())
            self.assertEqual(issue["neighbourhood_id"], "unassigned")

    def test_photos_needing_blur_are_withheld_unless_shown_on_purpose(self):
        from .test_adapter import handoff_group
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "images").mkdir()
            (folder / "images" / "0.jpg").write_bytes(b"\xff\xd8\xff\xd9")
            (folder / "post-groups.jsonl").write_text(json.dumps(handoff_group("yes")) + "\n")
            [withheld] = self.run_sample(input_path=folder / "post-groups.jsonl")["public"]
            conf = config()
            conf["output"]["photos_needing_blur"] = "show"
            [shown] = self.run_sample(conf, input_path=folder / "post-groups.jsonl")["public"]
        self.assertIsNone(withheld["evidence_thumbnail"])
        self.assertIn("blurred", withheld["evidence_withheld"])
        self.assertIsNotNone(shown["evidence_thumbnail"])
        self.assertNotIn("evidence_withheld", shown)
        self.assertEqual(withheld["neighbourhood_id"], "parkdale")  # placed from the location guess

    def test_input_without_severity_is_scored_with_the_default(self):
        from .test_adapter import handoff_group
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "post-groups.jsonl"
            path.write_text(json.dumps(handoff_group("yes")) + "\n")
            [issue] = self.run_sample(input_path=path)["issues"]
        self.assertEqual(issue["severity"], "Medium")
        self.assertEqual(issue["priority_reasons"][0], "Medium severity (+25)")

    def test_fields_the_input_already_has_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theirs.json"
            path.write_text(json.dumps([raw("a", neighbourhood_id="their-area", neighbourhood="Their area", ward="99", incident_id="THEIRS-1",
                                            priority_score=88, address="1 Their St")]))
            [issue] = self.run_sample(input_path=path)["issues"]
        self.assertEqual((issue["neighbourhood_id"], issue["neighbourhood_name"], issue["ward_id"], issue["incident_id"], issue["priority_score"], issue["address"]),
                         ("their-area", "Their area", "99", "THEIRS-1", 88, "1 Their St"))
        self.assertEqual(issue["provenance"]["neighbourhood_id"], "input")


if __name__ == "__main__":
    unittest.main()
