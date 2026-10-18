"""Geolocate one photo with Claude Code running headless on this machine, driving the GeoIssue tools.

Claude Code runs with its built-in tools switched off and the user's settings, plugins and hooks not
loaded; its only tools come from geoloc_mcp.py (place, map and asset search, Mapillary matching, pose,
final_answer). It uses the local Claude Code login, so no API key is needed. The tools, not the model,
decide whether an answer is verified.

Every job is a folder: status.json (live progress, read by scripts/serve.py), events.jsonl (Claude Code's
stream), claude.err, the tool log, the reference contact sheets and result.json. A job can run in the
foreground or as a detached background process that outlives the web server; writing a file named
"cancel" into the folder stops it.

Usage (from research/geoloc_tests, with the tools' venv):
  .venv/Scripts/python claude_geoloc.py --image images/test1_utsc.png [--minutes 10]
      [--truth LAT,LON] [--model opus] [--effort high] [--job-dir DIR]
--truth only scores the answer after the run ends; it is never passed to Claude Code or its tools.
This module only uses the standard library, so the web server can import it on any Python.
"""
import argparse
import calendar
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).parent
JOBS = HERE / "results" / "claude_jobs"
APP_JOBS = HERE.parent.parent / "data" / "geolocate"  # where scripts/serve.py puts the app's jobs
QUEUE_DIRS = [JOBS, APP_JOBS]  # command-line and app jobs share one GPU, so they queue together
DOWNLOADS = HERE / "data" / "agent_mly"  # geoloc_mcp.py downloads each job's Mapillary images to DOWNLOADS/<job>
GRACE_S = 180  # after the tool budget: time to answer, or to finish a match already under way
HEARTBEAT_S, STALE_S, START_S = 5, 60, 120  # worker heartbeat period; dead after STALE_S silent or START_S unstarted
WINDOWS = os.name == "nt"
FINAL_STATES = ("done", "no_answer", "failed", "cancelled")

SYSTEM = """You are an OSINT geolocation analyst for GeoIssue, a Toronto civic-issue map. The photo was taken somewhere \
in the City of Toronto. Find where the camera was, ideally within 10 m. Locate the place, never the people in it.

Work deductively from what is visible. Do not assume a type of place in advance and do not pick a place from \
memory: coordinates must come from tool results, and only an accepted image match verifies a location.
1. Observe: call view_photo, and zoom into anything legible with a view_photo box. List text, transit, structures, \
street furniture, vegetation, terrain, and the viewpoint (street level, elevated, indoors).
2. Hypothesise: state several distinct explanations of what kind of site this could be, with the visual evidence \
for and against each.
3. Generate candidates for each hypothesis with tools, citywide: search_places (text only) and find_intersection \
for names; find_features_near for combinations of mapped features; search_assets for City street furniture; \
nearby_places to inspect what is around a coordinate. Make independent calls in the same turn.
4. Verify candidates with match_street_images (up to 4 points per call) and compare the reference images it \
returns with the photo. Only accepted=true (75 or more verified points) confirms a place. When a hypothesis fails, \
move on to the next one instead of refining the same guess.
5. If a match is accepted, call estimate_pose with its match_id, then final_answer with the pose position.
6. final_answer without an accepted match is refused until the last 2 minutes of the budget. Then give a radius \
that honestly covers your uncertainty and say what evidence is missing.
Every tool result ends with the time used. Image matching takes about a minute per call, so choose what to \
verify carefully."""

PROMPT = "Geolocate this photo. Your time budget is {minutes:g} minutes. Start with view_photo."


# ---------- job files ----------
def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_status(job_dir):
    path = Path(job_dir) / "status.json"
    for _ in range(5):  # the worker may be replacing the file this instant
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.05)
        except FileNotFoundError:
            return None
    return None


def write_status(job_dir, status):
    path = Path(job_dir) / "status.json"
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(status, indent=1, default=str), encoding="utf-8")
    for _ in range(20):  # on Windows a reader holding the file blocks the replace for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)


def start_heartbeat(job_dir):
    """Touch job_dir/heartbeat every few seconds until the returned event is set. A worker that stops beating
    (crash, kill, reboot) reads as dead, whatever has since taken its process id."""
    stop, beat = threading.Event(), Path(job_dir) / "heartbeat"

    def run():
        while not stop.is_set():
            beat.touch()
            stop.wait(HEARTBEAT_S)

    threading.Thread(target=run, daemon=True).start()
    return stop


