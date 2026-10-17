import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analysis import adapter, geo
from analysis.record import as_incident
from analysis.reference import Reference
from analysis.stages import dedupe, locate, priority, stats, summaries

from .helpers import NOW, adapt, config, raw


def located(*raw_records, **locate_overrides):
    conf = config(locate=locate_overrides)
    records, report = adapt(raw_records, conf)
    locate.run(records, conf["stages"]["locate"], Reference(conf["stages"]["locate"]), report)
    return records


class GeoTest(unittest.TestCase):
    def test_distances(self):
        self.assertAlmostEqual(geo.distance_m([-79.3806, 43.6453], [-79.3806, 43.6553]), 1112, delta=2)
        self.assertAlmostEqual(geo.distance_to_line_m([0, 0.001], [[-0.01, 0], [0.01, 0]]), 111, delta=1)

    def test_polygon_with_hole(self):
        square = {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]]}
        self.assertTrue(geo.contains(square, [3, 3]))
        self.assertFalse(geo.contains(square, [1.5, 1.5]))
        self.assertFalse(geo.contains(square, [5, 5]))

    def test_snapping_keeps_nearby_points_together(self):
        centre = geo.snap_to_grid([-79.3951, 43.6457], 250)
        self.assertLess(geo.distance_m(centre, [-79.3951, 43.6457]), 250 * 0.71)
        for d_lng, d_lat in ((0.0003, 0.0003), (-0.0003, -0.0003), (0.0003, -0.0003)):
            self.assertEqual(geo.snap_to_grid([centre[0] + d_lng, centre[1] + d_lat], 250), centre)


class LocateTest(unittest.TestCase):
    def test_coordinates_get_area_ward_asset_and_address(self):
        [r] = located(raw())
        self.assertEqual((r["neighbourhood_id"], r["neighbourhood_name"], r["ward_id"], r["ward_name"]),
                         ("downtown", "Downtown", "10", "Spadina—Fort York"))
        self.assertEqual(r["address"], "King St W & Spadina Ave")
        self.assertEqual({a["type"] for a in r["nearby_assets"]}, {"TTC", "Schools", "Roads"})
        distances = [a["distance_m"] for a in r["nearby_assets"]]
        self.assertEqual(distances, sorted(distances))
        self.assertEqual((r["asset_id"], r["distance_m"]), (r["nearby_assets"][0]["asset_id"], distances[0]))
        self.assertEqual(r["location_radius_m"], 50)
        self.assertEqual(r["geo_trace"][0], {"stage": "Coordinates", "result": "Supplied with the photo or post", "status": "match"})

    def test_place_named_in_text_when_there_are_no_coordinates(self):
        [r] = located(raw(lat=None, text="huge pothole at queen and dufferin"))
        self.assertLess(geo.distance_m(r["geometry"]["coordinates"], [-79.4283, 43.6425]), 1)
        self.assertEqual(r["neighbourhood_id"], "parkdale")
        self.assertEqual(r["location_radius_m"], 75)
        self.assertIn("post text", r["geo_method"])

    def test_intersections_need_both_street_names_together(self):
        [r] = located(raw(lat=None, location_text="Queen Street West and Spadina Avenue intersection, Toronto"))
        self.assertEqual(r["address"], "Queen St W & Spadina Ave")  # from the OpenStreetMap gazetteer
        [slash] = located(raw(lat=None, text="misaligned storm drain cover at Queen/Spadina"))
        self.assertEqual(slash["address"], "Queen St W & Spadina Ave")
        [apart] = located(raw(lat=None, text="walked along queen for a while, then up to spadina"))
        self.assertNotIn("geometry", apart)

    def test_the_first_of_equally_precise_places_wins(self):
        [r] = located(raw(lat=None, text="broken windows from yonge and dundas up to yonge and college"))
        self.assertEqual(r["address"], "Dundas St & Yonge St")

    def test_stations_match_with_their_line_named_even_when_closed(self):
        [r] = located(raw(lat=None, location_text="Ellesmere RT Station, Toronto"))
        self.assertEqual(r["address"], "Ellesmere Station (closed)")
        self.assertEqual(r["ward_id"], "21")  # Scarborough Centre, from the ward boundaries

    def test_neighbourhood_level_text_gets_no_asset_or_street_address(self):
        [r] = located(raw(lat=None, text="garbage all over kensington market"))
        self.assertEqual(r["neighbourhood_id"], "kensington-market")
        self.assertGreater(r["location_radius_m"], 250)
        self.assertNotIn("asset_name", r)
        self.assertNotIn("nearby_assets", r)
        self.assertNotIn("address", r)

    def test_values_from_the_input_are_kept_unless_overwrite(self):
        [kept] = located(raw(neighbourhood_id="their-area", neighbourhood="Their area", address="123 Their St"))
        self.assertEqual((kept["neighbourhood_id"], kept["neighbourhood_name"], kept["address"]), ("their-area", "Their area", "123 Their St"))
        self.assertEqual(kept["provenance"]["neighbourhood_id"], "input")
        # An ID and its name always come from one source. The ward is its own layer, so it is still filled.
        self.assertEqual((kept["ward_id"], kept["provenance"]["ward_id"]), ("10", "locate"))
        [replaced] = located(raw(neighbourhood_id="their-area"), overwrite=True)
        self.assertEqual(replaced["neighbourhood_id"], "downtown")

    def test_unrecognised_text_leaves_the_record_unlocated(self):
        [r] = located(raw(lat=None, text="pothole on my street"))
        self.assertNotIn("geometry", r)


