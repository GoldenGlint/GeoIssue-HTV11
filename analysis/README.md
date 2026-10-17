# CivicLens analysis

Takes the photo-analysis output (JSON records plus photos) and produces what the map, table and ward pages need:

1. **Locate** (map-ready issues): coordinates, or a place named in the location guess or post text (an intersection such as "Queen and Spadina", a station or a park, from `analysis/refdata/`), then the ward from the City's boundaries, neighbourhood, nearest TTC station / school / road and a street-corner address. Each step is recorded in `geo_trace`, which the issue panel shows as "How this location was estimated".
2. **Dedupe**: sightings of the same issue (same type, close together, within 14 days, or a reposted photo) become one incident with a sighting count. Several photos from one post count as one sighting.
3. **Priority**: a 0-100 score with the reasons that produced it, for example `High severity (+40)` or `49 m from University of Toronto Scarborough (+15)`.
4. **Stats and summaries**: counts and 7-day trends per neighbourhood and ward, plus a short neutral summary per ward. Summaries come from Gemini when `GEMINI_API_KEY` is set and from a plain template otherwise.

It needs only Python 3.11 or newer. Nothing has to be installed.

## Run

```sh
python -m analysis                                # the fictional sample in analysis/samples/
python -m analysis --input path/to/their_output   # a .json or .jsonl file, or a folder of them
python -m analysis --input scraping/shared/post-groups.jsonl   # the scraping handoff: refreshes what the app shows
python -m analysis --offline                      # template summaries, no Gemini calls
python -m unittest discover -s analysis/tests -t .  # the tests
```

Then serve the repo with `npm run dev` or `python scripts/serve.py`. (Not `python -m http.server`: it would also serve `.env` and its Gemini key.) The map, table and dashboard load `data/analyzed/issues.public.json`, whose records follow `data-contract.md`, and fall back to the demo records when that file is missing.

The public output of the scraping handoff is committed, so the app shows the analysed posts on a fresh clone. After a new handoff, re-run the scraping line above and commit `data/analyzed/issues.public.json`, `report.json` and `areas.json`. Running the fictional sample overwrites them, so don't commit after that.

## When their output format changes

Edit `analysis/config.toml` only:

- **`[fields]`** lists where each value can be found in an input record, for example `lat = ["lat", "location.lat", "gps.latitude"]`. The first one present wins. Add the new path to the list.
- **`[values.*]`** maps their labels onto the frontend's values, for example `"Pothole" = ["pothole", "road damage"]`.
- **`[input] explode = "issues"`**: when one photo lists several issues, each becomes its own record, readable as `issue.type`, `issue.severity` and so on.

After every run, the console and `data/analyzed/report.json` list the input fields that weren't used and the labels that weren't recognised, so you can see what to add.

## When their output already has some of this

If a record already carries a neighbourhood, ward, address, incident ID or priority, that value is kept and the stage fills in only what's missing. `report.json` → `field_sources` shows where each field came from (`input`, `locate`, `dedupe`, `priority` or `default`).

- To recompute a value anyway, set `overwrite = true` on that stage in the config.
- To turn a stage off, set `enabled = false`.
- To remove a stage completely, also delete its file in `analysis/stages/`. Each stage is only imported when it's enabled.

The output stays valid for the frontend with every stage off.

## Output (`data/analyzed/`)

| File | What |
|---|---|
| `issues.public.json` | What the frontend reads: the Issue fields in `data-contract.md`, plus title and priority. Unverified issues are snapped to a 250 m grid, and the radius is widened to cover the true spot. Committed. |
| `issues.json` | Full incidents with precise locations, nearby assets and provenance. For internal use; gitignored. |
| `sightings.json` | Every input record after locating, with its `incident_id`. Gitignored. |
| `areas.json` | City, neighbourhood and ward stats, plus summaries. Committed. |
| `report.json` | Counts, dropped records and why, unused fields, unrecognised labels, field sources, warnings. Committed. |
| `photos/` | Evidence photos copied and renamed by issue ID. Gitignored; photos that need blurring are never copied. |

## Privacy

- Only the fields named in `[fields]` are read. Authors, handles and anything else are never copied, and `[output] private_fields` blocks them even when listed in `passthrough`.
- Post text is used only to find a place name, and the post ID only to count photos from one post as one sighting. Neither is written out.
- Issue IDs are `CL-` plus the first 8 hex characters of SHA-1(source post ID, plus `#n` for the n-th issue in a photo), so the post ID itself isn't published.

## Reference data

`analysis/refdata/toronto/` is exported from the frontend's `src/data.js` by `node scripts/export-analysis-reference.mjs`. Analyzed issues therefore use the same neighbourhood, ward and asset IDs as the map's filters and layers. TTC stations and major roads are real OpenStreetMap geometry; schools are approximate.

Neighbourhoods are assigned by the nearest of the frontend's 71 sample street corners, and each neighbourhood has one approximate ward. Area assignment is approximate, so every output is marked `reference_data: "placeholder"`. To add the City's official ward or neighbourhood boundaries, see `analysis/refdata/README.md`.
