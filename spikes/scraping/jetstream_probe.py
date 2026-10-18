"""S1/S2: measure Toronto image-post volume on Bluesky through Jetstream (no account needed).

Mode `replay` starts from a cursor N hours in the past and reads until caught up with live
(tests whether Jetstream gives a free backfill). Mode `live` reads for N minutes.
Only posts that hit the broad Toronto prefilter are stored; everything else is just counted.

    .venv/Scripts/python -m spikes.scraping.jetstream_probe replay --hours 24 --max-minutes 90
    .venv/Scripts/python -m spikes.scraping.jetstream_probe live --minutes 60
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import time
from collections import defaultdict
from datetime import datetime, timezone

import websockets

from spikes.common.config import DATA, RESULTS, ensure_dirs
from spikes.scraping.gazetteer import complaint_terms, match

ENDPOINTS = [
    "wss://jetstream2.us-east.bsky.network/subscribe",
    "wss://jetstream1.us-east.bsky.network/subscribe",
    "wss://jetstream2.us-west.bsky.network/subscribe",
]
IMAGE_EMBEDS = {"app.bsky.embed.images", "app.bsky.embed.recordWithMedia", "app.bsky.embed.video"}


def _images(embed: dict | None) -> tuple[str | None, list[dict]]:
    if not embed:
        return None, []
    etype = embed.get("$type")
    if etype == "app.bsky.embed.recordWithMedia":
        media = embed.get("media") or {}
        etype = media.get("$type")
        embed = media
    if etype == "app.bsky.embed.images":
        out = []
        for img in embed.get("images", []):
            ref = ((img.get("image") or {}).get("ref") or {}).get("$link")
            if ref:
                out.append({"cid": ref, "mime": (img.get("image") or {}).get("mimeType"), "alt": img.get("alt", "")})
        return etype, out
    if etype == "app.bsky.embed.video":
        ref = ((embed.get("video") or {}).get("ref") or {}).get("$link")
        return etype, ([{"cid": ref, "mime": "video", "alt": embed.get("alt", "")}] if ref else [])
    return etype, []


class Stats:
    def __init__(self) -> None:
        self.hourly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.first_us: int | None = None
        self.last_us: int | None = None
        self.deletes = 0

    def add(self, hour: str, key: str) -> None:
        self.hourly[hour][key] += 1


async def run(mode: str, hours: float, minutes: float, max_minutes: float) -> None:
    ensure_dirs(DATA / "bsky", RESULTS / "raw")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out_path = DATA / "bsky" / f"jetstream_{mode}_{stamp}.jsonl.gz"
    stats = Stats()
    now_us = int(time.time() * 1_000_000)
    cursor = now_us - int(hours * 3600 * 1_000_000) if mode == "replay" else None
    deadline = time.monotonic() + 60 * (max_minutes if mode == "replay" else minutes)
    endpoint_idx = 0
    requested_cursor = cursor

    with gzip.open(out_path, "wt", encoding="utf-8") as out:
        while time.monotonic() < deadline:
            url = f"{ENDPOINTS[endpoint_idx]}?wantedCollections=app.bsky.feed.post"
            if cursor:
                url += f"&cursor={cursor}"
            try:
                async with websockets.connect(url, max_size=2**23, ping_interval=20, open_timeout=20) as ws:
                    print(f"connected {ENDPOINTS[endpoint_idx]} cursor={cursor}", flush=True)
                    async for raw in ws:
                        ev = json.loads(raw)
                        t_us = ev.get("time_us")
                        if t_us:
                            stats.first_us = stats.first_us or t_us
                            stats.last_us = t_us
                            cursor = t_us
                        commit = ev.get("commit") or {}
                        if ev.get("kind") != "commit" or commit.get("collection") != "app.bsky.feed.post":
                            continue
                        if commit.get("operation") == "delete":
                            stats.deletes += 1
                            continue
                        if commit.get("operation") != "create":
                            continue
                        hour = datetime.fromtimestamp(t_us / 1e6, timezone.utc).strftime("%Y-%m-%dT%H")
                        rec = commit.get("record") or {}
                        text = rec.get("text") or ""
                        etype, imgs = _images(rec.get("embed"))
                        has_img = any(i["mime"] != "video" for i in imgs)
                        stats.add(hour, "posts")
                        if has_img:
                            stats.add(hour, "posts_with_images")
                        alt = " ".join(i["alt"] for i in imgs)
                        tags = [f.get("tag", "") for fc in rec.get("facets") or [] for f in fc.get("features") or [] if f.get("tag")]
                        m = match(" ".join([text, alt, " ".join("#" + t for t in tags)]))
                        if not m.prefilter:
                            if mode == "replay" and time.monotonic() > deadline:
                                break
                            continue
                        stats.add(hour, "prefilter")
                        if m.relevant:
                            stats.add(hour, "relevant")
                            if has_img:
                                stats.add(hour, "relevant_with_images")
                        out.write(json.dumps({
                            "did": ev.get("did"), "rkey": commit.get("rkey"), "cid": commit.get("cid"),
                            "time_us": t_us, "created_at": rec.get("createdAt"), "text": text,
                            "langs": rec.get("langs"), "embed_type": etype, "images": imgs, "tags": tags,
                            "strong": m.strong, "weak": m.weak, "relevant": m.relevant,
                            "complaints": complaint_terms(text + " " + alt),
                        }) + "\n")
                        if time.monotonic() > deadline:
                            break
                        if mode == "replay" and t_us > int(time.time() * 1_000_000) - 15_000_000:
                            print("caught up with live", flush=True)
                            deadline = 0
                            break
            except (OSError, websockets.WebSocketException) as exc:
                print(f"connection error: {exc!r}; rotating endpoint", flush=True)
                endpoint_idx = (endpoint_idx + 1) % len(ENDPOINTS)
                await asyncio.sleep(3)

    summary = {
        "mode": mode,
        "requested_cursor_hours_back": hours if mode == "replay" else None,
        "requested_cursor_iso": datetime.fromtimestamp(requested_cursor / 1e6, timezone.utc).isoformat() if requested_cursor else None,
        "first_event_iso": datetime.fromtimestamp(stats.first_us / 1e6, timezone.utc).isoformat() if stats.first_us else None,
        "last_event_iso": datetime.fromtimestamp(stats.last_us / 1e6, timezone.utc).isoformat() if stats.last_us else None,
        "deletes_seen": stats.deletes,
        "hourly": {h: dict(v) for h, v in sorted(stats.hourly.items())},
        "posts_file": str(out_path.relative_to(DATA.parent.parent)),
    }
    res_path = RESULTS / "raw" / f"jetstream_{mode}_{stamp}.json"
    res_path.write_text(json.dumps(summary, indent=2))
    totals = defaultdict(int)
    for v in stats.hourly.values():
        for k, n in v.items():
            totals[k] += n
    print(json.dumps({"first": summary["first_event_iso"], "last": summary["last_event_iso"], **totals}, indent=2))
    print(f"wrote {res_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["replay", "live"])
    ap.add_argument("--hours", type=float, default=24, help="replay: how far back to start")
    ap.add_argument("--minutes", type=float, default=60, help="live: how long to listen")
    ap.add_argument("--max-minutes", type=float, default=90, help="replay: wall-clock cap")
    a = ap.parse_args()
    asyncio.run(run(a.mode, a.hours, a.minutes, a.max_minutes))


if __name__ == "__main__":
    main()
