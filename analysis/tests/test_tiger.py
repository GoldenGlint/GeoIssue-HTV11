import copy
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from analysis import tiger
from analysis.pipeline import run
from scripts.serve import Handler
from .helpers import NOW, config
from .test_adapter import handoff_group


class TigerTest(unittest.TestCase):
    def test_pipeline_counts_independent_posts_and_strips_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "posts.json"
            group = handoff_group("yes", "yes", "uncertain")
            path.write_text(json.dumps([group]))
            result = run(path, config(), Path(tmp) / "out", NOW, offline=True)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["public"][0]["sightings_count"], 1)
        event = result["events"][0]
        self.assertEqual(event["issue_id"], result["public"][0]["issue_id"])
        self.assertEqual(len(event["sighting_id"]), 64)
        self.assertNotIn("post_id", event)
        self.assertNotIn("source_post", event)
        self.assertNotIn("author", event)

    def test_unknown_dates_remain_unknown_and_counts_do_not_invent_history(self):
        issue = {"incident_id": "i", "issue_id": "a", "ward_id": "10", "issue_type": "Flooding"}
        records = [{"incident_id": "i", "issue_id": "a", "sightings_count": 100,
                    "first_seen_at": tiger.iso(NOW), "provenance": {"first_seen_at": "default"}}]
        [event] = tiger.prepare_sightings([issue], records)
        self.assertIsNone(event["reported_at"])
        self.assertEqual(event["timestamp_basis"], "ingestion")
        self.assertEqual(tiger.prepare_sightings([issue], records), [event])

    def test_activity_uses_complete_hours_and_requires_a_real_baseline(self):
        now = NOW + timedelta(minutes=35)
        rows = [(NOW - timedelta(days=3), "10", 7, 0),
                (NOW - timedelta(hours=2), "10", 8, 1), (NOW, "10", 30, 0),
                (NOW - timedelta(hours=1), "11", 99, 0)]
        result = tiger.summarize_activity(rows, 7, now, tiger.iso(NOW - timedelta(days=10)))
        self.assertEqual(result["reports"], 144)
        self.assertEqual(result["undated_reports"], 1)
        wards = {row["ward_id"]: row for row in result["wards"]}
        self.assertEqual(wards["10"]["recent"], 8)  # current hour's 30 is deliberately excluded
        self.assertTrue(wards["10"]["emerging"])
        self.assertFalse(wards["11"]["emerging"])  # zero baseline is not an infinite surge
        self.assertEqual(len(result["series"]), 7 * 24 + 1)
        short = tiger.summarize_activity(rows, 7, now, tiger.iso(NOW - timedelta(days=4)))
        self.assertFalse(any(ward["emerging"] for ward in short["wards"]))

    def test_simulated_issues_move_forward_with_one_report_per_sighting(self):
        sample = {"generated_at": "2026-10-17T12:00:00Z", "issues": [
            {"issue_id": "CL-1", "ward_id": "10", "issue_type": "Flooding", "sightings_count": 3, "is_demo": True,
             "first_seen_at": "2026-10-10T12:00:00Z", "last_seen_at": "2026-10-16T12:00:00Z"},
            {"issue_id": "CL-2", "ward_id": "4", "issue_type": "Litter", "sightings_count": 1, "is_demo": True,
             "first_seen_at": "2026-10-17T06:00:00Z", "last_seen_at": "2026-10-17T06:00:00Z"}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(tiger, "sync", side_effect=lambda *args, **kwargs: (args, kwargs)):
            path = Path(tmp) / "issues.json"
            path.write_text(json.dumps(sample))
            (public, sightings, report), options = tiger.simulate(path)
        self.assertEqual(options, {"dataset": "simulated"})
        shift = tiger.moment(report["generated_at"]) - tiger.moment(sample["generated_at"])
        self.assertEqual(tiger.moment(public[0]["last_seen_at"]), tiger.moment("2026-10-16T12:00:00Z") + shift)
        self.assertLessEqual(tiger.moment(report["generated_at"]), datetime.now(timezone.utc))
        self.assertEqual([s["sighting_id"] for s in sightings], ["CL-1-0", "CL-1-1", "CL-1-2", "CL-2-0"])
        self.assertEqual([s["reported_at"] for s in sightings[:3]],
                         [public[0]["first_seen_at"], tiger.iso(tiger.moment("2026-10-13T12:00:00Z") + shift), public[0]["last_seen_at"]])
        self.assertEqual(report["counts"], {"sightings": 4, "issues": 2})

    def test_filter_validation(self):
        self.assertEqual(tiger.activity_options({"ward": ["10"], "type": ["Flooding"]}),
                         {"dataset": "collected", "days": 30, "ward": "10", "category": "Flooding"})
        for query in ({"days": ["100000"]}, {"days": ["7", "30"]}, {"ward": ["26"]},
                      {"type": ["'; DROP TABLE issues; --"]}, {"sql": ["SELECT 1"]}, {"dataset": ["private"]}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                tiger.activity_options(query)

    def test_missing_configuration_has_no_driver_or_connection_details(self):
        with patch.object(tiger, "setting", return_value=None), self.assertRaisesRegex(tiger.Unavailable, "not configured"):
            tiger.connection()

    def test_connection_errors_explain_missing_credentials_without_leaking_details(self):
        class DriverError(Exception):
            pass
        def connect(*args, **kwargs):
            raise DriverError(driver_message)
        driver = SimpleNamespace(connect=connect, Error=DriverError)
        cases = [("private-host: no password supplied", "missing its password"),
                 ("password authentication failed for user private-user", "rejected the credentials"),
                 ("postgresql://private-user:private-password@private-host unreachable", "unreachable")]
        for driver_message, expected in cases:
            with self.subTest(expected=expected), patch.dict("sys.modules", {"psycopg": driver}), \
                    patch.object(tiger, "setting", return_value="postgresql://example"), \
                    self.assertRaisesRegex(tiger.Unavailable, expected) as caught:
                tiger.connection()
            self.assertNotIn("private-", str(caught.exception))

    def test_failed_import_keeps_analysis_outputs(self):
        from analysis.__main__ import main
        with tempfile.TemporaryDirectory() as tmp, patch("sys.argv", ["analysis", "--offline", "--tiger", "--out", tmp]), \
                patch.object(tiger, "sync", side_effect=tiger.Unavailable("Not configured")), \
                redirect_stdout(io.StringIO()), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 1)
            self.assertTrue((Path(tmp) / "issues.public.json").is_file())


class TigerApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class QuietHandler(Handler):
            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=tempfile.gettempdir()))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url + path) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            body = error.read()
            return error.code, json.loads(body) if error.headers.get_content_type() == "application/json" else {}

    def test_api_rejects_invalid_filters_before_querying(self):
        with patch.object(tiger, "activity") as activity:
            self.assertEqual(self.get("/api/activity?days=99999")[0], 400)
            activity.assert_not_called()
            self.assertEqual(self.get("/api/issues?dataset=private")[0], 400)
            self.assertEqual(self.get("/api/activity?ward=10&ward=11")[0], 400)

    def test_valid_activity_route_passes_only_validated_arguments(self):
        with patch.object(tiger, "activity", return_value={"reports": 2}) as activity:
            self.assertEqual(self.get("/api/activity?days=7&ward=10&type=Flooding"), (200, {"reports": 2}))
            activity.assert_called_once_with(dataset="collected", days=7, ward="10", category="Flooding")

    def test_database_errors_are_explicit_and_do_not_leak_credentials(self):
        with patch.object(tiger, "issues", side_effect=RuntimeError("postgresql://user:secret@private-host")):
            code, body = self.get("/api/issues")
        self.assertEqual(code, 503)
        self.assertNotIn("secret", json.dumps(body))
        self.assertEqual(self.get("/api/arbitrary-sql")[0], 404)
        self.assertEqual(self.get("/.env")[0], 404)

    def test_storage_metrics_route_is_read_only_and_rejects_parameters(self):
        with patch.object(tiger, "database_stats", return_value={"reports_by_dataset": {"collected": 6}}) as stats:
            self.assertEqual(self.get("/api/tiger"), (200, {"reports_by_dataset": {"collected": 6}}))
            self.assertEqual(self.get("/api/tiger?sql=anything")[0], 400)
            stats.assert_called_once_with()
        with patch.object(tiger, "database_stats", side_effect=RuntimeError("postgresql://user:secret@private-host")):
            code, body = self.get("/api/tiger")
        self.assertEqual(code, 503)
        self.assertNotIn("secret", json.dumps(body))


