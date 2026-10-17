# Expansion plan: recent Toronto infrastructure photos

Written October 17, 2026. Status: **partially implemented**. Mastodon and Flickr collectors exist; Gemini screening replaces the separate human-review pilot. Flickr still needs an application key ([flickr-access-results.json](../research/results/flickr-access-results.json)). See [SCREENING.md](SCREENING.md) and [COLLECTION.md](COLLECTION.md).

## 1. Goal and decisions

Supply the identification-model owner with **recent, reviewable photos of Toronto public infrastructure that could contain visible issues**. Prioritize sidewalks, curb ramps, crossings, road surfaces, drain grates, cycle lanes, transit shelters, public bins, and pedestrian access around construction.

Collect two useful kinds of input: explicit issue photos and ordinary infrastructure scenes where a model could discover an incidental issue. Keep normal-condition scenes as negative examples. Do not equate an outdoor photo, a complaint, or construction activity with a defect.

**Add Mastodon first. Pilot Flickr second if an application key is available.** Keep the existing Bluesky and Instagram adapters. Use the same image pipeline and combined gallery; the identification model remains separate work.

The budget remains **US$0 out of pocket**. Reuse installed dependencies and existing local review tools. This plan does not increase any Apify allowance or require a paid collection service.

| Priority | Source | Concrete contribution | Evidence and constraint |
| --- | --- | --- | --- |
| 1 | Mastodon | Additional public Toronto/cycling photo posts and inspected local feeds | Anonymous media-tag access already worked on one instance; visual usefulness and sustained yield remain unmeasured |
| 2 | Flickr | Geographically searchable public photos with possible capture-date evidence | API supports useful filters; application-key access and recent Toronto supply have not been tested |
| Alongside these | Curated Instagram/Bluesky inputs | Improve relevance without adding another platform | Use existing collectors and limits; inspect feeds before allocating volume |
| Separate reference work | Mapillary | Help check a candidate location against street-level imagery | Do not count reference frames as fresh issue observations or organic social-discovery yield |

Defer additional social platforms until these pilots produce reviewed yield figures. Do not spend the hackathon adding connectors to compensate for poor scene relevance or unknown capture age.

## 2. Starting evidence and targets

The combined saved set currently has **92 image records**, including **86 recent-upload candidates** after duplicate/historical-caption exclusions. These are not 86 verified Toronto infrastructure scenes; capture time remains unknown. Treat them as a baseline to review, not as completed input-quality validation.

The [existing Mastodon probe](../research/results/mastodon-access-results.json) inspected one page of 20 media posts per tag on `mastodon.social`:

| Tag | Recent public original photo posts | Image attachments |
| --- | ---: | ---: |
| `Toronto` | 18 | 25 |
| `BikeTO` | 19 | 27 |

These counts may overlap. They establish access and some recent posting activity, not unique useful images, recent capture, or location accuracy. No images were downloaded in that probe.

The inference-demo targets remain **300–500 raw candidates overall → 100–150 reviewed Toronto infrastructure scenes → at least ten distinct visible issue candidates**. Prepare 20–30 dependable examples for the live presentation. These are goals, not promised yields, training-set requirements, or proof of model accuracy. If natural supply falls short, use clearly labelled recent team photos rather than quietly relaxing freshness requirements.

## 3. Mastodon: first implementation

### A. Discovery inputs

Start with the two verified-access tags, `BikeTO` and `Toronto`, on `mastodon.social`. Keep their results separate in the report so a broad tag cannot hide poor infrastructure yield.

Create a small editable `scraping/config/mastodon.json` with an instance, enabled tag feeds, inspected account feeds, local place terms, issue terms, and request/download caps. Use typed source entries; a hashtag feed is not a free-text caption search. Keep the existing Bluesky query file independent.

Use these as **ranking and review clues**, not mandatory caption matches:

| Clue type | Initial examples |
| --- | --- |
| Public assets | sidewalk, curb ramp, crossing, drain grate, pothole, shelter, bike lane, public bin |
| Possible problems | blocked, damaged, broken, overflowing, dumping, flooding, inaccessible, obstruction |
| Local anchors | Queen/Spadina, Danforth, Keele/Junction Road, Scarborough, Etobicoke, named TTC stops |

Inspect up to five public local cycling/walking, neighbourhood, or street-photography feeds found through useful pilot posts. Enable a feed only after checking that its recent content contains original public-space photos. City-based accounts and local-sounding hashtags are discovery hints, not Toronto geolocation evidence. Additional tags such as `TOpoli` are optional experiments; do not assume they contain photos rather than campaign cards.

