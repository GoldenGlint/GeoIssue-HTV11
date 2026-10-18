"""Toronto Open Data (CKAN) helpers: list and download dataset resources.

    .venv/Scripts/python -m spikes.common.opendata list toronto-centreline-tcl
    .venv/Scripts/python -m spikes.common.opendata get toronto-centreline-tcl "4326.geojson"
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from spikes.common.config import DATA, USER_AGENT, ensure_dirs

CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
OPENDATA_DIR = DATA / "opendata"


def resources(slug: str) -> list[dict]:
    r = httpx.get(f"{CKAN}/package_show", params={"id": slug}, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["resources"]


def download(slug: str, name_contains: str) -> Path:
    """Download the first resource whose name or URL contains `name_contains` (case-insensitive)."""
    ensure_dirs(OPENDATA_DIR)
    needle = name_contains.lower()
    for res in resources(slug):
        label = f"{res.get('name', '')} {res.get('url', '')}".lower()
        if needle in label:
            url = res["url"]
            suffix = Path(url.split("?")[0]).suffix or f".{res.get('format', 'dat').lower()}"
            dest = OPENDATA_DIR / f"{slug}{suffix}"
            if dest.exists() and dest.stat().st_size > 0:
                return dest
            with httpx.stream("GET", url, headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            return dest
    raise SystemExit(f"No resource in {slug} matching {name_contains!r}")


if __name__ == "__main__":
    cmd, slug = sys.argv[1], sys.argv[2]
    if cmd == "list":
        for res in resources(slug):
            print(f"{res.get('format', ''):8} {res.get('datastore_active')!s:5} {res.get('name')} :: {res.get('url')}")
    elif cmd == "get":
        print(download(slug, sys.argv[3]))
