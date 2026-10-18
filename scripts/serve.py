"""Local dev server: serves the app plus a small Gemini API, so the key stays on this machine.

Usage:  python scripts/serve.py            (http://127.0.0.1:5173, loopback only)
        python scripts/serve.py --port 8000

The key is read like the analysis pipeline reads it: GEMINI_API_KEY from the environment, else from
.env or spikes/.env in the repo root. GEMINI_MODEL overrides the model (default: the summaries model in
analysis/config.toml). GEMINI_API_BASE overrides the endpoint (used by tests).

Static files are an allowlist: the entry page, sw.js, frontend scripts and styles, credited evidence
assets, and the public analysis snapshot (issues.public.json, report.json, areas.json, photos/).
When GEOISSUE_PUBLISHED_DIR is set, /data/analyzed/* is read from $GEOISSUE_PUBLISHED_DIR/current
instead of the repository. Everything else, including raw batches and full-precision JSON, is 404.

Endpoints
  GET  /api/health  -> {"ok": true} with no upstream calls
  GET  /api/status  -> {"gemini": bool, "model": str, "tiger": bool, "ingest": object | null}
  GET  /api/issues, /api/pipeline, /api/activity, /api/tiger -> optional Tiger Data snapshots, history and storage metrics
  POST /api/triage  {"image": base64, "mime": "image/jpeg"}
                    -> suggested category, severity and description, privacy flags, and face/plate boxes
                       ([ymin, xmin, ymax, xmax], 0–1000) for blurring
  POST /api/digest  {"area": {...areas.json-style stats}, "label": "ward"} -> {"text", "method"}

Issues people submit are stored in Tiger Data with their photos as submitted (analysis/submissions.py):
  POST /api/submissions                  {category, severity, description, address, coordinates | location_status
                                          "locating", geolocation, photos: [{image: base64, mime}], ...}
                                          -> 201 {submission_id, token, location_status, issue}
  POST /api/submissions/<id>/location    {token, location_status, coordinates, geolocation}: Claude's answer for a
                                          submission sent while it was still locating -> {issue}; 409 once located
  GET  /api/submissions/<id>/photos/<n>  a published submission's photo

Photo geolocation with Claude Code (research/geoloc_tests/claude_geoloc.py) runs as a background job on
this machine, using the local Claude Code login, so it keeps going if the page or this server closes:
  POST /api/geolocate               {"image": base64, "mime"} -> the new job's status
  GET  /api/geolocate               -> {"jobs": [...]}, newest first
  GET  /api/geolocate/<id>          -> status: state, steps so far, result
  GET  /api/geolocate/<id>/photo    and /<id>/references/<m1>  -> the photo and the reference contact sheets
  POST /api/geolocate/<id>/cancel
GEOLOC_PYTHON is the Python with the vision tools installed (default: research/geoloc_tests/.venv, then .venv in
the repo root); GEOLOC_MODEL (default opus), GEOLOC_EFFORT (high), GEOLOC_MINUTES (10) and GEOLOC_MAX_RUNNING (1)
tune it; a job's Mapillary downloads are deleted when it ends unless GEOLOC_KEEP_DOWNLOADS is set. Only this app may use these endpoints (Host and Origin are checked, POSTs must be JSON), at most 5 jobs
run or wait at once, and the job folders (data/geolocate/) are not on the static allowlist.
A hosted copy of the app (GEOISSUE_CLAUDE_ORIGINS, default https://geoissue.photo) may also use them from the
visitor's browser, once the visitor turns on Settings -> Claude on this computer. Requests must still arrive on this
computer's loopback address, so each person's runs use their own Claude Code login.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import threading
import tomllib
from datetime import datetime, timezone
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis.stages import summaries  # noqa: E402  (shared key lookup and digest prompt)
from analysis import submissions, tiger
from analysis.config import setting
GEOLOC = ROOT / "research" / "geoloc_tests"
sys.path.insert(0, str(GEOLOC))
import claude_geoloc  # noqa: E402  (standard library only: job files and the background worker)

CATEGORIES = ["Pothole", "Sidewalk damage", "Graffiti", "Litter", "Flooding", "Other"]
MAX_BODY = 12 * 1024 * 1024
ENV_FILES = [".env", "spikes/.env"]
# Hosted copies of the app allowed to use this computer's Claude from the visitor's browser (see the docstring).
CLAUDE_ORIGINS = {o.strip() for o in setting("GEOISSUE_CLAUDE_ORIGINS", "https://geoissue.photo").split(",") if o.strip()}
SUBMISSION_ID = r"SUB-[0-9A-F]{10}"


def default_model():
    try:
        with open(ROOT / "analysis" / "config.toml", "rb") as f:
            return tomllib.load(f)["stages"]["summaries"]["model"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "gemini-3.5-flash-lite"


KEY = summaries.api_key(ENV_FILES)
MODEL = setting("GEMINI_MODEL", default_model())
API_BASE = setting("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
digest_cache = {}
GEMINI_SLOTS = threading.BoundedSemaphore(4)
PUBLIC_ANALYSIS = {"issues.public.json", "report.json", "areas.json"}
INGEST_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

TRIAGE_PROMPT = f"""You review photos submitted to GeoIssue, a Toronto civic-issue map. Look at the photo and answer in JSON.
- is_civic_issue: does it clearly show a problem in a public space that a city would fix?
- category: one of {", ".join(CATEGORIES)}. Pothole = road surface holes or broken asphalt. Sidewalk damage = cracked,
  heaved or broken sidewalks, curbs or ramps. Graffiti = tags or paint on public or private surfaces. Litter = trash,
  overflowing bins or dumping. Flooding = standing water, blocked drains. Other = anything else (streetlights, signs,
  fallen trees, damaged shelters).
