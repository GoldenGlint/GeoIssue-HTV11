"""Offline Mastodon normalization and sensitive-post handling."""

from datetime import datetime, timedelta, timezone
import unittest

from scraping.collectors import mastodon


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=7)


def status(key="one", *, sensitive=False, media=True, created=None):
    created = (created or NOW).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    item = {
        "id": key,
        "uri": f"https://mastodon.social/users/x/statuses/{key}",
        "url": f"https://mastodon.social/@x/{key}",
        "created_at": created,
        "sensitive": sensitive,
        "visibility": "public",
        "content": "<p>Toronto sidewalk @someone</p>",
        "reblog": None,
        "media_attachments": [],
    }
    if media:
        item["media_attachments"] = [{
            "id": f"m{key}", "type": "image",
            "url": f"https://files.mastodon.social/media_attachments/files/{key}.jpg",
            "description": "Street photo",
        }]
    return item


class MastodonTests(unittest.TestCase):
    def test_sensitive_and_boosts_are_skipped(self):
        values = [status("ok"), status("nsfw", sensitive=True)]
        values.append({**status("boost"), "reblog": status("other")})
        records, stats, hosts = mastodon.normalize(values, since=SINCE, now=NOW)
        self.assertEqual(len(records), 1)
        self.assertEqual(stats["sensitive_skipped"], 2)
        self.assertIn("files.mastodon.social", hosts)
        self.assertNotIn("@someone", records[0].caption)

    def test_html_caption_becomes_plain_text(self):
        self.assertEqual(mastodon.html_to_text("<p>Hello<br>world</p>"), "Hello\nworld")


if __name__ == "__main__":
    unittest.main()
