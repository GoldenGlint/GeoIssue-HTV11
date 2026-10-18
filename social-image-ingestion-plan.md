# GeoIssue: collecting fresh, useful social images

Draft researched on October 17, 2026. This is a proposed experiment and implementation plan; no collectors, paid runs, or image-quality benchmarks have been executed for this document.

**Implementation follow-up, October 17:** The collectors now retrieve real images, but broad Toronto discovery remains noisy and automatic scene/location verification is not implemented. A bounded targeted Bluesky pilot downloaded 44 images from 31 photo posts and found a drain-grate issue candidate with wider intersection context. See [the diagnosis, measured results, and next experiment](scraping/docs/TARGETED-DISCOVERY.md). This does not establish confirmed issue yield or geolocation accuracy.

## Recommendation

Build one small collection-and-filtering pipeline that accepts images from different sources. Prioritize an Instagram feasibility test, use Bluesky and Mastodon for the initial free collection, and add Flickr if its recent Toronto coverage proves useful. Choose the primary source using **fresh, unique, useful images per day and cost per useful image**.

For Instagram, test a maintained scraper against a curated list of public local accounts before relying on broad Toronto hashtags. Treat location-page collection as an unproven feature. Keep an account-connected official API route as a longer-term option for participating organizations.

Separate two outputs:

1. **Useful city scenes:** recent photos showing streets, sidewalks, public transit, parks, public facilities, or infrastructure, even when nothing is wrong.
2. **Civic issue candidates:** a subset with visible evidence of an issue, suitable for human verification.

A Toronto tag is a discovery hint. It does not establish that a photo contains a Toronto scene, was taken recently, or shows an issue.

The useful-scene pool is initially a temporary evaluation buffer. Scene-only images follow the existing non-issue deletion policy; a permanent city-photo archive would need a separate retention and reuse decision.

## Context incorporated

Read alongside this proposal:

- `initial-unfinalized-plans.md`: GeoIssue collects public posts, detects civic issues, locates them, and helps residents, volunteers, and staff respond. Its important early tests are collection yield and geolocation feasibility.
- `2026.10 Hack The Valley Datasheet.md`: the Toronto Civic Data Starter Guide, including 311, geography, transit, infrastructure, permits, and demographic sources.
- `2026.10 Hack The Valley School of Cities.md`: a usable Toronto civic prototype, grounded in urban data, with clear users and responsible interpretation.
- The supplied challenge and sponsor text: Gemini, Tiger Data, Vultr, GoDaddy, DEV, and the broader themes.

This proposal keeps the original **free-first, public-content-only** approach and its privacy protections. The existing plan explicitly gates even an Apify free-credit test on a later go/no-go; this draft does not authorize or run it. Credentials and hardware described in that earlier document still need checking when implementation begins.

**Updated user preferences:** US$0 out of pocket; local authenticated Instagram collection is now acceptable to investigate. This supersedes the original no-login restriction. The next experiment is authenticated Instaloader collection by location ID, with session setup performed locally by the user and public posts only. See `scraping/README.md` for current evidence and limitations; no authenticated collection has yet been tested.

For the first product, focus on a community volunteer finding and confirming **blocked pedestrian access, damaged public infrastructure, and dumping**. Add flooding if the collected sample contains enough examples. Keep the collection format general so the product can shift when evidence suggests a better use.

## 1. Source options and their roles

