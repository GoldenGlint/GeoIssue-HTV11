# Image collection

One shared image pipeline, independent source collectors, automatic Gemini screening, and detailed issue descriptions using same-post photos together. Human review is optional. Bluesky, Mastodon, Reddit, Instagram, and Flickr adapters are implemented (Flickr needs an API key). See [COLLECTION.md](docs/COLLECTION.md) and [SCREENING.md](docs/SCREENING.md).

## Layout

```text
scraping/
  collectors/             Working source adapters
    bluesky.py
    mastodon.py
    reddit.py             Toronto subreddits via the Arctic Shift archive (no key)
    flickr.py
    instagram_apify.py
    instagram_local.py
    instagram_urls.py     Shared Instagram URL validation
  media.py                MediaRecord, downloads, dates, hashes, review exports
  screen.py               Gemini screening; passed.jsonl holds images that meet every rule
  handoff.py              Bundle passed images and labelled same-post companion photos
  describe.py             Detailed issue descriptions using each post's photos together
  probe_queries.py        Rank searches by recent problem-word photos (no downloads, no Gemini)
  share.py                Export/pull passed records and Gemini results via git (no images)
  shared/                 Shareable text: passed.jsonl, post-groups.jsonl, screening-cache.jsonl
  demo.py                 Collect/import/merge/export commands and local server
  paths.py                Stable data, configuration, and template locations
  config/                 Editable collection inputs
    bluesky-queries.txt
    bluesky-authors.txt
    mastodon.json
    flickr.json
  templates/              Review gallery template (optional spot checks)
  tests/                  Offline checks
  docs/                   Source guides, workflow, and findings
  research/               Diagnostic probes and sanitized results
  data/                   Ignored local samples and sessions; preserved in place
```

The small top-level `bluesky.py`, `apify.py`, `instagram_local.py`, and `probe_instagram.py` files forward older imports/commands to their new locations. Edit implementations in `collectors/` or `research/`. The old query-file path links to `config/bluesky-queries.txt`; there is one editable list.

## Setup and commands

From the repository root, using Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scraping/requirements.txt
```

The base requirements cover Bluesky, Apify HTTP calls, image processing, and the gallery. For local Instaloader collection, install `scraping/requirements-instagram.txt`; for the optional gallery-dl access probe, install `scraping/requirements-research.txt`. Each optional file includes the base requirements. The old Bluesky/demo requirement filenames include the same base file.

Add `GEMINI_API_KEY` (and optionally `FLICKR_API_KEY`) to [scraping/.env](.env.example). Edit [config/bluesky-queries.txt](config/bluesky-queries.txt), collect, then screen:

```sh
.venv/bin/python -m scraping.collectors.bluesky \
  --query-file scraping/config/bluesky-queries.txt \
  --pool live --days 7 --max-posts 50 --max-pages 2 --max-images 200 \
  --output scraping/data/bluesky-live
.venv/bin/python -m scraping.screen --batch scraping/data/bluesky-live
```

Mastodon and Reddit:

```sh
.venv/bin/python -m scraping.collectors.mastodon --output scraping/data/mastodon-live
.venv/bin/python -m scraping.collectors.reddit --output scraping/data/reddit-live
.venv/bin/python -m scraping.screen --batch scraping/data/reddit-live
```

To get the team's current passed images without scraping, run `.venv/bin/python -m scraping.share pull`.

Sign in to Instagram in your own terminal and run a small local location test:

```sh
.venv/bin/python -m scraping.collectors.instagram_local login
.venv/bin/python -m scraping.collectors.instagram_local collect --limit 10
```

For Apify, set `APIFY_TOKEN` in `scraping/.env` following [.env.example](.env.example), then use the explicit `scraping.demo collect` command in [DEMO.md](docs/DEMO.md). Its existing ten-post and US$0.05 free-credit cap still apply. Viewing/importing/merging saved batches does not launch a new run.

Review the existing combined sample, choosing an unused port:

```sh
.venv/bin/python -m scraping.demo serve --out scraping/data/combined-demo --port 8767
```

The server binds to localhost and only serves the selected ignored data directory. [COLLECTION.md](docs/COLLECTION.md) explains combining saved sources and the `recent-candidates.jsonl` handoff. Saved gallery snapshots are not automatically refreshed from source posts.

## Shared contract and adding a source

The integration path is **source response → MediaRecord → process_media → local batch → scraping.screen → scraping.handoff → scraping.describe**. The handoff keeps independently passed records in `passed.jsonl` and bundles them with explicitly labelled companion photos in `post-groups.jsonl`. Add an ordinary module in `collectors/`; no provider registry, inheritance hierarchy, or app/database dependency is needed.

1. Normalize only each post's own images into `MediaRecord`, preserving native post identity and original media index. A place tag is a claim, not a verified camera position. Keep capture time unknown when it is unknown.
2. Reuse `process_media` with that source's explicit HTTPS image-host allowlist. It handles bounded downloads, image decoding/derivatives, duplicate hashes, known date checks, and conservative freshness fields. Do not duplicate this processing in the adapter.
3. Write `media.jsonl` and a sanitized source report under a separate `data/` batch. Reuse `write_gallery`; feed saved batches to `scraping.demo merge` for multi-platform review. Public-facing data still needs the existing privacy/verification gates.
4. Add bounded pagination, source refresh/deletion handling, and an offline check for that source's actual response shapes. Keep network calls out of imports and out of ordinary tests. Source failures must remain explicit.

Research probes belong in `research/`; runtime collectors must not import them. Sanitized capability/volume reports go in `research/results/`. Keep tokens in the existing ignored `.env` and sessions under `data/`; moving implementation files must not change those locations.

## Freshness and model ownership

Posting time, capture time, and a verified current condition are separate facts. The gallery prioritizes recent uploads, flags historical clues, and displays unknown capture age. Every freshness assessment starts with `alert_eligible: false`; a future notification path must independently verify current condition and location and recheck age before sending.

Collection supplies images and provenance to the identification-model owner. It does not infer confirmed defects or precise locations. Reference images and historical examples must remain distinguishable from current observations. See [the full workflow and handoff](docs/COLLECTION.md).

## Checks and further reading

Install `requirements-instagram.txt` to run the full suite, which includes the local Instagram adapter:

```sh
.venv/bin/python -m unittest discover -s scraping/tests -t . -p 'test_*.py'
```

- [Bluesky collector](docs/BLUESKY.md)
- [Reddit collector](docs/REDDIT.md)
- [Screening, prefilter, handoff and sharing](docs/SCREENING.md)
- [Instagram local setup and access evaluation](docs/INSTAGRAM.md)
- [Apify demo, imports, and review exports](docs/DEMO.md)
- [Collection controls, freshness, and model handoff](docs/COLLECTION.md)
- [Next-source expansion plan: Mastodon, then Flickr](docs/SOURCE-EXPANSION-PLAN.md)
- [Targeted discovery findings](docs/TARGETED-DISCOVERY.md)
