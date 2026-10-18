"""Submission routes, and the hosted app's access to this computer's Claude, in scripts/serve.py."""
import base64
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("geoissue_serve_submissions", ROOT / "scripts" / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\0" * 64).decode()
SUBMISSION = {"category": "Litter", "severity": "Low", "description": "Bags left beside a bin.", "address": "",
              "coordinates": [-79.3866, 43.6505], "photos": [{"image": JPEG, "mime": "image/jpeg"}]}


class SubmissionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class QuietHandler(serve.Handler):
            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(serve.ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, method="GET", body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", **(headers or {})} if data else headers or {}
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_a_located_submission_is_stored_with_its_photos_and_published(self):
        with patch.object(serve.tiger, "add_submission") as add:
            status, _, raw = self.request("/api/submissions", "POST", SUBMISSION)
        self.assertEqual(status, 201)
        reply = json.loads(raw)
        submission_id, token_sha256, submission, photos, issue = add.call_args.args
        self.assertEqual(submission_id, reply["submission_id"])
        self.assertEqual(token_sha256, serve.submissions.token_hash(reply["token"]))
        self.assertEqual(photos, [("image/jpeg", base64.b64decode(JPEG))])
        self.assertEqual(issue["issue_id"], submission_id)
        self.assertEqual(reply["issue"]["verification_status"], "Needs review")

    def test_a_submission_waiting_for_claude_is_stored_unpublished(self):
        with patch.object(serve.tiger, "add_submission") as add:
            status, _, raw = self.request("/api/submissions", "POST", {**SUBMISSION, "coordinates": None, "location_status": "locating",
                                                                       "geolocation": {"job_id": "20261018-120000-abcdef"}})
        self.assertEqual(status, 201)
        self.assertIsNone(add.call_args.args[4])
        self.assertIsNone(json.loads(raw)["issue"])

    def test_bad_submissions_and_outages_are_explicit(self):
        with patch.object(serve.tiger, "add_submission") as add:
            self.assertEqual(self.request("/api/submissions", "POST", {**SUBMISSION, "photos": []})[0], 400)
            self.assertEqual(self.request("/api/submissions", "POST", {**SUBMISSION, "coordinates": [2.35, 48.85]})[0], 400)
            add.assert_not_called()
        with patch.object(serve.tiger, "add_submission", side_effect=RuntimeError("postgresql://user:secret@host")):
            status, _, raw = self.request("/api/submissions", "POST", SUBMISSION)
        self.assertEqual(status, 503)
        self.assertNotIn(b"secret", raw)

    def test_only_the_submitting_browser_can_add_claudes_location_once(self):
        submission_id, token = serve.submissions.new_ids()
        waiting = {**SUBMISSION, "coordinates": None, "location_status": "locating", "geolocation": {"job_id": "j"}}
        waiting.pop("photos")
        stored = (waiting, serve.submissions.token_hash(token), datetime(2026, 10, 18, tzinfo=timezone.utc), "locating", 1)
        answer = {"location_status": "located", "coordinates": [-79.3866, 43.6505],
                  "geolocation": {"job_id": "j", "verified": True, "radius_m": 40, "place_description": "Queen and University"}}
        path = f"/api/submissions/{submission_id}/location"
        with patch.object(serve.tiger, "submission", return_value=stored), patch.object(serve.tiger, "locate_submission", return_value=True) as locate:
            self.assertEqual(self.request(path, "POST", {**answer, "token": "guess"})[0], 403)
            locate.assert_not_called()
            status, _, raw = self.request(path, "POST", {**answer, "token": token})
        self.assertEqual(status, 200)
        issue = json.loads(raw)["issue"]
        self.assertEqual(issue["geo_method"], "Located by Claude · verified by street-level imagery")
        self.assertEqual(locate.call_args.args[1]["address"], "Queen and University")
        with patch.object(serve.tiger, "submission", return_value=(*stored[:3], "located", 1)):
            self.assertEqual(self.request(path, "POST", {**answer, "token": token})[0], 409)
        with patch.object(serve.tiger, "submission", return_value=None):
            self.assertEqual(self.request(path, "POST", {**answer, "token": token})[0], 404)

    def test_photos_are_served_only_once_published(self):
        with patch.object(serve.tiger, "submission_photo", return_value=("image/jpeg", b"\xff\xd8\xffdata")) as photo:
            status, headers, raw = self.request("/api/submissions/SUB-0123456789/photos/0")
        self.assertEqual((status, headers["Content-Type"], raw), (200, "image/jpeg", b"\xff\xd8\xffdata"))
        photo.assert_called_once_with("SUB-0123456789", 0)
        with patch.object(serve.tiger, "submission_photo", return_value=None):
            self.assertEqual(self.request("/api/submissions/SUB-0123456789/photos/1")[0], 404)
        self.assertEqual(self.request("/api/submissions/../../.env/photos/0")[0], 404)

    def test_the_hosted_app_may_use_this_computers_claude_and_no_other_site_may(self):
        hosted = {"Origin": "https://geoissue.photo"}
        status, headers, _ = self.request("/api/geolocate", "OPTIONS", headers={**hosted, "Access-Control-Request-Method": "POST"})
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://geoissue.photo")
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")
        status, headers, _ = self.request("/api/status", headers=hosted)
        self.assertEqual((status, headers.get("Access-Control-Allow-Origin")), (200, "https://geoissue.photo"))
        with patch.object(serve.claude_geoloc, "list_jobs", return_value=[]):
            self.assertEqual(self.request("/api/geolocate", headers=hosted)[0], 200)
            evil = {"Origin": "https://evil.example"}
            self.assertEqual(self.request("/api/geolocate", "OPTIONS", headers=evil)[0], 403)
            status, headers, _ = self.request("/api/geolocate", headers=evil)
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            # a page that reached this server under another name (DNS rebinding) is refused
            self.assertEqual(self.request("/api/geolocate", headers={**hosted, "Host": "geoissue.photo"})[0], 403)
        # the database and Gemini routes are not opened to the hosted app
        status, headers, _ = self.request("/api/issues", headers=hosted)
        self.assertNotIn("Access-Control-Allow-Origin", headers)


if __name__ == "__main__":
    unittest.main()
