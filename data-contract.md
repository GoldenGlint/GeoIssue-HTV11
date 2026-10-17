# CivicLens data contract (frontend ⇄ issue API)

The frontend reads everything through `issueRepository` in `src/data.js`. Today it returns generated sample records; swap its two methods for API calls and the map, table, dashboard and exports keep working unchanged.

| Method | Today | Replace with |
| --- | --- | --- |
| `issueRepository.list()` | 240 deterministic sample issues | `GET /api/issues` → `Issue[]`, already filtered by the caller's role and privacy rules |
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
| `first_seen_at`, `last_seen_at` | ISO 8601 UTC string | |
| `source_category` | `'Public social post' \| 'Public imagery' \| 'Community submission'` | |
| `description` | string | Short, factual. |
| `explanation` | string | Why it was flagged; grounded in the evidence. |
| `evidence_thumbnail` | URL \| null | Privacy-processed (blurred, EXIF-stripped) derivative only. |
| `evidence_credit` | `{ title, author, license, license_url, source_url, is_sample }` \| null | *display* Required when the image is third-party or a sample. |
| `is_demo` | boolean | `true` for every sample record. |

Never include usernames, handles, author IDs, original post URLs, or precise coordinates for unverified issues in public responses.

## Submission draft (`submit`)

```json
{
  "category": "Pothole",
  "description": "Deep pothole in the curb lane",
  "address": "King St W & Spadina Ave",
  "coordinates": [-79.395, 43.646],
  "created_at": "2026-10-17T14:02:11.000Z"
}
```

`coordinates` come from the upload form's map pin and are rounded to 3 decimals (about 100 m) before leaving the browser. Photos are sent separately once real upload, privacy processing and review exist; the prototype never uploads them.

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

`wards` maps the 25 ward numbers to names. The sample assigns each neighbourhood one ward, which is only approximate. The dashboard's ward digest is built from the filtered records with a fixed template; when an AI digest is connected, keep observed counts separate from generated text.