@unittest.skipUnless(os.environ.get("TIGER_TEST_DATABASE_URL"), "requires a separate disposable TimescaleDB test database")
class TigerDatabaseTest(unittest.TestCase):
    def test_schema_snapshot_idempotency_historical_refresh_and_rollback(self):
        with patch.object(tiger, "setting", return_value=os.environ["TIGER_TEST_DATABASE_URL"]):
            tiger.initialize()
            tiger.initialize()
            now = datetime.now(timezone.utc)
            public = [{"issue_id": "test-a", "priority_score": 2, "geometry": {"type": "Point", "coordinates": [-79.4, 43.7]}, "is_demo": True}]
            events = [{"sighting_id": "test-old", "issue_id": "test-a", "ward_id": "10", "issue_type": "Flooding",
                       "reported_at": tiger.iso(now - timedelta(days=120)), "timestamp_basis": "source"},
                      {"sighting_id": "test-undated", "issue_id": "test-a", "ward_id": "10", "issue_type": "Flooding",
                       "reported_at": None, "timestamp_basis": "ingestion"}]
            report = {"generated_at": tiger.iso(now)}
            tiger.sync(public, events, report)
            with tiger.connection() as conn:
                before = conn.execute("SELECT sighting_id, reported_at, ingested_at FROM geoissue.sightings WHERE dataset = 'collected' ORDER BY sighting_id").fetchall()
            self.assertGreaterEqual(tiger.compress_history()["converted_or_already_columnstore_chunks"], 1)
            tiger.sync(public, events, report)
            with tiger.connection() as conn:
                self.assertEqual(before, conn.execute("SELECT sighting_id, reported_at, ingested_at FROM geoissue.sightings WHERE dataset = 'collected' ORDER BY sighting_id").fetchall())
                self.assertEqual(conn.execute("SELECT sum(reports) FROM geoissue.ward_activity_hourly WHERE dataset = 'collected'").fetchone()[0], 2)
            self.assertEqual(tiger.issues(), public)
            self.assertEqual(tiger.activity()["reports"], 1)
            bad = copy.deepcopy(events)
            bad[0]["issue_id"] = "nonexistent"
            with self.assertRaises(Exception):
                tiger.sync(public, bad, report)
            self.assertEqual(tiger.pipeline()["reports"], 2)
            tiger.sync(public, events[1:], report)
            with tiger.connection() as conn:
                self.assertEqual(conn.execute("SELECT sum(reports) FROM geoissue.ward_activity_hourly WHERE dataset = 'collected'").fetchone()[0], 1)
            self.assertTrue(tiger.benchmark("collected")["results_match"])


if __name__ == "__main__":
    unittest.main()
