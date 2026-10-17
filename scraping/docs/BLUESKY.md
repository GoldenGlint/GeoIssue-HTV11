# Standalone Bluesky collector

Bluesky works through direct public HTTP reads: no account, API key, Apify, or paid service is used by this collector. Search was verified against `https://api.bsky.app/xrpc/`; the equivalent search request at `public.api.bsky.app` returned HTTP 403 in this environment. Public author feeds also returned HTTP 200.

The collector is separate from the Instagram adapter and reuses `scraping.media.MediaRecord` and the existing image-processing functions. It does not read the Instagram token or modify its output directory.

The [live smoke-test summary](../research/results/bluesky-smoke-results.json) records 50 initial posts and 8 successful image downloads. A second run rechecked 7 retained posts, reused all 8 images, and downloaded one additional image. The sample currently contains 9 unreviewed images; these counts establish working collection, not useful-scene or civic-issue accuracy.

## Run

From the repository root, using Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scraping/requirements.txt
.venv/bin/python -m scraping.collectors.bluesky --query toronto --days 3 --max-posts 100 --max-images 20
```

If the project environment already has Requests and Pillow, no additional SDK is needed. Both dependencies are already used by the shared media pipeline.

More targeted searches and a curated public author feed:

```sh
.venv/bin/python -m scraping.collectors.bluesky --query "Toronto sidewalk" --query "Toronto flooding" --max-posts 50 --max-images 10
.venv/bin/python -m scraping.collectors.bluesky --author PUBLIC_HANDLE_OR_DID --days 7 --max-posts 100 --max-images 20
```

Replace `PUBLIC_HANDLE_OR_DID` with a public source you have selected. Queries and author feeds can be combined. With no source arguments, the query defaults to `toronto`.

For an editable search list, change [bluesky-queries.txt](../config/bluesky-queries.txt) and pass `--query-file`. Optional authors: [bluesky-authors.txt](../config/bluesky-authors.txt) with `--author-file`. At most **50** queries plus authors per run. Posts carrying nudity/sexual/graphic safety labels (moderation, self, or author) are skipped entirely.

- `--pool live|training`: live uses 1–7 days and up to 200 images/run; training allows up to 365 days and 1000 images/run.
- `--max-posts`: maximum posts inspected **per query/author**, default 100, maximum 500.
- `--max-pages`: maximum pages **per query/author**, default 5, maximum 20.
- `--max-images`: maximum new/replacement image download attempts **for the entire run**.
- `--days`: posting window for the selected pool.
- `--output`: defaults to `scraping/data/bluesky/`, which is gitignored.

After collection, run `python -m scraping.screen --batch <output>` ([SCREENING.md](SCREENING.md)).

## Output

| File | Purpose |
| --- | --- |
| `media.jsonl` | Shared, version-1 image records plus download status, dimensions, hashes, and relative image paths |
| `images/` | Local JPEG derivatives; metadata is stripped by the shared image pipeline |
| `bluesky-report.json` | Source/page counts, filtering decisions, failures, reuse, and refresh results |
| `index.html`, `data.js`, `report.json` | The shared review gallery, when `scraping/templates/review.html` is available |

Native post URIs and image CIDs provide identity. Author profile objects and handles are omitted; captions and alt text use the shared mention/link redaction. Native URIs still identify source posts, so the output is restricted local staging. Text redaction and EXIF removal do not anonymize people in image pixels.

`ready` means an image was technically downloaded and decoded. It does **not** mean the scene is useful, safe to publish, in Toronto, or a confirmed civic issue. Poster/graphic rejection, privacy checks, and issue classification belong to the shared review/filter stage. A Toronto search match is only a discovery clue. Upload time is available; capture time remains unknown.

Records now include a conservative `freshness` assessment. Historical-caption hints require age review; unknown capture time remains unknown even after a recent upload. Every assessment starts with `alert_eligible: false`. Any future notification path must independently verify current condition and location, then recheck age before sending. The gallery defaults to recent uploads, newest first, and excludes historical-caption review flags from that view.

## What is extracted

- A post's directly attached photographs, one record per image.
- The post's own photographs in a quote-with-media post.
- Original image positions, alt text, posting timestamps, and content identities.

Link-card thumbnails, video covers, quoted-post images, and author-feed reposts are skipped. A thumbnail-only image attachment can be retained if no full-size URL is supplied; the report counts that fallback. Only HTTPS image URLs under `cdn.bsky.app` are downloaded.

The HTTP collector currently provides bounded search and author-feed polling, not a complete citywide archive or a live firehose. Search results are indexed and need not be exhaustive. Low issue yield or many irrelevant photos must be measured on the actual sample.

## Repeat runs, updates, and deletion

Each run rechecks retained post IDs with `getPosts`, in batches of 25. Posts no longer available in that response are removed, including their unreferenced local image files. Changed image CIDs are processed again. Unchanged images are reused; exact-pixel duplicates are marked across runs. Near-duplicate hints within a new batch are supplied by the shared pipeline.

Older records are removed according to the selected posting window on a successful run. This cleanup requires running the collector; stopping the collector does not schedule future deletion. Data remains local and unreviewed. Re-review a changed image rather than carrying an old approval forward by post ID alone.

Existing records are revalidated before saving. If refresh fails, or every requested source fails, the previous manifest is preserved and the command exits with an error. If some sources succeed, a partial run is reported explicitly. Downloads are staged and the manifest is replaced only after processing. A lock prevents simultaneous runs in the same output directory. After an interrupted process, remove `.bluesky.lock` only once that process has stopped.

Pending images beyond the download cap are reported as deferred. Run again to process more while retaining earlier images. This relies on those posts still appearing in the bounded query/feed results; it is not a durable backlog or a guarantee of exhaustive coverage.

## Integration

The source adapter exposes `collect()` and `normalize()`; both return ordinary Python data and the existing `MediaRecord` objects. `run()` adds local persistence and image downloads. Future app workers can invoke the same functions and replace local storage when necessary. The normalized fields use `media_url` and `posted_at`, matching the Instagram adapter.

Initial use does not need a database, a new server, or another source SDK. Jetstream can be added if continuous collection becomes necessary; there is no stream or scheduled background job in this implementation.

## Checks

```sh
.venv/bin/python -m unittest scraping.tests.test_bluesky -v
```

The offline checks cover photo ownership, stable image positions, link/video exclusions, time/host validation, bounded pagination, reposts, repeated-run reuse, changed content, duplicate pixels, staged failure, missing-post cleanup, and preservation of another platform's output.

References: [search API](https://docs.bsky.app/docs/api/app-bsky-feed-search-posts), [author-feed API](https://docs.bsky.app/docs/api/app-bsky-feed-get-author-feed), [post lookup](https://docs.bsky.app/docs/api/app-bsky-feed-get-posts), and [public Jetstream documentation](https://github.com/bluesky-social/jetstream-legacy). Live results, rather than documentation alone, establish which host worked in this environment.