def worker_alive(job_dir, status):
    beat = Path(job_dir) / "heartbeat"
    if beat.exists():
        return time.time() - beat.stat().st_mtime < STALE_S
    # not beating yet: a worker that was just started gets a moment to come up
    try:
        created = calendar.timegm(time.strptime(status.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return False
    return time.time() - created < START_S


def kill_tree(pid):
    """Claude Code, the MCP server and any match or download under it."""
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            pass


def detached():
    """Popen options for a process group of its own, with no console window, that survives its parent."""
    if WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def claude_bin():
    """The claude executable; CLAUDE_BIN overrides it (the tests point it at a fake)."""
    return shutil.which(os.environ.get("CLAUDE_BIN") or "claude")


def new_job(jobs_dir, image_bytes, suffix, minutes, model, effort):
    """Create a job folder holding the photo and a queued status; returns its path."""
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = Path(jobs_dir) / job_id
    job_dir.mkdir(parents=True)
    (job_dir / f"photo{suffix}").write_bytes(image_bytes)
    write_status(job_dir, {"id": job_id, "state": "queued", "created_at": now_iso(), "image": f"photo{suffix}",
                           "minutes": minutes, "model": model, "effort": effort, "steps": []})
    return job_dir


def start_background(job_dir, python=None, max_running=1, keep_downloads=False):
    """Run the job in a detached worker process; returns its pid."""
    status = read_status(job_dir)
    argv = [python or sys.executable, str(HERE / "claude_geoloc.py"), "--job-dir", str(job_dir),
            "--image", str(Path(job_dir) / status["image"]), "--minutes", str(status["minutes"]),
            "--model", status["model"], "--effort", status["effort"], "--max-running", str(max_running)]
    if keep_downloads:
        argv.append("--keep-downloads")
    with open(Path(job_dir) / "worker.log", "ab") as log:
        proc = subprocess.Popen(argv, cwd=HERE, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                **detached())
    return proc.pid


def request_cancel(job_dir):
    (Path(job_dir) / "cancel").touch()
    status = read_status(job_dir)
    # no live heartbeat: nothing else will write the status (a worker that starts later sees the cancel file)
    beating = (Path(job_dir) / "heartbeat").exists() and worker_alive(job_dir, status or {})
    if status and status["state"] not in FINAL_STATES and not beating:
        status.update(state="cancelled", finished_at=now_iso())
        write_status(job_dir, status)
    return status


def job_status(job_dir):
    """status.json, with a job whose worker stopped beating (crash, kill, reboot) reported as failed."""
    status = read_status(job_dir)
    if status and status["state"] not in FINAL_STATES and not worker_alive(job_dir, status):
        status.update(state="failed", error="the background worker stopped unexpectedly")
    if status:  # the reference contact sheets written so far: m1, m2, ...
        status["references"] = sorted((p.name.split("_")[0] for p in Path(job_dir).glob("m*_references.jpg")),
                                      key=lambda m: int(m[1:]) if m[1:].isdigit() else 0)
    return status


def list_jobs(jobs_dir, limit=20):
    dirs = sorted((d for d in Path(jobs_dir).glob("*") if (d / "status.json").exists()), reverse=True)
    return [s for s in (job_status(d) for d in dirs[:limit]) if s]


# ---------- progress from Claude Code's stream ----------
def short_name(tool):
    return tool.removeprefix("mcp__geoissue__")


def describe_step(tool, args):
    """A plain-language line for a tool call, shown in the app while the job runs."""
    a = args or {}
    pt = lambda: f"{float(a.get('lat', 0)):.4f}, {float(a.get('lon', 0)):.4f}"
    labels = {
        "view_photo": lambda: "Looked closer at part of the photo" if a.get("box") else "Looked at the photo",
        "search_places": lambda: f"Searched places for “{a.get('query', '')}”",
        "nearby_places": lambda: f"Listed places near {pt()}" + (f" ({a['category']})" if a.get("category") else ""),
        "find_intersection": lambda: f"Looked up {a.get('street_a', '')} & {a.get('street_b', '')}",
        "find_features_near": lambda: f"Searched the map for {a.get('b')} within {a.get('within_m')} m of {a.get('a')}",
        "search_assets": lambda: "Searched City street furniture: " + ", ".join(a.get("require") or []),
        "match_street_images": lambda: f"Compared the photo with street imagery at {len(a.get('points') or [])} "
                                       f"spot{'s' if len(a.get('points') or []) != 1 else ''}",
        "estimate_pose": lambda: "Estimated the camera position from the match",
        "final_answer": lambda: "Committed to an answer",
    }
    try:
        return labels[tool]()
    except (KeyError, TypeError, ValueError):
        return f"Used {tool}"


def describe_outcome(tool, text):
    """A few words about a tool result, or '' when there is nothing worth showing."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return (text or "")[:120]
    if tool in ("search_places", "nearby_places", "find_intersection"):
        if isinstance(data, list):
            first = data[0].get("name") or data[0].get("streets") if data else None
            return f"{len(data)} found" + (f", first: {first}" if first else "")
        return str(data)[:120]
    if tool == "find_features_near" and isinstance(data, dict):
        return f"{data.get('n_candidate_areas', 0)} candidate areas"
    if tool == "search_assets" and isinstance(data, dict):
        return f"{data.get('n_candidates', 0)} candidate places"
    if tool == "match_street_images" and isinstance(data, dict):
        if not data.get("match_id"):
            return data.get("note") or "no street imagery there"
        best = max((t.get("inliers", 0) for t in data.get("top") or []), default=0)
        verdict = "match accepted" if data.get("accepted") else "no match"
        return f"{verdict}: best {best} of {data.get('accept_threshold', 75)} points needed, " \
               f"{data.get('n_reference_images', 0)} images compared"
    if tool == "estimate_pose" and isinstance(data, dict):
        return f"position within {data['radius_m']:.0f} m" if data.get("ok") and data.get("radius_m") else "no pose"
    return ""


class Progress:
    """Folds Claude Code's stream-json events into status.json."""

    def __init__(self, job_dir, status):
        self.job_dir, self.status, self.t0 = job_dir, status, time.time()
        self.pending = {}  # tool_use id -> step
        self.last_write = 0.0

    def event(self, e):
        s = self.status
        if e.get("type") == "system" and e.get("subtype") == "init":
            s["session_id"] = e.get("session_id")
            s["model_id"] = e.get("model")
            servers = {m["name"]: m["status"] for m in e.get("mcp_servers") or []}
            if servers.get("geoissue") != "connected":
                s["error"] = f"the geolocation tools did not start ({servers.get('geoissue', 'missing')})"
        elif e.get("type") == "assistant":
            for block in e.get("message", {}).get("content") or []:
                if block.get("type") == "tool_use":
                    name = short_name(block.get("name", ""))
                    step = {"t": round(time.time() - self.t0, 1), "tool": name,
                            "label": describe_step(name, block.get("input")), "outcome": None}
                    s["steps"].append(step)
                    self.pending[block.get("id")] = step
                elif block.get("type") == "text" and block.get("text", "").strip():
                    s["note"] = block["text"].strip()[:600]
        elif e.get("type") == "user":
            for block in e.get("message", {}).get("content") or []:
                if block.get("type") != "tool_result" or block.get("tool_use_id") not in self.pending:
                    continue
                step = self.pending.pop(block["tool_use_id"])
                content = block.get("content")
                text = content if isinstance(content, str) else next(
                    (c.get("text", "") for c in content or [] if c.get("type") == "text"), "")
                step["outcome"] = describe_outcome(step["tool"], text)
                step["done_t"] = round(time.time() - self.t0, 1)
        elif e.get("type") == "result":
            s["usage"] = {"cost_usd": e.get("total_cost_usd"), "turns": e.get("num_turns"),
                          "duration_s": round((e.get("duration_ms") or 0) / 1000, 1)}
            if e.get("is_error") or e.get("subtype") != "success":
                # usage limits and login problems arrive here, with the message in "result"
                s["error"] = s.get("error") or str(e.get("result") or f"Claude Code ended with {e.get('subtype')}")[:300]
            elif e.get("result"):
                s["note"] = str(e["result"])[:600]
        # a tool call must show while it runs (a match takes minutes); only heartbeats such as
        # thinking-token counts are throttled
        self.flush(force=e.get("type") != "system" or e.get("subtype") == "init")

    def flush(self, force=False):
        if force or time.time() - self.last_write > 0.5:
            self.status["elapsed_s"] = round(time.time() - self.t0, 1)
            write_status(self.job_dir, self.status)
            self.last_write = time.time()


# ---------- the run ----------
def remove_downloads(job_dir):
    """Delete the Mapillary images a job downloaded: often hundreds of MB, and only needed while it runs. The
    contact sheets the app shows are already in the job folder. Windows may hold a file for a moment after the
    tools are killed, so this tries a few times."""
    folder = DOWNLOADS / Path(job_dir).name
    for _ in range(5):
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            return
        time.sleep(1)


def score(final, truth):
    """Distance from the true camera position, for test runs."""
    import math
    tlat, tlon = map(float, truth.split(","))
    error = 6371000 * math.hypot(math.radians(final["lat"] - tlat),
                                 math.radians(final["lon"] - tlon) * math.cos(math.radians(tlat)))
    return {"error_m": round(error, 1), "within_radius": error <= final["radius_m"]}


def wait_for_turn(job_dir, status, max_running):
    """Queue behind jobs running in the job's folder and in QUEUE_DIRS, so image matches don't share the GPU.
    Waiting jobs start in the order they were created. Returns False if the job was cancelled while it waited."""
    me = (status.get("created_at", ""), status["id"])
    folders = {Path(d).resolve() for d in [job_dir.parent, *QUEUE_DIRS] if Path(d).is_dir()}
    while not (job_dir / "cancel").exists():
        others = [s for d in folders for s in list_jobs(d, limit=50) if s["id"] != status["id"]]
        running = [s for s in others if s["state"] == "running"]
        ahead = [s for s in others if s["state"] == "queued" and (s.get("created_at", ""), s["id"]) < me]
        if len(running) + len(ahead) < max_running:
            return True
        waiting_for = sorted(s["id"] for s in running + ahead)
        if status.get("state") != "queued" or status.get("waiting_for") != waiting_for:
            status.update(state="queued", waiting_for=waiting_for)
            write_status(job_dir, status)
        time.sleep(2)
    return False


def claude_command(job_dir, model, effort, minutes):
    return [claude_bin(), "-p", PROMPT.format(minutes=minutes), "--model", model, "--effort", effort,
            "--output-format", "stream-json", "--verbose",
            "--system-prompt-file", str(job_dir / "system.md"),
            "--tools", "",                                   # no built-in tools: no shell, files or web
            "--mcp-config", str(job_dir / "mcp.json"), "--strict-mcp-config",
            "--allowedTools", "mcp__geoissue", "--permission-mode", "dontAsk",
            "--setting-sources", "",                         # no user hooks, plugins or permission rules
            "--no-session-persistence"]


def run(job_dir, image, minutes=10, model="opus", effort="high", truth=None, max_running=1, keep_downloads=False):
    job_dir = Path(job_dir).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    heartbeat = start_heartbeat(job_dir)
    try:
        return run_job(job_dir, image, minutes, model, effort, truth, max_running)
    finally:
        if not keep_downloads:  # done, failed, timed out or cancelled alike
            remove_downloads(job_dir)
        heartbeat.set()


def run_job(job_dir, image, minutes, model, effort, truth, max_running):
    status = read_status(job_dir) or {"id": job_dir.name, "created_at": now_iso(), "image": str(image),
                                      "minutes": minutes, "model": model, "effort": effort}
    status.update(worker_pid=os.getpid(), steps=[], error=None)
    if not wait_for_turn(job_dir, status, max_running):
        status.update(state="cancelled", finished_at=now_iso())
        write_status(job_dir, status)
        return status
    status.update(state="running", started_at=now_iso())
    status.pop("waiting_for", None)
    if not claude_bin():
        status.update(state="failed", error="Claude Code (the claude command) is not installed or not on PATH")
        write_status(job_dir, status)
        return status
    (job_dir / "system.md").write_text(SYSTEM, encoding="utf-8")
    server = [str(HERE / "geoloc_mcp.py"), "--image", str(Path(image).resolve()), "--out", str(job_dir),
              "--minutes", str(minutes), "--model", f"claude-code:{model}"]
    (job_dir / "mcp.json").write_text(json.dumps({"mcpServers": {"geoissue": {
        "type": "stdio", "command": sys.executable, "args": server}}}, indent=1), encoding="utf-8")
    (job_dir / "result.json").unlink(missing_ok=True)

    env = {**os.environ, "MCP_TOOL_TIMEOUT": "900000", "MCP_TIMEOUT": "60000"}
    progress = Progress(job_dir, status)
    with open(job_dir / "events.jsonl", "wb") as events, open(job_dir / "claude.err", "wb") as err:
        try:
            proc = subprocess.Popen(claude_command(job_dir, model, effort, minutes), cwd=job_dir, env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, **detached())
        except OSError as error:
            status.update(state="failed", error=f"Claude Code didn't start: {error}", finished_at=now_iso())
            progress.flush(force=True)
            return status
        status["claude_pid"] = proc.pid
        progress.flush(force=True)
        stop = {"why": None}

        def watchdog():  # the stream read below blocks, so deadlines and cancel are checked here
            deadline = time.time() + minutes * 60 + GRACE_S
            while proc.poll() is None:
                if (job_dir / "cancel").exists():
                    stop["why"] = "cancelled"
                elif time.time() > deadline:
                    stop["why"] = "timeout"
                if stop["why"]:
                    kill_tree(proc.pid)
                    return
                time.sleep(1)

        threading.Thread(target=watchdog, daemon=True).start()
        for line in proc.stdout:
            events.write(line)
            events.flush()
            try:
                progress.event(json.loads(line))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        proc.stdout.close()
        proc.wait()

    result_path = job_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
    status["result"] = result and {k: result.get(k) for k in ("final", "audit", "tool_calls", "tool_s")}
    if truth and result and result.get("final"):  # offline scoring, after Claude Code has exited
        status["result"].update(score(result["final"], truth))
    if result and result.get("final"):  # an answer committed before a cancel or timeout still stands
        status["state"] = "done"
    elif stop["why"] == "cancelled":
        status["state"] = "cancelled"
    elif stop["why"] == "timeout":
        status.update(state="no_answer", error=f"no answer within {minutes:g} minutes")
    elif status.get("error"):  # Claude Code reported it: usage limit, login, tools that didn't start
        status["state"] = "failed"
    elif proc.returncode:
        tail = (job_dir / "claude.err").read_text(encoding="utf-8", errors="replace").strip()[-300:]
        status.update(state="failed", error=f"Claude Code exited with code {proc.returncode}" + (f": {tail}" if tail else ""))
    else:
        status.update(state="no_answer", error="Claude ended without calling final_answer")
    status["finished_at"] = now_iso()
    progress.flush(force=True)
    return status


def main():
    ap = argparse.ArgumentParser(description="Geolocate a Toronto photo with Claude Code and the GeoIssue tools")
    ap.add_argument("--image", required=True)
    ap.add_argument("--minutes", type=float, default=10, help="tool budget; the run is stopped 3 min after it")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--truth", help="LAT,LON of the true camera position, to score the answer")
    ap.add_argument("--job-dir", help="default: results/claude_jobs/<time>-<photo>")
    ap.add_argument("--max-running", type=int, default=int(os.environ.get("GEOLOC_MAX_RUNNING", 1)),
                    help="jobs allowed to run at once across the app's and the command line's job folders")
    ap.add_argument("--keep-downloads", action="store_true", default=bool(os.environ.get("GEOLOC_KEEP_DOWNLOADS")),
                    help="keep the job's Mapillary images in data/agent_mly/<job> (deleted by default when it ends)")
    args = ap.parse_args()
    job_dir = Path(args.job_dir or JOBS / f"{time.strftime('%Y%m%d-%H%M%S')}-{Path(args.image).stem}")
    status = run(job_dir, args.image, args.minutes, args.model, args.effort, args.truth, args.max_running,
                 args.keep_downloads)
    print(json.dumps({k: status.get(k) for k in ("id", "state", "error", "elapsed_s", "usage", "result")},
                     indent=2, default=str))
    print(f"job folder: {job_dir}")


if __name__ == "__main__":
    main()
