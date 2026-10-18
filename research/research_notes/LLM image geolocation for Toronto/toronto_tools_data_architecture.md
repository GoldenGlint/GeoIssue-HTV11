# Tools, data sources and architecture patterns for a hybrid LLM-plus-tools geolocator restricted to the City of Toronto

Scope note: the user asked that the team's draft cascade (L0/L1 metadata, L2 clues, L3 MegaLoc over Mapillary, L4 LightGlue, LightGBM fusion and conformal radius) be treated as an unverified hypothesis, not a baseline. The architecture section below reasons from first principles and says where the draft looks right or wrong. Research date: 2026-10-17. Several API probes were run live against the Toronto CKAN API, Panoramax, Wikimedia Commons and Bike Share GBFS on that date. Their outputs are quoted as "live probe" with the endpoint URL as the source.

**Requirement changes received mid-task, now reflected in these notes:**
- **Target precision is now ≤10 m, not 25–100 m.** Q1–Q6 were drafted for 25–100 m. Q8 re-weights the catalogue for metre-level precision: reference-position accuracy, LiDAR, orthos and massing, and point assets with IDs. It also lists which tools can only narrow the region at 10 m. Q5 has a "≤10 m update" block.
- **Street-view comparison is now a core step, and Google Street View needs a precise check.** See **Q7 (priority)**. Pose-estimation methods are covered by another researcher. These notes cover data, tools and architecture only.

## Q1. Street-level imagery for a reference index (Mapillary, KartaView, Panoramax, City of Toronto, Google Street View)

### Takeaway
Mapillary is the only practical, legally usable, API-accessible street-level source for building a Toronto image index. Panoramax has a small CC BY-SA set from a handful of contributors (about 32k images found in the Toronto bbox). KartaView's API timed out on Toronto queries. The City publishes 8 cm orthophotos, not street-level imagery. Google Street View's Terms of Service explicitly forbid indexing, pre-fetching, building ML test or validation sets, and showing Street View on the same screen as a non-Google map. At most it can serve a human moderator through a Google-hosted view. **Q7 analyses GSV in detail, including on-the-fly fetching for comparison.**

