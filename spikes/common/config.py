"""Shared paths, env loading and HTTP defaults for the feasibility spikes."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SPIKES = ROOT / "spikes"
RESULTS = SPIKES / "results"

load_dotenv(SPIKES / ".env")

# Large data and model caches can live on another drive (C: is nearly full):
# set CIVICLENS_DATA_DIR / CIVICLENS_CACHE_DIR in spikes/.env.
DATA = Path(os.environ.get("CIVICLENS_DATA_DIR") or SPIKES / "data")
CACHE = Path(os.environ.get("CIVICLENS_CACHE_DIR") or ROOT / ".cache")

# Keep model weights inside the project so they can be deleted in one go (disk is tight).
os.environ.setdefault("HF_HOME", str(CACHE / "hf"))
os.environ.setdefault("TORCH_HOME", str(CACHE / "torch"))

USER_AGENT = "CivicLensSpike/0.1 (Hack the Valley 11 civic-tech research prototype)"

# Toronto city bounding box (west, south, east, north)
TORONTO_BBOX = (-79.6393, 43.5810, -79.1152, 43.8555)


def env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name) or None
    if required and not value:
        raise SystemExit(f"Missing {name}. Add it to spikes/.env (see spikes/.env.example).")
    return value


def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
