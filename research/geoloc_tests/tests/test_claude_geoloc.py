"""Tests for the Claude Code geolocation runner and its MCP server, with a fake `claude` (no tokens spent).

Run from the repo root with the tools' Python:
  research/geoloc_tests/.venv/Scripts/python -m unittest discover -s research/geoloc_tests/tests -t research/geoloc_tests
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import claude_geoloc  # noqa: E402

FAKE = HERE / "fake_claude.py"


def fake_claude_bin(folder):
    """An executable that runs fake_claude.py, so Popen can start it like the real claude."""
    if os.name == "nt":
        path = Path(folder) / "fake_claude.cmd"
        path.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n')
    else:
        path = Path(folder) / "fake_claude"
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        path.chmod(0o755)
    return str(path)


class DescribeTest(unittest.TestCase):
    def test_step_labels_name_what_was_searched(self):
        self.assertEqual(claude_geoloc.describe_step("search_places", {"query": "Highland Hall"}),
                         "Searched places for “Highland Hall”")
        self.assertEqual(claude_geoloc.describe_step("match_street_images", {"points": [{}, {}]}),
                         "Compared the photo with street imagery at 2 spots")
        self.assertEqual(claude_geoloc.describe_step("view_photo", {"box": [0, 0, 10, 10]}),
                         "Looked closer at part of the photo")
        self.assertEqual(claude_geoloc.describe_step("mystery", {}), "Used mystery")

    def test_match_outcome_says_whether_it_was_accepted(self):
        result = {"match_id": "m1", "accepted": False, "accept_threshold": 75, "n_reference_images": 300,
                  "top": [{"inliers": 26}, {"inliers": 41}]}
        self.assertEqual(claude_geoloc.describe_outcome("match_street_images", json.dumps(result)),
                         "no match: best 41 of 75 points needed, 300 images compared")
        result.update(accepted=True)
        self.assertTrue(claude_geoloc.describe_outcome("match_street_images", json.dumps(result)).startswith("match accepted"))
        self.assertEqual(claude_geoloc.describe_outcome("search_places", "[]"), "0 found")
        self.assertEqual(claude_geoloc.describe_outcome("estimate_pose", json.dumps({"ok": True, "radius_m": 7.5})),
                         "position within 8 m")


class ProgressTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows: a just-killed process may still hold it
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_stream_events_become_steps_with_outcomes(self):
        status = {"id": "j", "steps": []}
        progress = claude_geoloc.Progress(self.dir, status)
        progress.event({"type": "system", "subtype": "init", "session_id": "s", "model": "m",
                        "mcp_servers": [{"name": "geoissue", "status": "connected"}]})
        progress.event({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "mcp__geoissue__find_intersection",
             "input": {"street_a": "Bathurst", "street_b": "Dundas"}}]}})
        progress.event({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a",
            "content": [{"type": "text", "text": json.dumps([{"streets": "Bathurst & Dundas", "lat": 1, "lon": 2}])}]}]}})
        progress.event({"type": "result", "subtype": "success", "total_cost_usd": 0.1, "num_turns": 2,
                        "duration_ms": 5000, "result": "done"})
        self.assertEqual(status["steps"][0]["label"], "Looked up Bathurst & Dundas")
        self.assertEqual(status["steps"][0]["outcome"], "1 found, first: Bathurst & Dundas")
        self.assertEqual(status["usage"], {"cost_usd": 0.1, "turns": 2, "duration_s": 5.0})
        self.assertIsNone(status.get("error"))
        self.assertEqual(claude_geoloc.read_status(self.dir)["steps"][0]["tool"], "find_intersection")

    def test_tools_that_failed_to_start_are_reported(self):
        status = {"steps": []}
        claude_geoloc.Progress(self.dir, status).event({"type": "system", "subtype": "init",
                                                        "mcp_servers": [{"name": "geoissue", "status": "failed"}]})
        self.assertIn("did not start (failed)", status["error"])


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows: a just-killed process may still hold it
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.image = self.tmp / "photo.jpg"
        self.image.write_bytes(b"not really a jpeg")
        for patch in (mock.patch.dict(os.environ, {"CLAUDE_BIN": fake_claude_bin(self.tmp), "FAKE_CLAUDE_MODE": "ok"}),
                      mock.patch.object(claude_geoloc, "QUEUE_DIRS", []),  # don't queue behind real jobs
                      mock.patch.object(claude_geoloc, "DOWNLOADS", self.tmp / "downloads")):
            patch.start()
            self.addCleanup(patch.stop)

    def run_job(self, name="job", **kwargs):
        return claude_geoloc.run(self.tmp / "jobs" / name, self.image, **{"minutes": 1, **kwargs})

    def test_a_finished_run_records_the_answer_and_its_steps(self):
        status = self.run_job()
        self.assertEqual(status["state"], "done")
        self.assertTrue(status["result"]["final"]["verified"])
        self.assertEqual([s["tool"] for s in status["steps"]], ["search_places", "final_answer"])
        self.assertEqual(status["note"], "It is at UTSC.")
        saved = claude_geoloc.read_status(self.tmp / "jobs" / "job")
        self.assertEqual(saved["state"], "done")
        self.assertTrue((self.tmp / "jobs" / "job" / "events.jsonl").read_text().count("\n") >= 6)
        command = claude_geoloc.claude_command(self.tmp, "opus", "high", 10)
        self.assertEqual(command[command.index("--tools") + 1], "")  # no built-in tools

    def downloaded(self, name="job"):
        """Stand-in Mapillary images, where geoloc_mcp.py would have downloaded them for this job."""
        folder = claude_geoloc.DOWNLOADS / name / "m1_p0"
        folder.mkdir(parents=True)
        (folder / "123.jpg").write_bytes(b"jpeg")
        return folder.parent

    def test_a_job_deletes_its_downloads_when_it_ends(self):
        folder = self.downloaded()
        self.assertEqual(self.run_job()["state"], "done")
        self.assertFalse(folder.exists())
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        folder = self.downloaded("failed")
        self.run_job("failed")
        self.assertFalse(folder.exists())

    def test_downloads_can_be_kept_for_debugging(self):
        folder = self.downloaded()
        self.run_job(keep_downloads=True)
        self.assertTrue((folder / "m1_p0" / "123.jpg").exists())

    def test_claude_failing_gives_a_failed_job_with_its_message(self):
        os.environ["FAKE_CLAUDE_MODE"] = "fail"
        status = self.run_job()
        self.assertEqual(status["state"], "failed")
        self.assertIn("Invalid API key", status["error"])

    def test_an_error_result_such_as_a_usage_limit_is_shown(self):
        os.environ["FAKE_CLAUDE_MODE"] = "limit"
        status = self.run_job()
        self.assertEqual((status["state"], status["error"]), ("failed", "Claude usage limit reached"))

    def test_missing_claude_is_a_clear_failure(self):
        os.environ["CLAUDE_BIN"] = str(self.tmp / "nowhere" / "claude")
        status = self.run_job()
        self.assertEqual(status["state"], "failed")
        self.assertIn("not installed", status["error"])

    def test_cancel_stops_a_running_job(self):
        os.environ["FAKE_CLAUDE_MODE"] = "slow"
        job = self.tmp / "jobs" / "job"
        threading.Timer(3, lambda: (job / "cancel").touch()).start()
        t = time.time()
        status = self.run_job()
        self.assertEqual(status["state"], "cancelled")
        self.assertLess(time.time() - t, 20)

    def test_a_run_past_its_budget_is_stopped(self):
        os.environ["FAKE_CLAUDE_MODE"] = "slow"
        with mock.patch.object(claude_geoloc, "GRACE_S", 1):
            status = self.run_job(minutes=0.02)
        self.assertEqual(status["state"], "no_answer")
        self.assertIn("no answer within", status["error"])

    def test_jobs_queue_behind_a_running_job(self):
        jobs = self.tmp / "jobs"
        busy = jobs / "a-busy"
        busy.mkdir(parents=True)
        claude_geoloc.write_status(busy, {"id": "a-busy", "state": "running", "steps": []})
        (busy / "heartbeat").touch()
        seen = []
        worker = threading.Thread(target=lambda: seen.append(self.run_job("b-next")))
        worker.start()
        time.sleep(3)
        self.assertEqual(claude_geoloc.read_status(jobs / "b-next")["state"], "queued")
        claude_geoloc.write_status(busy, {"id": "a-busy", "state": "done", "steps": []})
        worker.join(30)
        self.assertEqual(seen[0]["state"], "done")

    def test_waiting_jobs_start_one_at_a_time_in_order(self):
        jobs = self.tmp / "jobs"
        busy = jobs / "a-busy"
        busy.mkdir(parents=True)
        claude_geoloc.write_status(busy, {"id": "a-busy", "state": "running", "steps": []})
        (busy / "heartbeat").touch()
        for name in ("b-first", "c-second"):
            (jobs / name).mkdir()
            claude_geoloc.write_status(jobs / name, {"id": name, "created_at": f"2026-10-18T00:00:0{name[0] == 'c'}Z",
                                                     "state": "queued", "minutes": 1, "model": "opus",
                                                     "effort": "high", "image": str(self.image), "steps": []})
            (jobs / name / "heartbeat").touch()  # as if their workers were already up
        workers = [threading.Thread(target=self.run_job, args=(name,)) for name in ("c-second", "b-first")]
        for w in workers:
            w.start()
        time.sleep(3)
        claude_geoloc.write_status(busy, {"id": "a-busy", "state": "done", "steps": []})
        for w in workers:
            w.join(60)
        first, second = (claude_geoloc.read_status(jobs / n) for n in ("b-first", "c-second"))
        self.assertEqual((first["state"], second["state"]), ("done", "done"))
        self.assertLessEqual(first["finished_at"], second["started_at"])

    def test_liveness_follows_the_heartbeat_not_the_process_id(self):
        job = self.tmp / "jobs" / "j"
        job.mkdir(parents=True)
        # the pid of a live process (this one) must not keep a silent worker "running": pids get reused
        claude_geoloc.write_status(job, {"id": "j", "state": "running", "worker_pid": os.getpid(),
                                         "created_at": "2026-01-01T00:00:00Z", "steps": []})
        beat = job / "heartbeat"
        beat.touch()
        self.assertEqual(claude_geoloc.job_status(job)["state"], "running")
        old = time.time() - claude_geoloc.STALE_S - 5
        os.utime(beat, (old, old))
        self.assertEqual(claude_geoloc.job_status(job)["state"], "failed")
        self.assertEqual(claude_geoloc.request_cancel(job)["state"], "cancelled")

    def test_a_job_whose_worker_never_started_reads_as_failed_after_a_while(self):
        job = self.tmp / "jobs" / "j"
        job.mkdir(parents=True)
        claude_geoloc.write_status(job, {"id": "j", "state": "queued", "created_at": claude_geoloc.now_iso(), "steps": []})
        self.assertEqual(claude_geoloc.job_status(job)["state"], "queued")
        claude_geoloc.write_status(job, {"id": "j", "state": "queued", "created_at": "2026-01-01T00:00:00Z", "steps": []})
        self.assertEqual(claude_geoloc.job_status(job)["state"], "failed")

    def test_a_finished_run_stops_its_heartbeat(self):
        self.run_job()
        beat = self.tmp / "jobs" / "job" / "heartbeat"
        time.sleep(0.3)
        before = beat.stat().st_mtime
        time.sleep(claude_geoloc.HEARTBEAT_S + 1)
        self.assertEqual(beat.stat().st_mtime, before)


class McpServerTest(unittest.TestCase):
    """The JSON-RPC loop with a stand-in host, and the real tool host on a generated photo."""

    @classmethod
    def setUpClass(cls):
        try:
            import geoloc_mcp
        except ImportError as error:  # PIL or DuckDB missing: not the tools' Python
            raise unittest.SkipTest(f"geoloc_mcp needs the tools' Python: {error}")
        cls.mcp = geoloc_mcp

    def serve(self, host, *messages):
        out = io.BytesIO()
        self.mcp.serve(host, io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n"), out)
        return [json.loads(line) for line in out.getvalue().decode().splitlines()]

    def test_protocol_handshake_listing_and_errors(self):
        host = mock.Mock()
        host.mcp_call.side_effect = [{"content": [{"type": "text", "text": "ok"}], "isError": False}, RuntimeError("boom")]
        replies = self.serve(host,
                             {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                             {"jsonrpc": "2.0", "method": "notifications/initialized"},
                             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                             {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_places", "arguments": {"query": "x"}}},
                             {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_places"}},
                             {"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])  # the notification got no reply
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        names = [t["name"] for t in replies[1]["result"]["tools"]]
        self.assertIn("view_photo", names)
        self.assertIn("final_answer", names)
        self.assertEqual(replies[2]["result"]["content"][0]["text"], "ok")
        self.assertEqual(replies[3]["error"]["code"], -32603)
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_tool_host_zooms_enforces_the_budget_and_widens_unverified_answers(self):
        if not (HERE.parent / "data" / "places.duckdb").is_file():
            self.skipTest("needs data/places.duckdb")
        from PIL import Image
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            photo = Path(tmp) / "p.jpg"
            Image.new("RGB", (4000, 3000), "gray").save(photo)
            args = mock.Mock(image=str(photo), out=str(Path(tmp) / "job"), minutes=5, truth=None,
                             model="test", run_name=None)
            host = self.mcp.ToolHost(args)
            try:
                crop = host.mcp_call("view_photo", {"box": [0, 0, 100, 100]})
                self.assertEqual([c["type"] for c in crop["content"]], ["text", "image", "text"])
                self.assertIn("400x300", crop["content"][0]["text"])
                host.deadline = time.time() - 1
                late = host.mcp_call("search_places", {"query": "Union Station"})
                self.assertTrue(late["isError"])
                self.assertIn("Time is up", late["content"][0]["text"])
                answer = host.mcp_call("final_answer", {"lat": 43.6, "lon": -79.4, "radius_m": 20, "confidence": 0.9,
                                                        "evidence": "a guess"})
                self.assertIn("NOT verified", answer["content"][0]["text"])
                result = json.loads((Path(tmp) / "job" / "result.json").read_text())
                self.assertEqual((result["final"]["radius_m"], result["final"]["confidence"]), (1000, 0.3))
            finally:
                host.places_con.close()
                host.log_f.close()


if __name__ == "__main__":
    unittest.main()
