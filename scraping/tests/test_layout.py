"""Integration checks for the reorganized module and on-disk boundaries."""

from pathlib import Path
import subprocess
import sys
import unittest

from scraping import apify as legacy_apify, bluesky as legacy_bluesky
from scraping.collectors import bluesky, instagram_apify, instagram_local
from scraping.paths import CONFIG, DATA, REVIEW_TEMPLATE, ROOT


class LayoutTests(unittest.TestCase):
    def test_legacy_imports_and_default_paths_still_target_the_same_local_data(self):
        self.assertIs(legacy_bluesky.run, bluesky.run)
        self.assertIs(legacy_apify.collect, instagram_apify.collect)
        self.assertEqual(bluesky.DEFAULT_OUTPUT, DATA / "bluesky")
        self.assertEqual(instagram_local.SESSION_FILE, DATA / "instaloader/session.json")
        self.assertEqual(ROOT, Path(__file__).resolve().parents[1])
        self.assertTrue(REVIEW_TEMPLATE.is_file())
        self.assertEqual(bluesky.load_queries(CONFIG / "bluesky-queries.txt"),
                         bluesky.load_queries(ROOT / "bluesky-queries.txt"))

    def test_core_collectors_do_not_import_optional_instagram_sdks_or_research(self):
        script = """
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in ('instaloader', 'gallery_dl'):
        raise AssertionError('Optional SDK imported by base workflow')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import scraping.media, scraping.demo, scraping.collectors.bluesky, scraping.collectors.instagram_apify
assert 'scraping.research.instagram_probe' not in sys.modules
"""
        subprocess.run([sys.executable, "-c", script], cwd=ROOT.parent, check=True,
                       capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