| Source or route | Proposed role | Main limitation or test |
| --- | --- | --- |
| Instagram through a maintained scraper | First Instagram experiment; account feeds, known posts, carousels, then discovery queries | Measure freshness, retrievable images, pagination, and repeat-run yield. Vendor feature lists do not prove coverage. |
| Official Instagram API | Participating professional accounts; investigate supported discovery separately | Account setup, permissions, and accessible content must match our use. Do not assume universal public-account search. |
| Bluesky public HTTP APIs and Jetstream | Initial free source; query/account collection plus ongoing arrivals | Probe endpoint access and actual Toronto image volume. Stream replay depends on the host and version. |
| Mastodon tag and account timelines | Additional free source | Each instance has its own access settings and view of federated content; deduplicate across instances. |
| Flickr API | Geographically searchable photo source; possible scene/evaluation supplement | Requires an application key. Recent upload volume and actual capture age need measuring. |
| Wikimedia Commons / Mapillary | Reference imagery and geolocation evaluation | Keep separate from evidence of newly observed civic issues. |
| Reddit | Optional after access is approved | Do not make RSS or anonymous JSON a core dependency. |
| TikTok and other video sources | Later extension if still images underperform | Access and video processing add work; a cover image is not reliable evidence of the video’s contents. |
| Volunteer photos / submitted links | Reliable fallback and validation set | Lower automatic volume; submissions must still pass the same checks. |

Evidence behind this ordering:

