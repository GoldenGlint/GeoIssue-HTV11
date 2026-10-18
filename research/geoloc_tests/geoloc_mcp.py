"""MCP server that gives Claude Code the GeoIssue geolocation tools (stdio JSON-RPC, no SDK needed).

claude_geoloc.py starts Claude Code with this server as its only source of tools. The tools are the
geoloc_agent.Agent tools, so the Qwen and Claude agents search, match and verify the same way, and
final_answer applies the same rule: without an accepted image match the radius is widened and the
confidence capped by the harness, not the model. Additions for Claude:
  view_photo            the photo itself, or a zoomed crop of it (to read small signs)
  match_street_images   downloads Mapillary around the points in parallel and returns the top-ranked
                        references as a contact sheet image, so the model compares pictures, not numbers
  every result          carries the time used, and after the budget only final_answer still runs

Usage (Claude Code launches it): python geoloc_mcp.py --image PHOTO --out JOB_DIR --minutes 10
Ground truth never reaches this process: claude_geoloc.py scores the answer after the run.
Writes JOB_DIR/<job>.jsonl (every tool call), JOB_DIR/result.json (the answer and its audit) and the
reference contact sheets.
"""
import argparse
import base64
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

import geoloc_agent

HERE = Path(__file__).parent
PROTOCOL = "2025-06-18"
PHOTO_MAX_SIDE = 1568  # Claude downsizes larger images anyway

VIEW_PHOTO = {"type": "function", "function": {
    "name": "view_photo", "description": "Show the photo being geolocated. Without a box: the whole photo. With "
    "a box: that part at full resolution, enlarged, to read small text (signs, plates on poles, stop numbers).",
    "parameters": {"type": "object", "properties": {
        "box": {"type": "array", "items": {"type": "number"}, "description": "[x0, y0, x1, y1] in 0-1000 of "
                "the photo's width and height, e.g. [600, 200, 900, 450] for a sign in the upper right"}}}}}

TOOL_SPECS = [{"name": t["function"]["name"], "description": t["function"]["description"],
               "inputSchema": t["function"]["parameters"]} for t in [VIEW_PHOTO, *geoloc_agent.TOOLS]]


