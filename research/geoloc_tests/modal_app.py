"""CivicLens geolocation agent on Modal, split by compute need. Billing is per second and every container
scales to zero after SCALEDOWN_S idle, so nothing keeps running (or billing) after a run; the workspace
budget in Modal's Usage & Billing is the hard spending cap.

  CPU   agent loop, place/intersection search, OSM feature search, City asset search
  L4    Mapillary harvest + image matching (MegaLoc, ALIKED + LightGlue) + pose (GeoCalib + PnP)
  L40S  the LLM under Ollama, called as a Modal method (no public endpoint); --llm-gpu picks another GPU

Usage (from research/geoloc_tests):
  .venv/Scripts/python -m modal run modal_app.py::pull_model --model qwen3.8:27b     # once; runs on CPU
  .venv/Scripts/python -m modal run modal_app.py --image images/test3_gallery.jpg --minutes 20 \
      [--truth LAT,LON] [--model qwen3.8:27b] [--llm-gpu L40S] [--no-think]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import modal

HERE = Path(__file__).parent
GT = "/root/gt"
SCALEDOWN_S = 300
CPU_CODE = ["geoloc_agent.py", "places.py", "osm_local_search.py", "asset_search.py"]
CPU_DATA = ["data/Toronto.osm.pbf", "data/places.duckdb", "data/toronto_assets.duckdb"]
VISION_CODE = ["mapillary_harvest.py", "match.py", "pano.py", "pose.py"]


def local_env(key):
    """Read a key from the local .env (only exists on the laptop; remote imports get '')."""
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get(key, "")


def with_files(image, files):
    for f in files:
        image = image.add_local_file(HERE / f, f"{GT}/{f}")
    return image


app = modal.App("civiclens-geoloc")
models = modal.Volume.from_name("civiclens-models", create_if_missing=True)  # Ollama models + vision weights
mapillary = modal.Secret.from_dict({"MAPILLARY_TOKEN": local_env("MAPILLARY_TOKEN")})

cpu_image = with_files(
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("duckdb==1.5.6", "numpy", "pillow")
    .run_commands("python -c \"import duckdb; duckdb.sql('INSTALL spatial')\""),
    CPU_CODE + CPU_DATA)

vision_image = with_files(
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install("torch", "torchvision", index_url="https://download.pytorch.org/whl/cu128")
    .pip_install("numpy", "pillow", "opencv-python-headless", "huggingface_hub", "safetensors", "matplotlib",
                 "git+https://github.com/cvg/LightGlue.git", "git+https://github.com/cvg/GeoCalib")
    .env({"TORCH_HOME": "/models/torch", "HF_HOME": "/models/hf"}),
    VISION_CODE)

llm_image = (modal.Image.debian_slim(python_version="3.12")
             .apt_install("curl", "zstd", "ca-certificates", "pciutils")
             .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
             .env({"OLLAMA_MODELS": "/models/ollama", "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_KEEP_ALIVE": "30m"}))


def start_ollama():
    proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=2)
            return proc
        except OSError:
            time.sleep(1)
    raise RuntimeError("ollama serve did not start")


@app.function(image=llm_image, volumes={"/models": models}, cpu=4, timeout=3600)
def pull_model(model: str = "qwen3.8:27b"):
    """Download the LLM into the shared Volume on a cheap CPU container (no GPU needed to pull)."""
    proc = start_ollama()
    t = time.time()
    subprocess.run(["ollama", "pull", model], check=True)
    out = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
    proc.terminate()
    models.commit()
    print(f"pulled {model} in {time.time() - t:.0f}s\n{out}")


@app.cls(image=llm_image, gpu="L40S", volumes={"/models": models}, scaledown_window=SCALEDOWN_S,
         timeout=3600, max_containers=1)
class LLM:
    @modal.enter()
    def start(self):
        t = time.time()
        self.proc = start_ollama()
        self.ready_s = round(time.time() - t, 1)

    @modal.method()
    def chat(self, body: dict) -> dict:
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3000) as resp:
            data = json.load(resp)
        data["_gpu"] = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used", "--format=csv,noheader"],
                                      capture_output=True, text=True).stdout.strip()
        return data

    @modal.exit()
    def stop(self):
        self.proc.terminate()


@app.cls(image=vision_image, gpu="L4", volumes={"/models": models}, secrets=[mapillary],
         scaledown_window=SCALEDOWN_S, timeout=1800, max_containers=1)
class Vision:
    @modal.enter()
    def setup(self):
        os.chdir(GT)
        Path(".env").write_text(f'MAPILLARY_TOKEN="{os.environ["MAPILLARY_TOKEN"]}"\n')
        for d in ("images", "results/agent", "data"):
            Path(d).mkdir(parents=True, exist_ok=True)

    def cli(self, argv, timeout):
        res = subprocess.run([sys.executable, *argv], cwd=GT, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip()[-800:] or res.stdout.strip()[-800:])
        return res.stdout

    def contact_sheet(self, data, dirs):
        """The top retrieved references as the matcher saw them (panoramas rendered at the matched view)."""
        import io
        import numpy as np
        from PIL import Image, ImageDraw
        sys.path.insert(0, GT)
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
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=85)
        return buf.getvalue()

    @modal.method()
    def match(self, image_bytes: bytes, image_name: str, points: list, radius: float, run: str, mid: str):
        query = Path(GT) / "images" / image_name
        query.write_bytes(image_bytes)
        dirs, harvest = [], []
        for i, p in enumerate(points):
            d = Path(GT) / "data" / "agent_mly" / run / f"{mid}_p{i}"
            self.cli(["mapillary_harvest.py", "--center", f"{p['lat']},{p['lon']}", "--radius", str(radius),
                      "--out", str(d), "--area-name", f"{mid}_p{i}", "--pano-2048", "--per-area", "60"], 300)
            idx = json.loads((d / "index.json").read_text()) if (d / "index.json").exists() else []
            dates = sorted(r["captured_at"] for r in idx if r.get("captured_at"))
            # what was really downloaded: the model and the log both see these counts
            harvest.append({"lat": p["lat"], "lon": p["lon"], "images": len(idx),
                            "panoramas": sum(bool(r.get("is_pano")) for r in idx),
                            "oldest": time.strftime("%Y-%m-%d", time.gmtime(dates[0] / 1000)) if dates else None,
                            "newest": time.strftime("%Y-%m-%d", time.gmtime(dates[-1] / 1000)) if dates else None})
            if idx:
                dirs.append(str(d))
        if not dirs:
            return {"data": None, "harvest": harvest}
        out = Path(GT) / "results" / "agent" / f"{run}_{mid}.json"
        self.cli(["match.py", "--query", str(query), "--refs", *dirs, "--out", str(out)], 900)
        models.commit()  # keep downloaded MegaLoc/LightGlue weights for the next container
        data = json.loads(out.read_text())
        pair = Path(GT) / "results" / f"match_{Path(image_name).stem}_best.jpg"
        return {"data": data, "harvest": harvest, "sheet": self.contact_sheet(data, dirs),
                "pair": pair.read_bytes() if pair.exists() else None}

    @modal.method()
    def pose(self, image_name: str, run: str, mid: str):
        out = Path(GT) / "results" / "agent" / f"{run}_{mid}_pose.json"
        self.cli(["pose.py", "--query", f"images/{image_name}", "--refs-json",
                  f"results/agent/{run}_{mid}.json", "--out", str(out)], 600)
        models.commit()
        return json.loads(out.read_text())


@app.function(image=cpu_image, cpu=8, memory=8192, timeout=3600)
def agent(image_bytes: bytes, image_name: str, minutes: float, truth: str, model: str, llm_gpu: str,
          think: bool, max_tokens: int, num_ctx: int) -> dict:
    import base64
    os.chdir(GT)
    sys.path.insert(0, GT)
    import geoloc_agent

    Path("images").mkdir(exist_ok=True)
    Path("images", image_name).write_bytes(image_bytes)
    llm = LLM.with_options(gpu=llm_gpu)()
    vision = Vision()

    class ModalAgent(geoloc_agent.Agent):
        def post_chat(self, body, timeout):
            call = llm.chat.spawn(body)
            try:
                data = call.get(timeout=timeout)
            except Exception as err:  # a turn over its time limit: cancel it and let the loop retry or stop
                call.cancel()
                raise TimeoutError(f"LLM turn exceeded {timeout:.0f}s ({type(err).__name__})")
            self.gpu_info = data.pop("_gpu", "")
            return data

        def run_match(self, points, radius, mid):
            res = vision.match.remote(image_bytes, image_name, points, radius, self.run, mid)
            self.log("harvest", match_id=mid, per_point=res["harvest"])
            data = res["data"]
            if data is None:
                return None
            data["_harvest"] = res["harvest"]
            if res.get("sheet"):
                self.evidence[f"{mid}_references.jpg"] = res["sheet"]
                self.pending_images = [base64.b64encode(res["sheet"]).decode()]
            if res.get("pair"):
                self.evidence[f"{mid}_best_match_lines.jpg"] = res["pair"]
            return data

        def run_pose(self, mid):
            return vision.pose.remote(image_name, self.run, mid)

    args = argparse.Namespace(image=f"images/{image_name}", model=model, ollama="", minutes=minutes,
                              truth=truth or None, think=think, num_ctx=num_ctx, max_tokens=max_tokens,
                              turn_timeout=900, run_name=f"modal_{Path(image_name).stem}__{model.replace(':', '-')}"
                                                         f"__{llm_gpu}__{time.strftime('%H%M%S')}")
    # load the model onto the GPU before the clock starts, and record how long that took
    t = time.time()
    llm.chat.remote({"model": model, "messages": [{"role": "user", "content": "ok"}], "stream": False,
                     "think": False, "options": {"num_ctx": num_ctx, "num_predict": 1}})
    warm_s = round(time.time() - t, 1)
    a = ModalAgent(args)
    a.warm_s = warm_s
    try:
        a.run_loop()
    finally:
        summary = a.summary()
    summary["llm_gpu"] = f"{llm_gpu} ({getattr(a, 'gpu_info', '')})"
    return {"summary": summary, "log": a.log_path.read_text(), "evidence": a.evidence}


@app.local_entrypoint()
def main(image: str, minutes: float = 20, truth: str = "", model: str = "qwen3.8:27b", llm_gpu: str = "L40S",
         think: bool = True, max_tokens: int = 4096, num_ctx: int = 65536):
    p = Path(image)
    t = time.time()
    res = agent.remote(p.read_bytes(), p.name, minutes, truth, model, llm_gpu, think, max_tokens, num_ctx)
    out = HERE / "results" / "modal"
    out.mkdir(parents=True, exist_ok=True)
    run = res["summary"]["run"]
    (out / f"{run}.jsonl").write_text(res["log"], encoding="utf-8")
    (out / f"{run}.json").write_text(json.dumps(res["summary"], indent=2))
    ev_dir = out / run
    ev_dir.mkdir(exist_ok=True)
    for name, blob in (res.get("evidence") or {}).items():
        (ev_dir / name).write_bytes(blob)
    print(f"evidence images: {len(res.get('evidence') or {})} saved to results/modal/{run}/")
    print(json.dumps(res["summary"], indent=2))
    print(f"wall {time.time() - t:.0f}s; log saved to results/modal/{run}.jsonl")