- severity: High (hazard to people or vehicles, or blocking access), Medium (needs repair soon), Low (cosmetic).
- description: one factual sentence of at most 20 words about the problem only. Never describe people.
- confidence: 0 to 1, how sure you are about category and severity.
- public_scene: false if the photo shows a private interior or a private home's yard up close.
- person_is_subject: true if a person is the main subject (a selfie, portrait or group photo).
- faces and plates: bounding boxes [ymin, xmin, ymax, xmax] scaled 0-1000 for EVERY human face and EVERY vehicle
  licence plate visible, however small or partly hidden. Empty lists if none.
- reason: under 15 words explaining the category choice."""

BOXES = {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "INTEGER"}}}
TRIAGE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_civic_issue": {"type": "BOOLEAN"}, "category": {"type": "STRING", "enum": CATEGORIES},
        "severity": {"type": "STRING", "enum": ["High", "Medium", "Low"]}, "description": {"type": "STRING"},
        "confidence": {"type": "NUMBER"}, "public_scene": {"type": "BOOLEAN"}, "person_is_subject": {"type": "BOOLEAN"},
        "faces": BOXES, "plates": BOXES, "reason": {"type": "STRING"},
    },
    "required": ["is_civic_issue", "category", "severity", "description", "confidence", "public_scene", "person_is_subject", "faces", "plates"],
}


def gemini(parts, generation_config, timeout=45):
    request = urllib.request.Request(
        f"{API_BASE}/models/{MODEL}:generateContent",
        data=json.dumps({"contents": [{"role": "user", "parts": parts}], "generationConfig": generation_config}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"] if not p.get("thought")).strip()
    if not text:
        raise ValueError("empty response")
    return text


def clean_boxes(boxes):
    out = []
    for box in boxes or []:
        if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
            y0, x0, y1, x1 = (max(0, min(1000, int(v))) for v in box)
            if y1 > y0 and x1 > x0:
                out.append([y0, x0, y1, x1])
    return out


def triage(body):
    image, mime = body.get("image"), body.get("mime", "image/jpeg")
    if not image or mime not in ("image/jpeg", "image/png", "image/webp"):
        raise ValueError("send a base64 JPEG, PNG or WebP image")
    base64.b64decode(image, validate=True)  # reject anything that isn't base64
    result = json.loads(gemini(
        [{"inline_data": {"mime_type": mime, "data": image}}, {"text": TRIAGE_PROMPT}],
        {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": TRIAGE_SCHEMA},
    ))
    return {
        "is_civic_issue": bool(result.get("is_civic_issue")),
        "category": result.get("category") if result.get("category") in CATEGORIES else "Other",
        "severity": result.get("severity") if result.get("severity") in ("High", "Medium", "Low") else "Medium",
        "description": str(result.get("description", ""))[:200],
        "confidence": max(0.0, min(1.0, float(result.get("confidence") or 0))),
        "public_scene": bool(result.get("public_scene", True)),
        "person_is_subject": bool(result.get("person_is_subject")),
        "faces": clean_boxes(result.get("faces")), "plates": clean_boxes(result.get("plates")),
        "reason": str(result.get("reason", ""))[:160], "model": MODEL,
    }


def digest(body):
    area, label = body.get("area") or {}, body.get("label", "ward")
    for field in ("name", "total", "open", "by_type", "new_recent", "new_previous"):
        if field not in area:
            raise ValueError(f"area.{field} is required")
    prompt = summaries.build_prompt(area, label, 90, False, int(body.get("trend_days", 7)))
    key = hashlib.sha256(f"{MODEL}\n{prompt}".encode()).hexdigest()
    if key not in digest_cache:
        digest_cache[key] = gemini([{"text": prompt}], {"temperature": 0.2})
    return {"text": digest_cache[key], "method": f"gemini:{MODEL}"}


# ---- Submitted issues, stored in Tiger Data ----
def create_submission(body):
    cfg = submissions.config()
    submission, photos = submissions.parse(body, cfg)
    submission_id, token = submissions.new_ids()
    now = datetime.now(timezone.utc)
    located = submission["location_status"] != "locating"
    issue = submissions.build_issue(submission_id, submission, now, len(photos), cfg, now) if located else None
    tiger.add_submission(submission_id, submissions.token_hash(token), submission, photos, issue)
    return {"submission_id": submission_id, "token": token, "location_status": submission["location_status"], "issue": issue}


def locate_submission(submission_id, body):
    """Claude's answer for a submission sent while it was still locating; only its own browser has the token."""
    stored = tiger.submission(submission_id)
    if not stored:
        raise LookupError("no such submission")
    submission, token_sha256, created_at, status, photo_count = stored
    if not submissions.token_matches(body.get("token"), token_sha256):
        raise PermissionError("only the browser that sent this submission can add its location")
    if status != "locating":
        raise FileExistsError("this submission already has its location")
    cfg = submissions.config()
    status, coordinates, claude = submissions.location(body, cfg)
    if status not in ("located", "unverified", "not_found"):
        raise ValueError("send how Claude's run ended: located, unverified or not_found")
    claude = {**(submission.get("geolocation") or {}), **(claude or {})}
    submission = {**submission, "location_status": status, "coordinates": coordinates, "geolocation": claude,
                  "address": submission["address"] or (claude.get("place_description") or "")[:200]}
    issue = submissions.build_issue(submission_id, submission, created_at, photo_count, cfg) if coordinates else None
    if not tiger.locate_submission(submission_id, submission, issue):
        raise FileExistsError("this submission already has its location")
    return {"submission_id": submission_id, "location_status": status, "issue": issue}


