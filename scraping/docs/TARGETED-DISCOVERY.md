# Finding useful Toronto infrastructure photos

Investigated October 17, 2026. Recommendation: improve discovery and location evidence before scaling collection. Keep the existing adapters; the next work is source selection, scene review, and reference matching.

Current controls and follow-up: [COLLECTION.md](COLLECTION.md) documents the editable query file, combined Instagram/Bluesky gallery, conservative freshness flags, model-input handoff, and successful metadata-only Mastodon probe. The original targeted sample below remains an unverified discovery pilot.

## What the existing sample establishes

The saved Instagram review batch has 24 images from nine posts. All image records mention Toronto in their captions, eight carry a place claim, and none has a known capture time. A contact-sheet inspection shows mostly ads, celebrity cards, food, and people. One carousel supplies 13 records, illustrating why image count alone exaggerates sample diversity.

The saved broad Bluesky batch has 25 image records from 22 posts, with no structured location evidence or known capture dates. It also contains graphics and irrelevant scenes. These are access/download demonstrations, not evidence that useful issue discovery or geolocation works.

Instaloader and Apify are two ways of accessing Instagram, not two independent social platforms. Changing the tool while querying the same broad city population does not necessarily improve relevance.

The implemented shared pipeline validates and downloads images, strips metadata, and checks dates and duplicates. It does not implement the plan's automatic outdoor-scene classifier, civic-issue detector, or location verification. `ready` means technically downloaded.

## A targeted collection now available

A new, free, anonymous Bluesky collection is in `scraping/data/targeted-toronto/`. Existing batches were preserved. The sanitized machine-readable summary is [targeted-discovery-results.json](../research/results/targeted-discovery-results.json).

The test used a seven-day **posting** window, one page and at most 25 posts per query:

| Query | Returned posts |
| --- | ---: |
| `Toronto pothole` | 0 |
| `Toronto sidewalk` | 16 |
| `Toronto "bike lane"` | 25 |
| `Toronto flooding` | 7 |
| `Scarborough dumping` | 0 |
| `Spadina construction` | 2 |
| `"Queen" "Spadina"` | 25 |
| `Toronto streetphotography` | 14 |

After overlap between queries: **89 posts, 31 posts with attached photos, 44 image downloads, 43 images available for review, one exact duplicate excluded, no download failures, US$0 spent.** Some queries hit the cap; these are returned counts, not exhaustive totals or a daily supply estimate. Search matches can involve alt text and do not guarantee the intended semantic relationship between words.

One particularly useful post supplies four photos of a reportedly misaligned storm-drain grate at Queen/Spadina. A wider image contains the grate, streetcar tracks, a Queen Street sign, and construction signage naming Queen and Spadina. Close-ups show the grate and an annotated alignment claim. This is one issue candidate with multiple views, not four independent issue events. The post was uploaded October 12; capture time is unverified. No reference-image match or engineering assessment was performed.

Other results demonstrate the necessary rejection checks: Seattle bike lanes described as “Toronto style,” a 125-year-old sidewalk photo, weather notices from outside Canada, charts, and street portraits. Several outdoor photos show no evident infrastructure defect. Some street-photography posts explicitly describe older capture dates despite recent uploads.

Review at **http://127.0.0.1:8766/**. Search `misaligned` to see the drain example; clear the search for the full batch. The gallery remains unlabelled and private. To restart it:

```sh
.venv/bin/python -m scraping.demo serve --out scraping/data/targeted-toronto --port 8766
```

## Change discovery first

1. **Issue searches:** combine Toronto/local place terms with concrete objects and complaints: sidewalk blocked, curb ramp, drain grate, pothole, dumping, damaged shelter, bike lane obstruction. Issue names and local intersections are better starting points than the word “infrastructure.” Test each query separately; do not assume Boolean syntax works identically across sources.
2. **Outdoor-scene searches:** intersections, streets, transit stops, and local streetscape photography. Keep scene usefulness separate from defect detection. People-focused street photography still needs rejection under the existing privacy policy.
3. **Curated public feeds:** inspect cycling/walking advocates, neighbourhood reporters, and public-space photographers for original outdoor photos before selecting accounts. Skip feeds dominated by campaign cards and announcements. Institution names alone do not ensure useful photos.
4. **Instagram discovery:** prefer inspected account feeds and known photo/carousel URLs. Test more specific civic tags and small public-place IDs individually. A city-wide location tag is too broad. The current Instaloader wrapper accepts location IDs; the current Apify wrapper accepts direct URLs. Neither currently exposes arbitrary caption search or a geographical bounding box. Apify's published search input distinguishes hashtag, profile, and place discovery; it is not a guaranteed keyword search over every public caption. Its README and schema still disagree about some hashtag/place outputs, so test response shapes before relying on them.
5. **Scene review:** for the small pilot, use human labels first. Then evaluate one Gemini pass for public outdoor scene, visible issue evidence, readable location clues, privacy, and historical-photo warnings. Add SigLIP only if measurement justifies a second model. Model guesses do not establish the location or physical defect.

