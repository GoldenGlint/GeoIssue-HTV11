# Image collection and Instagram evaluation

For the current platform status, editable searches, combined Instagram/Bluesky gallery, freshness rules, and identification-model handoff, start with [COLLECTION.md](COLLECTION.md). The combined gallery is at **http://127.0.0.1:8767/** while its local server is running. The Instagram-specific setup and pilot history follow below.

Evaluated October 17, 2026. Scope: choose a collection route before building the app. Initial checks used anonymous access. The user is now open to local authenticated collection, superseding the earlier no-login preference. Public-content-only and US$0 out-of-pocket constraints still apply. The authenticated client has offline checks; live authenticated collection has not yet been tested.

## Apify demo

The standalone Apify demo is implemented and tested: **24 downloaded images from 9 photo posts**, using about **US$0.0324 of free credit and US$0 paid**, below the requested US$0.05 total. Open **http://127.0.0.1:8765** while the local server is running. Refreshing and reviewing the gallery never starts another scrape.

See [DEMO.md](DEMO.md) for setup, saved-result replay, labeling/export, the five-cent limit, and integration with other tools/platforms. The source adapter feeds the common `MediaRecord`/`process_media` pipeline; the gallery is optional. Poster and civic-issue decisions use review labels in this version, rather than a runtime visual classifier.

## Instaloader setup and Toronto collection

The local client is implemented in [`instagram_local.py`](../collectors/instagram_local.py) and uses the shared [`MediaRecord` and download pipeline](../media.py). Run these commands from the repository root. The project environment and dependencies have been installed during setup; the installation commands below also allow recreating it later.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scraping/requirements-instagram.txt
```

Sign in **in your own terminal**. It asks for your username, a hidden password, and a verification code if Instagram requires 2FA. It does not import browser sessions or send credentials to Apify.

```sh
.venv/bin/python -m scraping.collectors.instagram_local login
```

Session cookies are saved as JSON at `scraping/data/instaloader/session.json`, readable/writable by your user only. The password is not saved. The existing Git ignore rule excludes all of `scraping/data/`. Treat that session as a credential; keep it local and do not share its contents. A missing/invalid session never triggers an automatic login attempt.

Collect up to ten posts from the supplied Toronto location (the default target):

```sh
.venv/bin/python -m scraping.collectors.instagram_local collect --limit 10
```

The equivalent explicit target is:

```sh
.venv/bin/python -m scraping.collectors.instagram_local collect \
  'https://www.instagram.com/explore/locations/110941395597405/toronto-ontario/' \
  --limit 10
