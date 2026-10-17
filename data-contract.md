# CivicLens data contract (frontend ⇄ issue API)

The frontend reads everything through `issueRepository` in `src/data.js`. Today it returns generated sample records; swap its two methods for API calls and the map, table, dashboard and exports keep working unchanged.

| Method | Today | Replace with |
| --- | --- | --- |
| `issueRepository.sources()` | `{ sample: 240, pipeline: <count or 0> }` | Drop once there is one live source |
| `issueRepository.list(source)` | `'sample'`: 240 deterministic sample issues; `'pipeline'`: `data/analyzed/issues.public.json` | `GET /api/issues` → `Issue[]`, already filtered by the caller's role and privacy rules |
| `issueRepository.pipelineReport()`, `areaSummaries()` | `data/analyzed/report.json`, `areas.json` | Pipeline run metrics and per-area stats/summaries from the backend |
| `issueRepository.submit(draft)` | Saves metadata to browser storage | `POST /api/submissions` → `{ issue_id, verification_status: 'Pending review' }` |
| `issueRepository.submitCorrection(draft)` | Saves the correction to browser storage | `POST /api/issues/{issue_id}/corrections` → `{ correction_id, status: 'Pending review' }` |

Filtering, sorting, paging and search currently run in the browser (`src/issues.js`). When the dataset outgrows that, move the same filter semantics to query parameters; the Data Explorer's **Query** tab shows the equivalent SQL for the current filters.

## Issue

Fields follow `features.md` §7. Rows marked *display* are extras the UI uses that §7 does not list.

| Field | Type | Notes |
| --- | --- | --- |
| `issue_id` | string | Stable public ID, e.g. `CL-10712`. |
| `incident_id` | string \| null | Deduplicated incident; never a zoom-dependent map cluster ID. |
| `issue_type` | `'Pothole' \| 'Sidewalk damage' \| 'Graffiti' \| 'Litter' \| 'Flooding' \| 'Other'` | Keys of `categories` in `src/data.js`. |
| `severity` | `'High' \| 'Medium' \| 'Low'` | |
| `resolution_status` | `'Open' \| 'In review' \| 'Resolved'` | |
| `verification_status` | `'Needs review' \| 'Verified' \| 'Dismissed'` | |
| `geometry` | GeoJSON `Point` `[lng, lat]` | Public responses must already be coarsened. |
| `location_radius_m` | integer | Uncertainty radius shown on the map and in exports. |
| `geo_confidence` | number 0–1 | |
| `geo_method` | string | *display* e.g. `Visual clues + street-level match`, `Image GPS`, `Reporter-confirmed pin`. |
| `geo_trace` | `{ stage, result, status: 'match' \| 'skip' \| 'info' }[]` | *display* Steps of the geolocation cascade, shown as "How this location was estimated". |
| `geo_clues` | string[] | *display* Visual clues found in the image, e.g. `Street sign “Spadina Ave”`. |
| `neighbourhood_id` | string | City neighbourhood ID or slug. |
| `neighbourhood_name` | string | *display* |
| `ward_id` | string `'1'`–`'25'` | Assign by point-in-polygon against ward boundaries. |
| `ward_name` | string | *display* |
| `address` | string | *display* Nearest intersection or address, never a private residence. |
| `infrastructure_type` | `'TTC' \| 'Schools' \| 'Roads'` | Type of the nearest asset. |
| `asset_id` | string | Nearest asset. |
| `asset_name` | string | *display* |
| `distance_m` | integer | *display* Distance to the nearest asset. |
| `nearby_assets` | `{ type, asset_id, name, distance_m }[]` | *display* Nearest asset of each type, sorted by distance. Drives the "within N m of …" filter. |
| `detection_confidence` | number 0–1 | |
| `sightings_count` | integer | Independent sightings linked to this issue. |
| `priority_score` | integer 0–100 \| null | Staff priority. Computed by the analysis pipeline, or by `src/priority.js` for sample data (same rules). |
| `priority_reasons` | string[] | Why it scores that, e.g. `High severity (+40)`, `69 m from Finch Station (+12)`. Shown in issue details. |
| `first_seen_at`, `last_seen_at` | ISO 8601 UTC string | |
| `source_category` | `'Public social post' \| 'Public imagery' \| 'Community submission'` | |
| `description` | string | Short, factual. |
| `explanation` | string | Why it was flagged; grounded in the evidence. |
| `evidence_thumbnail` | URL \| null | Privacy-processed (blurred, EXIF-stripped) derivative only. |
| `evidence_credit` | `{ title, author, license, license_url, source_url, is_sample }` \| null | *display* Required when the image is third-party or a sample. Only `http(s)` source links are rendered. |
| `evidence_withheld` | string \| null | *display* Why there is no photo, e.g. it still needs face and plate blurring. Set by the analysis when a photo is flagged for blurring. |
| `evidence_blurred` | boolean | *display* Optional. `true` shows a "Faces and plates blurred" tag on the evidence photo. The pipeline should set it from the photo analysis's `privacy.blurred`. |
| `is_demo` | boolean | `true` for every sample record. |

