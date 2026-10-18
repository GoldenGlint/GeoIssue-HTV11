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

    def test_flagged_photos_are_shown_by_default_and_can_be_explicitly_withheld(self):
        from .test_adapter import handoff_group
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "images").mkdir()
            (folder / "images" / "0.jpg").write_bytes(b"\xff\xd8\xff\xd9")
            (folder / "post-groups.jsonl").write_text(json.dumps(handoff_group("yes")) + "\n")
            shown_result = self.run_sample(input_path=folder / "post-groups.jsonl")
            [shown] = shown_result["public"]
            conf = config()
            conf["output"]["photos_needing_blur"] = "withhold"
            [withheld] = self.run_sample(conf, input_path=folder / "post-groups.jsonl")["public"]
        self.assertIsNone(withheld["evidence_thumbnail"])
        self.assertIn("blurred", withheld["evidence_withheld"])
        self.assertIsNotNone(shown["evidence_thumbnail"])
        self.assertNotIn("evidence_withheld", shown)
        self.assertEqual(shown_result["report"]["counts"].get("photos_withheld", 0), 0)
        self.assertEqual(withheld["neighbourhood_id"], "parkdale")  # placed from the location guess

    def test_photos_from_one_post_are_one_titled_sighting(self):
        from .test_adapter import handoff_group
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "post-groups.jsonl"
            group = handoff_group("yes", "yes", "uncertain")
            group["supplemental_images"] = [{"local_path": "images/context.jpg", "caption": "private-context-marker", "author": "sample-author"}]
            (path.parent / "images").mkdir()
            for name in ("0.jpg", "1.jpg", "2.jpg", "context.jpg"):
                (path.parent / "images" / name).write_bytes(b"\xff\xd8\xff\xd9")
            path.write_text(json.dumps(group) + "\n")
            result = self.run_sample(input_path=path)
        written = "".join(p.read_text(encoding="utf-8") for p in Path(self.tmp.name).glob("*.json"))
        [issue] = result["public"]
        self.assertEqual(issue["sightings_count"], 1)
        self.assertEqual(issue["title"], "Blocked storm drain")
        self.assertIn("“Blocked storm drain” (flooding)", issue["explanation"])
        self.assertIn("3 photos from 1 post merged", issue["geo_trace"][-2]["result"])
        self.assertEqual(issue["source_posts"], [group["post_url"]])
        self.assertEqual(len(issue["evidence_photos"]), 4)
        self.assertEqual([photo["role"] for photo in issue["evidence_photos"]], ["evidence", "context", "context", "context"])
        self.assertEqual(len(list((Path(self.tmp.name) / "photos").glob("*.jpg"))), 4)
        self.assertNotIn("private-context-marker", written)
        self.assertNotIn("sample-author", written)

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

    def test_photo_url_prefix_publishes_a_browser_path(self):
        from .test_adapter import handoff_group
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "images").mkdir()
            (folder / "images" / "0.jpg").write_bytes(b"\xff\xd8\xff\xd9")
            (folder / "post-groups.jsonl").write_text(json.dumps(handoff_group("yes")) + "\n")
            out = folder / "out"
            result = run(folder / "post-groups.jsonl", config(), out, NOW, offline=True,
                         photo_url_prefix="./data/analyzed/")
            [issue] = result["public"]
            self.assertTrue(issue["evidence_thumbnail"].startswith("./data/analyzed/photos/"))
            self.assertFalse(issue["evidence_thumbnail"].startswith("file:"))
            name = issue["evidence_thumbnail"].rsplit("/", 1)[1]
            self.assertTrue((out / "photos" / name).is_file())


if __name__ == "__main__":
    unittest.main()
