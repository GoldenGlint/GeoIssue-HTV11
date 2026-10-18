# Implementation plan: more viable Toronto issue images

Drafted October 17, 2026. **Planning only: no new collection runs, spending, schedules, or collector changes are authorized by this document.** This replaces the earlier source-expansion proposal.

Priorities: **expand Bluesky, Mastodon and Reddit → improve screening coverage → curate Instagram and public Facebook Pages → pilot Threads → add X if an access route fits the budget.** Flickr is excluded at the user's request.

## 1. Outcome and constraints

Optimize for **new, distinct, locatable issue observations**, rather than raw photo count. A viable candidate must have:

- An independently passed image showing a visible issue in a public outdoor scene.
- Toronto evidence and medium/high locatability under the existing screening rules.
- A posting time within seven days, prioritizing the last 72 hours; no known historical capture or repost clue.
- A detailed assessment with `issue_supported: yes` for the passed image. `no`, `uncertain`, and pending assessments remain separate.
- Original source provenance and eligible same-post photos preserved for context.

These remain model-supported candidates, not verified current conditions. Report unknown capture age explicitly. Keep the existing privacy gates and `alert_eligible: false`. Count several views of one event as one observation; do not assume every image in a post depicts the same event.

Use the current pipeline: **collector → MediaRecord/process_media → screen → handoff → describe**. Reuse Requests, Pillow, JSON configuration, fingerprints and caches. No new database, job queue, provider framework, or vision model is needed.