Never include usernames, handles, author IDs, original post URLs, or precise coordinates for unverified issues in public responses.

## Submission draft (`submit`)

```json
{
  "category": "Pothole",
  "severity": "High",
  "description": "Deep pothole in the curb lane",
  "address": "King St W & Spadina Ave",
  "coordinates": [-79.395, 43.646],
  "blurred_areas": 2,
  "ai_suggestion": { "category": "Pothole", "severity": "High", "confidence": 0.87, "model": "gemini-3.5-flash-lite", "kept": ["category", "severity", "description"] },
  "created_at": "2026-10-17T14:02:11.000Z"
}
```

`coordinates` come from the upload form's map pin and are rounded to 3 decimals (about 100 m) before leaving the browser. `severity` may be null ("Not sure"). `ai_suggestion` is null without Gemini; `kept` lists the suggested fields the person left unchanged. Photos are sent separately once real upload, privacy processing and review exist; only the blurred versions should ever be uploaded, and the prototype never uploads them.

**Sightings.** "This is the same issue" in the upload form records `{ kind: "sighting", joined_issue_id, category, address, coordinates, description, created_at }` instead of a new issue, and adds one to that issue's `sightings_count` (re-scoring its priority). A backend should accept this as `POST /api/issues/{id}/sightings`.

## Local Gemini API (`scripts/serve.py`)

The dev server reads `GEMINI_API_KEY` from `.env` and exposes three endpoints; the browser never sees the key. Every frontend call fails soft (no server or no key turns the AI features off).

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /api/status` | — | `{ gemini: boolean, model }` |
| `POST /api/triage` | `{ image: base64, mime: "image/jpeg" \| "image/png" \| "image/webp" }` (the browser downscales to ≤ 1280 px) | `{ is_civic_issue, category, severity, description, confidence, public_scene, person_is_subject, faces: [[ymin, xmin, ymax, xmax]], plates: [...], reason, model }`. Boxes are scaled 0–1000. |
| `POST /api/digest` | `{ area: <one ward from areas.json, or the same shape built from the filtered issues>, label: "ward", trend_days }` | `{ text, method: "gemini:<model>" }`, written with the analysis pipeline's neutral prompt (`analysis/stages/summaries.py`). |

Errors come back as `{ error }` with 400 (bad input), 413 (too large), 502/504 (Gemini failed or unreachable) or 503 (no key).

## Correction draft (`submitCorrection`)

Anyone can suggest a fix to an issue from its detail panel. Nothing changes until a reviewer accepts it.

```json
{
  "issue_id": "CL-506AF535",
  "kind": "location",
  "coordinates": [-79.3941, 43.64735],
  "location_source": "google_maps_link",
  "note": "It is on the south curb, by the streetcar stop.",
  "created_at": "2026-10-17T14:02:11.000Z"
}
```

| Field | Notes |
| --- | --- |
| `kind` | `location`, `issue_type`, `resolved` or `not_an_issue` |
| `coordinates` | `[lng, lat]`, for `location` only. Kept at full precision: it is the issue's position, not a person's. |
| `location_source` | `map_pin` (dragged on the map), `google_maps_link` or `coordinates` (typed decimal, degrees-minutes or degrees-minutes-seconds) |
| `issue_type` | For `issue_type` only; one of the `categories` keys |
| `reason` | For `not_an_issue` only |
| `note` | Optional, up to 500 characters |

The server sets `status` (`Pending review`, `Accepted` or `Dismissed`). Accepting a location correction should move the issue, recompute its area, ward and nearby assets, set a small radius, and add a `geo_trace` step. The prototype does all of this in the browser, using the sample neighbourhoods and assets in `src/data.js`, and re-applies corrections accepted in that browser after a reload.

## Infrastructure

`infrastructure` in `src/data.js` is a list of `{ asset_id, type, name, geometry }` with GeoJSON `Point` or `MultiLineString` geometry:

- **TTC:** subway and LRT stations from OpenStreetMap.
- **Roads:** Gardiner Expressway, Don Valley Parkway, Highway 401 and Lake Shore Boulevard from OpenStreetMap.
- **Schools:** an approximate sample list. Replace it with the City's school locations dataset.

Regenerate the OpenStreetMap part with `python scripts/fetch-osm-infrastructure.py` (writes `src/osm-infrastructure.js`; © OpenStreetMap contributors, ODbL). In production, compute `nearby_assets` server-side with PostGIS (`ST_DWithin` / `ST_Distance` on geography).

## Wards and the election digest

`wards` maps the 25 ward numbers to names, and `wardBoundaries` (`src/ward-boundaries.js`, City of Toronto open data) holds their outlines; `wardAt([lng, lat])` returns the ward for a point. Sample issues get their ward this way. The analysis pipeline still assigns wards from its reference neighbourhoods (one ward each) and should switch to these boundaries. The dashboard's ward digest always shows the template paragraph from the observed counts; Gemini text (from the pipeline or written on demand) appears separately and is labelled as such.
