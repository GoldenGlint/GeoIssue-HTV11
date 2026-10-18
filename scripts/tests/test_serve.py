"""Public-file allowlist, health, and Gemini concurrency for scripts/serve.py."""
import base64
import importlib.util
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("geoissue_serve", ROOT / "scripts" / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)

TRIAGE = json.dumps({
    "is_civic_issue": False, "category": "Other", "severity": "Low", "description": "Nothing to fix.",
    "confidence": 0.2, "public_scene": True, "person_is_subject": False, "faces": [], "plates": [],
    "reason": "No defect.",
})


class ServeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(serve.Handler, directory=str(serve.ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def request(self, path, method="GET", data=None, headers=None):
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_allowlisted_assets_match_for_get_and_head(self):
        photos = list((ROOT / "data" / "analyzed" / "photos").glob("*"))
        paths = ["/", "/index.html", "/sw.js", "/src/app.js", "/src/views/dashboard-view.js",
                 "/src/styles.css?v=10", "/assets/evidence/credits.json",
                 "/data/analyzed/issues.public.json", "/data/analyzed/report.json", "/data/analyzed/areas.json"]
        if photos:
            paths.append("/data/analyzed/photos/" + photos[0].name)
        for path in paths:
            status, body = self.request(path)
            head, head_body = self.request(path, method="HEAD")
            self.assertEqual(status, 200, path)
            self.assertEqual(head, 200, path)
            self.assertGreater(len(body), 0, path)
            self.assertEqual(head_body, b"", path)

    def test_private_paths_and_traversal_are_404(self):
        for path in ("/data/analyzed/issues.json", "/data/analyzed/sightings.json", "/.env",
                     "/scraping/.env", "/README.md", "/analysis/config.toml", "/src/",
                     "/data/analyzed/photos/", "/src/../.env", "/data/analyzed/photos/%2e%2e/issues.json",
                     "/src/%2e%2e/%2eenv", "/assets/evidence/../credits.json"):
            for method in ("GET", "HEAD"):
                status, body = self.request(path, method=method)
                self.assertEqual(status, 404, f"{method} {path}")
                self.assertNotIn(b"GEMINI_API_KEY", body)

    def test_symlink_and_published_dir_cannot_escape(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret = root / "secret.json"
            secret.write_text('{"private": "full-precision"}', encoding="utf-8")
            published = root / "published"
            generation = published / "generations" / "20261018T000000Z"
            (generation / "photos").mkdir(parents=True)
            (generation / "issues.public.json").write_text('[{"issue_id": "PUBLISHED"}]', encoding="utf-8")
            (generation / "issues.json").write_text('{"private": "full-precision"}', encoding="utf-8")
            (generation / "photos" / "ok.jpg").write_bytes(b"jpeg")
            (generation / "photos" / "leak.jpg").symlink_to(secret)
            (generation / "photos" / "via.jpg").symlink_to(Path("..") / "issues.json")
            (published / "current").symlink_to(Path("generations") / "20261018T000000Z", target_is_directory=True)
            os.environ["GEOISSUE_PUBLISHED_DIR"] = str(published)
            try:
                status, body = self.request("/data/analyzed/issues.public.json")
                self.assertEqual(status, 200)
                self.assertIn(b"PUBLISHED", body)
                photo, _ = self.request("/data/analyzed/photos/ok.jpg")
                self.assertEqual(photo, 200)
                for path in ("/data/analyzed/photos/leak.jpg", "/data/analyzed/photos/via.jpg",
                             "/data/analyzed/issues.json"):
                    status, body = self.request(path)
                    self.assertEqual(status, 404, path)
                    self.assertNotIn(b"full-precision", body)
                missing = root / "empty-published"
                missing.mkdir()
                os.environ["GEOISSUE_PUBLISHED_DIR"] = str(missing)
                status, _ = self.request("/data/analyzed/issues.public.json")
                self.assertEqual(status, 404)
            finally:
                os.environ.pop("GEOISSUE_PUBLISHED_DIR", None)

    def test_health_makes_no_upstream_call_and_status_hides_ingest_details(self):
        with patch.object(serve, "gemini", side_effect=AssertionError("gemini")), \
             patch.object(serve.tiger, "database_stats", side_effect=AssertionError("tiger")):
            status, body = self.request("/api/health")
        self.assertEqual((status, json.loads(body)), (200, {"ok": True}))
        status, body = self.request("/api/status")
        self.assertEqual(status, 200)
        self.assertIsNone(json.loads(body)["ingest"])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            published = Path(tmp)
            generation = published / "generations" / "20261018T000000Z"
            generation.mkdir(parents=True)
            (generation / "ingest-status.json").write_text(json.dumps({
                "last_success_at": "2026-10-18T04:15:00Z", "status": "ok", "issue_count": 3,
                "secret_path": "/etc/geoissue/env",
            }), encoding="utf-8")
            (published / "current").symlink_to(Path("generations") / "20261018T000000Z", target_is_directory=True)
            os.environ["GEOISSUE_PUBLISHED_DIR"] = str(published)
            try:
                _, body = self.request("/api/status")
            finally:
                os.environ.pop("GEOISSUE_PUBLISHED_DIR", None)
        payload = json.loads(body)
        self.assertEqual(payload["ingest"], {
            "last_success_at": "2026-10-18T04:15:00Z", "status": "ok", "issue_count": 3,
        })
        self.assertNotIn(b"secret_path", body)
        self.assertNotIn(b"/etc/geoissue", body)

    def test_gemini_concurrency_limit_returns_429_and_releases_the_slot(self):
        body = json.dumps({"image": base64.b64encode(b"img").decode(), "mime": "image/jpeg"}).encode()
        headers = {"Content-Type": "application/json"}
        sem = threading.BoundedSemaphore(1)
        self.assertTrue(sem.acquire(blocking=False))
        with patch.object(serve, "GEMINI_SLOTS", sem), patch.object(serve, "KEY", "test-key"), \
             patch.object(serve, "gemini", side_effect=AssertionError("called")):
            status, payload = self.request("/api/triage", method="POST", data=body, headers=headers)
        self.assertEqual(status, 429)
        self.assertIn(b"Too many", payload)
        with patch.object(serve, "KEY", "test-key"), patch.object(serve, "gemini", return_value=TRIAGE):
            first, _ = self.request("/api/triage", method="POST", data=body, headers=headers)
            second, _ = self.request("/api/triage", method="POST", data=body, headers=headers)
        self.assertEqual((first, second), (200, 200))


if __name__ == "__main__":
    unittest.main()