Bluesky and Mastodon reads and the current Reddit archive route have no per-request charge to this project, but **usage is not unlimited**. Observe rate limits, access restrictions, archive lag, bounded pagination and backoff. Reddit collection currently uses the third-party Arctic Shift archive, not an unrestricted official Reddit API. [Mastodon limits](https://docs.joinmastodon.org/api/rate-limits/), [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift).

Keep **US$0 out of pocket**. The existing Instagram wrapper permits at most ten requested posts and US$0.05 of verified free credit per run. That historical limit is not an allowance for repeated runs or other actors. New provider pilots need their own explicitly allocated share of available free credit and an enforceable cap; skip actors whose minimum charges or account requirements do not fit. This plan does not increase any allowance.

## 2. Baseline and measurement

Before changing discovery, summarize the saved seven-day results and current handoff. Existing metadata probes found:

| Discovery input | Images returned | Images with problem words |
| --- | ---: | ---: |
| Bluesky: Bloor bike lanes | 24 | 24 |
| Bluesky: Toronto sidewalk | 14 | 14 |
| Mastodon: #Toronto | 140 | 32 |
| Mastodon: #BikeTO | 26 | 22 |
| Reddit: r/toronto | 203 | 50 |
| Reddit: r/TTC | 41 | 3 |

These are overlapping, bounded discovery counts, not screened viability or exhaustive supply. Sources: [query probes](../research/results/query-probe-results.json), [screening workflow](SCREENING.md).

The latest Instagram hashtag pilot produced 19 downloaded photos from ten posts, one initial pass and **zero new supported issues after detailed assessment**. Use that result to change discovery rather than repeat broad hashtag collection. [Pilot evidence](../research/results/instagram-expansion-results.json).

Record per query, tag, account, community and platform:

`posts fetched → photo posts → downloaded → distinct new images → screened → independently passed → supported image groups → distinct issue observations`

Also record failures, cap hits, source/age uncertainty, requests, credit consumption and elapsed effort. Preserve all `found_by` values on duplicates; do not count one image as several successes because several queries found it. Allocate cross-query credit fractionally or report overlap explicitly. Rank primarily by **incremental supported observations**, then supported groups per 100 images screened and per unit of credit. Problem-word counts are only a cheap discovery signal.

## 3. Phase 1: expand the working sources

### A. Bluesky: broaden systematically

Prepare approximately 60–90 candidate searches in two or three editable files under `scraping/config/`, grouped by issue and geography. Use `probe_queries` first, with no image downloads or Gemini calls. Retain successful existing searches as the comparison group.

Each collection run supports at most **50 queries plus author feeds**. Use multiple batches rather than raising that limit or generating every possible word combination. Start with one or two result pages per query; paginate deeper only when recent, useful results hit the cap.

Test these discovery families separately:

| Family | Example searches |
| --- | --- |
| Existing winners | `Bloor bike lanes`, `Toronto sidewalk`, `Toronto crosswalk`, `Queen Spadina` |
| Access | `Toronto blocked sidewalk`, `Toronto curb ramp`, `Toronto wheelchair access`, `Danforth pedestrian detour` |
| Surfaces | `Toronto pothole`, `Scarborough cracked sidewalk`, `Etobicoke road damage` |
| Waste and drainage | `Toronto dumped furniture`, `Toronto overflowing garbage`, `Toronto catch basin`, `Toronto standing water` |
| Transit and construction | `Toronto broken bus shelter`, `TTC damaged shelter`, `Toronto construction access`, `Eglinton sidewalk` |
| Resident language | `Toronto almost tripped`, `Toronto still not fixed`, `Toronto reported to 311`, `Toronto cannot get through` |
| Place-led scenes | `Parkdale street`, `Danforth construction`, `Junction sidewalk`, `Queen Street West Toronto` |

Expand geographic anchors to Bloor, Danforth, Yonge/Eglinton, Queen/Spadina, Parkdale, the Junction, Scarborough, Etobicoke and North York. An ambiguous street name needs a Toronto/neighbourhood anchor or later city screening. Use ordinary text searches first; do not assume X-style Boolean or image operators work in Bluesky.

Allocate roughly 70% of screening capacity to issue-oriented results and 30% to broader street/asset scenes. Inspect original-photo accounts discovered through useful posts, then add a small curated author list using the existing author-feed support. Keep some neighbourhood and category diversity rather than collecting only bike-lane posts.

**Deliverable:** ranked candidate searches, two or three query files, a selected active list and a report of new supported groups versus the existing searches.

### B. Mastodon: tags first, then account feeds if justified

Keep the existing tags as controls. Probe candidate tags such as `WalkTO`, `TorontoCycling`, `TorontoTransit`, `Scarborough`, `Etobicoke`, `NorthYork`, `Accessibility` and `Urbanism`. These are experimental seeds, not claims of recent photo supply. General tags require Toronto screening and should receive a small budget until they contribute local scenes.

The collector currently accepts **one instance and up to 12 tags per config**. A hashtag timeline is not arbitrary caption search. Test separate instance configurations only after checking public API access and recent relevant posts. Different instances can expose different federated slices; deduplicate by federation URI and image hash, not instance-local ID. [Timeline API](https://docs.joinmastodon.org/methods/timelines/#tag).

Start with configuration changes. If useful posters consistently lack tags, add a minimal account-feed option using public media statuses; **account collection is new work**, not a current feature. Skip boosts, sensitive statuses and non-public posts. Stop on login/access restrictions and defer rate-limited requests until reset.

**Deliverable:** ranked tag/instance results and, only if demonstrated useful, a small curated account-feed addition.

### C. Reddit: broaden communities, keep Toronto evidence strict

Retain `toronto`, `TTC`, `scarborough` and `etobicoke` as the baseline. First probe `torontobiking`; its [Bike Tag activity](https://www.reddit.com/r/torontobiking/comments/yptnqb/toronto_bike_tag_rules/) supplies public-space photo leads, although a bike photo is not evidence of a defect.

Then test these groups separately, verifying existence, access and recent image availability before enabling them:

- Toronto-adjacent/local: `TorontoDriving`, `askTO`, `northyork`, `bikeTO`. Earlier tests found little photo supply in several of these; re-test cheaply rather than allocating large downloads by default.
- Wider GTA comparison: `Mississauga`, `Brampton`, `Markham`, `Vaughan`, `RichmondHill`, `Pickering`. Enable only if they actually contribute Toronto scenes; neighbouring-city defects do not meet this project's city requirement.
- Topic communities: `urbanplanning`, `transit`, `bicycling`, `fuckcars`. Pilot a small metadata sample and look for Toronto-related attached photos before spending download/screening capacity. These names are candidate communities, not endorsements or measured sources.

The current collector fetches recent submissions by subreddit and supports **at most 15 communities per config**. It has no configurable keyword-search mode. Use several small configs and local title/body ranking first. For high-volume global communities, sample cheaply and skip if Toronto supply is negligible; do not download their entire photo feed. Add source-side text queries only if Arctic Shift documents the needed filter and a live probe confirms its behavior.

Keep galleries and original image positions. Existing direct `i.redd.it` support comes first. Measure how many otherwise useful posts are excluded because they are crossposts, comment images or other hosts; add only a proven, bounded gap. A crosspost may point to an original post for later resolution, but it must not create a second observation. Do not crawl all comments or arbitrary linked websites.

**Deliverable:** community ranking, a Toronto-focused active configuration and separate low-budget discovery configurations. Distinguish zero photo supply from API failure or archive lag.

## 4. Phase 2: make broader discovery survive screening

The default caption/alt-text problem-word filter can skip ordinary streetscapes that contain incidental defects. Do not remove it globally or loosen the definition of a visible issue.

1. Keep the normal prefilter for targeted issue batches.
2. Create a deterministic sample of up to 50 **distinct, previously skipped** images from broader discovery batches, balanced across sources. Use a separate local batch and the existing `--no-prefilter` option with an explicit request cap. Selecting the sample is a small planned addition; that option alone does not sample.
3. Compare supported observations found in the sample with the normal route. Record how often caption filtering hid a viable image, not just how often a broad image looked outdoors.
4. If useful misses occur, reserve the proposed 30% exploration allocation. Change the word list only for demonstrated vocabulary gaps; keep a bounded sample for photos without complaint wording.
5. Deduplicate before calling Gemini, reuse the shared cache and preserve all original post photos needed by `handoff`/`describe`. Companions never inherit an independent pass.

Use the existing automatic path; human spot checks remain optional. Do not count routine roadwork, infographics, ads, screenshots or protests as defects without visible supporting evidence. Recheck `issue_supported` after descriptions, because the Instagram pilot demonstrated that an initial pass can be overturned.

**Deliverable:** a comparison of caption-filtered and exploration batches, plus a source/query viability report. Collection volume must fit actual Gemini request limits; unlimited downloads cannot remove that bottleneck.

## 5. Phase 3: use Apify where it saves implementation work

Apify is a hosted collection option, not a mandatory dependency of every platform. The same token can access different actors, but **each actor has its own schema, pricing, account restrictions and adapter**. Do not pass another actor's output to the Instagram normalizer.

| Source | Recommended route | Planned discovery | Dependency |
| --- | --- | --- | --- |
| Instagram | Existing Apify collector | Inspected public profiles and known photo/carousel URLs | Existing free-credit checks; authenticated Instaloader is an alternative, but no successful local live batch is recorded |
| Facebook | Apify public Page posts pilot | A few inspected cycling, accessibility, neighbourhood and local-reporter Pages | New normalizer and bounded actor launch; Apify is practical here, not technically mandatory |
| Threads | Official keyword API if access already exists; otherwise test one Apify actor | Recent Toronto issue/place searches and selected public accounts | New adapter; official route needs app authorization/permissions; actor route uses credits |
| TikTok | Defer; optional photo-only pilot later | Photo carousels for proven Toronto issue searches | New source work and uncertain useful yield; skip video/frame extraction initially |

For Instagram, prepare 5–10 inspected feeds/post URLs and prioritize original street photos. Web/native search can find candidate URLs without spending scraper credit. Do not treat a profile, hashtag or place search as full public-caption keyword search. Existing target types must be tested separately. [Instagram input schema](https://apify.com/apify/instagram-scraper/input-schema).

For Facebook, inspect about five public Pages first and select a few recent original-photo posts. Use `apify/facebook-posts-scraper` as the first candidate: its input documents public Page URLs, result limits and newer-than dates. Public groups require a different actor and separate evaluation; private groups and login-gated material are outside this plan. [Facebook input schema](https://apify.com/apify/facebook-posts-scraper/input-schema).

For Threads, compare the already documented [Meta keyword endpoint](https://www.postman.com/meta/threads/request/34203612-b3b2c12a-7ce6-4d86-a3c6-6d31e3b66ea1) with one documented actor candidate such as [webdata_labs/threads-scraper](https://apify.com/webdata_labs/threads-scraper). That actor documents keyword results and media, but only approximately one page of search results; do not describe this as exhaustive search. Official API permissions and account access must be established before choosing that route. No Threads collection has been validated in this repo.

Pilot one new actor at a time. Check current pricing and output shape before launching, cap total posts across all seeds, preserve run IDs and resume a run rather than launching it again after an uncertain response. A result-count limit alone is not a spending cap. Do not import browser sessions, switch to paid plans or silently increase limits to make an actor work.

**Deliverable:** separate Instagram/Facebook/Threads pilot reports showing credit spent, actual photo downloads and new supported groups. Promote an adapter only after its sample contributes viable images or demonstrates a useful source niche.

## 6. Phase 4: obtain images from X.com

### Route A: official X API, if funded access is available

This is the clearest documented image-extraction route. It requires a developer app, a bearer token and API credits. Recent search covers seven days. X currently lists post reads at **US$0.005 per returned post**; verify the full billable request, expansions and current console pricing before a run. This route is deferred under US$0-out-of-pocket unless suitable credits already exist. [Search](https://docs.x.com/x-api/posts/search/introduction), [pricing](https://docs.x.com/x-api/getting-started/pricing).

Implementation steps for a proposed `scraping/collectors/x.py`:

1. Call `GET https://api.x.com/2/tweets/search/recent` with `start_time`/`end_time`, `sort_order=recency`, a small result cap and bounded `next_token` pagination.
2. Request `tweet.fields=created_at,attachments,possibly_sensitive`, `expansions=attachments.media_keys`, and `media.fields=media_key,type,url,alt_text,width,height`.
3. Join each post's ordered `attachments.media_keys` to `includes.media` by `media_key`; the includes list itself does not define attachment order. Keep only attached `type=photo` objects with a usable HTTPS URL. Exclude videos, GIF covers, link thumbnails and referenced-post media.
4. Download only the expected `pbs.twimg.com` photo URLs through `process_media`. Keep post ID, canonical post link, posting date, original attachment index, alt text and discovery query. Skip sensitive posts and retain unknown capture time.
5. Feed the normalized batch into the same screening and grouping path, subject to the source's permitted uses. Store credentials only in ignored local configuration.

[Media expansion documentation](https://docs.x.com/x-api/fundamentals/expansions).

Example **official API** queries:

```text
(Toronto OR Scarborough OR Etobicoke) (pothole OR "blocked sidewalk" OR "illegal dumping") has:images -is:retweet
(Toronto OR "BikeTO") ("bike lane" OR "curb ramp") has:images -is:retweet
(Toronto OR "TTC") ("broken shelter" OR "standing water" OR drain) has:images -is:retweet
```

Do not require `has:geo`: captions and signs may provide location even when posts lack native geotags. Preserve replies because residents may attach evidence in replies to public accounts.

### Route B: an Apify X actor, if it fits verified free credit

A possible candidate is [apidojo/twitter-scraper-lite](https://apify.com/apidojo/twitter-scraper-lite), subject to current actor pricing, free-plan/API eligibility, search behavior and image-response inspection. Use its documented input/query syntax; X web/actor filters such as `filter:images` are distinct from official API `has:images` and require separate verification. Retain only a post's own photo attachments, not a blanket list of every image URL in the result.

Do not default to [apidojo/tweet-scraper V2](https://apify.com/apidojo/tweet-scraper): its current documentation says Free users cannot use it through the API and describes query/demo restrictions. A low advertised per-thousand price does not establish compatibility with this project's tiny pilot allowance.

Pick **one** route after access and cost preflight. If neither fits, record X as deferred and continue with the working sources. Do not spend time building an unofficial browser/login workaround.

**Deliverable:** a documented access decision and, if feasible, one small normalized X batch with working source links, cost accounting and supported-group yield.

## 7. Shared implementation changes and verification

Make only the changes needed by a promoted source:

| Area | Change |
| --- | --- |
| `scraping/config/` | Candidate/active search files, subreddit cohorts and separate Mastodon instance configs; source-specific configs only when a pilot needs them |
| `scraping/probe_queries.py` | Preserve existing metadata probes; extend reports with deduplicated incremental yield by joining saved screening/description results, or use a small reporting helper |
| `scraping/media.py` | Retain a validated canonical post URL and extend `source_post_url` for promoted sources. It currently handles only Bluesky/Reddit/Mastodon; Instagram also needs this provenance fix |
| `scraping/collectors/` | Existing Instagram adapter stays; add ordinary Facebook/Threads/X modules only for successful pilots, each with explicit media-host validation |
| `scraping/screen.py` / workflow | Reuse `--no-prefilter`; add only bounded sample selection/reporting needed for broader discovery |
| `scraping/handoff.py`, `scraping/share.py` | Check new sources preserve links, groups, timestamps, image hosts and refresh behavior; retain existing contracts and handle source withdrawal |
| `scraping/research/results/` | Sanitized baseline, source comparisons and cost/yield reports; images, full account data and tokens stay ignored |

Adding a post URL must preserve native identity and existing manifests. Prefer an optional validated field over rewriting existing post IDs. Ensure processing and `source_post_url` preserve it rather than overwriting it with `None`. For each new source, inspect representative real response shapes before fixing field mappings.

Retained-post refresh is not uniformly implemented across existing collectors. Report that gap and add confirmed-missing/private-post cleanup before claiming a source is a continuing current feed; a failed request is not proof of deletion. Revalidate and rebuild exported handoffs before reuse. Preserve source attribution and permitted-use information; discovery access does not establish rights for model training or public republication.

Configuration/document-only changes need syntax/link checks. For implemented logic, run the relevant existing offline tests and add a focused response-shape check for each new adapter: attached-photo ownership, mixed carousel positions, sensitive posts, missing/invalid dates, untrusted hosts, canonical links, deduplication and a bounded failure. Money-handling changes must verify that disallowed plans, minimum charges and ambiguous run starts do not launch/relaunch collection. No network calls in ordinary tests.

## 8. Execution order and completion criteria

| Order | Work | Finish condition |
| --- | --- | --- |
| 1 | Baseline and discovery candidates | Saved counts reproduced; all new seeds clearly labelled experimental |
| 2 | Expand Bluesky/Mastodon/Reddit | Ranked searches and communities; bounded new batches with per-source overlap and failures |
| 3 | Broader-scene screening sample | Up to 50 skipped images assessed; supported yield compared with the normal prefilter |
| 4 | Instagram curation and Facebook pilot | Source-specific evidence of incremental supported groups and actual credit cost |
| 5 | Threads and X access decisions | Working, affordable access plus useful pilot, or explicit defer reason with no wasted run |
| 6 | Rebuild and describe handoff | Source links, exact photo evidence, context roles, age uncertainty and disagreement statuses retained |

First-round planning target: **500–1,000 distinct recent-upload candidates → 50–100 independently passed images → at least ten additional supported issue observations**. These are goals, not predicted conversion rates. Prefer breadth across several issue types and neighbourhoods; do not fill targets with duplicates or lower the city/freshness/issue requirements.

For an exploratory new source, two new supported observations is an initial continuation signal, not a quality guarantee. If an inspected sample adds none after one focused discovery revision, defer it. For tiny paid pilots, report the actual sample and uncertainty rather than demanding a statistical conclusion.

Use roughly 70% of the next screening budget on measured winners and 30% on exploration. Compare a second collection window with the first before claiming continuing supply. A suggested future cadence is every six hours with checkpoint overlap; creating a background schedule is separate work and is not part of this draft.

The completed implementation should produce **one ranked source/query report and one refreshed grouped handoff**, with supported observations separated from initial passes and context photos. If organic supply falls short, report the gap and use separately labelled team photos for the demo instead of treating old or unlocatable images as current evidence.
