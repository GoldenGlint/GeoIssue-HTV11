"""Stable locations for local data, credentials, configuration, and UI assets."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = ROOT / "config"
REVIEW_TEMPLATE = ROOT / "templates" / "review.html"
