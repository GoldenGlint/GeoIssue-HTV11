# Collection controls and model handoff

Updated October 17, 2026. This work supplies candidate images and provenance to the identification-model owner. **Default path is review-free:** collect → Gemini screen → grouped handoff → Gemini descriptions. Each post group includes recent, locatable Toronto issue candidates plus separately labelled eligible companion photos. See [SCREENING.md](SCREENING.md).

## What currently works

| Platform | Collector | Observed status |
| --- | --- | --- |
| Bluesky | Public HTTP search and author feeds | Live and training pools; drops nudity/sexual/graphic safety labels |
| Mastodon | Public media hashtag timelines | Collector implemented; drops `sensitive` posts; feeds the same screener |
| Flickr | Geographic photo search | Collector implemented; blocked until `FLICKR_API_KEY` is set |
| Instagram | Apify | Expanded live pilot: 19 photos from ten posts; first-pass candidate rejected by detailed assessment. Prefer curated URLs over broad tags |
| Instagram | Instaloader | Local authenticated location collector; no successful live batch recorded here |
| Screening | Gemini free-tier REST | `scraping.screen` answers Toronto / issue / locatability; human review optional |

The combined gallery at **http://127.0.0.1:8767/** includes Instagram and Bluesky sample batches used to validate screening once. After screening, cards show Gemini verdicts for optional spot checks.

## Two pools

| Pool | Posting window | Purpose |
| --- | --- | --- |
| `live` | 1–7 days | Current-issue candidates; refreshed and age-pruned |
| `training` | up to 365 days | Issue-detector training; age is not a defect |

## Edit Bluesky inputs

Edit [bluesky-queries.txt](../config/bluesky-queries.txt) and optional [bluesky-authors.txt](../config/bluesky-authors.txt). At most **50** queries plus author feeds per run.

```sh
.venv/bin/python -m scraping.collectors.bluesky \
  --query-file scraping/config/bluesky-queries.txt \
  --author-file scraping/config/bluesky-authors.txt \
  --pool live --days 7 --max-posts 50 --max-pages 2 --max-images 200 \
  --output scraping/data/bluesky-live

.venv/bin/python -m scraping.screen --batch scraping/data/bluesky-live
```

Instagram inputs remain public profile/post/tag URLs for Apify and a location ID for Instaloader. Apify keeps its spending checks and ten-post cap.

## Combine saved sources

```sh
.venv/bin/python -m scraping.demo merge \
  --batch scraping/data/review-demo \
  --batch scraping/data/bluesky \
  --batch scraping/data/targeted-toronto \
  --out scraping/data/combined-next

.venv/bin/python -m scraping.demo serve --out scraping/data/combined-next --port 8767
```

Choose a new output directory. Stop the existing server on that port before starting another. Merge copies saved local images without network calls, retains platform identity, combines repeated media keys, excludes exact pixel-hash duplicates across platforms, and preserves the source batches. Similar reposts may still require review. Conflicting saved versions of one image require selecting the intended source batch.

Combined galleries and their manifests are snapshots. Revalidate source records with their collectors and rebuild the combined set before a later handoff or public use. They do not automatically inherit later edits/deletions from source galleries. The model worker must also recheck the time window when consuming a saved manifest.

## Freshness and notifications

Use separate posting, capture, and condition-verification evidence:

- **Posting window:** prioritize the last 72 hours for triage; use up to seven days for the demo discovery pool. Retain known timestamps and sort newest first. The current gallery uses a seven-day recent-upload view.
- **Capture age:** a recent upload can contain a five-year-old pothole. Known old capture times are screened by the existing collector window. Explicit historical captions and older English month/year hints are flagged for review and excluded from the recent candidate handoff. These conservative hints are not a complete historical-image detector.
- **Unknown capture age:** retain the image as an unverified model candidate, clearly labelled as upload-date evidence only. Do not claim the condition is fresh.
- **Notifications:** every generated freshness assessment has `alert_eligible: false`. Scene usefulness and a visible-defect prediction do not override it. Any future notification service needs a separate current-condition and location verification step, and must recheck evidence age immediately before sending. No notification service or verification override is implemented here.
- **References:** older Mapillary/Commons imagery can support location matching, but cannot establish that a pothole or obstruction is still present. Keep reference imagery separate from current observations.

