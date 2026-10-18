"""Run one vision model on one image with the shared geolocation prompt; log latency and answer.

Usage:
  python model_test.py --backend gemini --model gemini-4-argon --image images/test2.png
  python model_test.py --backend ollama --model qwen3.5:9b --image images/test2.png [--think]
"""
import argparse
import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent


def load_env(path):
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def encode_image(path, max_side):
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), img.size


def post_json(url, body, headers, timeout=900):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def run_gemini(model, prompt, b64):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": b64}}, {"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "thinkingConfig": {"includeThoughts": True}},
    }
    resp = post_json(url, body, {"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    parts = resp["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    # Gemini returns thought summaries, not the raw reasoning trace
    thinking = "\n\n".join(p.get("text", "") for p in parts if p.get("thought"))
    return text, thinking, resp.get("usageMetadata", {})


def run_ollama(model, prompt, b64, think):
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "think": think,
        "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        # 8k context keeps an 8B Q4 model fully on the 8 GB GPU; 16k spilled 27% onto the CPU
        "options": {"num_ctx": 8192, "num_predict": 6144, "temperature": 0.2},
    }
    resp = post_json("http://127.0.0.1:11434/api/chat", body, {})
    usage = {k: resp.get(k) for k in ("prompt_eval_count", "eval_count", "load_duration", "total_duration")}
    return resp["message"]["content"], resp["message"].get("thinking", ""), usage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["gemini", "ollama"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--max-side", type=int, default=1600)
    ap.add_argument("--think", action="store_true", help="ollama only: enable thinking mode")
    args = ap.parse_args()

    load_env(HERE / ".env")
    prompt = (HERE / "prompt.txt").read_text()
    b64, size = encode_image(args.image, args.max_side)

    start = time.perf_counter()
    try:
        if args.backend == "gemini":
            text, thinking, usage = run_gemini(args.model, prompt, b64)
        else:
            text, thinking, usage = run_ollama(args.model, prompt, b64, args.think)
    except urllib.error.HTTPError as err:
        print(f"HTTP {err.code}: {err.read().decode()[:500]}")
        return
    latency = time.perf_counter() - start

    try:
        answer = json.loads(text)
    except json.JSONDecodeError:
        answer = {"unparsed": text}

    tag = f"{Path(args.image).stem}__{args.model.replace(':', '-')}{'__think' if args.think else ''}"
    out = HERE / "results" / f"{tag}.json"
    out.parent.mkdir(exist_ok=True)
    record = {"model": args.model, "backend": args.backend, "think": args.think, "image_size": size,
              "latency_s": round(latency, 1), "usage": usage, "thinking": thinking, "answer": answer}
    out.write_text(json.dumps(record, indent=2))

    best = answer.get("best_guess", {}) if isinstance(answer, dict) else {}
    print(f"{args.model}: {latency:.1f}s -> {best.get('nearest_intersection')} "
          f"({best.get('lat')}, {best.get('lon')}) r={best.get('radius_m')} m conf={best.get('confidence')}")
    print(f"saved {out.name}")


if __name__ == "__main__":
    main()