# ---- Photo geolocation with Claude Code ----
GEOLOC_JOBS = ROOT / "data" / "geolocate"
VENV_PYTHON = "Scripts/python.exe" if os.name == "nt" else "bin/python"
GEOLOC_PYTHON = Path(setting("GEOLOC_PYTHON", next(
    (p for p in (GEOLOC / ".venv" / VENV_PYTHON, ROOT / ".venv" / VENV_PYTHON) if p.is_file()), GEOLOC / ".venv" / VENV_PYTHON)))
GEOLOC_MODEL = setting("GEOLOC_MODEL", "opus")
GEOLOC_EFFORT = setting("GEOLOC_EFFORT", "high")
GEOLOC_MINUTES = float(setting("GEOLOC_MINUTES", 10))
GEOLOC_MAX_RUNNING = int(setting("GEOLOC_MAX_RUNNING", 1))
GEOLOC_KEEP_DOWNLOADS = bool(setting("GEOLOC_KEEP_DOWNLOADS"))  # keep each job's Mapillary images (debugging)
GEOLOC_MAX_ACTIVE = 5  # running or waiting; more are refused, so nothing can pile up Opus runs
JOB_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def geolocate_status():
    """Whether this machine can run a geolocation job, and if not, what is missing."""
    missing = [label for label, ok in (
        ("Claude Code (the claude command)", claude_geoloc.claude_bin()),
        (f"the vision tools' Python ({GEOLOC_PYTHON}; set GEOLOC_PYTHON)", GEOLOC_PYTHON.is_file()),
        ("the place index (research/geoloc_tests/data/places.duckdb)", (GEOLOC / "data" / "places.duckdb").is_file()),
    ) if not ok]
    return {"available": not missing, "model": GEOLOC_MODEL, "minutes": GEOLOC_MINUTES,
            "missing": missing, "street_imagery": (GEOLOC / ".env").is_file()}


