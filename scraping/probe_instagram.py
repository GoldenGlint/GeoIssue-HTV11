"""Compatibility entry point for research/instagram_probe.py, including direct execution."""

import sys

if not __package__:
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.research.instagram_probe import *

if __name__ == "__main__":
    raise SystemExit(main())