```

Optional flags:

- `--metadata-only`: test access and save image candidates without downloading images.
- `--since 2026-10-10T00:00:00Z`: exclude posts older than this example posting timestamp. The collector still scans the bounded sample because source order is unverified.
- `--output scraping/data/my-toronto-sample`: use a new/empty destination. Previous results are not overwritten.

Each run normally creates a dated directory under `scraping/data/instaloader/collections/` containing `candidates.jsonl` and `report.json`. Image-collection runs additionally produce `media.jsonl` and `images/`. The shared downloader validates CDN hosts, removes EXIF from saved derivatives, and detects exact duplicates within the run. Images remain unreviewed local staging data; downloads do not establish civic relevance, public-display suitability, capture age, or precise location.

The adapter checks that the author profile is known to be public, excludes private/unknown-privacy posts, skips videos and video covers, preserves original carousel indices, and sorts only the fetched sample locally. The post limit bounds posts scanned, not the number of usable photos. Authentication/access failures stop without automated retry; a mid-stream failure records a partial result. Instagram's legacy location endpoint may still reject authenticated requests, so successful live collection remains unverified until you sign in locally and run the sample.

## Recommendation

**With a US$0 budget and login now acceptable, test Instaloader's authenticated location collection first.** Apify is an optional comparison using verified free credit. gallery-dl is useful when downloading across many supported sites becomes important. A custom Playwright/Puppeteer scraper is a last resort for a particular missing capability.

This is an engineering recommendation based on documented capabilities, maintenance effort, and the anonymous checks below. Apify and custom browser automation have not been benchmarked live here. None of these tools establishes that Instagram will supply enough fresh Toronto images or useful civic evidence.

**Budget constraint confirmed by the user: US$0 out of pocket.** No subscriptions, top-ups, paid proxies, or paid overages. An Apify experiment may use only verified remaining Free-plan credits after the existing go/no-go; stop when that allowance is unavailable or exhausted. Do not assume that a token belongs to a Free-plan account.

Apify's [Free plan](https://apify.com/pricing) currently supplies US$5 per month and blocks service until the next cycle when it is exhausted. The actor's [pricing page](https://apify.com/apify/instagram-scraper/pricing) advertises up to 1,851 results within that allowance. This is a shared account budget, not a per-run allowance or a guarantee of useful images. It is suitable for a small pilot; a sustained mass-collection design must also work without Apify.

| Option | Where it fits | Discovery and access | Integration and maintenance | Decision |
| --- | --- | --- | --- | --- |
| Apify Instagram Scraper | Quick prototype collecting public account/post data | Vendor advertises profiles, posts, carousels, tags, and places; exact recent-post coverage needs testing | Structured API/export; vendor maintains extraction; usage cost and vendor dependence | Optional free-credit comparison |
| Instaloader | Local Instagram-specific work on known accounts/posts and location IDs | Public profiles and individual posts are documented; hashtag/location targets require login | Python library gives useful post/media objects; our environment must handle breakage and access limits | First authenticated location experiment; anonymous profile test failed here |
| gallery-dl | Downloading media from many supported platforms | Supports Instagram profiles/posts/tags, with cookie support; support does not guarantee anonymous discovery | CLI JSON and download archives are useful; provider-specific metadata still needs normalization | Optional later downloader; anonymous checks failed here |
| Custom Playwright/Puppeteer | Filling a narrowly identified gap in an existing collector | Only what the browser session can access; automation does not create a citywide discovery feed | We own selectors/response parsing, pagination, retries, metadata association, and browser operations | Defer until a specific unmet requirement justifies it |

## What the documentation establishes

### Apify

The [Apify-maintained actor](https://apify.com/apify/instagram-scraper) advertises public media and metadata extraction. Its listed Free-plan item rate is **US$2.70 per 1,000 results**, while the US$1.50 headline is a discounted rate on another plan. A result is an item, not necessarily one image or one useful scene.

Its descriptions of location URLs conflict: one section says place details, another includes place-sourced posts. Test that feature explicitly. The [input schema](https://apify.com/apify/instagram-scraper/input-schema) documents result limits/date filtering and warns about pinned posts. Apply a local timestamp check and distinguish place metadata from actual media.

Choosing this actor would delegate extraction work. We would still own source selection, media retrieval, deduplication, filtering, retention, and evaluation. Reliability is a hypothesis until the pilot and a later repeat run pass.

### Instaloader

The [target documentation](https://instaloader.github.io/basic-usage.html) explicitly requires login for hashtags, locations, and geotag downloads. It documents public profiles and individual posts separately. That distinction matters: a tool that can fetch a known post may still fail at discovering new Toronto posts.

The [Python integration guide](https://instaloader.github.io/as-module.html) makes it a natural local option for an eventual Python collector. Its [troubleshooting guide](https://instaloader.github.io/troubleshooting.html) describes rate limits and stricter anonymous access on some shared networks. We did not load login sessions, browser cookies, or credentials.

### gallery-dl

Its [supported-sites list](https://gdl-org.github.io/docs/supportedsites.html) includes Instagram and many other platforms. Its [CLI options](https://gdl-org.github.io/docs/options.html) include JSON extraction and download archives; its [Instagram settings](https://gdl-org.github.io/docs/configuration.html#extractorinstagrammax-posts) include post limits and media options. These help with downloading and repeat collection; they do not solve civic relevance or grant access.

The tested release's `DataJob` can return an error inside JSON while its process exits zero. For a profile, plain `--dump-json` may also emit a delegation record rather than media. The included probe uses `--resolve-json` and checks the actual message types, errors, and media count.

### Playwright versus Puppeteer

Both offer browser automation and network inspection: [Playwright network documentation](https://playwright.dev/python/docs/network), [Puppeteer request interception](https://pptr.dev/guides/network-interception). A rendered page may help with a rendering-specific problem, but that is different from an access restriction.

If a custom browser step becomes necessary, use **Playwright with Python** to keep it alongside the collection/vision code. Puppeteer remains reasonable for a Node-based collector. Neither has been tested against Instagram in this comparison. Avoid selecting one on an unsupported claim that it is inherently undetectable or bypasses login requirements.

## Observed anonymous access

See [the recorded report](../research/results/anonymous-access-results.json) for the latest checked-in run. The sample is one public institutional profile and one Toronto hashtag, from one environment, with one post requested per probe. It is an access diagnostic, not a volume, image-quality, or sustained-throughput benchmark.

The initial resolved checks returned:

| Probe | Version | Observation |
| --- | --- | --- |
| Instaloader, profile | 4.15.4 | `ConnectionException`: HTTP 401, with a request to wait before trying again |
| gallery-dl, same profile | 1.32.17 | `NotFoundError`; no media returned. This alone does not establish that the account is absent |
| gallery-dl, Toronto hashtag | 1.32.17 | `AbortExtraction`: redirected to a login page |
| Apify | Not run | Requires the existing credit/spending go/no-go |
| Custom browser | Not run | Deferred; no demonstrated rendering-specific need yet |

No images were downloaded. Access can vary by target, network, time, and version; these failures should not be generalized to every environment or to authenticated use. The report records the final reusable probe run separately because responses can change between requests.

## Reproduce the local probes

Use a project-local environment; the dependencies are pinned to the versions evaluated. The probe's process-group timeout currently targets macOS/Linux, including a future Linux worker.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scraping/requirements-research.txt
.venv/bin/python -m scraping.research.instagram_probe instaloader https://www.instagram.com/PUBLIC_ACCOUNT/ --limit 1
.venv/bin/python -m scraping.research.instagram_probe gallery-dl https://www.instagram.com/PUBLIC_ACCOUNT/ --limit 1
.venv/bin/python -m scraping.research.instagram_probe gallery-dl https://www.instagram.com/explore/tags/toronto/ --limit 1
python3 -m unittest discover -s scraping/tests -t . -p 'test_*.py'
```