class DedupeTest(unittest.TestCase):
    def merge(self, *raw_records, **settings):
        records = located(*raw_records)
        conf = config(dedupe=settings)["stages"]["dedupe"]
        return dedupe.run(records, conf, adapter.new_report()), records

    def test_close_sightings_of_the_same_issue_merge(self):
        issues, sightings = self.merge(raw("a", posted_at="2026-10-15T00:00:00Z"),
                                       raw("b", lat=43.6455, lng=-79.3954, posted_at="2026-10-16T00:00:00Z"))
        [issue] = issues
        self.assertEqual(issue["sightings_count"], 2)
        self.assertEqual(issue["issue_id"], sightings[0]["issue_id"])  # the earliest sighting names the issue
        self.assertEqual((issue["first_seen_at"], issue["last_seen_at"]), ("2026-10-15T00:00:00Z", "2026-10-16T00:00:00Z"))
        self.assertEqual({s["incident_id"] for s in sightings}, {issue["incident_id"]})

    def test_different_type_far_apart_or_weeks_apart_stay_separate(self):
        issues, _ = self.merge(raw("a"), raw("b", issue_type="graffiti"), raw("c", lat=43.6500),
                               raw("d", posted_at="2026-09-20T00:00:00Z"))
        self.assertEqual(len(issues), 4)

    def test_matching_photo_hashes_merge_reposts_anywhere(self):
        issues, _ = self.merge(raw("a", image_hash="c3a1f0e2b4d59687"),
                               raw("b", lat=43.6600, lng=-79.3500, image_hash="c3a1f0e2b4d59685"))
        self.assertEqual(len(issues), 1)

    def test_incident_ids_from_the_input_are_used_as_given(self):
        issues, _ = self.merge(raw("a", incident_id="THEIRS-1"), raw("b", lat=43.70, incident_id="THEIRS-1"), raw("c"))
        self.assertEqual(sorted(i["incident_id"] for i in issues)[1], "THEIRS-1")
        self.assertEqual(next(i for i in issues if i["incident_id"] == "THEIRS-1")["sightings_count"], 2)


class PriorityTest(unittest.TestCase):
    settings = config()["stages"]["priority"]

    def issue(self, **fields):
        base = {"issue_id": "CL-1", "severity": "Medium", "sightings_count": 1, "first_seen_at": "2026-10-16T12:00:00Z",
                "detection_confidence": 0.9, "resolution_status": "Open"}
        return {**base, **fields}

    def test_severity_sightings_age_and_nearby_school_add_up(self):
        score, reasons = priority.score_issue(self.issue(severity="High", sightings_count=3, first_seen_at="2026-10-07T12:00:00Z",
                                                         nearby_assets=[{"type": "Schools", "asset_id": "SCH-1", "name": "A School", "distance_m": 40}]),
                                              self.settings, NOW)
        self.assertEqual(score, 40 + 16 + 5 + 15)
        self.assertIn("40 m from A School (+15)", reasons)

    def test_low_confidence_scales_down_and_resolved_is_zero(self):
        self.assertEqual(priority.score_issue(self.issue(detection_confidence=0.4), self.settings, NOW)[0], round(25.5 * 0.7))
        self.assertEqual(priority.score_issue(self.issue(resolution_status="Resolved"), self.settings, NOW), (0, ["Resolved"]))

    def test_priority_from_the_input_is_kept(self):
        issues = [self.issue(priority_score=99)]
        priority.run(issues, self.settings, NOW, adapter.new_report())
        self.assertEqual(issues[0]["priority_score"], 99)


