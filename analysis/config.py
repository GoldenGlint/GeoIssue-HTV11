"""Loads config.toml. Relative paths in it are resolved from the repository root."""
import tomllib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.toml"


def setting(name, default=None):
    """Server-side environment lookup shared by the API and optional Tiger importer."""
    if os.environ.get(name):
        return os.environ[name]
    for file in (".env", "spikes/.env"):
        path = ROOT / file
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip().removeprefix("export ").strip() == name:
                    return value.strip().strip("'\"") or default
    return default


def load(path=None):
    with open(path or DEFAULT_CONFIG, "rb") as f:
        return tomllib.load(f)


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def stage(config, name):
    """Settings for one stage. A stage missing from the config counts as disabled."""
    return config.get("stages", {}).get(name, {"enabled": False})


def enabled(config, name):
    return bool(stage(config, name).get("enabled", False))
