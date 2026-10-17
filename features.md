CivicLens — Product Features & Interface Plan (v4 — decisions finalized)
Status: Four core UX decisions approved on 2026-10-17; remaining questions identified separately. Planning specification for Hack the Valley 11. Audience: Public residents, volunteers, City staff. Core principle: One civic issue dataset, two synchronized workspaces: Map Explorer and Data Explorer.
1. Application shell and persistent sidebar
A persistent left navigation sidebar is shared across both primary pages. On smaller screens, it collapses to icons or a drawer.
Map Explorer: map-based issue discovery and geographic investigation.
Data Explorer: SQL-like interactive issue table, bulk operations, and exports.
Upload new issue: prominent sidebar button available from both explorers; opens a dedicated submission form.
Saved: saved issues, saved searches/filters, bookmarked locations, drawn areas, and collections.
Recents: recently visited issues, areas, and searches (user-controlled history).
Verify: volunteer review queue (role-gated).
Settings / Help: preferences, legends, accessibility, methodology, and data sources.
Account identity at sidebar bottom: avatar, username/display name, account type (Public, Volunteer, City Staff), and account menu (profile, sign out). Guest access may show “Guest / Public.”
Navigation behavior: The current page is highlighted. Map position, selected filters, and selected issues are preserved when moving between Map Explorer and Data Explorer where practical.
2. Map Explorer — primary page
2.1 Main canvas
Full interactive 2D Toronto street map showing roads, highways, landmarks, neighbourhoods, and chosen infrastructure overlays.
Click/drag to pan; scroll, pinch, or buttons to zoom; search and fly to an address, intersection, ward, neighbourhood, school, TTC stop, or landmark.
A Search this area control re-runs results for the current viewport.
Markers represent verified or appropriately generalized AI-detected issues. Different symbols/colours indicate issue type; status and severity remain discernible without relying solely on colour.
At low zoom, nearby markers form numbered clusters; zooming in splits clusters into individual pins.
Map modes: Pins, Heatmap, and Neighbourhood/Ward boundaries (heatmap is secondary scope).
2.2 Explicit contextual right-panel rule
The right-side contextual panel is closed by default. It opens only after the user selects:
One issue pin → the issue detail view.
One numbered cluster/group of pins → a filterable, scrollable issue list within that cluster.
Multiple selected issue pins → a filterable, scrollable selection list with aggregate counts and actions.
It does not automatically open when the user pans, zooms, searches, changes filters, clicks empty map space, or selects an infrastructure overlay. Search results may instead appear as lightweight map hints or a left-side overlay; the issue detail panel remains selection-driven.
Clicking the selected issue or a row in a cluster/multi-selection list switches the same right panel to that issue's details. Provide a Back to results action to return to the cluster/selection list. Close via X, Escape, or clicking blank map space (unless doing a selection gesture).
2.3 Individual issue detail (in right panel)
Photo/blurred evidence, category, short description, and AI-supported explanation.
Approximate or verified location, detected/last-seen time, infrastructure relationship, and nearby relevant 311 context when available.
Severity, verification/resolution status, detection confidence, geolocation confidence radius, and number of independent sightings.
Save/bookmark, share view, inspect related sightings; role-gated verify, correct pin, or manage status.
Never reveal usernames, private interiors, or precise uncertain locations to unauthorized users.
2.4 Cluster and multi-pin selection
Cluster click (approved): Immediately open the right panel as a sortable/filterable issue list showing all issues in the clicked cluster. Include a prominent Zoom in action in that panel; do not automatically zoom on click. A cluster is a visual grouping at the current zoom, not necessarily one incident.
Multi-pin select (approved): Shift+click adds/removes individual pins; an explicit Box select toolbar mode enables click-and-drag rectangular selection. Normal dragging outside Box select always pans. Shift+click works without entering Box select. Optionally draw a lasso/polygon later (stretch). Clearly display N selected, allow clear selection and add/remove without closing panel.
Selection panel: Show issue rows (type, location, severity, date, verification) and summary by type/status; open an individual row in-place, then back to selection.
Actions: Save selected issues as a collection; export selection where permitted; narrow by filters. Do not conflate selecting 12 map pins with deduplicating them into 12 unique incidents unless IDs confirm uniqueness.
Define predictable interactions: dragging normally pans; rectangular selection only occurs in explicit selection mode (or with a documented keyboard modifier).
2.5 Draggable street-level explorer (Pegman-like)
Approved interaction: Provide a draggable person icon (Pegman-style) on the map. When dragging, highlight roads/locations with available Mapillary street-level photo coverage; dropping on a supported position opens Street-level Explorer anchored at the nearest available photo location.
Browse available Mapillary street photos (not a promise of continuous 360° navigation); show image date, photographer/provider attribution where required, camera heading when available, controls for adjacent photo locations when coverage permits, and Return to map. Optionally show nearby civic issue overlays or linked issue evidence.
No-coverage handling: if no imagery exists near the drop point, show “No street-level imagery available here” with a suggestion to move to a covered segment.
Feasibility boundary: The Mapillary photo browsing experience is the approved design, but implementation is feasibility-gated on viewer integration, coverage, availability, and provider terms. No full-city coverage, continuous 360° movement, or Google Street View equivalence is promised. Do not scrape or rehost Google Street View imagery as model-training or reference data.
This viewer is distinct from the right issue-context panel and may use a dedicated overlay/modal or split-pane; dropping the person icon does not count as selecting an issue pin.
2.6 Upload new issue
The Upload new issue button opens a dedicated form/modal, separate from the selection-driven right panel, so users can report an issue from either Map Explorer or Data Explorer.
Allow users to upload one or more photos, choose an issue category, add a short description, and set a Toronto location using address search or a draggable map pin. Suggest a location from photo metadata when available, but require the user to confirm it; allow approximate locations and display uncertainty honestly.
Show photo previews with remove/replace controls, required-field guidance, supported file types and size limits, upload progress, and actionable validation or retry messages. Keep entered details when an upload fails.
Before submission, show a review step and remind users to avoid personal information or identifiable people. Process uploaded evidence through the existing privacy and verification pipeline before publishing it.
On successful submission, show a confirmation and issue reference with Pending review status. New submissions enter the volunteer verification queue; they appear in the shared map/table dataset once approved and subject to existing permissions and filters. Submission does not automatically create a Toronto 311 service request.
3. Data Explorer — separate primary page
A full-width, paginated/virtualized SQL-style issues table, not raw access to the underlying SQL server. It consumes the same issue API as the map. Approved default: open with all issues across Toronto that the current user is authorized to access, subject to the same global filters used in Map Explorer. It does not default to the current map viewport or selected pins. A user-invoked View as table action can explicitly scope the table to a selected cluster or set of pins; display an obvious scope chip and Clear scope to return to all accessible Toronto issues.
Columns (user can reorder/show/hide later): issue ID, type, description, latitude/longitude only when permitted, area/ward, location confidence, nearby infrastructure category and asset name, severity, detected date, age, last seen, verification status, resolution status, sightings count, source category, cluster/incident ID, and AI confidence. Use separate identifiers for visual map cluster vs deduplicated incident; ephemeral zoom-dependent cluster IDs must not be exported as stable data.
Table interactions:
Keyword search; combine filters by neighbourhood/ward, drawn area, distance from infrastructure, issue type, infrastructure type, age/date range, severity, confidence, status, sightings count, and incident grouping.
Sort any supported column, select visible rows or filtered results, apply bulk actions within role permissions, and expand a row to inspect more detail.
Group by neighbourhood, infrastructure, issue category, status, or deduplicated incident; show counts. “Group by” is a table aggregation, not marker clustering on the map.
View on map moves selected records to Map Explorer and highlights them. View as table from a cluster or multi-pin selection opens a table scoped to that selection. Cross-page navigation preserves global filters; page-specific scopes are visible and independently removable.
Export filtered results, currently selected rows, or (for authorized users) a larger accessible dataset as CSV. Also support GeoJSON for GIS use; JSON is optional. Export must include units, an ISO timestamp convention, filters applied, provenance/source information, and appropriate coordinate precision. Large exports may require limits/pagination or a backend job.
Privacy and role authorization apply to backend queries and export files, not just on-screen columns. Published data is not assumed to prove whether a 311 issue was reported or resolved.
4. Search and infrastructure overlays
Unified search accepts Toronto addresses, intersections, neighbourhoods, wards, postal codes, landmarks, issues, and infrastructure names.
Infrastructure layer toggles: TTC subway/streetcar/stops, schools/universities, hospitals, government buildings, roads/highways, bridges, parks, bike lanes, public facilities, and other available licensed datasets.
Search for issues within a specified distance of a point asset (e.g., 500m of a TTC station), line asset (e.g., within 100m of Highway 401), or polygon asset (e.g., within/around school grounds).
Radius presets 250m / 500m / 1km / 2km; add a custom radius later.
Search/filter by issue category, detection age, confidence, severity, verification, location, source and proximity to selected infrastructure.
The sidebar and search filters stay synchronized between map and table; clearly expose active filters and a Reset option.
5. Saved, recents, labels, custom areas
Save individual issues, collections of issues, addresses, infrastructure places, camera/map views, and full queries (location + date/type/status filters + layers).
Recents record recently viewed entities, searches and areas only with appropriate consent/preferences; allow clear history.
Users can label/tag issues, places and drawn geographic areas, with personal notes and editable colours.
Draw radius circles, rectangles, and (stretch) polygons for named custom areas; query or save issues inside them.
Persist basic saved views locally for the demo; authenticated, cross-device saves and sharing are future work.
6. AI, verification, and interpretation
Detection pipeline identifies candidate issues in suitable public imagery, applies a privacy gate, estimates severity and location, and links repeat sightings.
Geolocation confidence is displayed honestly as a radius or coarse area; uncertain results go to a volunteer verification queue instead of an unjustifiably precise public pin.
Volunteers can inspect evidence, confirm/dismiss the issue, and drag/reposition a proposed pin, creating an audit trail.
Generate grounded neighbourhood/ward summaries and explain issue patterns based on retrieved records; clearly distinguish observed counts from inference.
Enrich with Toronto civic datasets including ward boundaries, TTC infrastructure, relevant 311 aggregates, road restrictions and suitable asset inventories when available.
7. Data model and interaction contracts
Issue: issue_id, incident_id (if deduplicated), geometry, location_radius_m, neighbourhood_id, ward_id, issue_type, infrastructure_type, asset_id, severity, detection_confidence, geo_confidence, first_seen_at, last_seen_at, verification_status, resolution_status, sightings_count, evidence_thumbnail, source_category, explanation.
User objects: saved_items, saved_queries, recent_activity, collections, annotations, custom_areas, verification_labels and role (with permission enforcement).
Map/UI state: viewport, zoom, layers, shared filter expression, selection IDs, selected visual cluster IDs, selection mode (pan | box), panel mode (closed | issue | cluster | multi), and data-table scope (all_accessible_toronto | selected_issue_ids). Keep issue ID-based selections stable across zoom changes; visual cluster membership may change with zoom.
Spatial queries: PostGIS geometry for points/lines/polygons; indexed distance and containment checks; deduplication/incident grouping happens separately from visual marker clustering.
8. MVP order for 3 people / 36 hours
P0 — cohesive live demo: persistent left sidebar/account type; Upload new issue button and photo/category/description/location submission form with confirmation and pending-review handling; 2D MapLibre map with panning, marker clusters, and search; selection-driven right panel; cluster click → right-side issue list + optional Zoom in; multi-pin selection via Shift+click and explicit Box select mode; Data Explorer opening on all accessible Toronto issues with shared filters; sortable/filterable table; CSV export; a handful of real Toronto infrastructure layers with nearby-issue distance queries. Same filters/data for both views.
P1 — if core works: saved searches and issues; recents; labelled custom areas (rectangle/circle); cross-navigation between table and map; volunteer verification and corrected pin; GeoJSON export; AI area digest.
P2 — stretch / feasibility-gated: approved Pegman-style draggable person for browsing available Mapillary street photos; polygon lasso; advanced grouping and bulk workflows; configurable columns; heatmap/timeline; shared collections and alerting. Street-level imagery should only be advertised as fully interactive after coverage and viewer feasibility are verified.
Live demo flow
Open Map Explorer → zoom into Toronto → click a cluster (right-side list opens, without auto-zoom) → optionally click Zoom in → filter cluster rows → select one issue → inspect right-side details → return → Shift+click several pins and use explicit Box select → View as table (scope chip: selected issues) → clear selection scope to see all accessible Toronto issues while preserving shared filters → filter by TTC station within 500m and last 7 days → export CSV → jump back to highlighted pins on the map. If coverage/viewer tests pass, drag the street-level person icon onto a Mapillary-covered road and browse nearby photos.
9. Approved decisions and remaining open questions
Locked product decisions (2026-10-17)
Click cluster: open right-side issue list with a Zoom in button; do not auto-zoom.
Multi-pin selection: Shift+click, plus explicit Box select mode; default drag pans.
Street-level exploration: draggable person icon dropped onto available Mapillary street photos, with photo-to-photo browsing and honest no-coverage behavior; delivery remains dependent on a successful integration spike.
Data Explorer initial scope: all accessible Toronto issues, using shared global filters; selection-scoped table is an explicit action only.
Unresolved details (recommended defaults for hackathon)
Exports: guest users export only public/coarsened fields; authorized staff may export more precise approved data, enforced server-side.
Saves: store locally for the MVP; link to an account when authentication exists.
Demo evidence: seed examples only when clearly labeled as such; do not present seeded records as genuinely scraped issues.
Infrastructure MVP: implement TTC stations, schools and road segments first.
Selecting a different marker with panel open: replace panel context without opening a second panel; closing or empty-map click clears active panel selection.
Filters: keep filters global across pages, but treat map-viewport and explicit selection-scope constraints as opt-in, page-specific filters.
10. Acceptance criteria for approved interactions
Scenario
Expected result
Click Upload new issue from either explorer
Dedicated submission form opens without changing the issue-context panel.
Submit a valid new issue with a photo and confirmed location
Show confirmation and issue reference; queue as Pending review and publish only after privacy processing and verification.
Upload fails or required fields are missing
Show actionable feedback, preserve entered details, and allow correction or retry.
Open Map Explorer
Full-width map; right panel closed.
Click one pin
Right-side details open.
Click a numbered cluster
Right-side sortable/filterable list opens; viewport does not zoom; Zoom in action available.
Click issue row in cluster list
Same right panel displays issue detail and Back to results.
Shift+click 3 pins
All 3 issue IDs selected; right-side multi-selection list opens; no duplicate IDs.
Activate Box select, then drag
Draw selection rectangle and select intersecting pins; dragging in regular mode pans.
Click empty map / Escape
Close right panel and clear current selection according to documented behavior.
Drop person on Mapillary-covered road
Open photo explorer at a covered photo location, with navigation/date/attribution.
Drop person outside imagery coverage
Show clear no-coverage feedback; no fabricated Street View.
Open Data Explorer from sidebar
Table defaults to all authorized Toronto issues under shared filters, independent of map viewport.
Use View as table on selected pins
Table opens with selected-ID scope and a visible Clear scope control.
Export filtered table
CSV rows/columns reflect applied permissions, filters and selected scope; no private coordinates are leaked.
Navigate between map and table
Shared filters persist; explicit map selection scope remains visible when carried over.



