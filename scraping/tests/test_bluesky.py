"""Offline checks for photo ownership, pagination, persistent state, and deletions."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scraping.collectors import bluesky
from scraping.media import read_jsonl


NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=7)


def post(key="one", count=1, cid="bafkqaaa"):
    return {
        "uri": f"at://did:plc:synthetic/app.bsky.feed.post/{key}",
        "record": {"createdAt": NOW.isoformat(), "text": "Toronto @example.test @account-with-hyphens.example https://example.test/",
                   "embed": {"$type": "app.bsky.embed.images", "images": [
                       {"image": {"ref": {"$link": cid + str(i)}}} for i in range(count)]}},
        "author": {"handle": "never-persist.example", "displayName": "Not retained"},
        "embed": {"$type": "app.bsky.embed.images#view", "images": [
            {"fullsize": f"https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:synthetic/{cid}{i}@jpeg",
             "alt": f"Street photograph {i} @example.test"} for i in range(count)]},
    }


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


class Session:
    def __init__(self, payloads):
        self.payloads, self.calls, self.headers = iter(payloads), [], {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(next(self.payloads))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def image_bytes(color="red"):
    output = BytesIO()
    Image.new("RGB", (200, 200), color).save(output, format="PNG")
    return output.getvalue()


class NormalizeTests(unittest.TestCase):
    def test_individual_images_have_stable_shared_schema_and_no_author_fields(self):
        records, stats = bluesky.normalize([post(count=2), post(count=2)], since=SINCE, now=NOW)
        self.assertEqual([record.media_index for record in records], [0, 1])
        self.assertEqual(stats["duplicate_media_keys"], 2)
        self.assertTrue(all(record.platform == "bluesky" and record.schema_version == 1 for record in records))
        self.assertEqual(records[0].location_evidence, [])
        self.assertNotIn("@example", records[0].caption)
        self.assertNotIn("hyphens.example", records[0].caption)
        self.assertNotIn("author", records[0].__dict__)

    def test_quote_with_own_media_uses_only_the_own_photos(self):
        value = post(count=2)
        value["embed"] = {"$type": "app.bsky.embed.recordWithMedia#view", "media": value["embed"],
                          "record": {"embeds": [post("someone-else")["embed"]]}}
        value["record"]["embed"] = {"$type": "app.bsky.embed.recordWithMedia",
                                     "media": value["record"]["embed"]}
        records, _ = bluesky.normalize([value], since=SINCE, now=NOW)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.post_id == value["uri"] for record in records))

    def test_link_cards_quoted_images_and_video_covers_are_not_photo_evidence(self):
        values = []
        for kind in ("external", "record", "video"):
            value = post(kind)
            value["embed"] = {"$type": f"app.bsky.embed.{kind}#view", "thumbnail": "cover.jpg",
                              "images": post()["embed"]["images"]}
            values.append(value)
        records, stats = bluesky.normalize(values, since=SINCE, now=NOW)
        self.assertEqual(records, [])
        self.assertEqual(stats["non_photo_posts_skipped"], 3)

    def test_invalid_url_does_not_shift_other_image_positions(self):
        value = post(count=2)
        value["embed"]["images"][0]["fullsize"] = "https://cdn.bsky.app.evil.test/photo.jpg"
        records, stats = bluesky.normalize([value], since=SINCE, now=NOW)
        self.assertEqual([record.media_index for record in records], [1])
        self.assertEqual(stats["invalid_images"], 1)

    def test_old_future_and_unknown_times_do_not_enter_the_recent_set(self):
        values = [post("old"), post("future"), post("unknown")]
        values[0]["record"]["createdAt"] = (SINCE - timedelta(seconds=1)).isoformat()
        values[1]["record"]["createdAt"] = (NOW + timedelta(hours=1)).isoformat()
        values[2]["record"].pop("createdAt")
        records, stats = bluesky.normalize(values, since=SINCE, now=NOW)
        self.assertEqual(records, [])
        self.assertEqual(stats["older_posts_skipped"], 1)
        self.assertEqual(stats["future_posts_skipped"], 1)
        self.assertEqual(stats["invalid_posts"], 1)

    def test_safety_labels_on_post_self_or_author_skip_the_whole_post(self):
        values = [post("mod"), post("self"), post("author"), post("ok")]
        values[0]["labels"] = [{"val": "nudity"}]
        values[1]["record"]["labels"] = {"values": [{"val": "porn"}]}
        values[2]["author"]["labels"] = [{"val": "graphic-media"}]
        records, stats = bluesky.normalize(values, since=SINCE, now=NOW)
        self.assertEqual([record.post_id for record in records], [values[3]["uri"]])
        self.assertEqual(stats["safety_labeled_posts_skipped"], 3)


class CollectionTests(unittest.TestCase):
    def test_query_file_preserves_hashtags_and_rejects_empty_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queries.txt"
            path.write_text("# Comment\n\nToronto sidewalk\n#BikeTO\nToronto sidewalk\n")
            self.assertEqual(bluesky.load_queries(path), ["Toronto sidewalk", "#BikeTO"])
            path.write_text("# No active queries\n")
            with self.assertRaises(ValueError):
                bluesky.load_queries(path)

    def test_pagination_is_bounded_and_uses_the_correct_host_without_auth(self):
        session = Session([{"posts": [post()], "cursor": "next"}, {"posts": [post("two")]}])
        posts, sources = bluesky.collect(session, ["Toronto"], [], since=SINCE, until=NOW, max_posts=2)
        self.assertEqual(len(posts), 2)
        self.assertEqual(sources[0]["pages"], 2)
        self.assertEqual(session.calls[1][1]["params"]["cursor"], "next")
        self.assertEqual(session.calls[1][1]["params"]["limit"], 1)
        self.assertTrue(session.calls[0][0].startswith("https://api.bsky.app/xrpc/"))
        self.assertNotIn("headers", session.calls[0][1])

    def test_hashtag_search_skips_date_filter_and_records_which_search_found_it(self):
        session = Session([{"posts": [post()]}, {"posts": [post()]}])
        posts, _ = bluesky.collect(session, ["#BikeTO", "Toronto"], [], since=SINCE, until=NOW)
        self.assertNotIn("since", session.calls[0][1]["params"])
        self.assertIn("since", session.calls[1][1]["params"])
        records, _ = bluesky.normalize(posts, since=SINCE, now=NOW)
        self.assertEqual(records[0].found_by, ["query:#BikeTO", "query:Toronto"])

    def test_403_on_a_later_page_keeps_earlier_pages_without_an_error(self):
        class Forbidden(Session):
            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if len(self.calls) > 1:
                    return Response({}, status=403)
                return Response({"posts": [post()], "cursor": "next"})
        posts, sources = bluesky.collect(Forbidden([]), ["Toronto"], [], since=SINCE, until=NOW)
        self.assertEqual(len(posts), 1)
        self.assertEqual(sources[0]["errors"], [])
        self.assertIn("paging_stopped", sources[0])

    def test_repeated_cursor_stops_and_partial_source_is_reported(self):
        session = Session([{"posts": [post()], "cursor": "same"},
                           {"posts": [post()], "cursor": "same"}])
        _, sources = bluesky.collect(session, ["Toronto"], [], since=SINCE, until=NOW)
        self.assertEqual(sources[0]["pages"], 2)
        self.assertTrue(sources[0]["errors"])

    def test_author_reposts_are_not_new_original_posts(self):
        session = Session([{"feed": [{"post": post(), "reason": {"$type": "app.bsky.feed.defs#reasonRepost"}},
                                     {"post": post("original")}]}])
        posts, sources = bluesky.collect(session, [], ["example.test"], since=SINCE, until=NOW)
        self.assertEqual(len(posts), 1)
        self.assertEqual(sources[0]["reposts_skipped"], 1)
        self.assertNotIn("example.test", json.dumps(sources))


class PersistenceTests(unittest.TestCase):
    def test_repeat_run_reuses_images_and_changed_media_is_downloaded(self):
        records, _ = bluesky.normalize([post()], since=SINCE, now=NOW)
        changed, _ = bluesky.normalize([post(cid="bafkreplacement")], since=SINCE, now=NOW)
        with tempfile.TemporaryDirectory() as folder, patch("scraping.media.fetch_image", return_value=image_bytes()) as fetch:
            rows, _ = bluesky.save(records, [], folder, since=SINCE)
            repeated, stats = bluesky.save(records, rows, folder, since=SINCE)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(stats["media_reused"], 1)
            self.assertEqual(len(repeated), 1)
            bluesky.save(changed, repeated, folder, since=SINCE)
            self.assertEqual(fetch.call_count, 2)

    def test_identical_pixels_across_runs_are_excluded(self):
        first, _ = bluesky.normalize([post()], since=SINCE, now=NOW)
        second, _ = bluesky.normalize([post("two")], since=SINCE, now=NOW)
        with tempfile.TemporaryDirectory() as folder, patch("scraping.media.fetch_image", return_value=image_bytes()):
            rows, _ = bluesky.save(first, [], folder, since=SINCE)
            rows, _ = bluesky.save(first + second, rows, folder, since=SINCE)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["auto_status"], "excluded")
            self.assertEqual(rows[1]["duplicate_of"], rows[0]["key"])

    def test_failed_staging_preserves_previous_manifest(self):
        records, _ = bluesky.normalize([post()], since=SINCE, now=NOW)
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "media.jsonl"
            manifest.write_text("previous-content\n")
            with patch("scraping.collectors.bluesky.process_media", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    bluesky.save(records, [], folder, since=SINCE)
            self.assertEqual(manifest.read_text(), "previous-content\n")

    def test_missing_post_is_rechecked_removed_and_its_image_deleted(self):
        records, _ = bluesky.normalize([post()], since=SINCE, now=NOW)
        with tempfile.TemporaryDirectory() as folder, patch("scraping.media.fetch_image", return_value=image_bytes()):
            rows, _ = bluesky.save(records, [], folder, since=SINCE)
            image = Path(folder) / rows[0]["local_path"]
            session = Session([{"posts": []}, {"posts": []}])
            with patch("scraping.collectors.bluesky.requests.Session", return_value=session), patch("scraping.collectors.bluesky.write_gallery"):
                report = bluesky.run(queries=["Toronto"], output=folder)
            self.assertEqual(report["posts_unavailable_on_refresh"], 1)
            self.assertEqual(read_jsonl(Path(folder) / "media.jsonl"), [])
            self.assertFalse(image.exists())

    def test_other_platform_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "media.jsonl"
            original = '{"platform":"instagram"}\n'
            manifest.write_text(original)
            with self.assertRaisesRegex(ValueError, "another platform"):
                bluesky.run(queries=["Toronto"], output=folder)
            self.assertEqual(manifest.read_text(), original)
            self.assertFalse((Path(folder) / ".bluesky.lock").exists())


if __name__ == "__main__":
    unittest.main()
