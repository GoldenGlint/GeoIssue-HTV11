# GeoIssue

Toronto civic-issue workspace for Hack the Valley. Social photos are collected, screened and described (`scraping/`), turned into map-ready issues (`analysis/`), and explored, verified and corrected in a dependency-free web app (`src/`).

Start with the [collection package guide](scraping/README.md) for setup, commands, editable searches, and adding a source. The shared image format and processing live in [scraping/media.py](scraping/media.py).

| Area | Start here |
| --- | --- |
| Web app: run it, plug in data, what is implemented | [Frontend](#frontend) below |
| Photos to map-ready issues: locate, merge, priority, area stats | [analysis/README.md](analysis/README.md) |
| Issue fields shared by the analysis and the app | [data-contract.md](data-contract.md) |
| Tiger Data setup, collected and simulated datasets, live report activity and benchmarks | [Tiger Data integration](tiger-data-plan.md) |
| Vultr hosting, on-demand ingestion, deployment and demo checks | [Vultr implementation plan](vultr-plan.md), [deploy guide](deploy/README.md) |
| Working collectors and review tools | [scraping/README.md](scraping/README.md) |
| Current collection status, freshness policy, and model handoff | [Collection workflow](scraping/docs/COLLECTION.md) |
| Automatic Gemini screening (Toronto / issue / locatability) | [Screening](scraping/docs/SCREENING.md) |
| Image-source experiment and expansion decisions | [Targeted discovery](scraping/docs/TARGETED-DISCOVERY.md) |
| Next social/photo sources and pilot gates | [Source expansion plan](scraping/docs/SOURCE-EXPANSION-PLAN.md) |
| Overall ingestion proposal | [Social-image ingestion plan](social-image-ingestion-plan.md) |
| Original project proposal | [Initial plan](initial-unfinalized-plans.md) |
| Challenge brief | [School of Cities](2026.10%20Hack%20The%20Valley%20School%20of%20Cities.md) |
| Civic-data references | [Toronto datasheet](2026.10%20Hack%20The%20Valley%20Datasheet.md) |

Source image batches, local credentials, and session files stay in ignored local storage. The evidence photos referenced by the public app data are included in `data/analyzed/photos/` under the current display policy. Research summaries in `scraping/research/results/` contain sanitized evidence rather than raw account data.

## Frontend

A local, dependency-free frontend based on `features.md`, `initial-unfinalized-plans.md`, and the three references in `UI-photos/`. Navy surfaces, cyan navigation, category-colored map markers, dashboard charts, and a synchronized issue table follow the references.

### Run

With Python 3.11 or newer (recommended, because it adds the Gemini features):

```sh
cp .env.example .env        # then put your key in .env: GEMINI_API_KEY=...
python scripts/serve.py     # http://127.0.0.1:5173
```

`scripts/serve.py` serves the app and a small local API (`/api/status`, `/api/triage`, `/api/digest`) that calls Gemini with the key from `.env`, so the key never reaches the browser. It never serves hidden files such as `.env`. Without a key, the app works and the AI features say they are off.

For Tiger Data, follow [the integration guide](tiger-data-plan.md): install the optional PostgreSQL driver, set `TIGER_DATABASE_URL`, initialize the schema, then add `--tiger` to the analysis command. The same server supplies database-backed issues and hourly report activity. The dashboard refreshes every 15 seconds and clearly labels the simulated dataset. Gemini and Tiger Data work independently.

With Node.js 18 or newer, `npm run dev` serves the app without the Gemini API or Tiger Data, so it has no issues to show; use `scripts/serve.py` with `TIGER_DATABASE_URL` for data. No installation or build step is required either way. Don't use `python -m http.server` once a `.env` exists: it would serve the key. ES modules require HTTP; opening `index.html` directly is not supported.

The app opens in light mode; the header sun/moon button or Preferences → Appearance switches to dark or follows the system setting. Both themes are colour tokens at the top of `src/styles.css` (light on `:root`, dark under `[data-theme="dark"]`); use the tokens rather than raw colours, and `npm test` checks that every text token meets WCAG AA contrast in both themes. `PRODUCT.md` and `DESIGN.md` describe the product and the visual system.

#### Locate a photo with Claude (optional)

`scripts/serve.py` can also find where a photo was taken by running [Claude Code](https://claude.com/claude-code) headless on this computer, with Opus driving the geolocation tools in `research/geoloc_tests/` (place, map and City-asset search, Mapillary image matching, pose estimation). It needs:

- the `claude` command, logged in (it uses your Claude Code login; no API key);
- the tools' Python environment, `research/geoloc_tests/.venv` (or set `GEOLOC_PYTHON` in `.env`), its data indexes in `research/geoloc_tests/data/` and a `MAPILLARY_TOKEN` in `research/geoloc_tests/.env`;
- a CUDA GPU for image matching (a laptop RTX 4060 works; other GPU work on the same machine slows matches down a lot).

Each photo runs as a detached background job (`research/geoloc_tests/claude_geoloc.py`), so it keeps going when the dialog, the page or the server closes; jobs wait their turn so matches don't share the GPU. Claude Code starts with its built-in tools off and your settings, plugins and hooks unloaded; its only tools come from `research/geoloc_tests/geoloc_mcp.py`. Only an accepted image match (75+ verified points) counts as verified; otherwise the harness widens the radius to 1 km and caps confidence at 0.3. `GEOLOC_MODEL` (default `opus`), `GEOLOC_EFFORT` (`high`), `GEOLOC_MINUTES` (time budget, `10`) and `GEOLOC_MAX_RUNNING` (`1`) tune it. A run is never started automatically: only Locate with Claude, Submit with an unknown location, or Locate a photo in Photo locations start one. Not enforced yet: because a run is expensive, it should later only be offered once Gemini's triage says the photo shows a real issue and looks locatable, and the person approves it. The same runner works from the command line: `research/geoloc_tests/.venv/Scripts/python research/geoloc_tests/claude_geoloc.py --image photo.jpg`.

### Plug in your data

`data-contract.md` documents the issue shape, the submission draft and the infrastructure format.

1. The app opens on the analysed scraping handoff: `data/analyzed/issues.public.json` (which follows `data-contract.md`), the run report for the funnel, and per-ward summaries for the digest. Refresh it with `python -m analysis --input scraping/shared/post-groups.jsonl` (see `analysis/README.md`). The **data switch** in the page header changes to 240 deterministic, fictional sample records spread over the 90 days before the fixed demo date (**October 17, 2026**), with a sample rainstorm on Oct 4–6 so the timeline has a real event in it; every sample record has `is_demo: true`. A choice made in the switch is remembered in the browser, and without analysed issues the app shows the sample. Later, replace `issueRepository.list()` with a request to your API.
2. Replace `issueRepository.submit(draft)` with your submission endpoint. The current implementation saves metadata in browser local storage (pin rounded to about 100 m) and previews photos in memory only. Real photo transport, privacy processing, review, authentication, and publication belong on the backend.
3. Set `evidence_thumbnail` to the evidence photo URL. The current policy displays collected photos in full, including those flagged for face/plate blurring. Run the analysis against `scraping/data/handoff/post-groups.jsonl` to copy the local handoff's images into `data/analyzed/photos/`. Fictional records use credited sample photos from `assets/evidence/` (CC BY / CC BY-SA, see `assets/evidence/CREDITS.md`), labelled as samples that do not depict the record.
4. `src/map.js` is the isolated map adapter. It renders real OpenStreetMap raster tiles styled for the active theme with no API key, geographic markers, pixel-based clusters, panning, cursor-anchored eased zoom, pinch zoom, double-click zoom, gentle pan momentum, Shift selection and box selection. Camera animation reuses the current tile scene until destination tiles are ready, and respects reduced-motion preferences. It can be replaced by MapLibre while preserving callbacks. Network access is required for tiles and optional fonts; an explicitly labeled schematic background and system fonts remain available offline.
5. Infrastructure layers use real OpenStreetMap geometry for TTC subway/LRT stations and four major roads (`src/osm-infrastructure.js`, regenerated by `python scripts/fetch-osm-infrastructure.py`). School positions are an approximate sample list.
6. Wards come from the City of Toronto's 25-ward boundaries (`src/ward-boundaries.js`, regenerated by `python scripts/fetch-ward-boundaries.py`; Open Government Licence – Toronto). Sample issues get their ward by point-in-polygon, and the map can draw ward outlines.

### Implemented interactions

- **Map Explorer** uses a compact title and floating search / filter controls over the expanded map. It opens without a context panel. Pins open details; clusters open a sortable/filterable list without auto-zoom. Zoom in is explicit. Shift + click toggles issue IDs; Box select (dashed square) makes a rectangular selection; ordinary drag pans, and a middle-button drag pans in either mode. Escape or blank-map click clears selection. High-severity pins and clusters carry a "!" badge, so severity never depends on colour alone. The selected pin is moved clear of the side panel or phone bottom sheet. Markers have contextual hover / focus previews; a single selected issue shows its uncertainty area. Fit all matching issues, keyboard map controls, and empty-result recovery are supported.
- **Issue details** show the full evidence photo without cropping, an enlarged viewer with previous/next controls, thumbnails for available companion photos (labelled as context), original social-post links, a **priority score with its reasons** (same rules as the analysis pipeline, `src/priority.js`), a "How this location was estimated" trace (method, cascade steps, visual clues, radius and confidence; from the analysis for analysed posts, illustrative for sample records), ward, last seen, nearby infrastructure and why it was flagged.
- **Ward outlines:** Infrastructure & proximity → Ward boundaries draws the 25 wards; clicking a ward label filters everything to that ward.
- **Shared filters** (search, issue type, severity, status, time, ward or neighbourhood, and infrastructure proximity) apply across map, table, and dashboard. Proximity works for one asset type or "any infrastructure". Filter chips can be removed individually. Search suggestions jump to matching issues, neighbourhoods and wards; no external geocoder is connected.
- **Data Explorer** defaults to all filtered Toronto records. View as table explicitly carries selected IDs with a removable scope chip. Columns cover priority, area and ward, location with nearest asset, detected, last seen, sightings, confidence, source and verification; they sort (including semantic severity ordering). Switching the demo role to City Staff sorts by priority. Sticky headers, selection actions, pagination, per-page sizes, map navigation, and CSV / GeoJSON downloads work. The **Query** tab shows the active filters, scope, sort and page as a read-only SQL statement plus the issue schema. Escape clears the table selection.
- **Dashboard** cards, timeline (daily up to 30 days, weekly beyond), category bars, resolution chart and hotspots derive from the same filtered sample records. With a 7- or 30-day filter, cards compare against the previous period of the same length computed from the data; no invented growth. The **ward digest** summarizes one of the 25 wards from the filtered records with a fixed, labelled template and counts down to the October 26 municipal election; with a Gemini key, "Write a summary with Gemini" adds a neutral written digest from the same counts (using the analysis pipeline's prompt), and on pipeline data it shows the pipeline's own summary. The **pipeline funnel** shows sample ingestion metrics (labelled as such) on sample data, and the real stage counts from the latest run on pipeline data.
- **Upload** supports up to 3 JPEG / PNG / WebP photos, size validation, previews, removal, a drag-the-map pin picker limited to Toronto, nearest address, review, and a local receipt. With a Gemini key, adding a photo **fills in category, severity and description** (editable, marked "Suggested by Gemini"), **refuses photos where a person is the subject** or that show a private space, and **pixelates faces and licence plates**; "Blur an area" lets anyone blur more by hand, with or without Gemini. "**Already reported nearby**" lists open issues of the same type within 150 m; "This is the same issue" adds a sighting (raising its priority) instead of filing a duplicate. Submissions and sightings appear under Saved. With Claude Code set up (see [Run](#locate-a-photo-with-claude-optional)), **Locate with Claude** under the pin picker finds where the first photo was taken in the background, shows each step as it runs, and offers **Move the pin here** with the radius and whether street imagery verified it; the review and the saved submission record that the pin came from Claude. **I don’t know where this is** drops the pin, address and confirmation: the issue can be submitted straight away, Claude starts on Submit (or on Locate with Claude), and its answer becomes the submission's location when the job ends, even after a reload; Saved → Your submissions shows locating, located (verified or not) or not found. **Photo locations** in the page header lists every job (running, finished or failed) with its evidence, the street-level references it compared, Show on map, Street View and Cancel, and a toast says when a job finishes.
- **Methodology** (sidebar → Help & methodology): data sources and licences, how an issue reaches the map (what is live, sample or in progress), the priority rules, privacy, and what the data can't tell you.
- Saved bookmarks, recents, preferences, and pending submission metadata persist in this browser. The demo role selector (sidebar, or Settings on a phone) shows a sample volunteer review queue. Review decisions last for the session. It is **not authentication**. The person icon opens Google Street View in a new tab: click it for the map centre, or drag it onto the map. GeoIssue links to Street View but never copies its imagery; an in-app Mapillary viewer is still future work.
- **Density** replaces the pins with a heat surface weighted by sightings, with its own scale. Click a hot spot to list the issues under it.
- **Crew routes** (climate action): the green *Plan crew route* button on the map plans the issues in view; a selection (box select, Shift + click, a cluster or *View area issues*) has the same button in its panel. The app orders the stops to keep driving short (nearest-next from every stop, then 2-opt), draws the route on the map, and estimates distance, driving time and CO₂ for a gas van versus an electric van, compared with visiting the issues in the order they were reported. *Directions in Google Maps* opens the first 11 stops. The assumptions are listed in the panel and in `src/route.js`; distances are straight lines × 1.3, so treat the figures as planning estimates.
- **Corrections**: *Suggest correction* on any issue reports a wrong location, wrong issue type, a fix, or "not a public issue". A location can be set by dragging the map under a pin, pasting a Google Maps link, or typing coordinates in decimal degrees, degrees-minutes or degrees-minutes-seconds (`src/coordinates.js`, tested by `npm test`). Corrections appear under Saved and in the volunteer Verify queue; accepting one updates the issue and its location trace.
- On phones the sidebar becomes a bottom tab bar, and the map supports pinch zoom.

### Limits and production integration

The public demo uses coarse fictional coordinates. CSV omits coordinates; GeoJSON exports approximate uncertainty areas with a minimum 250m radius. Authorization and coordinate precision must be enforced on a real backend, including exports, rather than trusted to this client. Sample ingestion funnel numbers, geolocation traces and explanations are illustrative. Gemini is used only through the local server and only when a key is in `.env`; photos are sent to Gemini for suggestions and blurring but never stored or published by this prototype. Locate with Claude sends the photo to Anthropic through Claude Code and keeps it, with the job's log, in `data/geolocate/` on this computer (ignored by git). Scraping runs separately (`scraping/`) and reaches the app through the analysis pipeline. No 311 requests, street-address geocoding, in-app Mapillary imagery or saved query builder is connected; corrections and reviews are stored in this browser only.

### Code layout

| File | Owns |
| --- | --- |
| `src/app.js` | Shell (sidebar, header, shared filters), routing, actions, keyboard shortcuts |
| `src/views/map-view.js` | Map Explorer page and the selection panel |
| `src/views/data-view.js` | Data Explorer table and Query tab |
| `src/views/dashboard-view.js` | Dashboard, ward digest, pipeline funnel |
| `src/views/workspace-view.js` | Saved, Recents, Verify |
| `src/views/methodology-view.js` | Methodology page |
| `src/modals.js` | Upload (Gemini suggestions, blurring, nearby reports), correction, Street View, infrastructure, export, settings, help, share and issue dialogs |
| `src/coordinates.js`, `src/search.js` | Reading Google Maps links and decimal / DMS coordinates, directions links; the search box and its suggestions |
| `src/route.js` | Crew route planning and its distance and CO₂ estimates (`npm test` covers it) |
| `src/api.js`, `src/blur.js` | Calls to the local API (Gemini, geolocation jobs); face/plate pixelation on a canvas |
| `src/state.js` | Shared UI state, browser persistence, local sightings |
| `src/issues.js`, `src/priority.js` | Filter, sort and search logic; priority score and reasons |
| `src/ui.js`, `src/format.js`, `src/icons.js` | Shared components, formatting helpers, icons |
| `src/data.js` | Sample issue generator, wards, infrastructure, `issueRepository` (collected or simulated issues from Tiger Data) |
| `src/ward-boundaries.js`, `src/osm-infrastructure.js` | Generated geodata (see scripts/) |
| `src/map.js` | Map engine |
| `src/styles.css` | Responsive styles |
| `scripts/serve.py` | Dev server with the Gemini API and the Claude geolocation jobs (recommended) |
| `src/geolocate.js` | Claude geolocation jobs: polling, the header indicator, the Photo locations dialog |
| `research/geoloc_tests/claude_geoloc.py`, `geoloc_mcp.py` | One geolocation job: Claude Code headless, and the MCP server that gives it the tools |
| `scripts/serve.mjs` | Static Node dev server |
| `scripts/export-analysis-reference.mjs` | Exports the frontend's neighbourhoods, wards and infrastructure for the analysis |
| `scripts/fetch-ward-boundaries.py`, `scripts/fetch-osm-infrastructure.py`, `scripts/fetch-osm-places.py` | Regenerate the ward and OpenStreetMap geodata, and the analysis's place gazetteer |
| `tests/` | `npm test`: coordinate parsing (needs Node 21 or newer) |
| `research/geoloc_tests/tests/` | Geolocation jobs, their MCP server and the server endpoints, with a fake `claude`: `research/geoloc_tests/.venv/Scripts/python -m unittest discover -s research/geoloc_tests/tests -t research/geoloc_tests` |

`npm run check` validates module syntax. Both dev servers bind to loopback only and refuse hidden files.
