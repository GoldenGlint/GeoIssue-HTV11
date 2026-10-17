# Standalone collection demo

The demo is running locally at **http://127.0.0.1:8765**. It contains real Instagram images collected through Apify. Viewing, refreshing, labeling, and exporting this gallery do not call Apify or start another scrape.

## What was collected

The October 17 pilot used about **US$0.0324 of free credit**, with **US$0 paid**, below the requested US$0.05 total. The account was verified as an enabled, non-paying Free-plan account before collection.

| Result | Count |
| --- | --- |
| Returned items, including one source error | 12 |
| Posts with photos | 9 |
| Individual images, including carousel slides | 24 |
| Successful image downloads | 24 |
| Video posts skipped | 2 |
| Source queries returning no items | 1 |

The first account-feed test returned mostly video; the hashtag test returned 23 images from eight posts. The sample includes advertisements and other noisy Toronto-tagged content. This is a small feasibility sample, not a representative sample of Toronto or a measured civic-issue detection benchmark. The sanitized summary is in [apify-demo-results.json](../research/results/apify-demo-results.json).

## Try the existing sample

Use the gallery's **Useful / Noise / Unsure** controls, select a reason for noise, and assess visible civic issues separately. Open an image to inspect it at full size. Search and filter the results, then download labels or export useful records.

Labels are stored in your browser. Download them before clearing browser storage. There are initially no approved images: successful scraping does not make a photo useful or verify its location.

To start the gallery again from the repository root:

```sh
.venv/bin/python -m scraping.demo serve --out scraping/data/review-demo --port 8765
```

Only the selected data directory is served, on `127.0.0.1`. The repository and `.env` are outside the served directory. Images are temporary local review data and are excluded from Git.

## Setup on another machine

Python 3.12 or newer is recommended. The demo itself needs only Requests and Pillow; it does not need a GPU, frontend build, database, or paid vision API.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scraping/requirements.txt
```

Keep the Apify token in `scraping/.env` using the format in [.env.example](../.env.example). It is never embedded in the gallery or passed in an API URL. Existing gallery review and imports do not need the token.

## Collect, resume, or import

Starting a new collection consumes free credit. New runs are explicitly requested from the command line; the browser has no run-start button or background polling. The current live adapter accepts at most ten requested posts and hard-rejects a cap above US$0.05 **per run**. The already-completed pilot's combined usage stayed below US$0.05; this is not a recurring monthly allowance for the demo.

```sh
# Starts one new run; use an intentional new output directory.
.venv/bin/python -m scraping.demo collect --url https://www.instagram.com/PUBLIC_ACCOUNT/ --limit 5 --days 7 --out scraping/data/new-pilot

# Reuses an existing run ID. Does not launch another actor.
.venv/bin/python -m scraping.demo resume --out scraping/data/new-pilot

# Uses an existing Apify JSON export. No actor run or account access.
.venv/bin/python -m scraping.demo import-apify /path/to/export.json --out scraping/data/imported

# Imports normalized records produced by another tool or social platform.
.venv/bin/python -m scraping.demo import-records /path/to/source-records.jsonl --allow-host cdn.example.org --out scraping/data/another-source
```

An import downloads the supplied image URLs from explicitly allowed hosts. Reopening the already-generated gallery needs neither downloads nor an API call.

Live requests verify the Free plan, zero subscription price, non-paying status, remaining credit, and the actor's current minimum cap. They send Apify's `maxTotalChargeUsd`, disable automatic restart, and use a server-side timeout. A saved launch intent blocks blind retry if the start response is lost; use the saved run ID/Apify Console to resolve it. The code never upgrades the plan or increases the cap to make a run work.

Export an approved set using downloaded labels:

```sh
.venv/bin/python -m scraping.demo export --out scraping/data/review-demo --labels ~/Downloads/civiclens-labels.json
```

This writes `accepted.jsonl`. Unknown batch/image identifiers and invalid labels are rejected. Only explicitly useful images that passed the automatic checks enter the accepted set. A useful street photo can have **no visible issue**.

## What the current filters do

Automatic: validate image URLs and redirects, bound downloads/decoded size, skip video covers, preserve carousel positions, remove exact image duplicates, screen known old posting/capture dates, flag similar/small images, and re-encode derivatives without EXIF. Source errors remain visible in the report.

Review labels: posters/ads, food/products, screenshots/memes, people as subjects, private places, misleading Toronto tags, and visible civic issues. **A runtime automatic poster/issue classifier is not implemented yet.** This demo produces a labeled evaluation set for that next step without spending on a vision API. Human checks are still needed for privacy, geography, and actual capture age.

## Integrate the collector into the app

The browser is optional. The app's worker can use these functions directly:

```python
from scraping.collectors.instagram_apify import IMAGE_HOSTS, normalize
from scraping.media import process_media

records, source_stats = normalize(apify_dataset_items)
rows = process_media(records, output_directory, hosts=IMAGE_HOSTS)
# Upsert rows in the app's database using row["key"].
```

The layers are separate:

| Layer | File | Responsibility |
| --- | --- | --- |
| Source adapter | [apify.py](../collectors/instagram_apify.py) | Apify requests, spending checks, and conversion of its response |
| Common record and image pipeline | [media.py](../media.py) | Source-neutral validation, downloads, derivatives, deduplication, date screening, and exports |
| Runner | [demo.py](../demo.py) | Collection/import/resume/export commands and localhost review |
| Review UI | [review.html](../templates/review.html) | Displays saved records and exports labels; never calls the scraper |

`MediaRecord` is the version-1 input contract: `platform`, `collector`, `post_id`, original `media_index`, `media_url`, timezone-aware `posted_at`, optional `captured_at`, caption/alt text, media ID, and location evidence. Missing capture time remains unknown. A place tag is stored as a place claim, not a verified camera position.

Processed records add a stable `key` (`platform:post_id:media_index`), `local_path`, dimensions, hashes, fetch time, automatic status, and reasons. The private exports retain provenance but omit author/profile/commenter fields; captions have account mentions and links redacted. They are not suitable as a public API response without the app's privacy handling.

To add another **tool for Instagram**, write one function returning `MediaRecord` objects from that tool's response. To add another **social platform**, do the same and supply that source's actual media-host allowlist. Both then reuse `process_media`, the review gallery, and accepted-record export. The separate [Bluesky collector](BLUESKY.md) in this workspace already uses that common record/pipeline interface.

## Verify requirements independently

```sh
# Apify spending, normalization, image pipeline, and export checks; no live calls.
.venv/bin/python -m unittest scraping.tests.test_demo -v

# All installed collector checks in this workspace.
.venv/bin/python -m unittest discover -s scraping/tests -t . -p 'test_*.py'
```

The checks cover paid/unknown account rejection, the five-cent cap, saved run IDs, resume without a new actor, carousel indexing, video-cover exclusion, source errors, stale imagery, metadata removal, duplicate pixels, unsafe redirects, explicit approval, and a different platform using the shared pipeline. Desktop/mobile browser checks also exercised labels, persistence, downloads, search/filtering, and all 24 local images.

The next visual-filter evaluation should compare predictions with reviewed labels, including rejected images, and report useful-scene precision/recall separately from civic-issue yield. This sample has no measured automatic visual-classifier accuracy.
