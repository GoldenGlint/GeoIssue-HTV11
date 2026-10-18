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
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows: a just-killed process may still hold it
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

    def request(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if resp.headers["Content-Type"] == "application/json" else raw
        except urllib.error.HTTPError as error:  # API errors are JSON; refused static paths are a plain 404 page
            body = error.read()
            return error.code, json.loads(body) if error.headers.get("Content-Type") == "application/json" else body

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


    def test_other_sites_cannot_use_the_api(self):
        body = {"image": base64.b64encode(PHOTO).decode(), "mime": "image/jpeg"}
        self.assertEqual(self.request("/api/geolocate", body, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/geolocate", body, {"Content-Type": "text/plain"})[0], 403)
        self.assertEqual(self.request("/api/geolocate", headers={"Host": "rebind.example:5173"})[0], 403)
        port = self.server.server_address[1]
        self.assertEqual(self.request("/api/geolocate", body, {"Origin": f"http://localhost:{port}",
                                                               "Host": f"localhost:{port}"})[0], 200)
        self.assertEqual(len(self.started), 1)

    def test_job_folders_are_never_served_as_static_files(self):
        with mock.patch.object(serve, "GEOLOC_JOBS", ROOT / "data" / "geolocate"):
            for path in ("/data/geolocate/", "/data//geolocate/x/events.jsonl", "/Data/GeoLocate/",
                         "/data/x/../geolocate/", "/data/geolocate%2Fx"):
                req = urllib.request.Request(self.base + path)
                with self.assertRaises(urllib.error.HTTPError, msg=path) as caught:
                    urllib.request.urlopen(req, timeout=10)
                self.assertEqual(caught.exception.code, 404, path)

    def test_too_many_active_jobs_are_refused(self):
        for _ in range(serve.GEOLOC_MAX_ACTIVE):
            self.assertEqual(self.start()[0], 200)
        code, body = self.start()
        self.assertEqual(code, 429)
        self.assertIn("already being located", body["error"])

    def test_a_worker_that_fails_to_start_leaves_a_failed_job(self):
        with mock.patch.object(serve.claude_geoloc, "start_background", side_effect=OSError("no python")):
            code, job = self.start()
        self.assertEqual((code, job["state"]), (200, "failed"))
        self.assertIn("no python", job["error"])


if __name__ == "__main__":
    unittest.main()