class StatsAndSummariesTest(unittest.TestCase):
    def areas(self):
        issues = [
            {"issue_id": "1", "issue_type": "Pothole", "ward_id": "10", "neighbourhood_id": "Downtown", "first_seen_at": "2026-10-16T00:00:00Z",
             "resolution_status": "Open", "priority_score": 50, "address": "King St W & Spadina Ave"},
            {"issue_id": "2", "issue_type": "Pothole", "ward_id": "10", "neighbourhood_id": "Downtown", "first_seen_at": "2026-10-08T00:00:00Z",
             "resolution_status": "Resolved", "priority_score": 0, "address": "x"},
            {"issue_id": "3", "issue_type": "Litter", "ward_id": "4", "neighbourhood_id": "Parkdale", "first_seen_at": "2026-09-01T00:00:00Z",
             "resolution_status": "Open", "priority_score": 20, "address": "y"},
        ]
        return stats.run(issues, config()["stages"]["stats"], NOW)

    def test_counts_and_trend_windows(self):
        result = self.areas()
        ward10 = next(a for a in result["by_area"]["ward_id"] if a["name"] == "10")
        self.assertEqual((ward10["total"], ward10["open"], ward10["new_recent"], ward10["new_previous"]), (2, 1, 1, 1))
        self.assertEqual(ward10["top_priority"][0]["issue_id"], "1")
        self.assertEqual(result["city"]["by_type"], {"Pothole": 2, "Litter": 1})

    def run_summaries(self, result, offline=False):
        report = adapter.new_report()
        with tempfile.TemporaryDirectory() as tmp:
            summaries.run(result, config()["stages"]["summaries"], report, Path(tmp) / "cache.json", offline=offline)
        return report

    def test_template_summary_offline(self):
        result = self.areas()
        self.run_summaries(result, offline=True)
        text = result["by_area"]["ward_id"][0]["summary"]["text"]
        self.assertTrue(text.startswith("Ward 10 has 2 issues"), text)
        self.assertIn("not every issue", text)

    def test_gemini_summary_and_cache(self):
        def fake_urlopen(request, timeout):
            response = mock.MagicMock()
            response.__enter__.return_value = io.BytesIO(json.dumps({"candidates": [{"content": {"parts": [{"text": "Ward 10 summary."}]}}]}).encode())
            return response

        result = self.areas()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cache = Path(tmp.name) / "cache.json"
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             mock.patch("analysis.stages.summaries.urllib.request.urlopen", side_effect=fake_urlopen) as urlopen:
            summaries.run(result, config()["stages"]["summaries"], adapter.new_report(), cache)
            request = urlopen.call_args_list[0].args[0]
            self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
            self.assertIn("Do not mention politicians", json.loads(request.data)["contents"][0]["parts"][0]["text"])
            calls = urlopen.call_count
            summaries.run(self.areas(), config()["stages"]["summaries"], adapter.new_report(), cache)
            self.assertEqual(urlopen.call_count, calls)  # second run is served from the cache
        self.assertEqual(result["by_area"]["ward_id"][0]["summary"], {"text": "Ward 10 summary.", "method": "gemini:gemini-3.5-flash-lite"})

    def test_gemini_failure_falls_back_to_the_template(self):
        result = self.areas()
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}), \
             mock.patch("analysis.stages.summaries.urllib.request.urlopen", side_effect=OSError("offline")):
            report = self.run_summaries(result)
        self.assertEqual(result["by_area"]["ward_id"][0]["summary"]["method"], "template")
        self.assertTrue(any("failed" in w for w in report["warnings"]))


class AsIncidentTest(unittest.TestCase):
    def test_single_sighting_incident(self):
        record = {"issue_id": "CL-ABC", "provenance": {}}
        issue = as_incident(record)
        self.assertEqual((issue["incident_id"], issue["sighting_ids"]), ("INC-ABC", ["CL-ABC"]))


if __name__ == "__main__":
    unittest.main()
