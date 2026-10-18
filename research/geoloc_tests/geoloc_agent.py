"""Tool-using geolocation agent: a local vision LLM (Ollama) looks at a photo and calls our location tools
until it commits to an answer or the time budget runs out. Every model turn (including its thinking) and
every tool call is logged to results/agent/<run>.jsonl, with a summary in <run>.json.

The LLM never computes the final coordinate itself from nothing: it proposes places, the tools generate and
verify candidates (map search, City assets, Mapillary image matching, pose), and it reports what they found.

Usage:
  .venv/Scripts/python geoloc_agent.py --image images/test2.png --model qwen3.8:27b --minutes 20
      [--truth LAT,LON] [--ollama http://127.0.0.1:11434] [--no-think]
"""
import argparse
import base64
import io
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

import places

HERE = Path(__file__).parent
OUT = HERE / "results" / "agent"
UNVERIFIED_RADIUS_M = 1000
UNVERIFIED_MAX_CONFIDENCE = 0.3

# Kept deliberately neutral: no site types, place names or tag examples drawn from the test photos, so any
# conclusion the model reaches is deduced from the photo and tool output, not suggested by the prompt.
SYSTEM = """You are an OSINT geolocation analyst for GeoIssue. The photo was taken somewhere in the City of Toronto.
Goal: find where the camera was, ideally within 10 m. Locate the place, never the people in it.

Work deductively from what is visible. Do not assume a type of place in advance and do not pick a place from
memory: coordinates must come from tool results.
1. Observe: list legible text, transit, structures, street furniture, vegetation, terrain, and the viewpoint
   (street level, elevated, indoors).
2. Hypothesise: state several distinct explanations of what kind of site this could be, with the visual
   evidence for and against each.
3. Generate candidates for each hypothesis with tools, citywide: search_places (text only) and
   find_intersection for names; find_features_near for combinations of mapped features; search_assets for
   City street furniture; nearby_places to inspect what is around a coordinate.
4. Verify candidates with match_street_images and compare the reference images you are shown with the photo.
   Only an accepted match (>= 75 verified points) confirms a place. When a hypothesis fails, move on to the
   next one instead of refining the same guess.
5. If a match is accepted, call estimate_pose with its match_id, then final_answer.
6. An unverified final_answer is only accepted in the last 2 minutes of the budget; until then keep testing
   other hypotheses. Then give a wide radius and say what evidence is missing.
Image matching takes about 1-2 minutes per call, so choose what to verify carefully."""

