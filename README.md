# CivicLens frontend

A local, dependency-free frontend based on `features.md`, `initial-unfinalized-plans.md`, and the three references in `UI-photos/`. Navy surfaces, cyan navigation, category-colored map markers, dashboard charts, and a synchronized issue table follow the references.

## Run

With Node.js 18 or newer:

```sh
npm run dev
```

Open http://127.0.0.1:5173. No installation or build step is required. Alternatively serve the repository with any static HTTP server, for example `python -m http.server 5173`. ES modules require HTTP; opening `index.html` directly is not supported.

## Plug in your data

1. Edit the 24 fictional records in `src/data.js`, or replace `issueRepository.list()` with a request to your API. Its existing return values demonstrate the expected issue fields from the product plan.
2. Replace `issueRepository.submit(draft)` with your submission endpoint. The current implementation saves metadata in browser local storage and previews photos in memory only. Real photo transport, privacy processing, review, authentication, and publication belong on the backend.
3. Set `evidence_thumbnail` to a privacy-processed image URL to replace the evidence placeholder. Every seeded issue has `is_demo: true`.
4. `src/map.js` is the isolated map adapter. It renders real OpenStreetMap raster tiles styled for the dark interface with no API key, geographic markers, pixel-based clusters, panning, cursor-anchored eased zoom, double-click zoom, gentle pan momentum, Shift selection and box selection. Camera animation reuses the current tile scene until destination tiles are ready, and respects reduced-motion preferences. It can be replaced by MapLibre while preserving callbacks. Network access is required for tiles and optional fonts; an explicitly labeled schematic background and system fonts remain available offline.

## Implemented interactions

- Map Explorer uses a compact title and floating search / filter controls over the expanded map. It opens without a context panel. Pins open details; clusters open a sortable/filterable list without auto-zoom. Zoom in is explicit. Shift + click toggles issue IDs; Box select makes a rectangular selection; ordinary drag pans. Escape or blank-map click clears selection. Markers have contextual hover / focus previews; a single selected issue shows its uncertainty area. Fit all matching issues, keyboard map controls, a mobile detail sheet, and empty-result recovery are supported.
- Search, issue type, severity, time, neighbourhood, resolution, and sample infrastructure proximity filters are shared across map, table, and dashboard. The fixed sample date is **October 17, 2026**. The map shows a live count of visible issues; View area issues explicitly selects those records without changing global filters. Filter chips can be removed individually. Keyboard search suggestions jump to matching sample issues and neighbourhoods; no external geocoder is connected.
- Data Explorer defaults to all filtered Toronto records. View as table explicitly carries selected IDs with a removable scope chip. Columns sort (including semantic severity ordering); sticky headers, selection actions, pagination, per-page sizes, map navigation, and CSV / GeoJSON downloads work. View on map frames all selected records, with room for the context panel. Selected exports default to the selected rows.
- Dashboard counts, category bars, neighbourhood rankings, resolution chart, and timeline derive from the same filtered sample records. No fake percentage growth or live AI output.
- Saved bookmarks, recents, preferences, and pending submission metadata persist in this browser. Upload supports up to 3 JPEG / PNG / WebP photos, size validation, previews, removal, confirmed address, review, and a local receipt.
- The desktop demo role selector shows a sample volunteer review queue. Review decisions last for the session. It is **not authentication**. Mapillary and evidence are visibly unconnected integration placeholders. Dragging the person opens the honest Mapillary placeholder rather than fabricated coverage.

## Limits and production integration

The public demo uses coarse fictional coordinates. CSV omits coordinates; GeoJSON exports approximate uncertainty areas with a minimum 250m radius. Authorization and coordinate precision must be enforced on a real backend, including exports, rather than trusted to this client. Infrastructure coordinates / distances are samples. No actual AI, scraping, 311 requests, location lookup, Mapillary imagery, correction-pin workflow, saved query builder, or full-city infrastructure dataset is connected. There is no paid service or API key configured.

`src/app.js` owns UI state and rendering; `src/styles.css` contains responsive styles. `npm run check` validates module syntax. The local Node server in `scripts/serve.mjs` binds to loopback only.
