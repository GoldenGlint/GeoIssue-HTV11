"""Tests for the geolocation endpoints of scripts/serve.py, with the background worker stubbed out."""
import base64
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("serve", ROOT / "scripts" / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)

PHOTO = b"\xff\xd8\xff\xe0 a tiny stand-in jpeg"
AVAILABLE = {"available": True, "model": "opus", "minutes": 10, "missing": [], "street_imagery": True}


class GeolocateApiTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.jobs = Path(tmp.name)
        self.started = []
        for patch in (mock.patch.object(serve, "GEOLOC_JOBS", self.jobs),
                      mock.patch.object(serve, "geolocate_status", lambda: dict(AVAILABLE)),
                      mock.patch.object(serve, "KEY", ""),  # geolocation must not need the Gemini key
                      mock.patch.object(serve.claude_geoloc, "start_background",
                                        lambda job, **kw: self.started.append((job, kw)))):
            patch.start()
            self.addCleanup(patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(serve.Handler, directory=str(ROOT)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if resp.headers["Content-Type"] == "application/json" else raw
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def start(self):
        return self.request("/api/geolocate", {"image": base64.b64encode(PHOTO).decode(), "mime": "image/jpeg"})

    def test_status_reports_whether_geolocation_can_run(self):
        code, body = self.request("/api/status")
        self.assertEqual(code, 200)
        self.assertTrue(body["geolocate"]["available"])

    def test_starting_a_job_saves_the_photo_and_starts_a_worker(self):
        code, job = self.start()
        self.assertEqual(code, 200)
        self.assertEqual(job["state"], "queued")
        self.assertRegex(job["id"], serve.JOB_ID)
        folder, options = self.started[0]
        self.assertEqual((folder / "photo.jpg").read_bytes(), PHOTO)
        self.assertEqual(options["max_running"], serve.GEOLOC_MAX_RUNNING)
        self.assertEqual(self.request("/api/geolocate")[1]["jobs"][0]["id"], job["id"])
        self.assertEqual(self.request(f"/api/geolocate/{job['id']}")[1]["id"], job["id"])
        self.assertEqual(self.request(f"/api/geolocate/{job['id']}/photo")[1], PHOTO)

    def test_bad_photos_and_unavailable_setups_are_refused(self):
        self.assertEqual(self.request("/api/geolocate", {"image": "aGk=", "mime": "image/gif"})[0], 400)
        self.assertEqual(self.request("/api/geolocate", {"image": "not base64!", "mime": "image/png"})[0], 400)
        with mock.patch.object(serve, "geolocate_status",
                               lambda: {**AVAILABLE, "available": False, "missing": ["Claude Code (the claude command)"]}):
            code, body = self.start()
        self.assertEqual(code, 503)
        self.assertIn("Claude Code", body["error"])
        self.assertEqual(self.started, [])

    def test_only_job_files_are_served(self):
        _, job = self.start()
        folder = self.jobs / job["id"]
        (folder / "m1_references.jpg").write_bytes(b"sheet")
        (folder / "events.jsonl").write_text("{}")
        self.assertEqual(self.request(f"/api/geolocate/{job['id']}/references/m1")[1], b"sheet")
        for path in (f"/api/geolocate/{job['id']}/references/m2", f"/api/geolocate/{job['id']}/events.jsonl",
                     f"/api/geolocate/{job['id']}/references/..%2Fevents.jsonl", "/api/geolocate/nope",
                     "/api/geolocate/..%2F..%2F.env", "/api/geolocate/20261018-000000-abcdef"):
            self.assertEqual(self.request(path)[0], 404, path)

    def test_cancel_marks_a_job_whose_worker_never_started(self):
        _, job = self.start()
        code, status = self.request(f"/api/geolocate/{job['id']}/cancel", {})
        self.assertEqual((code, status["state"]), (200, "cancelled"))
        self.assertTrue((self.jobs / job["id"] / "cancel").exists())
        self.assertEqual(self.request("/api/geolocate/nope/cancel", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
