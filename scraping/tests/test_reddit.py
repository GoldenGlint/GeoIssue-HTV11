"""Offline Reddit (Arctic Shift) normalization and paging."""

from datetime import datetime, timedelta, timezone
import unittest

from scraping.collectors import reddit


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=7)


def post(key="abc123", **overrides):
    value = {
        "id": key, "created_utc": int((NOW - timedelta(hours=2)).timestamp()),
        "title": "Bike lane removal on Bloor, thanks u/someone_here",
        "selftext": "", "author": "poster", "over_18": False, "spoiler": False,
        "removed_by_category": None, "post_hint": "image",
        "url": f"https://i.redd.it/{key}xyz.jpeg",
        "permalink": f"/r/toronto/comments/{key}/bike_lane_removal/",
        "link_flair_text": "Picture",
    }
    value.update(overrides)
    return value


class Response:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload

    def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []

    def get(self, url, **kwargs):
        self.calls.append(kwargs["params"])
        return next(self.responses)


class RedditTests(unittest.TestCase):
    def test_single_image_and_gallery_become_records(self):
        gallery = post("gal001", post_hint=None, url="https://www.reddit.com/gallery/gal001",
                       is_gallery=True,
                       gallery_data={"items": [{"media_id": "imgone1"}, {"media_id": "imgtwo2"},
                                               {"media_id": "gifthr3"}]},
                       media_metadata={
                           "imgone1": {"e": "Image", "id": "imgone1", "m": "image/jpg", "status": "valid"},
                           "imgtwo2": {"e": "Image", "id": "imgtwo2", "m": "image/png", "status": "valid"},
                           "gifthr3": {"e": "AnimatedImage", "id": "gifthr3", "m": "image/gif", "status": "valid"},
                       })
        records, stats = reddit.normalize([post(), gallery], since=SINCE, now=NOW)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].media_url, "https://i.redd.it/abc123xyz.jpeg")
        self.assertEqual([r.media_url for r in records[1:]],
                         ["https://i.redd.it/imgone1.jpg", "https://i.redd.it/imgtwo2.png"])
        self.assertTrue(records[0].post_id.startswith("https://www.reddit.com/r/toronto/comments/"))
        self.assertNotIn("someone_here", records[0].caption)

    def test_nsfw_removed_crosspost_old_and_link_posts_are_skipped(self):
        values = [post("nsfw01", over_18=True), post("remov1", removed_by_category="moderator"),
                  post("cross1", crosspost_parent="t3_x"),
                  post("old001", created_utc=int((SINCE - timedelta(days=1)).timestamp())),
                  post("link01", post_hint="link", url="https://example.com/story")]
        records, stats = reddit.normalize(values, since=SINCE, now=NOW)
        self.assertEqual(records, [])
        self.assertEqual(stats["nsfw_or_spoiler_skipped"], 1)
        self.assertEqual(stats["removed_posts_skipped"], 1)
        self.assertEqual(stats["crossposts_skipped"], 1)
        self.assertEqual(stats["older_posts_skipped"], 1)
        self.assertEqual(stats["non_photo_posts_skipped"], 1)

    def test_retries_flaky_responses_and_records_subreddit(self):
        session = Session([Response(422, {}), Response(200, {"data": [post()]})])
        config = {"api": "https://arctic-shift.photon-reddit.com/api", "subreddits": ["toronto"],
                  "max_posts_per_subreddit": 600}
        posts, sources = reddit.collect(session, config, since=SINCE, until=NOW, retry_wait=0)
        self.assertEqual(len(posts), 1)
        self.assertEqual(sources[0]["errors"], [])
        self.assertEqual(posts[0]["_found_by"], ["subreddit:toronto"])


if __name__ == "__main__":
    unittest.main()
