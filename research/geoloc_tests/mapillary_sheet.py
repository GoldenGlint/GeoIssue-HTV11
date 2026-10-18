"""Fetch recent Mapillary images around candidate points and save one contact sheet per candidate.

Usage: python mapillary_sheet.py --name wolseley --lat 43.6486 --lon -79.4045 [--radius 80] [--max 12]
"""
import argparse
import io
import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent


def load_env(path):
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=float, default=80, help="metres")
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--since", default="2022-01-01")
    args = ap.parse_args()
    load_env(HERE / ".env")

    dlat = args.radius / 111320
    dlon = args.radius / (111320 * math.cos(math.radians(args.lat)))
    bbox = f"{args.lon - dlon},{args.lat - dlat},{args.lon + dlon},{args.lat + dlat}"
    params = {
        "access_token": os.environ["MAPILLARY_TOKEN"],
        "fields": "id,captured_at,compass_angle,computed_compass_angle,computed_geometry,is_pano,thumb_1024_url",
        "bbox": bbox,
        "start_captured_at": f"{args.since}T00:00:00Z",
        "limit": 200,
    }
    start = time.perf_counter()
    data = get_json("https://graph.mapillary.com/images?" + urllib.parse.urlencode(params)).get("data", [])
    t_search = time.perf_counter() - start

    # newest first, then spread across headings so the sheet covers several directions
    data.sort(key=lambda d: -d["captured_at"])
    picked, seen = [], set()
    for d in data:
        heading = int((d.get("computed_compass_angle") or d.get("compass_angle") or 0) // 45)
        if (heading, d.get("is_pano")) not in seen:
            seen.add((heading, d.get("is_pano")))
            picked.append(d)
    # top up with the newest remaining images if the heading spread left free slots
    picked += [d for d in data if d not in picked][: max(0, args.max - len(picked))]
    picked = picked[: args.max]

    tiles = []
    for d in picked:
        with urllib.request.urlopen(d["thumb_1024_url"], timeout=60) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        img.thumbnail((480, 480))
        canvas = Image.new("RGB", (480, 300), "black")
        canvas.paste(img, (0, 0))
        when = time.strftime("%Y-%m-%d", time.gmtime(d["captured_at"] / 1000))
        heading = d.get("computed_compass_angle") or d.get("compass_angle") or 0
        ImageDraw.Draw(canvas).text((6, 280), f"{when} hdg {heading:.0f} {'pano' if d.get('is_pano') else ''}",
                                     fill="yellow")
        tiles.append(canvas)
    t_total = time.perf_counter() - start

    out_dir = HERE / "results" / "mapillary"
    out_dir.mkdir(parents=True, exist_ok=True)
    if tiles:
        cols = 3
        rows = math.ceil(len(tiles) / cols)
        sheet = Image.new("RGB", (480 * cols, 300 * rows), "black")
        for i, tile in enumerate(tiles):
            sheet.paste(tile, ((i % cols) * 480, (i // cols) * 300))
        sheet.save(out_dir / f"{args.name}.jpg", quality=85)
    (out_dir / f"{args.name}.json").write_text(json.dumps(picked, indent=2))
    print(f"{args.name}: {len(data)} images since {args.since} within ~{args.radius:.0f} m "
          f"(search {t_search:.1f}s, total {t_total:.1f}s); sheet of {len(tiles)} -> results/mapillary/{args.name}.jpg")


if __name__ == "__main__":
    main()