- Meta’s official [Instagram collection](https://www.postman.com/meta/instagram/collection/6yqw8pt/instagram-api) describes an API for Businesses and Creators. Its scope supports investigating connected organizations first. Meta’s detailed discovery pages returned HTTP 429 during this research, so exact current hashtag limits and discovery permissions remain unverified here.
- Bluesky’s [HTTP API reference](https://docs.bsky.app/docs/api/app-bsky-feed-get-author-feed) documents public reads through `public.api.bsky.app`. Replace the old plan’s expected search failure with a neutral capability test. A failed search request does not prove author feeds or streaming are unavailable.
- The official [Jetstream client documentation](https://github.com/bluesky-social/bsky/blob/main/packages/jetstream/README.md) distinguishes legacy public hosts from newer archive/replay capabilities. Verify the chosen host and persist its documented cursor; do not assume a portable, complete 24-hour archive.
- Mastodon documents [media-only hashtag timelines and pagination](https://docs.joinmastodon.org/methods/timelines/#tag), with authentication dependent on server settings.
- Flickr documents [public photo search](https://www.flickr.com/services/api/flickr.photos.search.html) with bounding boxes, upload/taken dates, licenses, and photo-type filters. Split large searches by geography and time rather than assuming pagination provides an unlimited archive.
- Reddit’s current [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) requires approved API access and restricts scraping/mining uses. A successful RSS response would establish connectivity, not a dependable approved ingestion route.
- TikTok’s [Display API](https://developers.tiktok.com/docs/en/display-api-overview) concerns creator profiles and videos; its [Research Tools](https://developers.tiktok.com/docs/en/research-api-codebook) serve qualifying researchers. Neither should be assumed to provide an immediately available citywide collection feed.

## 2. Instagram: three approaches

### A. Maintained scraper: best candidate for the first Instagram test

Start by evaluating `apify/instagram-scraper`, maintained by Apify, rather than adopting the different actor named in the original plan without checking it.

Its [documentation](https://apify.com/apify/instagram-scraper) lists profiles, posts, carousels, media URLs, and date filtering. However, the same page describes location URLs as place-detail inputs in one section and post sources elsewhere. **Location-to-recent-post collection needs a small explicit test.** Place coordinates must never be treated as the camera’s exact coordinates.

Test these inputs separately, with small result caps:

| Input | What must be demonstrated |
| --- | --- |
| Public account URL | Recent posts, usable timestamps, image URLs, carousel children, and a usable continuation mechanism |
| Known photo-post URL | Correct image and caption association; no profile/avatar images mistaken for post media |
| Known carousel URL | Every available slide appears separately and stays linked to its parent post |
| Hashtag query or URL | Actual post results, their ages, and how discovery differs from profile collection |
| Location URL | Whether it returns place metadata, posts, or both; whether posts are recent |

The [input schema](https://apify.com/apify/instagram-scraper/input-schema) exposes `directUrls`, `resultsLimit`, and `onlyPostsNewerThan`, but warns that pinned posts may still appear. Enforce our own timestamp filter and handle ordering locally. The README and schema also differ in their descriptions of search behavior, reinforcing the need to record actual response shapes.

At research time, the actor lists **US$2.70 per 1,000 results on the Free plan**; its lower headline price applies to other plans. Thus 1,000 returned items is about US$2.70 at that listed item rate, before any applicable extras. Results are not equivalent to useful images. Apify’s [platform pricing](https://apify.com/pricing) lists a US$5 free allowance, but available account credit and the selected actor’s charges must be checked before a run.

After the existing go/no-go, cap both results and spend, disable automatic paid expansion, record the actor build, and repeat the same queries later. A one-off successful export is insufficient evidence for a fresh feed.

### B. Official access with participating organizations

Investigate connected professional accounts belonging to neighborhood groups, cycling/transit organizations, local publications, and public-space photographers. This can make a useful curated source even if broad public discovery is unsuitable. Official account authorization is a distinct integration; it does not require scraping with someone’s personal session.

### C. Open-source collector

With login now acceptable and US$0 out of pocket required, Instaloader is the first candidate for a small authenticated location-ID experiment. Its own [troubleshooting documentation](https://instaloader.github.io/troubleshooting.html) describes rate limits and access problems. The location method is documented but has upstream failure reports; verify actual results and ordering before committing to it. Use a user-created local session, keep collection to public posts, and stop repeated access failures instead of building around unbounded retries.

## 3. Finding useful images at volume

### Use several discovery channels

Start with these proposed cohorts; the counts are experiment sizes, not validated source availability:

- **20–30 public local accounts:** community groups, transit/cycling advocates, neighborhood publications, and street/public-space photographers. Check recent posts before adding an account; institutional feeds may contain mostly announcement cards.
- **10–20 place/neighborhood seeds:** station names, parks, streets, intersections, and neighborhoods. Where a platform lacks place search, use these in text queries.
- **Two query arms:** broad Toronto/place terms for incidental observations; place plus issue terms for higher expected civic yield. Examples include `Toronto sidewalk blocked`, `Scarborough dumping`, and `TTC broken shelter`, translated to each platform’s supported syntax.

Do not assume hashtag search supports arbitrary caption keywords or Boolean queries. A platform’s profile search may return accounts rather than posts; account discovery and account-media collection are separate operations.

Keep a meaningful broad-query sample so targeted collection does not eliminate the original idea of finding issues in ordinary posts. Match ambiguous names such as Junction against additional local evidence.

### Collect incrementally

1. Backfill at most seven days for the initial sample; report the last-24-hour subset separately.
2. Poll active sources on a modest schedule supported by their limits. Use a stream for live arrivals where available.
3. Store a checkpoint per source/query and use a small overlap to catch delayed indexing.
4. Deduplicate by platform post ID and media position before downloading; then compare image hashes.
5. Process all carousel slides. An event flyer on slide one must not hide a useful street photo on slide two.
6. Download a bounded preview for screening; request a larger version only when small evidence or signage needs inspection. Expect media URLs to expire and refresh through the source when supported.
7. Apply backoff and a bounded retry policy to transient failures. Stop a failing connector instead of repeatedly paying or hammering it.

Reserve some collection capacity for low-volume areas and new sources. Reallocate the rest using **confirmed useful yield**, while checking that a few prolific accounts or one event do not dominate the dataset.

Reels/video can be a later experiment: sample a small number of distinct frames only when media access permits it, screen each frame, and count the video/event once in volume reports.

## 4. A shared parsing format

Normalize platform responses into a post record and one media record per image. Keep the first implementation as a few source functions feeding the same processing function, with SQLite and a temporary image directory for the spike.

| Fields | Purpose |
| --- | --- |
| Platform, native post ID, media index, source query, fetch time | Provenance, checkpoints, and idempotency |
| Posted time; capture time if actually available; time-evidence type | Distinguish a newly uploaded historical photo from a newly captured scene |
| Media type, URL, expiry if known, dimensions, temporary path | Reliable retrieval and processing |
| Caption, alt text, tags, place label | Discovery/context; omit unnecessary personal fields |
| Location evidence, origin, precision, conflicts | Distinguish city/venue tags from an intersection or camera position |
| Exact hash, perceptual hash, duplicate-group ID | Reposts and near duplicates; preserve genuinely changed conditions |
| Decision, reason codes, model/prompt version, review label | Explain and evaluate keep/reject decisions |
| Rights/access status, required attribution, retention deadline | Determine permitted storage and display |

Keep source identifiers in restricted provenance, never in public API responses by default. URLs and captions can themselves contain handles: store opaque/native IDs where possible, resolve handle-bearing links only when needed, and redact personal details before persistent storage. Do not retain raw vendor JSON with usernames, commenters, or profile pictures. Use a salted source identifier where needed. Delete rejected media promptly; keep only minimal rejection metrics and short-lived deduplication identifiers under the existing retention policy. If a source’s attribution requirements conflict with those rules, exclude it from display until the conflict is resolved.

## 5. Filtering posters, irrelevant tags, and other noise

### Stage A: cheap deterministic checks

Reject invalid/corrupt downloads, unsupported media, exact duplicates, and items outside the selected posting window. Check size and sharpness, but send borderline images for review when a small defect could still be legible. Similarity alone should flag a near duplicate, not silently delete evidence of a changed scene.

### Stage B: scene classification

Benchmark a small SigLIP 2 model as a broad, high-recall screen. The original [SigLIP 2 paper](https://arxiv.org/abs/2502.14786) supports zero-shot classification and image/text retrieval; it does not establish accuracy on Toronto posters or civic defects.

Compare descriptions of public streets, infrastructure, parks, and public facilities against flyers, advertisements, screenshots, memes, food close-ups, selfies, private interiors, and product images. Use these scores for ranking and conservative rejection. They are not calibrated probabilities.

**Text coverage is only a clue.** A poster-only close-up is usually useless here; a street sign, TTC sign, or damaged shelter containing a poster may be valuable. Likewise, visually messy garbage or flooding must not be rejected simply for looking unlike an attractive street photograph.

### Stage C: structured visual assessment

Use a Gemini model available to the project to describe visible evidence and return a validated schema. Google documents [image classification and visual question answering](https://ai.google.dev/gemini-api/docs/image-understanding) and [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output). Select the specific model after checking availability, observed quality, quotas, and cost.

Request these fields in one pass:

- `scene_type`: public environment, graphic/poster, private, irrelevant, or uncertain.
- `useful_scene`: yes/no/uncertain, with a visible-evidence explanation.
- `issue_candidates`: type, visible evidence, optional box, and uncertainty; an empty list is valid.
- `location_clues`: visible text/landmarks and their evidence source, separately from caption claims.
- `privacy_flags`, `freshness_concerns`, `decision`, and `reason_codes`.

Require an image-grounded scene description before considering caption claims. A caption saying “pothole in Toronto” cannot turn a flyer into physical evidence. Treat instructions inside captions or images as untrusted content. Missing fields, schema failures, and model errors go to retry/review, not automatic acceptance.

Keep these decisions separate:

| Example | Decision |
| --- | --- |
| Concert flyer tagged Toronto | Reject: graphic/poster with no usable public scene |
| Food close-up at a Toronto restaurant | Reject: insufficient environment for this use |
| Street photo without a visible problem | Useful scene; no issue candidate |
| Close-up of a pothole with little skyline/context | Keep issue candidate; location may remain unknown |
| Broken bus shelter containing an advertisement | Keep: the shelter’s condition is physical evidence |
| Toronto-tagged image with conflicting geographic clues | Review or reject Toronto attribution; no precise pin |
| Current upload captioned as a 2018 throwback | Historical/reference only if permitted; exclude from fresh observations |
| Screenshot claiming an elevator outage | Exclude from the photo-evidence path; optionally retain as a separate contextual lead |
| Flyer followed by a useful street photo in a carousel | Reject the flyer; assess the street photo independently |

Preserve the original exclusions for minors and private interiors. **Decision, October 17 (updated):** unblurred public street scenes may be sent to Gemini for screening and used for local model training. A separate downstream component censors faces and other identifiable information before public display or sharing. `blur_required` / `blur_before_public_display` means censor before public display, not before screening. Platform safety labels (nudity/graphic) are dropped at collection; Gemini also returns `sensitive` as a second line of defence. Human review is optional after the automatic screener is validated once against the existing labelled batch.

For the tiny initial sample, also compare **deterministic checks → Gemini** against **deterministic checks → SigLIP → Gemini**. Keep the extra classifier only if it reduces cost/time without losing useful scenes or subtle issues.

## 6. Using the additional civic data and technologies

The starter guide supplies geographic anchors and civic context. It does not itself supply a fresh social-image feed. Inspect actual resource schemas, refresh dates, geographic precision, and licenses before building joins; the catalogue pages alone do not establish those details.

| Supplied source | Concrete use | Boundary |
| --- | --- | --- |
| [Neighborhoods](https://open.toronto.ca/dataset/neighbourhoods/) and [wards](https://open.toronto.ca/dataset/city-wards/) | Local-name matching, area filters, and aggregate summaries | A neighborhood mention cannot establish an exact location |
| [TTC routes and schedules](https://open.toronto.ca/dataset/ttc-routes-and-schedules/) | Resolve station/stop/route references and nearby assets | A route spans many places; schedules do not prove a live disruption |
| [311 customer-initiated requests](https://open.toronto.ca/dataset/311-service-requests-customer-initiated/) | Compare issue categories and nearby/time-relevant published records | Follow the guide’s warning about partial coverage and changing categories; no match does not mean unreported |
| [Road restrictions](https://open.toronto.ca/dataset/road-restrictions/) and [active permits](https://open.toronto.ca/dataset/building-permits-active-permits/) | Add possible construction context to a verified scene | Nearby construction neither proves causation nor establishes that an obstruction is acceptable |
| OSM and public-facility datasets in the guide | Street/place anchors and asset context | A nearby asset is a candidate, not a confirmed match |
| Census, housing, election, and finance data | Optional later context for a clearly defined user question | Defer from ingestion; image/post counts do not measure neighborhood need or condition rates |

Technology choices:

- **Gemini:** visual screening, evidence extraction, and grounded explanations; benchmark rather than hard-code estimated per-image quality/cost.
- **Tiger Data:** a possible destination for posts, media decisions, spatial joins, and collection metrics after the spike. Its [extension documentation](https://docs.tigerdata.com/use-timescale/latest/extensions) lists PostGIS, pgvector, and TimescaleDB; confirm availability on the chosen service. Store image files outside the database. Add vector search only when it solves a measured need.
- **Vultr:** host the working collector and prototype after the source decision. Use ordinary compute first; GPU hosting depends on an observed bottleneck and available credits.
- **GoDaddy / DEV:** domain and project write-up once the prototype works. Solana and unrelated health challenges do not create an ingestion requirement.

The pasted prize page mixes date ranges, so this mapping treats the technologies as context rather than claiming current prize eligibility.

For School of Cities, demonstrate a usable flow: **find a candidate → see visual evidence and civic context → verify location/condition → record a useful follow-up**. Show when each source was last updated. Describe social observations as incomplete and unevenly sampled; do not rank wards by their apparent number of problems from social-image volume.

## 7. Feasibility experiment and decisions

### Phase 1: capability checks

Create small probes for Bluesky search/author feeds/stream, Mastodon media timelines, and Flickr if an application key is available. Record response status, actual result type, timestamps, image availability, pagination, checkpoint behavior, and collection cost. Timebox blocked sources and continue with working ones.

Prepare the Instagram input matrix above. Run it only after the existing Apify checkpoint, using approved free credit or a separately approved spending cap. This is independent of whether the free sources pass: Instagram preference warrants testing it, but does not justify silently spending money.

### Phase 2: comparable collection

Aim for **500–1,000 distinct images overall**, with roughly balanced broad and targeted query arms where sources permit. Keep image, post, account/source, duplicate cluster, and issue-event counts separate. Record an insufficient sample honestly rather than filling the recent set with old imagery.

Repeat collection in at least two separated windows and report the **incremental** images from the second run. A first backfill is not a daily production rate. Capture the last-24-hour, last-72-hour, and seven-day posting subsets; mark capture age as unknown unless supported by evidence.

### Phase 3: human labels and filter comparison

Hand-label a random sample before tuning, with a separate challenge set of posters, screenshots, signage, subtle defects, mixed carousels, and misleading location tags. Aim for at least 300 labels if volume permits. Use labels for useful scene, visible issue, Toronto evidence, privacy, and freshness evidence.

Split evaluation by parent post and duplicate/event group so related images cannot leak between tuning and holdout sets. Review a random sample of rejected images as well as accepted ones. To estimate recall, label a random pre-filter holdout or weight stratified samples correctly; checking only retained images cannot measure what the filter lost. Report small denominators and uncertainty.

### Proposed gates, not measured results

| Measure | Initial decision criterion |
| --- | --- |
| Download reliability | At least 95% of eligible sampled image URLs fetch promptly; report failures by source |
| Useful-scene precision | At least 85% of auto-kept images are human-confirmed useful scenes |
| Useful-scene recall | At least 90% on the labeled holdout; report civic-issue misses separately |
| Poster/noise rejection | At least 95% of labeled poster-only/irrelevant graphics rejected, while retaining at least 90% of useful signage/shelter examples |
| Civic feasibility | Preserve the original exploratory gate: at least 10 distinct human-confirmed issue events in at most 1,000 sampled images; this does not establish citywide yield |
| Issue-candidate precision | At least 70% for the exploratory review queue; public claims require verification |
| Continuing supply | Report fresh unique scenes and confirmed issue events from each later window; choose a daily target from observed supply and the user’s actual need |
| Cost | Report observed collection + download + inference cost per useful scene and per confirmed issue event, including paid failed/repeated work |
| Coverage and provenance | Every retained item has source/time evidence and a reason; disclose account and neighborhood concentration |

Report a funnel for each source and query arm: **returned posts → images → fetched → recent by posting time → distinct → useful scene → visible issue → human-confirmed event → usable location**. Keep human-added demo photos clearly separate from automatic collection.

Useful formulas:

- Useful-image yield = unique useful scenes / unique screened images.
- Issue yield = distinct confirmed issue events / unique screened images.
- Cost per useful image = total collection and processing cost / unique useful scenes.

For budgeting, an illustrative 10,000-image collection at 2% useful yield produces only 200 useful images. At 10% it produces 1,000. These are examples, not Toronto measurements; improving source selection and filtering can matter more than collecting more raw posts.

### Phase 4: choose the direction

| Observed result | Action |
| --- | --- |
| Instagram returns fresh scenes reliably and economically | Make curated Instagram accounts primary; retain the best free complementary source |
| Instagram account feeds work but location/hashtag discovery is poor | Monitor curated accounts and accept submitted links; drop the failing discovery route |
| Instagram access is unreliable or outside the budget | Lead with the best measured free source; keep Instagram as an optional connector |
| Useful scenes are plentiful but civic issue yield is low | Present a scene/context explorer or focus on targeted submissions; describe passive issue discovery as experimental |
| Issues are visible but precise locations are weak | Use area-level candidates and volunteer pins; do not force geolocation |
| All social sources have low fresh yield | Build the civic-data map and volunteer photo flow; use social content as supplementary leads |

The spike should deliver a source comparison, a private labeled contact sheet, filter error examples, measured costs, and one chosen collection route. Defer the full geolocation model cascade, fusion training, multiple video platforms, and production infrastructure until those results justify them.