Replace `PUBLIC_ACCOUNT` with a public account. The probes ignore gallery-dl's default configuration, keep its cache in memory, do not load cookies, and stop after a bounded timeout. They return a JSON summary and a nonzero exit status unless media extraction succeeds. Returned image URLs are counted, not downloaded or persisted. An `ok` result proves only that the limited extraction returned image URLs, not that those URLs fetch or the images are useful.

The checks cover the observed false-success cases, partial extraction errors, target validation, and removal of request URLs/target identifiers from diagnostic messages.

## Keep the eventual collector independent of the app

The local collector accepts a location URL/ID, time window, result limit, and output directory. The app can later invoke the same collector from a worker; no web framework, cloud database, or geolocation model is necessary for this collection.

Integration boundary: **source response → one normalized record per image → local staging → deduplication/filtering → accepted records**. The Instaloader adapter now feeds the shared `MediaRecord`/`process_media` pipeline. Start with private JSONL and image files; add database writes when the app exists. The earlier anonymous access probe remains diagnostic-only.

| Record field | Meaning |
| --- | --- |
| `schema_version`, `platform`, `collector` | Explicit data format and provenance |
| `post_id`, `media_index`, `media_id` | Stable native identity and original carousel position; preserve gaps where a slide is video |
| `posted_at`, `captured_at`, `fetched_at` | Separate upload, capture, and retrieval times; capture time may be unknown |
| `image_url`, `local_path`, dimensions, hashes | Retrieval and duplicate handling; these are restricted staging data |
| Redacted caption/alt text, `location_evidence` | Context without author/commenter profile metadata; tagged places are not camera positions |
| `review_status`, reason codes, model version | Initially unreviewed; later filtering decisions are explicit |

Do not couple this format to Apify field names. If the source changes, adapt its response once while preserving the downstream record format. Keep raw exports/media in ignored local staging with short retention. Re-encode/strip metadata and apply the existing privacy/filtering rules before any display. A scraper result is not a verified civic observation.

## Location selection and sorting

For the specific Apify actor linked above, the input schema exposes a date cutoff (`onlyPostsNewerThan`) but no documented location-feed sort control. Place search can return matching locations rather than their posts, and the README gives conflicting descriptions of location-URL outputs. We can sort returned posts by timestamp ourselves, but that does not establish that the source returned the newest posts or every post tagged there.

Instaloader documents [`get_location_posts(location_id)`](https://instaloader.github.io/module/instaloader.html#instaloader.Instaloader.get_location_posts) with login required. The installed 4.15.4 implementation requests the location's `recent` section, without a caller-controlled sort parameter. This is a direct location-ID query, not an arbitrary bounding-box/radius search. Multiple venue/place IDs would be needed to sample an area.

Documented support is not proof that the endpoint currently works. Upstream [issue #2447](https://github.com/instaloader/instaloader/issues/2447) reports authenticated location failures in 2024–2025; the installed code still uses the same endpoint pattern. This is historical failure evidence, not a fresh authenticated test. Login can also encounter request limits or challenges.

The next zero-cost experiment uses the new local client and 10 posts from the user-supplied Toronto location ID `110941395597405`. Expand to two or three place IDs only after that request works. The user signs in locally; passwords and session contents do not belong in chat, logs, or Git. The new client implements explicit session handling and does not automatically import browser sessions. The existing anonymous probe remains unchanged.

Check whether each location returns actual posts, whether additional pages work, timestamp order, date spread, duplicate IDs, and carousel image availability. Sort fetched posts locally; only stop at a date boundary once source ordering is demonstrated. If this small test fails, stop and record the failure rather than assuming that higher request volume will fix it. A successful result still needs image-content filtering: a place tag alone does not make a poster useful evidence.

## Apify pilot results and follow-up

The user authorized a demo using free credit, then lowered the target allowance to **US$0.05**. The completed account-feed and hashtag tests stayed below that combined amount. See [the sanitized results](../research/results/apify-demo-results.json) and [the demo guide](DEMO.md). New CLI runs permit at most ten requested posts, verify the account is on the Free plan, and enforce a maximum US$0.05 cap per run. There are no automatic reruns, paid upgrades, or browser-triggered scraping calls.

The source-normalized record format and gallery now support independent collection/filtering evaluation. The next visual-classifier test should use reviewed labels to measure useful-scene precision/recall and civic-issue yield separately. Location-page coverage and sustained fresh-post volume still need their own tests; neither is established by this small pilot.