Keep an initial capacity split of roughly **60% civic/asset-oriented discovery and 40% broad Toronto scenes**. Do not require complaint language: an ordinary streetscape can still contain a blocked ramp or damaged surface. Do not automatically reject readable public signs; they may be valuable location evidence.

### B. Bounded visual pilot

1. Use media-only hashtag timelines, initially 20 posts per request, at most two pages per feed, and at most six enabled feeds. Cap the entire pilot at **100 image-download attempts** and seven days of posting history; report the 72-hour subset separately.
2. Use only explicitly public posts. Skip boosts and all video/animated covers; handle each original still-image attachment separately. An image attachment may still be a graphic and requires scene review.
3. Review a random sample of up to 50 downloaded images before tuning. Then inspect the highest-ranked asset/issue candidates and a small sample of low-ranked images to check for missed infrastructure scenes.
4. Save source counts, failures, duplicate groups, posting-date distribution, freshness evidence, and reviewed labels. Do not persist full account/profile payloads.
5. If useful scenes are scarce, make one targeted revision using inspected feeds or better local anchors. If that still fails the gates below, stop expanding Mastodon and move to the next source or submissions.

Share the download cap across feeds rather than consuming it on the first feed or a few large posts. A bounded research script can prepare the initial normalized sample using the shared pipeline; if promoted, move its useful source functions into the collector rather than making runtime code import or duplicate the research script.