### Cited Findings
**Mapillary API v4 (graph.mapillary.com)**
- Rate limits: entity API 60,000 requests/min per app. Search API (e.g. `images?bbox=`) 10,000/min per app. Vector tiles (tiles.mapillary.com) 50,000/day (per day, not per minute). Overages give "Application request limit reached" (Graph) or a 4xx (tiles). — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- Image fields include `thumb_256_url`, `thumb_512_url`, `thumb_1024_url`, `thumb_2048_url`, `thumb_original_url`, `is_pano`, `camera_type` (perspective / fisheye / equirectangular-spherical), `computed_compass_angle`, `computed_geometry` (GeoJSON point after SfM), `sfm_cluster` (zlib-compressed JSON point cloud) and `mesh`. — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- Spatial query limits: for images, map_features and detections, the bbox "must be smaller than 0.01 degrees square", a limit formalized on 16 Jan 2026. `limit` defaults to and maxes at 2000. A radius search (lat/lng, radius default and max 50 m, limit max 100) exists but cannot be combined with bbox, tile, s2 or ids. For large areas the docs point to mapillary-python-sdk. — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- Map features and detections: `object_value` (e.g. `object--support--utility-pole`), `object_type` = `traffic_sign` or `point`, and `object_values` filters with wildcards. Point and traffic-sign vector-tile layers exist at zoom 14 only. Per-image detections come from `/:image_id/detections` (base64 polygon geometry plus value). — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- Coverage vector tiles: `mly1_public` and `mly1_computed_public` (map-matched), z0–14. The image layer is at z14 (points), the sequence layer at z6–14, the overview layer at z0–5. — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- The API page does not say how long thumbnail URLs stay valid and does not state licence terms. It shows "© Mapillary" attribution and links to the ToS. — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- Licence: Mapillary imagery is published under CC BY-SA 4.0 (changed from CC BY-NC on 29 April 2014). The help centre describes attribution requirements. — [Mapillary help: CC BY-SA license](https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data); [Wikipedia: Mapillary](https://en.wikipedia.org/wiki/Mapillary). A Mapillary forum thread argues Mapillary's own terms add restrictions in tension with CC terms (not resolved). — [Mapillary forum](https://forum.mapillary.com/t/licensing-issues-for-using-mapillary-images-on-wikimedia-commons/3821)
- Toronto coverage: no public statistic found. An OSM Canada thread says Montréal uploaded more than 1M high-resolution 360° images (3,000 km of road) to Mapillary, and that a contributor had no luck connecting with the City of Toronto. So Toronto coverage appears to be community-contributed only. — [OSM community: Montreal 360 imagery](https://community.openstreetmap.org/t/high-resolution-360-imagery-in-montreal/120447)
- Mapillary blurs faces and licence plates automatically. — [Mapillary.com](https://www.mapillary.com/)

**Panoramax**
- A live probe of `https://api.panoramax.xyz/api/collections?bbox=-79.64,43.58,-79.11,43.86&limit=100` returned 100 collections (the first page) totalling about 31,900 items. All were licensed `CC-BY-SA-4.0` and almost all came from one provider ("Coehill"), captured in 2023–2024. Two `mapcomplete` collections (16,867 and 3,584 items) may extend beyond Toronto. `api/search` returned image points in Toronto, e.g. at (-79.3599, 43.7147) dated 2025-08-23. — [Panoramax API live probe](https://api.panoramax.xyz/api/collections?bbox=-79.64,43.58,-79.11,43.86&limit=100)
- Panoramax is federated FOSS. Its GeoVisio backend (MIT) exposes a search and upload API. The network had about 105M images as of May 2026. — [Wikipedia: Panoramax](https://en.wikipedia.org/wiki/Panoramax); [OSM wiki: Panoramax](https://wiki.openstreetmap.org/wiki/Panoramax)

**KartaView**
- A live probe of `https://api.openstreetcam.org/2.0/photo/?lat=43.6532&lng=-79.3832&radius=300` returned `apiCode 408 "Query timeout. Narrow your filter..."` on two attempts (2,000 m and 300 m radii). Coverage and usability for Toronto are unverified. — [KartaView API live probe](https://api.openstreetcam.org/2.0/photo/?lat=43.6532&lng=-79.3832&radius=300&itemsPerPage=20)

**City of Toronto imagery**
- The City publishes OGC WMTS/ArcGIS MapServer orthorectified aerial imagery: a "most current year" service plus colour 8 cm years 2015–2022 (e.g. `https://gis.toronto.ca/arcgis/rest/services/basemap/cot_ortho/MapServer`), as well as historic black-and-white aerials. All are in Web Mercator. — [Toronto Open Data "Web Map Services" via CKAN](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=orthoimagery)
- No City street-level imagery dataset turned up in the CKAN searches run. — [CKAN package_search](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture)

**Google Street View (Maps Platform ToS, last modified 26 Aug 2026)**
- §3.2.3(a) No Scraping: Customer will not "pre-fetch, index, store, reshare, or rehost Google Maps Content outside the services" or "bulk download ... Street View images". — [Google Maps Platform ToS](https://cloud.google.com/maps-platform/terms)
- §3.2.3(c) No Creating Content From Google Maps Content: examples include "(v) construct an index of tree locations within a city from Street View imagery" and "(vii) use Google Maps Content to improve machine learning and artificial intelligence models, including to train, test, validate or fine-tune the models." — [Google Maps Platform ToS](https://cloud.google.com/maps-platform/terms)
- §3.2.3(e) No Use With Non-Google Maps: Customer will not "(ii) display Street View imagery and non-Google Maps on the same screen, or (iii) link a Google Map to non-Google Maps Content or a non-Google Map." — [Google Maps Platform ToS](https://cloud.google.com/maps-platform/terms)
- The Service Specific Terms permit caching only Street View Static API `pano_id` values. — [GMP Service Specific Terms (archived versions)](https://cloud.google.com/maps-platform/terms/maps-service-terms/index-20240522)
- A Google Street View MCP server exists (fetches imagery by address, coordinates or pano ID and saves to local files). Saving to local files would conflict with the no-caching and no-storing clauses above. — [Glama: google street view MCP](https://glama.ai/mcp/servers/integrations/google-street-view)

### Inferences
- **GSV cannot be the index.** Building a VPR index, computing embeddings, storing thumbnails, or even using GSV images to test or validate the model (§3.2.3(c)(vii)) is prohibited. That rules out a GSV-based evaluation set too.
- **GSV for human verification only, under conditions.** A moderator could open the predicted coordinate in Google's own UI (a Maps URL link-out or the Maps Embed/JS Street View in a separate view). The GeoIssue moderator screen must not show Street View next to a Leaflet/OSM/MapLibre map (§3.2.3(e)). Sending Street View frames to Claude or Gemini as "candidate images" would likely count as using Maps Content outside the Services, so avoid it. This is legal interpretation, not legal advice. Flag it to the team.
- **Enumerating Toronto Mapillary coverage cheaply.** The Toronto bbox (about -79.64..-79.11, 43.58..43.86) spans about 25 × 18 = 450 z14 tiles (my own slippy-map calculation). One pass over the `mly1_computed_public` image layer is well under the 50,000 tiles/day limit. It yields image ids, captured_at, compass angle and is_pano without touching the 0.01-degree bbox limit on the search API.
- **Storage budget on 15 GB free disk.** 1024-px JPEG thumbnails are typically 150–300 KB (my estimate, not measured). That puts 50k images at roughly 7–15 GB, so it is tight. Prefer storing only descriptors plus re-fetching `thumb_1024_url` on demand for the top-K. MegaLoc's 8,448-d descriptor in float16 is about 16.9 KB per image, so 100k images is about 1.7 GB. PCA or PQ to 512–1024 dims reduces that 8–16x.
- **Mapillary's precomputed map features are a free Toronto-wide street-furniture layer** (traffic signs, poles, hydrants and so on, at z14). They complement City open data. Treat object positions as approximate (SfM-triangulated).
- **Panoramax is a minor supplement** (same CC BY-SA licence, same ShareAlike obligations). KartaView is not worth hackathon time unless a quick tile probe shows Toronto coverage.

### Gaps
- No primary source gives Mapillary image counts, recency or pano share for Toronto. The team should measure with the 450 coverage tiles (needs their token).
- Current Mapillary ToS wording on downloading and derivative use (e.g. storing descriptors) was not verified. Whether thumbnail URLs expire was not stated in the docs.
- Whether the "0.01 degrees square" bbox limit means 0.01 deg² of area or 0.01° per side is ambiguous in the docs.
- The KartaView Toronto coverage check failed (timeouts).

## Q2. Toronto identification data (City open data, TTC GTFS, Bike Share GBFS, Overture, OSM/Overpass, Wikidata/Commons)

### Takeaway
Toronto has unusually rich, daily-refreshed, open gazetteer and asset data: Centreline, Intersections, 500k+ Address Points, transit shelters, benches, bins, poster boards, signals, building outlines, 3D massing, 8 cm orthos, GTFS and a 1,072-station GBFS feed. All are downloadable as GeoJSON, CSV, GPKG or SHP through the CKAN API, mostly under the Open Government Licence – Toronto. Combined with Overture places (CDLA-Permissive 2.0 / Apache / CC0 by source) and OSM (ODbL), they give deterministic "text → coordinate" and "feature combination → candidate set" tools. Mind the caveats: street-tree coordinates are snapped to parcels, Commons coordinates are often placeholders, and the public Overpass server has strict usage guidance.

### Cited Findings
**Access method for all City datasets.** CKAN API `https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=...` and `package_show`. Resources come as direct download URLs plus `datastore/dump/<id>` GeoJSON. Most are offered in EPSG:4326 and EPSG:2952 (or 2945). — [CKAN API live probe](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=centreline)

The table below comes from a live CKAN probe on 2026-10-17. "Licence" is the CKAN `license_title`. Many datasets show "License not specified" in metadata, but the portal-wide licence is the Open Government Licence – Toronto ([open.toronto.ca/open-data-license](https://open.toronto.ca/open-data-license/)). Verify per dataset.

| Dataset (CKAN id) | Content / notes | Formats | Refresh (last) | CKAN licence |
|---|---|---|---|---|
| `toronto-centreline-tcl` | Streets, walkways, rivers, rail, highways, admin boundaries, with names and address ranges | CSV, GeoJSON, GPKG, SHP | Daily (2026-10-16) | None listed |
| `intersection-file-city-of-toronto` | All intersections, to be overlaid on Centreline | CSV, GeoJSON, GPKG, SHP | Daily (2026-10-08) | Not specified |
| `address-points-municipal-toronto-one-address-repository` | "over 500,000 addresses", positioned on the correct side of the street within the parcel or building footprint | CSV, GeoJSON, GPKG, SHP | Daily (2026-10-16) | Not specified |
| `street-furniture-transit-shelter` | Astral Out-of-Home contract (2007, 20 years), up to 25,000 elements incl. up to 6,000 shelters | CSV, GeoJSON, GPKG, SHP | Semi-annual (2026-02-20) | OGL-Toronto |
| `street-furniture-bench`, `-litter-receptacle`, `-poster-board`, `-poster-structure`, `-publication-structure` | Street furniture points | CSV, GeoJSON, GPKG, SHP | Semi-annual (2026) | OGL-Toronto |
| `traffic-signals-tabular` | Signals, pedestrian crossovers, beacons, with attributes (audible, countdown, priority) | CSV, GeoJSON, GPKG, SHP, XLSX | As available (2026-10-17) | None listed |
| `traffic-control-devices` | Upcoming or recent signals, PXOs, beacons | CSV, GeoJSON, GPKG, SHP | (2026-02-20) | None listed |
| `red-light-cameras` | Camera locations | CSV, GeoJSON, GPKG, SHP | Daily | OGL-Toronto |
| `street-tree-data` | City-owned trees. **"The positioning shown is not accurate as the tree data has been geographically coded to the parcel address"** | CSV, GeoJSON, GPKG, SHP | As available (2026-06-04) | Not specified |
| `topographic-mapping-building-outlines` | Roof-extent polygons from high-resolution aerial photography; complex buildings as multiple roof-elevation polygons | CSV, GeoJSON, GPKG, SHP | Quarterly (2026-04-05) | Not specified |
| `3d-massing` | City Planning context massing (SHP and multipatch, yearly 2016–2019+, plus AutoCAD/SKP tile locator), "for information and illustrative purposes only" | SHP, PDF, web | Annual (2025-12-05) | Not specified |
| `web-map-services` | Orthophoto WMTS/MapServer, current year plus 2015–2022 at 8 cm, historic aerials | Web | — | OGL-Toronto |
| `ttc-routes-and-schedules` / `merged-gtfs-ttc-routes-and-schedules` | GTFS (routes, stop patterns, stop locations, schedules, all modes); "TTC provides updates approx. every 6 weeks" | ZIP | Monthly (2026-09-25) / Quarterly (2026-09-30) | Not specified |
| `ttc-gtfs-realtime-gtfs-rt` | GTFS-RT service disruptions | Web | Real-time | Not specified |
| `bike-share-toronto` | GBFS feed links (the CKAN text says 625 stations, which is stale; see below) | JSON | Real-time | Not specified |
| `cycling-network` | Bike lanes | CSV, GeoJSON, GPKG, SHP | Semi-annual (2026-09-14) | None |
| `311-service-requests-customer-initiated` | 311 requests (Solid Waste, Transportation, Toronto Water, MLS, Urban Forestry). Location recorded at first-3-character postal code (FSA) level | ZIP (yearly) | Monthly (2026-10-08) | Not specified |
| `311-open311-api-calls-for-service-requests` | Old Open311 API docs | DOC | "Will not be Refreshed" | None |

Sources for the table: [CKAN package_search: street furniture](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture), [centreline](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=centreline), [address points](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=address%20points), [3D massing](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=3D%20massing), [street tree](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20tree), [traffic signals](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20signals), [building outlines](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=building%20outlines), [TTC](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=TTC%20routes%20schedules), [bike share](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=bike%20share), [311/graffiti](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=graffiti), [orthoimagery](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=orthoimagery), [intersection](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=intersection)

**Bike Share GBFS (live)**
- Discovery URL `https://tor.publicbikesystem.net/customer/gbfs/v2/gbfs.json` (ttl 10 s) lists `station_information`, `station_status`, `geofencing_zones` and others under `toronto.publicbikesystem.net`. `station_information` returned **1,072 stations** on 2026-10-17, each with name (often an intersection, e.g. "Fort York Blvd / Capreol Ct"), lat/lon and address. — [Bike Share GBFS live probe](https://tor.publicbikesystem.net/customer/gbfs/v2/en/station_information)

**Overture Maps**
- Licences by theme: Places come from Meta, Microsoft, PinMeTo, Krick, RenderSEO, DAC and BrightQuery under **CDLA Permissive 2.0**, from Foursquare under **Apache 2.0**, and from AllThePlaces under **CC0 1.0**. **Buildings, Base, Divisions and Transportation are ODbL** (© OpenStreetMap contributors), with some CC BY 4.0 sources (Esri Community Maps, etc.). Addresses vary by source (e.g. PDDL, CC BY via OpenAddresses). — [Overture attribution](https://docs.overturemaps.org/attribution/)
- Access: the official `overturemaps` Python CLI downloads by `--bbox` and `--type` (`place`, `building`, ...) to GeoJSON or GeoParquet, reading only the bbox from cloud GeoParquet. DuckDB can query S3 GeoParquet directly (us-west-2), and each row has a `bbox` struct for efficient filtering. — [Overture docs: getting data](https://docs.overturemaps.org/getting-data); [Overture workshop](https://labs.overturemaps.org/workshop/2-accessing-data.html)
- Overture keeps public releases available for at most about 60 days (two monthly releases), so release paths in URLs go stale. — [GDAL GeoParquet tutorial](https://gdal.org/en/stable/tutorials/vector_geoparquet_tut.html)

**OSM via Overpass**
- Main public instance `https://overpass-api.de/api/interpreter` (FOSSGIS). Guidance: under 10,000 queries/day and under 1 GB/day is fine for one-off use, but "If you set something up that uses the Overpass API regularly, then divide those numbers by 100 (making less than 100 queries fetching less 10 MB of data per day fine)". App usage counts as the sum over all users. Requests must carry an identifying User-Agent, with no parallel scripts. "Commercial use should use self-hosted or paid" instances. — [OSM wiki: Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- Bellingcat OSM Search (`bellingcat/osm-search`, MIT): "A user friendly way to search OpenStreetMap data for features in proximity to each other". Self-hosted on PostgreSQL loaded with `osm2pgsql` from a PBF (the planet needs about 700 GB). Needs Firebase and Mapbox config for the hosted UI. It does not use Overpass. — [GitHub bellingcat/osm-search](https://github.com/bellingcat/osm-search)
- Its UI has a "Maximum distance between features" slider defaulting to 100 m. The workflow picks features seen in the photo (e.g. near a school, a supermarket and a sidewalked street) and lists locations where all co-occur. — [Bellingcat how-to (2023)](https://www.bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool/)

**Wikidata and Wikimedia Commons**
- Commons geosearch API: `https://commons.wikimedia.org/w/api.php?action=query&list=geosearch&gscoord=LAT|LON&gsradius=10000&gslimit=500&gsnamespace=6`. A live probe at Toronto City Hall hit the 500-result cap within 10 km. The nearest results sat at exactly 43.6532,-79.3832 (distance 0) with unrelated titles (e.g. "Fossilized Coral Structure.jpg"), meaning many files carry a generic "Toronto" placeholder coordinate. — [Commons API live probe](https://commons.wikimedia.org/w/api.php?action=query&list=geosearch&gscoord=43.6532|-79.3832&gsradius=10000&gslimit=500&gsnamespace=6&format=json)
- Wikidata structured data is CC0. — [Wikidata: Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)

### Inferences
- **Highest-value deterministic "text → coordinate" tools for Toronto:**
  1. Intersection resolver: Centreline street names plus the Intersection File, with fuzzy matching ("Dufferin & Bloor", "Yonge/Eg").
  2. Address resolver: Address Points (500k+, curb-side-correct, so about 10–30 m accuracy for a stated address).
  3. TTC resolver: GTFS stops (name and stop code; TTC pole signs show a stop number) and route shapes. Streetcar routes (GTFS `route_type=0`) limit the city to a few dozen corridors when overhead wires or tracks are visible.
  4. Bike Share station names (1,072, often intersection-named).
  5. Overture places for storefront names seen in OCR.

  The repo already has parquet anchors for streets, intersections, stops, routes, shelters and places under `spikes/data/anchors/`.
- **Asset co-occurrence search** (Bellingcat-style) for Toronto works better on City asset layers than on OSM tags alone. Shelters, benches, bins, poster boards, signals, PXOs and red-light cameras have near-complete City inventories, while OSM tagging of street furniture is uneven. Implement it locally as a DuckDB-spatial or GeoPandas STRtree query over City, OSM and Overture layers clipped to Toronto (all fit in RAM), not via public Overpass. A production GeoIssue would exceed the "<100 queries/day for regular use" guidance.
- **Do not use street trees for fine localisation** (parcel-snapped coordinates). Building outlines and 3D massing are usable for skyline or occlusion reasoning but are expensive to exploit.
- **The 311 data is a weak prior only** (FSA-level). It can tell which neighbourhoods generate many graffiti or pothole requests, not where a given photo is.
- **Commons and Wikidata matter mainly for landmarks** (churches, murals, named buildings). Filter out Commons files at the exact city-centroid coordinate, and respect per-file licences (mostly CC BY-SA or CC BY; I did not verify per-file mixes).
- **GBFS is live data.** Cache a snapshot of station_information. Station locations change rarely.

### Gaps
- The Open Government Licence – Toronto page is JS-rendered and could not be scraped this session. Licence fields for many datasets are blank in CKAN metadata, so confirm attribution wording ("Contains information licensed under the Open Government Licence – Toronto" is the commonly used form, but I did not verify it here).
- No City or TTC open dataset of **elevator locations or elevator outage status** was found in CKAN. TTC elevator alerts may appear in the GTFS-RT service-disruptions feed or on ttc.ca. Unverified.
- Whether TTC GTFS `stops.txt` `stop_code` matches the number printed on TTC stop poles was not verified this session.
- OSM extract sizes and sources for Toronto (Geofabrik Ontario, BBBike) were not checked.

## Q3. Tool types that measurably boost geolocation

### Takeaway
For civic-issue photos in a single city, the biggest wins are text-driven: OCR (street signs, storefronts, TTC station walls, stop numbers) plus fuzzy gazetteer resolution against City data, which gives 10–50 m when it fires. Second is VPR retrieval over a Toronto Mapillary gallery, verified with local feature matching (LightGlue inlier counts). Third are feature-combination searches over City, OSM and Overture layers. Sun and shadow analysis and skyline matching are niche verifiers. Reverse image search has only one clean, official API route: Google Cloud Vision Web Detection (plus Landmark Detection). Bing's APIs are gone, and Lens has no official API.

### Cited Findings
**OCR and document VLMs**
- PaddleOCR 3.x PP-OCRv5: server recognition model 81 MB, mobile recognition model 16 MB. A single model covers Simplified/Traditional Chinese, English and Japanese, plus "complex text scenarios such as handwriting, vertical text". — [PaddleOCR model list v3.3.x](https://www.paddleocr.ai/v3.3.2/version3.x/model_list.html); [InfoQ on PP-OCRv5](https://www.infoq.com/news/2025/09/baidu-pp-ocrv5)
- On OmniDocBench v1.6 (documents, not street scenes), small dedicated models (PaddleOCR-VL-1.6, MinerU2.5-Pro, GLM-OCR, about 0.9–1.2B) outscore Qwen3-VL-235B (89.78%), per an August 2026 Roboflow article. — [Roboflow: best open-source OCR models](https://blog.roboflow.com/best-open-source-ocr-models/)
- Qwen3.5-9B reports OCRBench 89.2, CC-OCR 79.3 and OmniDocBench1.5 87.7, so a general VLM is now a strong scene-text reader. — [HF: Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)

**Logo, landmark and reverse image search (official APIs)**
- Google Cloud Vision pricing (first 1,000 units/month free per feature, then per 1,000 units): Text Detection $1.50, Landmark Detection $1.50, Logo Detection $1.50, Web Detection $3.50, Label Detection $1.50, Object Localization $2.25 (lower tiers above 5M units). — [Cloud Vision pricing](https://cloud.google.com/vision/pricing)
- Bing Search APIs, including image and visual search, were retired on 11 Aug 2025 and existing resources decommissioned. Microsoft points users to "Grounding with Bing Search" in Azure AI Foundry, which returns LLM-grounded chunks, not raw results. — [The Register](https://www.theregister.com/2025/05/15/bing_search_apis_retired/); [dev.to summary](https://dev.to/tonywangca/best-bing-search-api-alternatives-in-2026-after-the-retirement-kdi)
- Google Lens has no official API. Third-party scrapers exist (e.g. an Apify actor at $0.0015 per image search with matches, plus $0.002 per run). — [Apify Google Lens actor pricing](https://apify.com/s-r/google-lens/pricing)
- TinEye API is sold in bundles: 5,000 searches for USD 200 ($0.04 each) down to 1M searches for USD 10,000 ($0.01 each). The post is undated, so the rates may be stale. — [TinEye blog: new image search pricing](https://blog.tineye.com/new-image-search-pricing/)

**VPR retrieval and verification**
- MegaLoc: retrieval model "SOTA on most VPR datasets", indoor and outdoor. It produces an L2-normalised 8,448-d descriptor, loads via `torch.hub.load("gmberton/MegaLoc", "get_trained_model")`, takes 322×322 ImageNet-normalised input, and is MIT licensed (arXiv 2502.17237, CVPRW 2025). — [GitHub gmberton/MegaLoc](https://github.com/gmberton/MegaLoc)
- LightGlue (code and weights Apache-2.0) supports SuperPoint, DISK, ALIKED and SIFT. "SuperPoint follows a different, restrictive license". ALIKED is BSD-3-Clause and DISK Apache-2.0. Speed on an RTX 3080 with compile and adaptivity: 150 FPS at 1,024 keypoints, 50 FPS at 4,096. Knobs: `depth_confidence` (early stop, default 0.95), `width_confidence` (pruning, 0.99), `filter_threshold` (0.1), `flash=True`. — [GitHub cvg/LightGlue](https://github.com/cvg/LightGlue)

**Sun and shadow**
- Bellingcat documents using SunCalc to chronolocate from shadow length and to establish camera direction. Their 2024 Shadow Finder tool searches globally for locations matching a shadow measurement and date/time. Shadow analysis needs daytime images with visible shadows. — [Bellingcat 2020: sun and shadows for geolocation](https://www.bellingcat.com/resources/2020/12/03/using-the-sun-and-the-shadows-for-geolocation/); [Bellingcat 2021: shadow length](https://www.bellingcat.com/resources/2021/05/18/unsure-when-a-video-or-photo-was-taken-how-to-tell-by-measuring-the-length-of-shadows/); [Bellingcat 2024: Shadow Finder](https://bellingcat.com/resources/2024/08/22/shadow-geolocate-geolocation-locate-image-tool-open-source-bellingcat-measure)

**Feature-combination search**
- Bellingcat OSM Search proximity search with a default 100 m maximum feature distance (see Q2). — [Bellingcat how-to](https://www.bellingcat.com/resources/how-tos/2023/05/08/finding-geolocation-leads-with-bellingcats-openstreetmap-search-tool/)

**Segmentation and detections**
- Mapillary already serves per-image detections and triangulated map features (traffic signs and point objects such as utility poles) through its API (see Q1). — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)

### Inferences
Ranked catalogue of tools for the orchestrator, by expected value for GeoIssue. Expected values are my judgement, not measured.

| # | Tool (callable function) | Backing data / model | When it fires | Typical precision when it fires | Cost / latency (est.) |
|---|---|---|---|---|---|
| 1 | `parse_post_text(text, alt_text, hashtags)` → streets, intersections, addresses, landmarks, TTC lines/stations | LLM structured output + regex | Most posts. Civic complainers often name the street | 25–100 m if intersection or address | 1 cheap LLM call |
| 2 | `ocr(image)` → text boxes | LLM itself (Claude/Gemini/Qwen3.5) or PP-OCRv5 locally | Signs, storefronts, station walls, shelter ads, stop poles | — | PP-OCRv5 under 0.3 s on GPU (est.); LLM included in the clue call |
| 3 | `resolve_place(strings[])` → ranked candidates with coordinates | rapidfuzz over Centreline names, Intersection File, Address Points, GTFS stops, GBFS, Overture places, Wikidata | Whenever 1 or 2 yields named entities | 10–50 m (address / intersection / stop) | ms, local |
| 4 | `feature_search(constraints, region)` (Bellingcat-style) | DuckDB-spatial / STRtree over City assets, OSM extract, Overture, GTFS shapes (streetcar corridors) | Distinctive combos (streetcar wires + shelter + PXO) | Narrows to N candidate sites. Rarely unique alone | ms–s, local |
| 5 | `vpr_search(image, prior_region)` → top-K Mapillary images | MegaLoc + FAISS over Toronto Mapillary gallery | Street-scene photos with facades or road geometry | 10–50 m if correct. Fails on close-ups, night, floods, indoor | ~20 ms embed + about 0.1–0.3 s flat search over 100–200k (est.) |
| 6 | `verify_match(image, cand_ids)` → inliers per candidate | ALIKED/DISK + LightGlue (avoid SuperPoint if a commercial future matters) + RANSAC | After 5, or to check text-derived candidates against nearby Mapillary images (radius search ≤50 m) | Strong same-place evidence. Also yields heading | about 10–40 ms per pair on a 4060 laptop (est. from 3080 figures) + thumbnail download |
| 7 | `mapillary_nearby(lat, lon, r≤50m)` | Mapillary radius search | Verify text-only candidates visually | — | 1 API call |
| 8 | `reverse_image(image)` | Cloud Vision Web Detection ($3.50/1k) / Landmark ($1.50/1k), TinEye API | Re-posted news photos, landmarks; detecting recycled or old images | Variable. Landmark gives lat/lng for famous sites only | ~0.5–2 s, $0.0015–0.04 |
| 9 | `sun_check(timestamp, candidate, heading)` | pvlib/astral sun azimuth vs shadow direction | Daytime, visible shadows, trustworthy post time | Constrains heading (±20–30°). Rarely position | ms |
| 10 | `ortho_patch(lat, lon)` | City 8 cm ortho WMTS | LLM checks crosswalk, lane or median layout at a candidate | Verifier only | ~0.5 s |
| 11 | Skyline/massing render | 3D Massing | Long views with towers (CN Tower) | Heading and position from the skyline | High dev effort. Skip for a hackathon |

- **OCR choice.** For a hackathon, let the VLM do OCR inside the single clue-extraction call (Claude/Gemini read signs well, and Qwen3.5-9B scores OCRBench 89.2). Add PP-OCRv5 only as a local fallback or to get box coordinates. Florence-2 and docTR are older options I did not verify this session.
- **Segmentation for road furniture.** Do not run Mask2Former/Mapillary-Vistas segmentation on the gallery. Mapillary's own detections and map features already cover the gallery side. For the query side, the VLM's structured description ("bus shelter, Astral ad panel, streetcar wires, PXO sign") is enough to drive `feature_search`.
- **Reverse image search is mostly for provenance and dedup** (is this an old photo or a news photo?), not primary geolocation for user-shot pothole photos. Scraping Lens or Yandex violates their ToS and is brittle. Cloud Vision Web Detection is the clean option.
- **Indoor TTC elevator photos** cannot be matched against Mapillary (little indoor coverage, my inference). Treat them as station identification: OCR station name or wall-tile text, then GTFS station, then about 100–200 m precision (station footprint). OSM `highway=elevator` and subway entrance nodes may refine to the specific elevator.

### Gaps
- I found no published measurements of how much each tool lifts accuracy on Toronto or civic-issue images. All lift estimates above are judgement. The team should measure on a labelled sample.
- RoMa (dense matcher) licence and speed were not verified this session. It is generally heavier than LightGlue.
- I found no information on a Yandex reverse-image API.
- Florence-2 and docTR scene-text accuracy were not re-verified.

## Q4. Existing MCP servers and tool wrappers for geospatial work

### Takeaway
Several open-source OSM MCP servers wrap Nominatim and Overpass and could be plugged into Claude directly. cyanheads/openstreetmap-mcp-server is the most production-minded, with built-in rate pacing. No Mapillary MCP server was found, and the Street View MCP is ToS-problematic. For a latency- and cost-sensitive pipeline, plain Python functions exposed as Claude/Gemini tool definitions over local Toronto data beat remote MCP calls to public OSM services. MCP is mainly a convenience for interactive debugging in Claude Code.

### Cited Findings
- **cyanheads/openstreetmap-mcp-server** (Apache-2.0, v0.6.1, stdio and Streamable HTTP, hosted at `https://openstreetmap.caseyjhand.com/mcp`). Tools: `openstreetmap_search_places`, `openstreetmap_reverse_geocode`, `openstreetmap_lookup_objects`, `openstreetmap_query_nearby` (radius plus tags), `openstreetmap_query_bbox`, `openstreetmap_query_raw` (Overpass QL). Spaces Nominatim calls 1,050 ms apart (1 req/s policy). Overpass concurrency defaults to 1, with failover endpoints and backoff to 10 min. Caches Nominatim 60 s and Overpass 10 min. Overpass results capped at 64 MiB. — [GitHub cyanheads/openstreetmap-mcp-server](https://github.com/cyanheads/openstreetmap-mcp-server)
- **GRABOSM/osm-mcp** (Node.js): about 30 tools (geocoding, routing, QA, analysis), with configurable Overpass endpoints tried in order on 429/5xx. — [Glama: GRABOSM/osm-mcp](https://glama.ai/mcp/servers/GRABOSM/osm-mcp/inspect); [socket.dev: osm-mcp](https://socket.dev/npm/package/osm-mcp)
- **Rusty0508/overpass-mcp** (Python, stdio, no keys): Nominatim geocoding, tagged-element search near a point or in an area, raw Overpass QL. GitHub URL not confirmed. — [Glama: overpass-mcp](https://glama.ai/mcp/servers/Rusty0508/overpass-mcp)
- **Pipeworx mcp-overpass**: hosted HTTP gateway for Overpass. — [getdrio listing](https://www.getdrio.com/mcp/io-github-pipeworx-io-overpass)
- **Google Street View MCP**: fetches and saves Street View images (ToS conflict, see Q1). — [Glama: google street view](https://glama.ai/mcp/servers/integrations/google-street-view)
- **No Mapillary MCP server** turned up in searches. — [search: "Mapillary MCP server"](https://www.mapillary.com/platform) (negative result)
- **Built-in provider tools.** Claude web search costs $10 per 1,000 searches plus tokens. Claude web fetch has no extra charge beyond tokens. — [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing). Gemini "Grounding with Google Maps" (Gemini 3+) gives 5,000 requests/month free (shared), then $14 per 1,000. "Grounding with Google Search" has the same 5,000/month free, then $14 per 1,000. — [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

### Inferences
- Use the OSM MCP servers for exploration and debugging in Claude Code, not in the per-image hot path. Public Nominatim (1 req/s) and Overpass (<100 queries/day for regular use) cannot sustain a feed of social posts.
- Write a small in-process "Toronto tool server" (Python functions: `resolve_place`, `feature_search`, `vpr_search`, `verify_match`, `mapillary_nearby`, `ortho_patch`) with JSON-schema tool definitions usable by both Claude tool use and Gemini function calling. Optionally expose the same functions as a local MCP server (stdio) so Claude Code can call them while developing.
- Gemini's Maps grounding is an interesting "Google-sanctioned" place-lookup tool. Google Maps ToS restrictions on storing results still apply (my inference: grounded output is Maps Content), so use it for transient lookups only and verify before storing coordinates.

### Gaps
- Install counts, maintenance status and test coverage for GRABOSM and Rusty0508 servers were not verified.
- Whether Claude's Messages API "MCP connector" can call these remote servers directly in production, and how it is priced, was not checked this session.
- The terms for storing Gemini Maps-grounded outputs were not read.

## Q5. Architecture patterns: cascade vs orchestrator vs retrieve-then-rerank; early exit, abstention, fusion, calibration; per-image cost and latency

### Takeaway
From first principles, the best fit is a **router-plus-evidence-graph hybrid**:
1. One cheap multimodal LLM call extracts structured clues and classifies the photo type.
2. Deterministic tools generate and verify candidates in parallel.
3. A bounded LLM adjudication (re-rank and abstain) runs only when evidence conflicts or is thin.
4. A small calibrated scorer decides exit or abstain, with per-route conformal radii.

A fully agentic ReAct loop costs about 5–10x more per image with higher variance and is harder to calibrate. A fixed linear cascade wastes compute on photos that VPR can never solve (close-up potholes, indoor elevators). The draft's "MegaLoc then LightGlue" belongs in only one branch (street scenes), and the text/OCR→gazetteer branch should be treated as the primary path. A LightGBM fuser likely overfits the few hundred labels a hackathon can produce. Use logistic regression or monotone rules plus isotonic calibration until the label count justifies more.

### Cited Findings
**Retrieve-then-rerank precedents**
- Img2Loc (SIGIR'24) treats geolocalization as text generation. It uses CLIP-based retrieval over an image-coordinate database and builds prompts for GPT-4V or LLaVA from the retrieved results plus the query image. It reports beating prior SOTA on Im2GPS3k and YFCC4k without training. — [arXiv 2403.19584](https://arxiv.org/abs/2403.19584)
- GeoRanker (NeurIPS 2025) critiques retrieve-then-select pipelines for crude similarity scores and point-wise training. It uses an LVLM to score query-candidate pairs by predicted distance with a multi-order distance loss, combining retrieved candidates with LVLM-generated GPS-only candidates and picking the top-scoring one. — [arXiv 2505.13731](https://arxiv.org/abs/2505.13731v3); [NeurIPS 2025 abstract](https://proceedings.neurips.cc/paper_files/paper/2025/hash/19b30d80dbb996efe36fd51a702800b7-Abstract-Conference.html)

**Pricing inputs (current as of 2026-10-17)**
- Claude per MTok (input / output): Haiku 5.5 $0.10 / $0.50 for prompts ≤100k tokens ($0.50 / $2.50 above). Haiku 4.5 $1 / $5. Sonnet 5.5 $2 / $10. Sonnet 5 $2 / $10 (the planned increase to $3/$15 "will not occur"). Opus 5.5 $4 / $20. Batch API is 50% off. Cache hits on Opus 5.5 and Sonnet 5.5 cost 0.05x base input. Tool use adds a system prompt of 286 tokens (Haiku 5.5, Sonnet 5.5, Opus 5.5, auto/none). Claude 4.7+ models use a tokenizer that produces about 30% more text tokens. — [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- Claude image tokens = ⌈w/28⌉ × ⌈h/28⌉. Claude 4.7+ uses the "high-resolution" tier (max long edge 2576 px, max 4,784 visual tokens), so a 1920×1080 image costs 2,691 tokens unresized, versus about 1,560 on the standard tier. A 1000×1000 image costs 1,296 tokens. Up to 600 images per request (100 for 200k-context models), 8000×8000 max; above 20 images, keep each image ≤2000 px. — [Claude vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- Gemini per MTok (input / output incl. thinking): `gemini-3.8-flash` and `gemini-3.6-flash` $0.75 / $3.75 through 31 Dec 2026, rising to $1.50 / $7.50 from 1 Jan 2027. `gemini-3-flash-preview` $0.50 / $3.00. `gemini-2.5-flash` $0.30 / $2.50. `gemini-3.5-flash-lite` $0.30 / $2.50. `gemini-3.1-flash-lite` $0.25 / $1.50. `gemini-2.5-flash-lite` $0.10 / $0.40. `gemini-3.1-pro-preview` $2 / $12. Batch is 50% off. Flash models have a free tier ("Free-tier content may be used to improve Google's products"). — [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Gemini 3 image tokens by `media_resolution`: low 280, medium 560, high 1,120, ultra_high 2,240. The default (unspecified) is 1,120. — [Gemini media resolution docs](https://ai.google.dev/gemini-api/docs/media-resolution)
- Per-call tool costs: Cloud Vision Web Detection $3.50/1k and Landmark $1.50/1k ([Cloud Vision pricing](https://cloud.google.com/vision/pricing)). Claude web search $10/1k ([Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Gemini Maps or Search grounding $14/1k after 5,000/month free ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)).
- LightGlue has built-in adaptive early stopping (`depth_confidence`) and point pruning, and runs at 150 FPS at 1,024 keypoints on an RTX 3080. — [GitHub cvg/LightGlue](https://github.com/cvg/LightGlue)

### Inferences

**A. Pattern comparison (judgement, grounded in the pricing above)**

| Pattern | How it works | Pros | Cons | Fit for GeoIssue |
|---|---|---|---|---|
| P1. Deterministic cascade, LLM only at choke points | Fixed stages; LLM for clue extraction (and maybe a final check) | Cheapest; predictable latency; easy to evaluate and calibrate | Rigid; wastes compute running VPR on hopeless images; weak on odd cases | Good backbone, but needs routing |
| P2. LLM orchestrator (ReAct / Claude tool use) | LLM chooses tools turn by turn until it answers | Flexible; handles long-tail clues (murals, festivals, construction signs); traces are explainable | 5–10x tokens (context resent each turn); latency 15–60 s; variance; may hallucinate coordinates instead of calling tools; hard to calibrate | Fallback for hard cases only, with a strict tool budget |
| P3. Retrieve candidates, then LLM re-ranks (Img2Loc / GeoRanker) | Tools produce top-K candidates with thumbnails and evidence; one LLM call picks or abstains | One extra call; LLM compares query vs candidates with all evidence; natural abstention | Zero-shot LLMs are not trained distance rankers (GeoRanker needed training); the LLM can be fooled by look-alike streets; LightGlue inliers are a more reliable same-place signal | Use as the adjudicator when deterministic evidence conflicts |
| P4 (recommended). Router + parallel tools + bounded adjudication | 1 LLM call: clues + photo-type route. Parallel deterministic candidate generation and verification. Calibrated exit. Adjudication (P3) only if ambiguous. Optional ≤3-step ReAct only if still unresolved and the item is "worth it" | Cost close to P1, accuracy close to P2 on hard cases; explicit abstention | More engineering; needs a labelled set to set thresholds | Best balance |

**B. Recommended flow (P4), Toronto-specific**
1. **Ingest (deterministic).** Post text, alt text, hashtags, author bio location, reply context, timestamp, and EXIF GPS if present. If GPS is present and inside the Toronto polygon, take a fast path to verification only.
2. **Clue call (1 multimodal LLM call, JSON schema).** Outputs:
   - OCR strings
   - named entities (streets, intersections, businesses, TTC stations/routes, landmarks)
   - scene type: {street-scene, close-up surface, indoor-transit, park/ravine, other}
   - visible infrastructure (streetcar wires, shelter type, PXO, signal, bike-share dock, ad panel)
   - day/night and shadow direction
   - issue type
   - self-rated "locatability"
3. **Route by scene type.**
   - Close-up surface with no text clues → text-only resolution, otherwise abstain early (no VPR; it cannot work).
   - Indoor-transit → station resolver (GTFS / OSM entrances and elevators).
   - Street-scene → all channels.
4. **Parallel candidate generation (deterministic, local):** `resolve_place` (text/OCR → gazetteer), `feature_search` (asset co-occurrence within 50–100 m, restricted by any text prior), and `vpr_search` (MegaLoc top-50 inside the prior region, or citywide if there is no prior). Merge into a candidate set clustered at about 30 m.
5. **Verification (deterministic):** for the top ~10 clusters, pull ≤50 m Mapillary neighbours (radius search) and run ALIKED+LightGlue; record inliers, heading agreement (Mapillary `computed_compass_angle` vs estimated heading), sun-azimuth consistency, and gazetteer match scores.
6. **Scorer, then exit or abstain.** Features: max inliers, inlier ratio, VPR top-1/top-2 similarity margin, number of independent channels agreeing within 50 m, gazetteer match type (address > intersection > street > neighbourhood), LLM locatability. The output is P(error ≤ 50 m) and a radius.
   - **Early exit 1:** exact address or intersection from text plus image consistency (no contradiction) → done, radius about 30–60 m.
   - **Early exit 2:** strong geometric verification (e.g. inliers above a threshold set on validation data) → done, radius about 15–30 m.
   - Otherwise go to step 7.
7. **Adjudication (only about 20–40% of images, estimate):** one LLM call with the query image, ≤10 candidate thumbnails (512 px), a compact evidence table and a mini-map description. The model must answer `{candidate_id | "none"}` with reasons and may not invent coordinates.
8. **Optional bounded agent (≤3 tool calls, about 5–10% of images):** the LLM may call `feature_search`, `mapillary_nearby`, `ortho_patch` or `reverse_image`, then must return to the scorer.
9. **Abstain** if the conformal radius exceeds 150–250 m (product choice). Show a moderator the top candidates instead. Human verification can use a Google Maps link-out (not embedded beside a non-Google map).

**C. Calibration and fusion**
- Use split or Mondrian conformal prediction per route (text-address, intersection, VPR-verified, station, adjudicated). Each route has very different error distributions, and a single global conformal radius would be either too wide for address hits or too narrow for VPR hits.
- With about 100–400 labelled Toronto images (realistic for a hackathon), prefer logistic regression or monotone gradient boosting with few features, then isotonic calibration. A full LightGBM over many features risks overfitting. Use the LLM's self-confidence only as one feature; it is poorly calibrated on its own (common finding, not re-verified here).
- **Where LightGBM fits:** later, once there are 1,000+ labels, as a learned ranker over candidates (features per candidate). The same scorer gives both ranking and P(correct).
- **Labels without violating ToS:** use Mapillary images held out from the index (CC BY-SA) and the team's own photos. Do not use Street View, because §3.2.3(c)(vii) forbids test and validation use.

**D. On alternatives the user raised**
- **GeoCLIP-style Toronto gallery** (image↔GPS contrastive). Gives a coarse prior (likely hundreds of metres to km at city scale) and needs training. MegaLoc over a Toronto Mapillary gallery already provides both coarse and fine retrieval with no training, so a GeoCLIP head is low priority. My inference; not benchmarked.
- **Overpass feature search as the main narrowing step.** Strong only when the clue combination is rare (e.g. streetcar wires + specific church + rail underpass). Toronto's residential grids repeat a lot. Use it as one parallel channel and a filter on VPR, not as the main step, and run it locally rather than on public Overpass.
- **LLM orchestrator first.** Justified only if most posts are odd long-tail cases. For pothole, graffiti, shelter and elevator posts, structured extraction plus deterministic resolution covers the common cases far more cheaply.

**E. Per-image cost estimates (my arithmetic from the listed prices; latency figures are rough estimates, not measured)**

Assumptions: query image downscaled to 1024×768 (Claude: 37×28 = 1,036 tokens; Gemini 3 default: 1,120 tokens); about 2,000 text tokens of instructions, tool schemas and post text; clue call output about 600 tokens. Re-rank call: query plus 10 candidates at 512×384 (Claude 266 tokens each). ReAct: 6 turns with context resent, about 32k cumulative input and about 2.3k output (+ thinking for Gemini).

| Model | P1/P4 clue call | P3/P4 re-rank call | P4 blended (clue + 30% re-rank) | P2 ReAct (6 turns, no cache) | Latency (est.) |
|---|---|---|---|---|---|
| Claude Haiku 5.5 ($0.10/$0.50) | about $0.0006 | about $0.0007 | **about $0.0008** | about $0.004 | ~1–3 s per call |
| Claude Sonnet 5.5 ($2/$10) | about $0.012 | about $0.014 | **about $0.016** | about $0.086 (about $0.04 with caching) | ~3–10 s per call; ReAct 20–60 s |
| Claude Opus 5.5 ($4/$20) | about $0.024 | about $0.028 | about $0.032 | about $0.17 | slower than Sonnet |
| Gemini 3.6/3.8 Flash ($0.75/$3.75 to Dec 2026) | about $0.008 (incl. ~1k thinking) | about $0.015 at default res, about $0.008 at low res | **about $0.011** (about 2x from Jan 2027) | about $0.044 | ~2–8 s per call (thinking-dependent) |
| Gemini 2.5 Flash-Lite ($0.10/$0.40) | about $0.0006 | about $0.001 | about $0.001 | about $0.004 | ~1–3 s |
| Local Qwen3.5-9B Q4 / Qwen3.5-4B / Gemma 4 E4B on RTX 4060 8 GB | $0 marginal | $0 | $0 | $0 | ~5–15 s per call for 9B (est.); re-rank with 11 images may exceed 8 GB KV/context. Prefer API for re-rank |

- Non-LLM pipeline (local, est. on a 4060 laptop): MegaLoc embed about 20–50 ms; FAISS flat search over 100–200k × 8,448-d on CPU about 0.1–0.3 s (or PCA-512 for milliseconds); ALIKED+LightGlue on 10–20 pairs about 0.3–1 s; Mapillary thumbnail fetches for 10–20 candidates about 0.5–2 s in parallel (network-bound). **End-to-end P4 is about 3–8 s typical, about 10–20 s with adjudication. P2 is about 20–60 s.**
- At 1,000 images/day: P4 with Haiku 5.5 is about $1/day; P4 with Sonnet 5.5 about $16/day; P2 with Sonnet 5.5 about $40–86/day. Add Cloud Vision Web Detection on 10% of images for about $0.35/day.
**F. ≤10 m update (after the requirement change; details in Q8)**
- **The early exits in B no longer meet the target.** "Exact address or intersection from text" and "VPR top-1 plus LightGlue inliers" give about 10–60 m. They become region narrowing (down to roughly 30–200 m), not exits.
- **A new final stage is needed: metric anchoring.**
  - (i) **Asset snapping.** The LLM or detector lists visible City-inventoried objects and their arrangement (shelter, poles by subtype, hydrant, bike ring, signal, PXO). A deterministic matcher finds the configuration of City assets (with IDs, ±0.3 m for poles) inside the narrowed region that fits the observed types and relative bearings.
  - (ii) **Geometric registration against nearby reference images** whose poses are known (Mapillary `computed_*`, ideally several images in the same `merge_cc`).
  - (iii) **Projection of the issue location** from the camera using the ground plane (City 2023 LiDAR-derived TIN), clamped to the semantic surface: pothole → edge-of-road polygon; sidewalk crack → sidewalk polygon; graffiti → building-outline edge or asset.
- **Only claim ≤10 m when an absolute anchor confirms the location.** That means a uniquely matched asset configuration, or registration to ≥2 reference images with consistent poses. Otherwise report the coarser conformal radius. Per-route conformal calibration will show which routes ever reach 10 m.
- **LLM role at 10 m:** describe objects, their order and left/right relations (structured JSON), and adjudicate between 2–5 candidate asset configurations with crops. Never output coordinates.

- **Model choice:** use a cheap model (Haiku 5.5 or Gemini Flash-Lite/Flash) for the clue call and a stronger model (Sonnet 5.5 or Gemini 3.x Flash with thinking) only for adjudication. Downscale images to ≤1024 px long edge for Claude 4.7+ models (their high-res tier otherwise spends 2,691+ tokens on a 1080p photo), and use `media_resolution=low/medium` for Gemini candidate thumbnails. The Gemini Flash free tier is fine for hackathon development, but free-tier content may be used by Google, so watch privacy for social-media images.

### Gaps
- No published latency measurements for Haiku 5.5, Sonnet 5.5 or Gemini 3.6/3.8 Flash on image inputs were found. The latency figures are rough estimates.
- No benchmark compares zero-shot LLM re-ranking against LightGlue-inlier re-ranking for same-place verification at city scale. GeoRanker's gains required training.
- Img2Loc's exact retrieval settings and street-level (1 km) accuracy numbers were not extracted (only the abstract was read).
- Gemini 2.5 image token counts (the 258-tokens-per-tile rule) were not verified in current docs. The Flash-Lite cost assumes about 1–1.5k tokens per image.
- No data on what share of Toronto civic-issue posts contain usable text clues. This drives the whole design and should be measured on the team's Bluesky corpus (`spikes/data/corpus`).

## Q6. Open-source VLMs with tool calling that fit 8 GB VRAM (quantized), and their OCR and geo ability

### Takeaway
Qwen3.5-9B (Apache-2.0, native vision, strong OCR at OCRBench 89.2, tool-calling at BFCL-V4 66.1) is the strongest documented candidate. At 4-bit it should fit in 8 GB alone, but not alongside MegaLoc, LightGlue and a re-rank prompt with many images. Qwen3-VL-8B and Gemma 4 (E4B / 12B, Apache-2.0, function calling) are alternatives. A local VLM is viable for the clue-extraction call (privacy, zero marginal cost). Use an API model for multi-image adjudication. No source benchmarks these small models on fine-grained (street-level) geolocation.

### Cited Findings
- **Qwen/Qwen3.5-9B:** "Causal Language Model with Vision Encoder" (image and video input), 9B (10B in safetensors metadata), 262,144-token native context (1.01M with YaRN). The card says it "excels in tool calling" (BFCL-V4 66.1, TAU2-Bench 79.1), with a tool-call parser for serving. OCRBench 89.2, OmniDocBench1.5 87.7, CC-OCR 79.3, MMMU 78.4, RealWorldQA 80.3. Apache-2.0. 581 derived quantizations on the Hub, usable in llama.cpp, Ollama or LM Studio. — [HF: Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B)
- **Qwen3-VL-8B:** GGUF builds run in llama.cpp (llama-mtmd-cli with a separate mmproj vision projector). The Thinking variant's chat template supports multi-step tool calling with JSON arguments (secondary source). VRAM estimates for Q4_K_M conflict: about 5.9–6 GB in two directories vs "about 12 GB" in one guide. — [codersera: Qwen3-VL 4B vs 8B](https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/); [aiindigo: Qwen3-VL-8B-Thinking GGUF](https://aiindigo.com/tool/qwen3-vl-8b-thinking-gguf); [llmrun.dev: Qwen3-VL-8B](https://llmrun.dev/model/qwen-qwen3-vl-8b-instruct)
- **Gemma 4:** initial release 31 Mar 2026 (E2B, E4B, 26B A4B, 31B), with a 12B "Unified" model added 3 Jun 2026 per Google's release log. Image input with variable aspect ratio and resolution across the family. Native function calling. Apache 2.0. Sources disagree on exact dates and sizes. — [Google Gemma releases](https://ai.google.dev/gemma/docs/releases?hl=en); [LM Studio: Gemma 4](https://lmstudio.ai/models/gemma-4); [Wikipedia: Gemma](https://en.wikipedia.org/wiki/Gemma_(language_model))
- **OCR-specialist small models** (PaddleOCR-VL-1.6, MinerU2.5-Pro, GLM-OCR, about 0.9–1.2B) lead document OCR benchmarks, but they target documents, not street scenes. — [Roboflow](https://blog.roboflow.com/best-open-source-ocr-models/)

### Inferences
- **VRAM budget on an 8 GB RTX 4060 Laptop.** A 9B model at Q4_K_M is about 5.5–6 GB of weights, plus about 0.6–1 GB for the vision projector, plus KV cache. That leaves little for MegaLoc (DINOv2-based, roughly 0.3–0.6 GB fp16, my estimate), ALIKED+LightGlue (about 0.5–1 GB) or multi-image prompts. Options:
  - (a) time-share the GPU (load the VLM for the clue call, then unload it);
  - (b) run Qwen3.5-4B or Gemma 4 E4B at Q4 (about 3 GB) beside the vision stack;
  - (c) keep local models for OCR and clue extraction only, and send re-ranking to Haiku 5.5 or Gemini Flash.

  With 31 GB system RAM, CPU offload of some layers is possible but slow.
- **Tool calling locally:** serve with llama.cpp server or vLLM using the model's tool-call parser and validate JSON outputs. Small models are more likely to emit malformed calls or skip tools, which is another reason to prefer the deterministic-pipeline pattern (P4), where the LLM fills one JSON schema instead of driving a loop.
- **Geo ability:** small open VLMs know Toronto's landmarks and major streets but are unlikely to localise ordinary streets from appearance alone. Use them for reading and describing, not for guessing coordinates. Their outputs should feed `resolve_place` and `feature_search`, never be used as final coordinates.

### Gaps
- No measured tokens/s or VRAM figures for Qwen3.5-9B or Gemma 4 E4B on an RTX 4060 Laptop were found. VRAM estimates for Qwen3-VL-8B Q4 conflict (about 6 GB vs about 12 GB).
- No benchmark of small open VLMs on scene-text OCR of Toronto-style street signs, or on street-level geolocation, was found.
- Qwen3.5 small-model sizes other than 9B (e.g. 4B) and their tool-calling scores were not verified this session.
- MegaLoc's backbone and VRAM were not stated on its GitHub page. The DINOv2 basis is assumed from my background knowledge.

## Q7 (PRIORITY). Google Street View for live candidate comparison: terms, pricing, pano accuracy, and Toronto coverage vs Mapillary, Apple Look Around, Bing Streetside, KartaView and Panoramax

### Takeaway
No clause in the current Google Maps Platform Terms (ToS last modified 26 Aug 2026; Service Specific Terms last modified 15 Oct 2026) permits analysing Street View images in your own backend. Several clauses cut against it:
- §3.2.3(a): no extracting "for use outside the Services";
- §3.2.3(c): no "creat[ing] content based on Google Maps Content", with the close analogue "construct an index of tree locations within a city from Street View imagery";
- §3.2.3(c)(vii): no using Maps Content to "test, validate" ML models;
- §3.2.3(e): no use near a non-Google map.

Fetching Static API images at candidate locations, feature-matching them against a user photo, and discarding them avoids the caching and indexing clauses but still derives location data from Street View content. I rate this as **high legal risk and not defensible without written permission from Google**. GSV is cheap and dense: metadata is free and unlimited, Static Street View has 10,000 free/month then $7 per 1,000, and Street View Tiles have 100,000 free/month then $2 per 1,000. But its safe role is human verification in a Google-rendered view. Mapillary (CC BY-SA, API-friendly) is the only clean source for automated live comparison. Its Toronto density is unmeasured and must be measured before committing. Apple Look Around covers Toronto but has only a display widget (MapKit JS). Bing Streetside is on a path to retirement. KartaView timed out. Panoramax is thin (about 32k images).

### Cited Findings
**Terms: what applies to Street View**
- The current Service Specific Terms list per-service sections (Address Validation, Air Quality, Directions, Distance Matrix, Geocoding, Geolocation, Google Earth, Maps Datasets, Maps Grounding Lite, Navigation SDK, Places, Pollen, Roads, Route Optimization, Routes, Solar, Weather...) and **have no Street View-specific section**. The only Street View mention is "Google ID Caching": "Customer may cache ... (b) pano_ID, from Street View Static API". So Street View falls under the general ToS restrictions. — [GMP Service Specific Terms (last modified Oct 15, 2026)](https://cloud.google.com/maps-platform/terms/maps-service-terms)
- ToS §3.2.3(a) No Scraping: "Customer will not export, extract, or otherwise scrape Google Maps Content for use outside the Services. For example, Customer will not: (i) pre-fetch, index, store, reshare, or rehost Google Maps Content outside the services; (ii) bulk download Google Maps tiles, Street View images, ..." — [GMP ToS (last modified Aug 26, 2026)](https://cloud.google.com/maps-platform/terms)
- ToS §3.2.3(b) No Caching: "Customer will not cache Google Maps Content except as expressly permitted under the Maps Service Specific Terms." — [GMP ToS](https://cloud.google.com/maps-platform/terms)
- ToS §3.2.3(c) No Creating Content From Google Maps Content: "Customer will not create content based on Google Maps Content. For example, Customer will not: ... (v) construct an index of tree locations within a city from Street View imagery; ... or (vii) use Google Maps Content to improve machine learning and artificial intelligence models, including to train, test, validate or fine-tune the models." — [GMP ToS](https://cloud.google.com/maps-platform/terms)
- ToS §3.2.3(e) No Use With Non-Google Maps: "Customer will not use the Google Maps Core Services with or near a non-Google Map in a Customer Application. For example, Customer will not ... (ii) display Street View imagery and non-Google Maps on the same screen". — [GMP ToS](https://cloud.google.com/maps-platform/terms)
- ToS §3.2.1(a): Customer will not "copy, modify, create a derivative work of, reverse engineer ... or otherwise attempt to extract any or all of the source code". The derivative-work wording here is about the Services' source code. — [GMP ToS](https://cloud.google.com/maps-platform/terms)
- ToS §3.2.4 Benchmarking: publicly disclosed comparative tests of the Services must include everything needed to replicate them. — [GMP ToS](https://cloud.google.com/maps-platform/terms)
- Street View Static API Policies (updated 2026-10-15): "Content pre-fetching, indexing, storing, or caching is generally prohibited, except for place IDs and panorama IDs"; "you can store panorama ID values indefinitely". Attribution must be visible and unmodified. **The policies page itself contains no clause on image analysis or derived data.** — [Street View Static API Policies](https://developers.google.com/maps/documentation/streetview/policies)
- For contrast, Google's sanctioned LLM route (Maps Grounding, SST §10) allows caching Grounded Output for up to 30 days only "for the purpose of evaluating and optimizing the performance or display", and forbids using it "to train, develop, or improve any machine learning models or artificial intelligence systems" and to "extract or otherwise separate Google Maps Content from the Grounded Output". — [GMP Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)

**Pricing and quotas (USD per 1,000 events, monthly)**
- Static Street View (Essentials): 10,000 free/month, then $7.00 (to 100k), $5.60 (100k–500k), $4.20 (500k–1M), $2.10 (1M–5M), $0.53 (5M+). — [GMP pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- Dynamic Street View (Pro, interactive panoramas): 5,000 free/month, then $14.00 down to $1.05. — [GMP pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- Street View Metadata (Essentials): unlimited free. The metadata docs say "No quota is consumed when you request metadata". Responses return `pano_id`, `location` (lat/lng), `date` (year-month or year), `copyright` and `status`. — [GMP pricing](https://developers.google.com/maps/billing-and-pricing/pricing); [Street View metadata docs](https://developers.google.com/maps/documentation/streetview/metadata)
- Map Tiles API Street View Tiles (Essentials): 100,000 free/month, then $2.00 per 1,000 (to 1M), down to $0.20 above 50M. — [GMP pricing](https://developers.google.com/maps/billing-and-pricing/pricing)

**Pano position accuracy**
- Google publishes no positional accuracy figure for panoramas. The metadata page contains the sentence "the panorama imagery is accurate to 50 meters". Its context (likely the pano search tolerance) could not be confirmed. — [Street View metadata docs](https://developers.google.com/maps/documentation/streetview/metadata)
- ISPRS 2012 (NCHU campus): intersecting a pair of GSV panoramas against surveyed points gave RMS errors of about ±0.5 m (X), ±1.2 m (Y) and ±5.8 m (height). "Errors in Google provided GSV positional parameters dominate". — [ISPRS Annals I-4, 2012](https://isprs-annals.copernicus.org/articles/I-4/305/2012/isprsannals-I-4-305-2012.html)
- An AprilTag-ground-truth study found per-panorama pose errors mostly 0.4–6 m, with one outlier around 12 m. — [arXiv 1503.04287](https://arxiv.org/pdf/1503.04287)
- A 2024 study notes "significant deviations in some locations" between GSV reported coordinates and known map locations, despite the expected RTK-GPS and laser data. — [arXiv 2411.08231](https://arxiv.org/pdf/2411.08231)

**Toronto coverage of alternatives**
- **Google:** Street View cars began covering the GTA in early 2009 and Toronto went live that year. — [TechWyse 2009](https://techwyse.com/blog/online-innovation/toronto-canada-now-appearing-in-google-street-view). A Street View tricycle imaged the UTM campus (year not stated, probably about 2012). — [UTM news](https://www.utm.utoronto.ca/node/2937). No source found on St. George campus or laneway coverage.
- **Apple Look Around:** released in December 2020 for southern Canada including Toronto. — [Apple Newsroom Canada, Dec 2020](https://www.apple.com/ca/newsroom/2020/12/apple-delivers-all-new-apple-maps-across-canada/); [Justin O'Beirne, Look Around release #11](https://justinobeirne.com/look-around-release-11). Apple backpack mapping rigs walked Toronto in 2021. — [blogTO 2021](https://blogto.com/tech/2021/09/apple-mapping-toronto-huge-backpack-camera-rigs). MapKit JS has `LookAround` and `LookAroundPreview` classes (from MapKit JS 5.79.0) for interactive display, and "not all places support Look Around". — [MapKit JS LookAround docs](https://developer.apple.com/documentation/mapkitjs/lookaround.md). The current MapKit terms on image extraction were not found.
- **Bing Streetside:** Bing Maps for Enterprise ends 30 June 2028 (migrate to Azure Maps). Basic accounts stopped working 30 June 2025. Users report Streetside no longer loading on bing.com/maps (community report, not official). Toronto coverage unknown. — [Microsoft Bing Maps coverage page](https://learn.microsoft.com/zh-tw/bingmaps/coverage); [OSM community: Bing Streetside discontinued?](https://community.openstreetmap.org/t/bing-streetside-discontinued/137189)
- **KartaView:** the API timed out for Toronto queries (live probe, see Q1). — [KartaView API live probe](https://api.openstreetcam.org/2.0/photo/?lat=43.6532&lng=-79.3832&radius=300&itemsPerPage=20)
- **Panoramax:** about 31.9k items in the first 100 collections intersecting the Toronto bbox, mostly one contributor, CC-BY-SA-4.0 (live probe, see Q1). — [Panoramax API live probe](https://api.panoramax.xyz/api/collections?bbox=-79.64,43.58,-79.11,43.86&limit=100)
- **Mapillary:**
  - API capacity is ample: radius search up to 50 m with ≤100 results, entity API 60k/min, tiles 50k/day. — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
  - No Toronto image count was found. Coverage is community-driven and "uneven". — [atlas.co: Mapillary](https://atlas.co/data-sources/mapillary)
  - NUS Global Streetscapes (about 10M Mapillary + KartaView images from 688 cities, 300+ attributes per image, on Hugging Face) could be filtered to Toronto to get a count. — [NUS Global Streetscapes](https://ual.sg/project/global-streetscapes)
- **City of Toronto traffic cameras** (an open-data alternative reference view): 336 cameras with number, name, WGS84 position, live image URL and four "comparison" reference images (North/East/South/West). — [CKAN traffic-cameras](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20camera); live CSV (336 rows) from [traffic-camera-list-4326.csv](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/a3309088-5fd4-4d34-8297-77c8301840ac/resource/8f9d6db7-faa0-405c-9627-b0298489cf9f/download/traffic-camera-list-4326.csv)

### Inferences
- **Q7.1, on-the-fly fetch, match and discard.**
  - It avoids §3.2.3(a)(i)'s "pre-fetch, index, store" and §3.2.3(b) caching if images never persist.
  - It still (1) extracts Street View pixels into a non-Google computer-vision pipeline ("for use outside the Services", §3.2.3(a)), and (2) produces location data derived from Street View imagery. That is structurally the same as example (v), "index of tree locations ... from Street View imagery", under §3.2.3(c).
  - Results would then be shown on GeoIssue's own (non-Google) map, which brushes against §3.2.3(e).
  - Evaluating accuracy against GSV-matched results is "test, validate" (§3.2.3(c)(vii)).
  - Map Tiles API Street View tiles are Google Maps Content under the same ToS, so switching from Static to Tiles does not change the analysis.
  - Bottom line: **do not make GSV comparison an automated core step.** If the team insists, get written confirmation from Google sales or legal. This is not legal advice.
- **Allowed and low-risk GSV uses:**
  - A moderator clicks "open in Google Maps/Street View" (link-out, separate screen) to eyeball a candidate.
  - Storing `pano_id`s (explicitly allowed) so the moderator link opens the right pano.
  - Calling metadata (free) to show "Street View available here". Even that is Maps Content and should not be mixed onto a non-Google map.
- **Cost if GSV were used anyway (for scale only):** 10 candidates × 4–6 headings per photo is 40–60 Static calls, about $0.28–0.42 per photo beyond the 10k free/month (which covers only about 170–250 photos/month). Street View Tiles are about 3.5x cheaper per event, but a full pano needs many tiles.
- **Pano accuracy vs the 10 m target:** published measurements suggest GSV pano positions are usually within a few metres, sometimes worse. Even GSV would not guarantee ≤10 m without registration to an absolute anchor.
- **Q7.4, is Mapillary alone dense enough?** Unknown until measured. Plan, using the team's token (about 450 z14 coverage tiles plus City layers):
  - (a) the share of Centreline road segments, by class (arterial, collector, local, laneway), with ≥1 Mapillary image within 10 m and captured in the last 3 years;
  - (b) the share of transit shelters, bike rings, hydrants and traffic-signal poles with ≥2 images within 20 m, pointing toward the asset (compare `computed_compass_angle` with the bearing to the asset);
  - (c) pano share;
  - (d) the share of images in large `merge_cc` components (better poses).

  If (b) is below about 50% for the issue types GeoIssue cares about, live Mapillary comparison cannot be the core step. Asset snapping (Q8) plus City traffic-camera views and orthophotos must carry the 10 m claim, with Mapillary as a bonus where present. My prior is dense coverage on arterials and downtown, sparse on residential side streets, laneways, parks and campuses. That is typical of crowd-sourced imagery, but I have not verified it for Toronto.
- **Apple Look Around and Bing Streetside are not usable sources** for automated comparison. Look Around is a display widget in MapKit JS with no image download. Streetside is being retired with Bing Maps.

### Gaps
- No primary source quantifies Google, Apple or Mapillary coverage density for Toronto side streets, laneways or campuses. The Global Streetscapes per-city counts were not extracted.
- No authoritative Google statement addresses "transient analysis" of Street View images. Google's separate "Geo Guidelines" permissions page (about.google brand resource centre) was not read.
- Street View Static API maximum image size and current per-minute quotas were not re-verified.
- Apple MapKit JS terms on Look Around imagery reuse were not found.
- The meaning of "accurate to 50 meters" on the GSV metadata page was not resolved.

## Q8. Data and tools for ≤10 m precision: reference-position accuracy, LiDAR, orthophotos, massing, and snap-able point assets with IDs

### Takeaway
At 10 m, the limiting factor is the absolute accuracy of the reference data, not retrieval. Toronto's open topographic layers are the best absolute anchors available to the team:
- 305,237 poles, typed and digitised at ±30 cm from aerial imagery, with elevation and derived height;
- aerial-derived tree points, building outlines, edge-of-road and sidewalk polygons;
- 8 cm orthophotos.

Inventoried assets with IDs (5,752 transit shelters `SH-xxxxx`, 42,947 fire hydrants `HY...`, 17,137 bike rings `BP-xxxxx`, signals, PXOs, cameras) let a detected object snap to a surveyed point. Mapillary positions (raw GPS or SfM-computed) are typically several metres off and inconsistent, so they serve for relative geometry and registration, not as the final coordinate. Text geocoding (street, intersection centroid, neighbourhood), GTFS stop names, Bike Share stations, VPR top-1 positions, Overpass feature search, reverse image search and LLM guesses can only narrow the region at 10 m.

### Cited Findings
**Mapillary reference-position fields and accuracy**
- Field definitions (verbatim):
  - `geometry` "GeoJSON Point geometry" (original)
  - `computed_geometry` "location after running image processing"
  - `altitude` "original altitude from camera Exif"
  - `computed_altitude`
  - `compass_angle` "original compass angle"
  - `computed_compass_angle`
  - `computed_rotation` "corrected orientation of the image as an axis-angle rotation vector"
  - `camera_parameters` "focal length, k1, k2"
  - `atomic_scale` "scale of the SfM reconstruction around the image"
  - `merge_cc` "ID of the connected component of images that were aligned together"
  - `sfm_cluster` "URL to the point cloud data in JSON and compressed by zlib"
  - `mesh` "URL to the mesh"
  - `quality_score` "predicted visual quality of the image in the range [0.0, 1.0]"
  - `make` and `model` (camera)
  - map feature `aligned_direction` "compass angle that the object faces", plus `first_seen_at`, `last_seen_at` and `images`.

  — [Mapillary API docs](https://www.mapillary.com/developer/api-documentation)
- Mapillary staff (forum): computed positions come from OpenSfM using image and GPS data, "an amalgamation of all images in a sector". Computed positions are "not corrected positions". Users report computed_geometry is sometimes worse than raw GPS and sometimes better. Bad GPS degrades computed results. — [Mapillary forum: How does Mapillary correct GPS location](https://forum.mapillary.com/t/how-does-mapillary-correct-gps-location/7193); [forum: estimated position severely off](https://forum.mapillary.com/t/the-estimated-position-is-sometimes-severely-off-causing-wrong-object-placements-on-map/8311); [forum: SfM lat/lon](https://forum.mapillary.com/t/sfm-lat-lon-not-in-api-lat-lon-question/2881)
- State of the Map 2022: the accuracy of Mapillary-generated map data "is highly related to the GPS accuracy of the capture device", and 3D reconstruction mitigates some of this. — [SotM 2022 talk](https://2022.stateofthemap.org/sessions/DKLT7X/)

**City and Province elevation, ortho and massing**
- City TIN: "derived from a 2023 LiDAR-derived 2.5 metre resolution bare-earth elevation source". Attributes: average elevation, slope, aspect. NAD83(CSRS) MTM10 (EPSG:2952), CGVD2013 vertical. SHP. — [CKAN triangular-irregular-network-tin](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=elevation)
- SolarTO was produced by GIS analysis of LiDAR. Its outputs are rooftop solar estimates, not raw LiDAR. — [CKAN solarto](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=lidar)
- Ontario Classified Point Cloud (Lidar-Derived): Open Government Licence – Ontario, 1 km × 1 km LAZ tiles, "specifications, parameters, accuracy and sensors may vary by project". Listed range 2009–2019. — [data.ontario.ca](https://data.ontario.ca/dataset/ontario-classified-point-cloud-lidar-derived)
- A GeoHub mirror lists a "GTA Lidar Point Cloud 2023" project. The 2023 GTA DTM packages carry the `on-oglo` licence code. — [IRIU mirror of GTA 2023 DTM](https://dev.donnees.iriu.ca/dataset/7c3d7022-2631-45bc-8f6b-f3d51b7779a7/resource/3df5be0b-afa6-46de-a8f2-d65d9a3b41e0). This conflicts with the University of Waterloo library record for GTA 2023 lidar, which says it is for "personal use for academic, research, and/or teaching purposes" under a data release agreement. — [UWaterloo geospatial: lidar](https://uwaterloo.ca/lib-geospatial/collections/canadian-geospatial-data-resources/ontario/lidar-cloud-point-and-raster-elevation-data)
- City orthophotos:
  - "City of Toronto Orthophoto Current Year" is a cached Web Mercator service with 24 levels of detail (finest display resolution about 0.019 m/px at LOD 23, which is not the capture GSD), copyright "City of Toronto". — [cot_ortho MapServer JSON](https://gis.toronto.ca/arcgis/rest/services/basemap/cot_ortho/MapServer?f=pjson)
  - Archived colour years 2015–2022 at 8 cm. The `web-map-services` dataset is listed under OGL-Toronto. — [CKAN web-map-services](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=orthoimagery)
- 3D Massing: yearly SHP and multipatch (2016–2019+), AutoCAD/SKP tiles, "for information and illustrative purposes only". Last refreshed 2025-12-05. — [CKAN 3d-massing](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=3D%20massing)

**Point and area assets usable as absolute anchors (live CKAN probe and CSV downloads, 2026-10-17)**

| Dataset | Count | ID / key fields | Positional quality stated | Licence (CKAN) |
|---|---|---|---|---|
| `topographic-mapping-poles` | **305,237** (Street Light 207,923; Misc 73,880; Traffic Signal 10,267; Pedestrian Light 7,094; Street Light + Signal 5,697; Hydro Tower 376) | `OBJECTID`, `SUBTYPE_DESC`, `ELEVATION`, `DERIVED_HEIGHT`, maintenance dates | "manual digitization from aerial imagery ... ground accuracy of +- 30cm". Poles near tall buildings or in deep shadow may be missing, and construction changes lag | None listed |
| `street-furniture-transit-shelter` | **5,752** (5,444 Existing, 308 Temporarily Removed) | `ID` (e.g. `SH-02003`), `SITEID` (e.g. `T8594`), `STYLE`, `BARCODE`, `POSTERBOARD`, fronting street, side, direction | Not stated | OGL-Toronto |
| `fire-hydrants` | **42,947** | `FACILITYID` (e.g. `HY2010909`), `LOCDESC` (address), `FIELDVERIFIED` (Yes/No) | Not stated | Not specified |
| `water-hydrants` | n/a | ownership and management groups ("general location") | "general location" | Not specified |
| `street-furniture-bicycle-parking` (locking rings) | **17,137** (16,830 Existing) | `ID` (e.g. `BP-11699`), address, fronting street, side, `ASSETTYPE` | Not stated | Not specified |
| `bicycle-parking-racks`, high-capacity, indoor stations | n/a | rack IDs | Not stated | Not specified |
| `street-furniture-bench`, `-litter-receptacle`, `-poster-board`, `-poster-structure`, `-publication-structure`, `-public-washroom` | n/a | Same schema family as shelters (ID, address, side) | Not stated | OGL-Toronto / not specified |
| `traffic-signals-tabular`, pedestrian crossovers, beacons | n/a | Signal attributes | Not stated | None listed |
| `traffic-cameras` | **336** | `REC_ID`, main and cross road, 4 direction reference image URLs | Not stated | Not specified |
| `red-light-cameras` | n/a | — | — | OGL-Toronto |
| `topographic-mapping-physical-location-of-trees` | n/a | Point layer "collected from high resolution aerial photography" | Aerial-derived (contrast: `street-tree-data` is geocoded to the parcel address and "not accurate") | OGL-Toronto |
| `topographic-mapping-edge-of-road`, `-physical-area-of-sidewalks`, `-building-outlines` | n/a | Polygons from high-resolution aerial photography | Aerial-derived | None / not specified |
| `pedestrian-network` | n/a | Sidewalk and crossing graph tied to intersections, signals and crossovers | Partly "manual collection from aerial imagery" | None |
| `water-valves`, `water-fittings` | n/a | Valve characteristics; "general location" | "general location" | Not specified |

Sources: [poles CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/cdf46145-7a91-4f1c-9dd1-91cd58338238/resource/5ce5f150-f0be-4417-af94-d531594d61f4/download/poles-4326.csv) and [CKAN poles](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=pole); [fire hydrants CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/fbfcf7fa-1026-4b29-bff6-0765ca3f8a54/resource/4575b5ca-59a1-41f5-93b4-e735577fbe53/download/fire-hydrants-data-4326.csv) and [CKAN hydrants](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=hydrant); [bike rings CSV](https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/71e6c206-96e1-48f1-8f6f-0e804687e3be/resource/f8b62a45-b4ef-4273-ac0a-5d4c95dcf554/download/street-furniture-bicycle-parking-data-4326.csv) and [CKAN bicycle parking](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=bicycle%20parking); [CKAN street furniture](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=street%20furniture) (shelter counts from the CKAN CSV cached in the repo at `spikes/data/opendata/street-furniture-transit-shelter.csv`); [CKAN topographic mapping](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=topographic%20mapping); [CKAN lidar (trees)](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=lidar); [CKAN sidewalk](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=sidewalk); [CKAN traffic cameras](https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_search?q=traffic%20camera)

### Inferences
**What can and cannot contribute at ≤10 m**

| Tool or data | Can it deliver ≤10 m alone? | Role at a 10 m target |
|---|---|---|
| Text → street name / neighbourhood | No (hundreds of metres to km) | Region narrowing only |
| Text → intersection centroid (Intersection File) | No. An intersection plus its approaches spans 30–100 m and the issue may be on any leg | Narrowing. Reaches ~10 m only if the text gives a corner ("NE corner") **and** an asset snap confirms |
| Text → address point (Address Points) | Sometimes. Points sit inside the parcel or building, so project to the curb. Along-street error is about the frontage width | Good prior. Confirm with an asset snap |
| GTFS stop / Bike Share station / Overture POI | Borderline (stop and station coordinates are 5–20 m objects; precision not documented) | Narrowing, then snap to the shelter ID or dock |
| VPR top-1 Mapillary position | No (raw or computed GPS is several metres off, plus camera-to-issue offset) | Narrowing to 20–50 m; supplies reference images for registration |
| LightGlue/RoMa against Mapillary refs | Only with good reference poses (same `merge_cc`, consistent `computed_*`, ≥2 refs) | Relative pose. Absolute accuracy is limited by reference pose error |
| **Asset snapping to City inventories** (poles ±0.3 m, shelters, hydrants, rings, signals, aerial trees) | **Yes**, if the matched configuration is unique | **Primary absolute anchor** |
| Orthophoto 8 cm / edge-of-road / sidewalk polygons | Yes as constraints (e.g. pothole must lie in the roadway) | Verification and clamping; LLM can compare crosswalk or lane layouts at shortlisted spots |
| City 2023 LiDAR TIN (2.5 m) | Supports ground-plane projection (camera height and slope) | Converts camera pose to issue position |
| City traffic cameras (336, fixed) | Yes near those intersections (fixed known views) | Reference views at major intersections, open data |
| Overpass/OSM feature search | No (OSM node accuracy varies) | Narrowing |
| Reverse image search, GeoCLIP, LLM-guessed coordinates | No | Narrowing or provenance only |
| Sun/shadow | No (heading only) | Constrains camera heading during registration |
| Google Street View | Possibly technically, but see Q7 (ToS) | Human verification only |

- **The "asset constellation" matcher is the key new deterministic tool.** Input: the LLM's structured list of visible assets with types, rough bearing order and distances (e.g. "shelter, left, ~5 m; street-light pole behind it; hydrant on right curb"). Search inside the narrowed region (STRtree over poles by subtype, shelters, hydrants, rings, signals, aerial trees). Score candidate camera positions on the sidewalk or roadway by how well predicted bearings and order match. With 305k typed poles at ±30 cm plus sparse distinctive assets (shelters, hydrants), short constellations are often unique within a 100–200 m region. This is my judgement and needs testing on labelled photos.
- **Reference-position hygiene for Mapillary:**
  - prefer images whose `computed_geometry` and `geometry` agree within a few metres;
  - prefer images in large `merge_cc` components with high `quality_score` and recent `captured_at`;
  - use `computed_compass_angle` rather than `compass_angle`;
  - treat Mapillary map-feature positions as approximate (triangulated from crowd images) and cross-check against City assets before use;
  - `sfm_cluster` and `mesh` provide local 3D structure for registration (another researcher covers the methods), but their absolute georeferencing inherits SfM and GPS error.
- **Licences:**
  - City layers are mostly OGL-Toronto (attribute and keep licence notices); several CKAN entries leave the licence blank.
  - Ontario lidar point cloud and DTM: OGL-Ontario per the data.ontario.ca listing, but the GTA 2023 point cloud has a conflicting restrictive record. Use the City's TIN (2023 LiDAR-derived) or the OGL-Ontario DTM.
  - Mapillary and Panoramax are CC BY-SA 4.0.
  - Do not use Google content as a reference.
- **Hackathon scope:** the asset layers above total under about 100 MB as CSV (poles 54 MB, hydrants 13 MB, rings 3.3 MB, from the downloads made for these notes). They load easily into DuckDB or GeoPandas in 31 GB RAM.

### Gaps
- No positional-accuracy statements were found for shelters, hydrants, bike rings, benches or bins (only poles state ±30 cm). Whether visible ID labels exist on Toronto shelters, hydrants or poles (which would allow OCR → ID → exact point) was not verified.
- Toronto Hydro utility-pole IDs and a TTC stop-pole dataset with surveyed positions were not found as open data.
- The licence and availability of the GTA 2023 LiDAR **point cloud** (vs the DTM) is unresolved. Point density and accuracy for that project were not found.
- The capture GSD and year of the "current year" orthophoto service were not confirmed (24 cache levels, archived years listed at 8 cm).
- No measured statistics on Mapillary `computed_geometry` error in Toronto exist. The team could measure it by comparing Mapillary images of poles against the ±30 cm City pole layer.