def job_dir(job_id):
    if not JOB_ID.match(job_id or "") or not (GEOLOC_JOBS / job_id / "status.json").is_file():
        raise LookupError("no such geolocation job")
    return GEOLOC_JOBS / job_id


def start_geolocation(body):
    status = geolocate_status()
    if not status["available"]:
        raise PermissionError("Geolocation needs " + " and ".join(status["missing"]))
    image, mime = body.get("image"), body.get("mime", "image/jpeg")
    if not image or mime not in SUFFIX:
        raise ValueError("send a base64 JPEG, PNG or WebP image")
    photo = base64.b64decode(image, validate=True)
    active = [j for j in claude_geoloc.list_jobs(GEOLOC_JOBS, 50) if j["state"] not in claude_geoloc.FINAL_STATES]
    if len(active) >= GEOLOC_MAX_ACTIVE:
        raise OverflowError(f"{len(active)} photos are already being located. Wait for one to finish.")
    job = claude_geoloc.new_job(GEOLOC_JOBS, photo, SUFFIX[mime], GEOLOC_MINUTES, GEOLOC_MODEL, GEOLOC_EFFORT)
    try:
        claude_geoloc.start_background(job, python=str(GEOLOC_PYTHON), max_running=GEOLOC_MAX_RUNNING,
                                       keep_downloads=GEOLOC_KEEP_DOWNLOADS)
    except OSError as error:  # the job must not sit "queued" in front of later ones
        status = claude_geoloc.read_status(job)
        status.update(state="failed", error=f"couldn't start the background worker: {error}",
                      finished_at=claude_geoloc.now_iso())
        claude_geoloc.write_status(job, status)
    return claude_geoloc.job_status(job)


def normalized_path(raw):
    """Collapse a URL path, rejecting traversal, encoded dots and hidden names."""
    path = unquote(raw)
    if "\x00" in path or "\\" in path or not path.startswith("/"):
        return None
    parts = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or part.startswith("."):
            return None
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def repo_file(path):
    """Allowlisted repository file, or None. Symlinks must still land on an allowlisted path."""
    if path in ("/", "/index.html"):
        relative = "index.html"
    elif path == "/sw.js":
        relative = "sw.js"
    elif path.startswith("/src/") and path.endswith((".js", ".css")):
        relative = path[1:]
    elif path.startswith("/assets/evidence/"):
        relative = path[1:]
        if relative.count("/") != 2:
            return None
    else:
        return None
    return contained_file(ROOT, relative)


def published_dir():
    raw = os.environ.get("GEOISSUE_PUBLISHED_DIR")
    return Path(raw) if raw else None


def analysis_file(path):
    """Public analysis snapshot. A published directory replaces the repository copy."""
    prefix = "/data/analyzed/"
    if not path.startswith(prefix):
        return None
    relative = path[len(prefix):]
    if relative not in PUBLIC_ANALYSIS and not (relative.startswith("photos/") and relative.count("/") == 1):
        return None
    name = relative.removeprefix("photos/")
    if relative.startswith("photos/") and (not name or name.startswith(".")):
        return None
    root = published_dir()
    base = root / "current" if root is not None else ROOT / "data" / "analyzed"
    try:
        if root is not None and not base.resolve().is_relative_to(root.resolve()):
            return None
    except OSError:
        return None
    return contained_file(base, relative)


def contained_file(root, relative):
    """Resolve root/relative and accept it only when the real path is still allowlisted."""
    try:
        root = root.resolve()
        target = (root / relative).resolve()
        landed = target.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    if landed in ("index.html", "sw.js") or landed in PUBLIC_ANALYSIS:
        allowed = True
    elif landed.startswith("src/") and landed.endswith((".js", ".css")) and not any(part.startswith(".") for part in landed.split("/")):
        allowed = True
    elif landed.startswith("assets/evidence/") and landed.count("/") == 2 and not landed.split("/")[-1].startswith("."):
        allowed = True
    elif landed.startswith("photos/") and landed.count("/") == 1 and not landed.split("/")[-1].startswith("."):
        allowed = True
    else:
        allowed = False
    return target if allowed and target.is_file() else None