TOOLS = [
    {"type": "function", "function": {
        "name": "search_places", "description": "Fuzzy text search of any named OpenStreetMap feature in Toronto. "
        "Text only: coordinates in the query are ignored; use nearby_places for that.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"},
                       "limit": {"type": "integer", "description": "default 8"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "nearby_places", "description": "Named places within radius_m of a coordinate, nearest first. "
        "Optional category filter: text matched against the place's OpenStreetMap key=value tag.",
        "parameters": {"type": "object", "properties": {
            "lat": {"type": "number"}, "lon": {"type": "number"},
            "radius_m": {"type": "number", "description": "default 500, max 3000"},
            "category": {"type": "string"}}, "required": ["lat", "lon"]}}},
    {"type": "function", "function": {
        "name": "find_intersection", "description": "Coordinates where two named streets meet.",
        "parameters": {"type": "object", "properties": {"street_a": {"type": "string"}, "street_b": {"type": "string"}},
                       "required": ["street_a", "street_b"]}}},
    {"type": "function", "function": {
        "name": "find_features_near", "description": "Bellingcat-style OpenStreetMap search: every place in Toronto "
        "where a feature with tag B lies within N metres of a feature with tag A. Tags are OpenStreetMap key=value "
        "pairs (keys include amenity, building, highway, railway, leisure, landuse, shop, tourism, office, "
        "public_transport, natural, man_made), or a bare key to match any value.",
        "parameters": {"type": "object", "properties": {
            "a": {"type": "string"}, "b": {"type": "string"}, "within_m": {"type": "number"},
            "b_min_area_m2": {"type": "number", "description": "minimum area of B polygons, default 0"}},
            "required": ["a", "b", "within_m"]}}},
    {"type": "function", "function": {
        "name": "search_assets", "description": "Search City of Toronto street-furniture layers for places where "
        "assets co-occur. Each spec is type[/subtype][:metres]; the first is the anchor. Types: pole (subtypes "
        "street_light, traffic_signal, pedestrian_light, miscellaneous, hydro_tower), shelter, hydrant, bike_ring, "
        "bin, bench, ttc_stop (bus, streetcar, subway), signal (pedestrian_crossover, beacon). Also "
        "osm:key=value:metres. Example: ['shelter', 'hydrant:15', 'pole/street_light:20'].",
        "parameters": {"type": "object", "properties": {
            "require": {"type": "array", "items": {"type": "string"}},
            "bbox": {"type": "string", "description": "optional min_lat,min_lon,max_lat,max_lon"}},
            "required": ["require"]}}},
    {"type": "function", "function": {
        "name": "match_street_images", "description": "Download Mapillary street-level images around up to 4 "
        "candidate points and match the photo against them (MegaLoc retrieval + LightGlue verification). "
        "Returns accepted (>=75 inliers = visual confirmation), the best matches and a match_id.",
        "parameters": {"type": "object", "properties": {
            "points": {"type": "array", "items": {"type": "object", "properties": {
                "lat": {"type": "number"}, "lon": {"type": "number"}}, "required": ["lat", "lon"]}},
            "radius_m": {"type": "number", "description": "search radius per point, 50-250, default 150"}},
            "required": ["points"]}}},
    {"type": "function", "function": {
        "name": "estimate_pose", "description": "Metre-level camera position, heading and uncertainty radius from "
        "an accepted match_street_images result (GeoCalib + PnP against posed Mapillary references).",
        "parameters": {"type": "object", "properties": {"match_id": {"type": "string"}}, "required": ["match_id"]}}},
    {"type": "function", "function": {
        "name": "final_answer", "description": "Commit to the answer. Ends the run.",
        "parameters": {"type": "object", "properties": {
            "lat": {"type": "number"}, "lon": {"type": "number"}, "radius_m": {"type": "number"},
            "confidence": {"type": "number", "description": "0-1"},
            "place_description": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["lat", "lon", "radius_m", "confidence", "evidence"]}}},
]


def compact(messages, keep, limit):
    """Shorten all but the last `keep` tool results to `limit` characters, and drop the pictures from all but
    the latest reference-image message (the query photo in message 1 always stays), so long runs fit."""
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    for i in tool_idx[:-keep] if keep else tool_idx:
        if len(messages[i]["content"]) > limit:
            messages[i]["content"] = messages[i]["content"][:limit] + " ...(older result shortened)"
    img_idx = [i for i, m in enumerate(messages) if i > 1 and m.get("images")]
    for i in img_idx[:-1]:
        messages[i].pop("images")
        messages[i]["content"] += " (older reference images removed to save space)"


def tool_points(obj, out):
    """Every (lat, lon) a tool returned, for auditing whether the final pin is backed by tool output."""
    if isinstance(obj, dict):
        if isinstance(obj.get("lat"), (int, float)) and isinstance(obj.get("lon"), (int, float)):
            out.append((float(obj["lat"]), float(obj["lon"])))
        for v in obj.values():
            tool_points(v, out)
    elif isinstance(obj, list):
        for v in obj:
            tool_points(v, out)
    return out


def dist_m(a, b):
    return 6371000 * math.hypot(math.radians(b[0] - a[0]), math.radians(b[1] - a[1]) * math.cos(math.radians(a[0])))


class Agent:
    def __init__(self, args):
        self.args = args
        self.run = args.run_name or f"{Path(args.image).stem}__{args.model.replace(':', '-')}__{time.strftime('%H%M%S')}"
        OUT.mkdir(parents=True, exist_ok=True)
        self.log_path = OUT / f"{self.run}.jsonl"
        self.log_f = open(self.log_path, "w", encoding="utf-8")
        self.t0 = time.time()
        self.deadline = self.t0 + args.minutes * 60
        self.matches = {}
        self.seen_calls = set()
        self.pending_images = []   # reference contact sheets to show the model after a match
        self.evidence = {}         # name -> bytes (contact sheets, match visualizations) saved with the run
        self.points = []           # every coordinate any tool returned
        self.warm_s = None
        self.final = None
        self.stats = {"turns": 0, "tool_calls": 0, "model_s": 0.0, "tool_s": 0.0}
        self.places_con = places.connect()

    def log(self, kind, **data):
        rec = {"t": round(time.time() - self.t0, 1), "type": kind, **data}
        self.log_f.write(json.dumps(rec, default=str) + "\n")
        self.log_f.flush()
        brief = {k: (v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v) for k, v in data.items()}
        print(f"[{rec['t']:7.1f}s] {kind}: {json.dumps(brief, default=str)[:600]}", flush=True)

    def remaining(self):
        return self.deadline - time.time()

    # ---------- tools ----------
    def run_cli(self, argv, timeout):
        res = subprocess.run([sys.executable, *argv], cwd=HERE, capture_output=True, text=True,
                             timeout=max(30, timeout), encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip()[-600:] or res.stdout.strip()[-600:])
        return res.stdout

    def tool_search_places(self, query, limit=8):
        return places.search(query, min(int(limit), 10), con=self.places_con)

    def tool_nearby_places(self, lat, lon, radius_m=500, category=None):
        return places.nearby(float(lat), float(lon), min(float(radius_m), 3000), category, 15,
                             con=self.places_con) or "nothing named within that radius"

    def tool_find_intersection(self, street_a, street_b):
        return places.intersection(street_a, street_b, con=self.places_con) or "no intersection found"

    def tool_find_features_near(self, a, b, within_m, b_min_area_m2=0):
        self.run_cli(["osm_local_search.py", "--a", a, "--b", b, "--within", str(within_m),
                      "--b-min-area", str(b_min_area_m2)], timeout=240)
        data = json.loads((HERE / "results" / f"osm_local_{a.replace('=', '-')}__{b.replace('=', '-')}.json").read_text())
        out = []
        for c in data["clusters"][:25]:
            big = max(c["hits"], key=lambda h: h["area_m2"])
            out.append({"lat": c["lat"], "lon": c["lon"], "b_area_m2": big["area_m2"], "dist_m": big["dist_m"],
                        "label": big["label"]})
        return {"n_candidate_areas": len(data["clusters"]), "top": out}

    def tool_search_assets(self, require, bbox=None):
        argv = ["asset_search.py", "--show", "0"]
        for spec in require:
            argv += ["--require", spec]
        if bbox:
            argv += ["--bbox", bbox]
        self.run_cli(argv, timeout=180)
        import re
        name = "__".join(re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") for s in require)[:120]
        data = json.loads((HERE / "results" / f"asset_search_{name}.json").read_text())
        return {"n_candidates": data["n_candidates"],
                "top": [{"lat": c["lat"], "lon": c["lon"], "n_hits": c["n_hits"]} for c in data["candidates"][:25]]}

    # run_match / run_pose / post_chat are the compute-heavy steps; modal_app.py overrides them to run remotely
    def run_match(self, points, radius, mid):
        """Harvest Mapillary around the points and match the query; returns match.py's JSON (or None)."""
        dirs = []
        for i, p in enumerate(points):
            d = HERE / "data" / "agent_mly" / self.run / f"{mid}_p{i}"
            self.run_cli(["mapillary_harvest.py", "--center", f"{p['lat']},{p['lon']}", "--radius", str(radius),
                          "--out", str(d), "--area-name", f"{mid}_p{i}", "--pano-2048", "--per-area", "60"],
                         timeout=min(300, self.remaining()))
            if (d / "index.json").exists() and json.loads((d / "index.json").read_text()):
                dirs.append(str(d))
        if not dirs:
            return None
        out = OUT / f"{self.run}_{mid}.json"
        self.run_cli(["match.py", "--query", self.args.image, "--refs", *dirs, "--out", str(out)],
                     timeout=min(600, self.remaining()))
        return json.loads(out.read_text())

    def run_pose(self, mid):
        out = OUT / f"{self.run}_{mid}_pose.json"
        self.run_cli(["pose.py", "--query", self.args.image, "--refs-json", str(OUT / f"{self.run}_{mid}.json"),
                      "--out", str(out)], timeout=min(300, self.remaining()))
        return json.loads(out.read_text())

    def tool_match_street_images(self, points, radius_m=150):
        radius = max(50, min(250, float(radius_m)))
        mid = f"m{len(self.matches) + 1}"
        data = self.run_match(points[:4], radius, mid)
        if not data:
            return {"match_id": None, "accepted": False, "note": "no Mapillary imagery near these points"}
        self.matches[mid] = data
        top = [{"rank": i, "lat": r["lat"], "lon": r["lon"], "inliers": r["inliers"], "area": r["area"],
                "view_heading": r.get("view_heading"),
                "captured": time.strftime("%Y-%m-%d", time.gmtime(r["captured_at"] / 1000)) if r.get("captured_at") else None}
               for i, r in enumerate(data["top"][:5], 1)]
        return {"match_id": mid, "accepted": data["accepted"], "accept_threshold": data["accept_inliers"],
                "n_reference_images": data["n_refs"], "harvest_per_point": data.get("_harvest"),
                "estimate": data["estimate"] and
                {k: data["estimate"].get(k) for k in ("lat", "lon", "best_inliers", "spread_m")}, "top": top,
                "note": "the top-ranked reference images are shown to you next" if self.pending_images else None}

    def tool_estimate_pose(self, match_id):
        if match_id not in self.matches:
            return f"unknown match_id {match_id}"
        data = self.run_pose(match_id)
        return {k: data.get(k) for k in ("ok", "method", "lat", "lon", "heading_deg", "radius_m", "n_inliers")}

    def tool_final_answer(self, lat, lon, radius_m, confidence, evidence, place_description=""):
        verified = any(m.get("accepted") for m in self.matches.values())
        if not verified and self.remaining() > 120:
            # verification-gated: an unverified answer only ends the run in the last 2 minutes
            self.log("final_rejected", reason="unverified", minutes_left=round(self.remaining() / 60, 1))
            return (f"Not accepted: no candidate has been visually verified and {self.remaining() / 60:.0f} "
                    "minutes remain. Test a different hypothesis (another kind of site or another area).")
        self.final = {"lat": float(lat), "lon": float(lon), "radius_m": float(radius_m),
                      "confidence": float(confidence), "place_description": place_description, "evidence": evidence}
        # the model's own radius is not trusted: without an accepted image match (>= 75 verified points) the
        # answer is a lead, so the harness widens the radius and caps the confidence deterministically
        if not any(m.get("accepted") for m in self.matches.values()):
            self.final.update({"verified": False, "model_radius_m": float(radius_m),
                               "model_confidence": float(confidence),
                               "radius_m": max(float(radius_m), UNVERIFIED_RADIUS_M),
                               "confidence": min(float(confidence), UNVERIFIED_MAX_CONFIDENCE)})
        else:
            self.final["verified"] = True
        return "recorded"

    def call_tool(self, name, arguments):
        fn = getattr(self, f"tool_{name}", None)
        if fn is None:
            return f"unknown tool {name}"
        key = (name, json.dumps(arguments, sort_keys=True))
        if key in self.seen_calls:  # repeated identical calls filled the 27B run's context; answer briefly
            self.log("tool_repeat", name=name, arguments=arguments)
            return "repeat of an earlier identical call; its result is above. Try something different."
        self.seen_calls.add(key)
        t = time.time()
        try:
            result = fn(**arguments)
        except Exception as err:
            result = f"tool error: {err}"
        dt = time.time() - t
        self.stats["tool_s"] += dt
        self.stats["tool_calls"] += 1
        if name != "final_answer":
            tool_points(result, self.points)
        self.log("tool_result", name=name, arguments=arguments, seconds=round(dt, 1), result=result)
        return result

    # ---------- model ----------
    def chat(self, messages, think=None):
        # num_predict caps each turn: without it a small model can think in a loop until the server errors out
        body = {"model": self.args.model, "messages": messages, "tools": TOOLS, "stream": False,
                "think": self.args.think if think is None else think,
                "options": {"num_ctx": self.args.num_ctx, "num_predict": self.args.max_tokens, "temperature": 0.3}}
        t = time.time()
        data = self.post_chat(body, timeout=max(60, min(self.args.turn_timeout, self.remaining() + 120)))
        self.stats["model_s"] += time.time() - t
        self.stats["turns"] += 1
        return data["message"], time.time() - t, data

    def post_chat(self, body, timeout):
        req = urllib.request.Request(f"{self.args.ollama}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)

    def run_loop(self):
        img = Image.open(self.args.image).convert("RGB")
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Geolocate this photo. You have {self.args.minutes} minutes.",
                     "images": [base64.b64encode(buf.getvalue()).decode()]}]
        nudges, warned = 0, False
        self.log("start", image=self.args.image, model=self.args.model, minutes=self.args.minutes, think=self.args.think)
        while self.final is None:
            if self.remaining() < 120 and not warned:
                messages.append({"role": "user", "content": "Less than 2 minutes left: call final_answer now "
                                 "with your best-supported location."})
                warned = True
            if self.remaining() < -180:
                self.log("timeout", note="no final answer before the deadline")
                break
            compact(messages, keep=6, limit=400)
            try:
                msg, dt, raw = self.chat(messages)
            except (TimeoutError, OSError) as err:
                # on failure (timeout, or a server error such as a full context) shrink history hard and ask
                # for an answer once more without thinking
                self.log("model_timeout", error=str(err), retry="compacted history, thinking off")
                compact(messages, keep=2, limit=200)
                messages.append({"role": "user", "content": "Call final_answer now with your best-supported location."})
                try:
                    msg, dt, raw = self.chat(messages, think=False)
                except (TimeoutError, OSError) as err2:
                    self.log("model_timeout", error=str(err2))
                    break
            calls = msg.get("tool_calls") or []
            self.log("model_turn", seconds=round(dt, 1), thinking=msg.get("thinking", ""),
                     content=msg.get("content", ""), tool_calls=[c["function"] for c in calls],
                     eval_count=raw.get("eval_count"), prompt_eval_count=raw.get("prompt_eval_count"))
            if not calls and (raw.get("eval_count") or 0) >= self.args.max_tokens and self.args.think:
                # the whole turn went on thinking and hit the cap: ask again without thinking
                try:
                    msg, dt, raw = self.chat(messages, think=False)
                except (TimeoutError, OSError) as err:
                    self.log("model_timeout", error=str(err))
                    break
                calls = msg.get("tool_calls") or []
                self.log("model_turn", retry="thinking off after hitting the token cap", seconds=round(dt, 1),
                         content=msg.get("content", ""), tool_calls=[c["function"] for c in calls],
                         eval_count=raw.get("eval_count"), prompt_eval_count=raw.get("prompt_eval_count"))
            messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
            if not calls:
                nudges += 1
                if nudges > 3:
                    break
                messages.append({"role": "user", "content": "Use a tool, or call final_answer if you are done."})
                continue
            for c in calls:
                fn = c["function"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                result = self.call_tool(fn["name"], args)
                messages.append({"role": "tool", "tool_name": fn["name"],
                                 "content": json.dumps(result, default=str)[:2500]})
                if self.final is not None:
                    break
            if self.pending_images and self.final is None:
                # show the model the real reference images so it compares pictures instead of narrating numbers
                messages.append({"role": "user", "images": self.pending_images, "content":
                                 "These are the top-ranked Mapillary reference images from your last "
                                 "match_street_images call (rank, verified points, capture date and position are "
                                 "printed under each). Compare them with the query photo: do any show the same "
                                 "place? Only an accepted match counts as confirmation."})
                self.log("shown_reference_images", count=len(self.pending_images))
                self.pending_images = []

    def summary(self):
        s = {"run": self.run, "image": self.args.image, "model": self.args.model, "minutes_budget": self.args.minutes,
             "wall_s": round(time.time() - self.t0, 1), **{k: round(v, 1) if isinstance(v, float) else v
                                                           for k, v in self.stats.items()},
             "final": self.final, "log": str(self.log_path), "model_warmup_s": self.warm_s}
        if self.final:
            # audit: is the pin backed by tool output, or did the model invent the coordinates?
            here = (self.final["lat"], self.final["lon"])
            nearest = min((dist_m(here, p) for p in self.points), default=None)
            accepted = [m["estimate"] for m in self.matches.values() if m.get("accepted") and m.get("estimate")]
            s["audit"] = {"tool_coordinates_returned": len(self.points),
                          "nearest_tool_coordinate_m": round(nearest, 1) if nearest is not None else None,
                          "supported_by_tool_output": nearest is not None and nearest <= 300,
                          "within_150m_of_accepted_match": any(dist_m(here, (e["lat"], e["lon"])) <= 150 for e in accepted),
                          "image_matches_run": len(self.matches),
                          "image_matches_accepted": sum(bool(m.get("accepted")) for m in self.matches.values())}
        if self.args.truth and self.final:
            tlat, tlon = map(float, self.args.truth.split(","))
            s["error_m"] = round(6371000 * math.hypot(math.radians(self.final["lat"] - tlat), math.radians(
                self.final["lon"] - tlon) * math.cos(math.radians(tlat))), 1)
            s["within_radius"] = s["error_m"] <= self.final["radius_m"]
        (OUT / f"{self.run}.json").write_text(json.dumps(s, indent=2))
        self.log("summary", **s)
        return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--model", default="qwen3.8:27b")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--truth")
    ap.add_argument("--no-think", dest="think", action="store_false")
    ap.add_argument("--num-ctx", type=int, default=65536)
    ap.add_argument("--max-tokens", type=int, default=4096, help="output cap per model turn (thinking included)")
    ap.add_argument("--turn-timeout", type=float, default=300, help="seconds before a model turn is abandoned")
    ap.add_argument("--run-name")
    args = ap.parse_args()
    agent = Agent(args)
    try:
        agent.run_loop()
    finally:
        print(json.dumps(agent.summary(), indent=2))


if __name__ == "__main__":
    main()