def jpeg_b64(img, quality=88):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def reference_sheet(data, dirs):
    """The top retrieved references as the matcher saw them (panoramas rendered at the matched view),
    labelled with rank, verified points, capture date and position. Same layout as modal_app.py."""
    import numpy as np
    import pano
    recs = {}
    for d in dirs:
        for r in json.loads((Path(d) / "index.json").read_text()):
            recs[r["id"]] = (r, Path(d))
    tiles = []
    for rank, t in enumerate(data["top"][:8], 1):
        if t["id"] not in recs:
            continue
        rec, d = recs[t["id"]]
        img = Image.open(d / rec["area"] / f"{t['id']}.jpg").convert("RGB")
        if t["is_pano"] and t.get("view_yaw") is not None:
            img = Image.fromarray(pano.perspective(np.asarray(img), t["view_yaw"], 0, 90, 480, 360,
                                                   level=pano.level_rotation(rec))[0])
        img.thumbnail((480, 360))
        tile = Image.new("RGB", (480, 384), "black")
        tile.paste(img, (0, 0))
        when = time.strftime("%Y-%m-%d", time.gmtime(t["captured_at"] / 1000)) if t.get("captured_at") else "?"
        ImageDraw.Draw(tile).text((6, 366), f"#{rank}  {t['inliers']} pts  {when}  {t['lat']:.5f},{t['lon']:.5f}",
                                  fill="yellow")
        tiles.append(tile)
    if not tiles:
        return None
    sheet = Image.new("RGB", (480 * 4, 384 * ((len(tiles) + 3) // 4)), "black")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % 4) * 480, (i // 4) * 384))
    return sheet


class ToolHost(geoloc_agent.Agent):
    """The agent's tools without its model loop: Claude Code is the loop."""

    def __init__(self, args):
        self.out_dir = Path(args.out)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        geoloc_agent.OUT = self.out_dir  # the agent's tool log, match and pose files go to the job
        args.run_name = args.run_name or self.out_dir.name  # names the job's Mapillary download folder
        super().__init__(args)

    def tool_view_photo(self, box=None):
        img = Image.open(self.args.image).convert("RGB")
        note = f"whole photo, {img.width}x{img.height} px"
        if box:
            x0, y0, x1, y1 = (max(0.0, min(1000.0, float(v))) for v in box)
            if x1 - x0 < 5 or y1 - y0 < 5:
                return "box too small: give [x0, y0, x1, y1] in 0-1000 with x1 > x0 and y1 > y0"
            img = img.crop((round(x0 * img.width / 1000), round(y0 * img.height / 1000),
                            round(x1 * img.width / 1000), round(y1 * img.height / 1000)))
            note = f"crop {[round(v) for v in (x0, y0, x1, y1)]} at full resolution ({img.width}x{img.height} px)"
            if max(img.size) < 800:  # enlarge small crops so fine print survives the model's image encoder
                scale = 800 / max(img.size)
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
        img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
        self.pending_images = [jpeg_b64(img)]
        return {"shown": note}

    def harvest(self, mid, i, p, radius):
        d = HERE / "data" / "agent_mly" / self.run / f"{mid}_p{i}"
        try:
            self.run_cli(["mapillary_harvest.py", "--center", f"{p['lat']},{p['lon']}", "--radius", str(radius),
                          "--out", str(d), "--area-name", f"{mid}_p{i}", "--pano-2048", "--per-area", "60"],
                         timeout=min(300, self.remaining()))
        except Exception as err:
            self.log("harvest_error", match_id=mid, point=p, error=str(err)[-300:])
        idx = json.loads((d / "index.json").read_text()) if (d / "index.json").exists() else []
        dates = sorted(r["captured_at"] for r in idx if r.get("captured_at"))
        day = lambda ms: time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))
        return d, {"lat": p["lat"], "lon": p["lon"], "images": len(idx),
                   "panoramas": sum(bool(r.get("is_pano")) for r in idx),
                   "oldest": day(dates[0]) if dates else None, "newest": day(dates[-1]) if dates else None}

    def run_match(self, points, radius, mid):
        # the downloads are network-bound, so the points are fetched at the same time
        with ThreadPoolExecutor(len(points)) as pool:
            done = list(pool.map(lambda ip: self.harvest(mid, ip[0], ip[1], radius), enumerate(points)))
        harvest = [h for _, h in done]
        dirs = [str(d) for d, h in done if h["images"]]
        self.log("harvest", match_id=mid, per_point=harvest)
        if not dirs:
            return None
        out = self.out_dir / f"{self.run}_{mid}.json"
        self.run_cli(["match.py", "--query", self.args.image, "--refs", *dirs, "--out", str(out)],
                     timeout=min(600, max(60, self.remaining())))
        data = json.loads(out.read_text())
        data["_harvest"] = harvest
        sheet = reference_sheet(data, dirs)
        if sheet:
            sheet.save(self.out_dir / f"{mid}_references.jpg", quality=85)
            self.pending_images = [jpeg_b64(sheet, 85)]
        return data

    def tool_match_street_images(self, points, radius_m=150):
        result = super().tool_match_street_images(points, radius_m)
        if self.pending_images and isinstance(result, dict):
            result["note"] = ("the image below shows the top-ranked references (rank, verified points, capture "
                              "date, position). Compare them with the photo: only accepted=true counts as "
                              "confirmation")
        return result

    def write_result(self):
        summary = self.summary()
        (self.out_dir / "result.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary

    def mcp_call(self, name, arguments):
        """One tools/call: the tool's JSON result, any image it produced, and the clock."""
        used = (time.time() - self.t0) / 60
        if self.remaining() <= 0 and name != "final_answer":
            text, is_error = "Time is up: call final_answer now with your best-supported location.", True
        else:
            self.pending_images = []
            result = self.call_tool(name, arguments)
            is_error = isinstance(result, str) and result.startswith(("tool error", "unknown tool"))
            text = result if isinstance(result, str) else json.dumps(result, default=str)
            if name == "final_answer" and self.final:
                summary = self.write_result()
                f = summary["final"]
                how = ("verified by an accepted image match" if f["verified"] else
                       f"NOT verified by an image match, so the harness widened the radius to {f['radius_m']:.0f} m "
                       f"and capped confidence at {f['confidence']:.2f}")
                text = f"Recorded: {how}. Stop now and reply with one sentence summarising the answer."
        content = [{"type": "text", "text": text}]
        content += [{"type": "image", "data": b64, "mimeType": "image/jpeg"} for b64 in self.pending_images]
        self.pending_images = []
        if name != "final_answer":
            left = self.remaining() / 60
            clock = f"[time used {used:.1f} of {self.args.minutes:g} min]"
            if left < 2:
                clock += " Less than 2 minutes left: call final_answer now."
            content.append({"type": "text", "text": clock})
        return {"content": content, "isError": is_error}


def respond(proto, msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id, **({"error": error} if error else {"result": result})}
    proto.write((json.dumps(msg) + "\n").encode("utf-8"))
    proto.flush()


def serve(host, stdin, proto):
    """Newline-delimited JSON-RPC over stdio. Calls run one at a time: the tools share a DuckDB connection."""
    for line in stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:  # notifications (initialized, cancelled) need no answer
            continue
        try:
            if method == "initialize":
                respond(proto, msg_id, {"protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL),
                                        "capabilities": {"tools": {}},
                                        "serverInfo": {"name": "geoissue-geoloc", "version": "0.1.0"}})
            elif method == "tools/list":
                respond(proto, msg_id, {"tools": TOOL_SPECS})
            elif method == "tools/call":
                params = msg.get("params") or {}
                respond(proto, msg_id, host.mcp_call(params.get("name"), params.get("arguments") or {}))
            elif method == "ping":
                respond(proto, msg_id, {})
            else:
                respond(proto, msg_id, error={"code": -32601, "message": f"method not found: {method}"})
        except Exception as err:  # a broken tool must not take the server down mid-run
            host.log("server_error", method=method, error=repr(err))
            respond(proto, msg_id, error={"code": -32603, "message": repr(err)[:500]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True, help="job directory for the tool log, evidence and result.json")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--model", default="claude-code")
    ap.add_argument("--run-name")
    args = ap.parse_args()
    args.truth = None  # the agent's tools never hold the answer; scoring happens offline
    # only JSON-RPC may reach Claude Code's pipe: keep a private copy of it, then point file descriptor 1
    # (Python prints and anything native, such as a DuckDB progress bar) at stderr
    proto = os.fdopen(os.dup(sys.stdout.fileno()), "wb")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    host = ToolHost(args)
    try:
        serve(host, io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8"), proto)
    finally:
        if host.final is None:  # Claude Code closed the pipe without an answer; a kill skips this, but the
            # runner's status.json still lists every step
            host.write_result()


if __name__ == "__main__":
    main()