## Establish location separately

Use a progression: **discovery hint → claimed place → visually supported candidate → reference checked → human verified**. A Toronto tag, an account's home city, and a tagged venue's centroid are discovery/location claims, not a camera coordinate.

For a retained public scene:

1. Read visible street names, stop IDs, public-business signs, and landmarks; retain their evidence separately from caption claims.
2. Resolve candidate intersections/assets using Toronto Centreline, address points, TTC stops, or OSM. Apply the municipal boundary after resolution; a city bounding rectangle alone can include neighbouring municipalities and the lake.
3. Compare candidates with street-level reference images using stable details such as facade geometry, road/track layout, and corner configuration. Inspect the reference capture date. Keep a coarse area or abstain when evidence is insufficient.
4. Store the reference image ID, capture date, match explanation, location precision, and reviewer decision. The reference camera location may differ from the defect's location.

An older reference can corroborate the **place** without corroborating that a transient defect still exists. Close-ups with no surroundings may remain unlocatable; collect a wider companion photo for team submissions.

## Tools already anticipated by the plan

| Source | Best role | What it does not establish |
| --- | --- | --- |
| Mapillary | Georeferenced outdoor reference imagery, capture dates, street-level comparisons; assess coverage around Queen/Spadina first | Fresh social discovery, guaranteed current defects, or perfect coordinate accuracy |
| Flickr API | Additional outdoor-photo discovery using `bbox`, `media=photos`, `geo_context=2`, date filters, `extras=geo,date_taken,date_upload,license,url_l`, and optionally issue text/tags | Reliable recent Toronto volume; user-supplied geotags still need checking. An application key is required. Outdoor context may be missing. |
| Wikimedia Commons | Small geotagged, licensed reference/evaluation supplement | Fresh issue reports; coordinates can identify the depicted object rather than the camera |
| Toronto 311, road restrictions, cycling network, TTC assets | Local issue categories, candidate areas, geographic anchors, and civic context | A ready-made verified photo feed, or proof that an image depicts the nearby record |
| Team phone photos | A dependable location test set with recorded coordinates and capture time | Organic social-discovery yield; disclose these separately |

Mapillary is the most useful next source for the proposed street-level comparison. Start with a coverage check and manual comparison in a small area before building the full embedding/matching cascade. Google Street View can also be opened for human comparison; automated acquisition/indexing would need a separate check of the applicable Google service terms.

## Sample size and next decision

For a demo, select **20–30 reviewed public outdoor scenes**, aim for **3–5 distinct issue candidates**, and include no-issue and rejected examples. Treat these as goals, not measured supply. Supplement with clearly labelled team photos if needed.

For the next discovery experiment, label **200 distinct images** split between broad/place discovery and targeted issue discovery, deduplicated and grouped by parent post/event. Measure useful-scene yield, distinct visible issue candidates, and candidates with usable location evidence. Repeat once in a later window to measure new supply. If promising, continue toward the original plan's 500–1,000-image experiment and independent holdout labels.

A larger random Toronto sample cannot repair missing location evidence. First demonstrate the complete path for the drain candidate: original image evidence → claimed intersection → reference comparison → reviewer confirmation. Keep this curated demo separate from an unbiased discovery benchmark.

## Documentation checked

- [Bluesky search lexicon](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/searchPosts.json): date/sort/author/tag parameters; query syntax and complete pagination are not guaranteed.
- [Apify Instagram input schema](https://apify.com/apify/instagram-scraper/input-schema) and [README](https://apify.com/apify/instagram-scraper): separate discovery types and output caveats.
- [Instaloader location posts](https://instaloader.github.io/module/instaloader.html#instaloader.Instaloader.get_location_posts): location-listed posts require login.
- [Mapillary's API example](https://github.com/mapillary/api-demo): coverage, image metadata, capture dates, detections, and viewer. The full developer reference required login during this check; Toronto coverage was not measured.
- [Flickr photo search](https://www.flickr.com/services/api/flickr.photos.search.html): geographic, outdoor-context, media, date, and license filters.
- [Google Street View policies](https://developers.google.com/maps/documentation/streetview/policies): consult the applicable API policies and service terms for any integration.