## Handoff to the model owner

The combined batch contains:

- `images/`: local JPEG derivatives with metadata removed.
- `media.jsonl`: all normalized records, including excluded and historical/review examples.
- `recent-candidates.jsonl`: technically ready recent-upload candidates, with explicit historical/age-review flags omitted. This still contains noise, possibly non-Toronto scenes, and unknown capture ages.
- `report.json`: source-batch names and collection/review counts.

The next stage should read **`scraping/data/handoff/post-groups.jsonl`** for passed images, same-post companions, and detailed issue assessments. **`passed.jsonl`** remains the flat list of independently passed images; companions never enter that list. Build with `python -m scraping.handoff`, then run `python -m scraping.describe`, or restore shared results with `python -m scraping.share pull`. Teammates do not need to re-scrape: `scraping/shared/` holds passed records, groups, descriptions and screening results as text, and images are re-downloaded and checked by `sha256`. Raw source-image batches stay local; the analysis exports the app’s displayed evidence photos into `data/analyzed/photos/` for inclusion with the public app data. The local page shows passed images and clearly distinguished context photos and does not collect labels. `blur_before_public_display` is retained as screening metadata; the current photo-display policy permits full collected photos, so the default analysis configuration does not withhold them.

`local_path` is relative to the batch. Each record retains `platform`, `collector`, `post_id`, `media_index`, caption/alt text, posting time, optional capture time, location claims, hashes, automatic status, freshness, and screening fields when present.

Split evaluation by parent post/duplicate/event group. Four photos of one drain are one candidate event. A useful street photo with no defect is a valid negative example.

Grow volume with wider Bluesky queries, Mastodon tags, training-pool windows, and Flickr once a key exists. Free-tier Gemini caps daily screening (~order of 1,000 requests/day; verify on your key). See [SCREENING.md](SCREENING.md) for the repeat schedule.

## Expansion status

1. **Mastodon:** collector at `scraping.collectors.mastodon` with [mastodon.json](../config/mastodon.json). Prior access probe: [mastodon-access-results.json](../research/results/mastodon-access-results.json).
2. **Flickr:** collector ready; needs `FLICKR_API_KEY`. See [flickr-access-results.json](../research/results/flickr-access-results.json).
3. **Instagram via Apify:** the October 17 continuation tested `BikeTO` and `TorontoConstruction` over seven days. Ten posts supplied 19 downloaded photos; 18 were screened and one was skipped by the problem-word prefilter. One street-work / bike-lane-removal photo passed the first screen, but the detailed assessment returned `issue_supported: no` (routine roadway work without a clear visible defect). It remains labelled **Needs review** in the handoff; no supported new issue example was added. The run used **US$0.027 in verified free credit, US$0 paid**, under its US$0.05 cap. Infographics and contractor ads remain common. See the [sanitized results](../research/results/instagram-expansion-results.json). The local batch is `scraping/data/instagram-apify-live-20261017`; `scraping/data/handoff-expanded-20261017` combines its candidate with the existing Bluesky, Mastodon and Reddit batches.
4. **Mapillary:** reference/geolocation evaluation only; not a fresh-issue feed.
5. **Next source choice:** [Flickr photo search](https://www.flickr.com/services/api/flickr.photos.search.html) is the next official photo API to try once an application key is available; it supports geographic bounds, dates and photo-only results. For another social network, pilot a few curated public Facebook Pages using [Apify's Facebook Posts Scraper](https://apify.com/apify/facebook-posts-scraper); its input schema documents public Page URLs and its output includes images. Facebook collection is not implemented here yet. Check its account pricing and apply a separate bounded free-credit pilot before running it.