def ingest_status():
    """Sanitized last success from the published snapshot. Missing or unexpected data is null."""
    root = published_dir()
    if root is None:
        return None
    try:
        base = root.resolve()
        path = (base / "current" / "ingest-status.json").resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    stamp, status, count = data.get("last_success_at"), data.get("status"), data.get("issue_count")
    if not (isinstance(stamp, str) and INGEST_STAMP.fullmatch(stamp) and status == "ok" and type(count) is int and count >= 0):
        return None
    return {"last_success_at": stamp, "status": "ok", "issue_count": count}


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        origin = self.claude_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def local_hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def claude_origin(self):
        """The hosted app's origin when it is asking this computer's Claude to locate photos, else None."""
        origin, path = self.headers.get("Origin"), urlsplit(self.path).path
        if origin in CLAUDE_ORIGINS and self.headers.get("Host") in self.local_hosts() and (
                path == "/api/status" or path == "/api/geolocate" or path.startswith("/api/geolocate/")):
            return origin
        return None

    def do_OPTIONS(self):
        """CORS preflight for the hosted app. Allow-Private-Network answers Chrome's local-network check."""
        if not self.claude_origin():
            return self.send_json(403, {"error": "not allowed"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_bytes(self, mime, body):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, target):
        try:
            body = target.read_bytes()
        except OSError:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(target)))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def same_origin(self):
        """Geolocation calls must come from this app on this computer, served here or hosted (CLAUDE_ORIGINS): a run
        uses the local Claude Code login. The Host check stops DNS rebinding; the Origin check stops other sites
        posting here (a no-cors POST with a text/plain body needs no preflight)."""
        hosts = self.local_hosts()
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (origin is None or origin in {f"http://{h}" for h in hosts} or origin in CLAUDE_ORIGINS)

    def submissions_post(self, path):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            return self.send_json(413, {"error": f"A submission is limited to {MAX_BODY // (1024 * 1024)} MB. Use fewer or smaller photos."})
        body = self.rfile.read(length)
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_json(415, {"error": "send the submission as JSON"})
        update = re.fullmatch(rf"/api/submissions/({SUBMISSION_ID})/location", path)
        if path != "/api/submissions" and not update:
            return self.send_json(404, {"error": "not found"})
        try:
            data = json.loads(body)
            if update:
                return self.send_json(200, locate_submission(update.group(1), data))
            return self.send_json(201, create_submission(data))
        except LookupError as error:
            return self.send_json(404, {"error": str(error)})
        except PermissionError as error:
            return self.send_json(403, {"error": str(error)})
        except FileExistsError as error:
            return self.send_json(409, {"error": str(error)})
        except (ValueError, TypeError, AttributeError) as error:
            return self.send_json(400, {"error": str(error)})
        except tiger.Unavailable as error:
            return self.send_json(503, {"error": str(error)})
        except Exception:
            return self.send_json(503, {"error": "Tiger Data is unavailable, so the submission wasn't saved. Try again shortly."})

    def geolocate_get(self, parts):
        if not parts:
            return self.send_json(200, {"jobs": claude_geoloc.list_jobs(GEOLOC_JOBS)})
        try:
            folder = job_dir(parts[0])
        except LookupError as error:
            return self.send_json(404, {"error": str(error)})
        if len(parts) == 1:
            return self.send_json(200, claude_geoloc.job_status(folder))
        if parts[1:] == ["photo"]:
            return self.send_file(folder / claude_geoloc.read_status(folder)["image"])
        if len(parts) == 3 and parts[1] == "references" and re.fullmatch(r"m\d{1,3}", parts[2]):
            sheet = folder / f"{parts[2]}_references.jpg"
            if sheet.is_file():
                return self.send_file(sheet)
        return self.send_json(404, {"error": "not found"})

    def geolocate_post(self, path):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 <= length <= MAX_BODY:
            return self.send_json(413, {"error": "request body too large"})
        # read the body before any answer: refusing with it unread can reset the connection on Windows
        body = self.rfile.read(length)
        if not self.same_origin() or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_json(403, {"error": "requests must come from this app, as JSON"})
        cancel = re.fullmatch(r"/api/geolocate/([^/]+)/cancel", path)
        if cancel:
            try:
                return self.send_json(200, claude_geoloc.request_cancel(job_dir(cancel.group(1))))
            except LookupError as error:
                return self.send_json(404, {"error": str(error)})
        if path != "/api/geolocate":
            return self.send_json(404, {"error": "not found"})
        if not body:
            return self.send_json(413, {"error": "request body missing"})
        try:
            return self.send_json(200, start_geolocation(json.loads(body)))
        except PermissionError as error:
            return self.send_json(503, {"error": str(error)})
        except OverflowError as error:
            return self.send_json(429, {"error": str(error)})
        except (ValueError, KeyError, TypeError) as error:
            return self.send_json(400, {"error": str(error)})

    def do_GET(self):
        url = urlsplit(self.path)
        path = normalized_path(url.path)
        if path is None:
            return self.send_error(404)
        if path == "/api/health":
            return self.send_json(200, {"ok": True})
        if path == "/api/status":
            return self.send_json(200, {"gemini": bool(KEY), "model": MODEL,
                                        "tiger": bool(setting("TIGER_DATABASE_URL")),
                                        "ingest": ingest_status(), "geolocate": geolocate_status()})
        if path in ("/api/issues", "/api/pipeline", "/api/activity", "/api/tiger"):
            try:
                query = parse_qs(url.query, keep_blank_values=True, max_num_fields=8)
                if path == "/api/tiger":
                    if query:
                        raise ValueError("Tiger Data service metrics do not accept filters")
                    data = tiger.database_stats()
                elif path == "/api/activity":
                    data = tiger.activity(**tiger.activity_options(query))
                else:
                    if set(query) - {"dataset"} or any(len(v) != 1 for v in query.values()):
                        raise ValueError("Only one dataset filter is supported")
                    dataset = tiger.dataset_name(query.get("dataset", ["collected"])[0])
                    data = tiger.issues(dataset) if path == "/api/issues" else tiger.pipeline(dataset)
                return self.send_json(200, data)
            except ValueError as error:
                return self.send_json(400, {"error": str(error)})
            except tiger.Unavailable as error:
                return self.send_json(503, {"error": str(error)})
            except Exception:
                return self.send_json(503, {"error": "Tiger Data is unavailable. Check schema setup and database permissions."})
        if path == "/api/geolocate" or path.startswith("/api/geolocate/"):
            if not self.same_origin():
                return self.send_json(403, {"error": "requests must come from this app"})
            return self.geolocate_get([p for p in path.split("/")[3:] if p])
        photo = re.fullmatch(rf"/api/submissions/({SUBMISSION_ID})/photos/(\d)", path)
        if photo:
            try:
                found = tiger.submission_photo(photo.group(1), int(photo.group(2)))
            except Exception:
                return self.send_json(503, {"error": "Tiger Data is unavailable"})
            return self.send_bytes(*found) if found else self.send_json(404, {"error": "no such photo"})
        if path.startswith("/api/"):
            return self.send_json(404, {"error": "Unknown API endpoint"})
        target = analysis_file(path) if path.startswith("/data/analyzed/") else repo_file(path)
        if target is None:
            return self.send_error(404)
        return self.send_file(target)

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/geolocate" or path.startswith("/api/geolocate/"):
            return self.geolocate_post(path)
        if path == "/api/submissions" or path.startswith("/api/submissions/"):
            return self.submissions_post(path)
        routes = {"/api/triage": triage, "/api/digest": digest}
        route = routes.get(path)
        if not route:
            return self.send_json(404, {"error": "not found"})
        if not KEY:
            return self.send_json(503, {"error": "GEMINI_API_KEY is not set. Add it to .env and restart the server."})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            return self.send_json(413, {"error": "request body missing or too large"})
        if not GEMINI_SLOTS.acquire(blocking=False):
            self.rfile.read(length)
            return self.send_json(429, {"error": "Too many analysis requests. Try again shortly."})
        try:
            return self.send_json(200, route(json.loads(self.rfile.read(length))))
        except (ValueError, KeyError, TypeError) as error:
            return self.send_json(400, {"error": str(error)})
        except urllib.error.HTTPError as error:
            return self.send_json(502, {"error": f"Gemini returned HTTP {error.code}"})
        except (urllib.error.URLError, TimeoutError) as error:
            return self.send_json(504, {"error": f"Gemini unreachable: {type(error).__name__}"})
        finally:
            GEMINI_SLOTS.release()

    def log_message(self, format, *args):  # quieter: skip static assets
        if "/api/" in self.path or (args and str(args[1]) >= "400"):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="Serve GeoIssue with a local Gemini API")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5173)))
    port = parser.parse_args().port
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT)))
    print(f"GeoIssue ready at http://127.0.0.1:{port}  ·  Gemini {'on (' + MODEL + ')' if KEY else 'off: add GEMINI_API_KEY to .env'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
