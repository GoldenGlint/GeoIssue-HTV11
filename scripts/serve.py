"""Local dev server: serves the app plus a small Gemini API, so the key stays on this machine.

Usage:  python scripts/serve.py            (http://127.0.0.1:5173, loopback only)
        python scripts/serve.py --port 8000

The key is read like the analysis pipeline reads it: GEMINI_API_KEY from the environment, else from
.env or spikes/.env in the repo root. GEMINI_MODEL overrides the model (default: the summaries model in
analysis/config.toml). GEMINI_API_BASE overrides the endpoint (used by tests).

Endpoints
  GET  /api/status  -> {"gemini": bool, "model": str}
  POST /api/triage  {"image": base64, "mime": "image/jpeg"}
                    -> suggested category, severity and description, privacy flags, and face/plate boxes
                       ([ymin, xmin, ymax, xmax], 0–1000) for blurring
  POST /api/digest  {"area": {...areas.json-style stats}, "label": "ward"} -> {"text", "method"}

Photo geolocation with Claude Code (research/geoloc_tests/claude_geoloc.py) runs as a background job on
this machine, using the local Claude Code login, so it keeps going if the page or this server closes:
  POST /api/geolocate               {"image": base64, "mime"} -> the new job's status
  GET  /api/geolocate               -> {"jobs": [...]}, newest first
  GET  /api/geolocate/<id>          -> status: state, steps so far, result
  GET  /api/geolocate/<id>/photo    and /<id>/references/<m1>  -> the photo and the reference contact sheets
  POST /api/geolocate/<id>/cancel
GEOLOC_PYTHON is the Python with the vision tools installed (default: research/geoloc_tests/.venv, then .venv in the repo root);
GEOLOC_MODEL (default opus), GEOLOC_EFFORT (high), GEOLOC_MINUTES (10) and GEOLOC_MAX_RUNNING (1) tune it.
Hidden files and folders (.env, .git, …) are never served.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
GEOLOC = ROOT / "research" / "geoloc_tests"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(GEOLOC))
from analysis.stages import summaries  # noqa: E402  (shared key lookup and digest prompt)
import claude_geoloc  # noqa: E402  (standard library only: job files and the background worker)

CATEGORIES = ["Pothole", "Sidewalk damage", "Graffiti", "Litter", "Flooding", "Other"]
MAX_BODY = 12 * 1024 * 1024
ENV_FILES = [".env", "spikes/.env"]


def setting(name, default=None):
    """Environment first, then the .env files, like analysis.stages.summaries.api_key."""
    if os.environ.get(name):
        return os.environ[name]
    for file in ENV_FILES:
        path = ROOT / file
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip().removeprefix("export ").strip() == name:
                    return value.strip().strip("'\"") or default
    return default


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

TRIAGE_PROMPT = f"""You review photos submitted to CivicLens, a Toronto civic-issue map. Look at the photo and answer in JSON.
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


# ---- Photo geolocation with Claude Code ----
GEOLOC_JOBS = ROOT / "data" / "geolocate"
VENV_PYTHON = "Scripts/python.exe" if os.name == "nt" else "bin/python"
GEOLOC_PYTHON = Path(setting("GEOLOC_PYTHON", next(
    (p for p in (GEOLOC / ".venv" / VENV_PYTHON, ROOT / ".venv" / VENV_PYTHON) if p.is_file()), GEOLOC / ".venv" / VENV_PYTHON)))
GEOLOC_MODEL = setting("GEOLOC_MODEL", "opus")
GEOLOC_EFFORT = setting("GEOLOC_EFFORT", "high")
GEOLOC_MINUTES = float(setting("GEOLOC_MINUTES", 10))
GEOLOC_MAX_RUNNING = int(setting("GEOLOC_MAX_RUNNING", 1))
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
    job = claude_geoloc.new_job(GEOLOC_JOBS, base64.b64decode(image, validate=True), SUFFIX[mime],
                                GEOLOC_MINUTES, GEOLOC_MODEL, GEOLOC_EFFORT)
    claude_geoloc.start_background(job, python=str(GEOLOC_PYTHON), max_running=GEOLOC_MAX_RUNNING)
    return claude_geoloc.job_status(job)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def hidden(self):
        return any(part.startswith(".") for part in unquote(urlsplit(self.path).path).split("/") if part)

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
            photo = folder / claude_geoloc.read_status(folder)["image"]
            return self.send_file(photo, {".png": "image/png", ".webp": "image/webp"}.get(photo.suffix, "image/jpeg"))
        if len(parts) == 3 and parts[1] == "references" and re.fullmatch(r"m\d{1,3}", parts[2]):
            sheet = folder / f"{parts[2]}_references.jpg"
            if sheet.is_file():
                return self.send_file(sheet, "image/jpeg")
        return self.send_json(404, {"error": "not found"})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/status":
            return self.send_json(200, {"gemini": bool(KEY), "model": MODEL, "geolocate": geolocate_status()})
        if path == "/api/geolocate" or path.startswith("/api/geolocate/"):
            return self.geolocate_get([p for p in path.split("/")[3:] if p])
        if self.hidden():
            return self.send_error(404)
        return super().do_GET()

    def do_HEAD(self):
        if self.hidden():
            return self.send_error(404)
        return super().do_HEAD()

    def do_POST(self):
        path = urlsplit(self.path).path
        cancel = re.fullmatch(r"/api/geolocate/([^/]+)/cancel", path)
        if cancel:
            try:
                return self.send_json(200, claude_geoloc.request_cancel(job_dir(cancel.group(1))))
            except LookupError as error:
                return self.send_json(404, {"error": str(error)})
        routes = {"/api/triage": triage, "/api/digest": digest, "/api/geolocate": start_geolocation}
        route = routes.get(path)
        if not route:
            return self.send_json(404, {"error": "not found"})
        if not KEY and route is not start_geolocation:
            return self.send_json(503, {"error": "GEMINI_API_KEY is not set. Add it to .env and restart the server."})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            return self.send_json(413, {"error": "request body missing or too large"})
        try:
            return self.send_json(200, route(json.loads(self.rfile.read(length))))
        except PermissionError as error:
            return self.send_json(503, {"error": str(error)})
        except (ValueError, KeyError, TypeError) as error:
            return self.send_json(400, {"error": str(error)})
        except urllib.error.HTTPError as error:
            return self.send_json(502, {"error": f"Gemini returned HTTP {error.code}"})
        except (urllib.error.URLError, TimeoutError) as error:
            return self.send_json(504, {"error": f"Gemini unreachable: {type(error).__name__}"})

    def log_message(self, format, *args):  # quieter: skip static assets
        if "/api/" in self.path or (args and str(args[1]) >= "400"):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="Serve CivicLens with a local Gemini API")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5173)))
    port = parser.parse_args().port
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT)))
    print(f"CivicLens ready at http://127.0.0.1:{port}  ·  Gemini {'on (' + MODEL + ')' if KEY else 'off: add GEMINI_API_KEY to .env'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
