"""Check actual extraction failures and target boundaries without network access."""

import unittest
from unittest.mock import patch

from scraping.research.instagram_probe import clean_error, gallery_result, target_kind
from scraping.research import instagram_probe
from scraping.paths import ROOT


class ProbeTests(unittest.TestCase):
    def test_worker_uses_the_relocated_module_from_the_project_root(self):
        arguments = ["probe", "instaloader", "https://www.instagram.com/example/", "--limit", "1"]
        with patch("sys.argv", arguments), \
                patch.object(instagram_probe.importlib.metadata, "version", return_value="fixture"), \
                patch.object(instagram_probe.subprocess, "Popen") as start, patch("builtins.print"):
            start.return_value.communicate.return_value = ('{"status":"ok"}', '')
            self.assertEqual(instagram_probe.main(), 0)
            self.assertEqual(start.call_args.args[0][1:3], ["-m", "scraping.research.instagram_probe"])
            self.assertEqual(start.call_args.kwargs["cwd"], ROOT.parent)

    def test_error_payload_is_failure_even_when_process_exits_zero(self):
        result = gallery_result([[-1, {"error": "AbortExtraction",
                                      "message": "Redirect to login"}]])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["image_url_count"], 0)

    def test_profile_dispatch_is_not_mistaken_for_extracted_media(self):
        result = gallery_result([[6, "https://www.instagram.com/example/posts/", {}]])
        self.assertEqual(result["status"], "unresolved")

    def test_partial_results_do_not_hide_errors(self):
        result = gallery_result([[2, {}], [3, "https://cdn.example/photo.jpg", {}],
                                 [-1, {"error": "HTTPError"}]])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["post_count"], 1)

    def test_only_plain_instagram_targets_are_accepted(self):
        self.assertEqual(target_kind("https://www.instagram.com/example/"), "profile")
        self.assertEqual(target_kind("https://www.instagram.com/p/Ab_C-1/"), "post")
        self.assertEqual(target_kind("https://www.instagram.com/explore/tags/toronto/"), "hashtag")
        for url in ("https://instagram.com.evil.test/example/", "http://instagram.com/example/",
                    "https://www.instagram.com/example/?sessionid=secret"):
            with self.assertRaises(ValueError):
                target_kind(url)

    def test_report_does_not_echo_target_or_request_url(self):
        text = clean_error("example received 401 at https://api.example/?secret=value",
                           "https://www.instagram.com/example/")
        self.assertNotIn("secret", text)
        self.assertNotIn("example", text)
        self.assertIn("401", text)


if __name__ == "__main__":
    unittest.main()