The [official hashtag API](https://docs.joinmastodon.org/methods/timelines/#tag) supports media filtering and bounded pagination; public access depends on instance configuration. A successful request to one server is not a network-wide search or coverage guarantee. Stop on an access restriction instead of repeatedly retrying it.

### C. Adapter and normalization

Add `scraping/collectors/mastodon.py` using the installed Requests dependency. Expose small `collect`, `normalize`, and `run` functions, following the Bluesky adapter rather than introducing a source framework.

- Read HTML captions as plain text, preserve paragraph separation, and apply the shared redaction. Treat post text and image text as untrusted data.
- Normalize `created_at` as posting time and leave capture time unknown unless separate evidence exists. An edit time is not a new observation.
- Use the federation `uri` for stable post identity across instances; retain the instance-local API ID only as needed for private refresh/checkpoint records. Preserve attachment positions and identities. [Status fields](https://docs.joinmastodon.org/entities/Status/)
- Use still-image attachment media, not avatars, link-card thumbnails, or quoted/boosted images. Inspect actual media hosts and explicitly allow the required HTTPS hosts through the existing downloader; do not accept arbitrary attachment hosts. [Attachment fields](https://docs.joinmastodon.org/entities/MediaAttachment/)
- For curated accounts, use their public media statuses, excluding boosts. Resolve account IDs on the selected instance rather than assuming IDs are portable. [Account media feeds](https://docs.joinmastodon.org/methods/accounts/#statuses)
- Reuse `MediaRecord`, `process_media`, `write_gallery`, and the existing freshness assessment. Keep the output under its own `scraping/data/` batch.

Before calling this a continuing collector, implement bounded pagination, a per-feed checkpoint/overlap, and retained-post refresh. Distinguish a confirmed missing/private post from a temporary API failure: remove withdrawn content on confirmed source evidence, but preserve the previous batch and report refresh failures. Rebuild combined snapshots after source refresh. Repeat collection once in a later window to measure **new** supply, not the same backfill twice.

## 4. Flickr: second, conditional pilot

### A. Check access and geographic supply first

Use a project application key kept in ignored local configuration. Request public photos only. If no key is available, record that dependency and continue with Mastodon/curated existing feeds; do not make a new scraper or paid service the fallback for this pilot.

Start with **two small named areas**, one around the Queen/Spadina demo area and one in Scarborough chosen from the actual demo coverage. Derive and record their bounds from known geography rather than inventing coordinates. For the pilot, manually check returned locations against the Toronto municipal boundary; a bounding rectangle can include neighbouring places or water.

Run at most six search requests initially, **25 photo results per request**, and cap downloads at **50 images**. Compare:

- A geographically constrained outdoor-photo search without issue terms.
- The same area with one concrete asset/issue term, such as sidewalk, drain, blocked access, or dumping.
- A small comparison without the outdoor-context restriction, because missing metadata could otherwise hide useful photos.

Use photo-only results, newest-upload ordering, a seven-day upload window, and available taken-date filters. Request geographic/date/licence metadata and a suitably sized image URL. Supported parameters include `bbox`, `media=photos`, `geo_context=2`, `sort=date-posted-desc`, and date limits. A bounding-box search is limited to 250 results per page, although this pilot stays well below that. [Photo search API](https://www.flickr.com/services/api/flickr.photos.search.html)

Allocate the 50-image cap across the search groups after metadata deduplication; downloading the first 50 hits would prevent a useful comparison between areas and filters.

Do not widen the current-issue window to years when the recent search is empty. Older photos may enter a separately labelled reference/evaluation set; they do not improve the fresh-observation yield.

### B. Resolve capture-date semantics before claiming freshness

**Flickr's “taken” date can default to upload time when EXIF is absent.** It can also have coarse precision and is not supplied as a timezone-aware UTC timestamp. Therefore, matching upload/taken dates are not proof of a fresh capture. [Flickr date semantics](https://www.flickr.com/services/api/misc.dates.html)

Inspect actual date/granularity fields and a few individual-photo responses before implementing conversion. Do not manufacture a timezone or second-level precision merely to satisfy `MediaRecord.captured_at`. Leave that field null when its meaning cannot be established. Retain a minimal date-evidence object on processed rows containing the raw taken value, reported precision, known timezone/basis, and uncertainty. The existing merged-row format can preserve optional metadata without changing the required input contract. [Individual-photo metadata](https://www.flickr.com/services/api/flickr.photos.getInfo.html)

Store returned coordinates and accuracy as **source location claims** in `location_evidence`; do not convert an accuracy level into an invented metre radius. Check whether the coordinate depicts the camera or the photographed object when that distinction matters. [Photo location metadata](https://www.flickr.com/services/api/flickr.photos.geo.getLocation.html)

Record licence and required attribution before selecting images for display. Keep necessary evidence through merge/export; if display requirements conflict with the existing privacy policy, exclude that image from public display. Public visibility alone is not the display decision.

### C. Build a persistent adapter only if the pilot is useful

If reviewed yield passes, add `scraping/collectors/flickr.py` and a small editable `scraping/config/flickr.json` for approved areas, query terms, licences, and caps. Reuse the shared pipeline. A Flickr photo ID is stable image identity; avoid importing owner/profile fields into the normalized record. Add public-availability and metadata refresh before treating saved snapshots as current input.

If the source provides good geolocated scenes but mostly old captures, classify its role as **reference imagery only**. If it contributes neither recent useful scenes nor useful references within the pilot, stop work on it for the hackathon.

## 5. Common freshness, location, and review rules

| Decision | Required handling |
| --- | --- |
| Recently uploaded; capture age unknown | Keep as an explicitly unverified candidate for scene/model evaluation; do not label the condition current |
| Known old capture or historical/repost clue | Exclude from the recent candidate handoff or send to age review; do not silently fall back to upload time |
| Source claims recent capture | Preserve the claim and its basis; still require current-condition verification before an alert |
| Toronto tag/account only | Discovery lead; no verified city classification or precise map pin |
| Named local place plus compatible visual clues | Toronto/location candidate; record the supporting clues and uncertainty |
| Place checked against map/reference and reviewer-confirmed | Record city/location support at the precision actually justified; an old reference verifies place, not today's defect |
| Normal infrastructure scene | Valid scene/negative example; no invented issue |
| Visible obstruction, damage, dumping, etc. | Issue candidate for the model/reviewer; observation is not an engineering determination or automatic alert |

Rank the last **72 hours** first and use **seven days** as the initial discovery limit. Apply both posting and known capture-date checks. Preserve person-focused/private-scene exclusions and the existing privacy gate before external analysis or publication.

Keep `alert_eligible: false` on every collected candidate. A future sender must independently verify current condition and location and recheck age immediately before sending. Neither a classifier score, a reviewer marking “useful,” nor a precise-looking geotag enables notifications.

Keep close-up and wider views linked to their parent post: the detail supports the possible issue, and the context can support location matching. Count an event once even when it has four images or is cross-posted to multiple platforms. Do not use the same reference frame as both query and matching target when evaluating geolocation.

## 6. Measurements and go/no-go gates

Record this funnel per source and discovery group:

**returned posts → attached images → downloaded → distinct → public infrastructure scenes → Toronto-supported scenes → age-evidence category → issue candidates → candidates with usable location evidence**.

“Toronto-supported” requires documented visual/map evidence beyond a tag or account residence. Keep caption-only location claims in a separate count. Report unknown capture age rather than treating the posting window as capture verification.

Use these **proposed pilot gates**, not claims about current accuracy or available volume:

Contribution counts below must pass the recent-upload and known-age checks. Report the unknown-capture-age subset separately; none of these gates establishes a verified current condition.

| Decision | Mastodon: up to 100 downloaded images | Flickr: up to 50 downloaded images |
| --- | --- | --- |
| Download reliability | At least 95% of eligible attempts fetch/decode; investigate systematic failures before expanding | Same |
| Useful scene contribution | At least 20 distinct reviewed Toronto-supported infrastructure scenes | At least 10 |
| Location contribution | At least five scenes with a specific, reviewable place/asset candidate | At least five, with the actual geo precision recorded |
| Role as an issue-candidate source | Aim for at least two distinct visually plausible issue events | Aim for at least one |
| Continuing supply | A later run adds new useful scenes; report elapsed time and incremental counts | Same, if promoted to a fresh-observation source |

Review **all pilot images when feasible**, including noise; otherwise label a random pre-ranking sample and keep targeted challenge examples separate. Do not call useful-scene precision/recall measured when only selected successes were reviewed. Report the number inspected and source concentration.

Passing scene/location gates but missing the issue target earns a **scene supplier** role, not an issue-discovery success. Failure after one focused discovery revision triggers a source switch or submission fallback. Do not fill quotas with graphics, old photos, repeated events, or unsupported Toronto claims.

Track useful scenes and distinct issue candidates **per reviewed image, per collection run, and per hour of collection/review effort**. Keep time spent reviewing noise visible. Reallocate collection capacity toward confirmed useful yield, while preserving some broad discovery and geographic diversity.

## 7. Deliverables and work order

| Order | Work item | Concrete finish condition |
| --- | --- | --- |
| 1 | Mastodon visual pilot and editable inputs | Bounded sample, complete counts, reviewed contact sheet, and source-role decision |
| 2 | Mastodon adapter if the pilot passes | Normalized batch/gallery, freshness fields, safe bounded requests, refresh/deletion behavior, and offline response checks |
| 3 | Flickr access/date/geo pilot if a key is available | Up to 50 images reviewed; capture-date uncertainty and location precision documented |
| 4 | Flickr adapter only if justified | Shared-format output with retained date/location/reuse evidence and source refresh |
| 5 | Revalidate and combine selected batches | New combined gallery and model handoff; older snapshots do not become fresh through merging |
| 6 | Select presentation examples and report gaps | 20–30 dependable examples; show scene-only, possible-issue, and reject/uncertain cases honestly |

Add per-source notes under `scraping/docs/`, sanitized pilot summaries under `scraping/research/results/`, and offline checks under `scraping/tests/`. The planned collector/config filenames above do not exist yet and are not runnable commands.

For each adapter, leave one small response-fixture check covering its meaningful boundaries: still-image ownership, visibility, timestamps, stable positions/identity, repeat-run duplicates, unsafe URLs, and failure preservation. Include Flickr's upload-equals-taken ambiguity and Mastodon's cross-instance identity in those checks. Ordinary tests must not make live API calls.

The model owner receives images plus normalized provenance, posting/capture evidence, location claims, hashes, automatic status, and review labels when available. Keep **recent-upload candidates**, **reviewed Toronto infrastructure scenes**, and **historical/reference images** distinguishable in exports. The current `recent-candidates.jsonl` is a technical/date candidate queue, not a substitute for the reviewed Toronto-scene set.

Record the combined data root so relative image paths resolve. Group evaluation splits by parent post and duplicate/event group. The collection work ends with a usable, inspectable input set and measured limitations; defect identification and location-model implementation remain with their respective owners.

## 8. If organic supply is insufficient

After the bounded pilots and one discovery revision per source, use the observed yield to set a realistic demo size. Keep the seven-day current-observation window. Ask the team to capture public infrastructure around confirmed Toronto locations, recording capture time and location and taking a detail view plus a wider context view. Include ordinary functioning infrastructure as well as any naturally observed problems; do not manufacture hazards.

Label these as team submissions and exclude them from social-source yield metrics. A smaller verified current set plus a larger clearly labelled unverified model-input queue is more useful than hundreds of images presented as fresh Toronto issue evidence without support.
